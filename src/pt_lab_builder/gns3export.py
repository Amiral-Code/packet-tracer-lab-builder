"""Beyond Packet Tracer: compile a spec into a GNS3 lab for the author's CCNA engine (`lab ccna`).

The engine runs IOU routers/switches and VPCS hosts from a TOML lab with `[nodes]` (R, SW, PC), `links` ("R1 e0/1 -
R2 e0/0", hosts without a port), `[base]` and `[solution]` CLI text, and `[[check]]` blocks (show command on a node,
regexes that must / must not appear). This module maps a pt-lab-builder spec onto that: every device port in use
becomes the next IOU port in link order (e0/0, e0/1, e0/2, e0/3, e1/0, ...), interface names are rewritten in every
configuration line, hosts become VPCS `ip` lines, and grade statements become show-command checks. Statements with
no fair show-command equivalent are listed in the output as comments, never silently dropped.

Devices GNS3/IOU cannot stand in for (ASA, home and provider gear, wireless, servers' services) make the export
fail with the reason: such a lab stays in Packet Tracer.
"""
import ipaddress
import re

from . import labgen

KIND = {"router": "R", "switch": "SW", "l3switch": "SW", "pc": "PC", "server": "PC", "laptop": "PC"}


def _kind(model):
    for prefix, kind in (("router-", "R"), ("l3switch-", "SW"), ("switch-", "SW")):
        if model.startswith(prefix):
            return kind
    if model in ("pc", "server", "laptop"):
        return "PC"
    return None


def _iou(i):
    return f"e{i // 4}/{i % 4}"


def port_maps(spec):
    """{device: {PT long port name: IOU name}}, ports numbered in the order links use them."""
    maps = {}
    for lk in spec.get("link", []):
        for end in (lk["a"], lk["b"]):
            name, port = end.split(None, 1)
            port = labgen.long_if(port)
            m = maps.setdefault(name, {})
            if port not in m:
                m[port] = _iou(len(m))
    for name, port, *_ in labgen.addressing_rows(spec):          # addressed but uncabled ports get a number too
        port = labgen.long_if(port)
        if "." in port or port.startswith(("Vlan", "Loopback")):
            continue
        m = maps.setdefault(name, {})
        if port not in m:
            m[port] = _iou(len(m))
    return maps


def _rename(text, pmap):
    """Rewrite every interface name of this device in a CLI text (subinterfaces keep their suffix)."""
    def sub(m):
        word = m.group(0)
        base, dot, rest = word.partition(".")
        full = labgen.long_if(base)
        if full in pmap:
            return pmap[full] + (dot + rest if dot else "")
        return word
    return re.sub(r"\b(?:[A-Z][A-Za-z-]*\s?\d+(?:/\d+)*(?:\.\d+)?)\b", sub, text)


def _checks(spec, pmaps, first4):
    checks, skipped = [], []
    hosts = {d["name"] for d in spec["device"] if _kind(d["model"]) == "PC"}
    for st in spec.get("grade", {}).get("items", []):
        w = labgen.words(st)
        k = w[0]
        if k in ("ping",):
            src, dst = w[1], w[2]
            rest = [x for x in w[3:] if x != "fail"]
            ip = rest[0] if rest else first4.get(dst)
            fail = "fail" in w
            if src in hosts:
                c = {"on": src, "cmd": f"ping {ip} -c 3", "wait": 15}
                c["reject" if fail else "expect"] = rf"bytes from {re.escape(ip)}"
            else:
                c = {"on": src, "cmd": f"ping {ip} repeat 3 timeout 1", "wait": 10}
                c["reject" if fail else "expect"] = r"Success rate is (66|100) percent"
            c["desc"] = f"{src} {'cannot reach' if fail else 'reaches'} {dst} ({ip})"
            checks.append(c)
        elif k == "route":
            net = ipaddress.ip_network(w[2], strict=True)
            nh = w[3]
            checks.append({"on": w[1], "cmd": "show ip route static",
                           "expect": rf"{re.escape(str(net))} \[1/0\] via {re.escape(nh)}",
                           "desc": f"{w[1]} has a static route to {net} via {nh}"})
        elif k == "ip" and len(w) == 4:
            iface = pmaps.get(w[1], {}).get(labgen.long_if(w[2]), labgen.long_if(w[2]))
            addr = str(ipaddress.ip_interface(w[3]).ip)
            if w[1] in hosts:
                skipped.append(st)
                continue
            checks.append({"on": w[1], "cmd": "show ip interface brief",
                           "expect": rf"^{re.escape(iface.replace('e', 'Ethernet', 1))}\s+{re.escape(addr)}\b",
                           "desc": f"{w[1]} {iface} has {addr}"})
        elif k == "ospf":
            net = ipaddress.ip_network(w[3], strict=True)
            checks.append({"on": w[1], "cmd": f"show running-config | section router ospf {w[2]}",
                           "expect": rf"network {re.escape(str(net.network_address))} {re.escape(str(net.hostmask))} area {w[4]}",
                           "desc": f"{w[1]} advertises {net} in OSPF area {w[4]}"})
        elif k == "line":
            line = " ".join(w[2:])
            checks.append({"on": w[1], "cmd": "show running-config",
                           "expect": "^" + re.escape(_rename(line, pmaps.get(w[1], {}))) + r"\s*$",
                           "desc": f"{w[1]}: {line}"})
        elif k == "vlan":
            checks.append({"on": w[1], "cmd": "show vlan brief", "expect": rf"^{w[2]}\s+{re.escape(w[3])}\b",
                           "desc": f"{w[1]} has VLAN {w[2]} named {w[3]}"})
        else:
            skipped.append(st)
    return checks, skipped


