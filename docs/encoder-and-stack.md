# Samsung SSC / UHQ to Windows — research checkpoint (2026-11-03)

## Verified environment
- Phone: SM-F966B, Android 17, ADB connected, root via `su` (u:r:ksu:s0).
- Windows workspace has four ARM64 ELF libraries, Ghidra 12.2, and prior ADB scripts.
- SHA256 of `libScalable_Encoder.so`: `90C4C1CBD59B0EDB9DF6D255ACC1F752E542E0CB99D3DE8E842AFC7CA9914CE7`.
- ADB access was used for read-only inspection. No phone settings, partitions, or codec preferences were altered.
- A previous Ghidra attempt failed in its launcher. A corrected absolute-path invocation imported and analyzed the encoder. The original Java decompilation script was missing the `ghidra.app.script.GhidraScript` import; fixed. Successful decompilation was written to `ghidra-decompiled.log`.

## Component responsibility and feasibility
| Component | Evidence | Role |
|---|---|---|
| `libScalable_Encoder.so` | ARM64 ELF, functions `ssc_encoder_create`, `ssc_encoder_init`, `ssc_encode`, `ssc_encoder_destroy` | Actual software SSC encoding (primary RE target) |
| `libsehbluetooth_audio_session_aidl.so` | Vendor AIDL, `SehSscConfiguration`, `IsOffloadSscConfigurationValid` | Samsung Android audio session/config interface |
| `vendor.samsung.hardware.bluetooth.audio-impl.so` | AIDL audio provider and codec capability references | Android Bluetooth audio provider, not a Windows driver |
| `libssc_default_listener.so` | `libsdsprpc.so`, `adsp_default_listener` | Qualcomm DSP listener; not the SSC PC software encoder |

An ARM64 Android .so cannot be directly loaded in an x64 Windows process. SSC support on Windows requires both a functioning native encoder and control of vendor-specific A2DP codec discovery/configuration, frame packing and Bluetooth transport. A virtual audio cable alone does not provide the latter.

## Decompilation: high-value facts
- `ssc_custom_mode_create(sample_rate, 0x360, ...)` accepts 44100, 48000, and 96000 Hz in the inspected binary; unrecognized sample rates return null. The constant `0x360` is 864 in decimal. The function name does not by itself establish units for this constant.
- `ssc_encoder_create(sample_rate, channels, arg3, error_out)` allocates a context, delegates to `ssc_encoder_init`, reports status via `error_out`, and frees the context on initialization failure.
- `ssc_encoder_init(context, sample_rate, channels, arg4)` accepts channel counts below 3; the code should be manually audited before invoking it with 0 channels. It initializes global DRC state, which may be non-reentrant.
- `ssc_encoder_get_size(channels, sample_rate)` computes the required context size based on the mode's internal tables; don't hardcode this.
- `ssc_encode(context, int32_input_pointer, arg3, int16_output_pointer, arg5)` is the decompiler's inferred parameter layout. **This is not yet a validated public ABI**: the actual input sample representation, output length/return semantics and frame size require a controlled device-side test. The decompiler represents the function return as void even though an internal encoded byte count is computed, so do not assume how the caller consumes length.
- `get_uhq_info_from_bitrate(bitrate, flag_ptr_a, flag_ptr_b)` has exact bitrate comparisons against 88000, 96000, 128000, 152000, 192000, 229000, 250000, 256000, 291000, 308000, 328000, 442000, 584000 and 886000. These are **internal bitrate selector branches**, not proof of live RF throughput or official operating modes. Several branches only write one output pointer; reverse engineer the caller before labeling the flags as specific modes.
- Exported DSP primitives include MDCT, range/entropy encode, pitch search, energy quantization, DRC, stereo shaping, and filter routines. This suggests a self-contained codec core rather than a thin interface to a phone-only DSP.

## Live device evidence
- Bluetooth history contains both `SSC HIFI` and `SSC UHQ2` labels for Buds4 Pro.
- Audio history from the same period also contains a `LE_AUDIO` route with `AUDIO_FORMAT_LC3`; the `A2DP` device initially reports `AUDIO_FORMAT_SBC`. Thus the HIFI/UHQ2 connection label does not establish which codec was streaming PCM.
- **Update 2026-11-03 live playback:** SSC encoding is positively confirmed, with UHQ2 true, 96 kHz stereo 8_24, selected bitrate 584000, peer MTU 1005 and SCMS-T false. Observed a 291000 -> 584000 bitrate transition during startup. Exact software encoder tests yielded 330- and 660-byte frames respectively, with an intact buffer canary. All details are in SSC_LIVE_PLAYBACK_2026-11-03.md and ssc_live_profile.json.
- Do not alter pairing or developer codec settings merely to force a trace without user agreement.

## Next execution gates
1. Trace Samsung's platform Bluetooth A2DP vendor codec implementation from system/APEX/framework libraries, not only the audio AIDL wrappers.
2. Recover the PCM format, context API, encoded output length, and frame header through a reproducible ARM64 test harness and input/output vectors.
3. Capture a consenting local device A2DP negotiation/packet trace and identify vendor codec ID, capabilities and media header rules. Compare the resulting binary configuration against the library's mode flags.
4. Prototype a native Windows codec via a clean x64 port or carefully isolated ARM64 emulation for **offline encoding first**. The proprietary binary may have redistribution/licensing restrictions.
5. Pick a Bluetooth transport strategy: an authorized/replaceable A2DP host stack or a dedicated external Bluetooth source implementation. Windows' stock Bluetooth A2DP path is not made SSC-aware by dropping in a DLL.
6. Validate audio using the actual Buds: sample rate, frame integrity, dynamic bitrate, latency, reconnection and fallbacks; only then consider a system-level route.

## Reproducibility and files
- `inspect_elf.py`: local ELF imports, exports, and strings.
- `current_state.py`, `live_diagnostics.py`, `route_check.py`, `ssc_stream_summary.py`: ADB diagnostics (preexisting).
- `ghidra-scripts/DecompileExports.java`: corrected Ghidra script.
- `ghidra-encoder-results.log`: initial successful import/analysis with prior Java-script compilation failure.
- `ghidra-decompiled.log`: successful export decompilation, including SSC core and UHQ bitrate decision logic.
- `ghidra-projects-abs/SSCEncoder.gpr`: editable Ghidra project.

## Status
**Research, Ghidra reverse engineering, software encoder ABI, Windows-to-phone Python/Rust bridge, real SSC UHQ2 live diagnostics and MTU preflight completed.** Windows Bluetooth transmission is not implemented. The unresolved blockers are live AVDTP vendor codec configuration/media packet capture, transport integration, and an independent x64 encoder. See SSC_LIVE_PLAYBACK_2026-11-03.md.
