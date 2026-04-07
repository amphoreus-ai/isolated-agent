#!/bin/bash
# /bin/sh replacement that forwards -c commands to task-env via SSH.
# Real sh is preserved at /bin/sh.real for container-internal use.
#
# Codex runs all task commands as: /bin/sh -lc "command"
# By intercepting this, ALL execution goes to task-env natively —
# including venv shebangs, pip, and compound command chains.

# Quick check: does any arg contain -c?
has_c=false
for arg in "$@"; do
  case "$arg" in
    -c|-lc|-cl|-elc|-lec|-ec|-ce) has_c=true; break ;;
  esac
done

if ! $has_c; then
  exec /bin/sh.real "$@"
fi

# Forward -c command to task-env
WD="$(pwd)"
case "$WD" in
  /workspace|/workspace/*) ;;
  *) WD="/workspace" ;;
esac

# Skip flags until we find the one containing -c, then grab the command
while [[ $# -gt 0 ]]; do
  case "$1" in
    -c)   shift; break ;;
    -*c*)  shift; break ;;  # -lc, -elc, etc.
    *)     shift ;;
  esac
done

if [[ $# -gt 0 ]]; then
  CMD="$1"
  exec ssh task-env "cd '${WD}' && ${CMD}"
fi

exec /bin/sh.real "$@"
