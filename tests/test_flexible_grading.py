"""Iteration 2: several right answers, IPv6, and the item types read from real activities."""

import ipaddress
import random
import re
import unittest
import xml.etree.ElementTree as ET

from pt_lab_builder import labgen, ptlab
from test_grading import device, tree


def pc(name, ip="", mask="", gw=""):
    d = ET.Element("DEVICE")
    eng = ET.SubElement(d, "ENGINE")
    ET.SubElement(eng, "NAME").text = name
    ET.SubElement(eng, "SAVE_REF_ID").text = f"save-ref-id:{abs(hash(name))}"
    port = ET.SubElement(ET.SubElement(ET.SubElement(eng, "MODULE"), "SLOT"), "PORT")
    for tag, val in (("TYPE", "eCopperFastEthernet"), ("IP", ip), ("SUBNET", mask), ("PORT_GATEWAY", gw),
                     ("PORT_DHCP_ENABLE", "false")):
        ET.SubElement(port, tag).text = val
    return d


def spec(*items, rows=(), answer=None):
    return {"lab": {"title": "t", "scenario": "s"},
            "device": [{"name": "SW1", "model": "switch-2960"}, {"name": "R1", "model": "router-2911"},
                       {"name": "PC1", "model": "pc"}, {"name": "PC2", "model": "pc"}],
            "addressing": {"rows": list(rows)}, "grade": {"items": list(items)},
            "config": {"answer": answer or {}}}


def grade(statements, devs, **kw):
    items, checks = labgen.compile_grade(spec(*statements, **kw))
    return items, ptlab.grade({"check": checks}, tree(*devs), checks, quiet=True)


def leaf(items, node_id):
    comp = ptlab.comparisons(items)
    return next(n for n in comp.iter("NODE") if n.findtext("ID") == node_id).find("NAME")


class SeveralRightAnswers(unittest.TestCase):
    def test_host_regex_matches_exactly_the_usable_hosts(self):
        rnd = random.Random(7)
        for net in ("192.168.10.0/24", "172.16.0.64/26", "10.1.2.0/23", "10.0.0.0/8", "192.168.1.0/30",
                    "10.255.255.0/31"):
            n = ipaddress.ip_network(net)
            rx = labgen.host_regex(net)
            lo, hi = int(n.network_address), int(n.broadcast_address)
            for a in [lo, hi, lo - 1, hi + 1] + [rnd.randrange(lo, hi + 1) for _ in range(300)] \
                    + [rnd.randrange(2 ** 32) for _ in range(300)]:
                a = ipaddress.ip_address(a % 2 ** 32)
                want = a in n and (n.prefixlen >= 31 or a not in (n.network_address, n.broadcast_address))
                self.assertEqual(bool(re.search(rx, str(a))), want, f"{net} {a} {rx}")
        self.assertEqual(labgen.host_regex("172.16.0.64/26"),
                         r"^172\.16\.0\.(6[5-9]|[7-9][0-9]|1[0-1][0-9]|12[0-6])$")

    def test_any_address_in_a_subnet(self):
        rows = [["PC1", "Fa0", "192.168.10.10/24", "192.168.10.1"]]
        st = "ip PC1 Fa0 in 192.168.10.0/24"
        items, _ = labgen.compile_grade(spec(st, rows=rows))
        name = leaf(items, "IP Address")
        self.assertEqual(name.get("variableName"), "{{RegEx:%s}}" % labgen.host_regex("192.168.10.0/24"))
        self.assertEqual(name.get("nodeValue"), "192.168.10.10")        # the answer network's own value
        self.assertEqual(leaf(items, "Subnet Mask").get("variableName"), "")
        for ip, ok in (("192.168.10.77", True), ("192.168.10.0", False), ("192.168.10.255", False),
                       ("192.168.11.5", False)):
            _, res = grade([st], [pc("PC1", ip, "255.255.255.0")], rows=rows)
            self.assertEqual(all(res), ok, ip)

    def test_any_address_on_a_router_interface(self):
        r = "interface GigabitEthernet0/0\n ip address 192.168.10.254 255.255.255.0\n"
        _, res = grade(["ip R1 G0/0 in 192.168.10.0/24"], [device("R1", r)])
        self.assertEqual(res, [True])

    def test_gateway_alternatives(self):
        st = "gw PC1 192.168.1.1|192.168.1.254"
        items, _ = labgen.compile_grade(spec(st))
        self.assertEqual(items[0]["regex"], r"^(192\.168\.1\.1|192\.168\.1\.254)$")
        for gw, ok in (("192.168.1.254", True), ("192.168.1.1", True), ("192.168.1.2", False)):
            _, res = grade([st], [pc("PC1", gw=gw)])
            self.assertEqual(res, [ok], gw)

    def test_description_and_banner_matching(self):
        r = ("hostname R1\nbanner motd ^CAuthorized access only!^C\ninterface GigabitEthernet0/0\n"
             " description Link to LAN 3\n")
        items, res = grade(["desc R1 G0/0 ~lan", "desc R1 G0/0 any", 'desc R1 G0/0 "Link to LAN 3"',
                            "banner R1 ~authorized", "banner R1 any"], [device("R1", r)],
                           answer={"R1": r})
        self.assertTrue(all(res), res)
        self.assertEqual(items[0]["regex"], ".*[Ll][Aa][Nn].*")
        self.assertEqual(items[0]["value"], "Link to LAN 3")
        self.assertEqual(items[1]["regex"], labgen.NON_EMPTY_REGEX)
        self.assertEqual(items[2]["regex"], "")
        _, res = grade(["desc R1 G0/0 ~wan", "banner R1 ~warning"], [device("R1", r)])
        self.assertEqual(res, [False, False])


