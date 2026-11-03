#!/usr/bin/env python3
"""Read-only, offline Bluetooth btsnoop SSC negotiation inspector.

Parses classic Android .log/.cfa btsnoop files (HCI H4 ACL) for AVDTP
media-codec service capabilities. Finds Samsung VID 0x00000075 and records
the exact two-byte codec ID and final vendor codec capability bytes.

This tool does not enable HCI logging, pair devices, modify Bluetooth
settings, or transmit over Bluetooth.

Usage:
    python ssc_snoop.py bluetooth_hci.log
    python ssc_snoop.py bluetooth_hci.log --json result.json

Caution: btsnoop files may contain private device addresses or traffic.
Do not publish full captures. This script only reports codec negotiation.
"""
from __future__ import annotations
import argparse
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path

BTSNOOP_MAGIC = b"btsnoop\x00"
BTSNOOP_HEADER_BYTES = 16
RECORD_HEADER_BYTES = 24
VENDOR_SAMSUNG = 0x75
SIGNALS = {
    0x02: "GET_CAPABILITIES",
    0x03: "SET_CONFIGURATION",
    0x04: "GET_CONFIGURATION",
    0x05: "RECONFIGURE",
    0x0C: "GET_ALL_CAPABILITIES",
}
MESSAGE_TYPES = {
    0: "COMMAND",
    1: "GENERAL_REJECT",
    2: "ACCEPT",
    3: "REJECT",
}
MAX_RECORD_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Candidate:
    record: int
    handle: str
    cid: str
    direction: str
    signal: str
    message_type: str
    vendor_id: str
    codec_id: str
    sample_rate_flags: str
    feature_flags: str
    possible_sample_rates: tuple[int, ...]
    raw_cie_hex: str


def sample_rates(mask: int) -> tuple[int, ...]:
    rates = []
    for bit, rate in ((0x10, 48000), (0x20, 44100),
                      (0x40, 32000), (0x80, 96000)):
        if mask & bit:
            rates.append(rate)
    return tuple(rates)


def decode_avdtp(payload: bytes, record_number: int,
                 handle: int, cid: int, direction: str) -> list[Candidate]:
    if len(payload) < 4:
        return []
    transport_header, signal = payload[0], payload[1] & 0x3f
    # Full AVDTP signal packet. Fragmented AVDTP signals need reassembly
    # and are intentionally NOT identified as validated negotiation.
    if (transport_header >> 2) & 3 != 0 or signal not in SIGNALS:
        return []
    msg_type = transport_header & 3
    if msg_type not in (0, 2):
        return []
    start = 4 if msg_type == 0 and signal == 0x03 else \
            3 if msg_type == 0 and signal == 0x05 else 2
    candidates = []
    data = payload[start:]
    pos = 0
    while pos + 2 <= len(data):
        category = data[pos]
        losc = data[pos + 1]
        end = pos + 2 + losc
        if end > len(data):
            break
        if category == 7 and losc >= 9:
            element = data[pos + 2:end]
            if len(element) >= 9 and element[1] == 0xff:
                vendor = int.from_bytes(element[2:6], "little")
                codec = int.from_bytes(element[6:8], "little")
                if vendor == VENDOR_SAMSUNG:
                    flags = element[8]
                    candidates.append(Candidate(
                        record=record_number,
                        handle=f"0x{handle:04x}", cid=f"0x{cid:04x}",
                        direction=direction,
                        signal=SIGNALS[signal],
                        message_type=MESSAGE_TYPES[msg_type],
                        vendor_id=f"0x{vendor:08x}",
                        codec_id=f"0x{codec:04x}",
                        sample_rate_flags=f"0x{flags & 0xf0:02x}",
                        feature_flags=f"0x{flags & 0x0f:02x}",
                        possible_sample_rates=sample_rates(flags & 0xf0),
                        raw_cie_hex=(bytes([losc]) + element).hex(" ")
                    ))
        pos = end
    return candidates


def scan_btsnoop(path: Path) -> tuple[list[Candidate], int, int]:
    """Return Samsung codec discovery records and total/fragmented record counts."""
    result: list[Candidate] = []
    pending: dict[tuple[int, bool], tuple[int, int, bytearray]] = {}
    count = 0
    incomplete = 0
    with path.open("rb") as src:
        header = src.read(BTSNOOP_HEADER_BYTES)
        if len(header) != BTSNOOP_HEADER_BYTES or header[:8] != BTSNOOP_MAGIC:
            raise ValueError("not a btsnoop file")
        version, datalink = struct.unpack(">II", header[8:])
        if version != 1 or datalink not in (1001, 1002):
            raise ValueError(f"unsupported btsnoop version/datalink {version}/{datalink}")
        while True:
            record = src.read(RECORD_HEADER_BYTES)
            if not record:
                break
            if len(record) != RECORD_HEADER_BYTES:
                raise ValueError("truncated btsnoop record header")
            original, included, flags, _drops, _ts = struct.unpack(">IIIIQ", record)
            if included > MAX_RECORD_BYTES or included > original:
                raise ValueError("invalid packet lengths")
            packet = src.read(included)
            if len(packet) != included:
                raise ValueError("truncated btsnoop packet")
            count += 1
            # H4 0x02 indicates ACL data; events and commands are irrelevant.
            if len(packet) < 5 or packet[0] != 0x02:
                continue
            acl_header = int.from_bytes(packet[1:3], "little")
            handle = acl_header & 0x0fff
            pb = (acl_header >> 12) & 3
            acl_length = int.from_bytes(packet[3:5], "little")
            acl = packet[5:5 + acl_length]
            if len(acl) != acl_length:
                continue
            direction_out = not bool(flags & 1)
            direction = "outgoing" if direction_out else "incoming"
            key = (handle, direction_out)
            if pb == 1:
                if key not in pending:
                    incomplete += 1
                    continue
                cid, expected, buf = pending[key]
                buf.extend(acl)
                if len(buf) >= expected:
                    payload = bytes(buf[:expected])
                    result.extend(decode_avdtp(payload, count, handle, cid, direction))
                    pending.pop(key, None)
                continue
            if len(acl) < 4:
                continue
            l2cap_len = int.from_bytes(acl[:2], "little")
            cid = int.from_bytes(acl[2:4], "little")
            if cid < 0x0040 or l2cap_len < 4 or l2cap_len > 65535:
                continue
            # New L2CAP PDU: continuation keyed by handle and direction.
            data = bytearray(acl[4:])
            pending.pop(key, None)
            if len(data) >= l2cap_len:
                result.extend(decode_avdtp(bytes(data[:l2cap_len]),
                                           count, handle, cid, direction))
            else:
                pending[key] = (cid, l2cap_len, data)
    incomplete += len(pending)
    return result, count, incomplete


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snoop", type=Path)
    p.add_argument("--json", type=Path, default=None)
    args = p.parse_args()
    entries, total, fragmented = scan_btsnoop(args.snoop)
    summary = {
        "records_scanned": total,
        "unreassembled_fragments": fragmented,
        "samsung_ssc_candidates": [asdict(entry) for entry in entries],
        "note": (
            "Vendor 0x75 codec 0x0103 is accepted by the inspected SSC parser; "
            "0x0e03 appears in a separate initialization blob. "
            "Do not assume which ID the earbuds use until live evidence."
        )
    }
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Saved findings to {args.json}")
    else:
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
