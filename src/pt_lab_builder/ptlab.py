#!/usr/bin/env python3
"""Packet Tracer file codec, activity assessment, and saved-file grading helpers."""
import copy
import datetime
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from .paths import activity_base_path, codec_path, open_packet_tracer

B, G, R, Y, D, Z = "\033[1m", "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def die(msg):
    sys.exit(f"{R}lab pt:{Z} {msg}")


# ---------------------------------------------------------------- file codec
def ptcrypt(mode, src, dst):
    try:
        executable = codec_path()
    except FileNotFoundError as exc:
        die(str(exc))
    p = subprocess.run([str(executable), mode, src, dst], capture_output=True, text=True)
    if p.returncode:
        die(f"ptcrypt {mode} failed on {src}: {p.stderr.strip()}")


def read_pkt(path):
    with tempfile.TemporaryDirectory() as tmp:
        x = os.path.join(tmp, "f.xml")
        ptcrypt("decode", path, x)
        with open(x, "rb") as fh:  # the Wizard password salt (ACTIVITY VALUE) holds XML-forbidden control bytes
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", fh.read().decode("utf-8", "replace"))
        return ET.ElementTree(ET.fromstring(text))


def write_pkt(tree, path):
    with tempfile.TemporaryDirectory() as tmp:
        x = os.path.join(tmp, "f.xml")
        # Packet Tracer's activity reader (CTreeNode::deserialize(QXmlStreamReader*)) steps through the
        # assessment tree with a fixed number of readNext() calls: it expects every element on its own
        # indented line, as Packet Tracer writes it, and <X></X> rather than <X />.
        ET.indent(tree, space=" ")
        tree.write(x, encoding="utf-8", xml_declaration=False, short_empty_elements=False)
        ptcrypt("encode", x, path)


# ---------------------------------------------------------------- XML helpers
def devices(tree):
    out = {}
    for d in tree.getroot().find("NETWORK/DEVICES"):
        out[d.findtext("ENGINE/NAME")] = d
    return out


def set_config(dev, text):
    """Replace the running-config of a router/switch/ASA. Packet Tracer re-parses it on load (a powered-on device)."""
    eng = dev.find("ENGINE")
    rc = eng.find("RUNNINGCONFIG")
    for line in list(rc):
        rc.remove(line)
    for line in text.strip("\n").splitlines():
        ET.SubElement(rc, "LINE").text = line.rstrip()
    sync_vlans(eng, text)


def sync_vlans(eng, text):
    """Mirror `vlan N` / ` name X` sections into the switch's VLAN database (ENGINE/VLANS). On a 2960 VLANs live in
    vlan.dat, not the running-config, and Packet Tracer drops assessment items (VLANS > N > VLAN Name) for VLANs
    the saved database does not contain."""
    vlans = eng.find("VLANS")
    if vlans is None:
        return
    wanted, current = {}, None
    for raw in text.splitlines():
        m = re.match(r"vlan ([\d,-]+)\s*$", raw)
        if m:
            current = [n for part in m.group(1).split(",") for n in
                       (range(int(part.split("-")[0]), int(part.split("-")[1]) + 1) if "-" in part else [int(part)])]
            for n in current:
                wanted.setdefault(n, f"VLAN{n:04d}")
            continue
        if current and raw.startswith(" ") and raw.strip().startswith("name "):
            for n in current:
                wanted[n] = raw.strip()[5:].strip()
            continue
        if not raw.startswith(" "):
            current = None
    existing = {v.get("number"): v for v in vlans.findall("VLAN")}
    for n, name in sorted(wanted.items()):
        if str(n) in existing:
            existing[str(n)].set("name", name)
        else:
            ET.SubElement(vlans, "VLAN", {"number": str(n), "rspan": "0", "name": name})


# Switching::ETemplate values, from the `sdm prefer` command handlers (sdm_prefer_default passes 0,
# sdm_prefer_dual_default 5, dual_routing 6, dual_vlan 7, access 2, routing 3, vlan 4, lanbase_routing 8, qos 9).
SDM_DUAL_IPV4_IPV6 = 5


def set_sdm_template(dev, template):
    """Set a switch's active and next SDM template (ENGINE/SDM), as if `sdm prefer` had been followed by a reload."""
    sdm = dev.find("ENGINE/SDM")
    if sdm is None:
        return False
    for tag in ("ACTIVE_TEMPLATE", "NEXT_TEMPLATE"):
        el = sdm.find(tag)
        if el is None:
            el = ET.SubElement(sdm, tag)
        el.text = str(template)
    return True


def get_config(dev):
    return [(l.text or "").rstrip() for l in dev.findall("ENGINE/RUNNINGCONFIG/LINE")]


def pc_port(dev):
    for p in dev.iter("PORT"):
        if p.find("PORT_DHCP_ENABLE") is not None and p.find("IP") is not None and p.find("TYPE") is not None \
                and "Bluetooth" not in (p.findtext("TYPE") or ""):
            return p
    return None


def set_pc(dev, s):
    p = pc_port(dev)
    if p is None:
        die(f"no IP port on {dev.findtext('ENGINE/NAME')}")
    dhcp = bool(s.get("dhcp", False))
    p.find("PORT_DHCP_ENABLE").text = "true" if dhcp else "false"
    p.find("IP").text = "" if dhcp else s.get("ip", "")
    p.find("SUBNET").text = "" if dhcp else s.get("mask", "")
    p.find("PORT_GATEWAY").text = "" if dhcp else s.get("gw", "")
    g = dev.find("ENGINE/GATEWAY")
    if g is not None:
        g.text = "" if dhcp else s.get("gw", "")
    if "ip6" in s or "gw6" in s:
        _set_pc_v6(dev, p, s.get("ip6", []), s.get("gw6", ""))


