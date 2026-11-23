#!/usr/bin/env python3
"""labgen - build a native Packet Tracer activity (.pka) from one lab spec (TOML).

  labgen.py build SPEC.toml [--open]   -> work/<id>.pka + work/<id>-answer.md
  labgen.py check SPEC.toml FILE.pka   -> grade a saved activity with the spec's grade statements

The spec describes the topology (devices from lib/devices, links, coloured areas, labels),
the addressing, the start and answer configurations (CLI snippets merged onto factory
configs), optional faults, the instruction pages and the grading. See labs/README.md.
"""
import copy
import html
import ipaddress
import os
import re
import shlex
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET

from . import ptbuild, ptlab
from .paths import library_dir, work_dir

HERE = os.path.dirname(os.path.realpath(__file__))

COLORS = {  # area colours (soft, readable behind device icons)
    "cyan": (170, 255, 255), "yellow": (255, 255, 170), "green": (200, 255, 200), "pink": (255, 210, 230),
    "orange": (255, 225, 180), "purple": (225, 210, 255), "blue": (200, 225, 255), "grey": (230, 230, 230),
    "red": (255, 200, 200),
}
SHORT = [("GigabitEthernet", ("Gig", "Gi", "G")), ("FastEthernet", ("Fa", "F")), ("Serial", ("Se", "S")),
         ("Ethernet", ("Eth", "E")), ("Loopback", ("Lo",)), ("Port-channel", ("Po",)), ("Vlan", ("Vl",))]


def die(msg):
    sys.exit(f"labgen: {msg}")


def long_if(name):
    """G0/0 -> GigabitEthernet0/0, fa0/1 -> FastEthernet0/1 (already long names pass through)."""
    m = re.match(r"([A-Za-z-]+)\s*([\d/.:]+)$", name.strip())
    if not m:
        return name
    word, num = m.group(1), m.group(2)
    for full, shorts in SHORT:
        if word.lower() == full.lower() or word.lower() in (s.lower() for s in shorts):
            return full + num
    return name


ABBR = {"GigabitEthernet": "G", "FastEthernet": "Fa", "Serial": "S", "Ethernet": "E", "Loopback": "Lo",
        "Port-channel": "Po", "Vlan": "Vlan"}


def short_if(name):
    """Cisco's usual short forms: G0/1, Fa0/1, S0/0/0."""
    for full in sorted(ABBR, key=len, reverse=True):
        if name.startswith(full):
            return ABBR[full] + name[len(full):]
    return name


# ---------------------------------------------------------------- configs
def blocks(lines):
    """[(header or None, [body lines])] in order; header None = global lines."""
    out = []
    for raw in lines:
        if not raw.strip() or raw.strip() == "!":
            continue
        if raw.startswith(" "):
            if out and out[-1][0] is not None:
                out[-1][1].append(raw.rstrip())
            continue
        line = raw.rstrip()
        if line in ("end",) or line.startswith("version "):
            continue
        if re.match(r"(interface|router|line|ip dhcp pool|ip access-list|vlan|class-map|policy-map|crypto|key chain)\b", line):
            out.append((line, []))
        else:
            out.append((None, [line]))
    return out


def merge(factory_lines, snippet):
    """Apply a CLI snippet (config-mode commands, running-config style) to a factory config."""
    base = blocks(factory_lines)
    head = [l for l in factory_lines if l.startswith("version ")][:1] or ["version 15.1"]
    index = {h: i for i, (h, _) in enumerate(base) if h}
    sec = None
    for raw in snippet.strip("\n").splitlines():
        if not raw.strip() or raw.strip() in ("!", "exit", "end", "conf t", "configure terminal", "enable"):
            if raw.strip() == "exit":
                sec = None
            continue
        line = raw.strip()
        # a section header is unindented and is the keyword plus a space: "router ospf 1" opens one,
        # " router-id 1.1.1.1" does not ("router\b" also matched the hyphen in router-id)
        top = not raw.startswith((" ", "\t")) and re.match(
            r"(interface|router|line|ip dhcp pool|ip access-list|vlan|class-map|policy-map|crypto|key chain)\s", line)
        if top:
            line = ("interface " + long_if(line.split(None, 1)[1])) if line.startswith("interface ") else line
            if line not in index:
                base.append((line, []))
                index[line] = len(base) - 1
            sec = index[line]
            continue
        if raw.startswith((" ", "\t")) and sec is not None:   # indentation decides: indented = inside the section
            body = base[sec][1]
            hit = [i for i, b in enumerate(body) if _cancels(line, b.strip())]
            keep = line != "no shutdown" and not (line.startswith("no ") and not line.startswith("no ip address") and hit)
            if line.startswith("no ") and line not in ("no shutdown", "no ip address"):
                hit += [i for i, b in enumerate(body) if b.strip() == line[3:]]
                keep = False
            new_line = " " + line
            if hit:
                first = min(hit)
                body[:] = [b for i, b in enumerate(body) if i not in hit]
                if keep:
                    body.insert(first, new_line)     # replace in place: keeps running-config order
            elif keep:
                body.append(new_line)
            continue
        sec = None
        if line.startswith("no "):                   # global "no X" removes line X
            target = line[3:]
            base = [(h, b) for h, b in base if h or b[0] != target]
            continue
        if line.startswith("hostname "):
            base = [(h, b) if h or not b[0].startswith("hostname ") else (None, [line]) for h, b in base]
            continue
        base.append((None, [line]))
    out = ["!"] + head + ["!"]
    for h, body in base:
        if h:
            out += [h] + body + ["!"]
        else:
            out += body
    return out + ["end", ""]


