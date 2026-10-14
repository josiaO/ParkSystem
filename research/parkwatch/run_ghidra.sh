#!/usr/bin/env bash
# Static Ghidra pass over the ParkWatch binaries that own camera, video, OCR, and gate calls.
# Does not execute the Windows binaries.
set -u
RESEARCH_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$RESEARCH_DIR/../.." && pwd)"
GHIDRA_DIR="${1:-/tmp/ocx-ghidra/ghidra_12.1.4_PUBLIC}"
SRC="$WORKSPACE_DIR/Current_ParkSystem_configs/ParkingSystem/ParkWatch"
STAGE=/tmp/ghidra-bins/parkwatch
mkdir -p "$RESEARCH_DIR/project" "$RESEARCH_DIR/evidence/ghidra" "$STAGE" /tmp/ocx-ghidra/home
rm -f "$RESEARCH_DIR/project/"*.lock "$RESEARCH_DIR/project/"*.lock~
export JAVA_TOOL_OPTIONS='-Duser.home=/tmp/ocx-ghidra/home'
export GHIDRA_HEADLESS_MAXMEM="${GHIDRA_HEADLESS_MAXMEM:-1400M}"
# Copies, not symlinks: Ghidra names the program from the real file name, so two
# IPC_QY.dll symlinks would overwrite one project's results.
cp -f "$SRC/VideoDrivers/IPC_QY/IPC_QY.dll" "$STAGE/QY_IPC_QY.dll"
cp -f "$SRC/VideoDrivers/IPC_QY1/IPC_QY.dll" "$STAGE/QY1_IPC_QY.dll"
cp -f "$SRC/SimpleLPRDevAgent.dll" "$STAGE/SimpleLPRDevAgent.dll"
cp -f "$SRC/DVNetSDK.dll" "$STAGE/DVNetSDK.dll"
cp -f "$SRC/VideoDrivers/IPC_QY/NetSDK.dll" "$STAGE/QY_NetSDK.dll"
cp -f "$SRC/VideoDrivers/IPC_QY/PlaySdk.dll" "$STAGE/QY_PlaySdk.dll"
cp -f "$SRC/VideoDrivers/IPC_QY/RtspRecvSdk.dll" "$STAGE/QY_RtspRecvSdk.dll"
cp -f "$SRC/Park.exe" "$STAGE/Park.exe"
analyze() {
  local file="$1" timeout="$2"
  echo "ANALYZE $file timeout=$timeout"
  "$GHIDRA_DIR/support/analyzeHeadless" "$RESEARCH_DIR/project" ParkGhidra \
    -import "$STAGE/$file" -overwrite -analysisTimeoutPerFile "$timeout" -max-cpu 2 \
    -scriptPath "$WORKSPACE_DIR/research/ocxconfig/scripts" \
    -preScript PrepAnalysis.java \
    -postScript TraceCamera.java "$RESEARCH_DIR/evidence/ghidra" \
    > "$RESEARCH_DIR/evidence/ghidra/$file.log" 2>&1
  if grep -q "SCRIPT ERROR" "$RESEARCH_DIR/evidence/ghidra/$file.log"; then
    echo "FAIL $file script"
  elif grep -q "Import succeeded" "$RESEARCH_DIR/evidence/ghidra/$file.log"; then
    echo "OK $file"
  else
    echo "FAIL $file"
  fi
}
analyze QY_IPC_QY.dll 180
analyze QY1_IPC_QY.dll 180
analyze SimpleLPRDevAgent.dll 180
analyze DVNetSDK.dll 240
analyze QY_NetSDK.dll 420
analyze QY_PlaySdk.dll 240
analyze QY_RtspRecvSdk.dll 240
analyze Park.exe 900
echo DONE
