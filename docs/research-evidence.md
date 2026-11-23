# Packet Tracer research evidence

This ledger separates observed file/binary facts from implementation inferences and unconfirmed behaviour. It is
for maintaining the builder, not a claim that undocumented Packet Tracer internals are a stable public API.

## 2026-11-22 baseline

- Packet Tracer: Linux 9.0.1 (`packettracer 9.0.1-1`).
- Main executable SHA-256: `3e871b6463798076e4c26adfc2bb4820b9a7822b18bf1cdb33d949048fd3a9db`.
- Local activity survey: 90 `.pka` files decoded successfully after stripping XML-forbidden control bytes from
  the opaque outer activity value. No third-party activity content is stored in this repository.
- Static inspection: Rizin through REA 6.10.1. Static string/symbol evidence corroborates names and storage, not
  runtime semantics. The scanner can omit large regions, so an absent string is not evidence that a feature is absent.

## Observed

Activity controls in the 90-file survey:

- `TIMERTYPE="0"` appeared in 88 activities.
- `TIMERTYPE="2"` appeared in two countdown activities. Both used
  `COUNTDOWNMS="600000"`, `COUNTDOWNLEFT="600000"`, `COUNTDOWN_EXPIRED="0"`, and `ENABLED="no"`.
- `PASS` was empty in seven activities. The other 83 values were uppercase 32-character hexadecimal strings.
- `FORWARD_ANS_SIM_MS` existed but was `0` in all 90 surveyed activities.
- Overall complete/incomplete feedback appeared as empty, text, or HTML-shaped content.
- Variable Manager pools and locking-tree switches were populated in multiple activities. The broad locking-tree
  contract is not fully mapped; only a conservative named-switch subset is exposed as presets.
- The local activity base exposes named locking switches for Config-tab use, switching to Simulation, command-log
  viewing, copy/paste, and many other global and per-device actions.

Saved connectivity PDUs in that corpus:

- 146 answer-network PDUs were found: 136 direct type `0`, eight patterned type `1`, and two type `20`.
- Observed patterned TCP PDUs use direct type `1`, a nested `CIpHeader` and `CTcpHeader`, source port `5000`,
  destination service port, `LENGTH=136`, `PDU_SIZE=10`, and a destination IP string.
- Type `20` examples were nested IPv6 ICMP PDUs; they are not implemented by the builder yet.

Device templates in that corpus included 90 ISR4321 and 15 Cisco 1841 instances. Both use the existing Router
template/reset path, so they are recognized by the library builder when a user's own initialization sources contain
them. Other observed types such as ASA 5506-X and HomeRouter-PT-AC need type-specific configuration and cabling
work before they can be exposed safely.

Static executable evidence:

- Strings `TIMERTYPE`, `COUNTDOWNMS`, and `FORWARD_ANS_SIM_MS` occur in the executable's read-only data.
- The symbol table contains the mangled name for `Util::md5Digest`.

## Inferred and implemented

- Timer type: `TIMERTYPE` is stored unchanged in `CActivityFile` field 0x330 (`getTimerType`/`setTimerType`).
  The activity window (`CInstructionDialog`) draws "Time Elapsed" for 0, "Time Left" for 1, and no timer for any
  other value. Countdown is therefore written as `1`. The two type-2 files above carry countdown values but show no
  timer; their values are most likely left over from an earlier setting.
- Activity Wizard password: `CActivityWizard::m_enablePassBtn_clicked` calls `Util::md5Digest(salt, utf8(password))`,
  which is MD5 over a fixed 12-byte salt (`c0a801be79392311a09bc602`, built inline) followed by the password,
  upper-case hex. Real files store the salt in `ACTIVITY VALUE` (the "opaque outer activity value" above). The formula
  reproduces the `PASS` of a published NetAcad activity from its widely known password. It is an edit deterrent only.
- TCP outcome statements reproduce the observed type-1 PDU shape. Aliases map HTTP/HTTPS/SSH/Telnet to their
  standard TCP ports; arbitrary ports use `tcp SRC DST PORT`.
