#!/usr/bin/env python3
"""Offline, read-only verifier for the Samsung Galaxy Buds4 Pro R640 decoder.

The supplied firmware is Samsung's proprietary binary and is NOT redistributed.
Input default is the locally downloaded, gitignored R640XXU0AZD2 image.

This script verifies fixed instruction signatures and decodes the Thumb TBB
jump table using byte offsets recovered from cross-references to Samsung's
SSC decoder log strings. These offsets are valid for the exact firmware
hash below; refuse to infer results for other firmware versions.

It does not flash firmware, open Bluetooth connections, send audio, or
produce executable code for the earbuds.

Usage:
  python3 scripts/audit-r640-receiver.py
  python3 scripts/audit-r640-receiver.py /path/to/R640XXU0AZD2.bin
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SHA256 = "b91289cd445449485087aa380559eea167e5c0009ecdb912139d11212e02749f"
SIZE = 8_968_784
VALIDATOR = 0x8D968
TBB_INSTR = 0x8D992
TBB_TABLE = 0x8D996
DEFAULT_LENGTH_BLOCK = 0x8D9BC
PREPARSE_UHQ = 0x8AFD4

# The receiver's threshold table is a minimum-length test, not an exact
# length equality. For unknown identifiers it uses default 0x1e4=484.
CASE_MINIMUM = {
    0x00: 330,  # UHQ e0 (291kbps)
    0x03: 660,  # UHQ e3 (584kbps)
    0x06: 174,  # UHQ e6 (152kbps)
    0x10: 224,  # f0
    0x11: 244,  # f1
    0x12: 324,  # f2
    0x14: 576,  # f4
    0x15: 372,  # f5
    0x16: 292,  # f6
}
UHQ_PROCESSED_LOW5 = (0x00, 0x03, 0x06)


def inspect(data: bytes) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != SIZE or digest != SHA256:
        raise ValueError(
            "Unknown/modified firmware. This audit is valid ONLY for exact "
            "SM-R640 R640XXU0AZD2 SHA-256 " + SHA256
        )
    if data[:4] != bytes.fromhex("fe ca fe ca"):
        raise ValueError("Missing expected Bestechnic firmware header")
    # The Buds4 Pro A2DP vendor-specific codec configuration path directly
    # compares vendor=0x75 and codec=0x0103 (Thumb CMP/MOVW/CMP sequence).
    if data[0x17AC78:0x17AC84] != bytes.fromhex(
        "75 2e 03 d1 40 f2 03 13 98 45 01 d0"
    ):
        raise ValueError("Expected SSC vendor ID 0x75 / codec ID 0x0103 not found")
    # These exact Thumb-2 instructions validate our offsets before interpreting
    # the computed table: ldrb byte3, AND 0x1f, cmp index 0x16, TBB [pc,r3].
    if data[0x8D982:0x8D986] != bytes.fromhex("db 78 00 20"):
        raise ValueError("Unexpected SSC validator instructions (byte3 read)")
    if data[TBB_INSTR:TBB_INSTR + 4] != bytes.fromhex("df e8 03 f0"):
        raise ValueError("Expected Thumb table-branch instruction absent")
    if data[0x8D98E:0x8D992] != bytes.fromhex("16 2b 14 d8"):
        raise ValueError("Expected max-index and default-branch changed")
    # Path has explicit equality handling for index 0 and 3 then 6; all other
    # UHQ info indexes return without entering the frame handling block.
    # Require byte-exact instructions from the disassembly as a guard.
    if data[0x8AFE8:0x8AFF2] != bytes.fromhex("06 f0 f0 03 e0 2b 40 f0 a9 80"):
        raise ValueError("Expected UHQ frame header type guard changed")
    if data[0x8AFF8:0x8B014] != bytes.fromhex(
        "13 f0 1f 02 0a d0 a2 f1 03 00 b0 fa 80 f0 40 09 "
        "20 b9 06 2a 40 d0 03 b0 bd e8 f0 8f"
    ):
        raise ValueError("Expected UHQ E0/E3/E6 branch tests changed")

    # In Thumb TBB, PC is current instruction + 4, so each destination is
    # (TBB_TABLE + 2*unsigned_table_byte). No implicit 4-byte entries.
    table = data[TBB_TABLE:TBB_TABLE + 23]
    destination = {
        index: TBB_TABLE + 2*table[index] for index in range(len(table))
    }
    expected_destinations = {
        0x00: 0x8D9EE,
        0x03: 0x8D9F8,
        0x06: 0x8DA02,
        0x04: DEFAULT_LENGTH_BLOCK,
    }
    for code, expected in expected_destinations.items():
        if destination[code] != expected:
            raise ValueError(
                f"Unexpected firmware decoder branch for {code:#x}: "
                f"{destination[code]:#x} vs {expected:#x}"
            )
    # Unknown e-class IDs including E4 go through the generic 484-byte
    # minimum check in the preliminary validator. Then the UHQ pre-parser's
    # E0/E3/E6 equality branch skips further processing for E4.
    modes = []
    for code in range(7):
        modes.append({
            "info_byte": f"0x{0xE0+code:02x}",
            "minimum_accepted_bytes_in_initial_validator": CASE_MINIMUM.get(code, 484),
            "validator_dispatch_file_offset": f"0x{destination[code]:x}",
            "accepted_by_uhq_preparser": code in UHQ_PROCESSED_LOW5,
        })
    return {
        "device": "Samsung Galaxy Buds4 Pro (SM-R640)",
        "firmware": "R640XXU0AZD2",
        "firmware_sha256": digest,
        "firmware_config_vendor_id": "0x00000075",
        "firmware_config_codec_id": "0x0103",
        "metadata": {
            "validator_file_offset": f"0x{VALIDATOR:x}",
            "uhq_preparser_file_offset": f"0x{PREPARSE_UHQ:x}",
            "thumb_tbb_file_offset": f"0x{TBB_INSTR:x}",
            "read_only": True,
        },
        "modes": modes,
        "conclusion": (
            "E4/886kbps is not an explicitly processed UHQ frame type in "
            "this firmware. E0/E3/E6 are explicitly dispatched. No inference "
            "is made for newer earbud firmware."
        ),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path, nargs="?", default=(
        root / "vendor-local/buds-fw/R640XXU0AZD2.bin"
    ))
    args = parser.parse_args()
    print(json.dumps(inspect(args.firmware.read_bytes()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
