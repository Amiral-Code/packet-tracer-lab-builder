"""Live checks without a human: a copy of a built activity that solves itself inside Packet Tracer.

`instrument()` adds a File Script Module to a copy of a built .pka. When Packet Tracer opens that copy, the script
(Packet Tracer's own JavaScript engine and IPC API) records the Check Results score of the start state, does what a
student would do (adds the student's cables, types every device's answer configuration into its CLI, sets the host
addresses), waits for the network to settle, then records the score again, runs the Connectivity Tests, saves the
solved network and writes a JSON report. A harness opens the copy hidden and accepts the script-privilege prompt
(see the user's pt-live-check.sh); `report()` turns the JSON into a verdict.

Packet Tracer facts this relies on (Packet Tracer 9.0, observed 2026-11-24):
- a File Script Module runs its scripts' main() when the file opens; with privileges declared, Packet Tracer first
  asks to allow them (Enter accepts);
- SystemFileManager.writeTextToFile() writes scrambled bytes; writePlainTextToFile() writes the text;
- CiscoDevice.enterCommand(cmd, mode) types into the CLI (mode "global" enters configuration mode, "" continues
  in the current mode) and returns [status, output] (0 = ok).
"""
import base64
import copy
import json
import xml.etree.ElementTree as ET

from . import labgen, ptlab

PRIVILEGES = ("GET_NETWORK_INFO", "CHANGE_NETWORK_INFO", "SIMULATION_MODE", "MISC_GUI", "FILE", "ACTIVITY_WIZARD",
              "IPC", "APPLICATION")
CONNECT = {"eStraightThrough": 8100, "eCrossOver": 8101, "eFiber": 8103, "eSingleMode": 8103, "eMultiMode": 8103,
           "ePhoneLine": 8104, "eSerialDCE": 8106,
           "eSerialDTE": 8106, "eCoaxial": 8110}

