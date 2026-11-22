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
        return ET.parse(x)


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
    """Replace the running-config of a router/switch. Packet Tracer re-parses it on load."""
    eng = dev.find("ENGINE")
    rc = eng.find("RUNNINGCONFIG")
    for line in list(rc):
        rc.remove(line)
    for line in text.strip("\n").splitlines():
        ET.SubElement(rc, "LINE").text = line.rstrip()


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


def get_pc(dev):
    p = pc_port(dev)
    gw = (p.findtext("PORT_GATEWAY") or "") or (dev.findtext("ENGINE/GATEWAY") or "")
    return {"ip": p.findtext("IP") or "", "mask": p.findtext("SUBNET") or "", "gw": gw,
            "dhcp": (p.findtext("PORT_DHCP_ENABLE") or "false") == "true"}


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
            out[ends] = c.findall("TYPE")[-1].text if c.findall("TYPE") else None
    return out


def run_check(c, devs, links=None):
    if "any" in c:  # several valid ways to do it: one of the sub-checks must pass
        return any(run_check({"device": c["device"], **sub}, devs, links) for sub in c["any"])
    if "cable" in c:  # a cable between exactly these two ports, of the expected type when one is given
        (a, pa, b, pb), want = c["cable"], c.get("cable_type")
        got = (links or {}).get(frozenset({(a, pa), (b, pb)}), False)
        return got is not False and (want is None or got == want)
    d = devs.get(c["device"])
    if d is None:
        return False
    if any(k in c for k in ("ip", "mask", "gw", "dhcp", "ip_in")):
        s = get_pc(d)
        for k in ("ip", "mask", "gw"):
            if k in c and s[k] != c[k]:
                return False
        if "dhcp" in c and s["dhcp"] != c["dhcp"]:
            return False
        if "ip_in" in c and not s["ip"].startswith(c["ip_in"]):
            return False
        return True
    if "vlan" in c:  # VLANs live in vlan.dat: the saved VLANS element, or config text not yet re-parsed
        num, name = c["vlan"]
        for v in d.iter("VLAN"):
            if v.get("number") == str(num):
                return v.get("name") == name
        bl = blocks(get_config(d))
        return f"name {name}" in bl.get(f"vlan {num}", [])
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
}


def comparisons(items):
    """checkType="2" marks an item Check Results grades (0 = listed only), as Packet Tracer's
    Activity Wizard writes it."""
    root = _node("Network", "Network", head=True)
    line_no = {}
    for it in items:
        path, name, nid, eclass, comp = PKA_KINDS[it["kind"]]
        cur = _child(root, it["device"])
        for part in path:
            cur = _child(cur, part.format(**it))
        value = {"port_on": "1"}.get(it["kind"], it.get("value", ""))
        variable = ""
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
    # the student cannot add, delete or re-cable devices (do not combine with student cabling)
    "fixed-topology": ("Create Devices", "Remove Devices", "Connect Links", "Disconnect Links"),
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
    ET.SubElement(act, "COMPONENT_LIST").text = "Other, Physical, Ip, Routing, Switching"
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
        else:
            ET.SubElement(pdu, "TYPE", {"patterned": "no"}).text = "0"
        ET.SubElement(pdu, "CUSTOM_TYPE")
        ET.SubElement(pdu, "SOURCE").text = devs[t["src"]].findtext("ENGINE/SAVE_REF_ID")
        ET.SubElement(pdu, "PORT")
        if protocol == "tcp":
            ET.SubElement(pdu, "DESTINATION").text = t["ip"]
        else:
            ET.SubElement(pdu, "DESTINATION", {"device": devs[t["dst"]].findtext("ENGINE/SAVE_REF_ID")})
        ET.SubElement(pdu, "COLOR").text = "-8664361" if t["succeed"] else "-3394765"
        ip = ET.SubElement(pdu, "PDU")
        ET.SubElement(ip, "TYPE").text = "CIpHeader"
        ET.SubElement(ip, "SRCADDR").text = t.get("src_ip", "") if protocol == "tcp" else ""
        ET.SubElement(ip, "DSTADDR").text = t["ip"]
        ET.SubElement(ip, "PROTOCOL")
        ET.SubElement(ip, "TTL").text = "32" if protocol == "tcp" else "255"
        body = ET.SubElement(ip, "PDU")
        if protocol == "tcp":
            for tag, val in (("TYPE", "CTcpHeader"), ("SRC", "5000"), ("DST", str(t["port"])),
                             ("CHK", "0"), ("LENGTH", "136")):
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
