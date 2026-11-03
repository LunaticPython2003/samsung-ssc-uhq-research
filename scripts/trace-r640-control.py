#!/usr/bin/env python3
"""Read-only Thumb-2 xref and call-chain reconnaissance of exact R640 firmware.
Disassembles small relevant windows; never modifies firmware or earbuds.
"""
import argparse, sys, struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools/pydeps"))
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB,CS_MODE_LITTLE_ENDIAN
from capstone.arm_const import ARM_OP_IMM
IMAGE=ROOT/"vendor-local/buds-fw/R640XXU0AZD2.bin"
b=IMAGE.read_bytes()
cs=Cs(CS_ARCH_ARM,CS_MODE_THUMB|CS_MODE_LITTLE_ENDIAN);cs.detail=True
def window(a,z):
 print("\n========== THUMB",hex(a),hex(z),"==========")
 for x in cs.disasm(b[a:z],a):
  print(f"{x.address:08x} {x.mnemonic:<10} {x.op_str}")
def scans(targets):
 # signed Thumb32 branch immediate expansion: need exact validation via capstone
 print("\n==== CALLSITE SCAN ====")
 found={t:[] for t in targets}
 for i in range(0,len(b)-4,2):
  hw1=b[i]|b[i+1]<<8
  hw2=b[i+2]|b[i+3]<<8
  # Thumb BL bit patterns
  if (hw1&0xf800)!=0xf000 or (hw2&0xd000)!=0xd000:continue
  # S|imm10|J1|J2|imm11
  S=(hw1>>10)&1;J1=(hw2>>13)&1;J2=(hw2>>11)&1
  I1=(~(J1^S))&1;I2=(~(J2^S))&1
  val=(S<<24)|(I1<<23)|(I2<<22)|((hw1&0x3ff)<<12)|((hw2&0x7ff)<<1)
  if S: val-=(1<<25)
  dest=((i+4)+val)&0xffffffff
  if dest in found:
   found[dest].append(i)
 for t,refs in found.items():
  print(f"{t:#x}: {len(refs)} possible BLs {[hex(x) for x in refs[:60]]}")
 return found
if __name__=="__main__":
 import argparse
 pa=argparse.ArgumentParser()
 pa.add_argument('--short',action='store_true')
 args=pa.parse_args()
 scans([0x8afd4,0x8d968,0x8de50,0x8b000,0x8afec,0x17ac78])
 if not args.short:
  for a,z in [(0x8afd4,0x8b170),(0x8d968,0x8da2a),(0x17bbbe,0x17bbd8),
              (0x8de50,0x8defa),(0x8e014,0x8e02a),(0x17ac54,0x17ac90)]:
   window(a,z)
