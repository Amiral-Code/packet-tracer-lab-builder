# Lab specification

One TOML file describes one original Packet Tracer activity.

| Section | Purpose |
|---|---|
| `[lab]` | `id`, `title`, level 1-5, `kind` (`configure`, `troubleshoot`, or `mixed`), exam/track, minutes, scenario, objectives, label options |
| `[activity]` | Optional timer, answer-convergence delay, Activity Wizard password, profile lock, and overall feedback |
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

Activity controls are optional. A countdown defaults to `[lab].time` when `countdown_minutes` is omitted.
`answer_convergence_ms` lets the answer network settle before Packet Tracer evaluates protocols such as OSPF or
STP; it defaults to 60000 when the answer configuration runs OSPF, EIGRP, RIP, BGP, HSRP or EtherChannel.
The Activity Wizard password comes from `ptlab build --password` or `$PTLAB_PASSWORD`, not from the spec (specs are
meant to be shared; `wizard_password` still works but lint warns). Packet Tracer stores it as MD5 of a fixed salt plus
the password, so treat it as an edit deterrent: it keeps students out of the Activity Wizard, not out of the file.
The complete feedback defaults to the lab's `debrief`. Feedback accepts the same compact paragraph/`code`/`**bold**`
markup as instruction text.

```toml
[activity]
timer = "countdown"                 # "elapsed" (default), "countdown" or "none"
countdown_minutes = 75              # positive whole minutes
answer_convergence_ms = 30000       # non-negative milliseconds
profile_locked = true
locking_preset = ["cli-only", "fixed-topology"]   # one preset or a list
start_in = "HQ"                     # open the activity inside this [[site]]'s wiring closet
incomplete_feedback = "Review the failed items and verify the related `show` commands."
complete_feedback = "All assessed outcomes pass. **Save your file** before leaving the lab."
```

Locking presets only enable named switches already present in the local activity base:

- `cli-only` disables the Config tab on devices while leaving router/switch CLI and endpoint Desktop access.
- `realtime-only` disables switching to Simulation mode.
- `exam` combines both and also disables the command log and copy/paste.
- `logical-only` disables switching to the Physical workspace.
- `fixed-topology` stops the student adding, deleting or re-cabling devices. It is the default for labs without
  `student = true` links; it cannot be combined with them.

All presets leave Check Results and Reset Activity available. `start_in` switches on the locking tree's "Start in
Physical Location" for the site's wiring closet; labs with student cabling start in the first site's closet by
default.

Grading statements (one string each; quote multi-word fields of `in` with double quotes):

| Statement | Grades | Packet Tracer item |
|---|---|---|
| `ip DEV IFACE A.B.C.D/NN` | interface or host address and mask | IP Address + Subnet Mask |
| `ip DEV IFACE in NET/LEN` | **any** usable host address of NET, and its mask | IP Address (`{{RegEx:…}}`) + Subnet Mask |
| `ip6 DEV IFACE ADDR/LEN` | an IPv6 address on a router, switch or host | Ipv6 Address > ADDR > IP Address + Prefix |
| `up DEV IFACE` | interface is up (no `shutdown`) | Port Up |
| `gw HOST A.B.C.D` | host default gateway | Default Gateway |
| `gw HOST A.B.C.D\|E.F.G.H` | host default gateway, any of these (e.g. real or HSRP virtual) | Default Gateway (`{{RegEx:…}}`) |
| `gw6 HOST ADDR` | host IPv6 default gateway (link-local allowed) | Default Gateway IPv6 |
| `dhcp HOST` | host uses DHCP | local check only |
| `hostname DEV NAME` | device hostname | Host Name |
| `line DEV TEXT` | an **unindented** running-config line, e.g. `ip route`, `ip nat inside source …`, `access-list …` | config line |
| `in DEV "PARENT" "LINE"` | an indented line inside a section, e.g. `in R1 "interface GigabitEthernet0/1" "ip helper-address 10.0.0.9"` | config line |
| `vlan SW ID NAME` | VLAN exists with that name | VLANS > ID > VLAN Name |
| `access SW IFACE VLAN` | access port in that VLAN | Access VLAN + ` switchport mode access` |
| `trunk SW IFACE [allowed LIST] [native N]` | trunk, its allowed list (written in IOS form, `10-12,99`) and native VLAN | ` switchport mode trunk`, allowed line, Native VLAN |
| `route DEV PREFIX/LEN NEXT-HOP` | static route (`0.0.0.0/0` for a default) | `ip route …` line |
| `ospf DEV PID PREFIX/LEN AREA` | OSPF network statement (wildcard computed) | ` network … area …` under `router ospf PID` |
| `stp SW VLAN PRIORITY` | per-VLAN bridge priority (multiple of 4096) | `spanning-tree vlan … priority …` line |
| `route6 DEV PREFIX/LEN NEXT-HOP` | IPv6 static route (`::/0` for a default) | `ipv6 route …` line |
| `rid DEV PID A.B.C.D` | OSPF router ID | ` router-id …` under `router ospf PID` |
| `passive DEV PID IFACE` | OSPF passive interface | ` passive-interface …` under `router ospf PID` |
| `portfast SW IFACE` | PortFast on an access port | PortFast |
| `portsec SW IFACE [max N] [sticky] [violation protect\|restrict\|shutdown]` | port security and its options | Port Security > Enabled, Max Secure Mac, Sticky Enabled, Violation |
| `desc DEV IFACE TEXT` | interface description: exact `TEXT`, `~word` (contains, any case) or `any` (not blank) | Description |
| `banner DEV TEXT` | MOTD banner: contains `TEXT`, `~word`, or `any` | Banner motd (`{{RegEx:…}}`) |
| `nat DEV IFACE inside\|outside` | NAT side of an interface | NAT |
| `acl DEV IFACE NAME in\|out` | ACL applied to an interface | Access-group In / Out |
| `hsrp DEV IFACE GROUP VIP [priority N] [preempt]` | HSRP group | ` standby …` lines |
| `pool DEV NAME NET/LEN [gw A.B.C.D] [dns A.B.C.D]` | IOS DHCP pool | DHCP Server > Pools > NAME > Name, Start IP address, Subnet mask, Default Gateway, DNS Server |
| `secret DEV PASSWORD` | `enable secret` (not `enable password`) | Enable Secret (type-5 hash) |
| `user DEV NAME PASSWORD` | `username NAME secret PASSWORD` | User Names > NAME |
| `ping SRC DST [A.B.C.D] [fail]` | end-to-end reachability; `fail` = must **not** succeed (ACL labs) | Connectivity Tests tab |
| `ping6 SRC DST [ADDR] [fail]` | IPv6 reachability (ICMPv6 echo) | Connectivity Tests tab |
| `tcp SRC DST PORT [A.B.C.D] [fail]` | TCP outcome on any port | Connectivity Tests tab, complex PDU |
| `http SRC DST [A.B.C.D] [fail]` | TCP/80 outcome | Connectivity Tests tab, complex PDU |
| `https SRC DST [A.B.C.D] [fail]` | TCP/443 outcome | Connectivity Tests tab, complex PDU |
| `ssh SRC DST [A.B.C.D] [fail]` | TCP/22 outcome | Connectivity Tests tab, complex PDU |
| `telnet SRC DST [A.B.C.D] [fail]` | TCP/23 outcome | Connectivity Tests tab, complex PDU |

