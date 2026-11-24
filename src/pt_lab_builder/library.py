#!/usr/bin/env python3
"""Build a private local device/template library from user-supplied Packet Tracer files."""
import copy
import glob
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from .paths import codec_path, library_dir
WANT = {  # (TYPE, model) -> library key
    ("Router", "2911"): "router-2911", ("Router", "ISR4331"): "router-isr4331",
    ("Router", "ISR4321"): "router-isr4321", ("Router", "1941"): "router-1941",
    ("Router", "1841"): "router-1841",
    ("Router", "2901"): "router-2901", ("Router", "2811"): "router-2811", ("Router", "Router-PT"): "router-pt",
    ("Router", "Router-PT-Empty"): "router-pt-empty",
    ("Switch", "2960-24TT"): "switch-2960", ("MultiLayerSwitch", "3560-24PS"): "l3switch-3560",
    ("MultiLayerSwitch", "3650-24PS"): "l3switch-3650",
    ("Pc", "PC-PT"): "pc", ("Laptop", "Laptop-PT"): "laptop", ("Server", "Server-PT"): "server",
    ("Printer", "Printer-PT"): "printer", ("IpPhone", "7960"): "ipphone-7960", ("Cloud", "Cloud-PT"): "cloud",
    ("Hub", "Hub-PT"): "hub", ("AccessPoint", "AccessPoint-PT"): "ap", ("LightWeightAccessPoint", "LAP-PT"): "lap",
    ("WirelessLanController", "WLC-3504"): "wlc-3504", ("WirelessLanController", "WLC-2504"): "wlc-2504",
    ("WirelessRouter", "Linksys-WRT300N"): "wrt300n", ("TabletPC", "TabletPC-PT"): "tablet",
    ("Pda", "SMARTPHONE-PT"): "smartphone",
    ("WirelessRouterNewGeneration", "HomeRouter-PT-AC"): "home-router",
    ("CableModem", "Cable-Modem-PT"): "cable-modem", ("DslModem", "DSL-Modem-PT"): "dsl-modem",
    ("CoAxialSplitter", "CoAxialSplitter-PT"): "coax-splitter",
    ("CentralOfficeServer", "Central-Office-Server"): "central-office", ("CellTower", "Cell-Tower"): "cell-tower",
    ("ASA", "5506-X"): "asa-5506x", ("ASA", "5505"): "asa-5505",
    ("AccessPoint", "AccessPoint-PT-N"): "ap-n", ("AccessPoint", "AccessPoint-PT-AC"): "ap-ac",
    ("LightWeightAccessPoint", "3702i"): "lap-3702i",
    ("Patch Panel", "Copper Patch Panel"): "patch-panel", ("Wall Mount", "Copper Wall Mount"): "wall-mount",
}
# Packet Tracer stores no port names: it derives them per model. Names for devices without an IOS
# configuration, as they appear on links in real files (the user's activities and Packet Tracer's samples).
PORT_NAMES = {
    "Linksys-WRT300N": ["Internet", "Ethernet 1", "Ethernet 2", "Ethernet 3", "Ethernet 4"],
    "HomeRouter-PT-AC": ["Internet", "GigabitEthernet 1", "GigabitEthernet 2", "GigabitEthernet 3",
                         "GigabitEthernet 4"],
    "Cable-Modem-PT": ["Port 0", "Port 1"],        # Port 0 coax, Port 1 Ethernet
    "DSL-Modem-PT": ["Port 0", "Port 1"],          # Port 0 phone line, Port 1 Ethernet
    "CoAxialSplitter-PT": ["Coaxial0", "Coaxial1", "Coaxial2"],
    "Cloud-PT": ["Serial0", "Serial1", "Serial2", "Serial3", "Modem4", "Modem5", "Ethernet6", "Coaxial7"],
    "Central-Office-Server": ["Backbone", "Coaxial0/0", "Coaxial0/1", "Coaxial0/2", "Coaxial0/3", "Coaxial0/4",
                              "Coaxial0/5"],
    "Cell-Tower": ["Coaxial0"],
    # access points: the Ethernet port is "Port 0" (links in the user's files; the library had FastEthernet0)
    "AccessPoint-PT": ["Port 0"], "AccessPoint-PT-N": ["Port 0"], "AccessPoint-PT-AC": ["Port 0"],
    "3702i": ["GigabitEthernet0"], "LAP-PT": ["GigabitEthernet0"],
    # WLC data ports count from 1 (Packet Tracer's own WLC samples and NetAcad cable GigabitEthernet1)
    "WLC-3504": ["GigabitEthernet1", "GigabitEthernet2", "GigabitEthernet3"],
    "WLC-2504": ["GigabitEthernet1", "GigabitEthernet2", "GigabitEthernet3", "GigabitEthernet4"],
    # structured cabling (NetAcad 1.1.4): jacks at the front, punch-downs at the back
    "Copper Patch Panel": [f"Jack{i}" for i in range(1, 25)] + [f"PunchDown{i}" for i in range(1, 25)],
    "Copper Wall Mount": [f"Jack{i}" for i in range(1, 5)] + [f"PunchDown{i}" for i in range(1, 5)],
    "5506-X": [f"GigabitEthernet1/{i}" for i in range(1, 9)] + ["Management1/1"],
    "5505": [f"Ethernet0/{i}" for i in range(8)],
}
IOS_TYPES = ("Router", "Switch", "MultiLayerSwitch")
# Routers with interface cards already fitted, taken whole from the user's own files: Packet Tracer stores a card as
# a MODULE in the router's slot tree with its own ports, so copying a real fitted router keeps that tree exactly.
# (TYPE, model, sorted card models) -> library key. Plain WANT keys only take routers with no card fitted.
VARIANTS = {
    ("Router", "1941", ("HWIC-2T",)): "router-1941-serial",
    ("Router", "2911", ("HWIC-2T",)): "router-2911-serial",
    ("Router", "1841", ("WIC-2T",)): "router-1841-serial",
    ("Router", "ISR4321", ("NIM-2T",)): "router-isr4321-serial",
    ("Router", "ISR4331", ("NIM-2T",)): "router-isr4331-serial",
}
# Devices whose optics (SFP modules in their uplink slots) make fiber ports usable, also taken whole:
# (TYPE, model, sorted card models, sorted SFP models) -> library key. Checked before VARIANTS.
SFP_VARIANTS = {
    ("Router", "2911", ("HWIC-1GE-SFP",), ("GLC-LH-SMD",)): "router-2911-sfp",          # fiber G0/0/0
    ("MultiLayerSwitch", "3650-24PS", (), ("GLC-LH-SMD",) * 3): "l3switch-3650-fiber",  # fiber G1/1/1-3
}
EMPTY_CARDS = ("WIC-Cover", "NIM-Cover")


