# SSC HiFi mode flags and the 2.304-Mbit/s claim — Fold7 validation

Research date: 2026-11-04. Tested on the user's temporarily rooted SM-F966B, original `/system/lib64/libScalable_Encoder.so`, previously recorded SHA-256 `90c4c1cbd59b0edb9df6d255acc1f752e542e0cb99d3de8e842afc7ca9914ce7`. No phone firmware/earbud firmware/Bluetooth settings modified.

## Independent source comparison

[ashenzar/ssc-uhq, findings F13 and F23](https://github.com/ashenzar/ssc-uhq/blob/main/findings.md) reports:

- SSC HiFi is capability flag `0x04`, but Samsung's encoder-creation mode argument is selected by priority: `0x08` -> **34**, else `0x04` -> **32**, else `0x02` -> **24**, else **16**. These numeric values are **codec/PCM-format enum-like values, not 32- or 34-bit PCM**.
- The author reports an identical S24U and S26U `libScalable_Encoder.so` (D2). **We did not independently obtain/compare S24U/S26U binaries**, and this statement is scoped to those phone models and that library; it doesn't exclude different DSP firmware or future paths.
- Source shows 96-kHz UHQ sample-mode selects from `[584000,584000,291000,152000]`. `get_header_from_bitrate` separately knows `E4=886000`, but the documented active sender has no path to select it.
- 2,304,000 bit/s equals either 24-bit/48-kHz **stereo** *uncompressed* PCM or 24-bit/96-kHz **mono** *uncompressed* PCM. The equality supports a possible specification-vs-transport mixup, but cannot independently establish intent behind Samsung marketing or which transport is in use.

## Original Fold7 encoder: mode 24 vs 32 vs 34

We recompiled our own isolated `ssc_arm64_probe.c` with its permissible `ssc_encoder_create(...,mode,...)` arguments extended to 32 and 34. The phone then encoded **eight consecutive frames** of a deterministic 440-Hz stereo PCM32 tone, for each combination below.

| Requested sample rate | Requested bitrate | Modes tested | Encoder return length / frame | Full eight-frame output SHA-256 equality |
| ---: | ---: | --- | --- | --- |
| 48 kHz | 328000 | 24, 32, 34 | 806 B | **identical** |
| 48 kHz | 584000 | 24, 32, 34 | 1279 B but wrote ~1434 B | identical, **not validated as complete frames** |
| 48 kHz | 886000 | 24, 32, 34 | 1279 B but wrote ~2172 B | identical, **not validated as complete frames** |
| 96 kHz | 328000 | 24, 32, 34 | 372 B | **identical** |
| 96 kHz | 584000 | 24, 32, 34 | 660 B | **identical** |
| 96 kHz | 886000 | 24, 32, 34 | 1000 B | **identical** |

The number of bytes returned and the eight-frame hash match for all three modes at each fixed sample-rate/bitrate setting. Checks used the original ARM64 encoder, not a reimplementation. Neither audio nor any identifying data was recorded or published; scratch output stayed under `/data/local/tmp/ssc_mode_*.raw`.

**Interpretation:** Switching HiFi/UHQ *mode argument alone* does **not** create a higher-rate encoder mode or different payload for this synthetic signal. The test does not establish that these modes behave identically under all PCM magnitudes, channel layouts, low-level state, adaptive rate switching or firmware. It is not a listening test and does not demonstrate 886-kbps audio playback.

## Classic A2DP physical throughput

The official [Bluetooth Core BR/EDR baseband specification, Table 6.8](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-61/out/en/br-edr-controller/baseband-specification.html) gives maximum asymmetric 3-DH5 **user** throughput `2178.1 kbit/s` (1021 payload bytes per 3.75 ms) before L2CAP, AVDTP, RTP and retransmission costs.

As a result, **2304 kbit/s of compressed audio cannot be continuously sustained over that maximum classic BR/EDR ACL path**. This statement concerns Classic A2DP and does not establish a value for an unexamined LE or proprietary physical transport. A radio or compressed bitrate cannot be inferred solely from 24-bit/96-kHz PCM capability.

A 886-kbps 1000-byte SSC frame every 9ms needs around 889kbps encoded payload throughput and **is within the physical EDR throughput budget**, so the radio bitrate alone does **not** prohibit E4. But with the previously observed 1005-byte peer MTU, one 1000-byte frame plus the fixed 12-byte RTP header **doesn't fit without fragmentation or a larger transport MTU**, under the explicit RTP-inclusive MTU assumption. The archived R640 firmware separately revealed an **800-byte** SSC receive queue on one path; the exact route and any reassembly are unresolved.

## Revised verdict

- **886 kbit/s**: demonstrated mode in the original phone encoder, and potentially physically sustainable over Classic EDR; not selected by the observed Samsung UHQ sender; **receiver decoding not proven**. Our recent [receiver audit](r640-e4-reaudit-2026-11-04.md) corrected an earlier false assertion of unconditional E4 drop: a pre-parser's caller ignores its return value, while another queue imposes the 800-byte constraint.
- **2304 kbit/s**: no named header mode in the tested software encoder, no proven on-air SSC capture, and **above the theoretical sustainable user throughput of single Classic 3-DH5**. It may refer to a PCM-format bitrate or some unexamined transport, but a marketing explanation remains an inference rather than a measured fact.
- **HiFi capability flag 0x04**: no independently observed new higher-rate output selected by passing mode 32 rather than mode 34 or 24 to the original Fold7 encoder under these tests.

The remaining decisive step for E4 is the live BlueZ A2DP transport and receiver test—after obtaining real capability bytes, MTU, and working 584kbps audio. No additional static assumption can substitute for that radio/decoder result.