- `cli-only`, `realtime-only`, and `exam` presets enable only locking switches found by exact name in the local
  activity base. They deliberately leave Check Results and Reset Activity unlocked.

## Still unknown or awaiting live confirmation

- Countdown expiry/reset behaviour, non-zero answer-convergence behaviour, profile-lock reset behaviour, and
  password acceptance need live Packet Tracer confirmation on generated activities.
- Generated TCP allow/deny tests are structurally matched to observed files, but their end-to-end execution needs
  live confirmation on services and ACLs configured by the builder.
- No reliable saved UDP PDU encoding was recovered in this survey. DNS/UDP generation is intentionally omitted
  rather than guessed.
- Current locking-preset effects still need live confirmation. The Physical Locations branch is regenerated from the
  generated network's own UUID paths (intercity, city, building, wiring closet; racks are not locations); "Start in
  Location" on a generated closet still needs live confirmation.

## 2026-11-22 live results

- Wizard password (salted hash): **confirmed**: the Activity Wizard asked for it and accepted it.
- Countdown (`TIMERTYPE="1"`): **confirmed**: the activity window showed Time Left.
- Start in closet: **failed** on the first try. `CActivityFile::doStartingTasks` first tests the Interface switch
  with ID "Physical Workspace" (text "Start in Physical Workspace"); only then does it walk Physical Locations
  and call `CWorkspace::switchTo(path)` → `CPhysicalObject::getFromPath`. The generated location IDs match the
  scheme of real activities (cumulative UUID paths present in all three networks). The builder now switches on
  "Start in Physical Workspace" together with the location; re-check pending.
- Per-item hints (`incorrectFeedback`) and the debrief page/complete feedback: **confirmed**.
- Fixed topology: **failed** on the first try: the global switches were on but deleting still worked. The global
  "Remove Devices" is referenced only by the lock-tree editor (a select-all); `CSelectedItems::hasUnremovableItem`
  and `CLogicalWorkspace::handleDeleteSelections` call `CAppWindow::isInterfaceLocked(category, device name,
  "Device_Remove")`. The activity base's Existing Devices branch named its own devices (IoT1…Router3), so no
  generated device had an entry. The builder now rebuilds Existing Devices from the generated devices and ports
  (Device_Remove, Port_Remove/Connect/Disconnect per port) and the presets switch those on; re-check pending.
  This also makes `cli-only`'s per-device "Device Use Config Tab" effective.
- 2nd live tries: start in closet **confirmed**; fixed topology **confirmed** (deleting a device and a cable refused).
- Feature probe (`examples/feature-probe.toml`): Check Results complete, Connectivity Tests 3/3 (ping, HTTP succeed;
  HTTPS fail with the ACL): config lines, sub-command lines, Access VLAN and TCP tests **confirmed**.
- Packet Tracer **silently drops** assessment items whose node does not exist in the answer network as it saves
  it. Two cases found by decoding the activity the student saved after Check Results:
  - VLAN name: the VLAN existed only in the answer's config text, not in the switch's VLAN database
    (`ENGINE/VLANS`). Fixed by mirroring `vlan`/`name` sections into the database; confirmed (the item appeared).
  - Static routes: Packet Tracer writes `ip route …` with a **trailing space**, so the LINES node ID must end with
    one. Fixed (`PT_TRAILING_SPACE`); re-check pending.
  The same saved file showed leftover port `DESCRIPTION`s from source templates ("Naar SW1 (beheer ongetagd)" on a
  2911, "Trunk naar SW1" on a 3560) being re-applied as `description` lines; they are now cleared at library build
  and on every device clone.
- Variable Manager authoring, regular-expression answers, scoring-model partial credit, and script modules remain
  research tasks.

## Round-trip verification (2026-11-23)

Opening a built activity in Packet Tracer and saving it immediately (Ctrl+S sent to a hidden window) already shows
the pruned assessment tree, so pruning happens at load. `ptlab verify SPEC SAVED.pka` compares the built items with
the kept ones. First run over the examples: four clean, Northstar 43/48. Causes, each fixed:

