# Fold7 seven-bitrate SSC UHQ sweep and offload audit
Research date: November 4, 2026. Original rooted Samsung Galaxy Z Fold7 (SM-F966B), Android 17.

## Scope and provenance

Ran `ssc_encode` from the original proprietary `/system/lib64/libScalable_Encoder.so` using a deterministic, low-amplitude synthetic 440-Hz PCM32 stereo tone. The harness requests 96,000 samples/s, 864 samples/channel per frame (9 ms), and eight successive frames at each of seven explicitly recognized rates. Each configuration runs in a fresh Android userspace process with a guard-protected output buffer. Reproducible code: `scripts/sweep_ssc_uhq_modes.py` (generates and compiles a temporary mode-extended copy of the previously published `ssc_arm64_probe.c`). All raw PCM/encoded frame data remain private on the connected phone; sanitized result JSON and synthetic SHA-256 values remain gitignored under `tools/`. No Bluetooth setting, firmware, or device pairing was altered.

## 1. Exact frame length / marker results

| Requested rate (bit/s) | Software encoder returned frame length | frame[3] & 0x1F | SSC E-type | Output status |
| ---: | ---: | --- | --- | --- |
| 152000 | **174 B** | **0x06** | E6 | 8/8 consistent |
| 250000 | **284 B** | **0x05** | E5 | 8/8 consistent |
| 291000 | **330 B** | **0x00** | E0 | 8/8 consistent |
| 308000 | **350 B** | **0x01** | E1 | 8/8 consistent |
| 442000 | **500 B** | **0x02** | E2 | 8/8 consistent |
| 584000 | **660 B** | **0x03** | E3 | 8/8 consistent |
| 886000 | **1000 B** | **0x04** | E4 | 8/8 consistent |

All modes returned exact frame extents matching the last modified position of the guarded output and kept guard bytes intact. These are complete *encoder output* results, **not on-air Bluetooth captures or receiver playback evidence**. The approximate three-byte excess over `target_bps × 864 / 96000 / 8` is the codec-frame header/rounding overhead, not an additional RTP payload header.

## 2. Comparison across Samsung encoder-creation modes

Ran every bitrate at mode arguments **24**, **32**, and **34**:
- 7 rates × 3 modes = **21 configurations**.
- 8 consecutive frames per configuration = **168 synthetic SSC frames total**, 56 per mode.
- Full 8-frame output SHA-256 was **identical among 24, 32 and 34 for all seven bitrate settings**. Header, length, frame extent and guard results also matched.
- Every synthetic mode-rate combination passed the consistent 96kHz frame length/identifier checks.

This is direct evidence that these mode-argument values do not change the output under the tested PCM signal and parameters. It is **not proof that HiFi and UHQ are universally the same** for different audio, rate selection, sample format, context or firmware. The separate sink capability bits can still control samplerate or sender policy.

