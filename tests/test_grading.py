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
                                  "value": " router-id 1.1.1.1"}])

    def test_ping_defaults_to_the_first_address(self):
        s = spec("ping PC1 R1", "ping PC1 R1 10.9.9.9 fail", rows=[["R1", "G0/0", "10.0.0.1/30", ""]])
        tests = labgen.connectivity_tests(s)
        self.assertEqual([(t["ip"], t["succeed"]) for t in tests], [("10.0.0.1", True), ("10.9.9.9", False)])

    def test_connectivity_tests_go_into_the_answer_scenario(self):
        t = tree(device("PC1", ""), device("R1", R1))
        ptlab.add_connectivity_tests(t, [{"src": "PC1", "dst": "R1", "ip": "10.0.0.1", "succeed": True}])
        pdu = t.getroot().find("SCENARIOSET/SCENARIO/PDU")
        self.assertEqual(pdu.findtext("TEST_CONDITION"), "3")
        self.assertEqual(pdu.findtext("PDU/DSTADDR"), "10.0.0.1")
        self.assertEqual(pdu.find("DESTINATION").get("device"), ptlab.devices(t)["R1"].findtext("ENGINE/SAVE_REF_ID"))


class MergeSections(unittest.TestCase):
    def test_router_id_stays_inside_router_ospf(self):
        out = labgen.merge(["version 15.1", "!", "end"], "router ospf 10\n router-id 2.2.2.2\n network 10.0.0.0 0.0.0.3 area 0\n")
        i = out.index("router ospf 10")
        self.assertEqual(out[i + 1:i + 3], [" router-id 2.2.2.2", " network 10.0.0.0 0.0.0.3 area 0"])


if __name__ == "__main__":
    unittest.main()
