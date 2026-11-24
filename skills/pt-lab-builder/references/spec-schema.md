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

Serial WAN: use a `-serial` model, a router taken whole from the user's own files with its serial card fitted
(`router-1941-serial` and `router-2911-serial` with HWIC-2T: `S0/0/0`, `S0/0/1`; `router-1841-serial` with
WIC-2T: `S0/0/0`, `S0/0/1`; `router-isr4321-serial` with NIM-2T: `S0/1/0`, `S0/1/1`; `router-isr4331-serial`
with NIM-2T: `S0/2/0`, `S0/2/1`). A serial port can only be cabled to another serial port. The link's **first**
end (`a`) is the DCE that supplies the clock; `cable = "eSerialDTE"` makes `b` the DCE instead. Packet Tracer
stores the link with no cable type and names the DCE end (`DCEDEV`/`DCEPORT`). Other cable values:
`eStraightThrough`, `eCrossOver`, `eFiber`, `eCoaxial`, `ePhoneLine` (chosen automatically when omitted).

Home and provider devices: `home-router` (HomeRouter-PT-AC: `Internet`, `GigabitEthernet 1`-`4`), `wrt300n`
(Linksys: `Internet`, `Ethernet 1`-`4`), `cable-modem` and `dsl-modem` (`Port 0` coax or phone line, `Port 1`
Ethernet), `coax-splitter` (`Coaxial0`-`2`), `cloud` (stock Cloud-PT: `Serial0`-`3`, `Modem4`, `Modem5`,
`Ethernet6`, `Coaxial7`), `central-office` and `cell-tower`. They take no `[config]` (no IOS): home routers start
in Packet Tracer's stock state (Internet by DHCP, LAN 192.168.0.1 with DHCP from .100, SSID Default). A cloud
maps its provider ports with `connect = [["Coaxial7", "Ethernet6"]]` (cable) or `[["Modem4", "Ethernet6"]]`
(DSL). Coax and phone links are chosen automatically. Port names containing a space are written as Packet
Tracer shows them, quoted in grade statements: `cable MODEM "Port 0" ISP-CLOUD Coaxial7`.

