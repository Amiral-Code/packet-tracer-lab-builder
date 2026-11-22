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
        top = re.match(r"(interface|router|line|ip dhcp pool|ip access-list|vlan|class-map|policy-map|crypto|key chain)\b", line)
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


def build_topology(spec, configs, pcs):
    layout(spec)
    t = ptbuild.Topology()
    t.configure_physical(spec.get("physical", {}))
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
        t.add(d["model"], d["name"], d["x"], d["y"], d.get("physical"))
        models[d["name"]] = d["model"]
    cidr = {(r[0], long_if(r[1])): r[2] for r in addressing_rows(spec)}
    for lk in spec.get("link", []):
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
def compile_grade(spec):
    """grade statements -> (pka items, lab-check checks)."""
    items, checks = [], []
    for st in spec.get("grade", {}).get("items", []):
        w = st.split()
        k = w[0]
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
        elif k == "line":                   # line DEV <exact running-config line>
            dev, line = w[1], st.split(None, 2)[2].strip().strip("'\"")
            items.append({"device": dev, "kind": "config_line", "value": line})
            checks.append({"device": dev, "desc": f"{dev}: {line}", "has": [r"\s*".join(map(re.escape, line.split()))]})
        elif k == "dhcp":                   # dhcp HOST
            checks.append({"device": w[1], "desc": f"{w[1]} uses DHCP", "dhcp": True})
        else:
            die(f"unknown grade statement: {st}")
    return items, checks


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


def build(path, open_after=False, output_dir=None, force=False):
    spec = load_spec(path)
    if not verify(copy.deepcopy(spec)) and not force:
        die("not built: fix the errors above (or pass --force to build anyway)")
    start = build_topology(spec, configs_for(spec, "start"), pcs_for(spec, "start"))
    answer = build_topology(spec, configs_for(spec, "answer"), pcs_for(spec, "answer"))
    items, _ = compile_grade(spec)
    a = {"id": 0, "title": spec["lab"]["title"], "pka_item": items, "brief": spec["lab"]["scenario"],
         "topics": spec["lab"].get("objectives", []), "level": spec["lab"].get("level", 2), "time": spec["lab"].get("time", 30)}
    pka = ptlab.build_pka(a, start.tree, answer.tree)
    ins = pka.getroot().find("ACTIVITY/INSTRUCTIONS")
    for p in list(ins):
        ins.remove(p)
    for page in pages(spec):
        ET.SubElement(ins, "PAGE", {"tabify": "0", "translate": "true", "title": ""}).text = page
    output_root = os.fspath(output_dir or work_dir())
    os.makedirs(output_root, exist_ok=True)
    out = os.path.join(output_root, spec["_id"] + ".pka")
    ptlab.write_pkt(pka, out)
    with open(os.path.join(output_root, spec["_id"] + "-answer.md"), "w", encoding="utf-8") as fh:
        fh.write(answer_guide(spec, spec.get("config", {}).get("answer", {}), items))
    print(f"built {out}  ({len(spec['device'])} devices, {len(spec.get('link', []))} links, {len(items)} graded items, {len(pages(spec))} pages)")
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