def _sub(parent, tag):
    e = parent.find(tag)
    return e if e is not None else ET.SubElement(parent, tag)


def _set_pc_v6(dev, port, addresses, gw6):
    """Static IPv6 the way a saved host stores it: PORT/IPV6_ADDRESSES/IPV6_ADDRESS (ADDRESS, PREFIX, TYPE 0),
    the gateway in PORT/IPV6_PORT_GATEWAY and ENGINE/GATEWAYV6 (seen in a real activity's answer network)."""
    box = _sub(port, "IPV6_ADDRESSES")
    for old in list(box):
        box.remove(old)
    for a in addresses:          # "2001:DB8:1::10/64"
        addr, prefix = a.split("/")
        e = ET.SubElement(box, "IPV6_ADDRESS")
        ET.SubElement(e, "ADDRESS").text = addr
        ET.SubElement(e, "PREFIX").text = prefix
        ET.SubElement(e, "TYPE").text = "0"
    _sub(port, "IPV6_PORT_GATEWAY").text = gw6
    eng = dev.find("ENGINE")
    if eng is not None:
        _sub(eng, "GATEWAYV6").text = gw6


def get_pc(dev):
    p = pc_port(dev)
    gw = (p.findtext("PORT_GATEWAY") or "") or (dev.findtext("ENGINE/GATEWAY") or "")
    ip6 = [f"{e.findtext('ADDRESS')}/{e.findtext('PREFIX')}".upper() for e in p.findall("IPV6_ADDRESSES/IPV6_ADDRESS")]
    gw6 = (p.findtext("IPV6_PORT_GATEWAY") or "") or (dev.findtext("ENGINE/GATEWAYV6") or "")
    return {"ip": p.findtext("IP") or "", "mask": p.findtext("SUBNET") or "", "gw": gw,
            "dhcp": (p.findtext("PORT_DHCP_ENABLE") or "false") == "true", "ip6": ip6, "gw6": gw6.upper()}


# ---------------------------------------------------------------- grading
def blocks(lines):
    """{'GLOBAL': [...], 'interface GigabitEthernet0/0': [...], 'router ospf 1': [...]} (stripped)"""
    out, cur = {"GLOBAL": []}, "GLOBAL"
    for raw in lines:
        if not raw.strip() or raw.strip() == "!":
            cur = "GLOBAL"
            continue
        if not raw.startswith(" "):
            out["GLOBAL"].append(raw.strip())
            cur = raw.strip()
            out.setdefault(cur, [])
        else:
            out.setdefault(cur, []).append(raw.strip())
    return out


def cables(tree):
    """{frozenset({(device, port), (device, port)}): cable type} for every cable in a network."""
    names = {d.findtext("ENGINE/SAVE_REF_ID"): d.findtext("ENGINE/NAME") for d in tree.getroot().iter("DEVICE")}
    out = {}
    for lk in tree.getroot().findall("NETWORK/LINKS/LINK"):
        c = lk.find("CABLE")
        if c is None:
            continue
        ports = [p.text for p in c.findall("PORT")]
        if len(ports) == 2:
            ends = frozenset({(names.get(c.findtext("FROM")), ports[0]), (names.get(c.findtext("TO")), ports[1])})
            if c.findtext("DCEDEV"):   # serial: no cable TYPE, the DCE end is named instead
                out[ends] = ("eSerial", names.get(c.findtext("DCEDEV")), c.findtext("DCEPORT"))
            elif lk.findtext("TYPE") in ("eCoaxial", "ePhoneLine"):
                out[ends] = lk.findtext("TYPE")
            elif lk.findtext("TYPE") == "eFiber":          # single- or multimode (Packet Tracer 9), or untyped
                out[ends] = c.findtext("TYPE") or "eFiber"
            else:
                out[ends] = c.findall("TYPE")[-1].text if c.findall("TYPE") else None
    return out


