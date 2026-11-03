#!/usr/bin/env python3
"""Analyze Samsung's in-memory BTSNOOP_LOG_SUMMARY without saving raw traffic.

Android's btsnooz ring buffer is Base64 + 9-byte header + zlib-compressed
records. This tool reads it from an ADB bluetooth_manager dump, reconstructs
HCI btsnoop in memory and searches AVDTP capabilities/SET_CONFIGURATION
messages for Samsung vendor codec IDs.

The output contains only protocol metadata, not device addresses, link keys,
application payloads, or raw Bluetooth service dumps. The in-memory buffer
may have overwritten the relevant negotiation or filtered ACL data.

Format reference:
https://android.googlesource.com/platform/packages/modules/Bluetooth/+/refs/heads/main/system/tools/scripts/btsnooz.py

Usage:
    python ssc_btsnooz.py --adb -o ssc_btsnooz_findings.json
    python ssc_btsnooz.py --dump previously_saved_dumpsys.txt
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import struct
import subprocess
import zlib
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from ssc_snoop import scan_btsnoop

PREFIX = "--- BEGIN:BTSNOOP_LOG_SUMMARY"
SUFFIX = "--- END:BTSNOOP_LOG_SUMMARY"
HEADER = b"btsnoop\x00" + struct.pack(">II", 1, 1002)
EPOCH_DELTA = 0x00DC_DDB3_0F2F_8000
SNOOZ_TYPES = {
    0x10: (4, 1), 0x11: (2, 1), 0x12: (3, 1), 0x17: (5, 1),
    0x20: (1, 0), 0x21: (2, 0), 0x22: (3, 0), 0x2D: (5, 0),
}
MAX_UNPACKED_BYTES = 32 * 1024 * 1024
MAX_PACKETS = 1_000_000


def extract_summary(service_dump: str) -> bytes:
    """Find exactly one complete BTSNOOP_LOG_SUMMARY section."""
    inside = False
    chunks: list[str] = []
    for line in service_dump.splitlines():
        if PREFIX in line:
            inside = True
            chunks = []
        elif inside and SUFFIX in line:
            if not chunks:
                raise ValueError("empty BTSNOOP summary")
            try:
                return base64.b64decode("".join(chunks), validate=True)
            except Exception as exc:
                raise ValueError("invalid BTSNOOP Base64 summary") from exc
        elif inside:
            chunks.append(line.strip())
    raise ValueError("BTSNOOP_LOG_SUMMARY not found or incomplete")


def decode_btsnooz(blob: bytes) -> tuple[bytes, dict]:
    """Convert Android btsnooz v1/v2 to btsnoop bytes in memory only."""
    if len(blob) < 12:
        raise ValueError("BTSNOOZ header too short")
    version, last_timestamp = struct.unpack_from("=bQ", blob, 0)
    if version not in (1, 2):
        raise ValueError(f"unsupported BTSNOOZ version {version}")

    inflater = zlib.decompressobj()
    raw = inflater.decompress(blob[9:], MAX_UNPACKED_BYTES + 1)
    if len(raw) > MAX_UNPACKED_BYTES or inflater.unconsumed_tail or not inflater.eof:
        raise ValueError("BTSNOOZ exceeds safe size or is truncated")
    raw += inflater.flush()
    if len(raw) > MAX_UNPACKED_BYTES:
        raise ValueError("BTSNOOZ payload too large")

    sizes: list[tuple[int, int, int, int, int]] = []
    offset = 0
    first_time = last_timestamp + EPOCH_DELTA
    header_size = 7 if version == 1 else 9
    while offset < len(raw):
        if len(raw) - offset < header_size:
            raise ValueError("truncated BTSNOOZ record header")
        if version == 1:
            included, dt_ms, typ = struct.unpack_from("=HIb", raw, offset)
            original = included
        else:
            included, original, dt_ms, typ = struct.unpack_from("=HHIb", raw, offset)
        if included == 0 or original < included or typ not in SNOOZ_TYPES:
            raise ValueError(f"invalid BTSNOOZ packet at {offset}")
        if offset + header_size + included - 1 > len(raw):
            raise ValueError("truncated BTSNOOZ record payload")
        sizes.append((offset + header_size, included, original, dt_ms, typ))
        offset += header_size + included - 1
        first_time -= dt_ms
        if len(sizes) > MAX_PACKETS:
            raise ValueError("too many BTSNOOZ records")

    out = io.BytesIO()
    out.write(HEADER)
    direction_counts = Counter()
    timestamp = first_time
    for data_at, included, original, dt_ms, typ in sizes:
        timestamp += dt_ms
        hci_type, direction = SNOOZ_TYPES[typ]
        direction_counts[f"{'in' if direction else 'out'}_hci_{hci_type}"] += 1
        out.write(struct.pack(">IIIIQ", original, included, direction, 0,
                              timestamp & 0xFFFFFFFFFFFFFFFF))
        out.write(bytes([hci_type]))
        out.write(raw[data_at:data_at + included - 1])
    return out.getvalue(), {
        "btsnooz_version": version,
        "ring_packets": len(sizes),
        "uncompressed_bytes": len(raw),
        "hci_packet_type_counts": dict(sorted(direction_counts.items())),
    }


def scan_service_dump(service_dump: str) -> dict:
    snooz = extract_summary(service_dump)
    btsnoop, metadata = decode_btsnooz(snooz)
    entries, total, missing = scan_btsnoop(btsnoop)
    return {
        "format": "in-memory Samsung btsnooz to HCI btsnoop to AVDTP",
        "source_bytes_base64_decoded": len(snooz),
        **metadata,
        "records_scanned": total,
        "unreassembled_acl_fragments": missing,
        "ssc_avdtp_candidates": [asdict(item) for item in entries],
        "limits": [
            "The ring buffer may not include the last device reconnection.",
            "Default Android snooz buffers may filter or truncate ACL packets.",
            "No AVDTP match does not mean a device lacks SSC.",
            "Codec identifier alone does not prove successful playback.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument("--adb", action="store_true")
    origin.add_argument("--dump", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="write sanitized codec metadata as JSON")
    args = parser.parse_args()
    if args.adb:
        proc = subprocess.run(
            ["adb", "shell", "dumpsys", "bluetooth_manager"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=True, timeout=45,
        )
        capture = proc.stdout.decode("utf-8", "replace")
    else:
        capture = args.dump.read_text(encoding="utf-8-sig", errors="replace")
    report = scan_service_dump(capture)
    rendered = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Sanitized SSC findings saved to {args.output}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
