# Samsung SSC / UHQ research

Reverse-engineering notes and experimental tools for Samsung Scalable Codec (SSC), with a particular focus on getting SSC UHQ audio out of a Windows Bluetooth source.

**Status: research prototype, not a Windows audio driver.** Samsung's original ARM64 encoder can be called from a rooted Galaxy phone, and the Windows Python and Rust clients can send it PCM and receive encoded frames. There is no independently ported x64 encoder, verified SSC A2DP packetizer, or confirmed Windows → Galaxy Buds playback yet.

## Findings so far

- Located the encoder API in Samsung's ARM64 `libScalable_Encoder.so` and the A2DP implementation in `libbluetooth_jni.so`. Exported entry points include `ssc_encoder_create`, `ssc_encoder_get_size`, `ssc_encode`, and `ssc_encoder_destroy`.
- Encoded synthetic stereo PCM at 44.1, 48 and 96 kHz on Android. A Windows Rust client and Python WAV converter communicate with a local Android encoder service over ADB forwarding.
- Captured an active Galaxy Buds4 Pro session using **SSC UHQ2, 96 kHz stereo, 24-bit (Android `8_24`), 584 kbps**, with a reported peer MTU of **1,005 bytes**. A startup transition from 291 → 584 kbps was also observed.
- Reproduced the observed rates through the original encoder at 96 kHz: **330-byte frames at 291 kbps** and **660-byte frames at 584 kbps**, for 864 PCM samples per channel.
- Recovered Samsung's candidate A2DP vendor identifier `0x00000075` and codec parser ID `0x0103`. A separate static initialization blob contains `0x0e03`. **The actual on-air codec ID and packet header remain unverified.**
- Added an offline btsnoop capability inspector, a sanitized live-log parser, and MTU preflight checks. The analyzed SSC A2DP implementation expects RTP, but the SSC-specific header and fragmentation behavior aren't proven.

## Repository layout

| Path | Purpose |
| --- | --- |
| `instructions.md` | How to identify and extract the original libraries from **your own** device; records the DirtyFrag root environment |
| `inspect_elf.py` | Inspect local AArch64 ELF dependencies, exported symbols and SSC-related strings |
| `ghidra-scripts/` | Ghidra headless scripts for function and Bluetooth-stack analysis |
| `ssc_arm64_probe.c` | One-off native Android encoder ABI and buffer checks |
| `ssc_rpc_server.c`, `ssc_rpc.py` | Android encoder service and Windows WAV-to-SSC test client |
| `ssc_inspect.py` | Inspect the custom `.sscf` research container (not an A2DP file) |
| `ssc-win-bridge/` | Native Windows Rust client, capability parsing, MTU preflight and examples |
| `ssc_snoop.py` | Offline HCI btsnoop AVDTP capability and configuration inspector |
| `ssc_live_report.py` | Extract an anonymized live SSC codec profile from logcat |
| `test_*.py` | Offline parser, protocol and log-extraction tests |
| `docs/` | Reverse-engineering notes and the verified 2026-11-03 playback session |

## Run the encoder bridge

Requirements: Windows with Python 3.10+ and Android Platform Tools (`adb`), plus a rooted Samsung device that actually contains `libScalable_Encoder.so`. For the current Android backend build, a Termux `clang` executable is expected at `/data/data/com.termux/files/usr/bin/clang`. Rust/Cargo is required for the Rust example. No Samsung library files are supplied here.

See [instructions.md](instructions.md) to identify the libraries and verify that the phone has `su` access.

Encode a **stereo uncompressed WAV** at 44.1, 48 or 96 kHz:

```powershell
adb devices -l
python ssc_rpc.py .\input.wav --depth 24 --bitrate 584000 -o .\output.sscf
python ssc_inspect.py .\output.sscf
```

The Python command compiles the server on the connected rooted Android device, forwards TCP port 23187 over ADB, and writes the proprietary encoder output in a **custom, length-prefixed research container**. It does not transmit Bluetooth audio. The `--bitrate` value selects an internal encoder mode; not every rate is guaranteed to be suitable for every sample rate or Bluetooth connection.

