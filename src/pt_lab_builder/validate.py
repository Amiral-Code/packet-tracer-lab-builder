"""Make every lab prove itself.

lint(spec)          problems in the spec itself, found before anything is built
selfcheck(spec)     grade the built networks with the lab's own grade statements:
                    - the answer network must score 100 %
                    - every fault, applied alone to the answer, must make at least one graded item fail
                    - (configure/mixed) graded items that already pass at the start are reported
"""

from __future__ import annotations

import copy
import ipaddress
import json
import re
import shlex
import xml.etree.ElementTree as ET

from . import labgen, ptbuild, ptlab
from .paths import library_dir

NON_PHYSICAL = ("Vlan", "Loopback", "Tunnel", "Port-channel")
INFRA_HOSTS = ("ipphone-7960", "cloud", "hub", "ap")


class Issues(list):
    def error(self, msg):
        self.append(("error", msg))

    def warn(self, msg):
        self.append(("warning", msg))

    @property
    def errors(self):
        return [m for level, m in self if level == "error"]

    def report(self, title):
        if not self:
            print(f"{title}: ok")
            return
        print(f"{title}: {len(self.errors)} error(s), {len(self) - len(self.errors)} warning(s)")
        for level, msg in self:
            print(f"  {'ERROR  ' if level == 'error' else 'warning'} {msg}")


def _index():
    with open(library_dir() / "devices" / "index.json", encoding="utf-8") as fh:
        return json.load(fh)