def run_check(c, devs, links=None):
    if "any" in c:  # several valid ways to do it: one of the sub-checks must pass
        return any(run_check({"device": c["device"], **sub}, devs, links) for sub in c["any"])
    if "wlan" in c:   # the WLAN a device offers (first wireless server) or has joined (wireless client)
        d = devs.get(c["device"])
        if d is None:
            return False
        eng = d.find("ENGINE")
        common = None
        if eng.find("CAPWAP_AC") is not None:     # a WLC: the WLAN named after its SSID, enabled, in the AP group
            ssid, auth, key = c["wlan"]
            wc = next((w for w in eng.iter("WLAN_CONFIG") if w.findtext("NAME") == ssid), None)
            grouped = ssid in [w.findtext("NAME") for w in eng.findall("CAPWAP_AC/AP_GROUPS/AP_GROUP/WLANS/WLAN")]
            return (wc is not None and grouped and wc.findtext("SSID") == ssid and wc.findtext("ENABLED") == "true"
                    and wc.findtext("AUTHEN_TYPE") == auth and (key is None or wc.findtext("WEP_KEY") == key))
        if eng.find("WIRELESS_SERVERS") is not None and len(eng.find("WIRELESS_SERVERS")):
            common = eng.find("WIRELESS_SERVERS")[0].find("WIRELESS_COMMON")
        elif d.findtext("ENGINE/TYPE") in ("WirelessRouter", "AccessPoint") and eng.find("WIRELESS_SERVER") is not None:
            common = eng.find("WIRELESS_SERVER/WIRELESS_COMMON")
        elif eng.find("WIRELESS_CLIENT") is not None:
            common = eng.find("WIRELESS_CLIENT/WIRELESS_COMMON")
        if common is None:
            return False
        ssid, auth, key = c["wlan"]
        return (common.findtext("SSID") == ssid and common.findtext("AUTHEN_TYPE") == auth
                and (key is None or common.findtext("WEP_PROCESS/KEY") == key))
    if "cable" in c:  # a cable between exactly these two ports, of the expected type when one is given
        (a, pa, b, pb), want = c["cable"], c.get("cable_type")
        got = (links or {}).get(frozenset({(a, pa), (b, pb)}), False)
        if want in ("eSerialDCE", "eSerialDTE"):   # a serial cable with the DCE end where the plan puts it
            return got == ("eSerial", *((a, pa) if want == "eSerialDCE" else (b, pb)))
        return got is not False and (want is None or got == want)
    d = devs.get(c["device"])
    if d is None:
        return False
    if any(k in c for k in ("ip", "mask", "gw", "dhcp", "ip_in", "ip6", "gw6")):
        s = get_pc(d)
        for k in ("ip", "mask"):
            if k in c and s[k] != c[k]:
                return False
        if "gw" in c and s["gw"] not in c["gw"].split("|"):
            return False
        if "dhcp" in c and s["dhcp"] != c["dhcp"]:
            return False
        if "ip_in" in c and not _host_in(s["ip"], c["ip_in"]):
            return False
        if "ip6" in c and c["ip6"].upper() not in s["ip6"]:
            return False
        if "gw6" in c and s["gw6"] != c["gw6"].upper():
            return False
        return True
    if "vlan" in c:  # VLANs live in vlan.dat: the saved VLANS element, or config text not yet re-parsed
        num, name = c["vlan"]
        for v in d.iter("VLAN"):
            if v.get("number") == str(num):
                return v.get("name") == name
        bl = blocks(get_config(d))
        return f"name {name}" in bl.get(f"vlan {num}", [])
    if "banner" in c:  # the MOTD text between its delimiters, possibly over several lines
        return bool(re.search(c["banner"], banner_text(get_config(d)), re.I | re.S))
    bl = blocks(get_config(d))
    if c.get("top"):  # an unindented line (Packet Tracer matches whole lines, not sub-commands)
        return all(any(re.fullmatch(rx, l, re.I) for l in bl["GLOBAL"]) for rx in c.get("has", []))
    if "block" in c:
        scope = None
        for k, v in bl.items():
            if re.fullmatch(c["block"], k, re.I):
                scope = v
                break
        if scope is None:
            return not c.get("has") and bool(c.get("absent_ok"))
    else:
        scope = [l.strip() for l in get_config(d) if l.strip()]
    for rx in c.get("has", []):
        if not any(re.fullmatch(rx, l, re.I) for l in scope):
            return False
    for rx in c.get("lacks", []):
        if any(re.fullmatch(rx, l, re.I) for l in scope):
            return False
    return True


def banner_text(lines):
    """The MOTD banner of a running-config: 'banner motd ^CText^C' (one or several lines) -> 'Text'."""
    for i, line in enumerate(lines):
        if line.startswith("banner motd "):
            rest = line[len("banner motd "):].lstrip()
            delim = "^C" if rest.startswith("^C") else rest[:1]
            body = rest[len(delim):]
            j = i
            while delim not in body and j + 1 < len(lines):
                j += 1
                body += "\n" + lines[j]
            return body.split(delim)[0]
    return ""


def _host_in(ip, net):
    """ip is a usable host address of net ('192.168.10.0/24')."""
    import ipaddress
    try:
        a, n = ipaddress.ip_address(ip), ipaddress.ip_network(net)
    except ValueError:
        return False
    return a in n and (n.prefixlen >= 31 or a not in (n.network_address, n.broadcast_address))


def grade(a, tree, checks=None, quiet=False):
    devs = devices(tree)
    checks = checks if checks is not None else a["check"]
    links = cables(tree)
    res = [run_check(c, devs, links) for c in checks]
    if not quiet:
        for c, ok in zip(checks, res):
            print(f"  {G + 'ok  ' if ok else R + 'FAIL'}{Z} {c['desc']}")
    return res



# ---------------------------------------------------------------- native activities (.pka)


def _node(name, nid, *, head, eclass="8", comp="", points="", value="", enabled=None, check="0", variable="",
          feedback=""):
    n = ET.Element("NODE")
    nm = ET.SubElement(n, "NAME", {"variableName": variable, "checkType": check,
                                   "variableEnabled": ("false" if head else "true") if enabled is None else enabled,
                                   "nodeValue": value, "obfuscateName": "false", "incorrectFeedback": feedback,
                                   "eclass": eclass, "headNode": "true" if head else "false",
                                   "overrideDBGrading": "false"})
    nm.text = name
    ET.SubElement(n, "ID").text = nid
    ET.SubElement(n, "COMPONENTS").text = comp
    ET.SubElement(n, "POINTS").text = points
    return n


def _child(parent, name, nid=None):
    nid = nid or name
    for c in parent.findall("NODE"):
        if c.findtext("ID") == nid:
            return c
    c = _node(name, nid, head=True)
    parent.append(c)
    return c


