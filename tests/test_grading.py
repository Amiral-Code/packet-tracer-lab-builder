import hashlib
import unittest
import xml.etree.ElementTree as ET

from pt_lab_builder import labgen, ptlab


def device(name, config, vlans=()):
    d = ET.Element("DEVICE")
    engine = ET.SubElement(d, "ENGINE")
    ET.SubElement(engine, "NAME").text = name
    ET.SubElement(engine, "SAVE_REF_ID").text = f"save-ref-id:{abs(hash(name))}"
    rc = ET.SubElement(engine, "RUNNINGCONFIG")
    for line in config.strip("\n").splitlines():
        ET.SubElement(rc, "LINE").text = line
    if vlans:
        v = ET.SubElement(engine, "VLANS")
        for num, vname in vlans:
            ET.SubElement(v, "VLAN", {"number": str(num), "name": vname})
    return d


def tree(*devs):
    root = ET.Element("PACKETTRACER5")
    ds = ET.SubElement(ET.SubElement(root, "NETWORK"), "DEVICES")
    for d in devs:
        ds.append(d)
    return ET.ElementTree(root)


SW = """hostname SW1
spanning-tree vlan 20 priority 28672
interface FastEthernet0/1
 switchport access vlan 10
 switchport mode access
interface GigabitEthernet0/1
 switchport trunk native vlan 99
 switchport trunk allowed vlan 10-12,99
 switchport mode trunk
"""
R1 = """hostname R1
interface GigabitEthernet0/0
 ip address 10.0.0.1 255.255.255.252
router ospf 1
 router-id 1.1.1.1
 network 10.0.0.0 0.0.0.3 area 0
ip route 0.0.0.0 0.0.0.0 10.0.0.2
"""


def spec(*items, rows=()):
    return {"lab": {"title": "t", "scenario": "s"}, "device": [{"name": "SW1", "model": "switch-2960"},
                                                            {"name": "R1", "model": "router-2911"},
                                                            {"name": "PC1", "model": "pc"}],
            "addressing": {"rows": list(rows)}, "grade": {"items": list(items)}}


def grade(statements, devs):
    items, checks = labgen.compile_grade(spec(*statements))
    return items, ptlab.grade({"check": checks}, tree(*devs), checks, quiet=True)