def sfp_modules(device):
    return tuple(sorted(m.findtext("MODEL") for m in device.iter("MODULE")
                        if m.findtext("TYPE") == "eSfpModule" and m.findtext("MODEL")))


def interface_cards(device):
    """Sorted models of the removable interface cards fitted in a device (blank covers excluded)."""
    return tuple(sorted(m.findtext("MODEL") for m in device.iter("MODULE")
                        if m.findtext("TYPE") == "eInterfaceCard" and m.findtext("MODEL") not in EMPTY_CARDS))


# Generic "-PT" devices take any network modules; their plain template must keep Packet Tracer's stock fit
STOCK_PT_MODULES = {
    "Router-PT": ("PT-ROUTER-NM-1CFE", "PT-ROUTER-NM-1CFE", "PT-ROUTER-NM-1FFE", "PT-ROUTER-NM-1FFE",
                  "PT-ROUTER-NM-1S", "PT-ROUTER-NM-1S"),
    "Cloud-PT": ("PT-CLOUD-NM-1AM", "PT-CLOUD-NM-1AM", "PT-CLOUD-NM-1CE", "PT-CLOUD-NM-1CX",
                 "PT-CLOUD-NM-1S", "PT-CLOUD-NM-1S", "PT-CLOUD-NM-1S", "PT-CLOUD-NM-1S"),
}


def pt_modules(device):
    return tuple(sorted(m.findtext("MODEL") for m in device.iter("MODULE")
                        if (m.findtext("TYPE") or "").startswith("ePt") and m.findtext("MODEL")
                        and not m.findtext("MODEL").endswith("-COVER")))


HOME_ROUTER_TYPES = ("WirelessRouter", "WirelessRouterNewGeneration")


