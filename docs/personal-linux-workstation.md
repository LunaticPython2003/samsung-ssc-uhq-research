# Personal Linux research workstation

This document records the clean setup on a personal **Zorin OS 18.1 (Ubuntu-family, x86_64)** host. It keeps the original Windows SSC project reproducible without requiring Windows or a system-wide Java installation.

## Filesystem

Repository:

`~/Documents/ssc-research/samsung-ssc-uhq-research`

Local-only resources (ignored by Git):

| Location | Contents |
|---|---|
| `vendor-local/` | Extracted proprietary Samsung ARM64 ELF files, never redistributable |
| `tools/jdk25/` | Portable verified Temurin JDK 25.0.5 |
| `tools/ghidra_12.2_PUBLIC/` | Portable verified Ghidra 12.2 |
| `ghidra-projects-local/` | Private reverse-engineering projects |
| `tools/*.log`, `tools/ghidra-runs/` | Private local decompiler output |
| `third-party-a2dpwb/` | Separate A2DP Windows Bridge checkout; local discovery patch applied |

The official installation archives were checked against published GitHub asset SHA-256 digests before extraction:
- Ghidra 12.2 ZIP: `2c2cd776db3c1f6a097ba418922378ac3649cadd5e844a6f5f088ae628a7be67`
- Temurin 25.0.5+8 Linux x64: `68982529869257d0ee6b824ec5aa270ff8b118bb438670da0b97ebdab178d7fb`

No `sudo` privileges were needed. The local Git author matches the earlier repository commits, without changing global Git settings. Pushes should use the explicitly authenticated **LunaticPython2003** identity; do not use corporate Git credentials.

## Connected device

Galaxy Z Fold7 (SM-F966B) is visible through USB ADB. `adb shell su -c id` returned UID 0 in the temporary `ksu` context. The earlier device root exploit was DirtyFrag, documented in [instructions.md](../instructions.md). Root is not guaranteed to survive a reboot or firmware update.

The following local hashes were verified:
- `vendor-local/libScalable_Encoder.so`: `90c4c1cbd59b0edb9df6d255acc1f752e542e0cb99d3de8e842afc7ca9914ce7`
- `vendor-local/libbluetooth_jni.so`: `7158e06a58c8fba811b729d76c68c0c12295501d06895d0524f476fdf1caf0fe`

## Testing

From the repo root:

```bash
bash scripts/check-workstation.sh
python3 ssc_rate_frame_analysis.py
```

Offline tests: Python test suite and native Rust crate. A real encoder test can also be run using `python3 ssc_rpc.py` and a 16-/24-bit stereo WAV, provided temporary root and Termux Clang remain available.

To inspect the proprietary binaries **locally**:

```bash
bash scripts/ghidra-local.sh encoder TraceSscHeadroom.java
bash scripts/ghidra-local.sh bluetooth DumpSscBitrateTables.java
bash scripts/ghidra-local.sh bluetooth TraceSscControlXrefs.java
```

Use `--import` at the end if starting a completely empty Ghidra project. Results are intentionally written to ignored files under `tools/ghidra-runs/`; do not upload these decompiled vendor outputs.

## A2DP Windows Bridge

The independent third-party project was cloned under `third-party-a2dpwb/` with its BTstack submodule. The research patch is:

`patches/a2dpwb-ssc-passive-discovery.patch`

It now uses standard Unix LF lines and applies with:

```bash
git -C third-party-a2dpwb apply --check ../patches/a2dpwb-ssc-passive-discovery.patch
git -C third-party-a2dpwb apply ../patches/a2dpwb-ssc-passive-discovery.patch
```

On this machine the patch is already applied. A2DP Windows Bridge's BTstack implementation builds Windows-specific `Windows.h` sources, so **native Linux cargo build/tests of its full workspace fail**, irrespective of the SSC codec patch. Use the Windows host or a proper Windows cross-compile environment to validate the full transmitter. The portable SSC Rust client itself works on Linux.

## Remaining important limits

- No authenticated over-the-air SSC frame has been decoded or transmitted by this project.
- No verified Buds negotiated AVDTP vendor codec ID, RTP media header or fragmentation policy.
- The remote phone-hosted encoder is not an independent Linux/Windows SSC implementation.
- This setup deliberately does **not** change the personal PC's Intel Bluetooth driver, pairing state, phone firmware or Bluetooth Developer Options.