SUBCMD = re.compile(r"(ip |ipv6 |no |shutdown|description|switchport|encapsulation|duplex|speed|channel-group|"
                    r"spanning-tree|network|router-id|passive-interface|default-information|default-router|"
                    r"dns-server|password|login|transport|exec-timeout|logging|clock rate|bandwidth|standby|"
                    r"permit|deny|remark|neighbor|redistribute|auto-summary|version|area|access-class|nat |"
                    r"service-policy|mls|power|negotiation|media-type|tunnel|keepalive|cdp|lldp|storm-control)")


def _is_sub(line):
    return bool(SUBCMD.match(line))


def _cancels(new, old):
    """Does adding `new` replace `old` inside a block?"""
    if new == "no shutdown" and old == "shutdown":
        return True
    if new == "shutdown" and old == "shutdown":
        return True
    if new.startswith("ip address ") and (old.startswith("ip address ") or old == "no ip address"):
        return True
    if new.startswith("description ") and old.startswith("description "):
        return True
    for key in ("switchport access vlan", "switchport mode", "switchport trunk native vlan",
                "switchport trunk allowed vlan", "encapsulation dot1Q", "router-id", "clock rate", "bandwidth"):
        if new.startswith(key) and old.startswith(key):
            return True
    return False


# ---------------------------------------------------------------- the build
def load_spec(path):
    with open(path, "rb") as fh:
        s = tomllib.load(fh)
    s["_path"] = path
    s["_id"] = s["lab"].get("id") or os.path.splitext(os.path.basename(path))[0]
    for key in ("debrief", "questions"):  # usually written under [grade], where TOML files them
        if key not in s and key in s.get("grade", {}):
            s[key] = s["grade"][key]
    return s


def addressing_rows(spec):
    return spec.get("addressing", {}).get("rows", [])


def pc_settings(spec):
    """PC/server address, mask and gateway from the addressing table (device, iface, cidr, gateway)."""
    out = {}
    for row in addressing_rows(spec):
        dev, iface, cidr = row[0], row[1], row[2]
        gw = row[3] if len(row) > 3 else ""
        if not cidr:
            continue
        if not any(d["name"] == dev and ptbuild_model_is_host(d["model"]) for d in spec["device"]):
            continue
        if cidr.lower() == "dhcp":
            out[dev] = {"dhcp": True}
            continue
        n = ipaddress.ip_interface(cidr)
        out[dev] = {"ip": str(n.ip), "mask": str(n.netmask), "gw": gw}
    return out


def ptbuild_model_is_host(model):
    return model in ("pc", "server", "laptop", "printer", "tablet", "smartphone")


def cable_for(ma, mb, pa, pb):
    if pa.startswith("Serial") or pb.startswith("Serial"):
        return "eSerialDCE"
    host = ("pc", "server", "laptop", "printer", "ipphone-7960", "ap")
    cls = lambda m: "host" if m in host else "router" if m.startswith("router") else "switch"
    a, b = cls(ma), cls(mb)
    same = a == b or {a, b} == {"host", "router"}
    return "eCrossOver" if same else "eStraightThrough"


TIER = {"router": 0, "l3switch": 1, "switch": 2, "wlc": 2, "cloud": 0}
XSTEP, YTOP, YSTEP, GAP = 170, 130, 135, 130


def tier(model):
    for prefix, n in TIER.items():
        if model.startswith(prefix):
            return n
    return 3                                    # hosts, servers, printers, phones, APs


