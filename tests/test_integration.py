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
        site = topology._sites[None]
        self.assertEqual(router.findtext("WORKSPACE/PHYSICAL").split(",")[-2], site["rack"].findtext("UUID_STR"))
        self.assertEqual(pc.findtext("WORKSPACE/PHYSICAL").split(",")[-2], site["building"].findtext("UUID_STR"))

    def test_cable_bends_are_segments_joined_by_break_points(self):
        topology = ptbuild.Topology()
        self.assertEqual(len(list(topology.root.iter("GEOCONNECTIONITEM"))), 0)   # no drawings from the source
        topology.configure_physical({"city": "Test City", "building": "Test Building",
                                     "closet": "Test MDF", "rack": "Test Rack"})
        sw = topology.add("switch-2960", "SW1", 100, 100, "building")
        topology.add("pc", "PC1", 200, 200, "building")
        topology.add("pc", "PC2", 300, 200, "building")
        topology.link("SW1", "FastEthernet0/2", "PC2", "FastEthernet0")
        lk = topology.link("SW1", "FastEthernet0/1", "PC1", "FastEthernet0")
        topology.route(lk, "SW1", "PC1", [[10, 20], [30, 40]], "#ff5500")
        segs = list(topology.root.iter("GEOCONNECTIONITEM"))
        self.assertEqual([(g.findtext("StartX"), g.findtext("StartY")) for g in segs][1:], [("10", "20"), ("30", "40")])
        self.assertEqual({g.findtext("Link") for g in segs}, {"1"})           # the second cable of the network
        self.assertEqual([g.findtext("IsStartCable") for g in segs], ["true", "false", "false"])
        self.assertEqual([(b.findtext("Cable1"), b.findtext("Cable2")) for b in topology.root.iter("BREAKPOINTITEM")],
                         [("0", "1"), ("1", "2")])
        self.assertEqual(lk.findtext("CABLE/GEO_VIEW_COLOR"), "#ff5500")
        self.assertEqual(segs[0].findtext("PhysicalObject1"), sw.findtext("WORKSPACE/PHYSICAL"))

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