# item kind -> (path under the device, display name, id, eclass, component)
PKA_KINDS = {
    "hostname": ([], "Host Name", "Host Name", "8", "Other"),
    "gw": ([], "Default Gateway", "Default Gateway", "0", "Ip"),
    "ip": (["Ports", "{port}"], "IP Address", "IP Address", "0", "Ip"),
    "mask": (["Ports", "{port}"], "Subnet Mask", "Subnet Mask", "0", "Ip"),
    # "Port Up" = the interface is up/up (shutdown turns it off); "Power" only means the port has power
    "port_on": (["Ports", "{port}"], "Port Up", "Port Up", "4", "Physical"),
    # the exact cable: this port is linked to that port of that device (NetAcad's structured-cabling activity grades
    # every patch-panel run this way); value = node name = "Connects to PEERPORT"
    "link_to": (["Ports", "{port}", "Link to {peer}"], "Connects to {peer_port}", "Connects to {peer_port}", "4",
                "Physical"),
    # a host set to DHCP (Desktop > IP Configuration > DHCP); path and value as graded in the user's activities
    "dhcp_client": (["Ports", "{port}"], "DHCP client enable", "DHCP client enable", "0", "Ip"),
    "router_id": (["OSPF", "{process}"], "Router ID", "Router ID", "1", "Routing"),
    # a line that must be present in the running-config (Activity Wizard "Entire Config" slot +
    # the {{DeviceConfig.isInConfig:LINE}} variable)
    "config_line": (["IOS Configuration", "Running Configuration", "Entire Config"], "Entire Config {n:02d}",
                    "Entire Config {n:02d}", "8", "Other"),
    # one running-config line, the way the Activity Wizard grades a ticked line: the node ID is the line
    # itself, or "PARENT LINE" for an indented line (value keeps IOS's leading space); items are matched
    # by ID, so line order does not matter
    "run_line": (["IOS Configuration", "Running Configuration", "LINES"], "{value}", "{line_id}", "8", "Other"),
    "vlan_name": (["VLANS", "{vlan}"], "VLAN Name", "VLAN Name", "5", "Switching"),
    "access_vlan": (["Ports", "{port}"], "Access VLAN", "Access VLAN", "5", "Switching"),
    "native_vlan": (["Ports", "{port}"], "Native VLAN", "Native VLAN", "5", "Switching"),
    # paths and value formats below were each read from graded items of real activities (see research-evidence.md)
    "ip6_addr": (["Ports", "{port}", "Ipv6 Address", "{addr}"], "IP Address", "IP Address", "0", "Ip"),
    "ip6_prefix": (["Ports", "{port}", "Ipv6 Address", "{addr}"], "Prefix Length", "Prefix", "0", "Ip"),
    "gw6": ([], "Default Gateway IPv6", "Default Gateway IPv6", "0", "Ip"),
    "description": (["Ports", "{port}"], "Description", "Description", "8", "Other"),
    "banner": ([], "Banner MOTD", "Banner motd", "8", "Other"),
    "nat": (["Ports", "{port}"], "NAT Mode", "NAT", "3", "Routing"),              # 1 inside, 2 outside
    "acl_in": (["Ports", "{port}"], "Access-group In", "Access-group In", "2", "Other"),
    "acl_out": (["Ports", "{port}"], "Access-group Out", "Access-group Out", "2", "Other"),
    "psec_on": (["Ports", "{port}", "Port Security"], "Enabled", "Enabled", "8", "Switching"),
    "psec_max": (["Ports", "{port}", "Port Security"], "Max Secure Mac", "Max Secure Mac", "8", "Switching"),
    "psec_sticky": (["Ports", "{port}", "Port Security"], "Sticky Enabled", "Sticky Enabled", "8", "Switching"),
    "psec_violation": (["Ports", "{port}", "Port Security"], "Port Security Violation", "Violation", "8",
                       "Switching"),                                              # 0 shutdown, 2 restrict
    "portfast": (["Ports", "{port}"], "PortFast", "PortFast", "5", "Switching"),
    "enable_secret": ([], "Enable Secret", "Enable Secret", "8", "Other"),       # value: md5crypt, salt mERr
    "username": (["User Names"], "Username", "{user}", "8", "Other"),            # value: "NAME HASH"
    "pool_name": (["DHCP Server", "Pools", "{pool}"], "Name", "Name", "0", "Ip"),
    # ASA, as in Packet Tracer's own assessment tree for a 5506-X (value strings keep their leading space)
    "nameif": (["Ports", "{port}"], "NameIf", "NameIf", "8", "Other"),
    "seclevel": (["Ports", "{port}"], "Security Level", "Security Level", "8", "Other"),
    "asa_obj_addr": (["Asa Object List", "{obj}"], "Address", "Address", "8", "Other"),       # " subnet A M"
    "asa_obj_nat": (["Asa Object List", "{obj}"], "Nat", "Nat", "8", "Other"),               # " nat (in,out) ..."
    # wireless, as in Packet Tracer's own tree: a home router's 2.4 GHz WLAN ("Wireless 2.4G") or a host ("Wireless")
    "wlan_ssid": (["{radio}"], "SSID", "SSID", "8", "Other"),
    "wlan_auth": (["{radio}", "Security Mode"], "Authen Type", "Authen Type", "8", "Other"),       # 0 open, 4 WPA2-PSK
    "wlan_enc": (["{radio}", "Security Mode"], "Encryption Type", "Encryption Type", "8", "Other"),  # 4 AES
    "wlan_key": (["{radio}", "Security Mode"], "Pass Phrase", "PassPhrase", "8", "Other"),   # display, node ID
    # a WLC's WLAN (Packet Tracer's own tree: CAPWAP Wireless > Wireless LANs > PROFILE), same leaves as above
    "wlc_ssid": (["CAPWAP Wireless", "Wireless LANs", "{wlan}"], "SSID", "SSID", "8", "Other"),
    "wlc_on": (["CAPWAP Wireless", "Wireless LANs", "{wlan}"], "Enabled", "Enabled", "8", "Other"),
    "wlc_auth": (["CAPWAP Wireless", "Wireless LANs", "{wlan}", "Security Mode"], "Authen Type", "Authen Type", "8",
                 "Other"),
    "wlc_enc": (["CAPWAP Wireless", "Wireless LANs", "{wlan}", "Security Mode"], "Encryption Type",
                "Encryption Type", "8", "Other"),
    "wlc_key": (["CAPWAP Wireless", "Wireless LANs", "{wlan}", "Security Mode"], "Pass Phrase", "PassPhrase", "8",
                "Other"),
    # the WLAN is offered by the APs of the default AP group (value and node = the WLAN's name)
    "wlc_group": (["CAPWAP Wireless", "AP Groups", "default-group", "WLANs"], "{wlan}", "{wlan}", "8", "Other"),
    "pool_start": (["DHCP Server", "Pools", "{pool}"], "Start IP address", "Start IP address", "0", "Ip"),
    "pool_mask": (["DHCP Server", "Pools", "{pool}"], "Subnet mask", "Subnet mask", "0", "Ip"),
    "pool_gw": (["DHCP Server", "Pools", "{pool}"], "Default Gateway", "Default Gateway", "0", "Ip"),
    "pool_dns": (["DHCP Server", "Pools", "{pool}"], "DNS Server", "DNS Server", "0", "Ip"),
}