def stock_home_router(device):
    """Packet Tracer's out-of-the-box home router: Internet by DHCP (type 0), LAN 192.168.0.1, DHCP pool from .100.
    Copies changed by an activity's author (blank or static addresses) are not usable as a template."""
    e = device.find("ENGINE")
    internet = next((p for p in device.iter("PORT") if p.find("PORT_DHCP_ENABLE") is not None), None)
    ssids = {s.text for w in device.iter("WIRELESS_SERVER") for s in w.iter("SSID")}
    return (e.findtext("INTERNET_CONNECTION_TYPE") == "0" and e.findtext("LAN_IP_ADDRESS") == "192.168.0.1"
            and e.findtext("DHCP_SERVER/POOLS/POOL/START_IP") == "192.168.0.100"
            and internet is not None and internet.findtext("PORT_DHCP_ENABLE") == "true" and ssids <= {"Default"})


def library_key(device):
    t = device.find("ENGINE/TYPE")
    if t is None:
        return None
    cards = interface_cards(device)
    sfp = SFP_VARIANTS.get((t.text, t.get("model"), cards, sfp_modules(device)))
    if sfp:
        return sfp
    if cards:
        return VARIANTS.get((t.text, t.get("model"), cards))
    stock = STOCK_PT_MODULES.get(t.get("model"))
    if stock is not None and pt_modules(device) != stock:
        return None
    if t.text in HOME_ROUTER_TYPES and not stock_home_router(device):
        return None
    return WANT.get((t.text, t.get("model")))


def load(path):
    with tempfile.TemporaryDirectory() as t:
        x = os.path.join(t, "a.xml")
        if subprocess.run([str(codec_path()), "decode", str(path), x], capture_output=True).returncode:
            return None
        s = open(x, "rb").read().decode("utf-8", "replace")
    try:
        return ET.fromstring(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s))
    except ET.ParseError:
        return None


def strip_user_apps(device):
    """Remove installed desktop-app folders (a directory holding an app_manifest.xml).
    Packet Tracer compares each one with its own built-in copy (CDevice::hasOutdatedUserApps) and
    asks the 'outdated user applications' question when the file's copy is older."""
    parent = {c: p for p in device.iter() for c in p}
    removed = 0
    for f in list(device.iter("FILE")):
        if f.findtext("NAME") == "app_manifest.xml" and f in parent:
            folder = parent[f]
            while folder is not None and folder.get("class") != "CDirectory" and folder in parent:
                folder = parent[folder]
            if folder is not None and folder in parent:
                parent[folder].remove(folder)
                removed += 1
    return removed


def factory_config(device, kind):
    """A factory-default running-config for a router or switch, from its own interface list.
    Packet Tracer re-parses this text when it opens the file, so it resets the IOS state."""
    lines = [l.text or "" for l in device.findall("ENGINE/RUNNINGCONFIG/LINE")]
    version = next((l for l in lines if l.startswith("version ")), "version 15.1")
    license = [l for l in lines if l.startswith("license udi ")]
    phys = [l.split(None, 1)[1] for l in lines if l.startswith("interface ")]
    phys = [i for i in phys if "." not in i and not i.startswith(("Vlan", "Loopback", "Tunnel", "Port-channel"))]
    out = ["!", version, "no service timestamps log datetime msec", "no service timestamps debug datetime msec",
           "no service password-encryption", "!"]
    if kind == "router":
        out += ["hostname Router", "!", "ip cef", "no ipv6 cef", "!"] + license + ["!"]
        for i in phys:
            out += [f"interface {i}", " no ip address"]
            if i.startswith("Serial"):
                out += [" clock rate 2000000"]
            elif not i.startswith("GigabitEthernet0/0/"):
                out += [" duplex auto", " speed auto"]
            out += [" shutdown", "!"]
        out += ["interface Vlan1", " no ip address", " shutdown", "!", "ip classless", "!",
                "ip flow-export version 9", "!", "line con 0", "!", "line aux 0", "!", "line vty 0 4", " login", "!", "end", ""]
    else:
        out += ["hostname Switch", "!", "spanning-tree mode pvst", "spanning-tree extend system-id", "!"]
        for i in phys:
            out += [f"interface {i}", "!"]
        out += ["interface Vlan1", " no ip address", " shutdown", "!", "line con 0", "!",
                "line vty 0 4", " login", "line vty 5 15", " login", "!", "end", ""]
    return out


