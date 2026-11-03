#!/usr/bin/env bash
# Reproduce the *identifier* catalogue from your own original Samsung encoder.
# Does not encode audio, change Bluetooth, pair devices, or modify firmware.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p tools
adb get-state | grep -qx device
adb push ssc_bitrate_catalog.c /data/local/tmp/ssc_bitrate_catalog.c >/dev/null
adb shell su -c '/data/data/com.termux/files/usr/bin/clang -O2 -Wall -Wextra /data/local/tmp/ssc_bitrate_catalog.c -o /data/local/tmp/ssc_bitrate_catalog -ldl'
adb shell su -c /data/local/tmp/ssc_bitrate_catalog > tools/ssc_bitrate_catalog_results.csv
python3 - <<'PY'
from pathlib import Path
import csv
p=Path('tools/ssc_bitrate_catalog_results.csv')
rows={int(r['requested_bps']):r for r in csv.DictReader(p.open())}
recognized={r for r,v in rows.items() if v['recognized']=='yes'}
expected={88000,96000,128000,152000,229000,250000,256000,
          291000,308000,328000,442000,584000,886000}
if recognized!=expected:
    raise SystemExit(f'RECOGNIZED MODE SET CHANGED: {sorted(recognized)} vs {sorted(expected)}')
for n in [1000000,1200000,1764000,2000000,2304000,2400000]:
    if rows[n]['header_code'] != '0xf3':
        raise SystemExit(f'Unexpected named high rate: {n}')
print(f'VALIDATED: {len(recognized)} recognized header IDs; highest: {max(recognized)} bps')
print('2.304/2.4 Mbps still fall back to generic 0xF3 marker.')
print('Source results saved only under gitignored tools/.')
PY
