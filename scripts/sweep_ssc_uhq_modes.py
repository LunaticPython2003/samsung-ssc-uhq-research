#!/usr/bin/env python3
"""Read-only synthetic PCM Samsung SSC rate sweep with a temporarily rooted Fold7.

Tests 96k stereo, 864 samples per channel, encoder mode enums 24/32/34,
and the E-family rates. Runs independent native encoder process per case.
No Bluetooth interaction. Temporary executables and outputs stay on phone,
and sanitized measurements in gitignored tools/.

Usage: python3 scripts/sweep_ssc_uhq_modes.py
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODES=(24,32,34)
RATES=(152000,250000,291000,308000,442000,584000,886000)
EXPECTED_MARKERS={152000:0x06,250000:0x05,291000:0x00,308000:0x01,
                  442000:0x02,584000:0x03,886000:0x04}
REMOTE="/data/local/tmp/ssc_uhq_mode_sweep"
FRAME_RE=re.compile(r"^frame=(\d+) result_register=(\d+) changed=(\d+) last_modified_exclusive=(\d+) canary=(\w+) prefix=([0-9a-fA-F]+)$")

def run(args: list[str],timeout=25) -> str:
    res=subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    if res.returncode:
        raise RuntimeError(f"subprocess failed rc={res.returncode}: {args[:3]}\n{res.stderr[-1200:]}")
    return res.stdout+res.stderr

def prepare() -> None:
    source=(ROOT/"ssc_arm64_probe.c").read_text()
    old="(depth!=16 && depth!=24)"
    if source.count(old)!=1:raise RuntimeError("Expected original C argument guard changed")
    new=source.replace(old,"(depth!=16 && depth!=24 && depth!=32 && depth!=34)")
    local=ROOT/"tools/ssc_uhq_mode_sweep.c"
    local.parent.mkdir(exist_ok=True)
    local.write_text(new)
    run(["adb","push",str(local),REMOTE+".c"])
    run(["adb","shell","su","-c",f"/data/data/com.termux/files/usr/bin/clang -O2 -Wall -Wextra {REMOTE}.c -o {REMOTE} -ldl -lm"],timeout=30)

def parse(output: str,rate:int,mode:int,expected_frames:int) -> dict:
    matches=[FRAME_RE.fullmatch(l.strip()) for l in output.splitlines()]
    frames=[m for m in matches if m]
    if len(frames)!=expected_frames:
        raise RuntimeError(f"missing frames at {rate=} {mode=}: {len(frames)} / {expected_frames}\n{output[-1300:]}")
    data=[]
    for m in frames:
        index,length,changed,extent,canary,prefix=m.groups()
        raw=bytes.fromhex(prefix)
        if len(raw)<4:raise RuntimeError("Missing frame header bytes")
        marker=raw[3]&0x1f
        data.append({"index":int(index),"returned_bytes":int(length),
                     "changed_bytes":int(changed),"last_modified_exclusive":int(extent),
                     "canary":canary,"frame_marker":marker,"header4":raw[:4].hex()})
    first=data[0]
    ok=(all(f["canary"]=="OK" and f["returned_bytes"]==f["last_modified_exclusive"]
          and f["frame_marker"]==EXPECTED_MARKERS[rate] for f in data))
    return {
      "mode":mode,"rate_bps":rate,"sample_rate_hz":96000,"frame_samples":864,
      "frames_tested":len(data),"returned_bytes":first["returned_bytes"],
      "last_modified_exclusive":first["last_modified_exclusive"],
      "frame3_low5":f"0x{first['frame_marker']:02x}",
      "expected_marker":f"0x{EXPECTED_MARKERS[rate]:02x}",
      "raw_frame3":f"0x{int(first['header4'][6:8],16):02x}",
      "all_frames_lengths_match_return_and_marker":ok,
      "all_canaries_ok":all(f["canary"]=="OK" for f in data),
      "all_frames":data,
    }

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames",type=int,default=8,choices=range(1,33))
    args=p.parse_args()
    run(["adb","shell","su","-c","id"],timeout=6)
    prepare()
    rows=[]
    for mode in MODES:
        for rate in RATES:
            outfile=f"/data/local/tmp/ssc_uhq_{rate}_{mode}.raw"
            cmd=f"{REMOTE} encode 96000 2 {mode} {rate} 864 {args.frames} {outfile}"
            output=run(["adb","shell","su","-c",cmd])
            row=parse(output,rate,mode,args.frames)
            digest=run(["adb","shell","su","-c",f"sha256sum {outfile}"]).split()[0]
            row["synthetic_output_sha256"]=digest
            rows.append(row)
            print(f"mode={mode:2d} bps={rate:6d} size={row['returned_bytes']:4d} "
                  f"frame3&0x1f={row['frame3_low5']} match={row['all_frames_lengths_match_return_and_marker']} "
                  f"sha256={digest[:12]}",flush=True)
    for rate in RATES:
        modes=[r for r in rows if r["rate_bps"]==rate]
        same=len({r["synthetic_output_sha256"] for r in modes})==1
        print(f"COMPARE {rate}: mode24/32/34 full-frame equality: {same}")
    out=ROOT/"tools/ssc_uhq_mode_sweep.json"
    out.write_text(json.dumps(rows,indent=2)+"\n")
    print("Results stored locally at",out)
if __name__=="__main__":
    main()