def _toml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _block(s):
    """A multi-line TOML string with no escape processing: a literal string, unless the text holds three quotes."""
    if "'''" not in s:
        return "'''\n" + s + "\n'''"
    return '"""\n' + s.replace("\\", "\\\\").replace('"', '\\"') + '\n"""'


def _toml_regex(s):
    return "'" + s + "'" if "'" not in s else _toml_str(s)


def export(spec):
    """The GNS3 lab TOML text for a spec, or ValueError naming what cannot be exported."""
    bad = [f"{d['name']} ({d['model']})" for d in spec["device"] if _kind(d["model"]) is None]
    if bad:
        raise ValueError("no GNS3/IOU equivalent for " + ", ".join(bad) + ": keep this lab in Packet Tracer")
    serial = [lk for lk in spec.get("link", []) if "S" == lk["a"].split()[1][:1].upper() and
              labgen.long_if(lk["a"].split()[1]).startswith("Serial")]
    if serial:
        raise ValueError("serial links are not exported yet (IOU numbers serial adapters separately)")
    pmaps = port_maps(spec)
    first4, _ = labgen.first_addresses(spec)
    lab = spec["lab"]
    out = [f"title = {_toml_str(lab['title'])}", f'block = "Packet Tracer exports"', f"level = {lab.get('level', 2)}",
           f"time = {lab.get('time', 30)}", f"topics = [{_toml_str(lab.get('exam', ''))}]"]
    links = []
    for lk in spec.get("link", []):
        ends = []
        for end in (lk["a"], lk["b"]):
            name, port = end.split(None, 1)
            dev = next(d for d in spec["device"] if d["name"] == name)
            ends.append(name if _kind(dev["model"]) == "PC" else f"{name} {pmaps[name][labgen.long_if(port)]}")
        links.append(" - ".join(ends))
    out.append("links = [" + ", ".join(_toml_str(l) for l in links) + "]")
    if lab.get("objectives"):
        out.append(f"takeaway = {_toml_str(lab['objectives'][0])}")
    steps = [s for p in spec.get("part", []) for s in p.get("steps", [])]
    brief = lab.get("scenario", "").strip() + "\n\n" + "\n".join(f"{i}. {_rename(s, {})}" for i, s in enumerate(steps, 1))
    out.append(f"brief = {_block(brief)}")
    out += ["", "[nodes]"] + [f'{d["name"]} = "{_kind(d["model"])}"' for d in spec["device"]]
    pcs = labgen.pc_settings(spec)
    base, sol = [], []
    for d in spec["device"]:
        name = d["name"]
        if _kind(d["model"]) == "PC":
            s = pcs.get(name, {})
            if s.get("dhcp"):
                base.append(f'{name} = "dhcp"')
            elif s.get("ip"):
                plen = ipaddress.ip_network(f"0.0.0.0/{s['mask']}").prefixlen
                gw = f" {s['gw']}" if s.get("gw") else ""
                base.append(f'{name} = "ip {s["ip"]}/{plen}{gw}"')
            continue
        start = spec.get("config", {}).get("start", {}).get(name, "")
        answer = spec.get("config", {}).get("answer", {}).get(name, "")
        if start.strip():
            base.append(f"{name} = {_block(_rename(start.strip(), pmaps.get(name, {})))}")
        if answer.strip():
            sol.append(f"{name} = {_block(_rename(answer.strip(), pmaps.get(name, {})))}")
    out += ["", "[base]"] + base + ["", "[solution]"] + sol
    checks, skipped = _checks(spec, pmaps, first4)
    for c in checks:
        out += ["", "[[check]]", f"on = {_toml_str(c['on'])}", f"cmd = {_toml_str(c['cmd'])}"]
        for key in ("expect", "reject"):
            if key in c:
                out.append(f"{key} = {_toml_regex(c[key])}")
        if "wait" in c:
            out.append(f"wait = {c['wait']}")
        out.append(f"desc = {_toml_str(c['desc'])}")
    if skipped:
        out += ["", "# graded in Packet Tracer but not exported as a GNS3 check:"] + [f"#   {s}" for s in skipped]
    return "\n".join(out) + "\n"
