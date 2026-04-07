#!/bin/bash
# Shell wrapper that forwards command execution to task-env via SSH.
# Set as SHELL env var so Codex uses this for shell command execution.

quote_arg() {
  printf "%s" "$1" | sed "s/'/'\\\\''/g"
}

# Clamp working directory to /workspace
WD="$(pwd)"
case "$WD" in
  /workspace|/workspace/*) ;;
  *) WD="/workspace" ;;
esac

WD_ESCAPED="$(quote_arg "$WD")"

case "${1:-}" in
  -c)
    shift
    CMD="$1"; shift
    CMD_ESCAPED="$(quote_arg "$CMD")"
    REMOTE="cd '${WD_ESCAPED}' && exec bash -c '${CMD_ESCAPED}'"
    for arg in "$@"; do
      REMOTE="${REMOTE} '$(quote_arg "$arg")'"
    done
    exec ssh task-env "$REMOTE"
    ;;
  "")
    exec ssh -t task-env "cd '${WD_ESCAPED}' && exec bash -l"
    ;;
  *)
    # Script file or other bash flags — forward to remote bash
    REMOTE="cd '${WD_ESCAPED}' && exec bash"
    for arg in "$@"; do
      REMOTE="${REMOTE} '$(quote_arg "$arg")'"
    done
    exec ssh task-env "$REMOTE"
    ;;
esac
