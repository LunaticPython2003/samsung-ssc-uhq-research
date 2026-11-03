"""Synthetic btsnooz v2 tests: no phone or private capture required."""
import base64
import struct
import unittest
import zlib

from ssc_btsnooz import decode_btsnooz, extract_summary, scan_service_dump
from test_ssc_snoop import SERVICE_0103, hci_acl, l2cap


def make_snooz(packets):
    # Each input is (H4 packet, btsnooz internal type).
    stream = bytearray()
    for packet, typ in packets:
        stream.extend(struct.pack("=HHIb", len(packet), len(packet), 37, typ))
        stream.extend(packet[1:])  # remove H4 type; internal type carries it
    return struct.pack("=bQ", 2, 123456789) + zlib.compress(bytes(stream))


class BtsnoozTests(unittest.TestCase):
    def test_btsnooz_acl_can_find_ssc(self):
        packet = hci_acl(l2cap(b"\x02\x02" + SERVICE_0103))
        snooz = make_snooz([(packet, 0x11)])
        payload = base64.b64encode(snooz).decode("ascii")
        dump = f"other data\n--- BEGIN:BTSNOOP_LOG_SUMMARY ---\n{payload}\n--- END:BTSNOOP_LOG_SUMMARY ---\n"
        meta = scan_service_dump(dump)
        self.assertEqual(meta["btsnooz_version"], 2)
        self.assertEqual(meta["ring_packets"], 1)
        self.assertEqual(meta["hci_packet_type_counts"], {"in_hci_2": 1})
        self.assertEqual(len(meta["ssc_avdtp_candidates"]), 1)
        self.assertEqual(meta["ssc_avdtp_candidates"][0]["codec_id"], "0x0103")
        self.assertNotIn("other data", str(meta))

    def test_event_and_command_only_cannot_find_avdtp(self):
        event = bytes.fromhex("04 0E 04 01 03 0C 00")
        cmd = bytes.fromhex("01 03 0C 00")
        blob = make_snooz([(event, 0x10), (cmd, 0x20)])
        hci, summary = decode_btsnooz(blob)
        self.assertTrue(hci.startswith(b"btsnoop\x00"))
        self.assertEqual(summary["ring_packets"], 2)
        self.assertEqual(summary["hci_packet_type_counts"]["in_hci_4"], 1)
        self.assertEqual(summary["hci_packet_type_counts"]["out_hci_1"], 1)

    def test_truncated_and_invalid_inputs(self):
        with self.assertRaises(ValueError):
            extract_summary("no Bluetooth data")
        with self.assertRaises(ValueError):
            decode_btsnooz(b"\x03" + bytes(12))
        good = make_snooz([(bytes.fromhex("04 0E 04 01 03 0C 00"), 0x10)])
        with self.assertRaises(ValueError):
            decode_btsnooz(good[:-4])
        with self.assertRaises(ValueError):
            decode_btsnooz(good[:9] + zlib.compress(b"\x01"))


if __name__ == "__main__":
    unittest.main()