The independent [ashenzar/ssc-uhq findings F13](https://github.com/ashenzar/ssc-uhq/blob/main/findings.md) reports priority selection `0x08`→ mode **34**, `0x04`→**32**, `0x02`→**24**, else **16**. These numeric modes are not literal 34-bit PCM.

## 3. Samsung SSC → audio HAL converter

Using Ghidra 12.2, decompiled the actual Fold7 `libbluetooth_jni.so` function:

- **`A2dpSscToHalConfig` at 0x00976278**. It reads an A2DP SSC codec configuration object and converts supported SSC sample-rate enums and channel/sample-format values into a `SehCodecConfiguration` SSC variant. Enumerated sample rates include 16, 24, 44.1, 48, 88.2, 96, 176.4, and 192 kHz. **Acceptance as a configuration value does not establish the encoder or Buds support it**.
- **`A2DP_VendorAdjustCodecSsc` at 0x00A91968** validates/adjusts an existing SSC vendor CIE and contains no new encoder or high-bitrate table in the inspected body.
- The separate `/vendor/lib64/libsehbluetooth_audio_session_aidl.so` implements `BluetoothAudioCodecs::IsOffloadSscConfigurationValid` (0x0010D984 in Ghidra's imported image) and `GetA2dpOffloadCodecCapabilities` (0x0010DFD0). These implement SSC-specific capability validation and routing through Samsung's AIDL audio session.
- **Neither converter/validator contains an alternate 886k or >886k encode-rate selection table.** They configure the HAL, rather than performing the proprietary SSC DSP encoding. Qualcomm/controller firmware implementing actual hardware offload was not decompiled here.

Source-only reproducible Ghidra script: `ghidra-scripts/AuditSscToHalConfig.java`. Decompiler output is proprietary and remains ignored locally under `tools/ghidra-runs/bluetooth-AuditSscToHalConfig.log`.

### Implication

These functions confirm *the existence of an SSC offload interface*, but do **not** prove that a second encoder supports 886 kbps, 2.304 Mbps, or anything above the live sender's 584 kbps. The prior normal UHQ2 rate table remains `[584000, 584000, 291000, 152000]`; the E4 path is encoder-valid but not selected by that table.

## 4. Linux Bluetooth injection / negotiated MTU

**Real-device injection was not performed this pass.** The user's actual Linux desktop is the appropriate environment, but CatDesk Personal's isolated command environment does **not** expose the host system D-Bus socket:

- `bluetoothctl list`: D-Bus assertion / exit 134.
- `btmon -i hci0`: **Failed to bind channel: Operation not permitted**.
- `python3 linux/ssc_bluez_probe.py`: D-Bus socket FileNotFound (`/run/dbus/system_bus_socket` absent).

These are **connector isolation/permission failures**, not proof that the Intel Bluetooth hardware or earbuds lack SSC. The user previously ran `python3 linux/ssc_bluez_probe.py` successfully in the real desktop session and saw one adapter, but no exposed endpoints while unconnected.

The authoritative BlueZ `org.bluez.MediaTransport1.Acquire()` API returns **(fd, read_mtu, write_mtu)**. That write MTU must be observed on a *negotiated Samsung SSC transport*, not inferred from SBC/AAC transport or Android's HAL-reported MTU. References:
- https://kernel.googlesource.com/pub/scm/bluetooth/bluez/+/master/doc/org.bluez.MediaTransport.rst
- https://github.com/bluez/bluez/blob/master/doc/btmon-a2dp.rst

### 886-kbps MTU condition

At 96 kHz / 864 samples per frame, E4 is exactly **1000 encoded bytes**. With the known 12-byte fixed RTP header, the single-packet RTP payload is **1012 bytes** before any additional SSC media header. Thus, **if the negotiated BlueZ write MTU includes RTP and is less than 1012**, a single E4 RTP packet cannot fit; a failure or silence then would NOT isolate a decoder problem. Normal E3/584 kbps is 660+12=**672 bytes** RTP-inclusive.

The audited public SM-R640 firmware image additionally shows a *particular* 800-byte SSC receive-queue cap, but its relation to live BlueZ transport / possible reassembly paths remains unproven. The E4 initial validator accepts a long frame and a UHQ pre-parser skips E4 yet its caller ignores the return result. **No unconditional global E4 rejection has been demonstrated.**

### Next step on actual desktop

Connect your Buds4 Pro to Linux in the normal user session, then run read-only `python3 linux/ssc_bluez_probe.py`. For a real link/MTU capture use an explicitly authorized Bluetooth monitor and custom SSC BlueZ A2DP source; no radio E4 test should be interpreted without confirming vendor ID **0x00000075**, codec ID **0x0103**, the actual SET_CONFIGURATION feature byte and **write_mtu** from a live SSC transport.

For controlled transmission start with E3/584 kbps to prove valid RTP packetization and audible decoding, then send a very short E4/886-kbps test **only if the BlueZ transport has sufficient MTU or verified SSC fragmentation**. Receiver silence alone is not adequate evidence without the transport logs. No changes to Bluetooth settings or earbud firmware were made in this sweep.

## Verdict

- **886 kbps: confirmed encoder output mode** E4/1000 bytes, all 3 encoder-mode arguments matched byte-for-byte for this PCM experiment.
- **2.304 Mbps: no recognized software frame mode or measured A2DP compressed transport at this bitrate**; 3-DH5 Classic asymmetric maximum user rate is ~2178.1 kbps before audio-protocol overhead.
- **Hardware offload: SSC-specific conversion and capability interface found, but no higher-rate encoder established.**
- **Buds4 Pro E4 decoding: unverified** until a real SSC BlueZ transport is negotiated and its MTU checked.

No proprietary binary, original vendor decompilation output, sensitive wireless trace, or identifying Bluetooth address is part of this report.
