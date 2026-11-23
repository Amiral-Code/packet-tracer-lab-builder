# Roadmap

Goal: an instructor (or the skill) describes a lab in plain words and gets a Packet Tracer activity that is
correct, graded fairly, hard to copy, pleasant to work in, and proven before anyone opens it.

## The quality gate (every iteration ends here)

An iteration is done only when all of these hold:

1. CI is green on Linux, macOS and Windows (Python 3.11 and 3.13).
2. Every example passes `ptlab lint` with no errors, builds, and survives the round trip: opened and saved by Packet
   Tracer 9.0.1, then `ptlab verify SPEC SAVED.pka` reports every item and test kept and every local check passing.
3. Every new Packet Tracer behaviour has been **seen working live**: an item turning green after a fix, a lock
   blocking what it should, a timer counting down. Until then it is listed as "pending live check" in
   `docs/packet-tracer-capabilities.md`, never as done.
4. Every new file-format fact is recorded in `docs/research-evidence.md` with its source (real file, binary
   trace, or live test), and inferences are labelled as inferences.
5. Spec reference, skill and README describe exactly what the code does.

## Done so far (0.2)

- Native `.pka` generation: three networks, instructions, assessment tree, connectivity tests (ping, TCP).
- `ptlab lint`: spec check plus self-check (the answer network scores 100 %, every fault is caught).
- Grading: addresses, interface state, gateways, hostnames, VLANs, access/trunk ports, static and OSPF routes,
  STP priority, any running-config line, cables; per-item hints, points, debrief feedback.
- Physical: sites in cities, measured rack stacking, floor grid, student cabling labs.
- Activity controls: timer, answer convergence, salted Wizard password, lock presets, start inside a closet.
- Live-confirmed: IP items, Port Up after cabling, ping tests (Check Results 9/9 + 3/3).

## Iteration 1: confirm and harden 0.2

The live checklist (one sitting, about 30 minutes, in `~/Study/labs/ccna/pt/work/`):

| Check | File | Pass when |
|---|---|---|
| ~~Wizard password~~ confirmed | `branch-cabling.pka` (password `tiznit`) | Extensions → Activity Wizard asks for it, `tiznit` opens it, a wrong one doesn't |
| ~~Start in closet~~ confirmed (2nd try) | `branch-cabling.pka` | the activity opens in the Physical view, inside Branch Wiring Closet |
| ~~Hints~~ confirmed | any lab, before doing anything | Check Results → each red item shows its hint |
| ~~Debrief~~ confirmed | any lab | the last instruction page is the debrief; it is also the complete feedback |
| ~~Fixed topology~~ confirmed (2nd try) | `static-two-sites.pka` | deleting a device or a cable is refused |
| ~~Countdown~~ confirmed | Northstar (90 min) | the activity window shows Time Left counting down |
| ~~Config lines~~ confirmed (route item: trailing-space fix, re-check) | `feature-probe.pka` | `route` and `stp` items turn green when configured |
| ~~Sub-command lines~~ confirmed | `feature-probe.pka` | `access`, `ospf` and the ACL `in` items turn green |
| ~~TCP tests~~ confirmed | `feature-probe.pka` | `http` passes and `https ... fail` passes only once the ACL is applied |
| Convergence | Northstar | items comparing OSPF-dependent state are not falsely red right after opening |

Then fix whatever fails, and add:

- ~~An `examples/feature-probe.toml` lab~~ done: one 30-minute lab covering every remaining check.
- ~~Round-trip verification~~ done: `ptlab verify` plus a local hidden open-and-save script; all five examples pass
  (it found and fixed: dropped `no switchport`, IPv6 rejected without the dual-stack SDM template, `ip route`'s
  trailing space, colons in line items, leftover template port descriptions).

## Iteration 2: fairer grading

- **Several right answers:** `{{RegExMatch:…}}` items, e.g. `ip PC1 Fa0 any-in 192.168.10.0/24` and gateway
  checks that accept any valid router address.
- **IPv6:** `ip6 DEV IFACE ADDR/LEN`, `route6`, `ping6` (type-20 PDUs are in the corpus).
- **More item types**, each only after a real file shows its value format: interface description, port security
  (maximum, violation, sticky), DHCP pools, HSRP group/priority/preempt, OSPF passive interfaces and router ID,
  ACL application per interface, NAT inside/outside.
- **UDP/DNS tests** once a saved UDP PDU is found (build one in Packet Tracer and save it).
- Lint: warn when a lab grades only configuration and no outcome, or only outcomes and no configuration.

## Iteration 3: devices and modules

- Add models from the user's own sources with a type class each (IOS, ASA, host, appliance, passive):
  ISR4321/1841 (done), ASA 5505/5506-X, 2950/2950T, Switch-PT, WLC-PT, sniffer, home router, DSL/cable modems,
  cell tower, Meraki. `configs_for` must only write IOS configuration to IOS devices.
- Module insertion: HWIC-2T/WIC-2T/NIM-2T serial, NIM-ES2-4, SFP optics, written the way Packet Tracer stores
  a module in its slot; then serial WAN labs with DCE clock rate checks.
- ASA labs: interfaces, security levels, ACLs, NAT objects (assessment classes exist).
- Wireless labs: WLC-based WLANs and range in the Physical view.

## Iteration 4: every student gets a different lab

- Variable Manager pools (seed, number, string, IP) generated from the spec: addressing and names change per
  student; items accept the student's own values ("Entire Range").
- Object location sets so even the logical layout differs.
- `ptlab variants SPEC -n 30`: thirty distinct, individually proven files plus one answer key per file.

## Iteration 5: instructor workflow

- `ptlab grade DIR` batch grading of saved student files into a CSV and an HTML report (per item, per student).
- Topic recipes the skill composes: VLAN + router-on-a-stick, inter-VLAN on L3 switch, OSPF single/multi-area,
  EtherChannel, STP tuning, HSRP, DHCP + relay, ACL policy, NAT/PAT, IPv6 dual-stack, port security, SSH hardening,
  wireless. Each recipe brings its config, faults, grade statements and connectivity tests.
- A troubleshooting fault library: realistic faults per recipe, each with symptom, evidence and explanation.
- Skill: ask only level/track/kind/topic/time, pick recipes, build, lint, and report the live checks still pending.

## Iteration 6: partial credit and better feedback

- The scoring model (work products, observables, reporting variables) for capstones: per-part scores and messages
  such as "two of three sites route correctly".
- Per-part progress shown in the activity window.

## Iteration 7: physical realism

- Structured cabling: patch panels and wall mounts, horizontal cabling, patching labs.
- Several closets per building, generic containers, background images.
- Cable colours and bend points for tidy generated racks.

## Iteration 8: beyond Packet Tracer

- The same spec format compiled to GNS3/CML for what Packet Tracer cannot do (MPLS, VRF, IS-IS, BGP policy,
  multicast, DMVPN), reusing the CCNA GNS3 engine; the skill routes these automatically.

## Iteration 9: release

- Versioned release with changelog, example gallery with screenshots, documentation for instructors and for
  contributors, skill evaluations, and a full regression run (every example built, opened and live-checked).
