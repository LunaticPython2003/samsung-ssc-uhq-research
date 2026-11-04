# Fold7 native Android SSC filesystem / 886-kbps audit
**Date:** 2026-11-04
**Method:** Read-only ADB/temporary root inspection on the user's *personal* Linux workstation. No Bluetooth configuration, firmware, private apps, pairing state, or system settings were changed. All extracted proprietary bytes remain gitignored under `vendor-local/android-886/`; numerical findings are stored as sanitized JSON under `tools/`.

## Device and reproducible inputs

- Phone: Samsung Galaxy Z Fold7 SM-F966B, Android 17, build `F966BXXUCCZIH`.
- Exact `/system/lib64/libScalable_Encoder.so` SHA-256: `90c4c1cbd59b0edb9df6d255acc1f752e542e0cb99d3de8e842afc7ca9914ce7`.
- Exact `/apex/com.android.bt/lib64/libbluetooth_jni.so` SHA-256: `7158e06a58c8fba811b729d76c68c0c12295501d06895d0524f476fdf1caf0fe`.
- Controller: Qualcomm **Hamilton** firmware `BTFW.HAMILTON_C.2.0.1-00397-PATCHZ-1.112320.18`; firmware files `/vendor/firmware/hmtbtfw20.tlv` and `hmtnv20.b39`.
- Analysis helper: `python3 scripts/audit_phone_ssc_paths.py` (requires rooted phone, does not inspect `/data` or copy personal material). This enumerates **30 targeted Android system/vendor/firmware/configuration files**, including 20 native ELF libraries, three selected ADSP firmware fragments, and the Bluetooth controller rampatch/NVM. Extra Qualcomm NVM board variants `hmtnv20.b20` and `hmtnv20.b3c` were compared separately.
- Important limitation: A search for an aligned 32-bit integer only finds literal table storage; optimized AArch64, DSP, or ARM assembly may construct an immediate arithmetically. Thus **absence of a literal does not establish absence of an encoder mode**.

## 1. Encoder and active A2DP software sender

The original encoder **does** recognize 886,000 bit/s and can return 1000-byte/9-ms frames marked `E4`. This was established in earlier separate direct `ssc_encode` harness tests at 96 kHz and remains valid; the present filesystem audit is not a new on-air test. The encoder binary does not store the little-endian `886000` value as a naturally aligned 4-byte raw literal, which is consistent with its compact instruction-based header-code classification.

The matching `libbluetooth_jni.so` contains the active 96-kHz UHQ2 adaptive bitrate selector's **four-entry table** at file offsets `0x1077B0..0x1077BC`, corresponding to:
`584000, 584000, 291000, 152000`.
A separate constant group `328000` appears at file offsets `0x10A2D0..0x10A2DC` for another branch. Prior Ghidra xrefs identified `a2dp_vendor_ssc_send_frames` as the adaptive-rate consumer.

**No additional 886,000 rate-selection table or direct literal was identified in this library's inspected paths.** This is *not* a proof that Android cannot request 886 with a different code path or modified stack; it says the observed production sender policy does not select it.

The vendor Qualcomm `libbluetooth_audio_session_aidl_qti.so` contains a solitary aligned `291000` little-endian literal at file offset `0xFB80`, but no 886,000 literal. This isolated match is **not** yet tied to a runtime SSC rate-control function and should not be presented as one.

## 2. Newly found ADSP-side Scalable component

An on-device firmware fragment `/vendor/firmware_mnt/image/adsp.b37` (9,923,904 bytes) contains both:

- `capi_sbc.c` and related `CAPI SBC` diagnostics;
- **`capi_scalable.c`** and eleven `CAPI SCALABLE` diagnostics (including get static properties, init, set/get param and end).

This is the strongest **new** footprint: a Qualcomm DSP **CAPI Scalable component** coexisting with the SBC codec component. It makes a distinct DSP implementation plausible. However:

