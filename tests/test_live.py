import unittest
from unittest.mock import patch

from pt_lab_builder import live


SPEC = {
    "lab": {"kind": "configure"},
    "device": [{"name": "R1", "model": "router-1941-serial"}, {"name": "R2", "model": "router-1941-serial"},
               {"name": "PC1", "model": "pc"}],
    "link": [{"a": "R1 S0/0/0", "b": "R2 S0/0/0", "cable": "eSerialDTE", "student": True},
             {"a": "R1 G0/0", "b": "PC1 Fa0"}],
    "addressing": {"rows": [["R1", "G0/0", "192.168.1.1/24", ""], ["PC1", "Fa0", "192.168.1.10/24", "192.168.1.1"],
                            ["PC1", "Fa0", "2001:db8:1::10/64", "fe80::1"]]},
    "config": {"answer": {"R1": "interface G0/0\n ip address 192.168.1.1 255.255.255.0\n no shutdown\n!\n"
                                "ip route 0.0.0.0 0.0.0.0 10.0.0.2\nend\n"}},
}


class LivePlanTests(unittest.TestCase):
    def setUp(self):
        with patch("pt_lab_builder.labgen.library_dir"):
            self.plan = live.plan(SPEC, "/abs/result.json", "/abs/solved.pka")

    def test_cli_lines_say_which_are_sub_commands_and_end_in_end(self):
        self.assertEqual(self.plan["configs"]["R1"], [
            [False, "interface GigabitEthernet0/0"], [True, "ip address 192.168.1.1 255.255.255.0"],
            [True, "no shutdown"], [False, "ip route 0.0.0.0 0.0.0.0 10.0.0.2"], [True, "end"]])

    def test_student_cables_only_with_the_dce_end_first(self):
        (link,) = self.plan["links"]       # the built-in R1-PC1 link is not the student's job
        self.assertEqual((link["a"], link["b"], link["type"]), ("R2", "R1", live.CONNECT["eSerialDTE"]))

    def test_hosts_get_their_answer_addresses(self):
        pc = self.plan["hosts"]["PC1"]
        self.assertEqual((pc["port"], pc["ip"], pc["mask"], pc["gw"]),
                         ("FastEthernet0", "192.168.1.10", "255.255.255.0", "192.168.1.1"))
        self.assertEqual(pc["ip6"], [["2001:DB8:1::10", 64]])

    def test_paths_and_timings(self):
        self.assertEqual((self.plan["result"], self.plan["save"]), ("/abs/result.json", "/abs/solved.pka"))
        self.assertGreaterEqual(self.plan["settle_ms"], 20_000)


class FaultLibraryTests(unittest.TestCase):
    def test_candidates_come_from_the_answer_configuration(self):
        from pt_lab_builder import troubleshoot
        spec = {"device": [{"name": "R1", "model": "router-2911"}],
                "addressing": {"rows": [["PC1", "Fa0", "192.168.1.10/24", "192.168.1.1"]]},
                "config": {"answer": {"R1": "interface G0/0\n ip address 192.168.1.1 255.255.255.0\n no shutdown\n"
                                            "ip route 0.0.0.0 0.0.0.0 10.0.0.1\nrouter ospf 1\n network 10.0.0.0 0.0.0.3 area 0\n"}}}
        kinds = {("apply" in f, f.get("replace", "")[:12], tuple(f.get("pc", {}).items())) for f in troubleshoot.candidates(spec)}
        self.assertIn((True, "", ()), kinds)                                   # interface shut down
        self.assertIn((False, "ip route 0.0", ()), kinds)                      # wrong next hop
        self.assertIn((False, " network 10.", ()), kinds)                      # wrong OSPF area
        self.assertIn((False, " ip address ", ()), kinds)                      # mistyped address
        self.assertIn((False, "", (("gw", "192.168.1.2"),)), kinds)            # host gateway

    def test_fault_blocks_are_valid_toml(self):
        import tomllib
        from pt_lab_builder import troubleshoot
        block = troubleshoot._fault_toml({"device": "R1", "find": ' ip address "x"', "replace": " y",
                                          "symptom": "s", "explain": "e"})
        self.assertEqual(tomllib.loads(block)["fault"][0]["find"], ' ip address "x"')


class Gns3ExportTests(unittest.TestCase):
    SPEC = {"lab": {"title": "T", "scenario": "s", "objectives": ["o"]},
            "device": [{"name": "R1", "model": "router-2911"}, {"name": "R2", "model": "router-2911"},
                       {"name": "PC1", "model": "pc"}],
            "link": [{"a": "R1 G0/0", "b": "R2 G0/1"}, {"a": "R1 G0/2", "b": "PC1 Fa0"}],
            "addressing": {"rows": [["R1", "G0/2", "192.168.1.1/24", ""], ["PC1", "Fa0", "192.168.1.10/24", "192.168.1.1"],
                                    ["R2", "G0/1", "10.0.0.2/30", ""]]},
            "config": {"answer": {"R1": "interface G0/2\n ip address 192.168.1.1 255.255.255.0\n"
                                        "ip route 0.0.0.0 0.0.0.0 GigabitEthernet0/0 10.0.0.2\n"}},
            "grade": {"items": ["ping PC1 R2", "route R1 0.0.0.0/0 10.0.0.2", "hostname R1 R1"]}}

    def test_ports_names_hosts_and_checks(self):
        import tomllib
        from pt_lab_builder import gns3export
        lab = tomllib.loads(gns3export.export(self.SPEC))
        self.assertEqual(lab["links"], ["R1 e0/0 - R2 e0/0", "R1 e0/1 - PC1"])
        self.assertIn("interface e0/1", lab["solution"]["R1"])
        self.assertIn("ip route 0.0.0.0 0.0.0.0 e0/0 10.0.0.2", lab["solution"]["R1"])
        self.assertEqual(lab["base"]["PC1"], "ip 192.168.1.10/24 192.168.1.1")
        self.assertEqual(lab["nodes"], {"R1": "R", "R2": "R", "PC1": "PC"})
        self.assertEqual([c["cmd"] for c in lab["check"]], ["ping 10.0.0.2 -c 3", "show ip route static"])
        self.assertIn("#   hostname R1 R1", gns3export.export(self.SPEC))

    def test_devices_without_an_iou_equivalent_are_refused(self):
        from pt_lab_builder import gns3export
        spec = dict(self.SPEC, device=self.SPEC["device"] + [{"name": "FW", "model": "asa-5506x"}])
        with self.assertRaisesRegex(ValueError, "FW"):
            gns3export.export(spec)


if __name__ == "__main__":
    unittest.main()
