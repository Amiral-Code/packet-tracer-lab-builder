import random
import unittest

from pt_lab_builder import variants

SPEC = '''[lab]
id = "demo"
title = "Demo"
[[device]]
name = "R1"
model = "router-2911"
[config.answer]
R1 = """
interface G0/0
 ip address 10.10.10.1 255.255.255.0
ip access-list standard NAT
 permit 10.10.0.0 0.0.255.255
ip route 172.16.40.0 255.255.255.0 192.168.5.2
ip route 0.0.0.0 0.0.0.0 203.0.113.1
"""
'''


class VariantTests(unittest.TestCase):
    def test_a_variant_moves_every_private_network_consistently(self):
        text = variants.make(SPEC, 1, "seed")
        new10 = text.split("ip address 10.")[1].split(".")[0]
        self.assertIn(f"permit 10.{new10}.0.0 0.0.255.255", text)      # the /16 ACL follows its networks
        self.assertNotIn("10.10.10.1", text)
        self.assertIn("203.0.113.1", text)                               # documentation ranges stay
        self.assertIn('id = "demo-v01"', text)
        self.assertIn('title = "Demo (variant 01)"', text)
        second = text.split("ip route 172.")[1].split(".")[0]
        self.assertTrue(16 <= int(second) <= 31)

    def test_same_seed_same_variant_and_different_index_differs(self):
        self.assertEqual(variants.make(SPEC, 3, "s"), variants.make(SPEC, 3, "s"))
        self.assertNotEqual(variants.make(SPEC, 3, "s"), variants.make(SPEC, 4, "s"))

    def test_a_home_routers_fixed_lan_is_kept(self):
        maps = variants.mapping("192.168.0.1 192.168.5.1", random.Random(1), keep_192_168_0=True)
        self.assertEqual(maps[2][0], 0)
        self.assertNotEqual(maps[2][5], 0)

    def test_addresses_inside_longer_numbers_are_not_touched(self):
        self.assertEqual(variants.apply("110.10.10.1 and 10.10.10.1", ({10: 99}, {}, {})), "110.10.10.1 and 10.99.10.1")


if __name__ == "__main__":
    unittest.main()


class GradeReportTests(unittest.TestCase):
    def test_reports_list_every_student_and_check(self):
        import csv
        import tempfile
        from pt_lab_builder import grading
        rows = [{"student": "alice", "variant": "lab-v01", "results": [("ping", True), ("ip", True)], "error": ""},
                {"student": "bob", "variant": "lab-v02", "results": [("ping", False), ("ip", True)], "error": ""},
                {"student": "eve", "variant": "", "results": [], "error": "no student network"}]
        with tempfile.TemporaryDirectory() as d:
            csv_path, html_path = grading.write_reports(rows, d)
            table = list(csv.reader(open(csv_path)))
            self.assertEqual(table[0][:5], ["student", "variant", "score", "total", "percent"])
            self.assertEqual(table[1][2:7], ["2", "2", "100", "ok", "ok"])
            self.assertEqual(table[2][5], "FAIL")
            self.assertEqual(table[3][-1], "no student network")
            self.assertIn("1/2 students", open(html_path).read())
