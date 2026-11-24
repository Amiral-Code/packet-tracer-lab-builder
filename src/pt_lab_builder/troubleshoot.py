"""A fault library: turn a configure lab into a troubleshooting lab.

Faults are drawn from the lab's own answer configuration, so they always fit it: an interface shut down, a static
route's next hop mistyped, an OSPF network in the wrong area, an interface address mistyped, an access port in the
wrong VLAN, an ACL applied in the wrong direction, `ip nat inside` missing, a host with the wrong gateway. Each comes
with the symptom a student would see and the explanation for the answer key. A fault is kept only when the lab's
self-check proves a graded item catches it.
"""
import ipaddress
import json
import random
import re
import tomllib

from . import labgen


def _q(text):
    return json.dumps(text, ensure_ascii=False)


def _bump(addr):
    ip = ipaddress.ip_address(addr)
    last = int(str(ip).split(".")[-1])
    return str(ip + (1 if last < 250 else -1)) if ip.version == 4 else None


def candidates(spec):
    """Every fault this lab's answer configuration allows: dicts ready for [[fault]]."""
    out = []
    answer = spec.get("config", {}).get("answer", {})
    for dev, text in answer.items():
        section = None
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            if not line.startswith(" "):
                section = line.strip()
            body = line.strip()
            if section and section.startswith("interface ") and body == "no shutdown" and line.startswith(" "):
                iface = section.split(None, 1)[1]
                out.append({"device": dev, "apply": f"{section}\n shutdown\n",
                            "symptom": f"Everything reached through {dev} {iface} is unreachable; the link light is red.",
                            "explain": f"{dev} {iface} was administratively down (show ip interface brief). "
                                       f"Fix: interface {iface}, no shutdown."})
            m = re.match(r"ip route (\S+) (\S+) (\d+\.\d+\.\d+\.\d+)$", body)
            if m and not line.startswith(" "):
                wrong = _bump(m.group(3))
                if wrong:
                    out.append({"device": dev, "find": body, "replace": body.rsplit(" ", 1)[0] + " " + wrong,
                                "symptom": f"Traffic for {m.group(1)} leaves {dev} but never arrives.",
                                "explain": f"{dev}'s route to {m.group(1)} pointed to {wrong}, an address nobody has "
                                           f"(show ip route). Fix: replace it with next hop {m.group(3)}."})
            m = re.match(r"network (\S+) (\S+) area (\d+)$", body)
            if m and section and section.startswith("router ospf"):
                wrong_area = str(int(m.group(3)) + 1)
                out.append({"device": dev, "find": " " + body, "replace": f" network {m.group(1)} {m.group(2)} area {wrong_area}",
                            "symptom": f"{dev} forms no OSPF adjacency on the {m.group(1)} network.",
                            "explain": f"{dev} advertised {m.group(1)} in area {wrong_area} instead of {m.group(3)}; "
                                       f"neighbours must agree on the area (show ip ospf interface)."})
            m = re.match(r"ip address (\d+\.\d+\.\d+\.\d+) (\d+\.\d+\.\d+\.\d+)$", body)
            if m and section and section.startswith("interface ") and line.startswith(" "):
                wrong = _bump(m.group(1))
                iface = section.split(None, 1)[1]
                if wrong:
                    out.append({"device": dev, "find": " " + body, "replace": f" ip address {wrong} {m.group(2)}",
                                "symptom": f"Hosts and neighbours cannot reach {dev} {iface} at {m.group(1)}.",
                                "explain": f"{dev} {iface} had {wrong} instead of {m.group(1)} (show ip interface "
                                           f"brief, compare with the addressing table)."})
            m = re.match(r"switchport access vlan (\d+)$", body)
            if m and section and section.startswith("interface "):
                wrong_vlan = "1" if m.group(1) != "1" else "99"
                iface = section.split(None, 1)[1]
                out.append({"device": dev, "find": f"{section}\n{line}" if f"{section}\n{line}" in text else " " + body,
                            "replace": (f"{section}\n switchport access vlan {wrong_vlan}" if f"{section}\n{line}" in text
                                        else f" switchport access vlan {wrong_vlan}"),
                            "symptom": f"The host on {dev} {iface} gets no address or reaches nothing in its subnet.",
                            "explain": f"{dev} {iface} was in VLAN {wrong_vlan} instead of {m.group(1)} "
                                       f"(show vlan brief)."})
            m = re.match(r"ip access-group (\S+) (in|out)$", body)
            if m and section and section.startswith("interface "):
                other = "out" if m.group(2) == "in" else "in"
                iface = section.split(None, 1)[1]
                out.append({"device": dev, "find": " " + body, "replace": f" ip access-group {m.group(1)} {other}",
                            "symptom": f"The policy {m.group(1)} has no effect on the traffic it should filter.",
                            "explain": f"ACL {m.group(1)} was applied {other} on {dev} {iface} instead of "
                                       f"{m.group(2)} (show ip interface {iface})."})
            if body == "ip nat inside" and section and section.startswith("interface "):
                iface = section.split(None, 1)[1]
                out.append({"device": dev, "apply": f"{section}\n no ip nat inside\n",
                            "symptom": "Inside hosts reach the edge router but nothing on the Internet.",
                            "explain": f"{dev} {iface} was not marked ip nat inside, so its traffic was never "
                                       f"translated (show ip nat translations stays empty)."})
    for row in labgen.addressing_rows(spec):
        if len(row) >= 4 and row[3] and row[2] and row[2] != "dhcp" and ":" not in row[2]:
            wrong = _bump(row[3])
            if wrong:
                out.append({"device": row[0], "pc": {"gw": wrong},
                            "symptom": f"{row[0]} reaches its own subnet but nothing beyond it.",
                            "explain": f"{row[0]}'s default gateway was {wrong} instead of {row[3]} (ipconfig)."})
    return out


