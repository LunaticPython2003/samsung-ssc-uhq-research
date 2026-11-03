# SSC interoperability research closure and build handoff
**Date:** 2026-11-03  
**Scope:** Cross-project commit audits, Samsung software encoder, public Galaxy Buds4 Pro firmware, and first Linux/Windows implementation choice.  
**Reproducible verifier:** `scripts/audit-r640-receiver.py`; private firmware file is not redistributed.

## Executive verdict

1. **Above 886 kbit/s:** None of the examined open-source SSC projects documents a *verified, earbuds-decoded* compressed SSC mode above 886 kbit/s. Claims for 2,304 kbit/s are not supported by their demonstrated packet captures or by our examined software-encoder header cases. This is not a universal proof that future firmware/DSP/LE Audio cannot provide other modes.
2. **886 kbit/s is real in the Samsung ARM64 software encoder:** header tag `E4`, `get_header_from_bitrate(886000)` returns `0xE4`, UHQ classification is positive, and the Fold7 encoder returns consistently sized **1000-byte frames** at 96 kHz/864 samples/channel. We previously transported 223 such frames across the Linux host's encoder-to-RTP **offline loopback** using a *hypothetical* MTU=1200, not Bluetooth. This is **not a supported Buds4 Pro UHQ playback mode on the inspected firmware**.
3. **New receiver-side finding:** The actual Buds4 Pro SM-R640 firmware `R640XXU0AZD2` explicitly processes `E0`, `E3` and `E6` UHQ frames, not `E4`. Its initial validator has a generic **484-byte minimum** for `E4` and may pass a 1000-byte E4 frame, but the downstream UHQ pre-parser takes an early return for E4 without the E0/E3/E6 frame-handling calls. Therefore **886 kbit/s is an encoder mode, not a demonstrated receiver-decodable bitrate for this specific firmware**.
4. **584 kbit/s is the strongest first build target**: E3, 660-byte/9-ms frame, explicit 660-byte Buds4 Pro validator case and normal downstream processing, matches Fold7 UHQ2 adaptive table (584/584/291/152) and previous Samsung runtime observation. Other project authors report 584 kbit/s UHQ playback on Buds3 Pro.
5. **A working Linux SSC system is no longer a blank-slate problem.** Multiple independent projects have substantial integration work. A standalone BlueZ A2DP source is the most portable first step on this machine; existing PipeWire code can inform later integration.

## 1. Public projects: actual commit and implementation evidence