Wireless: `wireless = { ssid = "AtlasHome", security = "wpa2-psk", passphrase = "..." }` on a `home-router` or
`wrt300n` configures its 2.4 GHz WLAN; on a `laptop` (or another wireless host) the network it joins, with the
host's addressing from the table (`["LAPTOP", "Wireless0", "dhcp", ""]`). Written to the answer network; add
`in_start = true` to also start that way. Grade with `wlan DEV SSID [wpa2 PASSPHRASE]` (Packet Tracer's `Wireless
2.4G` / `Wireless` nodes: SSID, Authen Type 4 = WPA2-PSK, Encryption Type 4 = AES, Pass Phrase) and a ping from
the wireless host. The live check (both modes) covers wireless labs: the client profiles Packet Tracer 9's API cannot
set are preloaded from the answer in solve mode.

Wireless LAN controller: `wlc-3504` / `wlc-2504` (data port `GigabitEthernet1`, crossover to a switch, chosen
automatically) with lightweight APs `lap` / `lap-3702i` on DHCP:
`wlc = { management = "192.168.60.2/24", gateway = "192.168.60.1", wlans = [{ ssid = "Staff", security =
"wpa2-psk", passphrase = "...", interface = "management" }], interfaces = [{ name = "staff", vlan = 20, ip =
"192.168.20.2/24", gateway = "192.168.20.1", dhcp = "192.168.20.1" }] }`. The management address is in both
networks; WLANs and dynamic interfaces only in the answer (`in_start = true` on one to start with it). Every WLAN
joins the default AP group. The AP needs an address on the management subnet (a router `ip dhcp pool`, in both
`[config.start]` and `[config.answer]`) and finds the WLC there by itself. Grade the controller with `wlan WLC
SSID [wpa2 PASSPHRASE]` (Packet Tracer's `CAPWAP Wireless > Wireless LANs > SSID` nodes: SSID, Enabled, Authen
Type, Encryption Type, Pass Phrase, and AP-group membership; the WLAN profile name is its SSID), the client with
`wlan LAPTOP ...` and a ping. Students configure the WLC in its web GUI from a PC (default login admin / Cisco123).
The live check preloads the WLC's WLANs in solve mode (its GUI cannot be scripted). Example: `wlc-clinic-wlan`.

WPA2-Enterprise (802.1X with a RADIUS server): on the WLC `radius = [{ ip, secret, port = 1645 }]` and a WLAN with
`security = "wpa2-enterprise"` (it uses the first RADIUS server); on a `server`
`aaa = { users = [[name, password]], clients = [{ ip = WLC management address, secret, name }] }`; on the client
`wireless = { ssid, security = "wpa2-enterprise", user, password }`. Grade with `radius WLC IP SECRET`,
`aaa SERVER user NAME PASSWORD`, `aaa SERVER client IP SECRET`, `wlan WLC SSID wpa2-ent` and
`wlan HOST SSID wpa2-ent USER PASSWORD` (all Packet Tracer's own items). `pc-wireless` is a desktop PC with an
802.11n card. Example: `wlc-clinic-enterprise`.

Per-part scores: a `[[part]]` may list its own `grade = [...]` statements; Check Results then shows a score per part
(the part title is the items' component). Statements under parts are added to the lab's grading automatically.

Interface cards: `modules = ["HWIC-2T"]` on a router fits cards into its empty slots, in slot order (copies of
real cards from the user's files; `ptlab init` lists each card and the chassis it was seen in, the only ones it may
go into). Ports are named by bay: 1841/1941/2911 HWIC slot n gives `Serial0/n/x`, ISR4321/4331 NIM bay n gives
`Serial0/n/x` with bays 1 and 2. A fitted card's interfaces start shut down and unconfigured, as on real hardware.

Fiber and access points: `router-2911-sfp` (HWIC-1GE-SFP card with a GLC-LH-SMD optic: fiber `G0/0/0`) and
`l3switch-3650-fiber` (GLC-LH-SMD optics: fiber `G1/1/1`-`G1/1/3`) are taken whole from the user's files. Fiber
links are chosen automatically and written as Packet Tracer 9 stores them, with the fiber type: single-mode between
these optics (a link read as multimode stays down on them); `cable = "eSingleMode"` / `"eMultiMode"` override it.
Access points `ap` (AccessPoint-PT), `ap-n`, `ap-ac` (Ethernet `Port 0`) and lightweight `lap`, `lap-3702i`
(`GigabitEthernet0`) take a straight-through cable to a switch.

Cable routing in the Physical view: a `[[link]]` may take `color = "#ff5500"` (the cable's colour) and
`bends = [[x, y], ...]` (bend points, in the coordinates of the room or rack both devices are in, the same as the
devices' own Physical positions); the cable is drawn device -> each bend -> device. Both ends must be in the same
room or rack. Bends only appear on cables that exist in that network (a student link has them in the answer only).

Structured cabling: `patch-panel` (Copper Patch Panel: `Jack1`-`Jack24` at the front, `PunchDown1`-`PunchDown24` at
the back) and `wall-mount` (Copper Wall Mount: `Jack1`-`Jack4`, `PunchDown1`-`PunchDown4`). Put the panel in the
rack and wall mounts in the office (`physical = "building"`). Every run is straight-through: switch port to panel
jack, panel punch-down to wall-mount punch-down, wall-mount jack to host. A student link that touches either is
graded jack by jack with Packet Tracer's own "Link to PEER > Connects to PORT" item (from the panel's side), so a
run on the wrong jack fails even when ping works. Example: `structured-cabling`. (Requires the two templates in the
library: `ptlab init ... --extra-source DIR` with a file that has them, e.g. NetAcad's structured-cabling activity.)

ASA firewalls: `asa-5506x` (`G1/1`-`G1/8`, `Management1/1`) and `asa-5505` (`E0/0`-`E0/7`). Their `[config]` is ASA
CLI (`nameif`, `security-level`, `route outside ...`, `object network`, `access-group ... interface ...`); every
port starts shut down, so used ports need `no shutdown`. Packet Tracer's tree for an ASA has **no running-config
line items**: grade it with `nameif`, `seclevel`, `ip`, `up`, `acl` (Access-group In/Out) and `object`, and prove
route, NAT and ACL with connectivity tests. Packet Tracer's ASA lets HTTP replies back in only when http is
inspected, so an `http` test through an ASA needs `inspect http` in a `global_policy` service policy (lint warns).
Labs with an ASA forward the answer network 60 s automatically (`answer_convergence_ms`); without it Packet Tracer
drops the ASA's items, because the ASA applies its configuration only after the file has loaded.

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
| `dhcp HOST` | host is set to DHCP | `Ports > PORT > DHCP client enable` |
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
| `nameif ASA IFACE NAME` | ASA interface name | `Ports > IFACE > NameIf` |
| `seclevel ASA IFACE 0-100` | ASA security level | `Ports > IFACE > Security Level` |
| `object ASA NAME NET/LEN [nat (IN,OUT) dynamic interface]` | ASA network object and its NAT rule | `Asa Object List > NAME > Address` / `Nat` |
| `clock DEV SERIAL RATE` | clock rate on a DCE serial port (lint refuses the DTE end and rates IOS rejects) | ` clock rate …` under the interface |
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
| `udp SRC DST PORT [A.B.C.D] [fail]` | UDP delivery to a port with **no service** (reachability, ACL filtering) | Connectivity Tests tab, complex PDU |

A UDP test cannot grade a service. Its PDU has no payload, and Packet Tracer counts it as successful when it is
delivered to a port where nothing listens, but as failed when a service such as DNS or TFTP receives it (live
Check Results, 2026-11-23: with DNS switched on, UDP/53 turned from pass to fail). Lint therefore refuses `udp`
to well-known service ports (DNS, DHCP, TFTP, NTP, SNMP, Syslog, RADIUS, TACACS+, CAPWAP). Use it to prove that
UDP traffic gets through, or is blocked by an ACL (`fail`), on a port with no service.

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
