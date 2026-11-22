"""ptbuild - build Packet Tracer topologies: clone devices, cable them, draw on the canvas.

Device entries come from template files (one clean device per model). A clone gets fresh
identities: name, save-ref-id (links point at it), serial number, port MAC addresses,
logical-workspace position and pointers, and its own node in the physical workspace.
"""
import copy
import random
import re
import uuid
import xml.etree.ElementTree as ET

from .paths import library_dir

_rng = random.Random()


def new_ref():
    return "save-ref-id:%d" % _rng.randrange(10**18, 10**19)


def new_mac(used):
    while True:
        m = "00%02X.%02X%02X.%02X%02X" % tuple(_rng.randrange(256) for _ in range(5))
        m = "%s.%s.%s" % (m[0:4], m[5:9], m[10:14])
        if m not in used:
            used.add(m)
            return m


def new_addr():
    return str(_rng.randrange(10**12, 10**13))


def physical_index(root):
    pw = root.find("PHYSICALWORKSPACE")
    nodes = {}
    parent = {}
    for p in pw.iter():
        for c in p:
            parent[c] = p
    for n in pw.iter("NODE"):
        u = n.findtext("UUID_STR")
        if u:
            nodes[u] = n
    return nodes, parent


def physical_path(root, target):
    """Return the UUID path from Intercity to a physical NODE."""
    pw = root.find("PHYSICALWORKSPACE")

    def visit(node, path):
        uid = node.findtext("UUID_STR")
        here = path + ([uid] if uid else [])
        if node is target:
            return here
        children = node.find("CHILDREN")
        if children is not None:
            for child in children.findall("NODE"):
                found = visit(child, here)
                if found:
                    return found
        return None

    if pw is not None:
        for node in pw.findall("NODE"):
            if found := visit(node, []):
                return found
    raise ValueError("physical node is not attached to the workspace")


# Rack geometry, measured in Packet Tracer 9.0.1 from two calibration racks (every model 16 units apart, then
# stacked): a rack node's X is the device's offset from the top of the rack, about 6.5 px per unit. Drawn
# heights: 1RU gear ~3 units, 2911 ~5.3, 1941 ~6.4, Server-PT ~13; the WLC 2504/3504 sit on a shelf tray. From
# about X=128 a device lands on the rack's bottom frame. Heights below include a small gap.
RACK_CAPACITY = 124
# + about 1 unit for the name label drawn under each device (confirmed in a student's rack screenshot: at 6 units
# the 2911's label was hidden under the next device).
RACK_UNITS = {"router-1941": 8, "router-2911": 7, "server": 15, "wlc-2504": 5, "wlc-3504": 5,
              "router-pt": 12, "router-pt-empty": 12}
DEFAULT_RACK_UNITS = 4
FLOOR_X, FLOOR_Y = 470, 120               # first free floor position beside the wiring closet
CLOSET_ICON = (40, 40, 400, 400)          # x1, y1, x2, y2 the closet icon covers in the building view


def rack_units(key):
    return RACK_UNITS.get(key, DEFAULT_RACK_UNITS)


def stack_rack(entries, reserved=()):
    """entries: [(key, slot or None)] in spec order -> {index: X}. Devices with a slot come first, by slot
    (1 = top), then the rest in spec order; each takes its model's height and skips reserved spans
    (equipment already in the base rack, such as its power distribution unit)."""
    order = sorted(range(len(entries)), key=lambda i: (entries[i][1] is None, entries[i][1] or 0, i))
    spans = sorted(reserved)
    pos, out = 0, {}
    for i in order:
        h = rack_units(entries[i][0])
        moved = True
        while moved:
            moved = False
            for a, b in spans:
                if pos < b and pos + h > a:
                    pos, moved = b, True
        out[i] = pos
        pos += h
    return out


def first_node_in(node, kind):
    return next((n for n in node.iter("NODE") if n.findtext("TYPE") == str(kind)), None)


def _renew_uuids(node):
    for n in node.iter("NODE"):
        if n.find("UUID_STR") is not None:
            n.find("UUID_STR").text = "{%s}" % uuid.uuid4()


def first_physical_node(root, kind):
    return next((node for node in root.findall(".//NODE") if node.findtext("TYPE") == str(kind)), None)


