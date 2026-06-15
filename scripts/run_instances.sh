#!/usr/bin/env bash
# run_instances.sh — launch N parallel intd-v2.js workers
# Usage: bash scripts/run_instances.sh [N]   (default: 5)
set -euo pipefail

NUM="${1:-5}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKER="$REPO_DIR/worker/intd-v2.js"

if [[ ! -f "$WORKER" ]]; then
  echo "[!] Worker not found: $WORKER" >&2; exit 1
fi
if [[ ! -d "$REPO_DIR/node_modules" ]]; then
  echo "[!] node_modules missing — run: npm install" >&2; exit 1
fi

echo "Launching $NUM intd-v2 instances..."
for i in $(seq 1 "$NUM"); do
  LOGFILE="/tmp/intd-${i}.log"
  echo "  Instance $i -> $LOGFILE"
  INSTANCE_ID="$i" CONFIG_PATH="$REPO_DIR/worker/intd-config.json" \
    nohup node "$WORKER" > "$LOGFILE" 2>&1 &
  sleep 0.3
done

echo ""
echo "Done. Check: ps aux | grep '[i]ntd-v2'"
for i in $(seq 1 "$NUM"); do echo "  tail -f /tmp/intd-${i}.log &"; done