def layout(spec):
    """Fill in x/y for devices that have none: one column group per area (in spec order, then
    devices outside any area), rows by tier, hosts under the switch they are cabled to."""
    devs = spec["device"]
    if all("x" in d and "y" in d for d in devs):
        return
    peers = {}
    for lk in spec.get("link", []):
        a, b = lk["a"].split()[0], lk["b"].split()[0]
        peers.setdefault(a, []).append(b)
        peers.setdefault(b, []).append(a)
    groups = [list(a["devices"]) for a in spec.get("area", [])]
    placed = {n for g in groups for n in g}
    rest = [d["name"] for d in devs if d["name"] not in placed]
    if rest:
        groups.insert(len(groups) // 2, rest)     # e.g. the ISP / WAN cloud between two sites
    model = {d["name"]: d["model"] for d in devs}
    x0 = 80
    for g in groups:
        rows = {}
        for n in g:
            rows.setdefault(tier(model[n]), []).append(n)
        # order each row under its parent in the row above (by first linked parent's index)
        order = {}
        for t in sorted(rows):
            def key(n):
                ups = [order[p] for p in peers.get(n, []) if p in order and tier(model[p]) < t]
                return (min(ups) if ups else 99, n)
            rows[t].sort(key=key)
            for i, n in enumerate(rows[t]):
                order[n] = i
        width = max(len(r) for r in rows.values())
        for t, r in rows.items():
            offset = (width - len(r)) * XSTEP / 2
            for i, n in enumerate(r):
                d = next(x for x in devs if x["name"] == n)
                d.setdefault("x", round(x0 + offset + i * XSTEP))
                d.setdefault("y", YTOP + sorted(rows).index(t) * YSTEP)
        x0 += width * XSTEP + GAP


def build_topology(spec, configs, pcs, which="answer"):
    """which = "start" leaves out the cables the student must add (links with student = true)."""
    layout(spec)
    t = ptbuild.Topology()
    t.configure_physical(spec.get("physical", {}))
    site_of = {}
    if spec.get("site"):
        t.configure_sites(spec["site"])
        site_of = {n: st["name"] for st in spec["site"] for n in st.get("devices", [])}
    pos = {d["name"]: (d["x"], d["y"]) for d in spec["device"]}
    for a in spec.get("area", []):  # areas first, so they sit behind the devices
        xs = [pos[n][0] for n in a["devices"]]
        ys = [pos[n][1] for n in a["devices"]]
        pad = a.get("pad", 60)
        x1, y1, x2, y2 = min(xs) - pad, min(ys) - pad - 20, max(xs) + pad + 40, max(ys) + pad + 40
        t.rect(x1, y1, x2, y2, COLORS.get(a.get("color", "grey"), (230, 230, 230)))
        t.note(a["label"], x1 + 8, y1 + 6)
    models = {}
    for d in spec["device"]:
        t.add(d["model"], d["name"], d["x"], d["y"], d.get("physical"), site=site_of.get(d["name"]))
        models[d["name"]] = d["model"]
    cidr = {(r[0], long_if(r[1])): r[2] for r in addressing_rows(spec)}
    for lk in spec.get("link", []):
        if which == "start" and lk.get("student"):
            continue
        (na, pa), (nb, pb) = lk["a"].split(None, 1), lk["b"].split(None, 1)
        pa, pb = long_if(pa), long_if(pb)
        cable = lk.get("cable") or cable_for(models[na], models[nb], pa, pb)
        t.link(na, pa, nb, pb, cable=cable)
        if spec["lab"].get("labels", False):  # optional own interface notes (Packet Tracer shows port names on hover)
            for (n, p), (m, _) in (((na, pa), (nb, pb)), ((nb, pb), (na, pa))):
                (x, y), (x2, y2) = pos[n], pos[m]
                lx, ly = x + (x2 - x) * 0.22 + 18, y + (y2 - y) * 0.22 - 8
                text = short_if(p)
                if (n, p) in cidr and cidr[(n, p)] and not ptbuild_model_is_host(models[n]):
                    text += "  ." + cidr[(n, p)].split("/")[0].split(".")[-1]
                t.note(text, round(lx), round(ly))
    for name, text in configs.items():
        ptlab.set_config(t.devices[name], "\n".join(text))
    for name, s in pcs.items():
        ptlab.set_pc(t.devices[name], s)
    for n in spec.get("note", []):
        t.note(n["text"], n["x"], n["y"])
    display_options(t.root, spec)
    return t


def display_options(root, spec):
    """Port names only on mouse-over, so they never cover the canvas text (PT: Options > Preferences)."""
    o = root.find("OPTIONS")
    if o is None:
        return
    want = {"PORTSHOWN": "true" if spec["lab"].get("always_show_ports", False) else "false",
            "PORTNOTSHOWNONMOUSEOVER": "false", "LINKLIGHTSSHOWN": "true", "MODELSHOWN": "true"}
    for tag, val in want.items():
        e = o.find(tag)
        if e is None:
            e = ET.SubElement(o, tag)
        e.text = val


def configs_for(spec, which):
    """Running-config text per router/switch: factory + hostname + snippets (+ faults for start)."""
    out = {}
    tpl_cfg = {}
    for d in spec["device"]:
        if ptbuild_model_is_host(d["model"]) or d["model"] in ("ipphone-7960", "cloud", "hub", "ap"):
            continue
        tpl = ET.parse(library_dir() / "devices" / (d["model"] + ".xml")).getroot()
        tpl_cfg[d["name"]] = [l.text or "" for l in tpl.findall("ENGINE/RUNNINGCONFIG/LINE")]
    cfg = spec.get("config", {})
    kind = spec["lab"].get("kind", "configure")
    answer_based_start = kind in ("troubleshoot", "mixed")
    for name, factory in tpl_cfg.items():
        snippet = f"hostname {name}\n"
        if which == "answer" or answer_based_start:
            snippet += cfg.get("answer", {}).get(name, "")
        else:
            snippet += cfg.get("start", {}).get(name, "")
        text = merge(factory, snippet)
        if which == "start" and kind == "mixed":
            # Mixed activities start from the reference configuration, then use config.start
            # as an overlay for the intentionally unfinished work before hidden faults are added.
            text = merge(text, cfg.get("start", {}).get(name, ""))
        if which == "start" and answer_based_start:
            for f in spec.get("fault", []):
                if f["device"] == name and "apply" in f:   # faults written as CLI, merged onto the answer
                    text = merge(text, f["apply"])
            joined = "\n".join(text)
            for f in spec.get("fault", []):
                if f["device"] == name and "find" in f:
                    if f["find"] not in joined:
                        die(f"fault on {name}: text not found in its answer config: {f['find']!r}")
                    joined = joined.replace(f["find"], f["replace"], 1)
            text = joined.split("\n")
        out[name] = text
    return out


def pcs_for(spec, which):
    pcs = pc_settings(spec)
    if which == "start" and spec["lab"].get("kind") != "troubleshoot":
        for name in spec.get("config", {}).get("unconfigured_hosts", []):
            pcs[name] = {"ip": "", "mask": "", "gw": ""}
    if which == "start":
        for f in spec.get("fault", []):
            if f["device"] in pcs and "pc" in f:
                pcs[f["device"]].update(f["pc"])
    return pcs


# ---------------------------------------------------------------- grading statements
TCP_PORTS = {"http": 80, "https": 443, "ssh": 22, "telnet": 23}
CONNECTIVITY_STATEMENTS = ("ping", "tcp", *TCP_PORTS)
GRADE_STATEMENTS = ("ip", "up", "gw", "hostname", "line", "in", "dhcp", "vlan", "access", "trunk", "route",
                    "ospf", "stp", *CONNECTIVITY_STATEMENTS, "cable")


def _args(statement, n):
    """Split a statement with shell-style quoting: in R1 "router ospf 1" "network 10.0.0.0 0.0.0.3 area 0"."""
    parts = shlex.split(statement)
    if len(parts) != n:
        die(f"grade statement needs {n} fields (quote multi-word ones): {statement}")
    return parts


def vlan_list(text):
    """'10,20,30,11,12' -> '10-12,20,30' (the form IOS shows in the running-config)."""
    nums = sorted({n for part in str(text).split(",") for n in
                   (range(int(part.split("-")[0]), int(part.split("-")[1]) + 1) if "-" in part else [int(part)])})
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if j == i else f"{nums[i]}-{nums[j]}" if j > i + 1 else f"{nums[i]},{nums[j]}")
        i = j + 1
    return ",".join(out)


