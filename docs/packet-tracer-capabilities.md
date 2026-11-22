# What a Packet Tracer activity can do

A map of Packet Tracer 9.0.1's activity (`.pka`) and platform capabilities, and of what pt-lab-builder uses so
far. Sources: Packet Tracer's bundled help (Activity Wizard, assessment-item reference, CLI references, Physical
workspace), locally available activity files (including a 90-file control-field survey), static binary evidence
collected with Rizin, and activities built and checked live. See [Research evidence](research-evidence.md) for the
observed/inferred/unknown boundary.

Status: **used** = the builder generates it and it was confirmed in Packet Tracer; **built** = generated, opens,
not yet confirmed live; **open** = available in Packet Tracer, not used yet.

## Activity features

| Feature | What it does | Where it lives | Status |
|---|---|---|---|
| Three networks | student, initial (Reset Activity), answer | `PACKETTRACER5` ×3, in that order | used |
| Instruction pages | multi-page HTML with Back/Next | `ACTIVITY/INSTRUCTIONS/PAGE` | used |
| Assessment tree | compares chosen settings of the student's network with the answer network (149 node classes, see below) | `COMPARISONS` (checkType 2 on graded leaves, 1 on their branches) | used: IP/mask, Port Up, gateway, hostname, VLAN name, access/native VLAN, config lines (`LINES` nodes) |
| Points and components per item | weight items; group the score by Ip/Routing/Switching/Physical/Other | `POINTS`, `COMPONENTS` | used: configurable positive integer weights per statement |
| Per-item feedback | a hint shown next to each **incorrect** item in Check Results | `NAME incorrectFeedback` | used: automatic and per-item overrides |
| Connectivity tests | Realtime PDUs sent at Check Results, expected to succeed or fail | PDUs in the answer network's first scenario, `TEST_CONDITION` 3/2 | used (ping) |
| Complex-PDU tests | the same with a TCP PDU to a port (HTTP 80, HTTPS 443, SSH 22, Telnet 23, or explicit port) | same scenario, complex PDU | built from observed TCP encodings; live outcome confirmation pending; UDP/DNS unknown |
| Overall feedback | message when complete / incomplete (HTML) | `OVERALL_COMPLETE_FEEDBACK`, `OVERALL_INCOMPLETE_FEEDBACK` | used (generic); custom per-lab text built |
| Dynamic feedback | live "Completion: x %" while working | `DYNAMIC_PERCENTAGE_FEEDBACK` | used |
| Timer | elapsed time, a countdown limit, or none | `ACTIVITY TIMERTYPE` (0 elapsed, 1 countdown, 2 none), `COUNTDOWNMS`, `COUNTDOWNLEFT` | built; values from the activity window's code, live expiry pending |
| Answer convergence | fast-forward the answer network before comparing (OSPF/STP need time) | `ACTIVITY FORWARD_ANS_SIM_MS` | built; field observed, non-zero behaviour needs live confirmation |
| User profile locking | changing the student name resets the activity | `USER_PROFILE_LOCKED` | built; live reset behaviour pending |
| Password | locks the Activity Wizard: MD5(fixed salt + password), salt also in `ACTIVITY VALUE`; reproduces a real NetAcad hash | `ACTIVITY PASS`, `VALUE` | built (`--password`); an edit deterrent, not secure storage |
| Locking tree | named switches, `on="yes"`: block Physical/Simulation, CLI/Config/Desktop tabs, delete/move/create devices, cabling, Check Results, Reset; per-device locks; **start in a Physical location**; open a device's dialog on start | `LOCKINGTREE` | built presets: `cli-only`, `realtime-only`, `logical-only`, `fixed-topology`, `exam`; `start_in` site closet (live check pending) |
| Initial network setup | alternative starting values for chosen items | `INITIALSETUP` | open |
| Object location sets | several logical layouts, picked at random or by variable | `OBJECT_LOCATIONS` | open |
| Variable Manager | seed/number/string/IP pools: per-student random names and addressing; "Entire Range" accepts any pool value as correct | `VARIABLE_MANAGER` | open: anti-copying, like `lab pt mystery` |
| Regular-expression items | `{{RegExMatch:…}}` instead of a fixed value (e.g. any host address in a subnet) | item `variableName` | open |
| Config-line scripts | `{{DeviceConfig.isInConfig:LINE}}`, `isInConfigParent:PARENT:LINE` (exact whole-line match, from the bundled `Ext.AssessmentModel.DeviceConfig.js`) | item `variableName` | known; `LINES` nodes are used instead |
| Scoring model and scripting | evidence-centred design: JavaScript rules combining items into partial credit and custom feedback ("2 of 3 routers addressed") | `SCRIPT_MODULE`, proficiency model | open, larger |
| Script modules | `.pts` extensions with their own UI and data store | `SCRIPT_MODULE_MANAGER` | open, larger |
| Multiuser | activities spanning several Packet Tracer instances (team labs) | `MURemoteNetwork` items | open |
| Activity window tabs | Network Topology, Addressing Table, User Notes tabs (8.2+) | `INSTRUCTIONS enable_tab` | open (format not yet traced) |