- `no switchport` was removed by the builder's merge (every indented `no X` was treated as "remove X"), so the 3560
  rejected the routed port's IP address. The merge now keeps negations IOS shows in its running-config.
- IPv6 on the 3560 needs `sdm prefer dual-ipv4-and-ipv6 default` and a reload. The SDM template is stored in
  `ENGINE/SDM/ACTIVE_TEMPLATE`; `sdm_prefer_dual_default` passes `Switching::ETemplate` 5 (default 0, access 2,
  routing 3, vlan 4, dual-routing 6, dual-vlan 7, lanbase-routing 8, qos 9). Switches whose answer uses IPv6 are
  preset to 5 in every network; `ipv6 unicast-routing` and the IPv6 addresses then appear in Packet Tracer's config.
- Even with the addresses present, the two `ipv6 address …` line items were dropped while every line without `:`
  was kept. First inference (wrong, corrected below): `:` cannot appear in a LINES node ID. Lint rejected such items
  until iteration 2.

After the fixes all five examples pass: every item and connectivity test kept, every local check passing on
Packet Tracer's answer network.

## Iteration 2: grading formats (2026-11-23)

Sources: 93 locally available activities (the user's own course files, decoded locally, nothing copied into the
repository), plus round trips of generated activities through Packet Tracer 9.0.1.

Observed in real activities:

- **Several right answers:** graded items carry `variableEnabled="true"` and `variableName="{{RegEx:PATTERN}}"`
  (71 items; not `RegExMatch`). Seen on port descriptions (`.*[Ss][3].*`, `^(?!\s*$).+`), MOTD banners, NAT source
  settings and IP addresses (`\b(192?)\.(168?)\.(2?)\.(25[0-5]|…)\b`). Case-insensitivity is written with character
  classes; the builder does the same and anchors its own patterns with `^…$`.
- **LINES IDs write `:` as `-`.** A Packet Tracer-saved answer has the ID
  `ipv6 route 2001-DB8-10--/64 2001-DB8-0-1--2` for the line `ipv6 route 2001:DB8:10::/64 2001:DB8:0:1::2`; IPv6
  addresses are printed compressed and upper case. This, not a ban on `:`, is why the earlier IPv6 line items were
  dropped. Lint no longer rejects them; the builder normalises the line and converts the ID.
- **Trailing spaces** in Packet Tracer's running-config (counted over the answer networks): `ip route` (105 of 118),
  `ip nat inside source static` (all; `… list` never), `switchport port-security mac-address sticky` (the bare
  command), `switchport port-security violation …`, `aaa authentication login`, `ip host`, `redistribute`.
- **Native item paths and values:** `Ports > IF > Ipv6 Address > ADDR > IP Address | Prefix`, `Default Gateway IPv6`,
  `Ports > IF > Description`, `Banner motd`, `Ports > IF > NAT` (1 inside, 2 outside: matched to `ip nat inside/outside`
  in the same file), `Ports > IF > Access-group In|Out` (the ACL name or number), `Ports > IF > Port Security >
  Enabled | Max Secure Mac | Sticky Enabled | Violation` (restrict = 2), `Ports > IF > PortFast` (1),
  `DHCP Server > Pools > NAME > Name | Start IP address | Subnet mask | Default Gateway | DNS Server`,
  `Enable Secret`, `User Names > NAME` (`NAME HASH`).
- **Secrets:** every `Enable Secret`/username hash uses MD5-crypt with the fixed salt `mERr`. MD5-crypt of `class`,
  `cisco12345` and `Ciscoenpa55` with that salt reproduces the stored values exactly.
- **Hosts' IPv6:** `PORT/IPV6_ADDRESSES/IPV6_ADDRESS` (`ADDRESS`, `PREFIX`, `TYPE` 0), `PORT/IPV6_PORT_GATEWAY`
  and `ENGINE/GATEWAYV6`.
- **ICMPv6 test:** type `20`, `DESTINATION` is the address text, then the same nested `CIpHeader`/`CIcmpMessage`
  as IPv4 with IPv6 `SRCADDR`/`DSTADDR`.

