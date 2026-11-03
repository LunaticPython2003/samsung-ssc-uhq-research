# Four SSC investigations — portable research summary

**Investigated:** 2026-11-03 on an earlier Windows machine; re-established tooling on a separate Zorin OS machine afterwards. This is a *derived technical summary*, not a copy of the proprietary Ghidra decompilation. The original Windows-only decompilation logs are not part of the Git repository.

## 1. Rate-control table users and loop timing

In the inspected Samsung `libbluetooth_jni.so`, `a2dp_vendor_ssc_send_frames` was identified as a runtime table consumer. The UHQ2 bitrate table is at image address `0x002077B0` on this firmware, with references in the send-frame path near `0x00A942FC` and `0x00A94344`. An older/standard table appears near `0x00207600`.

At frame-processing time, the path reads a current quality/busy-level index, clamps it to 3, obtains a target bitrate, compares against the last bitrate and schedules an encoder update when changed. Thus target bitrate selection is **not limited to initial AVDTP handshake**.

An internal counter limited to 1500 was observed near the diagnostic logging branch, **not verified to be a 1500-frame or 50 ms debounce**. The earlier live 291→584 kbps transition happened about 50 ms apart, but that is not enough to prove a timer/hysteresis policy. The producer of the quality-level state remains unresolved; no confirmed causal connection to LQI or RSSI yet.

Reproduce xrefs with `ghidra-scripts/TraceSscControlXrefs.java` against your own locally extracted Samsung Bluetooth library. Function addresses are tied to the tested firmware build.

## 2. 0x400 versus 0x200 selection

The internal Samsung SSC mode codes were reconstructed from `A2DP_VendorGetSscType`:

| Internal value | Selection |
| --- | --- |
| `0x400` | UHQ2 flag `0x02` set |
| `0x200` | non-UHQ2 96 kHz branch |
| `0x100` | alternative legacy feature branch, bit `0x04` |
| `0x080` | other legacy branch |

Feature bit `0x08` has **inverse bitrate-limitation polarity**: when set, limiter is off. These values are **internal mode return codes**, not vendor capabilities literally transmitted during AVDTP `GetCapabilities` or `SetConfiguration`. There was no verified `0x800` case in this selector. It remains possible that another firmware or codec family uses further modes.

Still unresolved: on-air codec ID `0x0103` versus the separate `0x0E03` static initialization reference; a full ACL/AVDTP trace is required.

## 3. Target rate, frame sizes and packet bounds

The Samsung encoder consumes **864 samples/channel per frame**. At 96 kHz, that is **9 ms**. Its entropy-coding and bit-allocation paths take the target bitrate as input.

| Selected bitrate | Theoretical 9 ms compressed budget | Isolated encoder frame | Overhead |
| --- | ---: | ---: | ---: |
| 152 kbps | 171 B | 174 B | 3 B |
| 291 kbps | 327.375 B | 330 B | 2.625 B |
| 328 kbps | 369 B | 372 B | 3 B |
| 584 kbps | 657 B | 660 B | 3 B |
| 886 kbps | 996.75 B | 1000 B | 3.25 B |

These frame lengths were measured with *synthetic input*, not by capturing Bluetooth radio traffic. The near-3-byte difference suggests an **internal codec-frame overhead**, not necessarily the additional A2DP/RTP media payload header.

During real Buds4 Pro playback, Samsung's HAL reported `peerMtu=1005`. **If** that MTU includes a fixed 12-byte RTP header, a 660-byte frame fits, whereas a 1000-byte frame does not. A 330-byte frame could fit three times only if the SSC-specific payload header is at most three bytes. True packet aggregation/fragmentation is unverified.

The repeatable arithmetic is implemented by `ssc_rate_frame_analysis.py`; it does **not** generate any radio packets.

## 4. Frequency-band allocation and quality degradation

The original encoder contains `ssc_mdct_forward`, `ssc_compute_band_energies`, `ssc_compute_allocation`, `ssc_quant_coarse_energy`, `ssc_quant_fine_energy`, `ssc_quant_all_bands`, and the `normal_headroom`/`uhq_headroom` branches.

A bitrate threshold near **192 kbps** changes one headroom processing path. Inside `uhq_headroom`, another branch tests approximately **270 kbps**. These code paths use frequency-dependent gain and nonuniform band bit allocation, meaning reduced rates may alter both spectral shaping and quantization noise.

**Not established:** a specific hard high-frequency cutoff such as 20 kHz, or an exact bit-budget-by-band table. Confirming those requires calibrating band indices to frequencies and ideally comparing reconstructed PCM from a decoder.

Use `ghidra-scripts/TraceSscHeadroom.java` for private local inspection. Do not commit its proprietary decompilation output.

## Next confirmed engineering gates

1. Capture actual Bluetooth **ACL** packets containing AVDTP discovery/negotiation and SSC media.
2. Trace the quality-level variable's producer to distinguish controller metrics from application-level queue control and identify hysteresis.
3. Validate the on-air codec identifier, flags, RTP payload header and frame aggregation.
4. Only then enable a controlled Bluetooth send path using a separate USB adapter; the existing Windows discovery patch is intentionally passive.
5. Resolve a native/distributable encoder separately from the host-side transport.

**Status:** Important protocol details reconstructed, but **not yet working Windows-to-Buds SSC playback**.
