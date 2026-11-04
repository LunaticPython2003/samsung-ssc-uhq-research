#!/usr/bin/env python3
"""Read-only SSC/886-kbps footprint audit of the user's own rooted Samsung phone.

Only copies operating-system and vendor library/firmware files into ignored
vendor-local/android-886/. No user-data, app secrets, wireless traces or files
under /data are accessed. No system configuration or playback is changed.

The output is a *literal-pattern* inventory. A hit is NOT a proven bitrate
selector until a real code reference is established with Ghidra.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "vendor-local" / "android-886"
TARGETS = [
 "/system/lib64/libScalable_Encoder.so",
 "/apex/com.android.bt/lib64/libbluetooth_jni.so",
 "/vendor/lib64/android.hardware.bluetooth.audio-impl.so",
 "/vendor/lib64/libbluetooth_audio_session.so",
 "/vendor/lib64/libbluetooth_audio_session_aidl.so",
 "/vendor/lib64/libbluetooth_audio_session_aidl_qti.so",
 "/vendor/lib64/libbluetooth_audio_session_qti.so",
 "/vendor/lib64/libbluetooth_audio_session_qti_2_1.so",
 "/vendor/lib64/libsehbluetooth_audio_session_aidl.so",
 "/vendor/lib64/vendor.samsung.hardware.bluetooth.audio-impl.so",
 "/vendor/lib64/hw/android.hardware.bluetooth.audio-impl-qti.so",
 "/vendor/lib64/hw/android.hardware.bluetooth.audio_sw.so",
 "/vendor/lib64/hw/audio.bluetooth.default.so",
 "/vendor/lib64/hw/audio.bluetooth_qti.default.so",
 "/vendor/lib64/hw/libsecaudiohal_aidl.so",
 "/vendor/lib64/hw/vendor.qti.hardware.bluetooth_audio@2.0-impl.so",
 "/vendor/lib64/hw/vendor.qti.hardware.bluetooth_audio@2.1-impl.so",
 "/vendor/lib64/libqc2audio_basecodec.so",
 "/vendor/lib64/libqc2audio_hwaudiocodec.so",
 "/vendor/lib64/libqc2audio_swaudiocodec.so",
 "/vendor/firmware/hmtbtfw20.tlv",
 "/vendor/firmware/hmtnv20.b39",
 "/vendor/etc/a2dp_audio_policy_configuration.xml",
 "/vendor/etc/bluetooth_audio_policy_configuration_7_0.xml",
 "/vendor/etc/bluetooth_qti_audio_policy_configuration.xml",
 "/vendor/etc/vintf/manifest/seh_bluetooth_audio.xml",
 "/apex/com.android.bt/etc/bluetooth/bt_stack.conf",
 # ADSP fragments from the on-device firmware_mnt mount, for literal scans;
 # literal matches here are low-confidence without segment/module disassembly.
 "/vendor/firmware_mnt/image/adsp.b10",
 "/vendor/firmware_mnt/image/adsp.b23",
 "/vendor/firmware_mnt/image/adsp.b37",
]
RATES=(152000,250000,291000,308000,328000,442000,584000,886000,2304000)

def fetch(path:str)->bytes:
    result=subprocess.run(["adb","exec-out","su","-c",f"cat {shlex.quote(path)}"],
                          capture_output=True,timeout=30)
    if result.returncode or not result.stdout:
        raise RuntimeError(f"{path}: rc={result.returncode}, "
                           f"reason={result.stderr.decode(errors='replace')[:120]}")
    return result.stdout

def all_offsets(buf:bytes, needle:bytes, cap:int=30)->list[int]:
    pos=0; offsets=[]
    while len(offsets)<cap:
        pos=buf.find(needle,pos)
        if pos<0: break
        offsets.append(pos)
        pos+=1
    return offsets

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    reports=[]
    for path in TARGETS:
        # The nested structure prevents collisions and keeps provenance explicit.
        target=OUT/path.lstrip("/")
        target.parent.mkdir(parents=True,exist_ok=True)
        try:
            if target.exists() and target.stat().st_size>0:
                data=target.read_bytes()
            else:
                data=fetch(path)
                target.write_bytes(data)
        except Exception as err:
            print("SKIP",path,str(err)[:220],flush=True)
            continue
        stats={"path":path,"file":str(target.relative_to(ROOT)),
            "bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),
            "elf":data.startswith(b"\x7fELF"),"rates":{}}
        for rate in RATES:
            pat=struct.pack("<I",rate)
            offs=all_offsets(data,pat)
            stats["rates"][str(rate)]={
                "aligned_literal_offsets":[hex(x) for x in offs if x%4==0],
                "unaligned_literal_offsets":[hex(x) for x in offs if x%4!=0],
                "ascii_count":len(all_offsets(data,str(rate).encode(),cap=100))
            }
        ascii_context=[]
        for m in re.finditer(rb"[ -~]{12,}",data):
            s=m.group(0)
            if re.search(rb"ssc[_ -]|scalable|a2dp_ssc|sscb|sscuhq|hifi.*ssc|ssc.*hifi",s,re.I):
                ascii_context.append(s[:150].decode(errors="replace"))
            if len(ascii_context)>=18:break
        stats["strings_sample"]=ascii_context
        reports.append(stats)
        interesting=[str(rate) for rate in RATES if
                     stats["rates"][str(rate)]["aligned_literal_offsets"]
                     or stats["rates"][str(rate)]["ascii_count"]]
        print(f"{path} bytes={len(data)} ELF={stats['elf']} "
              f"literal_or_ascii_rates={','.join(interesting) or 'none'}",flush=True)
    (ROOT/"tools").mkdir(exist_ok=True)
    dest=ROOT/"tools/android_ssc_886_footprint.json"
    dest.write_text(json.dumps(reports,indent=2)+"\n")
    print("Saved sanitized audit:",dest)
    # Explicit summary where an aligned 886000 constant was found.
    for row in reports:
        v=row["rates"]["886000"]
        if v["aligned_literal_offsets"] or v["ascii_count"]:
            print("886KBPS_CANDIDATE",row["path"],v)
    print("All proprietary files remain in gitignored vendor-local/android-886/")
if __name__=="__main__":main()