SCRIPT = r"""
var PLAN = __PLAN__;
var RES = {stage: "started", errors: [], commands: 0, rejected: [], links: [], hosts: [], notes: [], mode: PLAN.mode || "solve"};
function out() { ipc.systemFileManager().writePlainTextToFile(PLAN.result, JSON.stringify(RES)); }
function score(f) { return {correct: f.getCorrectAssessmentItemsCount(), total: f.getAssessmentItemsCount(),
                            percent: f.getPercentageComplete()}; }
function main() { setTimeout(solve, PLAN.boot_ms); }
function cleanUp() {}

function solve() {
    try {
        var f = ipc.appWindow().getActiveFile();
        var net = ipc.network();
        RES.before = score(f);
        RES.stage = "cabling";
        var lw = ipc.appWindow().getActiveWorkspace().getLogicalWorkspace();
        for (var i = 0; i < PLAN.links.length; i++) {
            var l = PLAN.links[i];
            RES.links.push([l.a + " " + l.pa + " - " + l.b + " " + l.pb, lw.createLink(l.a, l.pa, l.b, l.pb, l.type)]);
        }
        RES.stage = "configuring";
        for (var name in PLAN.configs) {
            var dev = net.getDevice(name);
            if (!dev) { RES.errors.push("no device " + name); continue; }
            typeConfig(name, dev, PLAN.configs[name]);
        }
        RES.stage = "wireless";
        for (var wn in PLAN.wireless) {
            var wd = net.getDevice(wn), ws = PLAN.wireless[wn];
            try {
                if (ws.role === "server") {
                    var srv = wd.getProcess("WirelessServer");
                    srv.setSsid(ws.ssid); srv.setAuthenType(ws.auth); srv.setEncryptType(ws.enc);
                    if (ws.key) srv.getWpaProcess().setKey(ws.key);   // WPA keys live in the WPA process, not WEP
                } else {
                    // the client's own settings, like the router's (setCurrentProfileStringIPs overran an internal
                    // list with the arguments tried); its address comes from the host settings below
                    var cli = wd.getProcess("WirelessClient");
                    cli.setSsid(ws.ssid); cli.setAuthenType(ws.auth); cli.setEncryptType(ws.enc);
                    if (ws.key) cli.getWpaProcess().setKey(ws.key);
                    cli.resetAllAssociations();          // re-scan with the new settings
                    RES.notes.push(wn + ": a wireless client's network profile cannot be set through Packet Tracer 9's " +
                                   "API, so it may not join; prove its connectivity with --answer");
                }
            } catch (e) { RES.errors.push("wireless " + wn + ": " + e); }
        }
        RES.stage = "hosts";
        setHosts(false);
        RES.stage = "settling";
        out();
        setTimeout(function () {
            // DHCP clients start only now: a request sent while spanning tree still blocks a freshly configured
            // access port is lost (observed: the host fell back to 169.254/16), as a student's would be
            if (PLAN.dhcp_ms) { setHosts(true); RES.stage = "leasing"; out(); }
            setTimeout(grade, PLAN.dhcp_ms);
        }, PLAN.settle_ms);
    } catch (e) { RES.errors.push("solve: " + e); out(); }
}

function setHosts(dhcp) {
    var net = ipc.network();
        for (var h in PLAN.hosts) {
            var s = PLAN.hosts[h];
            if (!!s.dhcp !== dhcp) continue;
            var d = net.getDevice(h);
            if (!d) { RES.errors.push("no host " + h); continue; }
            var p = d.getPort(s.port);
            if (s.dhcp) { p.setDhcpClientFlag(true); if (d.setDhcpFlag) d.setDhcpFlag(true); }
            else if (s.ip) { p.setIpSubnetMask(s.ip, s.mask); }
            if (s.gw) d.setDefaultGateway(s.gw);
            for (var k = 0; k < s.ip6.length; k++) {      // static addresses; the GUI leaves IPV6_ENABLED false
                RES.hosts.push([h, s.ip6[k][0], p.addIpv6Address(s.ip6[k][0], s.ip6[k][1], 0, false)]);
            }
            if (s.gw6) {             // the GUI sets it on the port and on the host's IPv6 process; ping6 needs the port one
                try { p.setv6DefaultGateway(s.gw6); d.getProcess("HostIpv6").setDefaultGateway(s.gw6); }
                catch (e) { RES.notes.push(h + ": IPv6 gateway " + s.gw6 + " not set: " + e); }
            }
        }
}

// Types a configuration at the device's console (getConsoleLine) exactly as a person would. The command API
// CiscoDevice.enterCommand refused valid lines: an ASA object's `nat (inside,outside) dynamic interface` (its
// tokenizer chokes on "(inside,outside)"; "( inside , outside )" passes) and section changes in "current" mode. Replies are collected from the
// console's outputWritten event; an IOS/ASA error marker after a line marks that line as rejected.
var ERR = /% ?(Invalid|Incomplete|Ambiguous|Unknown)|ERROR:/;
function typeConfig(name, dev, lines) {
    var term = null, how = ["getConsoleLine", "getCommandLine", "getIpcTerminalLine"];   // the console first: it parses like a person typing
    for (var h = 0; h < how.length && !term; h++) {     // an ASA has no getCommandLine(): try its other consoles
        try { if (dev[how[h]]) { term = dev[how[h]](); if (term && !term.enterCommand) term = null; } } catch (e) {}
        if (term && h > 0) RES.notes.push(name + ": no console line; typed through " + how[h]);
    }
    if (!term) { RES.errors.push(name + ": no console to type into"); return; }
    var buf = { text: "" };
    var grab = function (src, args) { for (var k in args) if (typeof args[k] === "string") buf.text += args[k]; };
    try { term.registerEvent("outputWritten", null, grab); } catch (e) { RES.notes.push(name + ": no console output events"); }
    var send = function (cmd) { var at = buf.text.length; term.enterCommand(cmd); RES.commands++; return buf.text.slice(at); };
    send("");
    send("enable");
    if (/assword/.test(String(term.getPrompt()))) send("");      // an ASA asks even when no password is set
    send("configure terminal");
    for (var j = 0; j < lines.length; j++) {
        var reply = send(lines[j][1]);
        if (ERR.test(reply)) RES.rejected.push([name, lines[j][1], "console", reply.replace(/\s+/g, " ").slice(0, 200)]);
    }
    RES.prompts = RES.prompts || {};
    RES.prompts[name] = String(term.getPrompt());
    try { term.unregisterEvent("outputWritten", null, grab); } catch (e) {}
}

function grade() {
    try {
        RES.stage = "grading";
        out();
        var f = ipc.appWindow().getActiveFile();
        RES.after = score(f);
        RES.stage = "testing";
        out();
        // the first run warms the network up (ARP, NAT, inspection state): its first packets can be lost, exactly
        // as a student's first Check Results; the second run is the one reported
        f.runConnectivityTests();
        setTimeout(function () {
            try {
                RES.warmup = f.getLastConnectivityTestCorrectCount();
                ipc.appWindow().getActiveFile().runConnectivityTests();
            } catch (e) { RES.errors.push("tests: " + e); }
            setTimeout(finish, PLAN.tests_ms);
        }, PLAN.tests_ms);
    } catch (e) { RES.errors.push("grade: " + e); out(); }
}

function finish() {
    try {
        var f = ipc.appWindow().getActiveFile();
        RES.tests = {correct: f.getLastConnectivityTestCorrectCount(), total: f.getConnectivityCount(), results: []};
        for (var i = 0; i < RES.tests.total; i++) RES.tests.results.push(String(f.getLastConnectivityTestResultAt(i)));
        RES.stage = "tested";
        out();                     // the results first: a save can open a modal dialog that stops this script
        if (PLAN.save) {
            if (ipc.systemFileManager().fileExists(PLAN.save)) RES.notes.push("not saved: " + PLAN.save + " exists");
            else RES.saved = ipc.appWindow().fileSaveAs(PLAN.save);
        }
        RES.stage = "done";
    } catch (e) { RES.errors.push("finish: " + e); }
    out();
}
"""


