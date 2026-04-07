#!/usr/bin/env bash
set -euo pipefail

: "$${HOME:=$home_dir}"
: "$${TMPDIR:=$tmp_dir}"

mkdir -p "$$HOME" "$$TMPDIR"

# ---------------------------------------------------------------------------
# Dynamic wrapper generation: scan task-env for all available commands and
# create symlinks to task-run for anything that doesn't already exist locally.
# This ensures ALL CLI calls get forwarded to task-env via SSH — not just the
# handful of tools listed in the Dockerfile.
# ---------------------------------------------------------------------------
_generate_wrappers() {
  local count=0
  while IFS= read -r cmd; do
    [[ -z "$$cmd" ]] && continue
    # Skip if a local binary or wrapper already exists
    [[ -e "/usr/local/bin/$$cmd" || -e "/usr/bin/$$cmd" || -e "/bin/$$cmd" ]] && continue
    ln -sf task-run "/usr/local/bin/$$cmd" 2>/dev/null && ((count++)) || true
  done < <(ssh -o ConnectTimeout=3 task-env \
    'find /usr/bin /usr/local/bin /bin -maxdepth 1 \( -type f -o -type l \) -printf "%f\n" 2>/dev/null' | sort -u)
  echo "Auto-generated $$count tool wrappers from task-env"
}

if ssh -o ConnectTimeout=3 task-env true 2>/dev/null; then
  _generate_wrappers
else
  echo "Warning: task-env not reachable, skipping dynamic wrapper generation"
fi

if [[ $$# -gt 0 ]]; then
  exec "$$@"
fi

cat <<BANNER
Agent runtime container is ready.
Task environment: task-env (via SSH)
Shared workspace: /workspace
HOME: $${HOME}
TMPDIR: $${TMPDIR}

Usage:
  task-exec "<shell command>"
  task-exec <binary> [args...]
BANNER

exec sleep infinity