def _fault_toml(f):
    lines = ["", "[[fault]]", f"device = {_q(f['device'])}"]
    if "apply" in f:
        lines.append('apply = """\n' + f["apply"] + '"""')
    if "find" in f:
        lines += [f"find = {_q(f['find'])}", f"replace = {_q(f['replace'])}"]
    if "pc" in f:
        lines.append("pc = { " + ", ".join(f"{k} = {_q(v)}" for k, v in f["pc"].items()) + " }")
    lines += [f"symptom = {_q(f['symptom'])}", f"explain = {_q(f['explain'])}"]
    return "\n".join(lines) + "\n"


def make(spec_text, out_id, count=3, seed="faults"):
    """(new spec text, chosen faults). The faults are spread over devices, each caught by a graded item."""
    from . import validate
    spec = tomllib.loads(spec_text)
    spec["_id"] = out_id
    rng = random.Random(seed)
    pool = candidates(spec)
    rng.shuffle(pool)
    chosen, used = [], set()
    for f in pool:
        if len(chosen) == count:
            break
        if f["device"] in used:            # one fault per device: a realistic mix, not one broken box
            continue
        trial = dict(spec)
        trial["lab"] = dict(spec["lab"], kind="troubleshoot")
        trial["fault"] = [f]
        issues, *_ = validate.selfcheck(trial)
        if not any("not detected" in m for _, m in issues):
            chosen.append(f)
            used.add(f["device"])
    text = re.sub(r'(?m)^kind = "\w+"', 'kind = "troubleshoot"', spec_text, count=1)
    text = re.sub(r'(?m)^id = ".*"', f'id = "{out_id}"', text, count=1)
    text = re.sub(r'(?m)^(title = ")(.*)"$', r'\1Troubleshooting: \2"', text, count=1)
    return text.rstrip("\n") + "\n" + "".join(_fault_toml(f) for f in chosen), chosen
