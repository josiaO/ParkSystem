#!/usr/bin/env bash
# Static Ghidra pass over the OcxConfig vendor package. Does not execute the Windows binaries.
# Usage: bash research/ocxconfig/run_analysis.sh [/absolute/path/to/ghidra]
set -u
RESEARCH_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$RESEARCH_DIR/../.." && pwd)"
GHIDRA_DIR="${1:-/tmp/ocx-ghidra/ghidra_12.1.4_PUBLIC}"
SRC="$WORKSPACE_DIR/Current_ParkSystem_configs/Camera_config/OcxConfig"
mkdir -p "$RESEARCH_DIR/project" "$RESEARCH_DIR/evidence" /tmp/ocx-ghidra/home
rm -f "$RESEARCH_DIR/project/"*.lock "$RESEARCH_DIR/project/"*.lock~
export JAVA_TOOL_OPTIONS='-Duser.home=/tmp/ocx-ghidra/home'
export GHIDRA_HEADLESS_MAXMEM="${GHIDRA_HEADLESS_MAXMEM:-1400M}"
analyze() {
  local file="$1" timeout="$2"
  echo "ANALYZE $file timeout=$timeout"
  "$GHIDRA_DIR/support/analyzeHeadless" "$RESEARCH_DIR/project" OcxVendor \
    -import "$SRC/$file" -overwrite -analysisTimeoutPerFile "$timeout" -max-cpu 2 \
    -scriptPath "$RESEARCH_DIR/scripts" \
    -preScript PrepAnalysis.java \
    -postScript TraceCamera.java "$RESEARCH_DIR/evidence" \
    > "$RESEARCH_DIR/evidence/$file.ghidra.log" 2>&1
  if grep -q "SCRIPT ERROR" "$RESEARCH_DIR/evidence/$file.ghidra.log"; then
    echo "FAIL $file script"
  elif grep -q "Import succeeded" "$RESEARCH_DIR/evidence/$file.ghidra.log"; then
    echo "OK $file"
  else
    echo "FAIL $file"
  fi
}
analyze CommModule.dll 180
analyze DevSearchHelper.dll 180
analyze NetSDK.dll 480
analyze OcxConfigClient.exe 600
analyze OcxConfig.ocx 700
echo DONE
