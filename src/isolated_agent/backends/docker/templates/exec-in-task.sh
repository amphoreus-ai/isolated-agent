#!/usr/bin/env bash
set -euo pipefail

TASK_WORKDIR="${TASK_WORKDIR:-/workspace}"

usage() {
  cat <<'EOF'
Usage:
  task-exec "<shell command>"
  task-exec <binary> [args...]

Examples:
  task-exec "python3 --version"
  task-exec node --version
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 64
fi

if ! ssh -o ConnectTimeout=2 task-env true 2>/dev/null; then
  echo "Cannot connect to task-env via SSH." >&2
  echo "Start it with: ./scripts/setup.sh && docker compose up -d --build" >&2
  exit 1
fi

if [[ $# -eq 1 ]]; then
  exec ssh task-env "cd '${TASK_WORKDIR}' && $1"
fi

CMD="$1"; shift
REMOTE="cd '${TASK_WORKDIR}' && exec '${CMD}'"
for arg in "$@"; do
  escaped=$(printf "%s" "$arg" | sed "s/'/'\\\\''/g")
  REMOTE="${REMOTE} '${escaped}'"
done
exec ssh task-env "$REMOTE"
