#!/usr/bin/env python3
"""Extract an anonymized SSC UHQ run profile from Android logcat.

Only saves encoder parameters/flags, timestamps, and relevant bitrate events.
Does NOT save private Bluetooth addresses, other app logs, or music metadata.

Usage:
    python ssc_live_report.py --adb -o ssc_live_profile.json
    python ssc_live_report.py --log logfile.txt -o ssc_live_profile.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

HAL = re.compile(
    r"SehCodecConfiguration\{codecType: SSC, encodedAudioBitrate: (\d+), "
    r"peerMtu: (\d+), isScmstEnabled: (\w+), config: CodecSpecific"
    r"\{sscConfig: SehSscConfiguration\{sampleRateHz: (\d+), "
    r"channelMode: ([A-Z_]+), bitsPerSample: (\d+)\}\}"
)
FRAME = re.compile(
    r"a2dp_ssc_encode_frames: nb_frame (\d+) sample (\d+) level (\d+) "
    r"limit (\w+) monitor (\w+) scmst (\w+)"
)
RATE = re.compile(r"new bitrate (\d+), previous bitrate (\d+)")
UPDATE = re.compile(
    r"a2dp_vendor_ssc_encoder_update: sample_rate=(\d+) "
    r"bits_per_sample=(\d+) channel_count=(\d+), "
    r"bitrate_limitation=(\w+), is_uhq2=(\w+)"
)
STATE = re.compile(r"A2DP_VendorGetTrackSampleRateSsc: (0x[0-9a-fA-F]+), uhq ver2 : (0x[0-9a-fA-F]+)")
TS = re.compile(r"^(\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})")


def summarize(text: str) -> dict:
    config = []
    frames = []
    transitions = []
    updates = []
    states = []
    offload = False
    for line in text.splitlines():
        if "SSC" not in line and "ssc" not in line:
            continue
        time = TS.match(line)
        ts = time.group(1) if time else None
        if match := HAL.search(line):
            bitrate, mtu, scmst, sample, channel, depth = match.groups()
            record = {
                "timestamp": ts, "codec": "SSC",
                "bitrate_bps": int(bitrate),
                "peer_mtu_bytes": int(mtu),
                "scmst": scmst == "true",
                "sample_rate_hz": int(sample),
                "channel_mode": channel,
                "bit_depth_field": int(depth),
            }
            if record not in config:
                config.append(record)
        if match := FRAME.search(line):
            n, sample, level, limit, monitor, scmst = match.groups()
            frames.append({
                "timestamp": ts,
                "frames_reported": int(n),
                "rate_hz": int(sample),
                "level": int(level),
                "limited": limit == "true",
                "monitor": monitor == "true",
                "scmst": scmst == "true",
            })
        if match := RATE.search(line):
            bitrate, previous = match.groups()
            transitions.append({
                "timestamp": ts,
                "from_bps": int(previous), "to_bps": int(bitrate)
            })
        if match := UPDATE.search(line):
            rate, bits, channels, limited, uhq = match.groups()
            updates.append({
                "timestamp": ts,
                "rate_hz": int(rate), "bit_depth_field": int(bits),
                "channels": int(channels),
                "bitrate_limited": limited == "true",
                "is_uhq2": uhq == "true",
            })
        if match := STATE.search(line):
            flags, version = match.groups()
            states.append({"timestamp": ts, "reported_flags": flags, "uhq_version": version})
        if "IsCodecOffloadingEnabled: enabled SSC" in line:
            offload = True

    latest = config[-1] if config else None
    return {
        "schema_version": 1,
        "source": "local Android logcat, anonymized; only SSC-related fields",
        "selected_configuration": latest,
        "configuration_events": config[-8:],
        "offload_reported_enabled": offload,
        "encoder_updates": updates[-8:],
        "uhq_mode_reports": states[-8:],
        "bitrate_transitions": transitions[-32:],
        "frame_event_count": len(frames),
        "frame_events": frames[-30:],
        "packet_framing_verified": False,
        "negotiated_vendor_codec_id_verified": False,
        "warnings": [
            "Selected HAL codec and encoder logs establish live SSC operation.",
            "Audio source resolution does not establish Bluetooth output rate.",
            "SSC frame boundaries, media header and AVDTP vendor codec ID need HCI packet capture.",
            "The peer MTU may be reported by HAL at the payload boundary; confirm transport header accounting from a live trace.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    inputs = ap.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--adb", action="store_true")
    inputs.add_argument("--log", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("ssc_live_profile.json"))
    args = ap.parse_args()
    if args.adb:
        run = subprocess.run(
            ["adb", "shell", "logcat", "-d", "-v", "threadtime"],
            capture_output=True, text=True, errors="replace", check=True
        )
        raw = run.stdout
    else:
        raw = args.log.read_text(encoding="utf-8-sig", errors="replace")
    report = summarize(raw)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "active_codec": report["selected_configuration"],
        "frame_event_count": report["frame_event_count"],
        "bitrate_transitions": report["bitrate_transitions"][-8:],
        "offload_reported_enabled": report["offload_reported_enabled"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
