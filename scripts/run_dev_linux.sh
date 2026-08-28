#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "Start API in terminal 1: uvicorn app.api_main:app --host 127.0.0.1 --port 8760"
echo "Start UI  in terminal 2: python -m app.desktop.main"