def comparisons(items):
    """checkType="2" marks an item Check Results grades (0 = listed only), as Packet Tracer's
    Activity Wizard writes it."""
    root = _node("Network", "Network", head=True)
    line_no = {}
    for it in items:
        path, name, nid, eclass, comp = PKA_KINDS[it["kind"]]
        comp = it.get("component") or comp          # a lab part ("Hardening") instead of the generic class
        nid = nid.format(**it)
        if it["kind"] in ("link_to", "wlc_group"):
            name = name.format(**it)
        cur = _child(root, it["device"])
        for part in path:
            cur = _child(cur, part.format(**it))
        value = {"port_on": "1"}.get(it["kind"], it.get("value", ""))
        # several right answers: Packet Tracer matches the student's value against {{RegEx:PATTERN}} instead
        variable = "{{RegEx:%s}}" % it["regex"] if it.get("regex") else ""
        if it["kind"] == "config_line":
            line_no[it["device"]] = line_no.get(it["device"], 0) + 1
            name = nid = name.format(n=line_no[it["device"]])
            variable = "{{DeviceConfig.isInConfig:%s}}" % it["value"]
        elif it["kind"] == "run_line":
            name, nid = it["value"].strip(), it["line_id"]
        cur.append(_node(name, nid, head=False, eclass=eclass, comp=comp, points=str(it.get("points", 1)),
                         feedback=it.get("hint", ""),
                         value=value, check="2", variable=variable))
    # tri-state checkboxes: every branch above a graded item is "partially checked" (1),
    # otherwise Check Results never descends into it
    for n in root.iter("NODE"):
        if n.find("NAME").get("headNode") == "true":
            n.find("NAME").set("checkType", "1")
    c = ET.Element("COMPARISONS")
    c.append(root)
    return c


def instructions_html(a):
    import html as _h
    esc = _h.escape
    lines = a["brief"].strip().splitlines()
    intro, tasks, table = [], [], []
    for l in lines:
        m = re.match(r"^\s*(\d+)\.\s+(.*)", l)
        if m:
            tasks.append(m.group(2))
        elif tasks and l.startswith("   "):
            tasks[-1] += " " + l.strip()
        elif l.strip() and re.search(r"\d+\.\d+\.\d+|::|/\d\d|G\d/|F\d/|S\d/", l):
            table.append(l.strip())
        else:
            intro.append(l)
    para = "".join(f"<p>{esc(x)}</p>" for x in " ".join(i.strip() if i.strip() else "\n" for i in intro).split("\n") if x.strip())
    css = ("body{font-family:Arial,sans-serif;font-size:10pt} h1{font-size:15pt} h2{font-size:12pt;margin-top:14px}"
           "pre{background:#f2f2f2;padding:6px} li{margin:3px 0}")
    obj = "".join(f"<li>{esc(t)}</li>" for t in a.get("topics", []))
    tbl = f"<h2>Addressing and topology</h2><pre>{esc(chr(10).join(table))}</pre>" if table else ""
    steps = "".join(f"<li>{esc(t)}</li>" for t in tasks)
    return (f'<html><head><style>{css}</style></head><body>'
            f'<h1>Activity {a["id"]:02d} - {esc(a["title"])}</h1>'
            f'<p><i>Level {a["level"]}/5 - about {a["time"]} minutes</i></p>'
            f'<h2>Objectives</h2><ul>{obj}</ul>'
            f'<h2>Scenario</h2>{para}{tbl}'
            f'<h2>Tasks</h2><ol>{steps}</ol>'
            f'<h2>Network description</h2><pre>{esc(a["brief"].strip())}</pre>'
            f'<h2>Checking your work</h2><p>Click <b>Check Results</b> at the bottom of this window: Packet Tracer '
            f'scores the items it can assess. For the full check, save the activity (Ctrl+S) and run '
            f'<b>ptlab check SPEC SAVED.pka</b> in a terminal.</p></body></html>')


# Activity Wizard password: CActivityWizard::m_enablePassBtn_clicked hashes Util::md5Digest(SALT, utf8(password))
# = MD5(SALT + password), upper-case hex, into ACTIVITY PASS; real files also carry the salt in ACTIVITY VALUE.
# Verified: this reproduces the PASS of a real NetAcad activity from its known password.
_CRYPT64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
IOS_SECRET_SALT = "mERr"   # every "enable secret"/"username ... secret" hash in real activities uses this salt