def _base_rack_reserved():
    """Spans already taken in the base rack (its power distribution unit)."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.parse(library_dir() / "base.xml").getroot()
    except (OSError, ET.ParseError):
        return []
    for node in root.iter("NODE"):
        if node.findtext("TYPE") == "4":
            return [(int(float(c.findtext("X") or 0)), int(float(c.findtext("X") or 0)) + ptbuild.DEFAULT_RACK_UNITS)
                    for c in node.findall("CHILDREN/NODE")]
    return []


def _port_ok(ports, iface):
    """Physical ports must exist on the model; logical ones (Vlan10, Lo0, G0/0.10, Po1) are created by config."""
    if iface in ports:
        return True
    if iface.startswith(NON_PHYSICAL):
        return True
    if "." in iface:
        return iface.split(".")[0] in ports
    return False


def lint(spec) -> Issues:
    issues = Issues()
    lab = spec.get("lab", {})
    if lab.get("kind", "configure") not in ("configure", "troubleshoot", "mixed"):
        issues.error(f"[lab] kind must be configure, troubleshoot or mixed, not {lab.get('kind')!r}")
    for field in ("title", "scenario"):
        if not lab.get(field):
            issues.error(f"[lab] has no {field}")
    activity = spec.get("activity", {})
    if not isinstance(activity, dict):
        issues.error("[activity] must be a table")
        activity = {}
    timer = activity.get("timer", "elapsed")
    if timer not in ("elapsed", "countdown", "none"):
        issues.error(f"[activity] timer must be elapsed, countdown or none, not {timer!r}")
    if timer == "countdown" or "countdown_minutes" in activity:
        minutes = activity.get("countdown_minutes", lab.get("time", 30))
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes <= 0:
            issues.error("[activity] countdown_minutes must be a positive integer")
    convergence = activity.get("answer_convergence_ms", 0)
    if isinstance(convergence, bool) or not isinstance(convergence, int) or convergence < 0:
        issues.error("[activity] answer_convergence_ms must be a non-negative integer")
    if "wizard_password" in activity:
        if not isinstance(activity["wizard_password"], str):
            issues.error("[activity] wizard_password must be a string")
        else:
            issues.warn("[activity] wizard_password is readable by anyone who has the spec: "
                        "prefer ptlab build --password or $PTLAB_PASSWORD")
    if "profile_locked" in activity and not isinstance(activity["profile_locked"], bool):
        issues.error("[activity] profile_locked must be true or false")
    preset = activity.get("locking_preset", "none")
    presets = [preset] if isinstance(preset, str) else preset if isinstance(preset, list) else [None]
    for p in presets:
        if p not in ptlab.LOCKING_PRESETS:
            issues.error(f"[activity] locking_preset must be one or a list of {', '.join(ptlab.LOCKING_PRESETS)}, "
                         f"not {p!r}")
    if "fixed-topology" in presets and any(lk.get("student") for lk in spec.get("link", [])):
        issues.error("[activity] locking_preset fixed-topology locks cabling, but this lab has student = true links")
    if "start_in" in activity and activity["start_in"] not in {s.get("name") for s in spec.get("site", [])}:
        issues.error(f"[activity] start_in {activity['start_in']!r} is not the name of a [[site]]")
    for field in ("complete_feedback", "incomplete_feedback"):
        if field in activity and not isinstance(activity[field], str):
            issues.error(f"[activity] {field} must be a string")
    try:
        index = _index()
    except OSError:
        issues.error("no device library: run `ptlab init --source PATH` first")
        return issues

    # devices
    model, seen = {}, set()
    for d in spec.get("device", []):
        name = d.get("name")
        if not name:
            issues.error("a [[device]] has no name")
            continue
        if name in seen:
            issues.error(f"device name {name} is used twice")
        seen.add(name)
        if d.get("model") not in index:
            issues.error(f"{name}: unknown model {d.get('model')!r} (see `ptlab models`)")
        model[name] = d.get("model")
    ports = {n: index.get(m, {}).get("interfaces", []) for n, m in model.items()}

    def endpoint(text, where):
        parts = text.split(None, 1)
        if len(parts) != 2:
            issues.error(f"{where}: {text!r} must be 'DEVICE PORT'")
            return None
        dev, port = parts[0], labgen.long_if(parts[1])
        if dev not in model:
            issues.error(f"{where}: unknown device {dev}")
            return None
        if port not in ports[dev]:
            issues.error(f"{where}: {dev} has no port {port} (it has {', '.join(ports[dev]) or 'none'})")
        return dev, port

    # links: ports exist, none used twice
    used = {}
    cabled = set()
    for i, lk in enumerate(spec.get("link", []), 1):
        for side in ("a", "b"):
            ep = endpoint(lk.get(side, ""), f"link {i}")
            if ep:
                if ep in used:
                    issues.error(f"{ep[0]} {labgen.short_if(ep[1])} is cabled twice (links {used[ep]} and {i})")
                used[ep] = i
                cabled.add(ep)

    # multilayer-switch ports are switchports: an IP address on a physical port needs "no switchport" first
    # (IOS and Packet Tracer reject the address otherwise, and the port's assessment items are silently dropped)
    for which in ("start", "answer"):
        for name, text in spec.get("config", {}).get(which, {}).items():
            if not str(model.get(name, "")).startswith("l3switch"):
                continue
            for head, body in ptlab.blocks(text.splitlines()).items():
                if not head.startswith("interface ") or head.split()[1].startswith(("Vlan", "Loopback", "Port-channel", "Tunnel", "vlan", "lo", "po", "Lo", "Po")):
                    continue
                if any(l.startswith("ip address ") for l in body) and "no switchport" not in body:
                    issues.error(f"[config.{which}] {name} {head}: an IP address on a multilayer-switch port needs "
                                 f"'no switchport' first")

    # sites: each device in at most one site; unlisted devices go to the first site
    sites = spec.get("site", [])
    site_of = {}
    for st in sites:
        if not st.get("name"):
            issues.error("a [[site]] has no name")
            continue
        for n in st.get("devices", []):
            if n not in model:
                issues.error(f"site {st['name']!r}: unknown device {n}")
            elif n in site_of:
                issues.error(f"{n} is in two sites ({site_of[n]!r} and {st['name']!r})")
            else:
                site_of[n] = st["name"]
    if len({st.get("name") for st in sites}) != len(sites):
        issues.error("two [[site]] tables share a name")
    first_site = sites[0]["name"] if sites else None

    x1, y1, x2, y2 = ptbuild.CLOSET_ICON
    for d in spec.get("device", []):
        ph = d.get("physical")
        if isinstance(ph, dict) and ph.get("location") == "building" and "x" in ph and "y" in ph \
                and x1 <= ph["x"] <= x2 and y1 <= ph["y"] <= y2:
            issues.warn(f"{d['name']}: building position ({ph['x']}, {ph['y']}) is under the wiring-closet icon; "
                        f"use x > {x2} or y > {y2}, or omit x/y for the automatic floor grid")

    # racks: generated devices stacked by measured model height must fit, per site
    racks = {}
    for d in spec.get("device", []):
        ph = d.get("physical")
        ph = {"location": ph} if isinstance(ph, str) else dict(ph or {})
        rackable = str(d.get("model", "")).startswith(("router", "switch", "l3switch", "wlc", "server"))
        if ph.get("location", "rack" if rackable else "building") == "rack" and "x" not in ph:
            racks.setdefault(site_of.get(d.get("name"), first_site), []).append((d.get("name"), d.get("model"), ph.get("slot")))
    for site, rack in racks.items():
        reserved = _base_rack_reserved() if site == first_site else []
        xs = ptbuild.stack_rack([(m, sl) for _, m, sl in rack], reserved)
        over = [f"{n} ({m}, needs {ptbuild.rack_units(m)} units at {xs[i]})" for i, (n, m, _) in enumerate(rack)
                if xs[i] + ptbuild.rack_units(m) > ptbuild.RACK_CAPACITY]
        if over:
            used = max(xs[i] + ptbuild.rack_units(m) for i, (_, m, _) in enumerate(rack))
            where = f"site {site!r}'s rack" if site else "the rack"
            issues.error(f"{where} is full ({used} of {ptbuild.RACK_CAPACITY} units needed): "
                         f"{'; '.join(over)} would hang below it. Move devices to "
                         f"physical = {{ location = \"closet\" }} or split them into [[site]] racks")

    # areas
    in_area = {}
    for a in spec.get("area", []):
        for n in a.get("devices", []):
            if n not in model:
                issues.error(f"area {a.get('label')!r}: unknown device {n}")
            elif n in in_area:
                issues.warn(f"{n} is in two areas ({in_area[n]!r} and {a.get('label')!r})")
            else:
                in_area[n] = a.get("label")

    # addressing
    addrs = {}           # ip -> (device, iface)
    nets = []            # (network, device, iface) for router/switch interfaces
    for row in labgen.addressing_rows(spec):
        if len(row) < 3:
            issues.error(f"addressing row {row} needs device, interface, address")
            continue
        dev, iface, cidr = row[0], labgen.long_if(row[1]), row[2]
        if dev not in model:
            issues.error(f"addressing: unknown device {dev}")
            continue
        if not _port_ok(ports[dev], iface):
            issues.error(f"addressing: {dev} has no port {iface}")
        if not cidr or cidr.lower() == "dhcp":
            continue
        try:
            n = ipaddress.ip_interface(cidr)
        except ValueError:
            issues.error(f"addressing: {dev} {row[1]}: {cidr!r} is not an address/prefix")
            continue
        if n.ip in (n.network.network_address, n.network.broadcast_address) and n.network.prefixlen < 31:
            issues.error(f"addressing: {dev} {row[1]}: {cidr} is the network or broadcast address")
        if str(n.ip) in addrs:
            other = addrs[str(n.ip)]
            issues.error(f"addressing: {n.ip} is used by both {other[0]} {other[1]} and {dev} {row[1]}")
        addrs[str(n.ip)] = (dev, row[1])
        if not labgen.ptbuild_model_is_host(model[dev]):
            nets.append((n, dev, iface))
            if not iface.startswith(NON_PHYSICAL) and "." not in iface and (dev, iface) not in cabled:
                issues.warn(f"addressing: {dev} {row[1]} has an address but no cable")
    virtual = {st.split()[4] for st in spec.get("grade", {}).get("items", []) if st.split()[:1] == ["hsrp"]
               and len(st.split()) > 4}
    for row in labgen.addressing_rows(spec):
        if len(row) < 4 or not row[3] or row[0] not in model or not row[2] or row[2].lower() == "dhcp":
            continue
        dev, cidr, gw = row[0], row[2], row[3]
        try:
            n, g = ipaddress.ip_interface(cidr), ipaddress.ip_address(gw)
        except ValueError:
            issues.error(f"addressing: {dev}: gateway {gw!r} is not an address")
            continue
        if g.version != n.version:
            issues.error(f"addressing: {dev} gateway {gw} and address {cidr} are different IP versions")
        elif g not in n.network and not (g.version == 6 and g.is_link_local):
            issues.error(f"addressing: {dev} gateway {gw} is outside its subnet {n.network}")
        elif g.version == 6 and g.is_link_local:
            pass                     # a router's link-local address: set in its config, not in the table
        elif str(g) in virtual:
            pass                     # an HSRP virtual address
        elif str(g) not in addrs:
            issues.warn(f"addressing: {dev} gateway {gw} is not any device's address in the table")

    # grade statements
    statements = spec.get("grade", {}).get("items", [])
    if not statements:
        issues.error("[grade] has no items: Check Results would score nothing")
    points = spec.get("grade", {}).get("points", {})
    if not isinstance(points, dict):
        issues.error("[grade.points] must be a table mapping exact grade statements to positive integers")
        points = {}
    for statement, value in points.items():
        if statement not in statements:
            issues.error(f"[grade.points] refers to a statement not present in items: {statement!r}")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            issues.error(f"[grade.points] {statement!r} must be a positive integer")
    table = {(r[0], labgen.long_if(r[1])): r[2] for r in labgen.addressing_rows(spec) if len(r) >= 3}
    try:
        first4, first6 = labgen.first_addresses(spec)
    except ValueError:
        first4, first6 = {}, {}
    first_addr, first_addr6 = set(first4), set(first6)
    for st in statements:
        w = st.split()
        if not w or w[0] not in labgen.GRADE_STATEMENTS:
            issues.error(f"grade: unknown statement {st!r} (known: {', '.join(labgen.GRADE_STATEMENTS)})")
            continue
        if len(w) < 2 or w[1] not in model:
            issues.error(f"grade: {st!r}: unknown device")
            continue
        problem = _statement_problem(w, st, model, ports, first_addr, first_addr6)
        if problem:
            issues.error(f"grade: {st!r}: {problem}")
            continue
        if w[0] in ("ip", "up", "ip6"):
            if len(w) < 3:
                issues.error(f"grade: {st!r}: missing interface")
                continue
            iface = labgen.long_if(w[2])
            if not _port_ok(ports[w[1]], iface):
                issues.error(f"grade: {st!r}: {w[1]} has no port {iface}")
            if w[0] == "ip" and (w[1], iface) in table and len(w) == 4 and table[(w[1], iface)] != w[3]:
                issues.warn(f"grade: {st!r} differs from the addressing table ({table[(w[1], iface)]})")

    # balance: configuration items say what was typed, outcome tests say whether it works; a lab needs both
    kinds = [st.split()[0] for st in statements if st.split()]
    outcome = [k for k in kinds if k in labgen.CONNECTIVITY_STATEMENTS]
    config = [k for k in kinds if k not in labgen.CONNECTIVITY_STATEMENTS and k not in ("up", "cable")]
    if statements and not outcome:
        issues.warn("grade: only configuration is graded; add ping/tcp/udp tests so a working network is also proven")
    elif statements and not config and not any(lk.get("student") for lk in spec.get("link", [])):
        issues.warn("grade: only outcomes are graded; add configuration items so partial work earns partial credit "
                    "and Check Results can point at what is wrong")

    # faults
    for i, f in enumerate(spec.get("fault", []), 1):
        if f.get("device") not in model:
            issues.error(f"fault {i}: unknown device {f.get('device')!r}")
        if not any(k in f for k in ("apply", "find", "pc")):
            issues.error(f"fault {i} ({f.get('device')}): needs apply, find/replace, or pc")
        for k in ("symptom", "explain"):
            if not f.get(k):
                issues.warn(f"fault {i} ({f.get('device')}): no {k} (the answer guide shows it)")
    if spec.get("fault") and lab.get("kind", "configure") == "configure":
        issues.warn("faults are ignored in a configure lab: use kind = troubleshoot or mixed")
    return issues


def _statement_problem(w, st, model, ports, first_addr, first_addr6=()):
    """Shape errors for one grade statement, or None."""
    k = w[0]
    need = {"ip": 5 if len(w) > 3 and w[3] == "in" else 4, "ip6": 4, "up": 3, "gw": 3, "gw6": 3, "hostname": 3,
            "dhcp": 2, "vlan": 4, "access": 4, "route": 4, "route6": 4, "ospf": 5, "rid": 4, "passive": 4, "stp": 4,
            "portfast": 3, "nat": 4, "acl": 5, "cable": 5}
    if k in need and len(w) != need[k]:
        return f"expects {need[k] - 1} fields after '{k}'"
    host = labgen.ptbuild_model_is_host(model.get(w[1], ""))
    ios_only = ("route", "route6", "ospf", "rid", "passive", "stp", "portfast", "portsec", "nat", "acl", "hsrp",
                "pool", "secret", "user", "banner", "desc", "vlan", "access", "trunk", "line", "in", "hostname")
    if host and k in ios_only:
        return f"{w[1]} is a host; '{k}' grades IOS configuration"
    if not host and k in ("gw", "gw6", "dhcp"):
        return f"{w[1]} is not a host; '{k}' grades a PC/server setting"
    try:
        if k == "line" and len(w) < 3:
            return "missing the config line"
        if k == "in":
            parts = shlex.split(st)
            if len(parts) != 4:
                return 'write it as: in DEV "PARENT LINE" "SUB-COMMAND" (quote both)'
        if k == "ip" and len(w) == 5:
            ipaddress.ip_network(w[4], strict=True)
        elif k == "ip":
            ipaddress.ip_interface(w[3])
        if k in ("ip6", "gw6", "route6"):
            if k == "ip6" and ipaddress.ip_interface(w[3]).version != 6:
                return "needs an IPv6 address/prefix"
            if k == "gw6":
                ipaddress.IPv6Address(w[2])
            if k == "route6":
                ipaddress.IPv6Network(w[2], strict=True)
        if k == "gw":
            for a in w[2].split("|"):
                ipaddress.IPv4Address(a)
        if k in ("ip", "ip6", "portfast", "portsec", "desc", "nat", "acl", "hsrp") and len(w) > 2:
            if not _port_ok(ports[w[1]], labgen.long_if(w[2])):
                return f"{w[1]} has no port {labgen.long_if(w[2])}"
        if k == "rid":
            int(w[2]); ipaddress.IPv4Address(w[3])
        if k == "passive":
            int(w[2])
        if k == "portsec":
            opts = w[3:]
            i = 0
            while i < len(opts):
                if opts[i] == "max":
                    if not 1 <= int(opts[i + 1]) <= 8192:
                        return "max must be 1-8192"
                    i += 2
                elif opts[i] == "violation":
                    if opts[i + 1] not in ("protect", "restrict", "shutdown"):
                        return "violation is protect, restrict or shutdown"
                    i += 2
                elif opts[i] == "sticky":
                    i += 1
                else:
                    return "options are: max N, sticky, violation protect|restrict|shutdown"
        if k in ("desc", "banner"):
            text = " ".join(shlex.split(st)[3 if k == "desc" else 2:])
            if not text:
                return "give the text, ~word (contains, any case) or any (not blank)"
        if k == "nat" and w[3] not in ("inside", "outside"):
            return "write it as: nat DEV IFACE inside|outside"
        if k == "acl" and w[4] not in ("in", "out"):
            return "write it as: acl DEV IFACE NAME in|out"
        if k == "hsrp":
            if len(w) < 5:
                return "write it as: hsrp DEV IFACE GROUP VIP [priority N] [preempt]"
            if not 0 <= int(w[3]) <= 4095:
                return "HSRP group must be 0-4095"
            ipaddress.IPv4Address(w[4])
            rest = w[5:]
            if "priority" in rest:
                if not 0 <= int(rest[rest.index("priority") + 1]) <= 255:
                    return "priority must be 0-255"
            if [x for x in rest if x not in ("priority", "preempt") and not x.isdigit()]:
                return "options are: priority N, preempt"
        if k == "pool":
            if len(w) < 4 or len(w) % 2:
                return "write it as: pool DEV NAME NET/LEN [gw A.B.C.D] [dns A.B.C.D]"
            ipaddress.ip_network(w[3], strict=True)
            for key, val in zip(w[4::2], w[5::2]):
                if key not in ("gw", "dns"):
                    return "options are: gw A.B.C.D, dns A.B.C.D"
                ipaddress.IPv4Address(val)
        if k == "secret" and len(shlex.split(st)) != 3:
            return "write it as: secret DEV PASSWORD"
        if k == "user" and len(shlex.split(st)) != 4:
            return "write it as: user DEV NAME PASSWORD"
        if k in ("vlan", "access") and not 1 <= int(w[2 if k == "vlan" else 3]) <= 4094:
            return "VLAN must be 1-4094"
        if k in ("access", "trunk"):
            if len(w) < 3:
                return "missing interface"
            if not _port_ok(ports[w[1]], labgen.long_if(w[2])):
                return f"{w[1]} has no port {labgen.long_if(w[2])}"
        if k == "trunk":
            opts = w[3:]
            if len(opts) % 2 or any(o not in ("allowed", "native") for o in opts[::2]):
                return "options are 'allowed LIST' and 'native VLAN'"
            if "allowed" in opts:
                labgen.vlan_list(opts[opts.index("allowed") + 1])
        if k == "route":
            ipaddress.ip_network(w[2], strict=True)
        if k == "ospf":
            ipaddress.ip_network(w[3], strict=True)
            int(w[2])
        if k == "stp":
            labgen.vlan_list(w[2])
            if int(w[3]) % 4096 or not 0 <= int(w[3]) <= 61440:
                return "priority must be a multiple of 4096 from 0 to 61440"
        if k == "cable":
            if w[3] not in model:
                return f"unknown device {w[3]}"
            for dev, port in ((w[1], w[2]), (w[3], w[4])):
                if labgen.long_if(port) not in ports[dev]:
                    return f"{dev} has no port {labgen.long_if(port)}"
        if k in labgen.CONNECTIVITY_STATEMENTS:
            base = 4 if k in ("tcp", "udp") else 3
            syntax = (f"{k} SRC DST PORT [A.B.C.D] [fail]" if k in ("tcp", "udp")
                      else f"{k} SRC DST [A.B.C.D] [fail]")
            if len(w) < base:
                return f"write it as: {syntax}, with DST a device name"
            if w[2] not in model:
                return f"unknown device {w[2]}"
            if k in ("tcp", "udp") and not 1 <= int(w[3]) <= 65535:
                return f"{k.upper()} port must be 1-65535"
            if k == "udp" and int(w[3]) in labgen.UDP_SERVICE_PORTS:
                return (f"UDP/{w[3]} is {labgen.UDP_SERVICE_PORTS[int(w[3])]}: Packet Tracer's UDP test fails when a "
                        f"service receives it, so it cannot prove a service works; use a port with no service "
                        f"(UDP tests prove delivery and ACL filtering only)")
            rest = w[base:]
            if rest.count("fail") > 1:
                return "use 'fail' at most once"
            addresses = [x for x in rest if x != "fail"]
            if len(addresses) > 1:
                return f"write it as: {syntax}"
            if addresses:
                (ipaddress.IPv6Address if k == "ping6" else ipaddress.IPv4Address)(addresses[0])
            elif k == "ping6":
                if w[2] not in first_addr6:
                    return f"{w[2]} has no IPv6 address in the addressing table: add the destination address"
            elif w[2] not in first_addr:
                return f"{w[2]} has no address in the addressing table: add the destination address"
            if k == "ping6" and w[1] not in first_addr6:
                return f"{w[1]} has no IPv6 address in the addressing table: ICMPv6 tests need a source address"
            if k != "ping" and w[1] not in first_addr:
                return f"{w[1]} has no address in the addressing table: TCP and UDP tests need a source address"
    except ValueError as e:
        return str(e)
    return None


def _grade(spec, which, s=None):
    s = s or spec
    t = labgen.build_topology(s, labgen.configs_for(s, which), labgen.pcs_for(s, which), which)
    _, checks = labgen.compile_grade(spec)
    return checks, ptlab.grade({"check": checks}, t.tree, checks, quiet=True)


def selfcheck(spec) -> Issues:
    issues = Issues()
    kind = spec["lab"].get("kind", "configure")
    checks, answer = _grade(spec, "answer")
    for c, ok in zip(checks, answer):
        if not ok:
            issues.error(f"the answer network fails its own grade item: {c['desc']}")
    _, start = _grade(spec, "start")
    if kind in ("configure", "mixed"):
        free = [c["desc"] for c, ok in zip(checks, start) if ok]
        if free and len(free) == len(checks):
            issues.error("every graded item already passes in the start network: the lab has nothing to do")
        elif free and kind == "configure":
            issues.warn(f"{len(free)} graded item(s) already pass at the start: {'; '.join(free[:4])}"
                        + (" ..." if len(free) > 4 else ""))
    pings = labgen.connectivity_tests(spec)
    for i, f in enumerate(spec.get("fault", []), 1):
        alone = copy.deepcopy(spec)
        alone["lab"]["kind"] = "troubleshoot"
        alone["fault"] = [f]
        _, res = _grade(spec, "start", alone)
        if all(res):
            msg = f"fault {i} ({f.get('device')}: {f.get('symptom', '')[:50]}) is not detected by any graded item"
            if pings:  # a ping test may catch it, but only Packet Tracer can run one
                issues.warn(msg + "; only a connectivity test could catch it (verify in Packet Tracer)")
            else:
                issues.error(msg)
    return issues, sum(answer), len(answer), sum(start)


def graded_paths(comparisons_root, values=False):
    """Paths (device > ... > item ID) of every graded leaf (checkType 2) under a COMPARISONS/NODE tree;
    with values=True a {path: (nodeValue, variableName)} dict."""
    out = {}

    def walk(node, path):
        here = path + [node.findtext("ID") or ""]
        name = node.find("NAME")
        if name is not None and name.get("checkType") == "2":
            out[" > ".join(here[1:])] = (name.get("nodeValue", ""), name.get("variableName", ""))
        for child in node.findall("NODE"):
            walk(child, here)

    if comparisons_root is not None:
        walk(comparisons_root, [])
    return out if values else list(out)


def verify_saved(spec, saved):
    """Compare a lab with the same activity after Packet Tracer has opened and saved it.

    Packet Tracer silently drops assessment items whose node does not exist in its own answer network (already at
    load time, so a save made right after opening is enough). Reports dropped items and connectivity tests, and
    runs the local checks against Packet Tracer's rewritten answer network, which `ptlab check` relies on."""
    issues = Issues()
    items, checks = labgen.compile_grade(spec)
    expected = graded_paths(ptlab.comparisons(items).find("NODE"))
    tree = ptlab.read_pkt(saved)
    root = tree.getroot()
    if root.tag != "PACKETTRACER5_ACTIVITY":
        issues.error(f"{saved} is not an activity (.pka)")
        return issues, {}
    built = graded_paths(ptlab.comparisons(items).find("NODE"), values=True)
    saved_values = graded_paths(root.find("COMPARISONS/NODE"), values=True)
    kept = set(saved_values)
    dropped = [p for p in expected if p not in kept]
    for p in dropped:
        issues.error(f"Packet Tracer dropped the item {p}: it does not exist in its answer network")
    # Packet Tracer keeps the value and pattern written for a graded item as they are (it does not refresh them from
    # its answer network), so only a changed pattern is a finding here; value formats are proven by verify_values
    for p in expected:
        if p in kept and built[p][1] != saved_values[p][1]:
            issues.error(f"Packet Tracer changed the answer pattern of {p}: {built[p][1]!r} -> {saved_values[p][1]!r}")
    for p in sorted(kept - set(expected)):
        issues.warn(f"Packet Tracer grades an item the spec did not ask for: {p}")
    nets = root.findall("PACKETTRACER5")
    answer = nets[2] if len(nets) >= 3 else None
    tests = labgen.connectivity_tests(spec)
    saved_tests = len(answer.findall("SCENARIOSET/SCENARIO/PDU")) if answer is not None else 0
    if saved_tests < len(tests):
        issues.error(f"Packet Tracer kept {saved_tests} of {len(tests)} connectivity tests")
    passed = 0
    if answer is not None:
        res = ptlab.grade({"check": checks}, ET.ElementTree(answer), checks, quiet=True)
        passed = sum(res)
        for c, ok in zip(checks, res):
            if not ok:
                issues.error(f"local check fails on Packet Tracer's answer network: {c['desc']} "
                             f"(ptlab check would mark a correct student wrong)")
    return issues, {"expected": len(expected), "kept": len(expected) - len(dropped), "tests": len(tests),
                    "saved_tests": saved_tests, "local": passed, "local_total": len(checks)}