Rust client checks:

```powershell
cargo test --offline --manifest-path .\ssc-win-bridge\Cargo.toml
python -m unittest -v test_ssc_rpc.py test_ssc_snoop.py test_ssc_live_report.py
```

To exercise the Rust client against the real Android encoder, compile and run `ssc_rpc_server.c` on the phone, forward `tcp:23187`, then run the `tone` or `live_tone` examples. The exact device setup is documented in [instructions.md](instructions.md). `live_tone` reproduces the observed 96 kHz / 584 kbps mode but deliberately sends no radio packets.

For live-device diagnostics:

```powershell
python ssc_live_report.py --adb -o .\ssc_live_profile.json
```

The output contains only selected codec-related fields. Raw HCI snoop/bugreports may contain device addresses and unrelated data and should not be published.

## Recent progress: bitrate tables and Windows discovery

The [new research report](docs/research-update-2026-11-03.md) documents recovered UHQ2 mode flags, Samsung's four-level bitrate tables, and observed encoder-frame counter patterns. The [btsnooz inspector](ssc_btsnooz.py) can decode the Android Bluetooth service ring in memory, without retaining raw private traffic. The analyzed ring had zero ACL packets, so the negotiated AVDTP codec configuration is still unknown.

The [A2DP Windows Bridge patch](patches/a2dpwb-ssc-passive-discovery.patch) recognizes Samsung endpoints during discovery, but does not enable radio transmission or modify Bluetooth drivers. The patched codec suite passed 28 tests, and the codec and Bluetooth host compiled.

Run all available local tests:

    python -m unittest -v test_ssc_rpc.py test_ssc_snoop.py test_ssc_btsnooz.py test_ssc_live_report.py
    cargo test --manifest-path ssc-win-bridge/Cargo.toml

## Personal Linux workstation and four-investigation follow-up

The project was rebuilt and tested on a personal Zorin OS 18.1 workstation. See [workstation setup](docs/personal-linux-workstation.md) for the portable Ghidra/JDK installation, Samsung library hashes, Android ADB access, and limitations of the Windows-only BTstack transmitter. Run `bash scripts/check-workstation.sh` for local verification.

The [four targeted investigations](docs/four-investigations-2026-11-03.md) trace bitrate-table consumers, internal mode flags, frame-size arithmetic, and frequency-band allocation. Supporting tools include `ssc_rate_frame_analysis.py`, `TraceSscControlXrefs.java`, and `TraceSscHeadroom.java`. The Ghidra scripts generate **private local** results; decompiled Samsung code is not redistributed.

## Linux bridge and the 886 kbps mode

The [Linux SSC bridge prototype](linux/README.md) now drives the actual Samsung encoder through ADB, checks the returned SSC frame marker, builds an **incomplete/experimental** RTP packet and validates it across a local Linux packet-preserving socket. It does not transmit over Bluetooth.

[High-bitrate investigation](docs/linux-bridge-high-bitrate-2026-11-03.md) confirmed that **886 kbps** is recognized by the original encoder and has a distinct UHQ frame marker, but its 1000-byte frame requires at least 1012 bytes with a fixed RTP header. The previous Buds4 Pro HAL reported an MTU of 1005 bytes, so sending 886 kbps would require a larger negotiated transport MTU or a verified fragmentation scheme. Samsung's analyzed normal UHQ2 bitrate table still peaks at **584 kbps**. Requests for 1.2–2.4 Mbps returned inconsistent output sizes and are not validated modes.

BlueZ offers an endpoint/transport interface for future use, and a [read-only probe](linux/ssc_bluez_probe.py) plus optional passive endpoint are supplied. CatDesk's restricted workspace cannot access the desktop's BlueZ system bus, so **no actual earbuds stream has been attempted**. PipeWire integration also remains incomplete.

Run the new offline tests with `python3 -m unittest -q test_ssc_linux_bridge.py`.

## Peak bitrate audit (verified on the Fold7)

