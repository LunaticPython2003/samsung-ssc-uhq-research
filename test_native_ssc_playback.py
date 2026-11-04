"""Tests of the anonymized native-Android SSC log parser; no ADB needed."""
import unittest
from scripts.report_native_ssc_playback import parse


class NativePlaybackParserTests(unittest.TestCase):
    def test_selected_codec_and_rate(self):
        raw="""11-04 18:43:41.807  100 100 V ssc_encoder: new bitrate 584000, previous bitrate 0
11-04 18:43:42.000  100 101 V ssc_encoder: a2dp_ssc_encode_frames: bitrate_idx 1 bit_rate 584000 nb_byte_read 0
11-04 18:43:42.010  100 101 V ssc_encoder: a2dp_ssc_encode_frames: bitrate_idx 1 bit_rate 584000 nb_byte_read 0
11-04 18:43:42.020  100 101 V ssc_encoder: a2dp_ssc_encode_frames: nb_frame 1 sample 96000 level 1 limit false monitor false scmst false
11-04 18:43:42.030  100 101 V a2dp_vendor_ssc: A2DP_ParseInfoSsc: codec info[00000075] codecid[0103] samplerate[0] limitation[a]
"""
        state="mCodecConfig: {codecName:SSC,mCodecType:8,mCodecPriority:8001,mSampleRate:0x8(96000),mBitsPerSample:0x8(8_24),mChannelMode:0x2(STEREO)}"
        audio="11-04 18:43:41.536 format update:FormatInfo{isSpatialized=false, channelMask=0x3, sampleRate=96000}"
        result=parse(raw,state,audio,"11-04 18:43:41")
        self.assertEqual(result["selected_a2dp_codec"],{
          "codec":"SSC","sample_rate_hz":96000,
          "bits_per_sample_field":"8_24","stereo":True})
        self.assertEqual(result["sender_bitrate_counts_bps"],{584000:2})
        self.assertEqual(result["sender_index_counts"],{1:2})
        self.assertEqual(result["vendor_codec_id_counts"],{"0x00000075:0x0103":1})
        self.assertEqual(result["sender_quality_levels"],{1:1})
        self.assertEqual(result["sender_sample_rate_counts"],{96000:1})
        self.assertEqual(result["bitrate_transitions"][0]["next"],584000)
        self.assertEqual(result["audio_source_rates_seen_hz"],[96000])

    def test_ignored_old_events_and_e4_notice(self):
        log="""11-04 18:43:39.000 V ssc: bitrate_idx 1 bit_rate 584000
11-04 18:43:42.000 V ssc: bitrate_idx 4 bit_rate 886000
"""
        r=parse(log,"","", "11-04 18:43:41")
        self.assertEqual(r["sender_bitrate_counts_bps"],{886000:1})
        self.assertEqual(r["sender_index_counts"],{4:1})
        self.assertIsNone(r["selected_a2dp_codec"])

if __name__=="__main__":unittest.main()
