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
        self.assertError(lambda s: s["grade"]["items"].append("vlan SW1 10"), "unknown statement")

    def test_no_grade_items(self):
        self.assertError(lambda s: s["grade"].update(items=[]), "score nothing")

    def test_subinterface_and_svi_are_allowed(self):
        spec_errors = self.lint(lambda s: s["addressing"]["rows"].append(["SW1", "Vlan99", "10.99.0.2/24", ""])).errors
        self.assertEqual(spec_errors, [])


if __name__ == "__main__":
    unittest.main()
