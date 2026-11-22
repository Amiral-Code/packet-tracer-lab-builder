import os
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from pt_lab_builder import labgen, library
from pt_lab_builder import paths


class CoreTests(unittest.TestCase):
    def test_locally_observed_router_models_are_recognized(self):
        self.assertEqual(library.WANT[("Router", "ISR4321")], "router-isr4321")
        self.assertEqual(library.WANT[("Router", "1841")], "router-1841")

    def test_interface_name_round_trip(self):
        self.assertEqual(labgen.long_if("G0/0/1"), "GigabitEthernet0/0/1")
        self.assertEqual(labgen.short_if("FastEthernet0/24"), "Fa0/24")

    def test_merge_replaces_interface_address_and_shutdown(self):
        factory = [
            "version 15.1",
            "interface GigabitEthernet0/0",
            " no ip address",
            " shutdown",
            "!",
            "end",
        ]
        result = labgen.merge(factory, """interface G0/0
 ip address 10.0.0.1 255.255.255.252
 no shutdown
""")
        text = "\n".join(result)
        self.assertIn(" ip address 10.0.0.1 255.255.255.252", text)
        self.assertNotIn("\n shutdown\n", text)

    def test_data_directory_override(self):
        with tempfile.TemporaryDirectory() as directory:
            old = os.environ.get("PTLAB_DATA_DIR")
            os.environ["PTLAB_DATA_DIR"] = directory
            try:
                self.assertEqual(paths.user_data_dir(), Path(directory).resolve())
            finally:
                if old is None:
                    os.environ.pop("PTLAB_DATA_DIR", None)
                else:
                    os.environ["PTLAB_DATA_DIR"] = old

    def test_dhcp_addressing_row_enables_dhcp(self):
        spec = {
            "device": [{"name": "PC1", "model": "pc"}],
            "addressing": {"rows": [["PC1", "Fa0", "dhcp", ""]]},
        }
        self.assertEqual(labgen.pc_settings(spec), {"PC1": {"dhcp": True}})

    def test_mixed_start_uses_answer_then_start_overlay_and_faults(self):
        with tempfile.TemporaryDirectory() as directory:
            devices = Path(directory) / "devices"
            devices.mkdir()
            root = ET.Element("DEVICE")
            engine = ET.SubElement(root, "ENGINE")
            config = ET.SubElement(engine, "RUNNINGCONFIG")
            for line in ("version 15.1", "interface GigabitEthernet0/0", " no ip address", " shutdown", "end"):
                ET.SubElement(config, "LINE").text = line
            ET.ElementTree(root).write(devices / "router-2911.xml")
            spec = {
                "lab": {"kind": "mixed"},
                "device": [{"name": "R1", "model": "router-2911"}],
                "config": {
                    "answer": {"R1": "interface G0/0\n ip address 10.0.0.1 255.255.255.252\n no shutdown\n"},
                    "start": {"R1": "interface G0/0\n shutdown\n"},
                },
                "fault": [{"device": "R1", "find": "ip address 10.0.0.1", "replace": "ip address 10.0.0.9"}],
            }
            with patch("pt_lab_builder.labgen.library_dir", return_value=Path(directory)):
                start = "\n".join(labgen.configs_for(spec, "start")["R1"])
                answer = "\n".join(labgen.configs_for(spec, "answer")["R1"])
            self.assertIn("ip address 10.0.0.9 255.255.255.252", start)
            self.assertIn("\n shutdown\n", start)
            self.assertIn("ip address 10.0.0.1 255.255.255.252", answer)
            self.assertNotIn("ip address 10.0.0.9", answer)


if __name__ == "__main__":
    unittest.main()
