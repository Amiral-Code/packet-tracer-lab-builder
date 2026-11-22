# Lab specification

One TOML file describes one original Packet Tracer activity.

| Section | Purpose |
|---|---|
| `[lab]` | `id`, `title`, level 1-5, `kind` (`configure`, `troubleshoot`, or `mixed`), exam/track, minutes, scenario, objectives, label options |
| `[physical]` | Optional inherited city/building/closet/rack names |
| `[[device]]` | Unique `name`, library `model`, optional logical `x`/`y`, optional physical placement |
| `[[link]]` | `a = "R1 G0/0"`, `b = "SW1 G0/1"`; optional cable override |
| `[[area]]` | Logical canvas label, colour, devices, and optional padding |
| `[[note]]` | Logical canvas text with coordinates |
| `[addressing]` | Rows of device, interface, CIDR/DHCP, gateway |
| `[config.start]` | Configuration present in a configure lab before the learner begins |
| `[config.answer]` | Reference configuration snippets merged onto factory configurations |
| `[[fault]]` | Troubleshooting changes plus learner-visible symptom and answer explanation |
| `[[part]]` | One instruction page: title, introduction, steps, hint, and why it matters |
| `[grade]` | Packet Tracer Check Results and saved-file checks |
| `debrief`, `questions` | Reflection page |

Use model keys reported by `ptlab models`. Ports must exist on the chosen model; an invalid port can make Packet Tracer reject the entire activity. Short interface names such as `G0/0`, `Fa0/1`, and `S0/0/0` are accepted.

Omit logical coordinates to use automatic site-by-site layout. Areas support cyan, yellow, green, pink, orange, purple, blue, grey, and red.

Configuration snippets use running-config form. Indentation means a command belongs to the preceding section:

```toml
[config.answer]
R1 = """
interface G0/0
 ip address 10.0.0.1 255.255.255.252
 no shutdown
router ospf 10
 network 10.0.0.0 0.0.0.3 area 0
"""
```

Troubleshooting labs start from the answer plus every declared fault. Prefer CLI-shaped `apply`; host faults use `pc`:

```toml
[[fault]]
device = "R1"
apply = """
interface G0/0
 shutdown
"""
symptom = "The WAN is down."
explain = "G0/0 was administratively shut; use `no shutdown`."
```

Mixed labs also start from the answer. They then apply `[config.start]` as an overlay for intentionally unfinished
configuration, followed by every declared fault. Use `unconfigured_hosts` for endpoints the learner must address:

```toml
[config]
unconfigured_hosts = ["PC1"]

[config.start]
R1 = """
interface G0/0
 no ip address
 shutdown
"""
```

Supported grading statements:

```toml
[grade]
items = [
  "ip R1 G0/0 10.0.0.1/30",
  "up R1 G0/0",
  "gw PC1 192.168.10.1",
  "hostname R1 HQ-R1",
  "line R1 ip route 0.0.0.0 0.0.0.0 10.0.0.2",
  "dhcp PC1",
]
```

Grade what the learner must change. The current DSL can check configuration facts but is not yet a full operational-state verifier; treat end-to-end behaviour, neighbor state, and physical placement grading as future extensions unless you add explicit support.

Serialization invariants established by local testing:

- `.pka` networks are main/student, initial/reset, then answer.
- Assessment elements must be indented, one per line, with explicit closing tags.
- Graded leaves use check type 2 and their ancestors use check type 1.
- Interface state is `Port Up`; `Power` is not link state.
- Installed desktop-app folders from source templates must be removed.
- Generated templates and activity settings must match the learner's Packet Tracer generation.
