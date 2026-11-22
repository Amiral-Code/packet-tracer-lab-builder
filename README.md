# Packet Tracer Lab Builder

Build original Cisco Packet Tracer activities (`.pka`) from readable TOML specifications. A lab can contain a topology drawn from scratch, start and answer networks, multi-page instructions, hidden troubleshooting faults, Check Results items, an answer guide, and a basic Physical workspace.

This project is independent of Cisco. Cisco Packet Tracer and Cisco device data are not distributed here. You must install Packet Tracer and initialize a private local template library from `.pkt`/`.pka` files you are allowed to use.

## Current status

The project is an alpha. Logical topology generation, configuration/troubleshooting activities, instruction pages, basic grading, and single-building Physical placement work. Hierarchical multi-site Physical layouts and grading of rack placement or student-created cabling are planned, but are not yet implemented.

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
git clone https://github.com/OWNER/pt-lab-builder.git
cd pt-lab-builder
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
ptlab build examples/static-two-sites.toml --output-dir work
ptlab build examples/static-two-sites.toml --output-dir work --open
ptlab check examples/static-two-sites.toml work/student-saved.pka
ptlab models
```

The build command writes the activity and an `-answer.md` guide. Generated files and the private template library are intentionally ignored by Git.

Use source files from the same Packet Tracer generation your learners use. A `.pka` generated from newer device templates may not open in an older Packet Tracer release.

## Install the AI skill

The repository includes the same portable skill for Claude Code and Codex.

```bash
gh skill install OWNER/pt-lab-builder pt-lab-builder --agent claude-code --scope user
gh skill install OWNER/pt-lab-builder pt-lab-builder --agent codex --scope user
```

Manual installation:

- Claude Code: copy `skills/pt-lab-builder` to `~/.claude/skills/`
- Codex: copy it to `~/.agents/skills/`

Start a new agent session, then ask for a lab, for example:

> Create a 75-minute level-5 CCNA capstone combining VLANs, EtherChannel, RSTP, multi-area OSPF, DHCP relay, NAT, ACLs, IPv6, and six troubleshooting faults.

Packet Tracer covers CCNA well and part of ENCOR. Describe advanced activities as “CCIE-style,” not full CCIE simulations; technologies such as MPLS, VRFs, IS-IS, DMVPN, advanced BGP policy, SD-WAN, and real QoS behaviour need another platform.

## Physical mode

The generator removes ghost devices inherited from source templates, places routers/switches/controllers/servers into distinct rack positions, and distributes endpoints across the building. Specs can rename the inherited containers and override device placement:

```toml
[physical]
city = "Casablanca"
building = "Headquarters"
closet = "Main Distribution Frame"
rack = "Rack 1"

[[device]]
name = "CORE1"
model = "l3switch-3650"
physical = { location = "rack", slot = 2 }

[[device]]
name = "PC1"
model = "pc"
physical = { location = "building", x = 172, y = 215 }
```

See [the specification reference](skills/pt-lab-builder/references/spec-schema.md) and [Physical-mode boundaries](skills/pt-lab-builder/references/physical-mode.md).

## Development

Run the standard-library test suite:

```bash
python -m unittest discover -s tests -v
```

The repository deliberately contains no extracted Cisco or course assets. Integration tests use paths supplied through environment variables.

## Before publishing

Choose and add an open-source license for your original code. Do not commit extracted Packet Tracer device XML, third-party course files, generated activities containing third-party content, or other material unless you have confirmed redistribution rights.