| Project | Commit evidence as of 2026-11-03 | What is actually established | 886 kbit/s / above |
|---|---|---|---|
| [salvetum/SSCOnWindows](https://github.com/salvetum/SSCOnWindows) | Sept 17–Oct 4, 2026: SSC backend isolation, daemon fixes, codec capability UI, BTstack stream tests | Author reports normal 48-kHz SSC playback to **Buds3 FE** over BTstack/WinUSB, with Samsung encoder via WSL/QEMU or Qiling | Lists 886 in a permitted encoder policy; **no UHQ playback verification on an UHQ-capable earbud**. Buds3 FE lacks UHQ cap 0x02 |
| [sachk/openssc](https://github.com/sachk/openssc) | [0e6c7d2](https://github.com/sachk/openssc/commit/0e6c7d26404a93cf3e491ab314caec7e735c89d2), [2f91a1a](https://github.com/sachk/openssc/commit/2f91a1a57b61449ba6f1c3e71f1dc4e575c812a8): bitrate stress and frame size profiles | Real A31/S26 basic SSC capture comparison; PipeWire plugin / QEMU encoder and experiments. [d7921bc](https://github.com/sachk/openssc/commit/d7921bc35) corrected packetization to place raw SSC frames **immediately after the standard RTP header**, removing an incorrectly added generic payload byte | Explicit `uhq-886` and `stress-2304` *probe profiles*. This is **not evidence the Buds accept either**, and the author labels the 2304 path experimental |
| [lori28167/SamsungScalableCodec-linux](https://github.com/lori28167/SamsungScalableCodec-linux) | [83afc68](https://github.com/lori28167/SamsungScalableCodec-linux/commit/83afc687a0ce207b48d20201386e001a86bab6ec), [c77d103](https://github.com/lori28167/SamsungScalableCodec-linux/commit/c77d1036980a3f7f6ed8330d14c09b031e23ea94): native CELT-derived codec, 96k adaptation, band count | Author reports 48k SSC streaming on **Buds3 Pro**, and UHQ roundtrip/model-decoder results; author does **not** claim completed over-earbud 96k UHQ playback | Buds3 Pro firmware analysis: UHQ receiver recognizes **E6 (152), E0 (291), E3 (584)**; E4 (886) lacks a dedicated parser/length case |
| [ashenzar/ssc-uhq](https://github.com/ashenzar/ssc-uhq) | [dffe4aa](https://github.com/ashenzar/ssc-uhq/commit/dffe4aabacdec162873a37a4cbb9b8f929b8755d): native byte-exact rebuild reported Oct 27, 2026, code in **private separate repo**, not independently inspected | Author reports 96-kHz 584/291/152 UHQ successfully playing on **Buds3 Pro**. Documents 584 adaptive sender ceiling and E4 known encoder mode, not in on-air captures | F23 explicitly says **886 not encountered in a capture**, and 2,304 kbit/s has no demonstrated compressed link |
| [Kuzanimi/SSC-Pipewire](https://github.com/Kuzanimi/SSC-Pipewire) | Only initial Sept 1, 2026 commit | Binary PipeWire codec plugin and modified BlueZ5 library; implementation closed-source and no independently reproduced audio capture | No reliable >886 evidence. Do **not** overwrite distro Bluetooth libraries with its unverified binaries |
| [Vinchethescript/samsung-ssc-reversed](https://github.com/Vinchethescript/samsung-ssc-reversed) | One initial 2024 commit | Explicitly self-described nonfunctional/decompiled SSC effort | No >886 playback evidence |
| [christiansupino/ssc-audio-port](https://github.com/christiansupino/ssc-audio-port) | One Sept 2026 initial commit | One-sentence porting aspiration; no shown encoder/transport | No bitrate verification |
| [Bananz0/Samsung-Scalable-Codec](https://github.com/Bananz0/Samsung-Scalable-Codec), [aldusialn/ssc-decomp](https://github.com/aldusialn/ssc-decomp) | GitHub API returned empty repositories | No source or commits to analyze | None |

**Use and attribution:** salvetum's application code is under MIT, lori's under GPL-3.0-or-later; `openssc` lacks an explicit project license in the reviewed README, so its implementation should be treated as a research reference rather than copied into another project without permission. `ashenzar`'s native bit-exact encoder is in a private repository and is not available for reuse.

## 2. Phone-side: verified encoder, sender, and packet-size evidence

Galaxy Fold7 original software encoder `libScalable_Encoder.so`, SHA-256:
`90c4c1cbd59b0edb9df6d255acc1f752e542e0cb99d3de8e842afc7ca9914ce7`

- `get_header_from_bitrate(886000)` -> **0xE4**; `get_uhq_info_from_bitrate` classifies it as an UHQ family mode.
- 96-kHz, stereo, 864 samples/channel (9 ms), return **1000-byte frame** with the `E4` marker. Repeated isolated tests and the host-only Linux pipeline reproduce this.
- 584000 -> `E3`, **660 bytes** per 9 ms; 291000 -> E0, 330 bytes; 152000 -> E6, 174 bytes.
- Above 886k, the named header classifier falls back to `F3`. Testing 2,304,000 and 2,400,000 produced ambiguous mismatch between return value (1279) and number of bytes written, so these are **not demonstrated valid high-rate SSC frames**.
- Samsung's `a2dp_vendor_ssc_send_frames` selects UHQ2 from `[584000,584000,291000,152000]`, with no 886k rate selected by the existing normal quality-index path. This is the sender's observed capability, not a universal encoder limit.
- The Samsung AIDL library exports `IsOffloadSscConfigurationValid` and SSC offload capabilities, but its decompiled routine did **not** demonstrate a higher compressed bitrate. Hardware DSP/firmware paths remain unverified.
- Published 2,304 kbps marketing may be uncompressed 24×48k×2 PCM; the same rate is *not* proven to be a radio codec bitstream. 24-bit/96 kHz raw PCM is 4,608 kbps.

The Fold7 Bluetooth HAL previously reported Buds peer MTU **1005 bytes**. **Conditionally**, if that MTU is RTP-inclusive, a 1000-byte E4 frame plus a minimal 12-byte RTP header needs at least **1012 bytes**, before any other header, thus 886k is at least seven bytes over the budget. A 660-byte E3 packet is **672 bytes** RTP-inclusive and fits.

### Important cross-project packetization corrections

- `sachk` reports captured standard SSC bitstream: the 12-byte RTPv2 header is immediately followed by the SSC frame **without a generic one-byte payload header**. An earlier commit added the byte, and a later commit removed it after comparing against a real phone capture.
- `lori` reports for UHQ E3/660 bytes: normally one frame per RTP packet; E0/330 and E6/174 may aggregate two SSC frames into one packet. This matches the receiver firmware's fast-path length thresholds and observed MTU.
- SSC UHQ frame headers begin `FF E0..` with 8-bit frame sequence spanning byte1 low nibble and byte2 high nibble; byte3's low five bits identify E0/E3/E6. These are **SSC frame** bytes, not an extra transport header.
- The correct A2DP vendor codec is consistently reported by these projects as vendor `0x00000075`, codec ID `0x0103`. Earlier phone-side static initialization `0x0E03` remains an unresolved implementation detail, not a confirmed alternative peer codec.
- 96-kHz UHQ mode bit is low feature flag `0x02`; `0x08` is a relevant 24-bit/no-limiter feature. Peer capability and exact SetConfiguration byte must still be measured before transmission.

## 3. New direct Buds4 Pro receiver analysis

**Input:** publicly archived **SM-R640** earbuds firmware, `R640XXU0AZD2`, April 2026, via:
https://github.com/timschneeb/galaxy-buds-firmware-archive/blob/main/R640/FOTA_R640XXU0AZD2.bin

**Provenance:** 8,968,784-byte `cafecafe` Bestechnic/ARM firmware image; SHA256:
`b91289cd445449485087aa380559eea167e5c0009ecdb912139d11212e02749f`

The archive publicly lists only this one SM-R640 firmware as of the research date. A May 9, 2026 GSMArena report describes its public rollout, but your Buds4 Pro may run an unarchived newer build. Public archive reference: https://github.com/timschneeb/galaxy-buds-firmware-archive No firmware flashing/updates were performed. The downloaded image remains gitignored under `vendor-local/buds-fw/`.

**Recovery method:** The Buds4 Pro's data-space string-pointer base is `0x1001FFE4` (unlike the older Buds3 Pro firmware mapping). This was derived by checking literal-pool references across strings such as `a2dp_audio_scalable_preparse_packet`, `a2dp_scalable_config`, and `SSC bitrate`. Local Capstone ARM/Thumb-2 disassembly was then used to locate receiver logic by real code xrefs.

**Vendor codec identity from receiver firmware:** The Buds4 Pro `a2dp_scalable_config` path at file offset `0x17AC78` compares the 32-bit vendor ID to `0x75`, then the 16-bit codec ID to `0x0103`; unmatched values exit without the Scalable Codec configuration handling. These precise Thumb instructions are also checked by the reproducible audit script. `0x0103` is therefore **firmware-grounded**, not merely copied from other repositories. The precise negotiated capability byte still requires live connection inspection.

**Initial frame validation:** file offsets `0x8D968..0x8DA28`. At `0x8D992` a Thumb `TBB [pc, r3]` dispatches on `frame[3] & 0x1F`. The table at `0x8D996` selects:
- E0 -> `0x8D9EE`, expected minimum frame length **330 bytes**.
- E3 -> `0x8D9F8`, expected minimum frame length **660 bytes**.
- E6 -> `0x8DA02`, expected minimum frame length **174 bytes**.
- E4 -> **default `0x8D9BC`**, generic **484-byte** minimum. **A 1000-byte E4 frame could pass this *initial* minimum-length check**, so that checker alone cannot be used as a playback verdict.

**UHQ packet-processing path:** file offsets `0x8AFD4..0x8B15C`. After checking sync byte `FF` and the `E0` header-family high nibble, it masks `frame[3] & 0x1F`. It **explicitly branches only on values 0, 3, and 6**, corresponding to E0, E3, and E6. For other values including `4` (E4), it returns early before the expected E0/E3/E6 frame-processing calls. The 886-kbps E4 marker is therefore **not a normally processed UHQ frame on this firmware**.

This is stronger evidence than the prior Buds3 Pro decoder report and explains why a valid encoder-produced E4 payload would still not be playable on the inspected Buds4 Pro firmware.

**Reproducibility:** `python3 scripts/audit-r640-receiver.py` verifies the exact firmware hash, the Thumb instructions and all 23 TBB destinations, with synthetic/fixed-assertion tests in `test_ssc_r640_receiver.py`. It does not redistribute copyrighted firmware bytes or generate modified images. The three new tests pass.

**Scope:** These findings hold for exactly `R640XXU0AZD2`; they do not prove later Buds4 Pro firmware builds couldn't add E4 support.

## 4. Engineering choices for the next conversation

### Preferred goal: genuine sound from Linux to Buds4 Pro, not yet highest bitrate

Host: user's personal Zorin installation. Previous diagnosis established **BlueZ DBus works from the normal Linux desktop**, while CatDesk's isolated shell cannot reach `/run/dbus/system_bus_socket`. `python3 linux/ssc_bluez_probe.py` showed one adapter and no exposed MediaEndpoint objects without a connected device. Local system has **PipeWire 1.0.5 / WirePlumber 0.4.17**; third-party SSC plugins reviewed target newer private interfaces (PipeWire 1.6.x and WP0.5). Avoid blindly installing their library replacements, especially closed-source SSC-Pipewire artifacts.

Recommended minimal first bridge:

```
Linux WAV/synthetic PCM 96 kHz stereo
      -> ADB / rooted Fold7 software SSC encoder (rate 584000, frame 864)
      -> verified FF E.. E3 / 660-byte encoded frame
      -> RTPv2 fixed 12-byte header + raw SSC frame
      -> BlueZ Media1 A2DP Source endpoint (vendor 0x75, codec 0x0103)
      -> MediaEndpoint1.SelectConfiguration / SetConfiguration
      -> MediaTransport1.Acquire (verify real write-MTU)
      -> one frame per packet, 9-ms audio duration; pace according to BlueZ/HCI feedback
      -> Galaxy Buds4 Pro
```

**Do not treat this sketch as a fully tested packet format**: real RTP timestamp/sequence policy and exact AVDTP peer configuration must be confirmed in transport logs. The existing 584k Linux prototype successfully encoded/loopback-checked **223 frames**, but did not open BlueZ or play on earbuds. Adapt the existing `linux/ssc_linux_bridge.py` and `linux/ssc_bluez_probe.py` instead of beginning another transport stack from scratch.

Suggested incremental acceptance gates:

1. From the host desktop session, connect Buds to BlueZ and extract the **actual remote vendor SEP capabilities** without changing firmware/drivers.
2. Register a safe test A2DP source endpoint and **successfully negotiate** Samsung codec ID `0x0103` and UHQ feature `0x02` with confirmed peer configuration.
3. Acquire the negotiated transport fd and actual **write MTU**. Confirm 672+ bytes are available (12 RTP + 660 frame) before media transmission.
4. Send **one bounded 96-kHz synthetic test stream** with 584k E3 frames; verify audible playback and Bluetooth stats. Do not try E4 or 2.304Mbps in the first working version.
5. Add buffering, RTP sequencing/timestamps, packet loss recovery and a fallback path; then PipeWire capture routing and eventually an independent native SSC encoder.
6. When a stable link exists, compare against third-party 584/291/152 bitrate-switching logic. Higher rates only if **later actual Buds4 Pro firmware** demonstrates acceptance plus sufficient MTU.

Windows continuation: `salvetum/SSCOnWindows` is already a near-complete independent BTstack/WinUSB source for **48-kHz SSC** and WSL/QEMU/Windows encoding; review its MIT-licensed implementation and adapt it to 96-kHz E3 only after the Linux stream works. Use a dedicated USB dongle; do NOT rebind the built-in Intel Bluetooth adapter.

### Final confidence table

| Question | Answer | Confidence |
|---|---|---|
| Is 886 kbit/s an actual named Samsung encoder mode? | **YES**, E4/1000 bytes at 96 kHz | High: local runtime + Ghidra + external projects |
| Is 886 kbit/s selected by Fold7's normal UHQ2 adaptive sender? | **NO** in inspected sender path | High: rate-control table |
| Does Buds4 Pro firmware R640XXU0AZD2 process E4 as UHQ? | **NO**: no E4 branch; early return | High: direct Thumb branch reconstruction |
| Is 886 kbit/s proven playable on Buds4 Pro? | **NO** | High that no proof exists; not a universal future-firmware exclusion |
| Is there confirmed playable SSC above 886 kbit/s? | **NO verified report found** | Moderate, bounded to examined public commits/binaries |
| Does the 2.304-Mbps marketing figure denote measured compressed Bluetooth bitrate? | **Unverified** | High that cited claims lack provided packet evidence |
| Do other independent devices prove 584-kbps UHQ on-air? | Reports of Buds3 Pro success | Third-party self-reported, not independently retested here |
| Should next implementation target 584-kbps E3? | **YES** | Strong technical basis |

No changes were made to earbuds firmware, installed Bluetooth drivers or existing audio services. All proprietary firmware and full decompiler outputs remain local and gitignored.