# Lines Packet Tracer writes into its running-config with a trailing space (seen in a saved activity:
# "ip route 10.99.0.0 255.255.0.0 192.168.2.254 "). LINES items are matched on the exact line, so an item
# without the space does not exist in the answer and Packet Tracer silently drops it.
PT_TRAILING_SPACE = {"ip route": " "}


def _line_item(items, checks, dev, parent, line):
    """A running-config line Packet Tracer grades natively (LINES node) plus the matching local check."""
    line = " ".join(line.split())
    if parent:
        parent = " ".join(parent.split())
        items.append({"device": dev, "kind": "run_line", "line_id": f"{parent} {line}", "value": " " + line})
        checks.append({"device": dev, "desc": f"{dev}: {parent} / {line}", "block": re.escape(parent),
                       "has": [re.escape(line)]})
    else:
        shown = line + PT_TRAILING_SPACE.get(" ".join(line.split()[:2]), "")
        items.append({"device": dev, "kind": "run_line", "line_id": shown, "value": shown})
        checks.append({"device": dev, "desc": f"{dev}: {line}", "has": [re.escape(line)], "top": True})


def connectivity_tests(spec):
    """Compile ICMP and TCP outcome statements for Packet Tracer's Connectivity Tests tab."""
    first = {}
    for row in addressing_rows(spec):
        if len(row) >= 3 and row[2] and row[2].lower() != "dhcp":
            first.setdefault(row[0], str(ipaddress.ip_interface(row[2]).ip))
    tests = []
    points = spec.get("grade", {}).get("points", {})
    for st in spec.get("grade", {}).get("items", []):
        w = st.split()
        if w[0] not in CONNECTIVITY_STATEMENTS:
            continue
        kind = w[0]
        protocol = "icmp" if kind == "ping" else "tcp"
        port = None
        rest_at = 3
        if kind == "tcp":
            port = int(w[3])
            rest_at = 4
        elif kind in TCP_PORTS:
            port = TCP_PORTS[kind]
        rest = w[rest_at:]
        succeed = "fail" not in rest
        rest = [x for x in rest if x != "fail"]
        ip = rest[0] if rest else first.get(w[2])
        if ip is None:
            die(f"{st}: {w[2]} has no address in the addressing table; give an explicit destination address")
        test = {"src": w[1], "dst": w[2], "ip": ip, "succeed": succeed, "protocol": protocol,
                "src_ip": first.get(w[1], ""), "points": points.get(st, 1)}
        if protocol == "tcp":
            test["port"] = port
            test["desc"] = f"{w[1]} {'can' if succeed else 'cannot'} open TCP/{port} on {w[2]} ({ip})"
        else:
            test["desc"] = f"{w[1]} {'can' if succeed else 'cannot'} ping {w[2]} ({ip})"
        tests.append(test)
    return tests