def md5crypt(password, salt=IOS_SECRET_SALT):
    """IOS type-5 secret ($1$, FreeBSD MD5-crypt). With Packet Tracer's fixed salt this reproduces the
    Enable Secret values of real activities (e.g. "class" -> $1$mERr$9cTjUIEqNGurQiFU.ZeCi1)."""
    import hashlib
    pw, sb, magic = password.encode(), salt.encode(), b"$1$"
    alt = hashlib.md5(pw + sb + pw).digest()
    ctx = pw + magic + sb + (alt * (len(pw) // 16 + 1))[:len(pw)]
    i = len(pw)
    while i:
        ctx += b"\0" if i & 1 else pw[:1]
        i >>= 1
    fin = hashlib.md5(ctx).digest()
    for i in range(1000):
        fin = hashlib.md5((pw if i & 1 else fin) + (sb if i % 3 else b"") + (pw if i % 7 else b"")
                          + (fin if i & 1 else pw)).digest()
    out = ""
    for a, b, c in ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5)):
        v = (fin[a] << 16) | (fin[b] << 8) | fin[c]
        for _ in range(4):
            out += _CRYPT64[v & 63]
            v >>= 6
    v = fin[11]
    for _ in range(2):
        out += _CRYPT64[v & 63]
        v >>= 6
    return f"$1${salt}${out}"


PASSWORD_SALT = bytes.fromhex("c0a801be79392311a09bc602")
# CActivityFile timer type (ACTIVITY TIMERTYPE, stored unchanged in field 0x330): the activity window draws
# "Time Elapsed" for 0 and "Time Left" (countdown) for 1, and no timer for anything else.
TIMER_TYPES = {"elapsed": "0", "countdown": "1", "none": "2"}


def password_hash(password):
    return hashlib.md5(PASSWORD_SALT + password.encode("utf-8")).hexdigest().upper()


def activity_attributes(settings):
    """Serialize the activity controls (timer, answer convergence, wizard password)."""
    timer = settings.get("timer", "elapsed")
    countdown_ms = int(settings.get("countdown_minutes", 0)) * 60_000 if timer == "countdown" else 0
    password = settings.get("wizard_password", "")
    attrs = {
        "COUNTDOWNLEFT": str(countdown_ms),
        "ELAPSED": "0",
        "TIMERTYPE": TIMER_TYPES[timer],
        "COUNTDOWNMS": str(countdown_ms),
        "FORWARD_ANS_SIM_MS": str(int(settings.get("answer_convergence_ms", 0))),
        "PASS": password_hash(password) if password else "",
        "COUNTDOWN_EXPIRED": "0",
        "ENABLED": "no",
    }
    if password:
        attrs["VALUE"] = PASSWORD_SALT.decode("latin-1")
    return attrs


LOCKING_PRESETS = {
    "none": (),
    "cli-only": ("Use Config Tab", "Router/Switch Config Tab", "Device Use Config Tab"),
    "realtime-only": ("Switching to Simulation",),
    "logical-only": ("Switching to Physical",),
    # the student cannot add, delete or re-cable devices (do not combine with student cabling). The global
    # "Remove Devices" is only the editor's select-all: deleting checks each device's own Device_Remove
    # (CSelectedItems::hasUnremovableItem, CLogicalWorkspace::handleDeleteSelections), so the per-device and
    # per-port switches are set too.
    "fixed-topology": ("Create Devices", "Remove Devices", "Connect Links", "Disconnect Links",
                       "Device_Remove", "Port_Remove", "Port_Connect", "Port_Disconnect"),
    "exam": ("Use Config Tab", "Router/Switch Config Tab", "Device Use Config Tab",
             "Switching to Simulation", "View Command Log", "Copy and Paste"),
}


def apply_locking_preset(locking_tree, preset):
    """Enable every matching global or per-device switch in a copied Packet Tracer locking tree.
    preset: one name or a list of names."""
    names = [preset] if isinstance(preset, str) else list(preset)
    wanted = {switch for name in names for switch in LOCKING_PRESETS[name]}
    found = set()
    for node in locking_tree.iter("NODE"):
        ident = node.findtext("ID")
        if ident in wanted:
            node.set("on", "yes")
            found.add(ident)
    missing = wanted - found
    if missing:
        die(f"activity base has no locking switch(es): {', '.join(sorted(missing))}")
    return found


def set_existing_devices(locking_tree, devices):
    """Rebuild Topology > Existing Devices for the generated devices ({name: [port, ...]}). Packet Tracer looks
    per-device switches up by device name, and the activity base lists its own devices; the base's first entry
    with at least one port is the template for every device (IoT entries have an empty Ports branch)."""
    if not devices:
        return
    branch = next((n for n in locking_tree.iter("NODE") if n.findtext("ID") == "Existing Devices"), None)
    if branch is None:
        die("the activity base has no Existing Devices locking branch")
    template = next((d for d in branch.findall("NODE")
                     if d.find("NODE[ID='Ports']") is not None and d.find("NODE[ID='Ports']/NODE") is not None), None)
    if template is None:
        die("the activity base's Existing Devices branch has no device with ports to copy")
    port_template = template.find("NODE[ID='Ports']").find("NODE")
    for old in branch.findall("NODE"):
        branch.remove(old)
    for name, ports in devices.items():
        entry = copy.deepcopy(template)
        for n in entry.iter("NODE"):
            n.set("on", "no")
        entry.find("ID").text = entry.find("TEXT").text = name
        port_branch = entry.find("NODE[ID='Ports']")
        for p in port_branch.findall("NODE"):
            port_branch.remove(p)
        for port in ports:
            pe = copy.deepcopy(port_template)
            for n in pe.iter("NODE"):
                n.set("on", "no")
            pe.find("ID").text = pe.find("TEXT").text = port
            port_branch.append(pe)
        branch.append(entry)