DEFAULT_VLANS = {"1", "1002", "1003", "1004", "1005"}


def factory_reset(device, kind):
    """Reset a template to factory state: IOS configuration, VLAN database, saved addresses."""
    eng = device.find("ENGINE")
    if kind in ("router", "switch"):
        new = factory_config(device, kind)          # read the interface list before clearing
        for tag in ("RUNNINGCONFIG", "STARTUPCONFIG"):
            e = eng.find(tag)
            if e is not None:
                for l in list(e):
                    e.remove(l)
        for text in new:
            ET.SubElement(eng.find("RUNNINGCONFIG"), "LINE").text = text
        vl = eng.find("VLANS")
        if vl is not None:
            for v in list(vl):
                if v.get("number") not in DEFAULT_VLANS:
                    vl.remove(v)
    if kind == "home":                               # keep the stock settings (Internet port is a DHCP client)
        return eng
    if kind == "asa":   # an ASA saved unconfigured has no running-config lines at all: start from that state
        for tag in ("RUNNINGCONFIG", "STARTUPCONFIG"):
            if eng.find(tag) is not None:
                for l in list(eng.find(tag)):
                    eng.find(tag).remove(l)
    for p in device.iter("PORT"):                    # saved addresses and descriptions on every port and host
        for tag in ("IP", "SUBNET", "PORT_GATEWAY", "PORT_DNS", "DESCRIPTION"):
            if p.find(tag) is not None:
                p.find(tag).text = ""
        if p.find("PORT_DHCP_ENABLE") is not None:
            p.find("PORT_DHCP_ENABLE").text = "false"
    if eng.find("GATEWAY") is not None:
        eng.find("GATEWAY").text = ""
    if kind == "wlc":   # no WLANs, joined APs, dynamic interfaces or RADIUS servers; its day-0 DHCP server off
        ac = eng.find("CAPWAP_AC")
        for path in ("WLANS", "APS", "RADIUS_SERVERS", "AP_GROUPS/AP_GROUP/WLANS"):
            for holder in ac.findall(path):
                for c in list(holder):
                    holder.remove(c)
        wi = eng.find("WLC_INTERFACES")
        for p in list(wi.findall("PORT")):
            if p.findtext("NAME") not in ("management", "virtual"):
                wi.remove(p)
            elif p.findtext("NAME") == "virtual":     # the fixed virtual address, as every sample has it
                p.find("IP").text, p.find("SUBNET").text = "192.0.2.1", "255.255.255.255"
            elif p.find("DHCP_SERVER_IP") is not None:
                p.find("DHCP_SERVER_IP").text = "0.0.0.0"
        # DHCP: keep only the factory day-0 pool (192.168.1.0/28); a sample's own pools go. Packet Tracer reports the
        # server enabled whatever ENABLED says, so the pools are what matters. The WLC saves DHCP_SERVERS twice.
        for pools in eng.findall("DHCP_SERVERS/ASSOCIATED_PORTS/ASSOCIATED_PORT/DHCP_SERVER/POOLS"):
            for pool in list(pools):
                if pool.findtext("NAME") != "day0-dhcp-mgmt":
                    pools.remove(pool)
    if kind == "lap":   # an AP keeps a copy of the WLANs it last learned; it always takes its address by DHCP
        for holder in eng.findall("CAPWAP/WLANS"):
            for c in list(holder):
                holder.remove(c)
        if eng.find("CAPWAP/PRIMARY_AC") is not None:
            eng.find("CAPWAP/PRIMARY_AC").text = "0.0.0.0"
        for p in device.iter("PORT"):
            if p.find("PORT_DHCP_ENABLE") is not None:
                p.find("PORT_DHCP_ENABLE").text = "true"
    for prof in device.iter("WIRELESS_PROFILE"):     # a sample's wireless profile may carry a static address
        for tag in ("IP_ADDRESS", "SUBNET_MASK", "DEFAULT_GATEWAY", "DNS"):
            if prof.find(tag) is not None:
                prof.find(tag).text = ""
        if prof.find("DHCP_ENABLED") is not None:
            prof.find("DHCP_ENABLED").text = "1"
    for tag in ("MODEM_CONNECTION_TYPES", "MODEM_CONNECTIONS", "PHONE_CONNECTIONS", "CONNECTIONS"):
        if eng.find(tag) is not None:            # a Cloud's mappings from its source file
            for c in list(eng.find(tag)):
                eng.find(tag).remove(c)
    return eng