def compile_grade(spec):
    """grade statements -> (pka items, lab-check checks)."""
    items, checks = [], []
    overrides = spec.get("grade", {}).get("hints", {})
    points = spec.get("grade", {}).get("points", {})
    for st in spec.get("grade", {}).get("items", []):
        w = st.split()
        k = w[0]
        first = len(items)
        try:
            _statement(st, w, k, items, checks, spec)
        finally:
            for it in items[first:]:
                if st in points:
                    it["points"] = points[st]
                if st in overrides:
                    it["hint"] = overrides[st]
                else:
                    it.setdefault("hint", default_hint(w, it))
    graded = {frozenset({(w[1], long_if(w[2])), (w[3], long_if(w[4]))})
              for w in (st.split() for st in spec.get("grade", {}).get("items", [])) if w[0] == "cable"}
    for lk in spec.get("link", []):          # every cable the student must add is graded
        if lk.get("student"):
            (na, pa), (nb, pb) = lk["a"].split(None, 1), lk["b"].split(None, 1)
            if frozenset({(na, long_if(pa)), (nb, long_if(pb))}) not in graded:
                _cable_item(items, checks, spec, na, pa, nb, pb)
    return items, checks


def default_hint(w, item):
    """A nudge shown next to an incorrect item in Check Results: where to look, never the answer."""
    k, dev = w[0], w[1] if len(w) > 1 else ""
    port = short_if(item["port"]) if item.get("port") else ""
    kind = item.get("kind")
    if kind in ("ip", "mask"):
        return f"Compare {dev} {port}'s address and mask with the addressing table (show ip interface brief / ipconfig)."
    if kind == "port_on":
        if k == "cable":
            return f"Is {dev} {port} cabled to the right port, with the right cable type? Check its link light."
        return f"{dev} {port} is not up/up: is it enabled (no shutdown) and is its cable connected?"
    if kind == "gw":
        return f"Check {dev}'s default gateway (ipconfig): it must be its router's address on the same subnet."
    if kind == "hostname":
        return f"Check this device's name: show running-config | include hostname."
    if kind == "vlan_name":
        return f"Check the VLANs on {dev} and their names: show vlan brief."
    if kind in ("access_vlan", "native_vlan") or k in ("access", "trunk"):
        return f"Check how {dev} {port or short_if(long_if(w[2]))} is configured: show interfaces switchport / show interfaces trunk."
    hints = {"route": f"Check the static routes on {dev}: show ip route static.",
             "ospf": f"Check which networks OSPF advertises on {dev}, and in which area: show ip protocols.",
             "stp": f"Check the bridge priority on {dev}: show spanning-tree.",
             "line": f"Compare {dev}'s running configuration with the task: show running-config.",
             "in": f"Compare {dev}'s running configuration with the task: show running-config."}
    return hints.get(k, f"Compare {dev}'s configuration with the task.")


