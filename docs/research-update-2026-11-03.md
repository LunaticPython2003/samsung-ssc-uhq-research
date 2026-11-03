# Samsung SSC UHQ research continuation — 2026-11-03

## Purpose and restrictions
Research on the current Windows PC and rooted Samsung Galaxy Z Fold7 (SM-F966B, Android 17). No Linux installation was needed. All ADB diagnostics were read-only. The internal Intel Windows Bluetooth adapter, device pairing, system drivers and firmware were untouched.

## Baseline before this session
- A Windows Python/Rust -> ADB -> Galaxy software encoder bridge worked. This does not make Windows transmit Bluetooth audio.
- Phone playback proved SSC UHQ2, 96 kHz, stereo 24-bit, nominal 584 kbps, and 291 -> 584 kbps startup transition. The standalone encoder returned 330-/660-byte frames at the observed 291-/584-kbps rates.
- Static Bluetooth source parser referenced Samsung vendor 0x75 and codec ID 0x0103, while a static initialization blob encoded 0x0e03. No live AVDTP packet verified either ID.
- Unknown: complete bitrate/feature tables, practical route to the embedded snoop diagnostics, and a working integration into Windows BTstack source discovery.

## New finding 1: Samsung embeds a compressed Bluetooth diagnostic buffer
ADB bluetooth_manager dumpsys includes three Base64 sections: BTSNOOP_LOG_SUMMARY, PickENH_LOG_SUMMARY and QCENH_LOG_SUMMARY.

BTSNOOP_LOG_SUMMARY contains btsnooz version 2: a 9-byte header followed by zlib-compressed length-prefixed HCI records. In this session, the decoded diagnostic snapshot contained **6,990 HCI packets**, only incoming events and outgoing controller commands, **zero ACL data packets**. Consequently **no AVDTP configuration or SSC media packets** could be read from this buffer. The other two enhanced buffers each decode to proprietary diagnostic packets (1,398 and 2,722 records), but are not valid AVDTP and must not be passed off as genuine media packets.

Created ssc_btsnooz.py (decodes dumpsys in memory and saves only anonymized summaries) and test_ssc_btsnooz.py (synthetic ACL discovery, no-ACL case, malformed input). Modified ssc_snoop.py to accept an in-memory btsnoop byte stream. Sanitized results in ssc_btsnooz_findings.json. No raw dumpsys, Bluetooth address, pairing keys or HCI packet dump was written to disk by this decoder.

This explains the previous empty snoop-file searches: the service does have a diagnostic ring, but this particular one is filtered of ACL traffic. To resolve AVDTP negotiation, a user-authorized **full ACL capture** or an isolated USB Bluetooth adapter is still needed. Do not interpret missing ACL frames as absence of SSC support.

## New finding 2: Samsung SSC feature flags and mode selection
Recovered by decompiling A2DP_VendorGetSscType, A2DP_VendorGetTrackBitrateLimitationSsc and A2DP_VendorUsesRtpHeaderSsc:
- Rate bits: 0x80 = 96 kHz, 0x20 = 44.1 kHz, 0x10 = 48 kHz, 0x40 = 32 kHz.
- SSC feature bit 0x02 means UHQ2, producing stack mode code 0x400.
- Without UHQ2, a 96-kHz-only mode chooses code 0x200.
- SSC feature bit 0x08 has **inverse bitrate-limitation polarity**: set = bitrate limiter off, clear = limiter on.
- Lower feature bit 0x04 selects a different legacy mode code (0x100 vs 0x080); its more descriptive meaning remains unknown.
- The SSC source stack uses RTP. A2DP_VendorGetPacketTimestampSsc simply copies a provided timestamp; it does not establish frame grouping or RTP clock policy.

Candidate example 0x8A represents rate=96k, UHQ2=yes, limiter=off. **It is synthetically constructed, not observed on the Bluetooth air link.** Updated Rust ssc-win-bridge/src/ssc_a2dp.rs and the inspect_caps example, with regression tests.

## New finding 3: Exact adaptive target bitrate tables
Recovered three variants of SscBitrateByBusyLevel and dumped four literal tables from Samsung Bluetooth stack data:

| Busy/quality level | Mode 0x400 UHQ2 | Mode 0x200 | Standard unrestricted | Standard limited |
| --- | ---: | ---: | ---: | ---: |
| 0 | 584000 | 328000 | 192000 | 128000 |
| 1 | 584000 | 328000 | 192000 | 128000 |
| 2 | 291000 | 328000 | 128000 | 128000 |
| 3 or higher | 152000 | 328000 | 88000 | 88000 |