def vkey(v):
    return tuple(int(p) for p in re.findall(r"\d+", v or "0"))


def network_roots(root):
    if root.tag == "PACKETTRACER5":
        return [root]
    if root.tag == "PACKETTRACER5_ACTIVITY":
        return root.findall("PACKETTRACER5")
    return []


def _has_usable_physical_workspace(root):
    """A base topology needs a PC to copy a physical node from, and the full
    building (2) / wiring closet (3) / rack (4) hierarchy that devices are placed into.
    Industrial or home samples often lack the rack, which made every router/switch fail."""
    pc = next((d for d in root.findall("NETWORK/DEVICES/DEVICE")
               if d.findtext("ENGINE/TYPE") == "Pc" and d.findtext("WORKSPACE/PHYSICAL")), None)
    workspace = root.find("PHYSICALWORKSPACE")
    if pc is None or workspace is None:
        return False
    kinds = {node.findtext("TYPE") for node in workspace.iter("NODE")}
    return {"2", "3", "4"} <= kinds


def _write_activity_base(activity, destination):
    locking = activity.find("LOCKINGTREE")
    options = activity.find("OPTIONS")
    if locking is None or options is None:
        return False
    container = ET.Element("PKA_CONTAINER")
    container.append(copy.deepcopy(locking))
    container.append(copy.deepcopy(options))
    ET.indent(container, space=" ")
    ET.ElementTree(container).write(destination, encoding="utf-8", short_empty_elements=False)
    return True


def _prune_physical_devices(root, template_uuid):
    referenced = {template_uuid}
    for device in root.findall("NETWORK/DEVICES/DEVICE"):
        referenced.update(part for part in (device.findtext("WORKSPACE/PHYSICAL") or "").split(",") if part)
    parents = {child: parent for parent in root.iter() for child in parent}
    for node in list(root.findall(".//NODE")):
        if node.findtext("TYPE") == "6" and node.findtext("UUID_STR") not in referenced:
            parents[node].remove(node)


# -------------------------------------------------------------- interface cards for empty slots
PORT_STEMS = {"eSmartSerial": "Serial", "eSerial": "Serial", "eCopperGigabitEthernet": "GigabitEthernet",
              "eFiberGigabitEthernet": "GigabitEthernet", "eGigabitEthernet": "GigabitEthernet",
              "eCopperFastEthernet": "FastEthernet", "eFiberFastEthernet": "FastEthernet", "eCopperEthernet": "Ethernet"}


def card_bays(device):
    """Bay number of each interface-card slot, in slot order, and whether it is empty. On ISR 4000 routers the NIM bays
    are 0/1 and 0/2 (bay 0 is the built-in ports); on 1841/1941/2811/2911 the HWIC/WIC slots are 0/0, 0/1, ...
    (seen in the user's files: ISR4321 NIM-2T -> Serial0/1/x, 1941 HWIC-2T -> Serial0/0/x, 2911 HWIC-1GE-SFP ->
    GigabitEthernet0/0/0)."""
    model = device.find("ENGINE/TYPE").get("model") or ""
    offset = 1 if model.startswith("ISR4") else 0
    slots = [sl for sl in device.iter("SLOT") if sl.findtext("TYPE") == "eInterfaceCard"]
    out = []
    for i, sl in enumerate(slots):
        mod = sl.find("MODULE")
        empty = mod is None or mod.findtext("MODEL") in EMPTY_CARDS
        out.append((i + offset, empty))
    return out


def card_port_names(card, bay):
    """Port names of a card in a bay: Serial0/1/0, Serial0/1/1, ..."""
    names, count = [], {}
    for p in card.findall("PORT"):
        stem = PORT_STEMS.get(p.findtext("TYPE") or "")
        if stem:
            names.append(f"{stem}0/{bay}/{len(names)}")
    return names