class IPv6(unittest.TestCase):
    def test_addresses_are_shown_the_packet_tracer_way(self):
        self.assertEqual(labgen.v6("2001:db8:0:1:0:0:0:1/64"), "2001:DB8:0:1::1/64")
        self.assertEqual(labgen.pt_line("ipv6 route 2001:db8:10::/64 2001:db8:0:1::2"),
                         "ipv6 route 2001:DB8:10::/64 2001:DB8:0:1::2")

    def test_line_ids_write_colons_as_dashes(self):
        # seen in an activity saved by Packet Tracer: 'ipv6 route 2001-DB8-10--/64 2001-DB8-0-1--2'
        items, _ = labgen.compile_grade(spec("route6 R1 2001:db8:10::/64 2001:db8:0:1::2",
                                             'in R1 "interface G0/0" "ipv6 address 2001:db8:0:ff::1/64"'))
        self.assertEqual(items[0]["line_id"], "ipv6 route 2001-DB8-10--/64 2001-DB8-0-1--2")
        self.assertEqual(items[0]["value"], "ipv6 route 2001:DB8:10::/64 2001:DB8:0:1::2")
        self.assertEqual(items[1]["line_id"], "interface GigabitEthernet0/0 ipv6 address 2001-DB8-0-FF--1/64")

    def test_router_ipv6_address_items_and_check(self):
        r = "interface GigabitEthernet0/0\n ipv6 address 2001:db8:0:ff::1/64\n"
        items, res = grade(["ip6 R1 G0/0 2001:DB8:0:FF::1/64"], [device("R1", r)])
        self.assertEqual(res, [True])
        comp = ptlab.comparisons(items)
        paths = [" > ".join(n.findtext("ID") for n in chain) for chain in _chains(comp.find("NODE"))]
        self.assertIn("Network > R1 > Ports > GigabitEthernet0/0 > Ipv6 Address > 2001:DB8:0:FF::1 > IP Address",
                      paths)
        self.assertIn("Network > R1 > Ports > GigabitEthernet0/0 > Ipv6 Address > 2001:DB8:0:FF::1 > Prefix", paths)

    def test_host_ipv6_from_a_second_addressing_row(self):
        rows = [["PC1", "Fa0", "192.168.1.10/24", "192.168.1.1"], ["PC1", "Fa0", "2001:db8:1::10/64", "fe80::1"]]
        settings = labgen.pc_settings(spec(rows=rows))["PC1"]
        self.assertEqual(settings["ip"], "192.168.1.10")
        self.assertEqual(settings["ip6"], ["2001:DB8:1::10/64"])
        self.assertEqual(settings["gw6"], "FE80::1")
        d = pc("PC1")
        ptlab.set_pc(d, settings)
        self.assertEqual(d.findtext(".//IPV6_ADDRESSES/IPV6_ADDRESS/ADDRESS"), "2001:DB8:1::10")
        self.assertEqual(d.findtext("ENGINE/GATEWAYV6"), "FE80::1")
        _, res = grade(["ip6 PC1 Fa0 2001:db8:1::10/64", "gw6 PC1 FE80::1"], [d], rows=rows)
        self.assertEqual(res, [True, True])

    def test_ping6_is_a_type_20_pdu_to_an_address(self):
        rows = [["PC1", "Fa0", "2001:db8:1::10/64", "fe80::1"], ["PC2", "Fa0", "2001:db8:2::10/64", "fe80::1"]]
        s = spec("ping6 PC1 PC2", rows=rows)
        tests = labgen.connectivity_tests(s)
        self.assertEqual((tests[0]["protocol"], tests[0]["ip"], tests[0]["src_ip"]),
                         ("icmp6", "2001:DB8:2::10", "2001:DB8:1::10"))
        answer = tree(pc("PC1"), pc("PC2"))
        ptlab.add_connectivity_tests(answer, tests)
        pdu = answer.getroot().find("SCENARIOSET/SCENARIO/PDU")
        self.assertEqual(pdu.findtext("TYPE"), "20")
        self.assertEqual(pdu.findtext("DESTINATION"), "2001:DB8:2::10")
        self.assertEqual(pdu.findtext("PDU/SRCADDR"), "2001:DB8:1::10")
        self.assertEqual(pdu.findtext("PDU/PDU/TYPE"), "CIcmpMessage")

    def test_udp_is_a_type_2_pdu_like_packet_tracers_complex_pdu(self):
        # shape copied from a Complex PDU (DNS, and OTHER/UDP port 69) saved by Packet Tracer
        rows = [["PC1", "Fa0", "10.0.0.10/24", "10.0.0.1"], ["PC2", "Fa0", "10.0.0.1/24", ""]]
        s = spec("udp PC1 PC2 5555", "udp PC1 PC2 7000 fail", rows=rows)
        tests = labgen.connectivity_tests(s)
        self.assertEqual([(t["protocol"], t["port"], t["ip"], t["succeed"]) for t in tests],
                         [("udp", 5555, "10.0.0.1", True), ("udp", 7000, "10.0.0.1", False)])
        answer = tree(pc("PC1"), pc("PC2"))
        ptlab.add_connectivity_tests(answer, tests)
        dns, tftp = answer.getroot().findall("SCENARIOSET/SCENARIO/PDU")
        self.assertEqual((dns.findtext("TYPE"), dns.find("TYPE").get("patterned")), ("2", "no"))
        self.assertEqual(dns.findtext("DESTINATION"), "10.0.0.1")
        self.assertEqual(dns.findtext("PDU/SRCADDR"), "10.0.0.10")
        self.assertEqual(dns.findtext("PDU/TTL"), "32")
        self.assertEqual([dns.findtext("PDU/PDU/" + t) for t in ("TYPE", "SRC", "DST", "LENGTH")],
                         ["CUdpHeader", "5000", "5555", "8"])
        self.assertEqual(tftp.findtext("PDU/PDU/DST"), "7000")
        self.assertEqual(tftp.findtext("TEST_CONDITION"), "2")


