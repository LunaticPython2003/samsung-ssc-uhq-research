"""Offline test vectors for Samsung SSC AVDTP in Bluetooth btsnoop files."""
from __future__ import annotations
import struct
import tempfile
import unittest
from pathlib import Path

from ssc_snoop import decode_avdtp, scan_btsnoop, sample_rates

SERVICE_0103 = bytes.fromhex("07 09 00 ff 75 00 00 00 03 01 30")
SERVICE_0E03 = bytes.fromhex("07 09 00 ff 75 00 00 00 03 0e 80")


def hci_acl(data: bytes, pb: int = 2) -> bytes:
    return bytes([0x02]) + struct.pack("<HH", 0x0001 | (pb << 12), len(data)) + data


def hci_record(data: bytes, flags: int = 1) -> bytes:
    return struct.pack(">IIIIQ", len(data), len(data), flags, 0, 0) + data


def btsnoop(packets: list[bytes]) -> bytes:
    return b"btsnoop\x00" + struct.pack(">II", 1, 1002) + b"".join(
        hci_record(packet) for packet in packets
    )


def l2cap(data: bytes) -> bytes:
    return struct.pack("<HH", len(data), 0x0040) + data


class SscSnoopTests(unittest.TestCase):
    def test_rate_flags(self):
        self.assertEqual(sample_rates(0xB0), (48000, 44100, 96000))
        self.assertEqual(sample_rates(0x0F), ())

    def test_get_capabilities_accept(self):
        avdtp = b"\x02\x02" + SERVICE_0103
        matches = decode_avdtp(avdtp, 7, 1, 0x0040, "incoming")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].codec_id, "0x0103")
        self.assertEqual(matches[0].raw_cie_hex, "09 00 ff 75 00 00 00 03 01 30")
        self.assertEqual(matches[0].signal, "GET_CAPABILITIES")
        self.assertEqual(matches[0].possible_sample_rates, (48000, 44100))

    def test_set_configuration_command(self):
        avdtp = b"\x00\x03\x04\x08" + SERVICE_0E03
        matches = decode_avdtp(avdtp, 8, 1, 0x0041, "outgoing")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].codec_id, "0x0e03")
        self.assertEqual(matches[0].sample_rate_flags, "0x80")

    def test_snoop_full_acl(self):
        avdtp = b"\x02\x02" + SERVICE_0103
        data = btsnoop([hci_acl(l2cap(avdtp))])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "hci.log"
            path.write_bytes(data)
            hits, total, partial = scan_btsnoop(path)
        self.assertEqual((total, partial), (1, 0))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].cid, "0x0040")
        self.assertEqual(hits[0].direction, "incoming")

    def test_snoop_acl_continuation(self):
        avdtp = b"\x02\x02" + SERVICE_0103
        l2 = l2cap(avdtp)
        data = btsnoop([hci_acl(l2[:8]), hci_acl(l2[8:], pb=1)])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "hci.log"
            path.write_bytes(data)
            hits, total, partial = scan_btsnoop(path)
        self.assertEqual((total, partial), (2, 0))
        self.assertEqual(len(hits), 1)

    def test_invalid_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wrong.log"
            path.write_bytes(b"not-btsnoop")
            with self.assertRaises(ValueError):
                scan_btsnoop(path)


if __name__ == "__main__":
    unittest.main()
