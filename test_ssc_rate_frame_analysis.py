"""Offline mathematical checks; deliberately no Bluetooth radio I/O."""
import unittest

from ssc_rate_frame_analysis import (
    expected_bytes_per_frame,
    max_complete_frames,
    OBSERVED_MODES,
)


class FrameSizeTests(unittest.TestCase):
    def test_encoder_length_near_three_byte_overhead(self):
        for mode in OBSERVED_MODES:
            with self.subTest(rate=mode.selected_bitrate_bps):
                overhead = mode.observed_frame_bytes - expected_bytes_per_frame(
                    mode.selected_bitrate_bps
                )
                self.assertLess(abs(overhead - 3), 0.4)

    def test_conservative_mtu_capacity(self):
        self.assertEqual(max_complete_frames(1005, 660), 1)
        self.assertEqual(max_complete_frames(1005, 330), 3)
        self.assertEqual(max_complete_frames(1005, 330, media_header_bytes=4), 2)
        self.assertEqual(max_complete_frames(1005, 1000), 0)

    def test_validation(self):
        with self.assertRaises(ValueError):
            expected_bytes_per_frame(0)
        with self.assertRaises(ValueError):
            max_complete_frames(1005, -1)


if __name__ == "__main__":
    unittest.main()
