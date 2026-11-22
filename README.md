# Packet Tracer Lab Builder

Build original Cisco Packet Tracer activities (`.pka`) from readable TOML specifications. A lab can contain a topology drawn from scratch, configure, troubleshoot, or mixed student states, start and answer networks, multi-page instructions, hidden troubleshooting faults, Check Results items, an answer guide, and a basic Physical workspace.

This project is independent of Cisco. Cisco Packet Tracer and Cisco device data are not distributed here. You must install Packet Tracer and initialize a private local template library from `.pkt`/`.pka` files you are allowed to use.

## Current status

The project is an alpha. Logical topology generation, configuration/troubleshooting activities, instruction pages,
grading (addresses, interface state, VLANs, access and trunk ports, static and OSPF routes, STP priority, any
running-config line, ICMP reachability, and TCP service outcomes), weighted partial credit, and Physical placement work. Activities can use
elapsed/countdown timing, answer-convergence delay, custom overall feedback, profile locking, and an Activity Wizard
password. Multi-site Physical layouts and student cabling labs work; grading of rack position is not implemented.

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
PYTHONPATH=src python -m unittest discover -s tests -v
```

The repository deliberately contains no extracted Cisco or course assets. Integration tests use paths supplied through environment variables.

## License and content boundary

The original code and skill are licensed under Apache-2.0. Cisco Packet Tracer, Cisco device data, third-party course files, and generated activities containing third-party content are not covered by this repository's license. Do not commit or redistribute those materials unless you have confirmed that you have the necessary rights.