def set_physical_locations(locking_tree, start_tree, start_location=None):
    """Rebuild the locking tree's Physical Locations branch from the generated network (the activity base's
    branch names the base file's own UUIDs). Each container gets "Enter" and "Start in Location" switches keyed
    by its UUID path from the intercity; start_location (a container NAME) is switched on."""
    branch = next((n for n in locking_tree.iter("NODE") if n.findtext("ID") == "Physical Locations"), None)
    workspace = start_tree.getroot().find("PHYSICALWORKSPACE")
    if branch is None or workspace is None:
        if start_location:
            die("cannot set a start location: the activity base or network has no physical workspace")
        return
    for child in branch.findall("NODE"):
        branch.remove(child)
    found = []

    def add(parent, node, path):
        if node.findtext("TYPE") in ("4", "6"):       # racks and devices are not locations
            return
        uid = node.findtext("UUID_STR")
        here = path + [uid]
        entry = ET.SubElement(parent, "NODE", {"on": "no"})
        ET.SubElement(entry, "ID").text = ",".join(here)
        ET.SubElement(entry, "TEXT").text = node.findtext("NAME")
        for ident, text in (("Enter", "Enter"), ("Start in Location", "Start in Physical Location")):
            switch = ET.SubElement(entry, "NODE", {"on": "no"})
            ET.SubElement(switch, "ID").text = ident
            ET.SubElement(switch, "TEXT").text = text
            if ident == "Start in Location" and start_location and node.findtext("NAME") == start_location:
                switch.set("on", "yes")
                found.append(node.findtext("NAME"))
        for child in node.findall("CHILDREN/NODE"):
            add(entry, child, here)

    for top in workspace.findall("NODE"):
        add(branch, top, [])
    if start_location and not found:
        die(f"start location {start_location!r} is not a city, building or wiring closet of this network")
    if start_location:
        # CActivityFile::doStartingTasks first checks Interface > "Physical Workspace" ("Start in Physical
        # Workspace"); without it the activity opens in the Logical view and the location is never shown
        start_physical = next((n for n in locking_tree.iter("NODE") if n.findtext("ID") == "Physical Workspace"), None)
        if start_physical is None:
            die("the activity base has no 'Start in Physical Workspace' switch")
        start_physical.set("on", "yes")


def build_pka(a, start_tree, answer_tree):
    pka_base = activity_base_path()
    if not pka_base.exists():
        die(f"{pka_base} is missing; run `ptlab init --source PATH` with a folder containing a .pka")
    base = ET.parse(pka_base).getroot()
    act = ET.Element("PACKETTRACER5_ACTIVITY")
    version = os.environ.get("PTLAB_PT_VERSION") or start_tree.getroot().findtext("VERSION") or "9.0.0"
    ET.SubElement(act, "VERSION").text = version
    # order read by CActivityFile::deserialize: main (yours), initial (Reset Activity), answer
    nets = [copy.deepcopy(start_tree.getroot()), copy.deepcopy(start_tree.getroot()), copy.deepcopy(answer_tree.getroot())]
    for net in nets:  # the activity page carries the description: no separate pop-up window
        d = net.find("NETWORK/DESCRIPTION")
        if d is not None:
            d.text = ""
        act.append(net)
    act.append(comparisons(a.get("pka_item", [])))
    init = ET.SubElement(act, "INITIALSETUP")
    init.append(_node("Network", "Network", head=True))
    ET.SubElement(init, "LOAD_INIT_TREE").text = "false"
    settings = a.get("activity", {})
    locking_tree = copy.deepcopy(base.find("LOCKINGTREE"))
    set_existing_devices(locking_tree, a.get("lock_devices"))
    apply_locking_preset(locking_tree, settings.get("locking_preset", "none"))
    set_physical_locations(locking_tree, start_tree, settings.get("start_location"))
    act.append(locking_tree)
    act.append(copy.deepcopy(start_tree.getroot().find("OPTIONS")) if start_tree.getroot().find("OPTIONS") is not None
               else copy.deepcopy(base.find("OPTIONS")))
    activity = ET.SubElement(act, "ACTIVITY", activity_attributes(settings))
    ins = ET.SubElement(activity, "INSTRUCTIONS", {"layout": "0", "enable_tab": "false"})
    ET.SubElement(ins, "PAGE", {"tabify": "0", "translate": "true", "title": ""}).text = instructions_html(a)
    vm = ET.SubElement(act, "VARIABLE_MANAGER")
    for t in ("SEED_POOLS", "NUMBER_POOLS", "STRING_POOLS", "IP_POOLS", "VARIABLES_POOLS"):
        ET.SubElement(vm, t)
    ET.SubElement(act, "OVERALL_INCOMPLETE_FEEDBACK", {"translate": "true"}).text = settings.get(
        "incomplete_feedback_html",
        "<html><body>Not complete yet. Fix the items marked incorrect and check again.</body></html>",
    )
    ET.SubElement(act, "OVERALL_COMPLETE_FEEDBACK", {"translate": "true"}).text = settings.get(
        "complete_feedback_html",
        "<html><body>All assessed items are correct. Save (Ctrl+S) and run ptlab check for the full check.</body></html>",
    )
    ET.SubElement(act, "UNLOCK_ASSESSMENT_ITEM_PERCENT").text = "100"
    ET.SubElement(act, "DYNAMIC_PERCENTAGE_FEEDBACK", {"TYPE": "1"}).text = "true"
    ET.SubElement(act, "USER_PROFILE_LOCKED").text = "true" if settings.get("profile_locked", False) else "false"
    ET.SubElement(act, "USER_PROFILE_NOGUEST").text = "false"
    parts = [c for c in dict.fromkeys(it.get("component") for it in a.get("pka_item", [])) if c]
    ET.SubElement(act, "COMPONENT_LIST").text = ", ".join(["Other", "Physical", "Ip", "Routing", "Switching"] + parts)
    ET.SubElement(act, "CLEAN_ACTIVITY").text = "false"
    sm = start_tree.getroot().find("SCRIPT_MODULE")
    act.append(copy.deepcopy(sm) if sm is not None else ET.Element("SCRIPT_MODULE"))
    au = ET.SubElement(act, "AUTHOR")
    ET.SubElement(au, "INFO").text = "Generated by pt-lab-builder"
    ET.SubElement(act, "OBJECT_LOCATIONS", {"INDEX": ""})
    ET.SubElement(act, "START_TIMESTAMP").text = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ET.SubElement(act, "CEPS")
    ET.SubElement(act, "EXT_PORT_MGR")
    return ET.ElementTree(act)

