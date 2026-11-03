# Linux SSC bridge and >556 kbps investigation — 2026-11-03

## Scope and conclusion

We built a **Linux host -> ADB forwarding -> original ARM64 Samsung SSC encoder -> provisional RTPv2 -> local Unix SOCK_SEQPACKET** proof of concept. All generated audio samples were synthetic; no existing music, microphone recording, personal Bluetooth identifiers, HCI packets or pairing keys were copied into the public repo.

**Succeeded:** Verified encoder frames at 584kbps and 886kbps and transported complete provisional RTP packets across a local packet-preserving Linux socket. Bounded pipelining made the test faster than real time in offline throughput.

**Not succeeded:** No BlueZ A2DP negotiation, no Buds4 Pro receiving SSC packets, and no live WirePlumber/PipeWire output profile. CatDesk's restricted shell cannot access the host D-Bus system socket. No Bluetooth driver, phone pairing, or firmware was modified.

## 1. Validated Samsung high-rate encoder modes

The original `libScalable_Encoder.so` was extracted on the user's Fold7 and matched the earlier SHA-256 `90c4c1cbd59b0edb9df6d255acc1f752e542e0cb99d3de8e842afc7ca9914ce7`. Its `get_uhq_info_from_bitrate`, `set_data_frame_header`, `get_header_from_bitrate`, and `set_limit_gain_from_bitrate` functions were decompiled privately on Linux with Ghidra 12.2.

### Encoder-recognized 96kHz modes

| Requested encoded rate | Return length (864 stereo samples/channel) | UHQ selector pair | Header code returned by Ghidra | Actual 96k/24-bit frame prefix |
| --- | ---: | --- | --- | --- |
| 291000 | 330 bytes | (1,1) | 0xE0 | `FF E0 0D 00` (low nibble 0) |
| 308000 | ~350 bytes, not independently characterized here | (recognized in decompiler) | 0xE1 | `FF E0 0D 01` |
| 442000 | ~500 bytes, not independently characterized here | (recognized in decompiler) | 0xE2 | `FF E0 0D 02` |
| 584000 | 660 bytes | (1,1) | 0xE3 | `FF E0 0D 03` |
| **886000** | **1000 bytes** | **(1,1)** | **0xE4** | **`FF E0 0D 04`** |
| 1200000 | return 1279 but 1384 bytes modified | (0,0) | fallback 0xF3 | `FF EE 01 F3` family |
| 2304000 | return 1279 but 2656 bytes modified | (0,0) | fallback 0xF3 | `FF EE 01 F3` family |
| 2400000 | return 1279 but 2766 bytes modified | (0,0) | fallback 0xF3 | `FF EE 01 F3` family |

For 584/886, the actual returned frame length agrees with last modified output byte; 2.4Mbps does **not**, so 2.4Mbps is not a safe/validated encoded SSC frame. Memory buffer guards remained intact, but canaries alone never prove correct return semantics or decodability.

The encoder has an actual *recognized* 886kbps format. This does **not** imply the Buds4 Pro advertise or support that format on the air. Samsung's official documentation supports **24-bit/96kHz** but does not state 2.4Mbps as the actual compressed link throughput:
https://www.samsung.com/in/audio-sound/galaxy-buds/galaxy-buds4-pro-white-sm-r640nzwainu/

### A critical additional limit in the Bluetooth source

The analyzed Samsung `a2dp_vendor_ssc_send_frames` path, at 96 kHz in UHQ2, selects `[584000,584000,291000,152000]` using the clamped busy/quality index. It contains **no 886000 entry in this rate-control table**. Thus 886k is an encoder-supported mode, but the inspected normal Samsung UHQ2 sender does not select it using this path.

Other firmware variants or separate configuration paths may exist, but they are not proven here.

## 2. Conditional Bluetooth packetization bound

The Buds4 Pro previously reported `peerMtu=1005` through Samsung's HAL. The Samsung SSC sender uses RTP, but its **SSC-specific media header and MTU accounting are not yet reconstructed/validated from real HCI packets**.

Under the *explicit assumption* that the 1005-byte value includes the standard 12-byte RTP header, available RTP payload is **at most 993 bytes** before vendor media headers.

| Encoder frame | Frame bytes | Minimum RTP+frame bytes | Fit in assumed 1005B? |
| --- | ---: | ---: | --- |
| UHQ2 584kbps | 660 | 672 | Yes (up to 333 bytes headroom before extra media header) |
| 886kbps | 1000 | 1012 | **No (at least 7 bytes too large)** |
| 2.4Mbps request | Not a reliable frame | n/a | Not established |

The 886kbps path would need a negotiated RTP-inclusive MTU **at least 1012 bytes plus any proprietary media header**, or a verified fragmentation mechanism. Our hypothetical `--mtu 1200` mode proves only that the **offline Linux packet processor** can handle a longer packet.

Do **not** assume fragmentation can be invented by splitting the frame: without the receiver's exact SSC media header and reassembly semantics, the Buds will not interpret arbitrary fragments.

## 3. Linux bridge implementation and benchmarks

Source:
- `linux/ssc_linux_bridge.py`: phone-backed encoder + provisional RTPv2 builder + Unix SOCK_SEQPACKET loopback receiver, MTU bounds, encoder marker checks, bounded request batches
- `linux/ssc_bluez_probe.py`: read-only BlueZ D-Bus endpoint inspection; opt-in temporary *passive/reject-only* custom SSC source endpoint
- `linux/ssc_pipewire_import.py`: optional explicit PipeWire node capture -> local WAV -> offline SSC test, with auto-delete of temporary capture
- `test_ssc_linux_bridge.py`: synthetic loopback, RTP header and sequence tests, 584/886 MTU checks, privacy-preserving endpoint parsing
- `ghidra-scripts/TraceSscRateModes.java`: reusable private-rate-analysis script; no decompiled proprietary output committed

