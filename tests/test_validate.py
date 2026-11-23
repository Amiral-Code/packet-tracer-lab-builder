import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pt_lab_builder import validate

INDEX = {
    "router-2911": {"interfaces": ["GigabitEthernet0/0", "GigabitEthernet0/1", "GigabitEthernet0/2", "Vlan1"]},
    "switch-2960": {"interfaces": ["FastEthernet0/1", "FastEthernet0/2", "GigabitEthernet0/1", "Vlan1"]},
    "pc": {"interfaces": ["FastEthernet0"]},
    "server": {"interfaces": ["FastEthernet0"]},
}

GOOD = {
    "lab": {"title": "t", "scenario": "s", "kind": "configure"},
    "device": [{"name": "R1", "model": "router-2911"}, {"name": "SW1", "model": "switch-2960"},
               {"name": "PC1", "model": "pc"}],
    "link": [{"a": "R1 G0/0", "b": "SW1 G0/1"}, {"a": "SW1 Fa0/1", "b": "PC1 Fa0"}],
    "addressing": {"rows": [["R1", "G0/0", "192.168.1.1/24", ""],
                            ["R1", "G0/0.10", "192.168.10.1/24", ""],
                            ["PC1", "Fa0", "192.168.1.10/24", "192.168.1.1"]]},
    "grade": {"items": ["ip R1 G0/0 192.168.1.1/24", "up R1 G0/0", "gw PC1 192.168.1.1"]},
}


class LintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        devices = Path(self.tmp.name) / "devices"
        devices.mkdir()
        (devices / "index.json").write_text(json.dumps(INDEX))
        self.patch = patch("pt_lab_builder.validate.library_dir", return_value=Path(self.tmp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def lint(self, mutate=None):
        spec = copy.deepcopy(GOOD)
        if mutate:
            mutate(spec)
        return validate.lint(spec)

    def assertError(self, mutate, fragment):
        errors = self.lint(mutate).errors
        self.assertTrue(any(fragment in e for e in errors), f"{fragment!r} not in {errors}")

    def test_good_spec_is_clean(self):
        self.assertEqual(self.lint().errors, [])

    def test_missing_port(self):
        self.assertError(lambda s: s["link"][0].update(a="R1 G0/7"), "has no port GigabitEthernet0/7")

    def test_port_cabled_twice(self):
        self.assertError(lambda s: s["link"][1].update(a="SW1 G0/1"), "cabled twice")

    def test_unknown_model(self):
        self.assertError(lambda s: s["device"][0].update(model="router-9999"), "unknown model")

    def test_duplicate_address(self):
        self.assertError(lambda s: s["addressing"]["rows"][2].__setitem__(2, "192.168.1.1/24"), "is used by both")

    def test_gateway_outside_subnet(self):
        self.assertError(lambda s: s["addressing"]["rows"][2].__setitem__(3, "10.0.0.1"), "outside its subnet")

    def test_network_address(self):
        self.assertError(lambda s: s["addressing"]["rows"][0].__setitem__(2, "192.168.1.0/24"), "network or broadcast")

    def test_unknown_grade_statement(self):
        self.assertError(lambda s: s["grade"]["items"].append("eigrp R1 10"), "unknown statement")

    def test_new_statements_are_checked(self):
        self.assertError(lambda s: s["grade"]["items"].append("vlan SW1 10"), "expects 3 fields")
        self.assertError(lambda s: s["grade"]["items"].append("access SW1 Fa0/9 10"), "has no port")
        self.assertError(lambda s: s["grade"]["items"].append("stp SW1 10 5000"), "multiple of 4096")
        self.assertError(lambda s: s["grade"]["items"].append("route R1 10.0.0.1/24 10.0.0.2"), "host bits")
        self.assertError(lambda s: s["grade"]["items"].append("trunk SW1 G0/1 permit 10"), "allowed LIST")
        self.assertError(lambda s: s["grade"]["items"].append("in R1 interface G0/0 no shutdown"), "quote both")
        self.assertError(lambda s: s["grade"]["items"].append("ping PC1 SW1"), "no address")
        self.assertError(lambda s: s["grade"]["items"].append("tcp PC1 R1 70000"), "1-65535")
        self.assertError(lambda s: s["grade"]["items"].append("udp PC1 R1 0"), "UDP port must be 1-65535")
        self.assertError(lambda s: s["grade"]["items"].append("udp PC1 R1"), "udp SRC DST PORT")
        self.assertError(lambda s: s["grade"]["items"].append("udp PC1 R1 53"), "UDP/53 is DNS")
        self.assertError(lambda s: s["grade"]["items"].append("dns PC1 R1"), "unknown")
        self.assertError(lambda s: s["grade"]["items"].append("https PC1 NOPE"), "unknown device")

    def test_iteration_2_statements(self):
        errors = self.lint(lambda s: s["grade"]["items"].extend([
            'in R1 "interface GigabitEthernet0/0" "ipv6 address 2001:DB8::1/64"', "ip PC1 Fa0 in 192.168.1.0/24",
            "ip6 R1 G0/0 2001:db8::1/64", "route6 R1 ::/0 2001:db8::2", "gw PC1 192.168.1.1|192.168.1.254",
            "portsec SW1 Fa0/1 max 2 sticky violation restrict", "portfast SW1 Fa0/1", "desc R1 G0/0 ~lan",
            "banner R1 any", "nat R1 G0/0 inside", "acl R1 G0/0 100 in", "hsrp R1 G0/0 1 192.168.1.254 priority 110 preempt",
            "pool R1 LAN 192.168.1.0/24 gw 192.168.1.1", "secret R1 class", "user R1 admin pw", "rid R1 1 1.1.1.1",
            "passive R1 1 G0/0"])).errors
        self.assertEqual(errors, [])
        self.assertError(lambda s: s["grade"]["items"].append("portsec SW1 Fa0/1 violation drop"), "violation is")
        self.assertError(lambda s: s["grade"]["items"].append("nat PC1 Fa0 inside"), "is a host")
        self.assertError(lambda s: s["grade"]["items"].append("gw R1 192.168.1.1"), "not a host")
        self.assertError(lambda s: s["grade"]["items"].append("ping6 PC1 R1"), "no IPv6 address")
        self.assertError(lambda s: s["grade"]["items"].append("ip6 R1 G0/0 10.0.0.1/24"), "IPv6")

    def test_config_only_grading_is_flagged(self):
        warnings = [m for level, m in self.lint() if level == "warning"]
        self.assertTrue(any("only configuration is graded" in w for w in warnings), warnings)
        warnings = [m for level, m in self.lint(lambda s: s["grade"]["items"].append("ping PC1 R1")) if level == "warning"]
        self.assertFalse(any("only" in w for w in warnings), warnings)

    def test_valid_new_statements_pass(self):
        errors = self.lint(lambda s: s["grade"]["items"].extend([
            "vlan SW1 10 SALES", "access SW1 Fa0/1 10", "trunk SW1 G0/1 allowed 10,20 native 99",
            "stp SW1 10 4096", "route R1 0.0.0.0/0 192.168.1.254", "ospf R1 1 192.168.1.0/24 0",
            'in R1 "interface GigabitEthernet0/0" "no shutdown"', "ping PC1 R1", "ping PC1 R1 8.8.8.8 fail",
            "http PC1 R1", "https PC1 R1 fail", "ssh PC1 R1 192.168.1.1", "telnet PC1 R1",
            "tcp PC1 R1 8443"])).errors
        self.assertEqual(errors, [])

    def test_activity_controls_are_checked(self):
        self.assertError(lambda s: s.update(activity={"timer": "clock"}), "timer must be")
        self.assertError(lambda s: s.update(activity={"timer": "countdown", "countdown_minutes": 0}),
                         "positive integer")
        self.assertError(lambda s: s.update(activity={"answer_convergence_ms": -1}), "non-negative integer")
        self.assertError(lambda s: s.update(activity={"profile_locked": "yes"}), "true or false")
        self.assertError(lambda s: s.update(activity={"locking_preset": "mystery"}), "locking_preset")

    def test_grade_points_are_checked(self):
        self.assertError(lambda s: s["grade"].update(points={"hostname R1 EDGE": 2}), "not present")
        self.assertError(lambda s: s["grade"].update(points={s["grade"]["items"][0]: 0}), "positive integer")

    def test_valid_grade_points_pass(self):
        errors = self.lint(lambda s: s["grade"].update(points={s["grade"]["items"][0]: 3})).errors
        self.assertEqual(errors, [])

    def test_valid_activity_controls_pass(self):
        errors = self.lint(lambda s: s.update(activity={"timer": "countdown", "countdown_minutes": 45,
                                                        "answer_convergence_ms": 30000,
                                                        "wizard_password": "lab-lock",
                                                        "profile_locked": True,
                                                        "locking_preset": "cli-only",
                                                        "complete_feedback": "Well done.",
                                                        "incomplete_feedback": "Review the failed items."})).errors
        self.assertEqual(errors, [])

    def test_no_grade_items(self):
        self.assertError(lambda s: s["grade"].update(items=[]), "score nothing")

    def test_sites_are_checked(self):
        self.assertError(lambda s: s.update(site=[{"name": "HQ", "devices": ["R1", "R9"]}]), "unknown device R9")
        self.assertError(lambda s: s.update(site=[{"name": "HQ", "devices": ["R1"]},
                                                  {"name": "BR", "devices": ["R1"]}]), "in two sites")

    def test_full_rack_is_rejected(self):
        def fill(s):
            s["device"] += [{"name": f"SRV{i}", "model": "server"} for i in range(9)]
        self.assertError(fill, "is full")

    def test_racks_are_per_site(self):
        def split(s):
            s["device"] += [{"name": f"SRV{i}", "model": "server"} for i in range(8)]
            s["site"] = [{"name": "A", "devices": [f"SRV{i}" for i in range(4)]},
                         {"name": "B", "devices": [f"SRV{i}" for i in range(4, 8)]}]
        self.assertFalse([e for e in self.lint(split).errors if "full" in e])

    def test_subinterface_and_svi_are_allowed(self):
        spec_errors = self.lint(lambda s: s["addressing"]["rows"].append(["SW1", "Vlan99", "10.99.0.2/24", ""])).errors
        self.assertEqual(spec_errors, [])


if __name__ == "__main__":
    unittest.main()
