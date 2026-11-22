import os
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
import io

from pt_lab_builder import labgen, ptlab, ptbuild


REQUIRED = ("PTLAB_LIBRARY_DIR", "PTLAB_PKA_BASE", "PTLAB_PTCRYPT")


@unittest.skipUnless(all(os.environ.get(name) for name in REQUIRED),
                     "set PTLAB_LIBRARY_DIR, PTLAB_PKA_BASE, and PTLAB_PTCRYPT for integration tests")
class IntegrationTests(unittest.TestCase):
    def test_physical_workspace_has_no_ghost_devices(self):
        topology = ptbuild.Topology()
        topology.configure_physical({"city": "Test City", "building": "Test Building",
                                     "closet": "Test MDF", "rack": "Test Rack"})
        router = topology.add("router-2911", "R1", 100, 100, {"location": "rack", "slot": 1})
        pc = topology.add("pc", "PC1", 200, 200, {"location": "building", "x": 200, "y": 300})
        names = [node.findtext("NAME") for node in topology.root.findall(".//NODE")
                 if node.findtext("TYPE") == "6"]
        self.assertEqual(names, ["Power Distribution Device0", "R1", "PC1"])
        self.assertIn("Test Rack", [node.findtext("NAME") for node in topology.root.findall(".//NODE")])
        self.assertEqual(router.findtext("WORKSPACE/PHYSICAL").split(",")[-2], topology._rack.findtext("UUID_STR"))
        self.assertEqual(pc.findtext("WORKSPACE/PHYSICAL").split(",")[-2], topology._building.findtext("UUID_STR"))

    def test_example_builds_and_round_trips(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            activity = Path(labgen.build(root / "examples" / "static-two-sites.toml", output_dir=output))
            self.assertTrue(activity.is_file())
            self.assertTrue((output / "static-two-sites-answer.md").is_file())
            tree = ptlab.read_pkt(activity)
            self.assertEqual(tree.getroot().tag, "PACKETTRACER5_ACTIVITY")
            networks = tree.getroot().findall("PACKETTRACER5")
            self.assertEqual(len(networks), 3)
            physical_names = [node.findtext("NAME") for node in networks[0].findall(".//NODE")
                              if node.findtext("TYPE") == "6"]
            self.assertNotIn("CORE", physical_names)
            self.assertEqual(len(physical_names), len(set(physical_names)))
            self.assertIn("HQ-R1", physical_names)
            self.assertIn("HQ-PC1", physical_names)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(labgen.check(root / "examples" / "static-two-sites.toml", activity), 1)
            spec = labgen.load_spec(root / "examples" / "static-two-sites.toml")
            _, checks = labgen.compile_grade(spec)
            answer = ET.ElementTree(networks[2])
            self.assertTrue(all(ptlab.grade({"check": checks}, answer, checks, quiet=True)))


if __name__ == "__main__":
    unittest.main()
