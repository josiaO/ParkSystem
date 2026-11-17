#!/usr/bin/env bash
# Zirp portal (public pay page + back office).
#   ./start-portal.sh                         build if needed, then start (PORT, default 3000)
#   ./start-portal.sh --api http://host:8760  point at another Zirp server first
#   ./start-portal.sh --rebuild               rebuild after updating the code
set -euo pipefail
cd "$(dirname "$0")"

command -v node >/dev/null || { echo "Node.js 20+ is required (e.g. sudo apt install nodejs, or nvm)."; exit 1; }

rebuild=0; api_args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --rebuild) rebuild=1 ;;
    --api) api_args=(--api "$2"); shift ;;
  esac
  shift
done

node scripts/check-env.mjs ${api_args[@]+"${api_args[@]}"} || true
[ -d node_modules ] || npm ci --no-audit --no-fund
if [ "$rebuild" = 1 ] || [ ! -f .next/BUILD_ID ]; then npm run build; fi
export PORT="${PORT:-3000}"
echo "Portal: http://localhost:$PORT   (pay page: /p/<ticket code>, back office: /admin)"
exec npx next start -p "$PORT"
