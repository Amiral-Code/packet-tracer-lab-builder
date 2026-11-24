# Example gallery

Twelve labs ship with the builder (and as `ptlab recipes`). Each one passes the spec check and self-check, Packet
Tracer's own round trip with every value identical to Packet Tracer's, and the live check: Packet Tracer solves it
from the start state to full marks and every connectivity test, and its answer network passes on its own.

| Recipe | Example | Level | Kind | Time | What the student does |
|---|---|---|---|---|---|
| cabling-physical | `branch-cabling` | 1 | mixed | 25 min | patch a branch in the Physical view: straight-through vs crossover |
| soho-cable-internet | `home-cable-internet` | 1 | configure | 25 min | cable a home to an ISP over coax, finish the provider's DHCP |
| soho-wlan-wpa2 | `home-wlan-security` | 1 | configure | 20 min | rename and secure a home WLAN with WPA2-PSK, rejoin a laptop |
| static-routing | `static-two-sites` | 2 | configure | 30 min | address two sites, static and default routes |
| acl-vlan-ospf | `feature-probe` | 2 | configure | 30 min | VLANs, routing and an extended ACL that allows web only |
| serial-wan-ospf | `serial-wan-triangle` | 2 | configure | 40 min | three sites on serial lines: DCE clocking and OSPF |
| serial-cards | `serial-card-upgrade` | 2 | configure | 25 min | find a new card's interfaces and bring up a serial line |
| fiber-uplink | `fiber-campus-uplink` | 2 | configure | 30 min | patch fiber between SFP optics, route over a routed uplink |
| asa-edge | `asa-edge-firewall` | 2 | configure | 35 min | ASA interfaces, security levels, PAT, ACL, inspection |
| dual-stack-hardening | `feature-probe-2` | 3 | configure | 45 min | IPv6, DHCP, HSRP, PAT, device access, port security (scored per part) |
| troubleshoot-branch | `ts-branch-offline` | 3 | troubleshoot | 35 min | find and fix four stacked faults across three layers |
| enterprise-capstone | `northstar-enterprise-recovery` | 4 | mixed | 90 min | finish and repair a multi-site enterprise cutover |

Live-check results (unattended, final code) are recorded in `docs/research-evidence.md`.
