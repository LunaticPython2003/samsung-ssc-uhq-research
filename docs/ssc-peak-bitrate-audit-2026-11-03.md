# Samsung SSC peak-bitrate audit — November 3, 2026

## Executive finding

**For the exact software encoder on the user's Galaxy Z Fold7, 886,000 bit/s is the highest bitrate with its own explicitly recognized encoder-frame header code.** The exhaustive branches in `get_header_from_bitrate` contain **13 named bitrate values**. The adjacent `get_uhq_info_from_bitrate` uses the same named high-rate family; bitrates beyond 886,000 are classified as a generic/unknown `0xF3` mode.

This is a statement about `/system/lib64/libScalable_Encoder.so`, not a universal Samsung SSC UHQ or Buds4 Pro Bluetooth bandwidth limit. There is a separate Samsung **AIDL SSC hardware/offload configuration path**, but it does not by itself establish a 2.304-Mbps radio stream.

Current normal *software Bluetooth sender* on the Fold7 uses a 96-kHz UHQ2 adaptive table of `[584000,584000,291000,152000]`, so the existence of an 886-kbps encoder mode does **not** mean the phone currently selects or transmits it.

## External sources and conflicting claims

1. Samsung Buds4 Pro specs: SSC UHQ is available with audio input/output format up to 24-bit/96 kHz, but the official specifications examined provide no independently measurable compressed-bitstream maximum:
   https://www.samsung.com/us/audio-sound/galaxy-buds4-pro/
2. Samsung's page on older **Scalable Codec** advertises **88–512 kbps** adaptation; it should not be treated as a peak SSC UHQ specification:
   https://www.samsung.com/in/support/mobile-devices/what-is-scalable-codec/
3. ComputerBase's Buds3 Pro review (2024) reports SSC HiFi (24-bit/48-kHz) variable bitrate reaching **2,304 kbit/s** and separately describes SSC UHQ (24-bit/96-kHz). This is a secondary article, without public on-air byte counts:
   https://www.computerbase.de/artikel/audio-video-foto/samsung-galaxy-buds-3-pro-test.88827/
4. SoundGuys (Adam Birney, July 31 2026) specifically attributes **2,304 kbps for SSC UHQ** to Samsung, while stating that independent lossless verification has not been established:
   https://www.soundguys.com/samsung-aptx-lossless-160833/
5. The public project `Vinchethescript/samsung-ssc-reversed` explicitly calls its partial encoder recreation nonfunctional and potentially incorrect. It does not provide an independently demonstrated high-bitrate A2DP sender:
   https://github.com/Vinchethescript/samsung-ssc-reversed
6. The public `christiansupino/ssc-audio-port` README describes an Android porting effort, without a demonstrated 2.304-Mbps or 886-kbps radio test:
   https://github.com/christiansupino/ssc-audio-port

**Crucial caveat:** 24 × 48,000 × 2 = **2,304,000 bits/s** is exactly the *uncompressed* PCM bitrate for 24-bit/48-kHz stereo. This could explain the published number, but that numerical coincidence alone **does not prove** the cited articles conflated PCM throughput with compressed Bluetooth data.

For comparison, uncompressed 24-bit/96-kHz stereo PCM is **4,608,000 bits/s**.

## Experimental methodology — real ARM64 encoder

Local hashes and provenance:
- `/system/lib64/libScalable_Encoder.so` on rooted Galaxy Z Fold7, SHA-256 `90c4c1cbd59b0edb9df6d255acc1f752e542e0cb99d3de8e842afc7ca9914ce7`.
- No change to Bluetooth, firmware, pairing, or source playback. Only local read-only `dlopen` and exported function calls.
- The standalone C probe `ssc_bitrate_catalog.c` invokes `get_header_from_bitrate(int)` and `get_uhq_info_from_bitrate(int,int*,int*)` on 50 candidate bitrates between 88 kbit/s and 4,608 kbit/s. The complete private CSV is `tools/ssc_bitrate_catalog_results.csv` (gitignored). To reproduce, execute `bash scripts/check-bitrate-catalog.sh`.

### The 13 explicitly recognized header IDs

| Encoder bitrate | Header code | Classification observations |
|---:|---|---|
| 88,000 | `0xF0` | Lower-rate family |
| 96,000 | `0xF1` | Lower-rate family |
| 128,000 | `0xF2` | Lower-rate family |
| 152,000 | `0xE6` | UHQ-classified by helper |
| 229,000 | `0xF4` | Lower-rate family |
| 250,000 | `0xE5` | UHQ-classified by helper |
| 256,000 | `0xF6` | Separate classifier state |
| 291,000 | `0xE0` | UHQ-classified by helper |
| 308,000 | `0xE1` | UHQ-classified by helper |
| 328,000 | `0xF5` | Separate classifier state |
| 442,000 | `0xE2` | UHQ-classified by helper |
| 584,000 | `0xE3` | UHQ-classified by helper |
| **886,000** | **`0xE4`** | **Highest recognized bitrate** |