def _statement(st, w, k, items, checks, spec):
    """One grade statement -> Packet Tracer items (+ local checks)."""
    if k == "ip":                       # ip DEV IFACE A.B.C.D/NN
        dev, iface, cidr = w[1], long_if(w[2]), w[3]
        n = ipaddress.ip_interface(cidr)
        items += [{"device": dev, "kind": "ip", "port": iface, "value": str(n.ip)},
                  {"device": dev, "kind": "mask", "port": iface, "value": str(n.netmask)}]
        if any(d["name"] == dev and ptbuild_model_is_host(d["model"]) for d in spec["device"]):
            checks.append({"device": dev, "desc": f"{dev} {short_if(iface)} {cidr}", "ip": str(n.ip), "mask": str(n.netmask)})
        else:
            checks.append({"device": dev, "desc": f"{dev} {short_if(iface)} {cidr}", "block": "interface " + re.escape(iface),
                           "has": [f"ip address {re.escape(str(n.ip))} {re.escape(str(n.netmask))}"]})
    elif k == "up":                     # up DEV IFACE
        dev, iface = w[1], long_if(w[2])
        items.append({"device": dev, "kind": "port_on", "port": iface})
        checks.append({"device": dev, "desc": f"{dev} {short_if(iface)} is up", "block": "interface " + re.escape(iface),
                       "lacks": ["shutdown"], "absent_ok": True})
    elif k == "gw":                     # gw HOST A.B.C.D
        items.append({"device": w[1], "kind": "gw", "value": w[2]})
        checks.append({"device": w[1], "desc": f"{w[1]} gateway {w[2]}", "gw": w[2]})
    elif k == "hostname":               # hostname DEV NAME
        items.append({"device": w[1], "kind": "hostname", "value": w[2]})
        checks.append({"device": w[1], "desc": f"{w[1]} hostname {w[2]}", "has": [f"hostname {re.escape(w[2])}"]})
    elif k == "line":                   # line DEV <exact top-level running-config line>
        dev, line = w[1], " ".join(st.split(None, 2)[2].strip().strip("'\"").split())
        _line_item(items, checks, dev, None, line)
    elif k == "in":                     # in DEV "PARENT LINE" "SUB-COMMAND"
        dev, parent, line = _args(st, 4)[1:]
        _line_item(items, checks, dev, parent, line)
    elif k == "dhcp":                   # dhcp HOST
        checks.append({"device": w[1], "desc": f"{w[1]} uses DHCP", "dhcp": True})
    elif k == "vlan":                   # vlan SW ID NAME
        dev, num, name = w[1], int(w[2]), w[3]
        items.append({"device": dev, "kind": "vlan_name", "vlan": str(num), "value": name})
        checks.append({"device": dev, "desc": f"{dev} VLAN {num} named {name}", "vlan": (num, name)})
    elif k == "access":                 # access SW IFACE VLAN
        dev, iface, vlan = w[1], long_if(w[2]), int(w[3])
        items.append({"device": dev, "kind": "access_vlan", "port": iface, "value": str(vlan)})
        parent = f"interface {iface}"
        _line_item(items, checks, dev, parent, "switchport mode access")
        checks.append({"device": dev, "desc": f"{dev} {short_if(iface)} access VLAN {vlan}",
                       "block": re.escape(parent), "has": [f"switchport access vlan {vlan}"]})
    elif k == "trunk":                  # trunk SW IFACE [allowed LIST] [native N]
        dev, iface = w[1], long_if(w[2])
        opts = dict(zip(w[3::2], w[4::2]))
        parent = f"interface {iface}"
        _line_item(items, checks, dev, parent, "switchport mode trunk")
        if "allowed" in opts:
            _line_item(items, checks, dev, parent, "switchport trunk allowed vlan " + vlan_list(opts["allowed"]))
        if "native" in opts:
            items.append({"device": dev, "kind": "native_vlan", "port": iface, "value": str(int(opts["native"]))})
            checks.append({"device": dev, "desc": f"{dev} {short_if(iface)} native VLAN {opts['native']}",
                           "block": re.escape(parent), "has": [f"switchport trunk native vlan {int(opts['native'])}"]})
    elif k == "route":                  # route DEV PREFIX/LEN NEXT-HOP|EXIT-IFACE
        net = ipaddress.ip_network(w[2], strict=True)
        via = w[3] if re.fullmatch(r"[\d.]+", w[3]) else long_if(w[3])
        _line_item(items, checks, w[1], None, f"ip route {net.network_address} {net.netmask} {via}")
    elif k == "ospf":                   # ospf DEV PID PREFIX/LEN AREA
        net = ipaddress.ip_network(w[3], strict=True)
        _line_item(items, checks, w[1], f"router ospf {int(w[2])}",
                   f"network {net.network_address} {net.hostmask} area {w[4]}")
    elif k == "stp":                    # stp SW VLAN PRIORITY
        _line_item(items, checks, w[1], None, f"spanning-tree vlan {vlan_list(w[2])} priority {int(w[3])}")
    elif k in CONNECTIVITY_STATEMENTS:   # graded inside Packet Tracer (Connectivity Tests tab)
        return
    elif k == "cable":                  # cable DEV PORT DEV PORT (also implied by every student = true link)
        _cable_item(items, checks, spec, w[1], w[2], w[3], w[4])
    else:
        die(f"unknown grade statement: {st}")


def _cable_item(items, checks, spec, a, pa, b, pb):
    pa, pb = long_if(pa), long_if(pb)
    models = {d["name"]: d["model"] for d in spec["device"]}
    link = next((lk for lk in spec.get("link", []) if frozenset(
        {(lk["a"].split(None, 1)[0], long_if(lk["a"].split(None, 1)[1])),
         (lk["b"].split(None, 1)[0], long_if(lk["b"].split(None, 1)[1]))}) == frozenset({(a, pa), (b, pb)})), {})
    want = link.get("cable") or (cable_for(models[a], models[b], pa, pb) if a in models and b in models else None)
    for dev, port in ((a, pa), (b, pb)):
        if not ptbuild_model_is_host(models.get(dev, "")):
            items.append({"device": dev, "kind": "port_on", "port": port,
                          "hint": default_hint(["cable", dev], {"kind": "port_on", "port": port})})
    checks.append({"device": a, "desc": f"cable {a} {short_if(pa)} - {b} {short_if(pb)}"
                   + (f" ({want.removeprefix('e')})" if want else ""), "cable": (a, pa, b, pb), "cable_type": want})


# ---------------------------------------------------------------- instructions
CSS = """body{font-family:Arial,Helvetica,sans-serif;font-size:10pt;color:#1d2731}
h1{font-size:16pt;color:#0b4f8a;margin:0 0 4px 0} h2{font-size:12pt;color:#0b4f8a;border-bottom:2px solid #9cc3e6;
padding-bottom:2px;margin-top:14px} .badge{display:inline-block;background:#0b4f8a;color:#fff;padding:2px 8px;
border-radius:8px;font-size:9pt;margin-right:6px} .kind{background:#b5651d} .box{background:#eef5fc;border-left:4px
solid #0b4f8a;padding:6px 10px;margin:8px 0} .hint{background:#fff7e0;border-left:4px solid #e0a800;padding:6px 10px;
margin:8px 0} .why{background:#eaf7ea;border-left:4px solid #2e8b57;padding:6px 10px;margin:8px 0}
table{border-collapse:collapse;margin:6px 0} th{background:#0b4f8a;color:#fff;padding:3px 8px;text-align:left}
td{border:1px solid #b9cde0;padding:3px 8px} tr:nth-child(even) td{background:#f4f8fc} code{background:#f1f1f1;padding:0 3px}
li{margin:3px 0}"""


