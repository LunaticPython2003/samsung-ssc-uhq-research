"""Linux SSC bridge tests. No system D-Bus, audio device or Bluetooth required."""
import math
import socket
import struct
import tempfile
import threading
import unittest
import wave
from pathlib import Path

from linux.ssc_linux_bridge import RtpState, capacity, validate_uhq_frame, bridge_wav
from linux.ssc_bluez_probe import vendor_info, describe_bluez_objects, ENDPOINT1


class LinuxBridgeTests(unittest.TestCase):
    def test_rtp_skeleton_sequence_timestamp_rollover(self):
        cursor = RtpState(sequence=65535, timestamp=0xFFFF_FFF0)
        packet = cursor.pack_candidate(b"\xff\xe0\x0d\xe3")
        self.assertEqual(len(packet), 16)
        self.assertEqual(packet[:2], b"\x80\x60")
        self.assertEqual(struct.unpack_from("!H", packet, 2)[0], 65535)
        self.assertEqual(struct.unpack_from("!I", packet, 4)[0], 0xFFFF_FFF0)
        nxt = cursor.next_frame()
        self.assertEqual(nxt.sequence, 0)
        self.assertEqual(nxt.timestamp, 848)
        with self.assertRaises(ValueError):
            cursor.pack_candidate(b"")

    def test_584_and_886_fit_limits(self):
        self.assertEqual(capacity(1005, 660), (True, 0))
        self.assertEqual(capacity(1005, 1000), (False, 7))
        self.assertEqual(capacity(1200, 1000), (True, 0))
        self.assertEqual(capacity(1005, 330, 4), (True, 0))
        self.assertEqual(capacity(1005, 1000, 4), (False, 11))
        with self.assertRaises(ValueError):
            capacity(12, 660)

    def test_header_validation_without_mistaking_f3_high_rate_for_uhq(self):
        self.assertTrue(validate_uhq_frame(b"\xff\xe0\x0d\x23" + bytes(656), 660, 584000))
        self.assertTrue(validate_uhq_frame(b"\xff\xe0\x0d\x24" + bytes(996), 1000, 886000))
        self.assertFalse(validate_uhq_frame(b"\xff\xe0\x0d\x23" + bytes(996), 1000, 886000))
        self.assertTrue(validate_uhq_frame(b"\xff\xee\x01\xf5" + bytes(656), 660))
        self.assertFalse(validate_uhq_frame(b"\xff\xf3\x01\xf3" + bytes(656), 660))
        self.assertFalse(validate_uhq_frame(b"\xff\xe0\x0d\xe3", 660))

    def test_bluez_probe_never_exposes_device_addresses(self):
        flags = vendor_info(bytes.fromhex("7500000003018a"))
        self.assertEqual(flags["codec_id"], "0x0103")
        self.assertTrue(flags["uhq2_feature"])
        self.assertIsNone(vendor_info(bytes.fromhex("7500000001018a")))
        managed = {
            "/org/bluez/hci0": {"org.bluez.Adapter1": {}},
            "/org/bluez/hci0/dev_11_22_33_44_55_66/sep1": {
                ENDPOINT1: {"Capabilities": list(bytes.fromhex("7500000003018a"))}
            },
        }
        data = describe_bluez_objects(managed)
        self.assertEqual(data["bluez_adapter_count"], 1)
        self.assertEqual(data["samsung_ssc_endpoint_candidates"][0]["flags"], "0x8a")
        self.assertNotIn("11_22_33", str(data))

    def _fake_server(self, port_socket, frame_bytes: int, expected_frames: int):
        with port_socket:
            conn, _ = port_socket.accept()
            with conn:
                hello = recv_n(conn, 28)
                self.assertEqual(hello[:4], b"SSC1")
                (_, _, _, _, selected_bitrate, _, _) = struct.unpack("<4s6I", hello)
                conn.sendall(struct.pack("<4sii", b"SSCR", 0, 9540))
                for i in range(expected_frames):
                    (n,) = struct.unpack("<I", recv_n(conn, 4))
                    self.assertEqual(n, 864 * 2 * 4)
                    recv_n(conn, n)
                    marker = {584000: 3, 886000: 4}[selected_bitrate]
                    frame = b"\xff\xe0" + bytes([(i & 0xF) << 4, marker]) + bytes(frame_bytes-4)
                    conn.sendall(struct.pack("<i", frame_bytes) + frame)

    def test_full_loopback_with_synthetic_encoder(self):
        for bitrate, frame_size, packets, blocked in [(584000, 660, 3, 0), (886000, 1000, 0, 3)]:
            with self.subTest(bitrate=bitrate), tempfile.TemporaryDirectory() as d:
                wav_path = Path(d) / "test.wav"
                with wave.open(str(wav_path), "wb") as w:
                    w.setnchannels(2)
                    w.setsampwidth(2)
                    w.setframerate(96000)
                    w.writeframes(bytes(864 * 3 * 2 * 2))
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.bind(("127.0.0.1", 0))
                server.listen(1)
                port = server.getsockname()[1]
                worker = threading.Thread(target=self._fake_server, args=(server, frame_size, 3), daemon=True)
                worker.start()
                result = bridge_wav(wav_path, bitrate=bitrate, mtu=1005, batch_frames=3, no_adb=True, port=port)
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(result["frames_encoded"], 3)
                self.assertEqual(result["provisional_rtp_packets_loopback"], packets)
                self.assertEqual(result["frames_blocked_by_provisional_mtu"], blocked)
                self.assertEqual(result["batch_frames"], 3)


def recv_n(sock: socket.socket, n: int) -> bytes:
    result = bytearray()
    while len(result) < n:
        piece = sock.recv(n - len(result))
        if not piece:
            raise ConnectionError("Unexpected EOF in test")
        result.extend(piece)
    return bytes(result)


if __name__ == "__main__":
    unittest.main()
