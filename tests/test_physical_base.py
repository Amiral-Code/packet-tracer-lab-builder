import unittest
import xml.etree.ElementTree as ET

from pt_lab_builder.library import _has_usable_physical_workspace


def network(node_types, with_pc=True):
    """A minimal network root with a physical workspace holding nodes of the given TYPEs."""
    root = ET.Element("PACKETTRACER5")
    devices = ET.SubElement(ET.SubElement(root, "NETWORK"), "DEVICES")
    if with_pc:
        device = ET.SubElement(devices, "DEVICE")
        engine = ET.SubElement(device, "ENGINE")
        ET.SubElement(engine, "TYPE").text = "Pc"
        ET.SubElement(ET.SubElement(device, "WORKSPACE"), "PHYSICAL").text = "{a},{b}"
    workspace = ET.SubElement(root, "PHYSICALWORKSPACE")
    for kind in node_types:
        ET.SubElement(ET.SubElement(workspace, "NODE"), "TYPE").text = kind
    return root


class PhysicalBaseSelection(unittest.TestCase):
    def test_full_hierarchy_is_usable(self):
        self.assertTrue(_has_usable_physical_workspace(network(["1", "2", "3", "4", "6"])))

    def test_missing_rack_is_rejected(self):
        # industrial samples (e.g. a PLC/HMI demo) have no rack: every router/switch placement failed
        self.assertFalse(_has_usable_physical_workspace(network(["1", "2", "3", "6"])))

    def test_missing_pc_is_rejected(self):
        self.assertFalse(_has_usable_physical_workspace(network(["1", "2", "3", "4"], with_pc=False)))


if __name__ == "__main__":
    unittest.main()
