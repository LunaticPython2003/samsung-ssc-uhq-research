#!/usr/bin/env python3
"""Summarize a *live native Android* Samsung SSC session via personal PC ADB.

Read-only: does not change log verbosity, codec settings, pairing, services,
firmware, audio, Bluetooth radios, or playback. Raw logcat and dumpsys remain
IN MEMORY and are not saved. Output is sanitized protocol metadata without
Bluetooth addresses, app names, titles, or audio payload.

Example:
 python3 scripts/report_native_ssc_playback.py --start '11-04 18:43:41' --output tools/native_ssc_session.json
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

RX_BITRATE=re.compile(r"bitrate_idx\s+(\d+)\s+bit_rate\s+(\d+)")
RX_TRANSITION=re.compile(r"new bitrate\s+(\d+),\s+previous bitrate\s+(\d+)")
RX_FRAME=re.compile(r"nb_frame\s+(\d+)\s+sample\s+(\d+)\s+level\s+(\d+)")
RX_CIE=re.compile(r"codec info\[([0-9a-fA-F]{8})\]\s+codecid\[([0-9a-fA-F]{4})\]")
RX_MTU=re.compile(r"peerMtu[:=]\s*(\d+)",re.I)
RX_CODEC=re.compile(r"mCodecConfig:\s*\{codecName:(SSC|AAC|SBC|LDAC|aptX)[,}]([^}]*)}")
RX_AUDIO_SOURCE=re.compile(r"format update:FormatInfo\{[^}]*sampleRate=(\d+)")
RX_TIMESTAMP=re.compile(r"^(\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})")

def adb(*args,timeout=30):
    p=subprocess.run(["adb",*args],capture_output=True,timeout=timeout,check=True)
    return p.stdout.decode("utf-8","replace").replace("\x00","")

def parse(logcat:str,bt:str,audio:str,start:str):
    counts=Counter();idx=Counter();samples=Counter();quality=Counter();codec_ids=Counter()
    transitions=[];mtus=Counter();frame_calls=0;last=None
    for line in logcat.splitlines():
        m=RX_TIMESTAMP.match(line)
        if not m or m[1][:len(start)]<start:continue
        ts=m[1];last=ts
        if x:=RX_BITRATE.search(line):
            idx[int(x[1])]+=1; counts[int(x[2])]+=1
        if x:=RX_FRAME.search(line):
            frame_calls+=1; samples[int(x[2])]+=1; quality[int(x[3])]+=1
        if x:=RX_TRANSITION.search(line):
            transitions.append(dict(time=ts,previous=int(x[2]),next=int(x[1])))
        if x:=RX_CIE.search(line):
            codec_ids[f"0x{x[1].lower()}:0x{x[2].lower()}"]+=1
        if x:=RX_MTU.search(line):
            mtus[int(x[1])]+=1
    codec_match=RX_CODEC.search(bt)
    selected=(dict(codec=codec_match[1],
                   sample_rate_hz=(96000 if "96000" in codec_match[2] else 48000 if "48000" in codec_match[2] else None),
                   bits_per_sample_field=("8_24" if "8_24" in codec_match[2] else None),
                   stereo="STEREO" in codec_match[2]) if codec_match else None)
    active_sources=[]
    for line in audio.splitlines():
        if not line.startswith(start[:5]):continue
        m=RX_TIMESTAMP.match(line)
        if m and m[1][:len(start)]<start:continue
        if x:=RX_AUDIO_SOURCE.search(line):active_sources.append(int(x[1]))
    return dict(
       schema=1,
       date_and_start_time=start,
       newest_logcat_time=last,
       selected_a2dp_codec=selected,
       sender_rate_selection_count=sum(counts.values()),
       sender_bitrate_counts_bps=dict(sorted(counts.items())),
       sender_index_counts=dict(sorted(idx.items())),
       sender_quality_levels=dict(sorted(quality.items())),
       frame_summary_event_count=frame_calls,
       sender_sample_rate_counts=dict(sorted(samples.items())),
       bitrate_transitions=transitions[-40:],
       vendor_codec_id_counts=dict(sorted(codec_ids.items())),
       observed_peer_mtu_log_values=dict(sorted(mtus.items())),
       audio_source_rates_seen_hz=sorted(set(active_sources)),
       caveats=[
         "Sender-selected bitrate is NOT an independent HCI/air-bitrate measurement.",
         "24-bit/96kHz Bluetooth output does not prove source media is lossless.",
         "Logcat is a rotating ring; absence of earlier transitions does not prove none happened.",
         "HCI snoop must contain ACL media packets for on-air packet analysis."
       ]
    )

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--start",default="11-04 18:43:41")
    a.add_argument("--output",type=Path,default=Path("tools/native_ssc_session.json"))
    args=a.parse_args()
    log=adb("shell","logcat","-d","-v","threadtime",timeout=45)
    bt=adb("shell","dumpsys","bluetooth_manager",timeout=20)
    audio=adb("shell","dumpsys","audio",timeout=20)
    result=parse(log,bt,audio,args.start)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
