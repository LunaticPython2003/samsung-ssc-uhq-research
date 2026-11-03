#!/usr/bin/env bash
# Read-only environment check, except local build cache/test output.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
CARGO="$HOME/.cargo/bin/cargo"
[[ -x "$CARGO" ]] || CARGO="$(command -v cargo)"
echo "[1/5] Git status:"
git status --short --branch
echo "[2/5] Python tests:"
python3 -m unittest -q test_ssc_rpc.py test_ssc_snoop.py test_ssc_btsnooz.py test_ssc_live_report.py test_ssc_rate_frame_analysis.py test_ssc_linux_bridge.py test_ssc_r640_receiver.py
echo "[3/5] Rust tests:"
"$CARGO" test --offline --manifest-path ssc-win-bridge/Cargo.toml --quiet
echo "[4/5] Private binaries / portable Ghidra:"
sha256sum vendor-local/libScalable_Encoder.so vendor-local/libbluetooth_jni.so
tools/jdk25/bin/java -version 2>&1 | head -1
test -x tools/ghidra_12.2_PUBLIC/support/analyzeHeadless
echo "Ghidra available."
echo "[5/5] ADB / temporary su:"
adb devices -l
adb shell su -c id || echo "ADB root unavailable; offline tests still completed."
echo "Workstation checks complete; no Bluetooth drivers or settings touched."