Observed in round trips (live Packet Tracer, no GUI interaction):

- Packet Tracer keeps the value and pattern written for a **graded** item exactly as written (a deliberately wrong
  NAT value `9` and pool start `1.2.3.4` survived a save). Saved graded values therefore prove nothing.
- On save it fills the **rest** of the tree from its own answer network. Saving a copy with no assessment items
  (`ptlab bare`) yields Packet Tracer's own value for every node: the reference `ptlab verify --values` compares
  against. It showed port-security `protect` = 1 (so shutdown 0, protect 1, restrict 2), the DHCP pool start
  = the network address, and that `banner motd ^C…^C` is misread by Packet Tracer (use another delimiter, e.g. `#`).
- `examples/feature-probe-2.toml` (38 items over every new kind, two connectivity tests): 38/38 items kept, 2/2
  tests kept, 38/38 values identical to Packet Tracer's own, 30/30 local checks pass on Packet Tracer's answer.

Live-confirmed 2026-11-23 with Check Results on `feature-probe-2.pka` (40/40 items, 2/2 connectivity tests):

- `{{RegEx:}}` items turn green for values other than the answer's: PC1 at 192.168.10.150 with gateway
  192.168.10.1 (answer .10 / .254), description "Users LAN segment", banner "Only authorized staff may connect".
- `ping6` (type-20 PDU) passes once PC2 has its global address and the link-local gateway.
- The generated enable-secret hash, the `{user}` item, and IPv6 config lines with `:` stored as `-` all go green.
- A wrong entry stays red as it should: with FE80::1 typed into PC2's *link-local* field and no global address,
  the three IPv6 items and ping6 failed.

UDP connectivity tests (2026-11-23):

- A Complex PDU saved by the user (application DNS, and OTHER/UDP port 69) is stored as scenario `PDU` with
  `TYPE patterned="no"` `2`, `DESTINATION` as address text, and a `CIpHeader` (`SRCADDR`, `DSTADDR`, `TTL` 32)
  holding a `CUdpHeader` (`SRC` 5000, `DST` port, `CHK` 0, `LENGTH` 8). Choosing "DNS" only sets the port.
- Built that way, five tests survived Packet Tracer's own save unchanged.
- Live Check Results on `udp-probe.pka` (PC1 -> SRV1, default services):

  | Test | DNS off | DNS on |
  |---|---|---|
  | ping | pass | pass |
  | UDP/53 | pass | **fail** |
  | UDP/69 (TFTP, on by default) | fail | fail |
  | UDP/5555 (no service) | pass | pass |
  | UDP/53 to a missing host, expected to fail | pass | pass |

  Inference: the empty-payload PDU counts as delivered at a closed port, and as failed when a service consumes and
  rejects it. UDP tests are therefore used for delivery and filtering only.
- Filtering confirmed live on `udp-acl-probe.pka` (PC1 -> R1 -> SRV1): without the ACL, `udp ... 5555 fail` was
  red (2/3); after `access-list 100 deny udp any any eq 5555` / `permit ip any any` inbound on G0/0, ping,
  UDP/5556 (should pass) and UDP/5555 (should fail) were all correct (3/3).
- Corroboration: none of the 310 connectivity tests in the 93 decoded activities is UDP (ICMP, ICMPv6 and TCP
  only); Packet Tracer's help says a Complex PDU's application choice only sets its ports. No public source
  describes UDP test outcomes.

Still open: whether Check Results compares the stored value or the answer network's value for non-pattern items.
They are identical for every generated item, so it does not affect grading.

## Iteration 3: serial WAN (2026-11-23)

Observed in the 93 decoded activities:

- Interface cards fitted in routers: 1941 + HWIC-2T (111 devices), ISR4321 + NIM-2T (54), 2911 + HWIC-2T (27),
  1841 + WIC-2T (9), ISR4331 + NIM-2T (9), ISR4331 + NIM-ES2-4 (15), 2911 + HWIC-1GE-SFP (6). A card is a
  `MODULE` (`TYPE` eInterfaceCard, `MODEL`) in a `SLOT` of the router's module tree, holding its own `PORT`s
  (`eSmartSerial`, with `CLOCKRATE`). Empty slots hold `WIC-Cover`/`NIM-Cover`.