Mode 0x400/0x200 take precedence over the limiter flag in the inspected AIDL helper. A busy level above 3 is clamped to index 3. This **explains the observed 291k-to-584k change** as a level 2-to-1 transition; it does not prove the trigger was radio congestion. These are encoder target bitrates, not measured RF throughput.

Added public-reconstructable lookup and tests to ssc-win-bridge/src/ssc_a2dp.rs. Decompilation logs and repeatable Ghidra scripts: ghidra-ssc-bitrate-timestamp.log, ghidra-ssc-bitrate-tables.log, TraceSscBitrateAndTimestamp.java and DumpSscBitrateTables.java.

## New prototype: passive SSC discovery in an actual Windows A2DP transmitter
Modified the **local** third-party A2DP Windows Bridge checkout:
- app/src/crates/codec/src/caps.rs: recognizes Samsung vendor 0x75 and both candidate IDs (0x0103, 0x0e03), recording (SEID, codec ID, flags).
- app/src/crates/bt-host/src/app.rs: logs an SSC discovery record and explains that transmission is disabled.
- No new SSC encoder kind, no automatic selection, no raw radio transmissions, no Windows driver rebinding.
- Standalone patch saved to patches/a2dpwb-ssc-passive-discovery.patch. The third-party source is not bundled in our main research project.

The patched third-party codec crate passed cargo check **and all 28 of its unit tests**, including the new passive SSC discovery test, after fetching BTstack and build dependencies. The full patched bt-host crate also passed cargo check on Windows, including the new event-logging match arm. No Bluetooth radio was used.

Local Windows hardware reports only the built-in Intel Wireless Bluetooth adapter, USB VID 8087/PID 0026. No dedicated, spare USB dongle was detected, so an A2DP Windows Bridge WinUSB live test would risk taking over the internal Windows Bluetooth stack. It was intentionally not attempted.

## Verification
- Standalone Rust ssc-win-bridge: **15/15 tests** passed, including a new encoder-frame header validator.
- Python offline tests: **17/17 tests** passed.
- Synthetic 0x8A SSC CIE example parsed correctly as 96 kHz / UHQ2 / limiter off / stack mode 0x400.
- Real btsnooz buffer decoded and sanitized. The lack of ACL prevented AVDTP ID resolution.
- Compilation and **28/28 tests** of the patched A2DPWB codec crate succeeded; no Buds playback was attempted.
- Extra native ARM64 tests at 96 kHz: bitrate 152000 -> 174-byte frames, bitrate 328000 -> 372-byte frames; canaries intact.

## New knowledge compared to before
We moved from “no accessible HCI file” to a functioning in-memory diagnostic decoder with a measured, testable explanation of why the ring buffer cannot establish the AVDTP negotiation (zero ACL packets). We also resolved two previously opaque feature bits, one UHQ2 mode selector and four complete busy-level bitrate tables (16 static entries). The Windows-native transmitter now has a passive detection hook rather than none. Additionally, native probing of 18 consecutive frames and saved SSCF samples reveals repeatable encoder-frame signatures and sequence counters: a 0xFF 0xEE family carrying a 4-bit modulo-16 sequence in the upper nibble of byte 2, and a 0xFF 0xE0..EF family carrying an 8-bit counter across the low nibble of byte 1 and upper nibble of byte 2. This is **codec-frame framing**, NOT the unknown Bluetooth A2DP/RTP media header. Pure Rust validation and tests are in ssc-win-bridge/src/frame.rs.

What we have NOT learned: which vendor codec ID the Buds actually negotiate over the air, the complete SSC-specific RTP/media header and fragmentation policy, whether the Buds accept a non-Samsung host's stream, or how to execute the proprietary encoder independently on x64.

## Next tasks, in order
1. Obtain permission for a fresh *full HCI ACL* trace (reconnecting/resetting Bluetooth after enabling full logging may interrupt audio), or use a dedicated USB Bluetooth adapter with BTstack to inspect sink capabilities without touching the internal Windows driver.
2. Verify AVDTP vendor ID, feature bytes and radio packet format against real packets. Never guess them in a sender.
3. After actual peer evidence, enable isolated prototype SEP configuration, RTP framing and short-stream verification with existing Samsung encoder bridge.
4. Add buffering, RTP pacing/quality adjustment, and native Windows capture only after the Buds successfully decode an SSC stream.
5. Longer-term: eliminate phone dependence with a legal independent encoder or an appropriate local runtime.

## Assessment
Progress on a genuine Windows end-user SSC UHQ playback implementation remains around **3/10**: this session made substantial advances in protocol understanding and code integration, but **no on-air Windows-to-Buds playback has yet been achieved**.