def clone_device(root, template, name, x, y, used_macs=None):
    """Append a copy of `template` (a DEVICE element) to root's network with new identities.
    Returns the new DEVICE element."""
    used_macs = used_macs if used_macs is not None else {m.text for m in root.iter("MACADDRESS") if m.text}
    d = copy.deepcopy(template)
    eng = d.find("ENGINE")
    eng.find("NAME").text = name
    if eng.find("SYS_NAME") is not None:
        eng.find("SYS_NAME").text = name
    if eng.find("SAVE_REF_ID") is None:   # files older than ~7.2 have none; links need one
        ET.SubElement(eng, "SAVE_REF_ID")
    eng.find("SAVE_REF_ID").text = new_ref()
    if eng.find("SERIALNUMBER") is not None and eng.find("SERIALNUMBER").text:
        sn = eng.find("SERIALNUMBER").text
        eng.find("SERIALNUMBER").text = sn[:3] + "".join(_rng.choice("0123456789ABCDEFGHJKLMNPRSTUVWXYZ") for _ in sn[3:])
    for p in d.iter("PORT"):
        m = p.find("MACADDRESS")
        if m is not None and m.text:
            mac = new_mac(used_macs)
            m.text = mac
            if p.find("BIA") is not None:
                p.find("BIA").text = mac
    lg = d.find("WORKSPACE/LOGICAL")
    lg.find("X").text, lg.find("Y").text = str(x), str(y)
    for t in ("MEM_ADDR", "DEV_ADDR"):
        if lg.find(t) is not None:
            lg.find(t).text = new_addr()
    root.find("NETWORK/DEVICES").append(d)
    return d


def give_physical_node(root, device, like_device):
    """Give `device` its own physical-workspace node, a copy of `like_device`'s, in the same container."""
    nodes, parent = physical_index(root)
    path = like_device.findtext("WORKSPACE/PHYSICAL").split(",")
    src = nodes[path[-1]]
    n = copy.deepcopy(src)
    u = "{%s}" % uuid.uuid4()
    n.find("UUID_STR").text = u
    n.find("NAME").text = device.findtext("ENGINE/NAME")
    parent[src].append(n)
    device.find("WORKSPACE/PHYSICAL").text = ",".join(path[:-1] + [u])
    return n


def link(root, dev_a, port_a, dev_b, port_b, cable="eStraightThrough", kind="eCopper", like=None):
    """Cable two devices. `like` is an existing LINK element to copy the format from."""
    tpl = like if like is not None else next(root.iter("LINK"))
    lk = copy.deepcopy(tpl)
    lk.find("TYPE").text = kind
    c = lk.find("CABLE")
    c.find("FROM").text = dev_a.findtext("ENGINE/SAVE_REF_ID")
    c.find("TO").text = dev_b.findtext("ENGINE/SAVE_REF_ID")
    ports = c.findall("PORT")
    ports[0].text, ports[1].text = port_a, port_b
    for t, dev in (("FROM_DEVICE_MEM_ADDR", dev_a), ("TO_DEVICE_MEM_ADDR", dev_b)):
        if c.find(t) is not None:
            c.find(t).text = dev.findtext("WORKSPACE/LOGICAL/DEV_ADDR") or new_addr()
    for t in ("FROM_PORT_MEM_ADDR", "TO_PORT_MEM_ADDR"):
        if c.find(t) is not None:
            c.find(t).text = new_addr()
    if c.find("TYPE") is not None:
        c.find("TYPE").text = cable
    root.find("NETWORK/LINKS").append(lk)
    return lk


# ---------------------------------------------------------------- whole topologies
import json as _json
import os as _os