Examples explicitly **not recognized as named header modes**: 176,000, 192,000, 320,000, 512,000, 576,000, 640,000, 705,600, 768,000, 960,000, 1,000,000, 1,200,000, 1,764,000, 2,000,000, 2,304,000, 2,400,000, 3,000,000 and 4,608,000 bit/s. These return the generic code `0xF3`. The `0xF3` fallback is **not proof that calling the encoder fails for every input**; indeed, earlier high-rate tests wrote data. However it is **not a separately validated, self-describing SSC mode**.

**Interpretation caution:** For several lower modes, `get_uhq_info_from_bitrate` leaves one output argument untouched (the C probe initializes it to `-777`). Consequently the report's recognition conclusion is based on the *dedicated frame-header mapping*, **not** on treating those unmodified outputs as meaningful codec flags.

The same analyzed binary's `get_header_from_bitrate` decompilation contains the complete cases above and a default `0xF3`, providing stronger evidence than merely probing a sparse selection of bitrates. The high-rate tests at 1.2, 2.304, and 2.4 Mbps returned `1279` while touching **1384, 2656, and 2766 output bytes**, respectively—ambiguous/inconsistent frame extents and therefore NOT safe to transmit as verified codec frames. This distinction was maintained in the Linux bridge.

### Extra limit: MTU, even for valid 886-kbps frames

At 96kHz and 864 samples/channel, a codec frame lasts 9ms. A verified 886-kbps encoder frame is **1000 bytes**; at 584kbps it is **660 bytes**. Under the *provisional assumption* that Samsung's reported peer MTU 1005B includes a 12B fixed RTP header:

- 584-kbps frame: `660+12=672` B, fits before additional SSC headers.
- 886-kbps frame: `1000+12=1012` B, misses the hypothetical cap by **at least 7B**.
- Real SSC RTP media framing/fragmentation/MTU convention has not been captured and could change that calculation.

## Additional Samsung/Qualcomm offload-library inspection

Extracted the following **private, gitignored** ELF files from the device with `adb exec-out su -c 'cat ...'` because standard `adb pull /vendor` lacked permission:

- `/vendor/lib64/libsehbluetooth_audio_session_aidl.so`
- `/vendor/lib64/vendor.samsung.hardware.bluetooth.audio-impl.so`
- `/vendor/lib64/libbluetooth_audio_session_aidl_qti.so`
- `/vendor/lib64/hw/android.hardware.bluetooth.audio-impl-qti.so`
- `/vendor/lib64/hw/android.hardware.bluetooth.audio_sw.so`

ELF symbol inspection of Samsung's audio-session library identified **`BluetoothAudioCodecs::IsOffloadSscConfigurationValid`** and **`BluetoothAudioCodecs::GetA2dpOffloadCodecCapabilities`**.

Ghidra decompilation confirmed:

1. `IsOffloadSscConfigurationValid` validates a **Samsung SSC CodecSpecific variant** and certain allowed configuration field values.
2. `GetA2dpOffloadCodecCapabilities` provides an SSC-specific capability object in Samsung's AIDL Bluetooth audio structure (separate from the software-encoder entry points).
3. Neither analyzed function proves that a 2.304-Mbps compressed frame rate is negotiated or selected. A hardware/offload implementation remains an **open hypothesis**.
4. No trustworthy **aligned** 32-bit literal `2304000` or `2400000` occurred in the inspected copy of these libraries or the software Bluetooth JNI. Earlier unaligned 4-byte matches were accidental overlapping table data, not reliable bitrate constants. This negative binary scan **cannot exclude** constants synthesized by instructions or stored in other firmware/driver layers.

**Source audit script:** `ghidra-scripts/AuditSscOffload.java`, used against the locally extracted `libsehbluetooth_audio_session_aidl.so`. Its decompiled output remains ignored under `tools/ghidra-runs/offload-ssc-audit.log` and must never be published.

The presence of `SehSscCapabilities` shows there is a separate SSC offload *configuration path* in Samsung's stack. It does **not** demonstrate an active DSP/firmware encoder for the current Buds4 Pro session. The normal UHQ2 rate-control path in `libbluetooth_jni.so` previously reconstructed the 584/291/152 kbps table and the actual phone playback reached 584 kbps.

## Findings and limits

**Established with high confidence:** The examined **software encoder's complete named bitrate mapping** ends at **886kbps**. No other separately named bitrate above 886kbps was found there. The 886kbps mode is reproducible using the original ARM64 library.

**Unresolved:** What a Samsung marketing/press 2,304-kbps figure denotes; whether firmware/DSP offload implements a different compressed bitstream at higher rates; actual Buds4 Pro SSC vendor capability flags, peer MTU, fragmentation, and measured HCI/air throughput.

**Most useful next experiment:** capture **full HCI ACL + AVDTP negotiation + media** while SSC UHQ is active on the Fold7, then inspect actual payload lengths and A2DP codec IDs. If the SSC media payload is indeed only ~660 bytes every 9ms and one frame per media packet, observed 584kbps operation can be grounded in on-air evidence. If multi-megabit transmission is occurring via another path, the negotiated codec/transport and packet length distribution will expose it.

Bottom line: **No evidence from this firmware that a named standalone SSC encoder rate above 886kbps exists.** The published 2.304-Mbps claim remains an unresolved independent transport/marketing question, not a proven Buds4 Pro encoded-bitrate capability.
