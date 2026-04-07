#!/bin/bash
# Dispatch script for tool wrappers.
# When symlinked as e.g. "python3", runs python3 in task-env via SSH.
# When called directly: task-run <cmd> [args...]

CMD="$(basename "$0")"
if [ "$CMD" = "task-run" ]; then
  CMD="$1"; shift
fi

# Clamp working directory to /workspace
WD="$(pwd)"
case "$WD" in
  /workspace|/workspace/*) ;;
  *) WD="/workspace" ;;
esac

# Build properly quoted remote command
REMOTE="cd '${WD}' && exec '${CMD}'"
for arg in "$@"; do
  escaped=$(printf "%s" "$arg" | sed "s/'/'\\\\''/g")
  REMOTE="${REMOTE} '${escaped}'"
done

exec ssh task-env "$REMOTE"
