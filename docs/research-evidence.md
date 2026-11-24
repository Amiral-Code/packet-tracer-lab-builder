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
  stock home router intact in all three networks. Live-confirmed (see below).
- Live Check Results on `home-cable-internet.pka` (2026-11-23): all 10 items green (Port Up on the home router,
  modem and cloud ports, the provider's DHCP pool); the home router got 198.51.100.10 from the provider's pool
  through modem, coax and cloud mapping. The ping test failed only because HOME-PC had been left on a blank
  static configuration, which no Check Results item showed: `dhcp HOST` was a local check only. It now also adds
  Packet Tracer's native item `Ports > PORT > DHCP client enable` = 1 (eclass 0), as graded in two of the user's
  activities; kept and value-identical in Packet Tracer's own save (home-cable-internet 11/11, Northstar 55/55).
- With HOME-PC on DHCP the ping test passed (live-confirmed). The saved file keeps `PORT_DHCP_ENABLE` true and the
  gateway learned by DHCP, but not the leased address (its `IP` stays empty).

## Iteration 3: ASA 5506-X (2026-11-24)

- Neither of the user's ASA activities configures the firewall; Packet Tracer's own ASA 5505 samples keep their
  configuration as running-config lines.
- The 5506-X template came from a physical-mode activity where it had been saved **powered off** (`ENGINE/POWER`
  false; `router-isr4331-serial` too) and inside a logical cluster (`DEVCLUSTERID` 2-{...}), which hid it from the
  student. Every cloned device is now powered on and placed in the root view (`1-1`). A powered-off ASA keeps no
  running-config and drops it on save, which first looked like "Packet Tracer saves no ASA running-config".
- Powered on, Packet Tracer re-parses the ASA's running-config text on load and prints it back with every port
  (`no nameif` / `no security-level` / `no ip address` / `shutdown` when unused). Ports are shut by default, so the
  text must keep `no shutdown` (Packet Tracer does not print it).
- The ASA's assessment tree has no `IOS Configuration > Running Configuration > LINES`; it has native nodes:
  `Ports > IF > NameIf` / `Security Level` (eclass 8) / `Access-group In` (eclass 2) / IP Address / Subnet Mask /
  Port Up, `Asa Object List > NAME > Address` (` subnet A M`) / `Nat` (` nat (inside,outside) dynamic interface`),
  `Access-Group List > N`, `ACL > NAME` (one string per ACL), `Routes > Static RoutesV2 > RouteN`
  (`0.0.0.0-0-GigabitEthernet1/1-0-1`, no next hop), `Policy Maps`, `Service Policy List`.
- Items are pruned at load, before the ASA applies its configuration: 5/12 kept without answer convergence,
  12/12 with `FORWARD_ANS_SIM_MS` 60000.
- Live (probe, then `examples/asa-edge-firewall.toml`'s configuration): all ASA items red before and green after
  configuring, without `write memory`; ping passed; HTTP (browser and the http test) failed through ASA PAT even
  with the outside ACL removed, `show xlate` listing the flows as `TCP-other`; with `class-map
  inspection_default` / `policy-map global_policy` / `inspect http` / `service-policy global_policy global` the page
  loaded and Check Results showed 14/14 and 2/2. Packet Tracer's ASA therefore needs inspection for HTTP replies,
  unlike a real ASA. `enable` prompts for a password even when none is set (press Enter); `show conn` is not
  implemented.
- `examples/asa-edge-firewall.toml`: 12/12 items and 2/2 tests kept, 12/12 values identical to Packet Tracer's own,
  9/9 local checks on its answer network.

## Live checks without a person (2026-11-24)

Packet Tracer can grade a lab by itself. Facts used (Packet Tracer 9.0, help pages `scriptModules*.htm` and the
`IpcAPI` reference shipped in the AppImage, and experiments):

- A `.pka` carries a File Script Module (`SCRIPT_MODULE/SCRIPTS/SCRIPT` with `ID` and base64 `CONTENT`;
  `PT_APP_META/SECURITY_SETTINGS/PRIVILEGE`). Its scripts run when the file opens and `main()` is called; with
  privileges declared Packet Tracer first shows a plain "Cisco Packet Tracer" window asking to allow them, and Enter
  allows them. Without privileges nothing could be written out.
- `ipc.appWindow().getActiveFile()` is the activity: `getCorrectAssessmentItemsCount()`,
  `getAssessmentItemsCount()`, `getPercentageComplete()`, `runConnectivityTests()`,
  `getLastConnectivityTestCorrectCount()`, `getLastConnectivityTestResultAt(i)` ("Correct"/"Incorrect").
- `SystemFileManager.writeTextToFile()` writes scrambled bytes; `writePlainTextToFile()` writes the text.
- `CiscoDevice.enterCommand(cmd, mode)` returns `{first: status, second: output}` (0 ok, 2 invalid). It refused
  section changes in mode "" and an ASA object's `nat (inside,outside) dynamic interface` (its tokenizer chokes on
  `(inside,outside)`; `( inside , outside )` passes). The device's console, `getConsoleLine()`, behaves like a person
  at the CLI (`FW>`, `Password:`, `FW#`, `FW(config-network-object)#`) and accepted every line; it is what the live
  check types into. An ASA has no `getCommandLine()`.
- Hosts: `HostPort.setIpSubnetMask`, `setDhcpClientFlag` plus `Pc.setDhcpFlag` (the port flag alone did not make the
  PC lease), `Pc.setDefaultGateway`, `HostPort.addIpv6Address`; a host's IPv6 gateway is set on its IPv6 process:
  `Device.getProcess("HostIpv6").setDefaultGateway()`.
  Cables: `LogicalWorkspace.createLink(dev1, port1, dev2, port2, type)` (8100 straight, 8101 cross, 8104 phone,
  8106 serial with the first end DCE, 8110 coax).
- The first connectivity-test run after the network comes up can lose packets (ARP), as a student's first Check
  Results does; the live check runs the tests twice and reports the second run.
- `AppWindow.fileSaveAs()` on an existing file opens a modal "Overwrite File?" dialog that stops the script.

Results (final code, each run unattended, 92-203 s):

| Example | Start | After solving | Connectivity tests |
|---|---|---|---|
| branch-cabling (student cabling) | 2/6 | 6/6 | 3/3 |
| feature-probe | 0/11 | 11/11 | 3/3 |
| feature-probe-2 (IPv6 hosts, ping6) | 0/38 | 38/38 | 2/2 |
| northstar-enterprise-recovery (mixed, 6 faults) | 7/55 | 55/55 | 4/4 |
| ts-branch-offline (troubleshooting) | 2/6 | 6/6 | 3/3 |
| serial-wan-triangle | 0/32 | 32/32 | 3/3 |
| home-cable-internet (coax, DHCP) | 0/11 | 11/11 | 1/1 |
| asa-edge-firewall | 0/12 | 12/12 | 2/2 |
| static-two-sites | 0/14 | 14/14 | 2/2 |

These agree with every live result a person had produced (serial 35/35 incl. tests, home cable, ASA 14/14).

What the live check found that no file-level check could:

- **Northstar's answer network did not work.** Its 55 items all scored correct, the round trip and value proof
  passed, yet every connectivity test failed. Diagnosis by script (show commands run inside Packet Tracer on the
  answer network): both EtherChannels were suspended (`Po1(SD)`, members `(s)`), CORE1's port-channels and VLAN
  interfaces were down, and OSPF sat in `INIT` with interfaces `WAITING` for minutes. A timeline showed why: the
  OSPF dead timer fell from 38 to 29 s over 180 s of real time, i.e. Packet Tracer's clock had almost stopped under
  a broadcast storm. Cause: the port-channels were trunks but their member ports carried only `channel-group`, and
  the 3560 core had no `switchport trunk encapsulation dot1q`, so the bundles failed and the redundant switch
  triangle looped. Bisection labs (same router models, plain OSPF; with IPv6, DHCP, default-originate; with the
  lab's activity settings) all converged, which ruled out the routers and the activity. Fixed in the example:
  members configured like their port-channel (encapsulation on the 3560, trunk mode, allowed VLANs) before
  `channel-group`. Afterwards: 55/55 items, 4/4 tests, values unchanged.
- **Troubleshooting labs need their faults undone, not only the answer typed** (a fault that shuts a port is not
  touched by an answer that never mentions the port). The script reverses each fault first: `apply` lines are
  negated, find/replace faults remove the faulty line and type the correct one in its section.
- **Timing a student would not notice:** DHCP clients must start after spanning tree has opened their access ports
  (a request sent earlier is lost and the host falls back to 169.254/16), and a routing lab needs about 90 s.
- **Merge bug found on the way:** a setting that exists once (`spanning-tree mode`, `vtp mode`, ...) was added beside
  the factory value instead of replacing it; it now replaces it.

## Iteration 3: fiber optics and access points (2026-11-24)

- In the user's files: 2911 + HWIC-1GE-SFP + GLC-LH-SMD (fiber `GigabitEthernet0/0/0`), 3650 with GLC-LH-SMD in
  `G1/1/1`-`G1/1/3` (`eSfpModule` MODULEs in the uplink slots), ISR4331 + NIM-ES2-4 (switch ports `G0/1/0`-
  `G0/1/3`; only in two T-Labs outside the library sources), LAP 3702i (`GigabitEthernet0`), AccessPoint-PT and
  AccessPoint-PT-N linked on `Port 0`. The library had named the AccessPoint-PT port `FastEthernet0`, which no link
  could use. AccessPoint-PT-AC's port name is inferred from its siblings (no link to one in any file).
- A fiber link saved by an older Packet Tracer has no cable `TYPE`. Packet Tracer 9 writes `TYPE` `eSingleMode` or
  `eMultiMode` and `OVERWITE_MISMATCH_FIBER` false (a link created through the API between GLC-LH-SMD optics
  became `eSingleMode`). Loading an untyped fiber link, Packet Tracer 9 makes it `eMultiMode`, and with the
  single-mode optics both ports stay down: `verify --values` showed Port Up 0 in the answer network. Written as
  single-mode, the answer network's ports come up (14/14 values) and the live check passes (0 -> 14/14, 1/1).

## Iteration 3: cards in empty slots (2026-11-24)

- An empty card slot is a `SLOT` (`TYPE` eInterfaceCard) with no `MODULE` (or a `WIC-Cover`/`NIM-Cover`). A card is
  a `MODULE` (`TYPE` eInterfaceCard, `MODEL`) holding its `PORT`s; copying one from a real router into another's
  empty slot works: Packet Tracer kept every item and the card's serial link came up (live check).
- Bay numbering from the user's files: HWIC/WIC slots are 0/0, 0/1, ... on 1841/1941/2911; NIM bays are 0/1, 0/2 on
  ISR4321/4331 (built-in ports are 0/0). Cards seen: HWIC-2T (1841, 1941, 2911), WIC-2T (1841, 2811), NIM-2T
  (ISR4321, ISR4331), HWIC-1GE-SFP (2911), WIC-1ENET and HWIC-8A (1841), HWIC-AP-AG-B (2811).
- A copied card keeps the source lab's port state (`POWER` true), so its interface counted as up before the
  student did anything; fitted cards now start with `POWER` false and `no ip address` / `shutdown` in the factory
  configuration (start 0/8 instead of 1/8).

## Iteration 3: wireless (2026-11-24)

- XML: a home router's 2.4 GHz WLAN is the first `WIRELESS_SERVERS/WIRELESS_SERVER` (`_cwsp_rng_tid`), mirrored in
  `ENGINE/WIRELESS_SERVER`; `WIRELESS_COMMON` holds `SSID`, `AUTHEN_TYPE`, `ENCRYPT_TYPE` and, for WPA,
  `WEP_PROCESS/KEY` (the passphrase). A wireless host has `WIRELESS_CLIENT` with the same common block, `PROFILES`
  and `CURRENT_PROFILE/WIRELESS_PROFILE` (SSID, AUTHEN_TYPE, ENCRYPT_TYPE, WEP_KEY, DHCP_ENABLED, IP_ADDRESS, ...).
  The API reference gives the enums: authen 0 null, 1 WEP, 2 WPA-PSK, 3 WPA-EAP, 4 WPA2-PSK, 5 WPA2-EAP, 6 open;
  encrypt 0 none, 1/2 WEP 64/128, 3 TKIP, 4 AES; network type 7 mixed.
- Packet Tracer's tree (bare copy): `DEV > Wireless 2.4G > SSID`, `> Security Mode > Authen Type / PassPhrase (shown
  "Pass Phrase") / Encryption Type` on a home router; `DEV > Wireless > ...` on a host. Written as above, all eight
  items were kept with values identical to Packet Tracer's own.
- A wireless host's address comes from its joined profile: the laptop template's "Default" profile (from a
  wireless sample) had DHCP off and a static 10.1.1.3/8, so the answer laptop joined but could not reach the LAN.
  Host templates' profiles are now reset to DHCP; a joined profile takes the host's addressing.
- API: `getProcess("WirelessServer")` / `("WirelessClient")` with `setSsid`, `setAuthenType`, `setEncryptType`;
  the WPA passphrase is `getWpaProcess().setKey()` (`getWepProcess()` does not hold it). `WirelessClientProcess`
  `setCurrentProfileStringIPs`, `setCurrentProfile` and `addProfile` all throw `vector::_M_range_check: __n (which is
  14) >= this->size() (which is 14)` whatever the arguments, so a script cannot join a client in Packet Tracer 9;
  the answer-network live check proves wireless connectivity instead (8/8, ping 1/1).

## Release proof (2026-11-24, v0.2.0)

- All eleven examples (the twelfth, home-wlan-security, needs the answer mode: Packet Tracer 9's API cannot join a
  wireless client) pass the live check twice, unattended: solved by the script from the start state to full marks
  and every connectivity test, and the answer network run live on its own (22 runs, all ok); home-wlan-security's
  answer network passes (8/8, 1/1).
- Per-part scores (`feature-probe-2`): 38/38 items kept with values identical to Packet Tracer's own; the saved file
  lists the parts in `COMPONENT_LIST` and files 9, 15 and 14 items under them. A comma in a part title split the
  comma-separated `COMPONENT_LIST` and Packet Tracer dropped that part from its items; commas become " / ".
- A generated variant (`ptlab variants`, Northstar v01, re-addressed 10.237/172.25): live check 7/55 -> 55/55, 4/4.
- A generated troubleshooting lab (`ptlab troubleshoot` on serial-wan-triangle, three faults): start 29/32 (each
  fault caught), live check after repair 32/32, 3/3.
- `ptlab gns3` export of static-two-sites: the CCNA GNS3 engine's selftest passes (8/8 failing before, 8/8 passing
  after the solution, no broadcast storm).



## Structured cabling (2026-11-24)

Source: the public repository alexnkoma/Packet-tracer-labs, file `1.1.4...structured-cabling...rack.pka` (NetAcad
activity, Packet Tracer 8.2.0). Used only as evidence and as the source of the two device templates (via
`--extra-source`); nothing of its content is copied into the examples.

- Devices: TYPE `Patch Panel` model `Copper Patch Panel` (48 ports: `Jack1-24`, `PunchDown1-24`), TYPE `Wall Mount`
  model `Copper Wall Mount` (`Jack1-4`, `PunchDown1-4`), all ports `eCopperFastEthernet`; no IOS, no config.
- Runs: every cable is copper straight-through (`eCopper` / `eStraightThrough`): switch port to panel jack, panel
  punch-down to wall-mount punch-down, wall-mount jack to host.
- Grading: `DEVICE > Ports > PORT > Link to PEER > Connects to PEERPORT` (eclass 4, nodeValue = name = "Connects to
  PEERPORT"), on the patch panel for both its jacks and its punch-downs; hosts at a wall mount are graded on the host
  side with `Link to WALL > Type` = "0 0". The tree also offers `Is Managed in Wiring Closet`.
- Proof: `structured-cabling` example, items kept 12/12 with values identical to Packet Tracer's own; live check
  0/12 -> 12/12 and 2/2 pings through wall plate and panel; answer network 12/12, 2/2.
\n

## Wireless LAN controller (2026-11-24)

Sources: Packet Tracer's own samples (`saves/01 Networking/Wireless/Wireless LAN/WLC/*.pkt`, e.g.
`wlc_3504_simple_wlan.pkt`, PT 7.3) and NetAcad's 1.1.6 wireless activity (alexnkoma/Packet-tracer-labs, PT 8.2).

- WLC data ports count from 1 (`GigabitEthernet1`, in every sample link); the sample cables WLC to switch with a
  crossover. A lightweight AP takes its address by DHCP and joins a WLC on its subnet by itself.
- XML: management address in `WLC_INTERFACES/PORT[NAME=management]` and `MANAGEMENT_INTERFACE/PORT`; dynamic
  interfaces are further `WLC_INTERFACES` ports (NAME, VLAN_NUMBER, IP, SUBNET, PORT_GATEWAY, DHCP_SERVER_IP);
  WLANs in `CAPWAP_AC/WLANS/WLAN_CONFIG` (SSID, AUTHEN_TYPE 4 / ENCRYPT_TYPE 4 = WPA2/AES, WEP_KEY = passphrase,
  VLAN, INTERFACE_NAME, ENABLED), listed in `AP_GROUPS/AP_GROUP[default-group]/WLANS`; joined APs in `APS` by MAC.
  An AP keeps the WLANs it learned in `CAPWAP/WLANS`.
- Templates carry their sample's state (WLANs, joined APs, dynamic interfaces, DHCP pools such as `net10`): reset.
  Packet Tracer reports the WLC's DHCP server enabled whatever `ENABLED` says; only the factory pool
  `day0-dhcp-mgmt` (192.168.1.0/28) is kept.
- Packet Tracer's own graded tree (bare save): `WLC > CAPWAP Wireless > Wireless LANs > PROFILE > SSID / Enabled /
  VLAN / Central Authentication / Central Switching / Security Mode > Authen Type / WEP Key / PassPhrase ("Pass
  Phrase") / Encryption Type`, `AP Groups > default-group > WLANs > PROFILE`, plus ports (management, virtual,
  Vlan1) and DHCP pools. NetAcad's 1.1.6 grades only the client side.
- Proof (`wlc-clinic-wlan`): items kept 10/10, values identical to Packet Tracer's own; Packet Tracer scores the
  start network 0/10. Answer network live: the AP joined the WLC (its MAC in `APS`, the WLAN in its CAPWAP copy), the
  laptop associated with WPA2-PSK, leased an address and pinged the admin PC: 10/10, 1/1. The first runs failed:
  the router's DHCP pool was written under `[config]`, which is ignored (now a lint error), and the laptop's first
  DHCP request went out before the AP had joined (answer mode now asks again after settling; WLC labs settle 90 s).
  Solve mode reaches 4/10: the WLC is configured in its web GUI, which the script API cannot drive.

## Variable Manager and scoring scripts (2026-11-24)

NetAcad's 1.1.4 and 1.1.6 activities: the Variable Manager holds one IP pool (`VLAN20Adds`, any address of
192.168.20.0/25) for an "any address in the subnet" answer, which `{{RegEx:}}` items already give; the script modules
are the stock framework (EventManager, Main, ProficiencyModel, ScoringModels, VariableManager), no custom scoring.
Not implemented: per-student variants and per-part scores cover the same needs.

## Scripting a WLC and wireless clients (2026-11-24)

Sources: Packet Tracer's own API reference (`help/default/IpcAPI`, Doxygen), its binary's strings, and its WLC web
GUI (`art/html/resources.bin`, a Qt resource file: zstd-compressed pages under `/art/html/wlc/`), plus probes run
inside Packet Tracer (a File Script Module writing its findings to a file).

- The simulation clock does not advance on its own while a script waits: HTTP requests, an AP's CAPWAP join and
  console pings stayed pending until `ActivityFile.runConnectivityTests()` was called; after it, the same requests
  completed (a web page in about 28 s of simulated time).
- PCs have `HttpClient` and `HttpBackgroundClientManager.createClient()` (methods `go`, `http_get`, `http_post`,
  event `onDone(content, serverIp, responseType, url)`; responseType 3 = page, 4 = refused/unauthorized, 5 = not
  found, 8 = no server on that port, 11 = bad URL). Background clients fetch real pages.
- The WLC's GUI is HTTPS only (HTTP: 8; HTTPS: the "Cisco Systems Login" page). Its pages submit key/values through
  Packet Tracer's `CHttpFormExtractor` (create: `buttonClicked=4, vap_profileName, vap_ssid, wlan_id`; edit adds
  `enabled, interface, authen=[WPA2][Auth(PSK)], encryptType=aes, authenKey, ...`) and log in with the native
  `submitIoeLogin`, which fills the request's `userName`/`password` (HTTP Basic). The API's client cannot carry those
  credentials (URL user info: 11; header strings or JSON as http_get/http_post arguments: 4), so protected pages
  answer 4 and posts are accepted (3) but ignored. The WLC's `CapwapAC` and the AP's `CapwapProcess` exist through
  `getProcess` but expose no methods beyond the generic Process ones. Conclusion: a WLC cannot be configured by script.
- Wireless client profile calls (`addProfile`, `setCurrentProfile[StringIPs]`) are documented with 15 parameters and
  fail with `vector::_M_range_check: __n (which is 14) >= this->size() (which is 14)` whatever is passed.
- Therefore the live check's solve mode preloads exactly these GUI-only settings from the answer network into the
  start network before Packet Tracer opens it (`CAPWAP_AC`, `WLC_INTERFACES`, `MANAGEMENT_INTERFACE` of a WLC;
  `WIRELESS_CLIENT` of a wireless host), drives the clock, solves everything else by typing and API calls, and makes
  preloaded clients re-scan after their access point changes. Results: home-wlan-security 8/8, 1/1 (the router is set
  through the API, the laptop joins and pings); wlc-clinic-wlan 10/10, 1/1 (the AP joins live, the laptop associates
  through it, leases and pings). The report marks the start score as "with the GUI-only settings preloaded"; the true
  start network was scored by a plain run (wlc-clinic-wlan 0/10).

## Cable bend points and colours (2026-11-24)

Source: a file saved for the purpose by the author (PT 9.0.1: two PCs, one copper cable, two bend points, coloured).

- Colour: `CABLE/GEO_VIEW_COLOR` (#rrggbb).
- Bends are not in the LINK: `PACKETTRACER5/.../GEOVIEW_GRAPHICSITEMS/ParentPhyObject[Path = the room both devices
  are in]` holds the cable as segments `GeoConnectionItems/GEOCONNECTIONITEM` (StartX/Y, EndX/Y in the room's
  coordinates, the ends at the devices' own Physical node X/Y; Color; PhysicalObject1/2 = the devices' physical
  paths; IsStartCable/IsEndCable; Link = the cable's index in NETWORK/LINKS) and `BreakPointItems/BREAKPOINTITEM`
  (X, Y, Cable1/Cable2 = the indices of the two segments it joins, within that room).
- The library's base topology carried such a drawing from its source file (Link 1); Packet Tracer attached it to
  every generated lab's second cable and recoloured it. Generated topologies now start without drawings.
- Proof: a lab with one cable bent twice and coloured, another only coloured: after Packet Tracer's save, both bends,
  their joins, the segments and both colours are unchanged.

