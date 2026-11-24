# Changelog

## Unreleased

- Structured cabling: copper patch panels and wall mounts (`patch-panel`, `wall-mount`), their jacks and
  punch-downs, and each run graded with Packet Tracer's own "Link to PEER > Connects to PORT" item, the way
  NetAcad's structured-cabling activity grades it. New example and recipe `structured-cabling`, proven live
  (0/12 -> 12/12, pings 2/2; answer network 12/12).
- Wireless LAN controllers: `wlc-3504` / `wlc-2504` with lightweight APs, `wlc = {...}` (management address,
  dynamic interfaces, WLANs in Packet Tracer's own format) and `wlan WLC SSID wpa2 KEY` graded with the native
  `CAPWAP Wireless` items. Templates are reset to factory state (no sample WLANs, joined APs, interfaces or DHCP
  pools; an AP forgets the WLANs it learned). New example and recipe `wlc-clinic-wlan`.
- Lint: device configuration written directly under `[config]` (ignored before, silently) is an error.
- Live check, answer mode: DHCP clients ask again once the network has settled; WLC labs wait 90 s for the AP.
- `ptlab init --extra-source DIR`: a folder whose files only add device models the regular sources lack (a
  downloaded sample cannot replace a proven template).

## 0.2.0 (2026-11-24)

Every example in this release is proven three ways: `ptlab lint` (spec check and self-check), Packet Tracer's own
round trip (`ptlab verify --values`: every item kept, every value identical to Packet Tracer's own), and a live
check run by Packet Tracer itself (`ptlab live-prepare`: the lab is solved from its start state to full marks and
every connectivity test passes, and its answer network passes on its own).

### Proving labs

- `ptlab verify SPEC SAVED [--values BARE]` and `ptlab bare`: compare a built lab with the copy Packet Tracer saves.
- `ptlab live-prepare` / `live-report`: a script inside the activity (Packet Tracer's JavaScript engine and API)
  types every answer configuration at each device's console, adds the student's cables, repairs hidden faults, sets
  host addresses, waits for the network and grades it; `--answer` runs the answer network itself live.
- Found on the way: Northstar's EtherChannel design (port-channel members without trunk settings, no trunk
  encapsulation on the 3560) suspended the bundles and looped the switch triangle until Packet Tracer's clock
  nearly stopped, although all 55 items scored correct. Fixed.

### Grading

- Several right answers (`{{RegEx:}}` items): any host address in a subnet, either of two gateways, a description
  or banner that mentions a word.
- IPv6 everywhere (`ip6`, `gw6`, `route6`, `ping6`), UDP tests (delivery and filtering only), DHCP clients.
- New statements: `portsec`, `portfast`, `nat`, `acl`, `hsrp`, `pool`, `rid`, `passive`, `secret`, `user`, `desc`,
  `banner`, `clock`, `nameif`, `seclevel`, `object`, `wlan`, `udp`.
- Per-part scores: statements listed under a `[[part]]` are reported as that part in Check Results.
- Lint warns when a lab grades only configuration or only outcomes, refuses UDP tests to service ports, and warns
  about HTTP through an ASA without `inspect http`.

### Devices and media

- Serial WAN: routers with HWIC-2T, WIC-2T and NIM-2T cards, serial links with a named DCE end.
- Cards in empty slots (`modules = ["HWIC-2T"]`), named by bay and starting shut down.
- Home and provider gear: home router, Linksys, cable and DSL modems, splitter, cloud cable/DSL mapping, central
  office, cell tower; coax and phone links.
- ASA 5506-X and 5505 with native ASA items.
- Fiber: 2911 with an SFP card and 3650 with GLC-LH-SMD optics, single-mode fiber links in Packet Tracer 9's format.
- Access points (AccessPoint-PT, -N, -AC, LAP, LAP 3702i) and wireless WLANs (`wireless = {...}`) with WPA2-PSK.
- Fixed: Linksys and access-point port names, devices saved switched off or inside a cluster in their source file,
  wireless profiles carrying a sample's static address, single global settings added beside the factory value.

### For instructors

- `ptlab recipes` and `ptlab new`: start a lab from one of twelve proven examples with fresh addressing.
- `ptlab troubleshoot`: turn a configure lab into a troubleshooting lab with faults drawn from its own answer
  configuration, each caught by a graded item.
- `ptlab variants`: one re-addressed copy per student, each checked.
- `ptlab grade`: grade a folder of saved student files into grades.csv and grades.html, matching each to its variant.
- `ptlab gns3`: compile a spec into a GNS3 lab (IOU + VPCS) for the author's CCNA engine.

## 0.1.0

First release: native `.pka` generation from TOML specs, assessment items and connectivity tests, Physical mode,
locking presets, the AI skill.
