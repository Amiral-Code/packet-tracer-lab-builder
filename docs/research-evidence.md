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
  was kept. Inference: `:` cannot appear in a LINES node ID (it separates Packet Tracer assessment paths, e.g.
  `Network:Router0:Power`). Lint now rejects such items.

After the fixes all five examples pass: every item and connectivity test kept, every local check passing on
Packet Tracer's answer network.