### Assessable node classes (149)

Routing: RoutingProcess (static routes, `ip routing`), RoutingProcessV6, OSPF/OSPFv3, EIGRP/EIGRPv6, RIP/RIPng,
BGP, NAT/NATv6, GRE, tunnels, ISATAP.
Switching: SwitchPort (mode, access/native/voice VLAN, trunk VLANs, PortFast, BPDU guard, root guard, storm
control), VLANs, VTP, STP (per-VLAN priority, RSTP, PortFast default), EtherChannel, port security, DHCP
snooping, DAI.
Services: DHCP server/pools/relay, DHCPv6, DNS, NTP, syslog, SNMP, FTP/TFTP, HTTP/HTTPS, email, SSH, AAA,
RADIUS/TACACS, privilege levels and parser views, terminal lines (passwords, access-class).
Security: ACL/ACLv6, zone-based firewall, CBAC, IPS, IPsec (crypto maps, IKE, transform sets), Easy VPN, ASA
objects and access groups.
QoS: class maps, policy maps, priority/custom queues.
Voice: CME, ephones, dial peers.
Wireless: AP and WLC settings, wireless clients.
Devices and ports: power, port up, IP/mask/IPv6, MAC, description, Link-to (cable peer), DCE port, keepalive.
Not every leaf's value format is documented; the builder only grades formats confirmed in real files.

## Platform

### Devices

Packet Tracer's own sample files use 140 device models; the builder recognizes 26. The latest local survey found
ISR4321 and 1841 templates, so both are now supported when present in a user's initialization sources.
CCNA/CCNP-relevant models available but not yet in the library include ASA 5505/5506-X, ISA 3000, IR1101,
IR8340, C8200 (PT8200), 819HGW, 829,
CGR1240, 2950/2950T switches, Switch-PT, IE-2000/3400/9300 industrial switches, WLC-PT, Meraki MX65W and server,
DSL and cable modems, home router (AC), analog and home-VoIP phones, cell tower and central-office server, sniffer,
plus about 80 IoT things, PLC/HMI and OT gear. Adding a model is one entry in `library.WANT`, plus deciding whether
the builder treats it as IOS (configurable), host, or neither.

Modules: routers take HWIC-2T/WIC-2T/NIM-2T serial cards, HWIC-4ESW/NIM-ES2-4 switch modules, HWIC-1GE-SFP and
SFP/GLC optics, HWIC-AP wireless, analog voice (HWIC-8A, NM-8AM). The builder cannot add modules yet, so serial
WAN links need a template that already has a serial card.

### IOS features (from the CLI references)

Routers: static v4/v6, OSPF/OSPFv3, EIGRP v4/v6, RIP/RIPng, basic BGP, NAT/PAT, standard/extended/named ACLs,
DHCP and DHCPv6 pools, HSRP, GRE and IPsec (crypto maps, dynamic maps), zone-based firewall, CBAC/IPS, AAA with
RADIUS/TACACS, SSH, NTP, syslog, SNMP, parser views, QoS class/policy maps, Frame Relay/HDLC/PPP (with PAP/CHAP).
Switches: VLANs, VTP, PVST/Rapid-PVST, EtherChannel (LACP/PAgP), port security, DHCP snooping, DAI, storm
control, voice VLAN, SPAN, L2NAT, REP and PTP (industrial), SVIs and routed ports on multilayer switches.
Out of scope for Packet Tracer: MPLS, VRFs, IS-IS, advanced BGP policy, multicast routing, DMVPN, SD-WAN, real QoS.

### Physical workspace

Intercity → city → building → wiring closet → rack, plus generic containers; custom backgrounds and grids;
moving devices between containers; Ethernet copper limited to 100 m and wireless ranges by distance (only when
"cable length effects" is on); cable bend points, group points and colours; structured cabling (copper/fibre
patch panels, wall mounts, horizontal cabling straight-through only); an industrial control panel (9.0).
Builder: sites (building/closet/rack per site, cities), measured rack stacking, floor grid, student cabling labs
graded by Port Up and pings. Cable-length effects are forced off.

### Simulation mode

Event list with protocol filters, step-by-step PDU inspection (OSI and inbound/outbound views), complex PDUs, and
scenarios. An activity can start in Simulation mode (locking tree) for "watch and explain" labs.

## Suggested next steps for the builder

1. **Live-confirm the newly built controls:** countdown expiry, non-zero answer convergence, profile lock, password,
   custom overall feedback, and TCP allow/deny outcomes in Packet Tracer 9.0.1.
2. **Extend locking controls:** live-confirm current presets, then add a `cabling` preset that starts inside the
   intended wiring closet without depending on unstable source-template UUIDs.
3. **Flexible answers:** `RegExMatch` items such as "any host address in 192.168.10.0/24".
4. **More models and modules:** ASA 5505/5506-X, 2950, sniffer, home router, cell tower; serial and switch
   modules for WAN labs.
5. **Per-student variants:** Variable Manager pools for addressing and names.
6. **Conditional partial credit:** research the scoring model for rules such as “two of three routers addressed.”
   Ordinary per-item partial credit already works through statement point weights.