# ---------------------------------------------------------------- connectivity tests
def add_connectivity_tests(answer_tree, tests):
    """Store ping tests the way the Activity Wizard does: saved PDUs in the answer network's first
    scenario. CActivityFile::runConnectivityTestAt reads getAnsNetworkFile()->getScenarioSet()->
    getScenarioAt(0), runs each PDU from the same-named device of the student's network and compares
    the outcome with TEST_CONDITION (3 = should succeed, 2 = should fail, other = not tested)."""
    root = answer_tree.getroot()
    devs = devices(answer_tree)
    sset = root.find("SCENARIOSET")
    if sset is None:
        sset = ET.SubElement(root, "SCENARIOSET")
    scen = sset.find("SCENARIO")
    if scen is None:
        scen = ET.SubElement(sset, "SCENARIO")
        ET.SubElement(scen, "NAME", {"translate": "true"}).text = "Scenario 0"
        ET.SubElement(scen, "DESCRIPTION", {"translate": "true"})
    for t in tests:
        protocol = t.get("protocol", "icmp")
        pdu = ET.SubElement(scen, "PDU")
        if protocol == "tcp":
            ET.SubElement(pdu, "TYPE", {"name": "", "start": "3000", "patterned": "yes"}).text = "1"
        elif protocol == "udp":   # as saved by Packet Tracer's Complex PDU dialog (DNS or OTHER/UDP): type 2
            ET.SubElement(pdu, "TYPE", {"patterned": "no"}).text = "2"
        else:   # 0 = ICMP echo, 20 = ICMPv6 echo (same nested CIpHeader/CIcmpMessage, IPv6 addresses)
            ET.SubElement(pdu, "TYPE", {"patterned": "no"}).text = "20" if protocol == "icmp6" else "0"
        ET.SubElement(pdu, "CUSTOM_TYPE")
        ET.SubElement(pdu, "SOURCE").text = devs[t["src"]].findtext("ENGINE/SAVE_REF_ID")
        ET.SubElement(pdu, "PORT")
        if protocol in ("tcp", "udp", "icmp6"):
            ET.SubElement(pdu, "DESTINATION").text = t["ip"]
        else:
            ET.SubElement(pdu, "DESTINATION", {"device": devs[t["dst"]].findtext("ENGINE/SAVE_REF_ID")})
        ET.SubElement(pdu, "COLOR").text = "-8664361" if t["succeed"] else "-3394765"
        ip = ET.SubElement(pdu, "PDU")
        ET.SubElement(ip, "TYPE").text = "CIpHeader"
        ET.SubElement(ip, "SRCADDR").text = t.get("src_ip", "") if protocol in ("tcp", "udp", "icmp6") else ""
        ET.SubElement(ip, "DSTADDR").text = t["ip"]
        ET.SubElement(ip, "PROTOCOL")
        ET.SubElement(ip, "TTL").text = "32" if protocol in ("tcp", "udp") else "255"
        body = ET.SubElement(ip, "PDU")
        if protocol == "tcp":
            for tag, val in (("TYPE", "CTcpHeader"), ("SRC", "5000"), ("DST", str(t["port"])),
                             ("CHK", "0"), ("LENGTH", "136")):
                ET.SubElement(body, tag).text = val
        elif protocol == "udp":
            for tag, val in (("TYPE", "CUdpHeader"), ("SRC", "5000"), ("DST", str(t["port"])),
                             ("CHK", "0"), ("LENGTH", "8")):
                ET.SubElement(body, tag).text = val
        else:
            for tag, val in (("TYPE", "CIcmpMessage"), ("ICMPTYPE", "8"), ("CODE", "0"), ("ID", "0"),
                             ("SEQ", "0"), ("CHK", "0")):
                ET.SubElement(body, tag).text = val
        ET.SubElement(ip, "TOS").text = "0"
        ET.SubElement(pdu, "TEST_CONDITION").text = "3" if t["succeed"] else "2"
        ET.SubElement(pdu, "POINTS").text = str(t.get("points", 1))
        ET.SubElement(pdu, "PDU_SIZE").text = "10" if protocol == "tcp" else "0"
        if protocol != "tcp":
            ET.SubElement(pdu, "START").text = "0"


# ---------------------------------------------------------------- launcher
def open_pt(path):
    if os.environ.get("PTLAB_NO_OPEN"):
        print(f"Open it in Packet Tracer: {path}")
        return
    try:
        open_packet_tracer(path)
    except FileNotFoundError as exc:
        print(f"{exc}\\nOpen it in Packet Tracer: {path}")
        return
    print(f"{D}Opening Packet Tracer…{Z}")