def _chains(node, path=()):
    path = path + (node,)
    kids = node.findall("NODE")
    if not kids:
        yield path
    for k in kids:
        yield from _chains(k, path)


class NewItemTypes(unittest.TestCase):
    def test_enable_secret_hash_matches_real_activities(self):
        self.assertEqual(ptlab.md5crypt("class"), "$1$mERr$9cTjUIEqNGurQiFU.ZeCi1")
        self.assertEqual(ptlab.md5crypt("Ciscoenpa55"), "$1$mERr$Amm/da5NtiazLuZDbgqZ60")
        items, res = grade(["secret R1 class", "user R1 admin Secr3t"],
                           [device("R1", "enable secret 5 $1$mERr$9cTjUIEqNGurQiFU.ZeCi1\n"
                                         "username admin secret Secr3t\n")])
        self.assertEqual(res, [True, True])
        self.assertEqual(items[1]["value"], "admin " + ptlab.md5crypt("Secr3t"))
        _, res = grade(["secret R1 class"], [device("R1", "enable password class\n")])
        self.assertEqual(res, [False])

    def test_port_security_uses_observed_values(self):
        sw = ("interface FastEthernet0/1\n switchport mode access\n switchport port-security\n"
              " switchport port-security maximum 2\n switchport port-security mac-address sticky\n"
              " switchport port-security violation restrict\n spanning-tree portfast\n")
        items, res = grade(["portsec SW1 Fa0/1 max 2 sticky violation restrict", "portfast SW1 Fa0/1"],
                           [device("SW1", sw)])
        self.assertTrue(all(res), res)
        self.assertEqual([(i["kind"], i["value"]) for i in items],
                         [("psec_on", "1"), ("psec_max", "2"), ("psec_sticky", "1"), ("psec_violation", "2"),
                          ("portfast", "1")])
        items, _ = labgen.compile_grade(spec("portsec SW1 Fa0/1 violation protect"))
        self.assertEqual((items[1]["kind"], items[1]["value"]), ("psec_violation", "1"))   # as Packet Tracer fills it
        # a protect line typed as a sub-command carries Packet Tracer's trailing space
        items, _ = labgen.compile_grade(spec('in SW1 "interface Fa0/1" "switchport port-security violation protect"'))
        self.assertEqual(items[0]["line_id"], "interface FastEthernet0/1 switchport port-security violation protect ")

    def test_nat_acl_hsrp_pool_ospf_extras(self):
        r = ("interface GigabitEthernet0/0\n ip nat inside\n ip access-group WEB in\n standby 1 ip 10.0.0.254\n"
             " standby 1 priority 110\n standby 1 preempt\ninterface GigabitEthernet0/1\n ip nat outside\n"
             "ip dhcp pool LAN\n network 10.0.0.0 255.255.255.0\n default-router 10.0.0.1\n dns-server 8.8.8.8\n"
             "router ospf 1\n router-id 1.1.1.1\n passive-interface GigabitEthernet0/0\n")
        items, res = grade(["nat R1 G0/0 inside", "nat R1 G0/1 outside", "acl R1 G0/0 WEB in",
                            "hsrp R1 G0/0 1 10.0.0.254 priority 110 preempt",
                            "pool R1 LAN 10.0.0.0/24 gw 10.0.0.1 dns 8.8.8.8", "rid R1 1 1.1.1.1",
                            "passive R1 1 G0/0"], [device("R1", r)])
        self.assertTrue(all(res), res)
        kinds = {(i["kind"], i.get("value")) for i in items}
        self.assertTrue({("nat", "1"), ("nat", "2"), ("acl_in", "WEB"), ("pool_start", "10.0.0.0"),
                         ("pool_gw", "10.0.0.1")} <= kinds)
        self.assertIn("interface GigabitEthernet0/0 standby 1 preempt", {i.get("line_id") for i in items})


if __name__ == "__main__":
    unittest.main()
