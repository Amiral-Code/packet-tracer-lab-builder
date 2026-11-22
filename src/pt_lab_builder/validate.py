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

from . import labgen, ptlab
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
    for row in labgen.addressing_rows(spec):
        if len(row) < 4 or not row[3] or row[0] not in model or not row[2] or row[2].lower() == "dhcp":
            continue
        dev, cidr, gw = row[0], row[2], row[3]
        try:
            n, g = ipaddress.ip_interface(cidr), ipaddress.ip_address(gw)
        except ValueError:
            issues.error(f"addressing: {dev}: gateway {gw!r} is not an address")
            continue
        if g not in n.network:
            issues.error(f"addressing: {dev} gateway {gw} is outside its subnet {n.network}")
        elif str(g) not in addrs:
            issues.warn(f"addressing: {dev} gateway {gw} is not any device's address in the table")

    # grade statements
    statements = spec.get("grade", {}).get("items", [])
    if not statements:
        issues.error("[grade] has no items: Check Results would score nothing")
    table = {(r[0], labgen.long_if(r[1])): r[2] for r in labgen.addressing_rows(spec) if len(r) >= 3}
    for st in statements:
        w = st.split()
        if not w or w[0] not in ("ip", "up", "gw", "hostname", "line", "dhcp"):
            issues.error(f"grade: unknown statement {st!r}")
            continue
        if len(w) < 2 or w[1] not in model:
            issues.error(f"grade: {st!r}: unknown device")
            continue
        if w[0] in ("ip", "up"):
            if len(w) < 3:
                issues.error(f"grade: {st!r}: missing interface")
                continue
            iface = labgen.long_if(w[2])
            if not _port_ok(ports[w[1]], iface):
                issues.error(f"grade: {st!r}: {w[1]} has no port {iface}")
            if w[0] == "ip" and (w[1], iface) in table and len(w) > 3 and table[(w[1], iface)] != w[3]:
                issues.warn(f"grade: {st!r} differs from the addressing table ({table[(w[1], iface)]})")

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


def _grade(spec, which, s=None):
    s = s or spec
    t = labgen.build_topology(s, labgen.configs_for(s, which), labgen.pcs_for(s, which))
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
    for i, f in enumerate(spec.get("fault", []), 1):
        alone = copy.deepcopy(spec)
        alone["lab"]["kind"] = "troubleshoot"
        alone["fault"] = [f]
        _, res = _grade(spec, "start", alone)
        if all(res):
            issues.error(f"fault {i} ({f.get('device')}: {f.get('symptom', '')[:50]}) is not detected by any graded item")
    return issues, sum(answer), len(answer), sum(start)