```toml
[grade]
items = [
  "ip R1 G0/0 10.0.0.1/30",
  "up R1 G0/0",
  "access SW1 Fa0/5 10",
  "trunk SW1 G0/1 allowed 10,20,99 native 99",
  "route R1 0.0.0.0/0 10.0.0.2",
  'in R1 "router ospf 1" "router-id 1.1.1.1"',
  "ping PC1 SRV1",
  "ping GUEST1 SRV1 fail",
  "https PC1 SRV1",
  "telnet GUEST1 SRV1 fail",
]

[grade.points]
"https PC1 SRV1" = 3
"telnet GUEST1 SRV1 fail" = 2
```

`points` is optional and maps an exact statement to a positive integer. It weights each native Check Results leaf
generated by that statement; for example, `ip` produces independently scored address and mask leaves. A connectivity
statement has one PDU outcome and receives the stated weight. Unlisted statements remain worth one point. This gives
straightforward partial credit without custom scripting.

IPv6 works everywhere: addresses in config lines are written the way Packet Tracer prints them (compressed,
upper case) and the item ID stores `:` as `-`, as Packet Tracer does. Hosts get IPv6 from a second addressing-table
row for the same port (`["PC2", "Fa0", "2001:db8:10::20/64", "fe80::1"]`); `ping6` uses those addresses. Switches
whose answer configuration uses IPv6 are given the dual-IPv4-and-IPv6 SDM template automatically. On multilayer
switches an IP address on a physical port needs `no switchport` (lint checks).

Several right answers: `ip … in NET`, `gw A|B`, `desc … ~word|any` and `banner` are graded by a regular expression
(Packet Tracer's `{{RegEx:…}}` items) instead of one value, so a student who picks another valid address, the other
gateway or their own wording still passes. Prefer them whenever the task leaves a choice.

Lint warns when a lab grades only configuration (add ping/tcp tests so a working network is proven) or only
outcomes (add configuration items so partial work earns partial credit).

How Packet Tracer grades config lines (from its `Ext.AssessmentModel.DeviceConfig` plugin and the Activity
Wizard's `LINES` nodes): a line is matched **whole and exactly** against the student's running-config. An
indented sub-command is identified by its parent line plus the line, so it only matches under that parent. That is why
`line` must be an unindented line; for anything inside `interface`, `router`, `line vty`, `ip dhcp pool` or a named
ACL, use `in` (or `access`/`trunk`/`ospf`). `ptlab lint` enforces it: the self-check fails a `line` item that
only exists indented in the answer. Write lines exactly as `show running-config` prints them (full interface names,
IOS keyword order).

Connectivity tests are stored as saved PDUs in the answer network's first scenario and run by Packet Tracer
from the same-named device in the student's network. Only Packet Tracer can run them: `ptlab lint` does not
simulate the traffic, and `ptlab check` reports only the config items. DST's address defaults to its first address
in the addressing table; TCP tests also require a source address there. Use outcome tests (inter-VLAN routing,
NAT, ACL policy, allowed and blocked services) on top of config items, not instead of them, so `ptlab lint` can
still prove each fault is caught. ICMP and TCP encodings are based on saved Packet Tracer activities; UDP/DNS is
not exposed until an observed compatible encoding is available.

Every Check Results item receives a short diagnostic hint by default. Override one without revealing its answer
by mapping the exact grade statement under `[grade.hints]`:

```toml
[grade.hints]
"trunk SW1 G0/1 allowed 10,20,99" = "Compare the allowed VLAN list on both ends of the uplink."
```

Serialization invariants established by local testing:

- `.pka` networks are main/student, initial/reset, then answer.
- Assessment elements must be indented, one per line, with explicit closing tags.
- Graded leaves use check type 2 and their ancestors use check type 1.
- Interface state is `Port Up`; `Power` is not link state.
- Installed desktop-app folders from source templates must be removed.
- Generated templates and activity settings must match the learner's Packet Tracer generation.
