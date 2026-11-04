# Experimental SSC UHQ 886 kbps native Android rate-table override

**Date:** November 4, 2026 (device-local time, Asia/Kolkata).
**Environment:** Personal Linux workstation → ADB → temporarily rooted Galaxy Z Fold7 SM-F966B, Android 17, firmware `F966BXXUCCZIH`. Galaxy Buds4 Pro connected over native SSC 96-kHz, 24-bit stereo A2DP while music playback was active.
**Scope:** A bounded, **in-memory-only** override of Samsung's original software SSC adaptive bitrate table, paired with verbose Samsung Bluetooth and L2CAP logs. No firmware, controller NVM, on-disk system library, Bluetooth settings or earbud pairing data was altered.

## Summary — new positive evidence

**We demonstrated native Android sender selection of 886,000 bps, followed by real Samsung AVDTP/L2CAP transmit-submission requests carrying 1,012-byte SSC/RTP payloads.**

- Ghidra found the UHQ2 rate table at `libbluetooth_jni.so` ELF file offset **`0x1077B0`**, corresponding to Ghidra symbol `DAT_002077B0` (which includes an analysis-tool image base). Entries were verified against the **running Bluetooth process**: `[584000,584000,291000,152000]`.
- Read-only `/proc/PID/mem` inspection worked. A separate helper opened the live process memory with `O_RDWR` without modifying it, establishing that a reversible process-local change was technically possible.
- A guarded test changed **only table index 1** from `584000` to `886000` for **1,500 ms**. A backup watchdog process ran independently and verified rollback.
- The helper printed `OVERRIDE_VERIFIED: [584000,886000,291000,152000]` and `ROLLBACK_VERIFIED: table[1]=584000`. A separate post-test read verified **all four original values**.
- The immediate logcat sample showed **95 calls** to Samsung's native `a2dp_ssc_encode_frames` at **`bitrate_idx 1 bit_rate 886000`**, proving actual native sender selection. A transition **`886000 -> 584000`** was logged on restoration. The overlapping sample also contained 153 calls at 584000.
- A near-contemporaneous verbose log at **18:59:00.009** showed:

  ```text
  AVDT_WriteReqOpt: avdt_handle=5 ... m_pt=0x60
  L2CA_DataWrite: CID: 0x0040  Len: 1012
  l2c_csm_open: ... psm: BT_PSM_AVDTP(0x0019)
  l2c_link_check_send_pkts: Sending to lower layer
  AVDT_WriteReqOpt: result=0
  ```

  This is the **real Android Bluetooth media transport** accepting a 1,012-byte L2CAP payload for transmission, not the earlier Linux loopback test. The payload size is exactly **12 bytes RTP + 1000 bytes encoded E4**. The direct raw HCI ACL payload bytes were *not* extracted; assigning the E4 marker to this particular packet is inferred from the synchronized bitrate selection and length.

- After the experiment, `dumpsys bluetooth_manager` still showed **SSC, 96kHz, 24-bit stereo**, an A2DP state machine in **Connected** state, and `Offload started handle: 0`. The process-local rate table was restored. The available error summaries showed no immediate fatal encoder/L2CAP errors.

**Interpretation:** Samsung's stock software stack can select, encode and **submit 886-kbps-sized SSC audio packets to AVDTP/L2CAP** when the adaptive table is overridden. The claim that Android would automatically refuse every E4-sized packet before L2CAP is no longer tenable on this exact firmware. **We have NOT proved the radio delivered the packet successfully, nor that the Buds4 Pro decoded it or produced audible 886-kbps audio.** L2CAP `DataWrite` and `AVDT_WriteReqOpt result=0` are local acceptance/handoff events, not remote decoder acknowledgments.

## Critical condition: adaptive link-quality index

A second experiment used the exact same **index-1-only** override for **2,000 ms** while streaming relevant log tags into an anonymized collector. The helper again verified patch and rollback, but it did **not** force 886-kbps output that time:

- Live encoder logs selected `bitrate_idx 2 bit_rate 291000` in 234 observed calls.
- The test observed 260 `L2CA_DataWrite Len:672` events with 260 `AVDT_WriteReqOpt result=0`.
- Subsequent read-only inspection of two Samsung global variables (`DAT_0104AAF8`, `DAT_0104AAFC`, offset-corrected for Ghidra's `0x100000` image base) confirmed **target=291000, previous=291000**.
- The **672-byte** RTP size is ambiguous without frame bytes: it can be either one 660-byte E3 frame + 12-byte RTP or **two 330-byte E0 frames + 12-byte RTP**. It therefore cannot by itself prove continued 584-kbps encoding in the second test.

This shows a hardcoded table-index-1 override only works while Samsung's quality controller selects index 1. It is **not** a universal 886-kbps force switch. A robust future probe must first identify the current quality level and patch only its matching table entry, or otherwise use a carefully scoped approved override mechanism.

## About the MTU concern

The earlier Android HAL had reported `peerMtu=1005`. We previously predicted an E4 frame could not fit in one 1005-byte RTP-inclusive packet (1000 encoded + 12 RTP = 1012). **The observed L2CAP `Len:1012` events disprove the narrower claim that the local software AVDTP/L2CAP API refuses to enqueue a 1012-byte packet.**

However, this does not establish that the peer's AVDTP/L2CAP accepted the entire SDU or that the receiving decoder processed it. The exact meaning of the HAL `peerMtu=1005`, possible lower-layer ACL fragmentation, and remote receive buffer limits still require a full HCI capture and/or receiver-side playback confirmation.

The local Intel Linux adapter's MTU is irrelevant here; we used the native **Fold7's** Bluetooth controller.

## Reproducible code and controls

Source-only artifacts:
- `experiments/native_ssc_temp_override.c`: exact-firmware in-memory override with strict four-value guard, two independent rollback opportunities, PID/mapping verification, maximum 5-second TTL, and no disk writes.
- `experiments/read_ssc_table.c`: read-only `/proc/PID/mem` verification.
- `experiments/inspect_ssc_globals.c`: read-only live target/applied bitrate values (and rate table).

The test source is **research code**, not an on-device installer or universal Samsung support patch. Hardcoded virtual offsets and symbol locations apply only to the binary hash used during the experiment and MUST be reverified before any other phone firmware. The live experiments can cause audio glitches, temporarily disconnect Bluetooth, or crash/restart the Bluetooth process. Never persist the patch or flash firmware. The 1,500-ms experiment has already finished and its original table was verified restored.

All raw Android logs, music and Bluetooth identifying data remain untracked; the temporary on-device executable lives under `/data/local/tmp/` and the source's local work copies under gitignored `tools/`. No raw HCI ACL packets were captured.

## What remains before declaring 886-kbps Buds4 Pro playback

1. **Audible feedback:** did the Buds continue playing audio seamlessly, briefly mute, stutter, or disconnect during the bounded 886-kbps period? No listener feedback has been received.
2. **Full HCI ACL capture** during a repeat: confirm actual `FF E0 ... 04` encoded E4 bytes in the transmitted media SDU and determine controller completion/fragmentation behavior. Android's currently accessible BTSNOOZ summary has only commands/events, not ACL data.
3. **Receiver acceptance:** audible audio and no gaps, ideally with a synchronized test signal, are required to infer decoder support. Sending `Len:1012` with result zero does not establish decoding.
4. **MTU/receiver parser:** distinguish the archived R640 firmware's 800-byte queue and E0/E3/E6-specific pre-parser from the actual radio packet/reassembly path running on these physical Buds.
5. **Only then** consider a dynamic automatic-index override or user-selected 886 kbps mode. Higher than 886 kbps still lacks a recognized native encoder header mode in the inspected `libScalable_Encoder.so`.

**Bottom line:** We crossed the important Android sender/packetization barrier; 886 kbps is now experimentally demonstrated through Samsung's AVDTP/L2CAP submit path, although its *on-air/decoded* status is unresolved.
