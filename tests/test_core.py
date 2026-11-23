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

    def test_merge_keeps_negations_shown_in_the_running_config(self):
        out = labgen.merge(["version 15.0", "ip domain-lookup", "interface GigabitEthernet0/1", " switchport mode access",
                            "end"],
                           "interface G0/1\n no switchport\n ip address 10.0.0.1 255.255.255.252\nno ip domain-lookup\n")
        i = out.index("interface GigabitEthernet0/1")
        self.assertIn(" no switchport", out[i + 1:i + 4])
        self.assertIn("no ip domain-lookup", out)
        self.assertNotIn("ip domain-lookup", out)

    def test_merge_still_removes_with_other_negations(self):
        out = labgen.merge(["version 15.0", "interface FastEthernet0/1", " switchport access vlan 10", "end"],
                           "interface Fa0/1\n no switchport access vlan 10\n")
        i = out.index("interface FastEthernet0/1")
        self.assertNotIn(" switchport access vlan 10", out)
        self.assertNotIn(" no switchport access vlan 10", out)

    def test_global_negation_does_not_shift_later_sections(self):
        # "no ip routing" removes a global line; the interface edits after it must still land in their own blocks
        answer = ["version 15.0", "ip routing", "interface GigabitEthernet0/1", " ip address 10.0.0.1 255.255.255.252",
                  "interface Vlan10", " ip address 10.10.10.1 255.255.255.0", " ipv6 address 2001:DB8:10::1/64", "end"]
        out = labgen.merge(answer, "no ip routing\ninterface Vlan10\n no ip address\n"
                                   " no ipv6 address 2001:DB8:10::1/64\n shutdown\n")
        g, v = out.index("interface GigabitEthernet0/1"), out.index("interface Vlan10")
        self.assertEqual(out[g + 1], " ip address 10.0.0.1 255.255.255.252")
        self.assertEqual(out[v + 1:v + 3], [" no ip address", " shutdown"])
        self.assertNotIn(" ipv6 address 2001:DB8:10::1/64", out)
        self.assertNotIn("ip routing", out)

    def test_fitted_cards_select_a_serial_variant_and_plain_keys_need_no_card(self):
        def router(model, cards=(), modules=()):
            d = ET.fromstring(f'<DEVICE><ENGINE><TYPE model="{model}">Router</TYPE></ENGINE><MODULE/></DEVICE>')
            for typ, names in (("eInterfaceCard", cards), ("ePtRouterModule", modules)):
                for name in names:
                    m = ET.SubElement(d.find("MODULE"), "MODULE")
                    ET.SubElement(m, "TYPE").text = typ
                    ET.SubElement(m, "MODEL").text = name
            return d
        self.assertEqual(library.library_key(router("1941")), "router-1941")
        self.assertEqual(library.library_key(router("1941", ["HWIC-2T", "WIC-Cover"])), "router-1941-serial")
        self.assertIsNone(library.library_key(router("1941", ["HWIC-2T", "HWIC-2T"])))   # no such variant
        self.assertEqual(library.library_key(router("ISR4331", ["NIM-2T"])), "router-isr4331-serial")
        stock = library.STOCK_PT_MODULES["Router-PT"]
        self.assertEqual(library.library_key(router("Router-PT", modules=stock)), "router-pt")
        self.assertIsNone(library.library_key(router("Router-PT", modules=stock[:-1])))

    def test_serial_link_names_the_dce_end_and_has_no_cable_type(self):
        from pt_lab_builder import ptbuild
        root = ET.fromstring("<PACKETTRACER5><NETWORK><DEVICES/><LINKS/></NETWORK></PACKETTRACER5>")
        devs = []
        for i, name in enumerate(("R1", "R2")):
            d = ET.fromstring(f"<DEVICE><ENGINE><NAME>{name}</NAME><SAVE_REF_ID>save-ref-id:{i}</SAVE_REF_ID>"
                              f"</ENGINE><WORKSPACE><LOGICAL><DEV_ADDR>{i}</DEV_ADDR></LOGICAL></WORKSPACE></DEVICE>")
            root.find("NETWORK/DEVICES").append(d)
            devs.append(d)
        tpl = ET.fromstring(ptbuild.LINK_TEMPLATE)
        lk = ptbuild.link(root, devs[0], "Serial0/0/0", devs[1], "Serial0/0/1", cable="eSerialDTE", kind="eSerial", like=tpl)
        c = lk.find("CABLE")
        self.assertEqual(lk.findtext("TYPE"), "eSerial")
        self.assertIsNone(c.find("TYPE"))
        self.assertEqual((c.findtext("DCEDEV"), c.findtext("DCEPORT")), ("save-ref-id:1", "Serial0/0/1"))
        from pt_lab_builder import ptlab
        links = ptlab.cables(ET.ElementTree(root))
        self.assertTrue(ptlab.run_check({"cable": ("R2", "Serial0/0/1", "R1", "Serial0/0/0"),
                                         "cable_type": "eSerialDCE"}, {}, links))
        self.assertFalse(ptlab.run_check({"cable": ("R1", "Serial0/0/0", "R2", "Serial0/0/1"),
                                          "cable_type": "eSerialDCE"}, {}, links))

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
