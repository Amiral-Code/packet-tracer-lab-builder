"""Topic recipes: proven labs to start from.

Every recipe is one of the shipped examples, each of which passes the spec check, Packet Tracer's own round trip
(items kept, values identical to Packet Tracer's) and the live check (Packet Tracer solves it from the start state
to full marks and every connectivity test). `ptlab new RECIPE OUT.toml` writes a fresh copy with new addressing and
its own id, ready to edit; the skill picks recipes by topic.
"""
from pathlib import Path

from . import variants

RECIPES = {
    # name: (example file, CCNA topics, level, kind, minutes, what the student does)
    "cabling-physical": ("branch-cabling", "1.3 cabling, Physical view", 1, "mixed", 25,
                         "patch a branch in the Physical view: straight-through vs crossover"),
    "structured-cabling": ("structured-cabling", "1.3 cabling, structured cabling", 1, "configure", 25,
                           "run desk-to-switch cabling through wall plates and a patch panel, jack by jack"),
    "soho-cable-internet": ("home-cable-internet", "1.2 SOHO, 1.3 coax, 4.3 DHCP", 1, "configure", 25,
                            "cable a home to an ISP over coax and finish the provider's DHCP"),
    "soho-wlan-wpa2": ("home-wlan-security", "1.11 wireless, 5.9 WPA2", 1, "configure", 20,
                       "rename and secure a home WLAN with WPA2-PSK and rejoin a laptop"),
    "static-routing": ("static-two-sites", "3.3 static and default routes", 2, "configure", 30,
                       "address two sites and route between them with static and default routes"),
    "acl-vlan-ospf": ("feature-probe", "5.6 ACLs, 2.1 VLANs, 3.3 routing", 2, "configure", 30,
                      "VLANs, routing and an extended ACL that allows web only"),
    "serial-wan-ospf": ("serial-wan-triangle", "1.3 serial, 3.4 OSPF", 2, "configure", 40,
                        "three sites on serial lines: DCE clocking and single-area OSPF"),
    "serial-cards": ("serial-card-upgrade", "1.1 router modules, 1.3 serial", 2, "configure", 25,
                     "find a new card's interfaces and bring up a serial line"),
    "fiber-uplink": ("fiber-campus-uplink", "1.3/1.6 fiber, SFP, routed ports", 2, "configure", 30,
                     "patch fiber between SFP optics and route across a routed uplink"),
    "asa-edge": ("asa-edge-firewall", "5.x firewall, 4.1 PAT", 2, "configure", 35,
                 "bring an ASA online: nameif, security levels, PAT, ACL, inspection"),
    "dual-stack-hardening": ("feature-probe-2", "1.8/1.9 IPv6, 3.4 OSPF, 4.x DHCP/NAT/HSRP, 5.x hardening", 3,
                             "configure", 45, "dual stack, DHCP, HSRP, PAT, device access and port security"),
    "troubleshoot-branch": ("ts-branch-offline", "1.10 troubleshooting, 3.3 routing", 3, "troubleshoot", 35,
                            "find and fix four stacked faults across three layers"),
    "enterprise-capstone": ("northstar-enterprise-recovery", "capstone: VLANs, LACP, RPVST, OSPF, DHCP, ACL, NAT, IPv6",
                            4, "mixed", 90, "finish and repair a multi-site enterprise cutover"),
}


def recipe_dir():
    """Installed wheels carry the examples as pt_lab_builder/recipes; a source checkout has them in examples/."""
    here = Path(__file__).resolve().parent
    for d in (here / "recipes", here.parent.parent / "examples"):
        if d.is_dir():
            return d
    raise FileNotFoundError("no recipe files (examples) found next to the package")


def new(name, out_path, seed="new"):
    """Write a fresh copy of a recipe: new private addressing (a variant), its own id derived from the file name."""
    example = RECIPES[name][0]
    text = (recipe_dir() / f"{example}.toml").read_text(encoding="utf-8")
    text = variants.make(text, 1, seed)
    out_path = Path(out_path)
    import re
    text = re.sub(r'(?m)^id = ".*"', f'id = "{out_path.stem}"', text, count=1)
    text = re.sub(r'(?m)^(title = ".*?) \(variant 01\)"$', r'\1"', text, count=1)
    out_path.write_text(text, encoding="utf-8")
    return out_path