def strip_assessment(src, dst):
    """A copy of a built activity with every assessment item removed. Opened and saved by Packet Tracer, it comes
    back with the whole assessment tree filled in from Packet Tracer's own answer network: the reference for the
    value of every item the builder writes (see verify_values)."""
    tree = ptlab.read_pkt(src)
    node = tree.getroot().find("COMPARISONS/NODE")
    if node is None:
        raise ValueError(f"{src} is not a built activity")
    for child in node.findall("NODE"):
        node.remove(child)
    ptlab.write_pkt(tree, dst)


def verify_values(spec, bare_saved):
    """Compare the value of every graded item with the value Packet Tracer itself fills in for that node."""
    issues = Issues()
    items, _ = labgen.compile_grade(spec)
    built = graded_paths(ptlab.comparisons(items).find("NODE"), values=True)
    filled = {}

    def walk(node, path):
        here = path + [node.findtext("ID") or ""]
        name = node.find("NAME")
        if name is not None:
            filled[" > ".join(here[1:])] = name.get("nodeValue", "")
        for child in node.findall("NODE"):
            walk(child, here)

    root = ptlab.read_pkt(bare_saved).getroot().find("COMPARISONS/NODE")
    if root is not None:
        walk(root, [])
    same = 0
    for path, (value, pattern) in built.items():
        if path not in filled:
            issues.error(f"Packet Tracer has no node {path}")
        elif filled[path].strip() != value.strip():
            msg = f"{path}: the lab writes {value!r}, Packet Tracer's own value is {filled[path]!r}"
            if pattern:     # graded by its pattern; the value is only what the Activity Wizard displays
                issues.warn(msg + " (graded by pattern)")
                same += bool(re.search(pattern[len("{{RegEx:"):-2], filled[path]))
            else:
                issues.error(msg)
        else:
            same += 1
    return issues, {"items": len(built), "same": same}
