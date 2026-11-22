import unittest
import xml.etree.ElementTree as ET

from pt_lab_builder.library import _has_usable_physical_workspace
from pt_lab_builder.ptbuild import stack_rack


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


class RackStacking(unittest.TestCase):
    def test_devices_stack_by_model_height(self):
        xs = stack_rack([("router-2911", None), ("switch-2960", None), ("server", None)])
        self.assertEqual(xs, {0: 0, 1: 7, 2: 11})

    def test_slot_orders_devices_from_the_top(self):
        xs = stack_rack([("switch-2960", 2), ("router-1941", 1)])
        self.assertEqual(xs, {1: 0, 0: 8})

    def test_reserved_power_unit_is_skipped(self):
        xs = stack_rack([("switch-2960", None)] * 6, reserved=[(20, 24)])
        self.assertEqual(sorted(xs.values()), [0, 4, 8, 12, 16, 24])


if __name__ == "__main__":
    unittest.main()
