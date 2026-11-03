#!/usr/bin/env python3
"""Inspect the deliberately nonstandard SSCF research container.

Usage: python ssc_inspect.py ssc_test_tone.sscf
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import statistics
import struct
from pathlib import Path

MAGIC=b"SSCF"
HEADER="<4s8I"
FRAME_HEADER="<2I"

def inspect(path: Path) -> dict:
    data=path.read_bytes()
    header_size=struct.calcsize(HEADER)
    if len(data)<header_size:
        raise ValueError("too short for SSCF header")
    (magic, version, rate, channels, depth, bitrate, samples,
     count, valid_total)=struct.unpack_from(HEADER,data)
    if magic!=MAGIC or version!=1:
        raise ValueError("not an SSCF v1 research file")
    if count>500000:
        raise ValueError("unreasonable frame count")
    offset=header_size
    lengths=[]
    valid_samples=[]
    prefixes=[]
    for index in range(count):
        if offset+8>len(data):
            raise ValueError(f"truncated frame header {index}")
        length,valid=struct.unpack_from(FRAME_HEADER,data,offset)
        offset+=8
        if length<4 or length>16384 or valid>samples:
            raise ValueError(f"invalid frame header {index}")
        if offset+length>len(data):
            raise ValueError(f"truncated frame {index}")
        frame=data[offset:offset+length]
        lengths.append(length)
        valid_samples.append(valid)
        if len(prefixes)<5:
            prefixes.append(frame[:8].hex())
        offset+=length
    if offset!=len(data):
        raise ValueError(f"{len(data)-offset} unparsed trailing bytes")
    if sum(valid_samples)!=valid_total:
        raise ValueError("PCM sample count inconsistent with header")
    return {
        "path":str(path),
        "sha256":hashlib.sha256(data).hexdigest(),
        "rate_hz":rate,"channels":channels,"bit_depth":depth,
        "selected_bitrate_bps":bitrate,"samples_per_frame":samples,
        "frame_count":count,"pcm_samples_per_channel":valid_total,
        "duration_s": round(valid_total / rate,6),
        "encoded_bytes":sum(lengths),
        "frame_bytes_min":min(lengths) if lengths else 0,
        "frame_bytes_max":max(lengths) if lengths else 0,
        "frame_bytes_mean":round(statistics.mean(lengths),2) if lengths else 0,
        "frame_size_distribution":dict(collections.Counter(lengths).most_common(10)),
        "frame_prefix_hex":prefixes,
        "nonstandard_container":True
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path",type=Path)
    args=ap.parse_args()
    import json
    print(json.dumps(inspect(args.path),indent=2))

if __name__=="__main__":
    main()
