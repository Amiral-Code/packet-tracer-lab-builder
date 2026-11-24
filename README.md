# Packet Tracer Lab Builder

Build original Cisco Packet Tracer activities (`.pka`) from readable TOML specifications. A lab can contain a topology drawn from scratch, configure, troubleshoot, or mixed student states, start and answer networks, multi-page instructions, hidden troubleshooting faults, Check Results items, an answer guide, and a basic Physical workspace.

This project is independent of Cisco. Cisco Packet Tracer and Cisco device data are not distributed here. You must install Packet Tracer and initialize a private local template library from `.pkt`/`.pka` files you are allowed to use.

## Current status

Version 0.2.0 (alpha). Configure, troubleshooting and mixed activities with Check Results grading (addresses,
IPv4/IPv6, interface state, VLANs and trunks, routing, OSPF, STP, port security, NAT, ACLs, HSRP, DHCP, device
access, ASA interfaces and objects, wireless WLANs, any running-config line, several right answers, per-part scores)
and connectivity tests (ping, ping6, TCP services, UDP delivery). Devices include IOS routers and switches with
serial, fiber and switch cards, ASA firewalls, home routers, modems, clouds, access points and wireless hosts.
Physical mode, timers, locking and student cabling labs work.

Every example is proven in Packet Tracer itself: kept and value-identical through Packet Tracer's own save, and
solved by Packet Tracer from its start state to full marks (the live check). See `docs/examples.md`,
`docs/instructors.md` and `CHANGELOG.md`; contributors start with `docs/contributing.md`.

## Requirements

- Cisco Packet Tracer on Windows, Linux, or macOS
- Python 3.11 or newer
- A C++17 compiler, Crypto++, and zlib development files
- A folder containing your own compatible `.pkt` and at least one `.pka` file, used locally to derive clean device and activity templates

Typical native dependencies:

- Ubuntu/Debian: `sudo apt install g++ libcrypto++-dev zlib1g-dev`
- macOS with Homebrew: `brew install python cryptopp zlib`
- Windows: install Python and MSYS2, then install the MinGW C++ compiler, Crypto++, and zlib packages; place the MinGW `bin` directory on `PATH`

## Install

Clone the repository and install it into an isolated Python environment:

```bash
git clone https://github.com/Amiral-Code/packet-tracer-lab-builder.git
cd packet-tracer-lab-builder
python -m pip install .
```

Initialize the native codec and private template library. `--source` is repeatable:

```bash
ptlab init --build-codec --source "/path/to/your/packet-tracer-files"
ptlab doctor
```

Nothing is uploaded. Extracted templates stay in the operating system's application-data directory:

- Linux: `${XDG_DATA_HOME:-~/.local/share}/pt-lab-builder`
- macOS: `~/Library/Application Support/pt-lab-builder`
- Windows: `%LOCALAPPDATA%\pt-lab-builder`

Use `PTLAB_DATA_DIR`, `PTLAB_LIBRARY_DIR`, `PTLAB_PTCRYPT`, or `PTLAB_PACKET_TRACER` to override discovery.

## Build and grade a lab

```bash
ptlab lint examples/static-two-sites.toml
ptlab build examples/static-two-sites.toml --output-dir work
ptlab build examples/static-two-sites.toml --output-dir work --open
ptlab check examples/static-two-sites.toml work/student-saved.pka
ptlab models
```

`ptlab lint` checks the spec (ports, cabling, addressing, gateways, grade statements) and then proves the lab against itself: the answer network must score 100 % on the lab's own grade statements, and every hidden fault, applied alone, must make at least one graded item fail. `ptlab build` runs the same checks first and refuses to write a lab that fails them (`--force` overrides). The build command writes the activity and an `-answer.md` guide. Generated files and the private template library are intentionally ignored by Git.

Grading is native Packet Tracer Check Results: addresses (IPv4 and IPv6), interface state, gateways, VLANs and
trunks, static/OSPF routing, port security, PortFast, NAT, ACL placement, HSRP, DHCP pools, enable secrets, local
users, banners, descriptions, any running-config line, cables, and connectivity tests (ping, ping6, TCP services,
UDP delivery, including traffic that must be blocked). Where a task leaves a choice, items accept every right answer: any host
address in a subnet, either of two gateways, a description that mentions a word.