def plan(spec, result_path, save_path=None):
    """What the script does for this lab: cables, CLI lines per device, host settings, timings."""
    models = {d["name"]: d["model"] for d in spec["device"]}
    links = []
    for lk in spec.get("link", []):
        if lk.get("student"):
            (na, pa), (nb, pb) = lk["a"].split(None, 1), lk["b"].split(None, 1)
            pa, pb = labgen.long_if(pa), labgen.long_if(pb)
            cable = lk.get("cable") or labgen.cable_for(models[na], models[nb], pa, pb)
            if cable == "eSerialDTE":   # createLink makes its first end the DCE
                (na, pa), (nb, pb) = (nb, pb), (na, pa)
            links.append({"a": na, "pa": pa, "b": nb, "pb": pb, "type": CONNECT[cable]})
    configs = {}
    for name, lines in undo_faults(spec).items():
        configs[name] = lines
    for name, text in spec.get("config", {}).get("answer", {}).items():
        lines = configs.get(name, [])
        for raw in text.strip("\n").splitlines():
            line = raw.rstrip()
            if line.strip() and line.strip() not in ("!", "end", "exit", "conf t", "configure terminal", "enable"):
                if line.startswith("interface "):
                    line = "interface " + labgen.long_if(line.split(None, 1)[1])
                lines.append([line.startswith(" "), line.strip()])   # [is a sub-command, text]
        lines.append([True, "end"])         # leave configuration mode, as a student would
        configs[name] = lines
    hosts = {}
    first6 = {}
    for row in labgen.addressing_rows(spec):
        if len(row) >= 3 and row[2] and ":" in row[2]:
            n = row[2].split("/")
            first6.setdefault(row[0], []).append([labgen.v6(n[0]), int(n[1])])
    for name, s in labgen.pcs_for(spec, "answer").items():
        port = next((labgen.long_if(r[1]) for r in labgen.addressing_rows(spec) if r[0] == name), "FastEthernet0")
        hosts[name] = {"port": port, "ip": s.get("ip", ""), "mask": s.get("mask", ""), "gw": s.get("gw", ""),
                       "dhcp": bool(s.get("dhcp")), "ip6": first6.get(name, []), "gw6": s.get("gw6", "")}
    settle = int(spec.get("activity", {}).get("answer_convergence_ms", 0)) or \
        (60_000 if labgen.needs_convergence(spec) else 20_000)
    if labgen.needs_convergence(spec):            # OSPF adjacencies, spanning tree on re-configured ports
        settle = max(settle, 90_000)
    dhcp_ms = 45_000 if any(h["dhcp"] for h in hosts.values()) else 0
    wireless = {}
    for d in spec["device"]:
        w = d.get("wireless")
        if w and not w.get("in_start"):
            secure = w.get("security", "open") != "open"
            wireless[d["name"]] = {"role": "server" if d["model"] in ("home-router", "wrt300n") else "client",
                                   "ssid": w["ssid"], "auth": 4 if secure else 0, "enc": 4 if secure else 0,
                                   "key": w.get("passphrase", "") if secure else ""}
    return {"links": links, "configs": configs, "hosts": hosts, "wireless": wireless, "boot_ms": 15_000, "settle_ms": max(settle, 20_000),
            "dhcp_ms": dhcp_ms,
            "tests_ms": 25_000, "result": str(result_path), "save": str(save_path) if save_path else ""}


def _cli(line):
    """[is a sub-command, text] for one running-config style line (interface names expanded)."""
    if line.startswith("interface "):
        line = "interface " + labgen.long_if(line.split(None, 1)[1])
    return [line.startswith(" "), line.strip()]