def md(text):
    """tiny markdown: `code`, **bold**; paragraphs on blank lines."""
    e = html.escape(text.strip())
    e = re.sub(r"`([^`]+)`", r"<code>\1</code>", e)
    e = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", e)
    return "".join(f"<p>{p.replace(chr(10), ' ')}</p>" for p in e.split("\n\n") if p.strip())


def feedback_html(text):
    """Wrap compact Markdown-like feedback in the same readable style as instruction pages."""
    return f'<html><head><style>{CSS}</style></head><body>{md(text)}</body></html>'


def pages(spec):
    lab = spec["lab"]
    kind = lab.get("kind", "configure")
    head = (f'<h1>{html.escape(lab["title"])}</h1><span class="badge">Level {lab.get("level", 2)}/5</span>'
            f'<span class="badge kind">{html.escape(kind.title())}</span><span class="badge">~{lab.get("time", 30)} min</span>'
            + (f'<span class="badge">{html.escape(lab["exam"])}</span>' if lab.get("exam") else ""))
    rows = "".join(f"<tr><td>{html.escape(r[0])}</td><td>{html.escape(short_if(long_if(r[1])))}</td><td>{html.escape(r[2])}</td>"
                   f"<td>{html.escape(r[3] if len(r) > 3 else '')}</td></tr>" for r in addressing_rows(spec))
    table = (f"<h2>Addressing table</h2><table><tr><th>Device</th><th>Interface</th><th>Address</th><th>Gateway</th></tr>{rows}</table>"
             if rows else "")
    obj = "".join(f"<li>{html.escape(o)}</li>" for o in lab.get("objectives", []))
    out = [f'<html><head><style>{CSS}</style></head><body>{head}<h2>Scenario</h2><div class="box">{md(lab["scenario"])}</div>'
           f'<h2>Objectives</h2><ul>{obj}</ul>{table}'
           f'<p><i>Use <b>Next</b> for each part. Check your work with <b>Check Results</b>; for the full check save '
           f'(Ctrl+S) and run <code>ptlab check SPEC SAVED.pka</code>.</i></p></body></html>']
    for i, p in enumerate(spec.get("part", []), 1):
        steps = "".join(f"<li>{md(s)[3:-4]}</li>" for s in p.get("steps", []))
        hint = f'<div class="hint"><b>Hint.</b> {md(p["hint"])[3:-4]}</div>' if p.get("hint") else ""
        why = f'<div class="why"><b>Why it matters.</b> {md(p["why"])[3:-4]}</div>' if p.get("why") else ""
        out.append(f'<html><head><style>{CSS}</style></head><body><h1>Part {i}: {html.escape(p["title"])}</h1>'
                   f'{md(p.get("intro", ""))}<ol>{steps}</ol>{hint}{why}</body></html>')
    if spec.get("debrief"):
        out.append(f'<html><head><style>{CSS}</style></head><body><h1>Debrief</h1><div class="why">{md(spec["debrief"])}</div>'
                   f'<h2>Check yourself</h2><ul>' + "".join(f"<li>{html.escape(q)}</li>" for q in spec.get("questions", []))
                   + "</ul></body></html>")
    return out


def answer_guide(spec, answer_cfg_snippets, items):
    lab = spec["lab"]
    lines = [f"# {lab['title']} - answer guide", "", f"Level {lab.get('level', 2)}/5 · {lab.get('kind', 'configure')} · ~{lab.get('time', 30)} min", ""]
    if spec.get("fault"):
        lines += ["## The faults", ""]
        for i, f in enumerate(spec["fault"], 1):
            lines += [f"{i}. **{f['device']}** - {f.get('symptom', '')}", f"   - {f.get('explain', '')}"]
        lines.append("")
    student = [lk for lk in spec.get("link", []) if lk.get("student")]
    if student:
        models = {d["name"]: d["model"] for d in spec["device"]}
        lines += ["## Cabling", "", "| From | To | Cable |", "|---|---|---|"]
        for lk in student:
            (na, pa), (nb, pb) = lk["a"].split(None, 1), lk["b"].split(None, 1)
            cable = lk.get("cable") or cable_for(models[na], models[nb], long_if(pa), long_if(pb))
            lines.append(f"| {na} {pa} | {nb} {pb} | {cable.removeprefix('e')} |")
        lines.append("")
    lines += ["## Reference configuration", ""]
    for name, text in answer_cfg_snippets.items():
        if text.strip():
            lines += [f"### {name}", "", "```", text.strip(), "```", ""]
    lines += ["## Graded items", ""] + [f"- {st}" for st in spec.get("grade", {}).get("items", [])]
    return "\n".join(lines) + "\n"


def verify(spec, quiet=False):
    """Lint the spec, then prove the lab against its own grade statements. Returns True if usable."""
    from . import validate
    lint = validate.lint(spec)
    if not quiet or lint:
        lint.report("spec check")
    if lint.errors:
        return False
    checks, passed, total, at_start = validate.selfcheck(spec)
    if not quiet or checks:
        checks.report(f"self-check (answer {passed}/{total}, start {at_start}/{total}, "
                      f"{len(spec.get('fault', []))} fault(s))")
    return not checks.errors


