#!/usr/bin/env bash
# Run portable Ghidra against private, locally extracted Samsung binaries.
# Usage: bash scripts/ghidra-local.sh bluetooth TraceSscControlXrefs.java
#        bash scripts/ghidra-local.sh encoder TraceSscHeadroom.java
#        bash scripts/ghidra-local.sh bluetooth DumpSscBitrateTables.java --import
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:-}"
SCRIPT="${2:-}"
IMPORT="${3:-}"
if [[ ! -f "ghidra-scripts/$SCRIPT" ]]; then
    echo "Supply a script from ghidra-scripts/." >&2
    exit 2
fi
case "$MODE" in
    encoder)
        LIB="libScalable_Encoder.so"
        PROJECT="SSCEncoder"
        DIR="encoder"
        ;;
    bluetooth)
        LIB="libbluetooth_jni.so"
        PROJECT="SSCBluetooth"
        DIR="bluetooth"
        ;;
    *)
        echo "Usage: $0 encoder|bluetooth ScriptName.java [--import]" >&2
        exit 2
        ;;
esac
JAVA_HOME="$ROOT/tools/jdk25"
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"
GHIDRA="$ROOT/tools/ghidra_12.2_PUBLIC/support/analyzeHeadless"
[[ -x "$GHIDRA" && -r "$ROOT/vendor-local/$LIB" ]] || {
    echo "Install portable JDK/Ghidra and extract the local Samsung libraries first." >&2
    exit 3
}
mkdir -p "$ROOT/ghidra-projects-local/$DIR" "$ROOT/tools/ghidra-runs"
LOG="$ROOT/tools/ghidra-runs/${MODE}-${SCRIPT%.java}.log"
if [[ "$IMPORT" == "--import" ]]; then
    "$GHIDRA" "$ROOT/ghidra-projects-local/$DIR" "$PROJECT" \
        -import "$ROOT/vendor-local/$LIB" \
        -scriptPath "$ROOT/ghidra-scripts" -postScript "$SCRIPT" \
        -analysisTimeoutPerFile 330 > "$LOG" 2>&1
else
    "$GHIDRA" "$ROOT/ghidra-projects-local/$DIR" "$PROJECT" \
        -process "$LIB" -noanalysis \
        -scriptPath "$ROOT/ghidra-scripts" -postScript "$SCRIPT" > "$LOG" 2>&1
fi
echo "Ghidra completed. Private analysis log: $LOG"
grep -E "REPORT:|TOTAL_FUNCTIONS|UNIQUE_DECOMPILED_FUNCTIONS|TABLE_REFERENCE_COUNT|ERROR" "$LOG" | tail -16 || true
