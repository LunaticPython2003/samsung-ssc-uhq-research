# Experimental Linux SSC bridge

This directory contains the Linux-side proof of concept. **It does not send SSC over Bluetooth yet.** It encodes real PCM using Samsung's original ARM64 software library on a temporarily rooted Galaxy Fold7, then tests preliminary RTP framing through a local packet-preserving socket.

## 1. Reproduce the Linux-to-Android-to-RTP loopback

With the phone connected over USB and `adb shell su -c id` succeeding:

```bash
python3 linux/ssc_linux_bridge.py --wav tools/test.wav --bitrate 584000 --batch-frames 8 --mtu 1005
```

Required input: stereo PCM WAV, 44.1/48/96 kHz; the tests used a **synthetic** 96 kHz tone. A 2-second, 96 kHz synthetic WAV can be generated with:

```bash
python3 - <<'PY'
import math, struct, wave
with wave.open("tools/test.wav", "wb") as out:
    out.setnchannels(2); out.setsampwidth(2); out.setframerate(96000)
    out.writeframes(b"".join(
        struct.pack("<hh", *(int(3000*math.sin(2*math.pi*440*i/96000)),)*2)
        for i in range(192000)
    ))
PY
```

No Bluetooth adapter, A2DP endpoint, HCI packet or wireless device is opened by this command. It takes the phone's actual SSC frames and sends a **provisional** 12-byte RTPv2-header-plus-frame packet through Linux `AF_UNIX/SOCK_SEQPACKET`. It checks packet equality and MTU size; that says nothing about whether the earbuds decode the packet.

### High bitrate comparison

```bash
python3 linux/ssc_linux_bridge.py --wav tools/test.wav --bitrate 886000 --batch-frames 8 --mtu 1005
python3 linux/ssc_linux_bridge.py --wav tools/test.wav --bitrate 886000 --batch-frames 8 --mtu 1200
```

The first command should report oversized frames, because 1000-byte SSC frame + 12-byte fixed RTP header exceeds an assumed RTP-inclusive MTU of 1005 by **at least seven bytes**. The second **only** tests a hypothetical 1200-byte MTU in loopback. The actual Buds MTU/fragmentation convention is not yet verified. **Receiver re-audit:** the archived Buds4 Pro firmware lacks a dedicated E4 branch in one UHQ pre-parser, but E4 can pass initial length validation and that pre-parser's caller ignores its return value. Another SSC queue caps frames at 800 bytes. A larger MTU alone therefore does **not** establish 886-kbps playback. DSP support and alternative reassembly remain unverified. See [the corrected instruction-level audit](../docs/r640-e4-reaudit-2026-11-04.md).

High-rate requests above the allowlisted 886000 bps are deliberately **rejected by the Android RPC server**: isolated tests at 1.2–2.4Mbps wrote beyond the length returned by the encoder, and their header marker was unrecognized.

### Batching

`--batch-frames 8` pipelines eight PCM frames over one ADB roundtrip. That can make **offline throughput** faster than audio duration, but an eight-frame batch represents up to 72ms of audio plus processing and connection latency. It is **not a demonstrated low-latency live playback path**.

## 2. BlueZ interface probe

Read-only from your **normal desktop terminal**:

```bash
python3 linux/ssc_bluez_probe.py
```

Optional temporary discovery experiment (candidate 0x0103, not verified on air):

```bash
python3 linux/ssc_bluez_probe.py --register --codec-id 0x0103 --flags 0x8a --lifetime-seconds 45
```

This registers an **A2DP source endpoint** over BlueZ D-Bus but **always rejects configuration and does not send audio**. It reports only anonymized adapter counts, vendor ID, codec ID and feature flags; it automatically unregisters on exit.

Do not run the registration command unless you are comfortable with it temporarily participating in Bluetooth codec selection. It may affect current audio negotiation while active. `0x8a` is a constructed candidate, **not** a recorded Buds4 Pro capability byte.

CatDesk's restricted workspace does not mount `/run/dbus/system_bus_socket`, so these live BlueZ actions cannot be verified there; run them from the host desktop terminal if desired. No system Bluetooth settings or drivers need modification.

## 3. Optional PipeWire capture import

```bash
python3 linux/ssc_pipewire_import.py --target YOUR_EXPLICIT_PIPEWIRE_OUTPUT_MONITOR --seconds 3 --bitrate 584000
```

This is a **two-stage** capture-to-WAV-and-encode diagnostic, not a live PipeWire Bluetooth sink. It records only an explicitly named PipeWire node and deletes the temporary capture by default. You must select the output monitor yourself; it deliberately never auto-selects a microphone or system output.

For a native PipeWire SSC profile in the future, we would need to implement its BlueZ5 codec interface (SPA plugin) and wire it into WirePlumber policy, or manage a standalone BlueZ transport independently. Merely adding `ssc` to `bluez5.codecs` will not work.

## 4. Remaining work

- Capture actual AVDTP capabilities and selected SSC vendor codec ID (candidate 0x0103 vs 0x0e03)
- Recover the SSC-specific media header/fragmentation and verify RTP clocking
- Confirm the accepted peer MTU in a real BlueZ `MediaTransport1.Acquire()`
- Move from loopback RTP to an explicit, isolated Bluetooth transport
- Later, replace Samsung's Android-hosted proprietary encoder with a local native implementation

See [the full higher-bitrate report](../docs/linux-bridge-high-bitrate-2026-11-03.md).