DYNAMIC = re.compile(r"^(router (ospf|eigrp|rip|bgp)|standby |channel-group |spanning-tree mode)", re.M)


def needs_convergence(spec):
    """Routing protocols, HSRP, EtherChannel and STP need time before the answer network is compared."""
    return any(DYNAMIC.search(re.sub(r"^\s+", "", text, flags=re.M))
               for text in spec.get("config", {}).get("answer", {}).values())


def start_location(spec):
    """[activity] start_in = site name -> that site's wiring closet. Cabling labs start in the first site's
    closet by default, so the student lands next to the rack."""
    activity = spec.get("activity", {})
    sites = spec.get("site", [])
    name = activity.get("start_in")
    if name is None and any(lk.get("student") for lk in spec.get("link", [])) and sites:
        name = sites[0]["name"]
    if not name:
        return None
    site = next((s for s in sites if s["name"] == name), None)
    if site is None:
        die(f"[activity] start_in: no [[site]] named {name!r}")
    return site.get("closet") or f"{name} Wiring Closet"


def build(path, open_after=False, output_dir=None, force=False, password=None):
    spec = load_spec(path)
    if not verify(copy.deepcopy(spec)) and not force:
        die("not built: fix the errors above (or pass --force to build anyway)")
    start = build_topology(spec, configs_for(spec, "start"), pcs_for(spec, "start"), "start")
    answer = build_topology(spec, configs_for(spec, "answer"), pcs_for(spec, "answer"))
    items, _ = compile_grade(spec)
    tests = connectivity_tests(spec)
    if tests:
        ptlab.add_connectivity_tests(answer.tree, tests)
    settings = dict(spec.get("activity", {}))
    if password:
        settings["wizard_password"] = password
    if "answer_convergence_ms" not in settings and needs_convergence(spec):
        settings["answer_convergence_ms"] = 60_000
    if "start_location" not in settings:
        settings["start_location"] = start_location(spec)
    if "locking_preset" not in settings and not any(lk.get("student") for lk in spec.get("link", [])):
        settings["locking_preset"] = "fixed-topology"
    if settings.get("timer", "elapsed") == "countdown":
        settings.setdefault("countdown_minutes", spec["lab"].get("time", 30))
    complete_feedback = settings.pop("complete_feedback", None)
    incomplete_feedback = settings.pop("incomplete_feedback", None)
    if complete_feedback is None and spec.get("debrief"):
        complete_feedback = "All assessed items are correct.\n\n" + spec["debrief"]
    if complete_feedback:
        settings["complete_feedback_html"] = feedback_html(complete_feedback)
    if incomplete_feedback:
        settings["incomplete_feedback_html"] = feedback_html(incomplete_feedback)
    a = {"id": 0, "title": spec["lab"]["title"], "pka_item": items, "brief": spec["lab"]["scenario"],
         "topics": spec["lab"].get("objectives", []), "level": spec["lab"].get("level", 2),
         "time": spec["lab"].get("time", 30), "activity": settings,
         "lock_devices": {name: start.ports(name) for name in start.devices}}
    pka = ptlab.build_pka(a, start.tree, answer.tree)
    ins = pka.getroot().find("ACTIVITY/INSTRUCTIONS")
    for p in list(ins):
        ins.remove(p)
    for page in pages(spec):
        ET.SubElement(ins, "PAGE", {"tabify": "0", "translate": "true", "title": ""}).text = page
    output_root = os.fspath(output_dir or work_dir())
    os.makedirs(output_root, exist_ok=True)
    out = os.path.join(output_root, spec["_id"] + ".pka")
    for opt in pka.getroot().iter("ENABLE_CABLE_LENGTH_EFFECTS"):
        opt.text = "false"   # distances between generated buildings must never take links down
    ptlab.write_pkt(pka, out)
    with open(os.path.join(output_root, spec["_id"] + "-answer.md"), "w", encoding="utf-8") as fh:
        fh.write(answer_guide(spec, spec.get("config", {}).get("answer", {}), items))
    print(f"built {out}  ({len(spec['device'])} devices, {len(spec.get('link', []))} links, {len(items)} graded items, {len(tests)} connectivity tests, {len(pages(spec))} pages)")
    if open_after:
        ptlab.open_pt(out)
    return out


def check(path, saved):
    spec = load_spec(path)
    _, checks = compile_grade(spec)
    tree = ptlab.read_pkt(saved)
    if tree.getroot().tag == "PACKETTRACER5_ACTIVITY":
        student = tree.getroot().find("PACKETTRACER5")
        if student is None:
            die(f"{saved} contains no student network")
        tree = ET.ElementTree(student)
    res = ptlab.grade({"check": checks}, tree, checks)
    print(f"\n{sum(res)}/{len(res)} checks pass.")
    return 0 if all(res) else 1


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("build", "check"):
        die(__doc__)
    if sys.argv[1] == "build":
        build(sys.argv[2], "--open" in sys.argv)
    else:
        sys.exit(check(sys.argv[2], sys.argv[3]))