def undo_faults(spec):
    """What a student types to repair the hidden faults of a troubleshoot/mixed lab, per device: an `apply` fault is
    reversed line by line (X -> no X, no X -> X, section lines kept); a find/replace fault removes the faulty line
    and types the correct one, inside its section. Host faults are repaired by the host settings."""
    if spec["lab"].get("kind", "configure") not in ("troubleshoot", "mixed"):
        return {}
    answer = labgen.configs_for(spec, "answer")
    out = {}
    for f in spec.get("fault", []):
        dev = f["device"]
        if "apply" in f:
            raw = [l.rstrip() for l in f["apply"].strip("\n").splitlines() if l.strip()]
            for i, line in enumerate(raw):
                opens = not line.startswith(" ") and i + 1 < len(raw) and raw[i + 1].startswith(" ")
                if opens:
                    out.setdefault(dev, []).append(_cli(line))
                    continue
                indent = " " if line.startswith(" ") else ""
                body = line.strip()
                out.setdefault(dev, []).append(_cli(indent + (body[3:] if body.startswith("no ") else "no " + body)))
        elif "find" in f and dev in answer:
            lines = answer[dev]
            for i, line in enumerate(lines):
                if f["find"] in line:
                    faulty = line.replace(f["find"], f["replace"], 1)
                    parent = next((lines[j] for j in range(i, -1, -1) if not lines[j].startswith(" ")), None) \
                        if line.startswith(" ") else None
                    for text in (" no " + faulty.strip() if parent else "no " + faulty.strip(), line):
                        if parent:
                            out.setdefault(dev, []).append(_cli(parent))
                        out.setdefault(dev, []).append(_cli(text if text.startswith(" ") or not parent else " " + text.strip()))
                    break
    return out


def instrument(spec, built, out_pka, result_path, save_path=None, answer=False):
    """A copy of `built` whose File Script Module solves and grades the lab (see the module docstring).
    answer=True: the student's network is replaced by a copy of the answer network and nothing is typed, so Packet
    Tracer runs the lab's own solution live: it must reach full marks and pass every connectivity test. This proves
    the design (e.g. a layer-2 loop that stalls the simulation) and covers what the API cannot do, such as joining a
    wireless client to a WLAN (its profile calls fail in Packet Tracer 9)."""
    tree = ptlab.read_pkt(built)
    sm = tree.getroot().find("SCRIPT_MODULE")
    if sm is None:
        raise ValueError(f"{built} has no script module")
    p = plan(spec, result_path, save_path)
    if answer:
        root = tree.getroot()
        nets = root.findall("PACKETTRACER5")
        at = list(root).index(nets[0])
        root.remove(nets[0])
        root.insert(at, copy.deepcopy(nets[-1]))
        p.update({"links": [], "configs": {}, "hosts": {}, "wireless": {}, "dhcp_ms": 0, "mode": "answer"})
    script = SCRIPT.replace("__PLAN__", json.dumps(p))
    s = ET.SubElement(sm.find("SCRIPTS"), "SCRIPT")
    ET.SubElement(s, "ID").text = "LiveCheck.js"
    ET.SubElement(s, "CONTENT").text = base64.b64encode(script.encode()).decode()
    privileges = sm.find("PT_APP_META/SECURITY_SETTINGS")
    for p in PRIVILEGES:
        ET.SubElement(privileges, "PRIVILEGE").text = p
    ptlab.write_pkt(tree, out_pka)


def report(spec, result_path):
    """(ok, lines) from the script's JSON: full marks after solving, and not before."""
    res = json.load(open(result_path, encoding="utf-8"))
    lines, ok = [], res.get("stage") in ("tested", "done") and not res.get("errors")
    before, after, tests = res.get("before", {}), res.get("after", {}), res.get("tests", {})
    lines.append(f"start state:   {before.get('correct', '?')}/{before.get('total', '?')} items")
    lines.append(f"after solving: {after.get('correct', '?')}/{after.get('total', '?')} items, "
                 f"connectivity tests {tests.get('correct', '?')}/{tests.get('total', '?')}")
    if after and after.get("correct") != after.get("total"):
        ok = False
    if tests and tests.get("correct") != tests.get("total"):
        ok = False
        lines += [f"  test {i + 1}: {r}" for i, r in enumerate(tests.get("results", []))]
    if res.get("mode") != "answer" and before and before.get("total") and before.get("correct") == before.get("total"):
        ok = False
        lines.append("  the start state already scores full marks")
    for dev, cmd, status, output in res.get("rejected", []):
        lines.append(f"  {dev} rejected `{cmd}` (status {status}){': ' + output.strip() if output else ''}")
    lines += [f"  link not created: {l[0]}" for l in res.get("links", []) if not l[1]]
    lines += [f"  error: {e}" for e in res.get("errors", [])]
    lines += [f"  note: {n}" for n in res.get("notes", [])]
    if res.get("stage") not in ("tested", "done"):
        lines.append(f"  the script stopped at stage {res.get('stage')!r}")
    elif res.get("stage") == "tested":
        lines.append("  note: graded, but the solved network was not saved (the save did not finish)")
    return ok, lines
