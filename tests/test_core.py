import os
from pathlib import Path
import tempfile
import unittest

from pt_lab_builder import labgen
from pt_lab_builder import paths


class CoreTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
