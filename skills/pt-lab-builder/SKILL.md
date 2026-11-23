---
name: pt-lab-builder
description: Design, build, and validate original Cisco Packet Tracer activities from TOML specs, including configure, troubleshooting, multi-topic capstone, and basic Physical-mode labs. Use for requests to create Packet Tracer, CCNA, ENCOR, or CCIE-style practice labs. Route unsupported Packet Tracer technologies to a more capable emulator.
license: Apache-2.0
---

# Packet Tracer lab builder

Use the installed `ptlab` CLI. Do not assume a repository location or a home-directory layout.

Before authoring, run `ptlab doctor`. If required local templates or the codec are missing, explain the exact `ptlab init --build-codec --source PATH` command; never invent or redistribute device templates.

Clarify only information that materially changes the lab: level 1-5, track, configure/troubleshoot/mixed intent, topic or exam objective, and approximate time. Infer sensible defaults when the request already provides enough context.

Packet Tracer covers CCNA and part of ENCOR. Use another platform for MPLS, VRFs, IS-IS, advanced BGP policy, multicast routing, DMVPN, SD-WAN, device NETCONF/RESTCONF, or real QoS behaviour. Call advanced Packet Tracer labs “CCIE-style,” not full CCIE labs.

Write original scenarios, instructions, topologies, and faults. Do not copy NetAcad, Cisco, or third-party course activity content.

For the TOML structure, grading statements, device/link rules, and known serialization invariants, read [references/spec-schema.md](references/spec-schema.md). When the request includes a Physical workspace or physical cabling, also read [references/physical-mode.md](references/physical-mode.md).

Grade with the most specific statement (`access`, `trunk`, `vlan`, `route`, `ospf`, `stp`, `ip`, `up`, `gw`, and
`ip6`, `gw6`, `route6`, `rid`, `passive`, `portfast`, `portsec`, `desc`, `banner`, `nat`, `acl`, `hsrp`, `pool`,
`secret`, `user`, `clock`) and use `line` only for unindented running-config lines; anything inside a section needs
`in DEV "PARENT" "LINE"`. When the task leaves the student a choice, grade the choice, not one answer:
`ip DEV IFACE in NET/LEN` (any host address), `gw HOST A|B` (either gateway), `desc DEV IFACE ~word` or `any`,
`banner DEV ~word`. IPv6 is fully supported, including hosts (a second addressing row) and `ping6`.
Add connectivity tests for the outcomes the lab is about, on top of the config items: `ping`/`ping6` for reachability
and `http`/`https`/`ssh`/`telnet` or `tcp ... PORT` for service policy. Use `fail` for traffic that must be blocked.
`udp ... PORT` proves UDP delivery or filtering only, to a port with no service: a UDP test fails when a service
(DNS, TFTP, ...) receives it, so never use it to grade a service.
Serial WAN labs use the `-serial` models (`ptlab models`); the first end of a serial link is the DCE, and
`clock DEV SERIAL RATE` grades its clock rate.
Do not invent UDP/DNS saved-PDU encodings; they are not supported yet.
When the request calls for weighted or partial credit, map exact statements under `[grade.points]`; keep ordinary
items at one point and give larger weights only to outcomes that genuinely deserve more influence.

For timed or assessment-oriented requests, use `[activity]` for elapsed/countdown timing, answer convergence,
Activity Wizard password, profile locking, and lab-specific completion feedback. Read the activity-control and
connectivity sections of [references/spec-schema.md](references/spec-schema.md) before using them.

Check, then build:

```bash
ptlab lint SPEC.toml                       # spec check + self-check, no file written
ptlab build SPEC.toml --output-dir OUTPUT  # runs the same checks first and refuses on errors
```

`ptlab lint` proves the lab before anyone opens it: ports exist and are cabled once, addresses are valid and
unique, host gateways sit in their subnet, every grade statement is valid, the **answer network scores 100 %**
against the lab's own grade statements, and **every fault, applied alone, makes at least one graded item fail**.
Fix every error; never use `--force` to ship a lab. Treat warnings as review items (for example, graded items
that already pass at the start of a configure lab give free points).

After building, when Packet Tracer is available, prove the file the way Packet Tracer reads it: open the built
`.pka` in Packet Tracer, save it (Ctrl+S) as a copy, and run `ptlab verify SPEC SAVED.pka`. Packet Tracer silently
drops assessment items it cannot find in its own answer network (already when it loads the file), so `verify`
reports dropped items and connectivity tests, and runs the local checks on Packet Tracer's rewritten answer network.
To also prove every item's value, make a copy without assessment items (`ptlab bare BUILT.pka BARE.pka`), open and
save it the same way, and add `--values BARE.pka`: Packet Tracer fills that copy's tree from its own answer network.
Fix every error before delivering the lab.

Use `--open` only after telling the user that Packet Tracer will appear. Validate the generated file in a compatible Packet Tracer version when GUI access is available, and never terminate a Packet Tracer process the validation did not start.

Deliver the `.pka` path, level/kind/time, covered topics, number of graded items, and answer-guide path. Tell the learner to open the answer guide only after a real attempt.
