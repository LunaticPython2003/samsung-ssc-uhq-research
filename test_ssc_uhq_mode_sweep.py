"""Offline tests for Samsung SSC sweep result interpretation (no Android required)."""
import unittest
from scripts.sweep_ssc_uhq_modes import EXPECTED_MARKERS, RATES, MODES, parse


class SweepParserTests(unittest.TestCase):
    def test_all_expected_uhq_markers(self):
        expected={152000:6,250000:5,291000:0,308000:1,
                  442000:2,584000:3,886000:4}
        self.assertEqual(EXPECTED_MARKERS,expected)
        self.assertEqual(len(RATES)*len(MODES),21)

    def test_a_valid_886_frame_uses_e4_tag(self):
        # Exact observed output layout of the real Android C test.
        s="frame=0 result_register=1000 changed=1000 last_modified_exclusive=1000 canary=OK prefix=ffe00d04"
        parsed=parse(s,886000,34,1)
        self.assertEqual(parsed["frame3_low5"],"0x04")
        self.assertTrue(parsed["all_frames_lengths_match_return_and_marker"])
        self.assertTrue(parsed["all_canaries_ok"])

    def test_e4_is_not_the_same_as_e3(self):
        s="frame=0 result_register=1000 changed=1000 last_modified_exclusive=1000 canary=OK prefix=ffe00d03"
        parsed=parse(s,886000,34,1)
        self.assertFalse(parsed["all_frames_lengths_match_return_and_marker"])

    def test_truncated_frame_fails_validation(self):
        s="frame=0 result_register=1000 changed=1000 last_modified_exclusive=800 canary=OK prefix=ffe00d04"
        parsed=parse(s,886000,34,1)
        self.assertFalse(parsed["all_frames_lengths_match_return_and_marker"])

    def test_missing_frame_rejected(self):
        with self.assertRaises(RuntimeError):
            parse("",584000,24,1)

    def test_canary_corruption_reported(self):
        s="frame=0 result_register=660 changed=660 last_modified_exclusive=660 canary=CORRUPTED prefix=ffe00d03"
        parsed=parse(s,584000,24,1)
        self.assertFalse(parsed["all_frames_lengths_match_return_and_marker"])
        self.assertFalse(parsed["all_canaries_ok"])


if __name__=="__main__":
    unittest.main()
