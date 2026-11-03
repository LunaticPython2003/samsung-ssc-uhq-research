#!/usr/bin/env python3
"""Opt-in PipeWire capture -> WAV -> SSC -> *offline* RTP loopback experiment.

This is a staged import, NOT live audio playback. Requires the user's normal
desktop PipeWire session. To prevent accidentally recording a microphone,
an explicit --target PipeWire node name is always required.

Example (replace TARGET_MONITOR with a monitor you explicitly selected):
  python3 linux/ssc_pipewire_import.py --target TARGET_MONITOR --seconds 3

The captured WAV is removed automatically unless --keep-private-wav is set.
No Bluetooth endpoint is registered and no controller drivers are changed.
"""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

from ssc_linux_bridge import bridge_wav


def capture_pipewire(target: str, seconds: float, output: Path) -> tuple[int, int]:
    if not target.strip() or seconds < 1 or seconds > 15:
        raise ValueError("Explicit target and recording duration 1-15 seconds required")
    args = [
        "pw-record", "--target", target,
        "--rate", "96000", "--channels", "2", "--format", "s16",
        "--latency", "36ms", str(output)
    ]
    # Capture only a user-selected node; never auto-select a microphone.
    with subprocess.Popen(
        args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    ) as process:
        try:
            time.sleep(seconds)
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            try:
                _, stderr = process.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                process.terminate()
                _, stderr = process.communicate(timeout=3)
            if process.returncode not in (0, -signal.SIGINT):
                raise RuntimeError("PipeWire recorder failed: " +
                                   stderr.decode("utf-8", "replace")[-600:])
    with wave.open(str(output), "rb") as wav:
        hz, count = wav.getframerate(), wav.getnframes()
        if count == 0 or wav.getnchannels() != 2 or hz != 96000:
            raise RuntimeError("PipeWire recording had no valid 96 kHz stereo PCM")
    return hz, count


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", required=True, help="explicit PipeWire node name (e.g. an output monitor)")
    p.add_argument("--seconds", type=float, default=3.0)
    p.add_argument("--bitrate", type=int, choices=(584000, 886000), default=584000)
    p.add_argument("--mtu", type=int, default=1005)
    p.add_argument("--batch-frames", type=int, default=4)
    p.add_argument("--keep-private-wav", action="store_true")
    args = p.parse_args()
    workspace = Path(__file__).resolve().parents[1] / "tools"
    workspace.mkdir(exist_ok=True)
    # The tools folder is gitignored. The file is removed by default.
    with tempfile.NamedTemporaryFile(prefix="private_pipewire_", suffix=".wav",
                                     dir=workspace, delete=False) as temp:
        wav_path = Path(temp.name)
    try:
        hz, samples = capture_pipewire(args.target, args.seconds, wav_path)
        result = bridge_wav(
            wav_path, bitrate=args.bitrate, mtu=args.mtu,
            batch_frames=args.batch_frames,
        )
        print(json.dumps({
            "pipewire_sample_rate": hz,
            "pipewire_captured_samples": samples,
            "codec_bridge": result,
            "notice": "Offline verification only. NOT Bluetooth, NOT live audio monitoring.",
        }, indent=2))
    except Exception as exc:
        print(f"PipeWire import unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        if not args.keep_private_wav:
            wav_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
