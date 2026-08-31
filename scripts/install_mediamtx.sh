#!/usr/bin/env bash
# Download MediaMTX into vendor/mediamtx/ (Linux amd64).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/vendor/mediamtx"
VERSION="${MEDIAMTX_VERSION:-v1.11.3}"
ARCH="${MEDIAMTX_ARCH:-linux_amd64}"
mkdir -p "$DEST"
cd "$DEST"
URL="https://github.com/bluenviron/mediamtx/releases/download/${VERSION}/mediamtx_${VERSION}_${ARCH}.tar.gz"
echo "Fetching $URL"
curl -fsSL -o mediamtx.tar.gz "$URL"
tar -xzf mediamtx.tar.gz
chmod +x mediamtx
./mediamtx --version
echo "Installed: $DEST/mediamtx"