- A serial `LINK` has `TYPE` eSerial and **no** cable `TYPE`; `DCEDEV`/`DCEPORT` name the DCE end
  (Packet Tracer 7.2 to 8.x, `IS_MANAGED_IN_RACK_VIEW` from 8.0).
- Running-configs show ` clock rate 2000000` on serial interfaces by default, on both ends; the DCE end shows
  the configured rate. No activity grades clock rate natively: it is graded as a config line.
- Generic devices carry user-changed module sets: Router-PT and Cloud-PT templates are therefore only taken
  with Packet Tracer's stock fit.

Implemented: `-serial` library variants taken whole from those files, serial links in the format above, `clock`
statement, lint for serial pairing and DCE ends. `examples/serial-wan-triangle.toml` (ISR4321 + two 1941s, three
serial links): 32/32 items and 3/3 tests kept by Packet Tracer's own save, 32/32 values identical to Packet
Tracer's own, 23/23 local checks on its answer network, and all three serial links kept with their DCE ends.
Live-confirmed 2026-11-23 (`serial-wan-triangle.pka`, Check Results **35/35**, Connectivity Tests **3/3**):
`show controllers serial 0/1/0` on HQ reports `DCE V.35`; after configuring, every serial item, the three
clock-rate lines and all three pings are green. In the student's saved network the DCE ports hold the configured
`CLOCKRATE` (128000, 128000, 64000) and the DTE ports `CLOCKRATE` 0 with no `clock rate` line, so the
` clock rate 2000000` seen on both ends in older files is a saved-configuration artefact, not live behaviour.
On ISR routers `show controllers serial` needs the port number (`show controllers serial 0/1/0`).

## Iteration 3: home and provider devices (2026-11-23)

- Packet Tracer stores no port names for these devices; names come from links in the user's files and Packet
  Tracer's samples: HomeRouter-PT-AC `Internet`, `GigabitEthernet 1`-`4`; Linksys-WRT300N `Internet`,
  `Ethernet 1`-`4` (the library had listed `FastEthernet0`-`4`, which no link could use); Cable-Modem-PT and
  DSL-Modem-PT `Port 0`/`Port 1`; CoAxialSplitter-PT `Coaxial0`-`2`; stock Cloud-PT `Serial0`-`3`, `Modem4`,
  `Modem5`, `Ethernet6`, `Coaxial7`; Central-Office-Server `Backbone`, `Coaxial0/0`-`0/5`; Cell-Tower `Coaxial0`.
- Coax and phone links have link `TYPE` `eCoaxial` / `ePhoneLine` and no cable `TYPE`. Copper links to home and
  provider devices are straight-through in the samples (two user files use crossover to a modem).
- A Cloud's cable/DSL mapping: `MODEM_CONNECTIONS/CONNECTION` (`PORT1` coax or modem port, `PORT2` Ethernet port)
  and `MODEM_CONNECTION_TYPES/CONNECTION_TYPE` (`PORT` the Ethernet port, `DSL` true/false). Frame-relay style
  sub-links live in `CONNECTIONS` (not used).
- Home routers keep non-IOS settings in the engine (`INTERNET_CONNECTION_TYPE` 0 = DHCP, 2 = static,
  `LAN_IP_ADDRESS`, `DHCP_SERVER/POOLS/POOL`, wireless `SSID`); the Internet port's `PORT_DHCP_ENABLE` is true
  out of the box. Several source copies were author-modified (blank 0.0.0.0, static WAN, custom SSID), so only
  stock-state copies are used as templates. No activity grades home-router settings, so none are graded yet.
- `examples/home-cable-internet.toml`: 10/10 items (including Port Up on the home router, modem and cloud ports)
  and 1/1 test kept by Packet Tracer's own save, 10/10 values identical to its own, cloud mapping, coax link and
  stock home router intact in all three networks. Pending live check.

