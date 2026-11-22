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
    ("Router", "2911"): "router-2911", ("Router", "ISR4331"): "router-isr4331", ("Router", "1941"): "router-1941",
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
}


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
    for p in device.iter("PORT"):                    # saved addresses on every port and host
        for tag in ("IP", "SUBNET", "PORT_GATEWAY", "PORT_DNS"):
            if p.find(tag) is not None:
                p.find(tag).text = ""
        if p.find("PORT_DHCP_ENABLE") is not None:
            p.find("PORT_DHCP_ENABLE").text = "false"
    if eng.find("GATEWAY") is not None:
        eng.find("GATEWAY").text = ""
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


def build(sources, destination=None):
    """Create local templates from .pkt/.pka files the user is allowed to use."""
    destination = Path(destination or library_dir())
    devices_out = destination / "devices"
    files = []
    for rank, source in enumerate(sources):
        source = Path(source)
        label = source.name or f"source-{rank + 1}"
        for extension in ("*.pkt", "*.pka"):
            for filename in glob.glob(str(source / "**" / extension), recursive=True):
                files.append((rank, label, Path(filename)))
    if not files:
        raise RuntimeError("no .pkt or .pka files found under the supplied source folders")
    found = {}
    base = None
    activity_base = None
    for rank, label, filename in files:
        root = load(filename)
        if root is None:
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
                device_type = device.find("ENGINE/TYPE")
                if device_type is None:
                    continue
                key = WANT.get((device_type.text, device_type.get("model")))
                if key and (key not in found or score > found[key][0]):
                    found[key] = (score, copy.deepcopy(device), label, filename, version)
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
        factory_reset(d, "router" if ty == "Router" else "switch" if ty in ("Switch", "MultiLayerSwitch") else "host")
        ET.ElementTree(d).write(devices_out / (key + ".xml"), encoding="utf-8")
        ifaces = [i for i in ifaces if "." not in i and (not i.startswith("Vlan") or i == "Vlan1")]
        index[key] = {"type": d.find("ENGINE/TYPE").text, "model": d.find("ENGINE/TYPE").get("model"),
                      "version": version, "source": label, "file": filename.name, "interfaces": ifaces}
        print(f"{key:18} {index[key]['model']:16} {version:12} {label:22} {len(ifaces)} interfaces")
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
