#!/bin/bash
# bwrap shim that redirects execution to task-env via SSH.
# Preserves --chdir, --setenv, and --clearenv semantics.
# All other bwrap options (--ro-bind, --tmpfs, --uid/gid, etc.) are
# parsed and discarded — the Docker container is the sandbox boundary.

[[ "${1:-}" == "--version" ]] && { echo "bubblewrap 0.11.0"; exit 0; }

CHDIR="/workspace"
CLEARENV=false
declare -a SETENVS=()

# Known flag arities from bwrap(1)
declare -A ARITY_2=(
  [--ro-bind]=1 [--ro-bind-try]=1 [--bind]=1 [--bind-try]=1
  [--dev-bind]=1 [--dev-bind-try]=1 [--symlink]=1
  [--overlay]=1 [--tmp-overlay]=1 [--overlay-src]=1 [--ro-overlay]=1
)
declare -A ARITY_1=(
  [--tmpfs]=1 [--dev]=1 [--proc]=1 [--dir]=1
  [--unsetenv]=1 [--lock-file]=1 [--sync-fd]=1 [--seccomp]=1
  [--exec-label]=1 [--file-label]=1 [--perms]=1 [--size]=1
  [--uid]=1 [--gid]=1 [--hostname]=1 [--cap-add]=1 [--cap-drop]=1
  [--file]=1 [--bind-data]=1 [--ro-bind-data]=1 [--chmod]=1
  [--remount-ro]=1 [--add-seccomp-fd]=1 [--block-fd]=1
  [--userns-block-fd]=1 [--info-fd]=1 [--json-status-fd]=1
  [--userns]=1 [--userns2]=1 [--pidns]=1
)

CMD=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --)       shift; CMD=("$@"); break ;;
    --chdir)  CHDIR="$2"; shift 2 ;;
    --clearenv) CLEARENV=true; shift ;;
    --setenv) SETENVS+=("$2=$3"); shift 3 ;;
    *)
      if [[ -n "${ARITY_2[$1]+_}" ]]; then shift 3
      elif [[ -n "${ARITY_1[$1]+_}" ]]; then shift 2
      elif [[ "$1" == --* ]]; then shift
      else CMD=("$@"); break
      fi ;;
  esac
done

[[ ${#CMD[@]} -eq 0 ]] && { echo "bwrap-shim: no command" >&2; exit 1; }

# Build remote command preserving env semantics
REMOTE="cd '${CHDIR}'"

if $CLEARENV; then
  REMOTE="${REMOTE} && exec env -i"
  for ev in "${SETENVS[@]}"; do
    escaped=$(printf "%s" "$ev" | sed "s/'/'\\\\''/g")
    REMOTE="${REMOTE} '${escaped}'"
  done
else
  for ev in "${SETENVS[@]}"; do
    escaped=$(printf "%s" "$ev" | sed "s/'/'\\\\''/g")
    REMOTE="${REMOTE} && export '${escaped}'"
  done
  REMOTE="${REMOTE} && exec"
fi

for arg in "${CMD[@]}"; do
  escaped=$(printf "%s" "$arg" | sed "s/'/'\\\\''/g")
  REMOTE="${REMOTE} '${escaped}'"
done

exec ssh task-env "$REMOTE"