def build(sources, destination=None, extra_sources=()):
    """Create local templates from .pkt/.pka files the user is allowed to use. Extra sources only fill models that
    no regular source has (so a new sample file cannot replace a proven template)."""
    destination = Path(destination or library_dir())
    devices_out = destination / "devices"
    files = []
    for rank, source in enumerate(list(sources) + list(extra_sources)):
        source = Path(source)
        label = source.name or f"source-{rank + 1}"
        for extension in ("*.pkt", "*.pka"):
            for filename in glob.glob(str(source / "**" / extension), recursive=True):
                files.append((rank, label, Path(filename)))
    if not files:
        raise RuntimeError("no .pkt or .pka files found under the supplied source folders")
    found = {}
    cards = {}
    base = None
    activity_base = None
    n_regular = len(list(sources))
    for rank, label, filename in files:
        root = load(filename)
        if root is None:
            continue
        extra = rank >= n_regular              # an extra source never wins over a regular one
        if extra:
            # only its device templates count, never its base topology or activity
            for network in network_roots(root):
                version = network.findtext("VERSION") or root.findtext("VERSION") or "0"
                for device in network.findall("NETWORK/DEVICES/DEVICE"):
                    key = library_key(device)
                    # regular sources come first in `files`, so this only fills models they lack
                    if key and key not in found:
                        found[key] = ((vkey(version), -rank), copy.deepcopy(device), label, filename, version)
            continue
        if root.tag == "PACKETTRACER5_ACTIVITY" and root.find("LOCKINGTREE") is not None:
            score = (vkey(root.findtext("VERSION")), -rank)
            if activity_base is None or score > activity_base[0]:
                activity_base = (score, copy.deepcopy(root), filename)
        for network in network_roots(root):
            version = network.findtext("VERSION") or root.findtext("VERSION") or "0"
            score = (vkey(version), -rank)
            if _has_usable_physical_workspace(network) and (base is None or score > base[0]):
                base = (score, copy.deepcopy(network), filename)
            for device in network.findall("NETWORK/DEVICES/DEVICE"):
                key = library_key(device)
                if key and (key not in found or score > found[key][0]):
                    found[key] = (score, copy.deepcopy(device), label, filename, version)
                chassis = device.find("ENGINE/TYPE").get("model") if device.find("ENGINE/TYPE") is not None else None
                for mod in device.iter("MODULE"):        # interface cards, for empty slots of other routers
                    card = mod.findtext("MODEL")
                    if mod.findtext("TYPE") != "eInterfaceCard" or not card or card in EMPTY_CARDS:
                        continue
                    entry = cards.setdefault(card, {"chassis": set(), "best": None})
                    entry["chassis"].add(chassis)
                    if entry["best"] is None or score > entry["best"][0]:
                        entry["best"] = (score, copy.deepcopy(mod), filename.name)
    if not found:
        raise RuntimeError("no supported Packet Tracer device models were found")
    if base is None:
        raise RuntimeError("no source file contained both a PC and a usable Physical workspace")
    devices_out.mkdir(parents=True, exist_ok=True)
    index = {}
    for key, (_, device, label, filename, version) in sorted(found.items()):
        d = device
        ifaces = [l.text.split(None, 1)[1] for l in d.findall("ENGINE/RUNNINGCONFIG/LINE")
                  if l.text and l.text.startswith("interface ")]
        model = d.find("ENGINE/TYPE").get("model")
        if model in PORT_NAMES and d.find("ENGINE/TYPE").text == "ASA":
            ifaces = list(PORT_NAMES[model])            # physical ports only (Vlan/Management from config)
        if not ifaces and model in PORT_NAMES:
            ifaces = list(PORT_NAMES[model])
        if not ifaces:  # hosts have no IOS config: name the ports from their card types
            names = {"eCopperFastEthernet": "FastEthernet", "eCopperGigabitEthernet": "GigabitEthernet",
                     "eHostWirelessG": "Wireless", "eHostWirelessN": "Wireless", "eHostWirelessAC": "Wireless",
                     "eFiberFastEthernet": "FastEthernet", "eFiberGigabitEthernet": "GigabitEthernet"}
            count = {}
            for pt in d.iter("PORT"):
                stem = names.get(pt.findtext("TYPE") or "")
                if stem:
                    ifaces.append(f"{stem}{count.get(stem, 0)}")
                    count[stem] = count.get(stem, 0) + 1
        strip_user_apps(d)
        ty = d.find("ENGINE/TYPE").text
        factory_reset(d, "router" if ty == "Router" else "switch" if ty in ("Switch", "MultiLayerSwitch")
                      else "home" if ty in HOME_ROUTER_TYPES else "asa" if ty == "ASA"
                      else "wlc" if ty == "WirelessLanController" else "lap" if ty == "LightWeightAccessPoint"
                      else "host")
        ET.ElementTree(d).write(devices_out / (key + ".xml"), encoding="utf-8")
        ifaces = [i for i in ifaces if "." not in i and (not i.startswith("Vlan") or i == "Vlan1")]
        index[key] = {"type": d.find("ENGINE/TYPE").text, "model": d.find("ENGINE/TYPE").get("model"),
                      "ios": d.find("ENGINE/TYPE").text in IOS_TYPES,
                      "version": version, "source": label, "file": filename.name, "interfaces": ifaces}
        print(f"{key:18} {index[key]['model']:16} {version:12} {label:22} {len(ifaces)} interfaces")
    # interface cards: one clean copy of each, and the chassis models it was found in
    (devices_out / "cards").mkdir(exist_ok=True)
    card_index = {}
    for card, entry in sorted(cards.items()):
        _, mod, source_file = entry["best"]
        for p in mod.iter("PORT"):                   # saved addresses and descriptions of the source lab
            for tag in ("IP", "SUBNET", "DESCRIPTION", "PORT_GATEWAY"):
                if p.find(tag) is not None:
                    p.find(tag).text = ""
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", card)
        ET.ElementTree(mod).write(devices_out / "cards" / f"{safe}.xml", encoding="utf-8")
        card_index[card] = {"file": f"cards/{safe}.xml", "chassis": sorted(entry["chassis"]), "source": source_file,
                            "ports": [p.findtext("TYPE") for p in mod.findall("PORT")]}
        print(f"card {card:16} fits {', '.join(sorted(entry['chassis']))}")
    with open(devices_out / "cards.json", "w", encoding="utf-8") as fh:
        json.dump(card_index, fh, indent=1)
    for key, item in index.items():                  # empty card bays of each template
        d = ET.parse(devices_out / (key + ".xml")).getroot()
        item["card_bays"] = [bay for bay, empty in card_bays(d) if empty]
    with open(devices_out / "index.json", "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=1)
    # empty base topology: keep the physical workspace (one container path + a device node template)
    _, r, filename = base
    devs = r.find("NETWORK/DEVICES")
    keep = next(d for d in devs if d.find("ENGINE/TYPE").text == "Pc")
    path = keep.findtext("WORKSPACE/PHYSICAL").split(",")
    meta = {"source": filename.name, "container_path": path[:-1], "node_uuid": path[-1]}
    for d in list(devs):
        if d.find("ENGINE/TYPE").text != "Power Distribution Device":
            devs.remove(d)
    for l in list(r.find("NETWORK/LINKS")):
        r.find("NETWORK/LINKS").remove(l)
    for tag in ("RECTANGLES", "ELLIPSES", "LINES", "POLYGONS"):
        e = r.find(tag)
        if e is not None:
            for c in list(e):
                e.remove(c)
    notes = r.find("PHYSICALWORKSPACE/NOTES")
    if notes is not None:
        for c in list(notes):
            notes.remove(c)
    _prune_physical_devices(r, meta["node_uuid"])
    ET.ElementTree(r).write(destination / "base.xml", encoding="utf-8")
    with open(destination / "base.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    print("base:", meta["source"])
    if activity_base is not None:
        _, activity, filename = activity_base
        _write_activity_base(activity, destination / "pka-base.xml")
        print("activity settings:", filename.name)
    else:
        print("warning: no .pka supplied; activity generation still needs pka-base.xml")
    return destination


def list_models():
    path = library_dir() / "devices" / "index.json"
    if not path.exists():
        print("device library is missing; run `ptlab init --source PATH`")
        return 1
    with open(path, encoding="utf-8") as fh:
        models = json.load(fh)
    for key, item in sorted(models.items()):
        print(f"{key:20} {item['model']:18} {len(item['interfaces']):2} ports")
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="+")
    args = parser.parse_args()
    build([Path(source).expanduser().resolve() for source in args.source])