class GradeStatements(unittest.TestCase):
    def test_vlan_list_uses_the_ios_form(self):
        self.assertEqual(labgen.vlan_list("99,10,11,12,20"), "10-12,20,99")
        self.assertEqual(labgen.vlan_list("10,11"), "10,11")
        self.assertEqual(labgen.vlan_list("5-7,1"), "1,5-7")

    def test_switching_statements_pass_on_a_correct_switch(self):
        _, res = grade(["access SW1 Fa0/1 10", "trunk SW1 G0/1 allowed 10,11,12,99 native 99",
                        "stp SW1 20 28672"], [device("SW1", SW)])
        self.assertTrue(all(res), res)

    def test_access_fails_on_the_wrong_vlan(self):
        _, res = grade(["access SW1 Fa0/1 20"], [device("SW1", SW)])
        self.assertFalse(all(res))

    def test_vlan_name_from_saved_vlans_or_config(self):
        _, res = grade(["vlan SW1 10 SALES"], [device("SW1", SW, vlans=[(10, "SALES")])])
        self.assertEqual(res, [True])
        _, res = grade(["vlan SW1 10 SALES"], [device("SW1", SW + "vlan 10\n name SALES\n")])
        self.assertEqual(res, [True])
        _, res = grade(["vlan SW1 10 SALES"], [device("SW1", SW, vlans=[(10, "VLAN0010")])])
        self.assertEqual(res, [False])

    def test_routing_statements(self):
        _, res = grade(["route R1 0.0.0.0/0 10.0.0.2", "ospf R1 1 10.0.0.0/30 0",
                        'in R1 "router ospf 1" "router-id 1.1.1.1"'], [device("R1", R1)])
        self.assertTrue(all(res), res)

    def test_line_only_matches_top_level_lines(self):
        # Packet Tracer compares whole lines: an indented sub-command never matches a top-level check
        _, res = grade(["line R1 network 10.0.0.0 0.0.0.3 area 0"], [device("R1", R1)])
        self.assertEqual(res, [False])

    def test_sub_command_items_use_the_wizard_line_id(self):
        items, _ = grade(['in R1 "router ospf 1" "router-id 1.1.1.1"'], [device("R1", R1)])
        self.assertEqual(items, [{"device": "R1", "kind": "run_line", "line_id": "router ospf 1 router-id 1.1.1.1",
                                  "value": " router-id 1.1.1.1",
                                  "hint": "Compare R1's running configuration with the task: show running-config."}])

    def test_custom_hint_is_written_as_incorrect_feedback(self):
        statement = "up R1 G0/0"
        s = spec(statement)
        s["grade"]["hints"] = {statement: "Inspect the interface state and its cable."}
        items, _ = labgen.compile_grade(s)
        comparisons = ptlab.comparisons(items)
        leaf = next(n for n in comparisons.iter("NAME") if n.get("headNode") == "false")
        self.assertEqual(leaf.get("incorrectFeedback"), "Inspect the interface state and its cable.")

    def test_statement_points_weight_native_items_and_connectivity_pdus(self):
        statement = "hostname R1 EDGE"
        s = spec(statement, "https PC1 R1", rows=[["PC1", "Fa0", "10.0.0.10/24", ""],
                                                  ["R1", "G0/0", "10.0.0.1/24", ""]])
        s["grade"]["points"] = {statement: 5, "https PC1 R1": 3}
        items, _ = labgen.compile_grade(s)
        self.assertEqual(items[0]["points"], 5)
        comparisons = ptlab.comparisons(items)
        leaf = next(n for n in comparisons.iter("NODE") if n.findtext("ID") == "Host Name")
        self.assertEqual(leaf.findtext("POINTS"), "5")
        self.assertEqual(labgen.connectivity_tests(s)[0]["points"], 3)

    def test_ping_defaults_to_the_first_address(self):
        s = spec("ping PC1 R1", "ping PC1 R1 10.9.9.9 fail", rows=[["R1", "G0/0", "10.0.0.1/30", ""]])
        tests = labgen.connectivity_tests(s)
        self.assertEqual([(t["ip"], t["succeed"]) for t in tests], [("10.0.0.1", True), ("10.9.9.9", False)])

    def test_tcp_aliases_and_explicit_ports(self):
        rows = [["PC1", "Fa0", "10.0.0.10/24", "10.0.0.1"], ["R1", "G0/0", "10.0.0.1/24", ""]]
        s = spec("https PC1 R1", "telnet PC1 R1 fail", "tcp PC1 R1 8443 10.9.9.9", rows=rows)
        tests = labgen.connectivity_tests(s)
        self.assertEqual([(t["protocol"], t["port"], t["ip"], t["succeed"]) for t in tests],
                         [("tcp", 443, "10.0.0.1", True), ("tcp", 23, "10.0.0.1", False),
                          ("tcp", 8443, "10.9.9.9", True)])
        self.assertTrue(all(t["src_ip"] == "10.0.0.10" for t in tests))

    def test_connectivity_tests_go_into_the_answer_scenario(self):
        t = tree(device("PC1", ""), device("R1", R1))
        ptlab.add_connectivity_tests(t, [{"src": "PC1", "dst": "R1", "ip": "10.0.0.1", "succeed": True}])
        pdu = t.getroot().find("SCENARIOSET/SCENARIO/PDU")
        self.assertEqual(pdu.findtext("TEST_CONDITION"), "3")
        self.assertEqual(pdu.findtext("PDU/DSTADDR"), "10.0.0.1")
        self.assertEqual(pdu.find("DESTINATION").get("device"), ptlab.devices(t)["R1"].findtext("ENGINE/SAVE_REF_ID"))

    def test_tcp_connectivity_test_uses_a_saved_tcp_pdu(self):
        t = tree(device("PC1", ""), device("R1", R1))
        ptlab.add_connectivity_tests(t, [{"src": "PC1", "dst": "R1", "src_ip": "10.0.0.10",
                                         "ip": "10.0.0.1", "port": 443, "protocol": "tcp",
                                         "succeed": True}])
        pdu = t.getroot().find("SCENARIOSET/SCENARIO/PDU")
        self.assertEqual(pdu.findtext("TYPE"), "1")
        self.assertEqual(pdu.find("TYPE").get("patterned"), "yes")
        self.assertEqual(pdu.findtext("DESTINATION"), "10.0.0.1")
        self.assertEqual(pdu.findtext("PDU/SRCADDR"), "10.0.0.10")
        self.assertEqual(pdu.findtext("PDU/PDU/TYPE"), "CTcpHeader")
        self.assertEqual(pdu.findtext("PDU/PDU/DST"), "443")
        self.assertEqual(pdu.findtext("PDU_SIZE"), "10")

    def test_activity_controls_use_confirmed_packet_tracer_values(self):
        attrs = ptlab.activity_attributes({"timer": "countdown", "countdown_minutes": 10,
                                           "answer_convergence_ms": 30000, "wizard_password": "lab-lock"})
        self.assertEqual(attrs["TIMERTYPE"], "1")          # 0 = "Time Elapsed", 1 = "Time Left", other = none
        self.assertEqual(attrs["COUNTDOWNMS"], "600000")
        self.assertEqual(attrs["COUNTDOWNLEFT"], "600000")
        self.assertEqual(attrs["FORWARD_ANS_SIM_MS"], "30000")
        self.assertEqual(attrs["PASS"], hashlib.md5(ptlab.PASSWORD_SALT + b"lab-lock").hexdigest().upper())
        self.assertEqual(attrs["VALUE"].encode("latin-1"), ptlab.PASSWORD_SALT)

    def test_password_hash_matches_a_real_activity(self):
        # a published NetAcad activity locked with the widely known instructor password
        self.assertEqual(ptlab.password_hash("PT_ccna5"), "468D92E6B15141624011AD1B03B46B63")

    def test_no_password_means_no_salt(self):
        attrs = ptlab.activity_attributes({})
        self.assertEqual((attrs["PASS"], attrs["TIMERTYPE"]), ("", "0"))
        self.assertNotIn("VALUE", attrs)

    def test_existing_devices_are_rebuilt_and_locked_per_device_and_port(self):
        locking = ET.Element("LOCKINGTREE")
        branch = ET.SubElement(locking, "NODE", {"on": "no"})
        ET.SubElement(branch, "ID").text = "Existing Devices"
        stale = ET.SubElement(branch, "NODE", {"on": "no"})
        ET.SubElement(stale, "ID").text = ET.SubElement(stale, "TEXT").text = "Router0"
        for ident in ("Device_Remove", "Device Use Config Tab"):
            sw = ET.SubElement(stale, "NODE", {"on": "no"})
            ET.SubElement(sw, "ID").text = ident
        ports = ET.SubElement(stale, "NODE", {"on": "no"})
        ET.SubElement(ports, "ID").text = "Ports"
        port = ET.SubElement(ports, "NODE", {"on": "no"})
        ET.SubElement(port, "ID").text = ET.SubElement(port, "TEXT").text = "Vlan1"
        for ident in ("Port_Remove", "Port_Connect", "Port_Disconnect"):
            sw = ET.SubElement(port, "NODE", {"on": "no"})
            ET.SubElement(sw, "ID").text = ident
        for ident in ("Create Devices", "Remove Devices", "Connect Links", "Disconnect Links"):
            sw = ET.SubElement(locking, "NODE", {"on": "no"})
            ET.SubElement(sw, "ID").text = ident
        ptlab.set_existing_devices(locking, {"R1": ["GigabitEthernet0/0", "GigabitEthernet0/1"], "SW1": ["Vlan1"]})
        ptlab.apply_locking_preset(locking, "fixed-topology")
        names = [d.findtext("ID") for d in branch.findall("NODE")]
        self.assertEqual(names, ["R1", "SW1"])                       # the base's own devices are gone
        r1 = branch.find("NODE")
        self.assertEqual(r1.find("NODE[ID='Device_Remove']").get("on"), "yes")
        self.assertEqual(r1.find("NODE[ID='Device Use Config Tab']").get("on"), "no")
        r1_ports = r1.find("NODE[ID='Ports']").findall("NODE")
        self.assertEqual([p.findtext("ID") for p in r1_ports], ["GigabitEthernet0/0", "GigabitEthernet0/1"])
        self.assertTrue(all(sw.get("on") == "yes" for p in r1_ports for sw in p.findall("NODE")))

    def test_physical_locations_follow_the_generated_network(self):
        net = ET.Element("PACKETTRACER5")
        ws = ET.SubElement(net, "PHYSICALWORKSPACE")
        def node(parent, kind, name, uid):
            n = ET.SubElement(parent, "NODE")
            for tag, val in (("TYPE", kind), ("NAME", name), ("UUID_STR", uid)):
                ET.SubElement(n, tag).text = val
            return ET.SubElement(n, "CHILDREN")
        city = node(node(ws, "0", "Intercity", "{a}"), "1", "Tiznit", "{b}")
        closet = node(node(city, "2", "Branch", "{c}"), "3", "Branch Closet", "{d}")
        node(closet, "4", "Rack 1", "{e}")
        locking = ET.Element("LOCKINGTREE")
        workspace = ET.SubElement(locking, "NODE", {"on": "no"})
        ET.SubElement(workspace, "ID").text = "Physical Workspace"
        branch = ET.SubElement(locking, "NODE", {"on": "no"})
        ET.SubElement(branch, "ID").text = "Physical Locations"
        ptlab.set_physical_locations(locking, ET.ElementTree(net), "Branch Closet")
        ids = [n.findtext("ID") for n in branch.iter("NODE") if n.findtext("ID", "").startswith("{")]
        self.assertEqual(ids, ["{a}", "{a},{b}", "{a},{b},{c}", "{a},{b},{c},{d}"])   # racks are not locations
        started = [n for n in branch.iter("NODE") if n.findtext("ID") == "Start in Location" and n.get("on") == "yes"]
        self.assertEqual(len(started), 1)
        self.assertEqual(workspace.get("on"), "yes")   # "Start in Physical Workspace", or the view stays Logical

    def test_locking_preset_enables_matching_global_and_device_switches(self):
        locking = ET.Element("LOCKINGTREE")
        for ident in ("Use Config Tab", "Router/Switch Config Tab", "Device Use Config Tab", "Check Results"):
            node = ET.SubElement(locking, "NODE", {"on": "no"})
            ET.SubElement(node, "ID").text = ident
        ptlab.apply_locking_preset(locking, "cli-only")
        values = {n.findtext("ID"): n.get("on") for n in locking.findall("NODE")}
        self.assertEqual(values["Use Config Tab"], "yes")
        self.assertEqual(values["Device Use Config Tab"], "yes")
        self.assertEqual(values["Check Results"], "no")


