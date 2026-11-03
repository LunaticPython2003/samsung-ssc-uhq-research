"""Tests for anonymized live SSC runtime profile extraction."""
import unittest
from ssc_live_report import summarize

LOG = """
11-03 17:11:36.823  5630 19655 I a2dp_vendor_ssc_encoder: a2dp_ssc_encode_frames: nb_frame 1 sample 96000 level 2 limit false monitor false scmst false
11-03 17:11:36.823  5630 19655 E a2dp_vendor_ssc_encoder: a2dp_ssc_encode_frames: new bitrate 291000, previous bitrate 0
11-03 17:11:36.873  5630 19655 E a2dp_vendor_ssc_encoder: a2dp_ssc_encode_frames: new bitrate 584000, previous bitrate 291000
11-03 17:12:06.946  5630 6128 I a2dp_vendor_ssc_encoder: a2dp_vendor_ssc_encoder_update: sample_rate=96000 bits_per_sample=34 channel_count=2, bitrate_limitation=false, is_uhq2=true
11-03 17:12:06.946  5630 6128 I a2dp_vendor_ssc: A2DP_VendorGetTrackSampleRateSsc: 0x20, uhq ver2 : 0x2
11-03 17:12:06.947  5630 6128 I BTAudioA2dpSehAIDL: a2dp_get_selected_hal_codec_config: SehCodecConfiguration=SehCodecConfiguration{codecType: SSC, encodedAudioBitrate: 584000, peerMtu: 1005, isScmstEnabled: false, config: CodecSpecific{sscConfig: SehSscConfiguration{sampleRateHz: 96000, channelMode: STEREO, bitsPerSample: 34}}}
11-03 17:12:06.947  5630 6128 I BTAudioCodecStatusSehAIDL: IsCodecOffloadingEnabled: enabled SSC
11-03 17:12:22.244  5630 19655 I a2dp_vendor_ssc_encoder: a2dp_ssc_encode_frames: nb_frame 1 sample 96000 level 1 limit false monitor false scmst false
unrelated personal content should never appear in the report
"""

class LiveReportTests(unittest.TestCase):
    def test_live_profile_reconstructs_codec(self):
        p = summarize(LOG)
        self.assertEqual(
            (p["selected_configuration"]["sample_rate_hz"],
             p["selected_configuration"]["bitrate_bps"],
             p["selected_configuration"]["peer_mtu_bytes"],
             p["selected_configuration"]["bit_depth_field"]),
            (96000,584000,1005,34)
        )
        self.assertTrue(p["offload_reported_enabled"])
        self.assertTrue(p["encoder_updates"][0]["is_uhq2"])
        self.assertEqual(p["frame_event_count"],2)
        self.assertEqual(p["bitrate_transitions"][-1]["from_bps"],291000)
        self.assertEqual(p["bitrate_transitions"][-1]["to_bps"],584000)
        self.assertEqual(p["frame_events"][-1]["level"],1)

    def test_omits_noncodec_content(self):
        import json
        data=json.dumps(summarize(LOG))
        self.assertNotIn("unrelated personal content",data)
        self.assertNotIn("5630",data)
        self.assertNotIn("6128",data)

    def test_empty_log_is_not_fabricated(self):
        p=summarize("nothing to report")
        self.assertIsNone(p["selected_configuration"])
        self.assertEqual(p["frame_event_count"],0)
        self.assertFalse(p["offload_reported_enabled"])

if __name__ == "__main__":
    unittest.main()
