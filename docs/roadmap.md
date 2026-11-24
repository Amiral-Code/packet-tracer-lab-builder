# Roadmap

Goal: an instructor (or the skill) describes a lab in plain words and gets a Packet Tracer activity that is
correct, graded fairly, hard to copy, pleasant to work in, and proven before anyone opens it.

## The quality gate (every iteration ends here)

An iteration is done only when all of these hold:

1. CI is green on Linux, macOS and Windows (Python 3.11 and 3.13).
2. Every example passes `ptlab lint` with no errors, builds, and survives the round trip: opened and saved by Packet
   Tracer 9.0.1, then `ptlab verify SPEC SAVED.pka` reports every item and test kept and every local check passing.
3. Every new Packet Tracer behaviour has been **seen working live**: an item turning green after a fix, a lock
   blocking what it should, a timer counting down. Grading behaviour is checked without a person by the live check
   (`ptlab live-prepare` / `live-report`, harness `pt-live-check.sh`): Packet Tracer itself solves the lab and
   grades it, from 0 to full marks; GUI behaviour (locks, timers, views) still needs a person. Until then it is listed as "pending live check" in
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

Built and proven by round trip (every item kept, every value equal to Packet Tracer's own):

- ~~**Several right answers**~~ `{{RegEx:…}}` items (the real format; not `RegExMatch`): `ip DEV IFACE in NET/LEN`,
  `gw HOST A|B`, `desc DEV IFACE ~word|any|TEXT`, `banner DEV ~word|any|TEXT`.
- ~~**IPv6**~~ `ip6` (routers, switches, hosts), `gw6`, `route6`, IPv6 config lines (`:` stored as `-` in item IDs),
  `ping6` (type-20 PDU), host IPv6 from a second addressing row. Northstar grades its IPv6 again.
- ~~**More item types**~~ each from a real file and checked against Packet Tracer's own value: description, banner,
  port security (enabled, maximum, sticky, violation), PortFast, NAT inside/outside, ACL per interface, HSRP,
  DHCP pools, OSPF router ID and passive interfaces, enable secret, local users.
- ~~`ptlab verify --values`~~ with `ptlab bare`: proves every item's value against Packet Tracer itself.
- ~~Lint~~ warns when a lab grades only configuration or only outcomes; accepts link-local and HSRP gateways.
- Fixed on the way: start overlays after a global `no …` line landed in the wrong section (Northstar's CORE1 start
  network), `no ip address` did not remove the address, `in` parents with short interface names never matched.

Live-confirmed 2026-11-23 (`feature-probe-2.pka`, Check Results **40/40**, Connectivity Tests **2/2**):

| Check | Result |
|---|---|
| Several right answers | PC1 at 192.168.10.150 with gateway 192.168.10.1 (answer: .10 and .254): IP Address, Subnet Mask, Default Gateway green |
| Description / banner wording | "Users LAN segment" and "Only authorized staff may connect" (not the answer text): green |
| IPv6 items and ping6 | all IPv6 items green, ping6 PC2 to SRV1 passes |
| Port security, NAT, HSRP, DHCP pool, secrets | every item green, including the generated enable-secret hash and the local user |

- ~~**UDP tests**~~ `udp SRC DST PORT [fail]`, copied from a Complex PDU the user saved (type 2, `CUdpHeader`).
  Live probe (`udp-probe.pka`): UDP to a port with no service passes, UDP to an unreachable host fails as expected,
  but UDP to a listening service fails (DNS on: UDP/53 pass -> fail; TFTP/69 always fails). So there is no `dns`
  test: lint refuses UDP to service ports. ACL filtering confirmed live (`udp-acl-probe.pka`: `fail` test red
  without the ACL, 3/3 with it). Grading a DNS server needs its records as assessment items, which waits
  for a real file that grades them.

## Iteration 3: devices and modules

- Add models from the user's own sources with a type class each (IOS, ASA, host, appliance, passive):
  ISR4321/1841 (done), ASA 5505/5506-X, 2950/2950T, Switch-PT, WLC-PT, sniffer, home router, DSL/cable modems,
  cell tower, Meraki. `configs_for` must only write IOS configuration to IOS devices.
- ~~**Serial WAN**~~ `-serial` models (1941/2911 + HWIC-2T, 1841 + WIC-2T, ISR4321/ISR4331 + NIM-2T) taken
  whole from the user's files, serial links with a named DCE end, `clock` statement, serial lint;
  `examples/serial-wan-triangle.toml` proven by round trip and live-confirmed (Check Results 35/35, 3/3).
- ~~**Home and provider devices**~~ home router, Linksys (port names fixed), cable/DSL modems, splitter, stock
  Cloud with `connect` cable/DSL mapping, central office, cell tower; coax and phone links; IOS configuration only
  on IOS devices; `examples/home-cable-internet.toml` proven by round trip and live-confirmed (all items green, ping passes).
- ~~**Live checks without a person**~~ `ptlab live-prepare` / `live-report` and the `pt-live-check.sh` harness:
  Packet Tracer solves each lab (console typing, cables, hosts, fault repair) and grades it. All nine examples
  pass unattended; it found and fixed a broken EtherChannel design in Northstar that every file-level check passed.
- ~~**Fiber optics and access points**~~ `router-2911-sfp`, `l3switch-3650-fiber` (GLC-LH-SMD), single-mode fiber
  links in Packet Tracer 9's format, `ap-n`, `ap-ac`, `lap-3702i`, access-point port names fixed (`Port 0`);
  `examples/fiber-campus-uplink.toml` proven by round trip and live check. The ISR4331 with NIM-ES2-4 exists only
  in two labs outside the library sources (T-Labs) and is left out.
- ~~**Cards in empty slots**~~ `modules = [...]`: the library keeps a clean copy of every card in the user's files and
  where it was seen; the builder fits it, names its ports by bay and starts them shut down.
  `examples/serial-card-upgrade.toml` proven by round trip (8/8 values) and live check (0 -> 8/8, 1/1).
- ~~**ASA labs**~~ `asa-5506x`/`asa-5505`, ASA CLI configs, native items (`nameif`, `seclevel`, `object`, `acl`,
  `ip`, `up`), automatic answer convergence, `inspect http` lint; `examples/asa-edge-firewall.toml` proven by round
  trip; the same lab live-confirmed as a probe (14/14, 2/2).
- ~~**Wireless (home router / Linksys WLANs, wireless hosts)**~~ `wireless = {...}`, `wlan` statement on Packet
  Tracer's own nodes; `examples/home-wlan-security.toml` proven by round trip (8/8 values) and the answer-network
  live check (8/8, ping 1/1). Still open: WLC-based WLANs (the user's files grade them: WLANs, RADIUS, dynamic
  interfaces) and range in the Physical view.
- ~~**Live check of the answer network**~~ `live-prepare --answer` runs the lab's own solution live: it proves the
  design under Packet Tracer's simulation and covers what the API cannot do.

## Iteration 4: every student gets a different lab

- ~~**`ptlab variants SPEC --count N`**~~ consistent re-addressing of the private IPv4 space per student (10.A,
  172.16-31.B, 192.168.C; wider prefixes and ACL wildcards follow), each variant passing the spec check and
  self-check before it is written, reproducible from a seed, `--build` for the files and answer keys.
- Variable Manager pools (seed, number, string, IP) inside one file: addressing and names change per student
  (open: the variants above give the same result with one file per student, which every Packet Tracer reads).
- Object location sets so even the logical layout differs.
- `ptlab variants SPEC -n 30`: thirty distinct, individually proven files plus one answer key per file.

## Iteration 5: instructor workflow

- ~~**`ptlab grade SPEC DIR`**~~ batch grading of saved student files into grades.csv and grades.html (per student,
  per check); with a folder of variant specs each file is graded against the variant it matches.
- ~~**Topic recipes**~~ `ptlab recipes` / `ptlab new RECIPE OUT`: the twelve proven examples (cabling, SOHO cable and
  WLAN, static, ACL/VLAN/OSPF, serial OSPF, cards, fiber, ASA, dual stack and hardening, troubleshooting, capstone)
  shipped in the wheel; a new lab is a fresh re-addressed copy. Open: router-on-a-stick, EtherChannel-only, STP
  tuning and SSH-only recipes as separate small labs (they exist inside the capstone today).
- ~~**Fault library**~~ `ptlab troubleshoot SPEC OUT --faults N`: faults drawn from the lab's own answer configuration
  (shut interface, wrong next hop, wrong OSPF area, mistyped address, wrong access VLAN, ACL direction, missing NAT
  inside, wrong host gateway), each with symptom and explanation, kept only when a graded item catches it.
- Skill: ask only level/track/kind/topic/time, pick recipes, build, lint, and report the live checks still pending.

## Iteration 6: partial credit and better feedback

- ~~**Per-part scores**~~ a `[[part]]` may carry `grade = [...]`: its items are filed under the part's title, which
  joins `COMPONENT_LIST`, so Check Results scores each part ("Hardening 9/14"), as NetAcad activities name their
  components after tasks ("Device Hardening Configuration", "VLAN Config"). `feature-probe-2` uses it.
- The scripted scoring model (work products, observables, reporting variables) and messages such as "two of three
  sites route correctly" (open: needs the activity's Main.js/ScoringModels.js scripts, seen in 83 user files).

## Iteration 7: physical realism

- ~~Structured cabling: patch panels and wall mounts, horizontal cabling, patching labs.~~ Done 2026-11-24
  (`structured-cabling`, proven live).
- Several closets per building, generic containers, background images.
- Cable colours and bend points for tidy generated racks.

## Iteration 8: beyond Packet Tracer

- ~~**`ptlab gns3 SPEC OUT`**~~ compiles a spec into a lab for the author's CCNA GNS3 engine (IOU routers/switches,
  VPCS): ports renamed in link order, base and solution configs, grade statements as show-command checks (the
  rest listed in the file). The exported static-two-sites passes the engine's selftest (8/8 failing before, 8/8
  passing after the solution). Open: serial links, and topics only GNS3/CML can run (MPLS, VRF, IS-IS, BGP policy).

## Iteration 9: release

- ~~**v0.2.0**~~ released 2026-11-24 with changelog, example gallery (`docs/examples.md`), instructor and contributor
  guides, and a full regression: every example built, round-tripped through Packet Tracer and live-checked in
  both modes (22 runs).

## Still open (needs a sample file or a person)

- ~~Cable bend points~~ done 2026-11-24 from a sample saved by the author (`bends`, `color` on a link).
- ~~WLC-based WLANs~~ and ~~WPA2-Enterprise with RADIUS~~ done 2026-11-24 (`wlc-clinic-wlan`,
  `wlc-clinic-enterprise`, proven live in both modes).
- Variable Manager pools inside one file: checked in NetAcad files, they serve "any address in a subnet", which
  RegEx items already do; not planned.
- The scripted scoring model (Main.js / ScoringModels.js) for messages beyond per-part scores.
- ~~GNS3 export of serial links~~ done 2026-11-24 (IOU serial adapters s2/x-s3/x); topics only GNS3/CML can run.
- GUI behaviours that no script can observe: locks, timers, views (a person checks these).
