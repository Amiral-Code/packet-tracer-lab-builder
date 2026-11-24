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


if __name__ == "__main__":
    unittest.main()