Prove a built lab the way Packet Tracer reads it: open it in Packet Tracer, save a copy, then

```bash
ptlab verify SPEC.toml SAVED.pka                        # items and tests Packet Tracer kept, local checks
ptlab bare work/lab.pka work/lab-bare.pka               # open + save this copy too, then:
ptlab verify SPEC.toml SAVED.pka --values work/lab-bare.pka   # every value equals Packet Tracer's own
```

One file per student and a class report:

```bash
ptlab variants SPEC.toml --count 30 --output-dir work/class --build   # 30 re-addressed labs + answer keys
ptlab grade work/class submitted/                                   # grades.csv + grades.html
```

Then let Packet Tracer solve the lab itself: `ptlab live-prepare` copies the activity with a script (Packet Tracer's
own JavaScript engine and API) that records the start score, adds the student's cables, types every answer
configuration at each device's console, sets host addresses, waits, and records Check Results and the Connectivity
Tests (run twice, as a student would) in a JSON report; `ptlab live-report` gives the verdict: no full marks at the
start, full marks after solving. Open the copy with any harness that accepts Packet Tracer's script-privilege
prompt; the author's Hyprland harness is `pt-live-check.sh` (opens it hidden, presses Enter on the prompt, closes
only its own Packet Tracer).

```bash
ptlab live-prepare SPEC.toml work/lab.pka work/lab-live.pka /abs/lab-live.json --save /abs/lab-solved.pka
ptlab live-report SPEC.toml /abs/lab-live.json
```

Use source files from the same Packet Tracer generation your learners use. A `.pka` generated from newer device templates may not open in an older Packet Tracer release.

## Install the AI skill

The repository includes the same portable skill for Claude Code and Codex.

```bash
gh skill install Amiral-Code/packet-tracer-lab-builder pt-lab-builder --agent claude-code --scope user
gh skill install Amiral-Code/packet-tracer-lab-builder pt-lab-builder --agent codex --scope user
```

Manual installation:

- Claude Code: copy `skills/pt-lab-builder` to `~/.claude/skills/`
- Codex: copy it to `~/.agents/skills/`

Start a new agent session, then ask for a lab, for example:

> Create a 75-minute level-5 CCNA capstone combining VLANs, EtherChannel, RSTP, multi-area OSPF, DHCP relay, NAT, ACLs, IPv6, and six troubleshooting faults.

Packet Tracer covers CCNA well and part of ENCOR. Describe advanced activities as “CCIE-style,” not full CCIE simulations; technologies such as MPLS, VRFs, IS-IS, DMVPN, advanced BGP policy, SD-WAN, and real QoS behaviour need another platform.

## Physical mode

Each `[[site]]` becomes its own building, wiring closet and rack, in its own city when the city name differs. Rack equipment is stacked from the top by real model height (measured in Packet Tracer 9.0.1), endpoints are placed on the building floor, and `ptlab lint` rejects a rack that overflows.

```toml
[[site]]
name = "HQ"
city = "Casablanca"
building = "Northstar HQ"
devices = ["HQ-EDGE", "CORE1", "HQ-SW1", "HQ-PC1"]

[[site]]
name = "Branch"
city = "Rabat"
devices = ["BR-R1", "BR-SW1", "BR-PC1"]
```

**Cabling labs:** a link marked `student = true` is missing from the start network. Packet Tracer grades it through Port Up on both ends (add `ping` tests for the end-to-end result), and `ptlab check` verifies the cable's ports and type in the saved file. See `examples/branch-cabling.toml`.

See [the specification reference](skills/pt-lab-builder/references/spec-schema.md) and [Physical mode](skills/pt-lab-builder/references/physical-mode.md).

For everything Packet Tracer activities can do, and what the builder uses so far, see [Packet Tracer capabilities](docs/packet-tracer-capabilities.md). The plan to finish the project is in [the roadmap](docs/roadmap.md).

## Development

Run the standard-library test suite:

```bash
PYTHONPATH=src:tests python -m unittest discover -s tests -v
```

The repository deliberately contains no extracted Cisco or course assets. Integration tests use paths supplied through environment variables.

## License and content boundary

The original code and skill are licensed under Apache-2.0. Cisco Packet Tracer, Cisco device data, third-party course files, and generated activities containing third-party content are not covered by this repository's license. Do not commit or redistribute those materials unless you have confirmed that you have the necessary rights.
