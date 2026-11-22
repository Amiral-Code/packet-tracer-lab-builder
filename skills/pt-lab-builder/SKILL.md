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

Build with:

```bash
ptlab build SPEC.toml --output-dir OUTPUT
```

Use `--open` only after telling the user that Packet Tracer will appear. Validate the generated file in a compatible Packet Tracer version when GUI access is available, and never terminate a Packet Tracer process the validation did not start.

Deliver the `.pka` path, level/kind/time, covered topics, number of graded items, and answer-guide path. Tell the learner to open the answer guide only after a real attempt.