def with_cable(t, a, pa, b, pb, kind):
    devs = ptlab.devices(t)
    links = t.getroot().find("NETWORK/LINKS")
    if links is None:
        links = ET.SubElement(t.getroot().find("NETWORK"), "LINKS")
    cable = ET.SubElement(ET.SubElement(links, "LINK"), "CABLE")
    ET.SubElement(cable, "FROM").text = devs[a].findtext("ENGINE/SAVE_REF_ID")
    ET.SubElement(cable, "PORT").text = pa
    ET.SubElement(cable, "TO").text = devs[b].findtext("ENGINE/SAVE_REF_ID")
    ET.SubElement(cable, "PORT").text = pb
    ET.SubElement(cable, "TYPE").text = kind
    return t


class Cabling(unittest.TestCase):
    SPEC = {"lab": {"title": "t", "scenario": "s", "kind": "mixed"},
            "device": [{"name": "R1", "model": "router-2911"}, {"name": "PC1", "model": "pc"}],
            "link": [{"a": "R1 G0/2", "b": "PC1 Fa0", "student": True}], "grade": {"items": []}}

    def grade(self, t):
        items, checks = labgen.compile_grade(self.SPEC)
        return items, ptlab.grade({"check": checks}, t, checks, quiet=True)

    def test_student_link_is_graded_by_port_up_and_cable(self):
        items, res = self.grade(tree(device("R1", R1), device("PC1", "")))
        self.assertEqual([(i["device"], i["kind"]) for i in items], [("R1", "port_on")])
        self.assertEqual(res, [False])

    def test_right_cable_passes_wrong_type_fails(self):
        ok = with_cable(tree(device("R1", R1), device("PC1", "")), "PC1", "FastEthernet0", "R1",
                        "GigabitEthernet0/2", "eCrossOver")
        self.assertEqual(self.grade(ok)[1], [True])
        wrong = with_cable(tree(device("R1", R1), device("PC1", "")), "R1", "GigabitEthernet0/2", "PC1",
                           "FastEthernet0", "eStraightThrough")
        self.assertEqual(self.grade(wrong)[1], [False])


class MergeSections(unittest.TestCase):
    def test_router_id_stays_inside_router_ospf(self):
        out = labgen.merge(["version 15.1", "!", "end"], "router ospf 10\n router-id 2.2.2.2\n network 10.0.0.0 0.0.0.3 area 0\n")
        i = out.index("router ospf 10")
        self.assertEqual(out[i + 1:i + 3], [" router-id 2.2.2.2", " network 10.0.0.0 0.0.0.3 area 0"])


if __name__ == "__main__":
    unittest.main()