The [peak-bitrate audit](docs/ssc-peak-bitrate-audit-2026-11-03.md) compares Samsung's public 2,304-kbps claim reported by third-party publications with directly analyzed device binaries. The inspected software encoder has **13 explicitly named header modes, with 886kbps highest**; higher requests return its generic `0xF3` code. Separately, Samsung's AIDL Bluetooth offload library contains an SSC-specific validator and capabilities object, but no confirmed multi-megabit encoded-transmission rate. The distinction between format, encoder output, and *over-the-air Bluetooth bitrate* remains essential.

The audit is reproducible using the source-only probe `ssc_bitrate_catalog.c` and `bash scripts/check-bitrate-catalog.sh`. Only private local output is saved under `tools/`, and the Samsung binaries are excluded from Git.

## Verified Buds4 Pro receiver parser and cross-project audit

The [final research handoff](docs/ssc-cross-project-r640-verification-and-build-handoff-2026-11-03.md) compares SSCOnWindows, openssc, SSC-Pipewire, ssc-uhq, and other projects against **the actual SM-R640 Galaxy Buds4 Pro firmware**. The April 2026 receiver image `R640XXU0AZD2` has E6/152 kbps, E0/291 kbps and E3/584 kbps branches in its UHQ sequence pre-parser, but the [November 4 instruction-level re-audit](docs/r640-e4-reaudit-2026-11-04.md) corrected our earlier overstatement about E4/886 kbps: an initial validator admits sufficiently long E4 frames and the pre-parser's caller ignores its return status. A separate SSC packet queue caps copied data at 800 bytes, short of an E4 frame's 1000 bytes. Whether a downstream DSP or alternative fragmented path decodes E4 is **not established**.

Reproduce the read-only analysis against your own locally downloaded firmware with `python3 scripts/audit-r640-receiver.py`. The original firmware is proprietary and gitignored; only the verification script, tests, branch mapping and analysis are published. No firmware changes or device flashing are required. Later R640 firmware could differ.

**Implementation target:** Start at 584 kbps/96 kHz using a standalone BlueZ A2DP source and Samsung's working phone-hosted encoder. Only after proving audio playback should we add PipeWire/WirePlumber integration. Your installed PipeWire 1.0.5 and WirePlumber 0.4.17 are older than the private-plugin ABI used by the reviewed PipeWire 1.6.x SSC projects.

## HiFi mode flags and Classic Bluetooth throughput

A [direct Fold7 encoder comparison](docs/ssc-hifi-flags-and-throughput-2026-11-04.md) confirms that Samsung encoder creation-mode values **24, 32 and 34** produce **identical eight-frame binary output** for the tested synthetic PCM and requested rates, including E3/584kbps and E4/886kbps at 96kHz. This does **not** prove that the modes are always identical, and it does **not** establish earbuds decoding of E4. The official Bluetooth Core maximum asymmetric 3-DH5 user throughput is **2178.1kbps**, so a continuous **2304kbps** compressed stream exceeds the limit of Classic BR/EDR A2DP; **886kbps itself is physically feasible**, pending the negotiated MTU, receiver queue and decode path.

## What's left

1. Obtain an actual HCI AVDTP exchange to settle the vendor codec ID and peer configuration.
2. Recover the SSC-specific RTP payload header and prove frame aggregation or fragmentation behavior.
3. Integrate a verified packetizer with a Windows Bluetooth A2DP host implementation, then test on the Buds.
4. Replace the phone-hosted encoder with a lawful independent x64 implementation or another suitable local execution strategy.

The phone-assisted prototype is not yet suitable for live listening, and no workaround here enables SSC in the stock Windows A2DP driver.

## Legal / attribution

Samsung SSC and the extracted firmware libraries are proprietary; this repository does **not** redistribute them. The original third-party project [A2DP Windows Bridge](https://github.com/SeiyaFunaokaJP/A2DP-Windows-Bridge) is investigated as a possible host stack, but its code is not vendored here.

The repository's existing GPL-3.0 license applies to this project's own source. It does not change the license of any Samsung or third-party binary. Reproducibility and accurate reporting are the priorities; decompiled vendor source is not included.