class Topology:
    """t = Topology(); r1 = t.add("router-2911", "R1", 200, 100); t.link(r1, "GigabitEthernet0/0", sw, ...)
    t.rect(x1, y1, x2, y2, (170, 255, 255)); t.note("text", x, y); t.save_xml(path)"""

    def __init__(self):
        self.lib = library_dir()
        self.tree = ET.parse(self.lib / "base.xml")
        self.root = self.tree.getroot()
        with open(self.lib / "base.json", encoding="utf-8") as fh:
            self.meta = _json.load(fh)
        with open(self.lib / "devices" / "index.json", encoding="utf-8") as fh:
            self.index = _json.load(fh)
        self.macs = set()
        self.devices = {}
        self.keys = {}
        nodes, parent = physical_index(self.root)
        self._phys_tpl = nodes[self.meta["node_uuid"]]
        self._phys_parent = parent[self._phys_tpl]
        # The source topology can contain physical nodes for devices removed by make_library.
        # Keep only nodes still referenced by the base network plus our one cloning template.
        live = {part for d in self.root.findall("NETWORK/DEVICES/DEVICE")
                for part in (d.findtext("WORKSPACE/PHYSICAL") or "").split(",") if part}
        for node in list(nodes.values()):
            uid = node.findtext("UUID_STR")
            if node.findtext("TYPE") == "6" and node is not self._phys_tpl and uid not in live:
                parent[node].remove(node)
        self._phys_parent.remove(self._phys_tpl)        # the base file's own PC node is only a template
        rack = first_physical_node(self.root, 4)
        # one site to start with: the base's own building/closet/rack (its rack keeps the power unit)
        self._sites = {None: self._site(first_physical_node(self.root, 2), first_physical_node(self.root, 3), rack,
                                        reserved=[(int(float(c.findtext("X") or 0)),
                                                   int(float(c.findtext("X") or 0)) + DEFAULT_RACK_UNITS)
                                                  for c in (rack.findall("CHILDREN/NODE") if rack is not None else [])])}
        self._default_site = None
        self._link_tpl = None

    @staticmethod
    def _site(building, closet, rack, reserved=()):
        return {"building": building, "closet": closet, "rack": rack, "reserved": list(reserved),
                "counts": {"rack": 0, "closet": 0, "building": 0}, "rack_items": []}

    def configure_sites(self, sites):
        """[{name, city?, building?, closet?, rack?}, ...]: the first site renames the base's containers; every
        further site gets its own copy of building > wiring closet > rack (new UUIDs, no inherited devices),
        in the same city as an earlier site with that city name, or in a new city."""
        city0 = first_physical_node(self.root, 1)
        base = self._sites.pop(None)
        cities = {}
        for i, site in enumerate(sites):
            name = site["name"]
            city_name = site.get("city") or (city0.findtext("NAME") if city0 is not None else "City")
            if i == 0:
                st = base
                if city0 is not None:
                    city0.find("NAME").text = city_name
                cities[city_name] = city0
            else:
                city = cities.get(city_name)
                if city is None:                       # a new city beside the first one
                    city = copy.deepcopy(city0)
                    kids = city.find("CHILDREN")
                    for k in list(kids):
                        kids.remove(k)
                    _renew_uuids(city)
                    city.find("NAME").text = city_name
                    city.find("X").text = str(200 + 700 * len(cities))
                    city.find("Y").text = "200"
                    first_physical_node(self.root, 0).find("CHILDREN").append(city)
                    cities[city_name] = city
                building = copy.deepcopy(base["building"])
                for holder in building.iter("CHILDREN"):  # drop inherited devices (power unit, PCs)
                    for k in list(holder):
                        if k.findtext("TYPE") == "6":
                            holder.remove(k)
                _renew_uuids(building)
                in_city = sum(1 for k in city.find("CHILDREN").findall("NODE") if k.findtext("TYPE") == "2")
                building.find("X").text = str(100 + 300 * in_city)
                building.find("Y").text = "100"
                city.find("CHILDREN").append(building)
                st = self._site(building, first_node_in(building, 3), first_node_in(building, 4))
            for kind, field, default in ((2, "building", name), (3, "closet", f"{name} Wiring Closet"),
                                         (4, "rack", f"{name} Rack")):
                node = st[field]
                if node is not None:
                    node.find("NAME").text = str(site.get(field) or default)
            self._sites[name] = st
            if i == 0:
                self._default_site = name

    def configure_physical(self, settings):
        """Rename the inherited city/building/closet/rack containers."""
        mapping = ((1, "city"), (2, "building"), (3, "closet"), (4, "rack"))
        for kind, field in mapping:
            if value := settings.get(field):
                node = first_physical_node(self.root, kind)
                if node is not None:
                    node.find("NAME").text = str(value)

    def add(self, key, name, x, y, physical=None, site=None):
        tpl = ET.parse(self.lib / "devices" / (key + ".xml")).getroot()
        d = clone_device(self.root, tpl, name, x, y, self.macs)
        n = copy.deepcopy(self._phys_tpl)
        u = "{%s}" % uuid.uuid4()
        n.find("UUID_STR").text = u
        n.find("NAME").text = name
        placement = {"location": physical} if isinstance(physical, str) else dict(physical or {})
        default = "rack" if key.startswith(("router", "switch", "l3switch", "wlc", "server")) else "building"
        st = self._sites[site if site is not None else self._default_site]
        targets = {"rack": st["rack"], "closet": st["closet"], "building": st["building"]}
        available = [k for k, v in targets.items() if v is not None]
        location = placement.get("location", default)
        if location not in targets:
            raise ValueError(f"physical location {location!r} is unknown; use rack, closet, or building")
        if targets[location] is None and "location" not in placement:
            # the base topology lacks this container: fall back instead of failing the whole build
            location = next((k for k in ("rack", "closet", "building") if targets[k] is not None), None)
        if location is None or targets[location] is None:
            raise ValueError(f"physical location {placement.get('location', default)!r} is not in the base topology "
                             f"(available: {', '.join(available) or 'none'}); re-run `ptlab init` with a source "
                             f"file whose Physical workspace has a building, wiring closet and rack")
        target = targets[location]
        children = target.find("CHILDREN")
        if children is None:
            children = ET.SubElement(target, "CHILDREN")
        index = st["counts"][location]
        st["counts"][location] += 1
        if location == "rack":
            px, py = 0, 0     # stacked below by model height
        else:
            # the wiring-closet icon covers about x/y 50-395 of the building view (1 unit ~ 1 px in PT 9.0.1):
            # endpoints go on a grid to its right
            px, py = FLOOR_X + (index % 5) * 110, FLOOR_Y + (index // 5) * 110
        n.find("X").text = str(placement.get("x", px))
        n.find("Y").text = str(placement.get("y", py))
        children.append(n)
        if location == "rack" and "x" not in placement:
            st["rack_items"].append((n, key, placement.get("slot")))
            xs = stack_rack([(k, sl) for _, k, sl in st["rack_items"]], st["reserved"])
            for i, (node, _, _) in enumerate(st["rack_items"]):
                node.find("X").text = str(xs[i])
        d.find("WORKSPACE/PHYSICAL").text = ",".join(physical_path(self.root, target) + [u])
        self.devices[name] = d
        self.keys[name] = key
        return d

    def interfaces(self, key):
        return self.index[key]["interfaces"]

    def ports(self, name):
        """Port names of a device in this topology (from its template)."""
        return self.index[self.keys[name]]["interfaces"]

    def link(self, a, port_a, b, port_b, cable="eStraightThrough"):
        for dev, port in ((a, port_a), (b, port_b)):   # a link to a missing port makes PT refuse the file
            if isinstance(dev, str) and port not in self.ports(dev):
                raise ValueError(f"{dev} has no port {port}; it has: {', '.join(self.ports(dev))}")
        if self._link_tpl is None:
            self._link_tpl = ET.fromstring(LINK_TEMPLATE)
        kind = "eSerial" if cable in ("eSerialDCE", "eSerialDTE") else ("eFiber" if cable == "eFiber" else "eCopper")
        return link(self.root, self.devices[a] if isinstance(a, str) else a, port_a,
                    self.devices[b] if isinstance(b, str) else b, port_b, cable=cable, kind=kind, like=self._link_tpl)

    def rect(self, x1, y1, x2, y2, rgb=(170, 255, 255), outline="#000000"):
        rs = self.root.find("RECTANGLES")
        r = ET.SubElement(rs, "RECTANGLE", {"uuid": "{%s}" % uuid.uuid4()})
        for t, v in (("TopLeftX", x1), ("TopLeftY", y1), ("BottomRightX", x2), ("BottomRightY", y2)):
            ET.SubElement(r, t).text = str(v)
        c = ET.SubElement(r, "Color")
        for t, v in zip(("Red", "Green", "Blue"), rgb):
            ET.SubElement(c, t).text = str(v)
        ET.SubElement(r, "Filled", {"OUTLINECOLOR": outline, "OUTLINED": "true"}).text = "1"
        ET.SubElement(r, "RECTCLUSTERID").text = "1-1"
        ET.SubElement(r, "MEM_ADDR").text = new_addr()
        return r

    def note(self, text, x, y):
        notes = self.root.find("PHYSICALWORKSPACE/NOTES")
        n = ET.SubElement(notes, "NOTE", {"uuid": "{%s}" % uuid.uuid4()})
        ET.SubElement(n, "X").text = str(x)
        ET.SubElement(n, "Y").text = str(y)
        ET.SubElement(n, "Z").text = "40000"
        ET.SubElement(n, "TEXT").text = text
        ET.SubElement(n, "NOTECLUSTERID").text = "1-1"
        ET.SubElement(n, "MEM_ADDR").text = new_addr()
        return n

    def save_xml(self, path):
        ET.indent(self.tree, space=" ")
        self.tree.write(path, encoding="utf-8", short_empty_elements=False)


LINK_TEMPLATE = """<LINK><TYPE>eCopper</TYPE><CABLE><LENGTH>1</LENGTH><FUNCTIONAL>true</FUNCTIONAL>
<FROM></FROM><PORT></PORT><TO></TO><PORT></PORT><FROM_DEVICE_MEM_ADDR></FROM_DEVICE_MEM_ADDR>
<TO_DEVICE_MEM_ADDR></TO_DEVICE_MEM_ADDR><FROM_PORT_MEM_ADDR></FROM_PORT_MEM_ADDR><TO_PORT_MEM_ADDR></TO_PORT_MEM_ADDR>
<GEO_VIEW_COLOR>#6ba72e</GEO_VIEW_COLOR><IS_MANAGED_IN_RACK_VIEW>false</IS_MANAGED_IN_RACK_VIEW><TYPE>eStraightThrough</TYPE></CABLE></LINK>"""