All Linux tests below used a 2-second 96kHz stereo 16-bit synthetic tone with a 24-bit SSC encoder context, 864 samples per channel per frame.

| Mode | 584000, 1005 MTU, batch1 | 584000, 1005 MTU, batch8 | 886000, 1005 MTU, batch8 | 886000, **hypothetical** 1200 MTU, batch8 |
| --- | --- | --- | --- | --- |
| Encoded SSC frames | 223 | 223 | 223 | 223 |
| Exact frame size | 660 bytes | 660 bytes | 1000 bytes | 1000 bytes |
| RTP+SSC packets through local loopback | 223 | 223 | 0 (all failed MTU bound) | 223 |
| Frame header rejects | 0 | 0 | 0 | 0 |
| Overall elapsed incl. startup | 4.041s | 1.926s | 1.809s | 1.942s |
| Active encoder/ADB processing only | ~3.3s (estimated from prior measurement, not exact) | 1.371s | 1.295s | 1.392s |
| Active throughput vs audio duration | below real time | ~1.46x | ~1.55x | ~1.44x |

**Batching is not equivalent to low-latency real-time playback.** Eight 9ms SSC frames represent 72ms of PCM before one group is completed, plus encoding and transport delay. The loopback is an offline correctness/throughput test, not radio timing or audio quality validation.

All audio and local packet data remain under `tools/` (gitignored); only synthetic sample metrics are documented.

## 4. BlueZ/PipeWire feasibility and isolation blocker

Linux BlueZ publicly supports registering A2DP endpoints via `org.bluez.Media1.RegisterEndpoint` and a stream's read/write MTU through `org.bluez.MediaTransport1.Acquire()`:
- https://github.com/bluez/bluez/blob/master/doc/org.bluez.MediaEndpoint.rst
- https://kernel.googlesource.com/pub/scm/bluetooth/bluez/+/master/doc/org.bluez.MediaTransport.rst

PipeWire maintains a custom BlueZ5 codec plugin interface; it is not enough to list `ssc` in WirePlumber's `bluez5.codecs`. A standalone BlueZ source endpoint is a reasonable *first* transport experiment before PipeWire codec integration:
- https://github.com/PipeWire/pipewire/blob/master/spa/plugins/bluez5/bluez5-dbus.c
- https://github.com/PipeWire/wireplumber/blob/master/src/config/wireplumber.conf.d.examples/bluetooth.conf

`linux/ssc_bluez_probe.py` defaults to **read-only D-Bus object introspection**. `--register` is an explicit, temporary passive endpoint: it rejects any actual streaming configuration and unregisters when the script exits, avoiding unverified Bluetooth transmission. The hypothetical feature byte `0x8A` is **not a captured negotiation**.

**Execution blocker:** CatDesk Personal's shell is inside a constrained environment with `/run/dbus/system_bus_socket` absent. Attempting `python3 linux/ssc_bluez_probe.py` correctly returned `org.freedesktop.DBus.Error.FileNotFound`; this is *not evidence that BlueZ or the Intel Bluetooth controller is broken on the actual host*. The user's normal desktop session is necessary for live endpoint registration, observing remote sink capabilities, and reading the actual write MTU. No drivers or pairing were changed.

A PipeWire import wrapper is provided, but cannot be validated against the host audio graph inside the restricted shell. It records only a user-explicitly chosen output monitor, then encodes offline. It does not register a new system audio sink.

## 5. What we established and what remains

**Established:**
- Exact encoder recognition of 886kbps, distinct from arbitrary high-bit-rate memory writes
- 886k marker 0xE4 / low-nibble `04` in verified encoded frames
- 886k frame length 1000 bytes at 96 kHz / 864 samples / 24-bit encoder context
- Maximum normal UHQ2 rate table in this Samsung sender still 584kbps
- The provisional single-packet MTU requirement for 886k is at least 1012B plus any SSC media header, under the documented MTU assumption
- A Linux/USB/ADB/encoder/RTP-skeleton/Unix-socket **offline** prototype with real encoded output
- Improved offline throughput using 8-frame batches
- BlueZ D-Bus passive endpoint probe code and separate PipeWire capture-import helper

**Unresolved:** exact Buds AVDTP vendor codec ID (0x0103 vs 0x0e03), received capabilities, packetization and fragmentation, actual local BlueZ write MTU, whether earbuds accept 886k, a local native encoder and actual Linux or Windows SSC playback.

## Next live experiment

From a *normal* personal Linux desktop terminal, start with:

```bash
cd ~/Documents/ssc-research/samsung-ssc-uhq-research
python3 linux/ssc_bluez_probe.py
```

If BlueZ is reachable and the user wants to observe negotiation, the optional passive endpoint can be run for a short window:

```bash
python3 linux/ssc_bluez_probe.py --register --codec-id 0x0103 --flags 0x8a --lifetime-seconds 45
```

This does not transmit audio, but may temporarily influence BlueZ's codec selection while running. Follow with a user-authorized HCI ACL trace to validate codec flags and actual packet MTU, then prototype the real vendor media header. Do not enable direct radio sending until those fields are grounded.

**Bottom line:** 584kbps is already above 556kbps and is our active confirmed UHQ2 playback mode. 886kbps is a real encoder mode, technically transportable across the Linux host pipeline, but **not yet bridged to Buds4 Pro**. 2.4Mbps is not validated by this binary.