- The observed strings do not identify a bitrate table or the specific PCM/SSC variant used.
- They do not show that the component is loaded for the Buds4 Pro or currently used for audio.
- No little-endian **886000** aligned literal was found in the selected ADSP fragments `adsp.b10`, `adsp.b23`, or `adsp.b37`.
- The other earlier Samsung vendor audio AIDL libraries expose an SSC **offload configuration** interface, but do not themselves implement a proven higher-bitrate encoder.
- A Ghidra/Hexagon-level control-flow audit of the DSP CAPI module is future research; this pass was a file inventory/string/literal scan, not a full DSP decompilation.

Qualcomm's `qdssc`/sensor subsystem strings elsewhere in ADSP are **not automatically audio codec references**: distinguish them from the exact `capi_scalable.c` audio component.

## 3. Controller firmware and the 2,304,000 literal

The Hamilton controller rampatch `hmtbtfw20.tlv` contained no aligned little-endian `886000` or `2304000` raw literal. Its NVM files, however, contain a **2304000** 32-bit value:

- `hmtnv20.b20`: file offset `0x1AF0`
- `hmtnv20.b39`: file offset `0x1AF0`
- `hmtnv20.b3c`: file offset `0x1B20`

All three occurrences have identical neighboring data after accounting for board-specific relocation. These are Bluetooth controller **NVM configuration bytes**, not encoded audio measurements. The exact tag/field meaning has not been decoded, and the value must **not** be equated with an SSC bitrate merely because it matches some published 2.304-Mbit/s claims. The publicly documented Qualcomm `hmtnv`/ `hmtbtfw` files are NVM board data and controller patch firmware respectively.

## 4. Baseline live state before requesting playback

A read-only `dumpsys bluetooth_manager` reports `A2dpOffloadEnabled: true` at the service level and controller capability `a2dp_source_offload_capability_mask: 31`. **Neither confirms that an actual SSC stream uses DSP offload**.

The phone was not currently transmitting when the baseline was collected: Bluetooth status `BLE_ON`, and the A2DP source state was disabled. Retained Android logcat lines from approximately 18:09–18:11 show earlier native SSC encoder events:
- `sample=96000` Hz;
- `level=2`;
- `limit=false`, `monitor=false`, `scmst=false`;
- no explicit bitrate-transition or selected HAL configuration record survived in the parsed baseline.

These are historic encoder-processing log lines, **not a measured audio/RF bitrate**. Index 2 would select 291000 in the identified UHQ2 table **if that exact path and mode were active**, but those lines do not alone prove that value was transmitted.

Reproducible tools already present:
```bash
python3 ssc_live_report.py --adb -o tools/ssc_during_playback.json
python3 ssc_btsnooz.py --adb -o tools/ssc_during_btsnooz.json
```

The in-memory BTSNOOZ_LOG_SUMMARY baseline contained **6990 records** (4432 incoming HCI events + 2558 outgoing HCI commands), but **no HCI ACL packets** and no AVDTP SSC candidates. A full HCI snoop capture would need appropriate system developer logging and probably a Bluetooth reconnect. We did **not** enable or restart Bluetooth.

## 5. Exact next experiment: native audio, no custom Linux bridge

1. Connect the **Buds4 Pro to the Fold7** (not Linux), ensuring they are the selected audio output.
2. Enable the phone/Buds' **SSC UHQ 24-bit/96 kHz** setting if the UI offers it. Capture the actual selected codec from dumpsys/logs; do **not** infer it from the source file.
3. Play a **locally downloaded or Wi-Fi-streamed 24-bit/96 kHz Hi-Res Lossless track** using Apple Music or a known bona fide lossless source (if no 24/96 album is available, use regular lossless and label its rate accurately). Play continuously for roughly 90–120 seconds while staying near the phone.
4. Tell the assistant **“playing now”** while the track is actually streaming. The assistant can immediately run the native ADB logcat/HAL profile and compare with the baseline from the personal workstation.
5. If logcat still cannot expose actual HCI media bitrates, explicitly discuss user-authorized full Bluetooth HCI snoop logging for another capture rather than claiming an AVDTP packet trace from the event-only BTSNOOZ summary.

**Correct limitation:** Lossless PCM input does not force 886 kbps SSC on the radio. The sender may select 584/291/152 kbps dynamically regardless of source resolution.

All code and reports may be committed to the personal repo; vendor firmware, raw logs, addresses and copyrighted media should remain local and untracked.
