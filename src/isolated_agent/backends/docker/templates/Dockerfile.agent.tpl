FROM $base_image

# System dependencies + compiler for LD_PRELOAD interceptor
RUN $pkg_install_cmd

# Build execve interceptor (LD_PRELOAD library).
# Catches execve calls that bypass the symlink/shim layer.
COPY intercept/exec_forward.c /tmp/exec_forward.c
RUN gcc -shared -fPIC -O2 -o /lib/libexec_forward.so /tmp/exec_forward.c -ldl \
    && rm /tmp/exec_forward.c

# Install agent CLI
RUN $cli_install_cmd

# SSH key + config for connecting to task-env
COPY .ssh/agent_key /root/.ssh/id_ed25519
COPY ssh_config /root/.ssh/config
RUN chmod 700 /root/.ssh \
    && chmod 600 /root/.ssh/id_ed25519 /root/.ssh/config

# Execution forwarding scripts (symlink layer — makes tools discoverable in PATH)
COPY scripts/exec-in-task.sh     /usr/local/bin/task-exec
COPY scripts/task-shell.sh       /usr/local/bin/task-shell
COPY scripts/task-run.sh         /usr/local/bin/task-run
COPY scripts/sh-wrapper.sh       /usr/local/bin/sh-wrapper
COPY scripts/entrypoint.sh       /usr/local/bin/agent-entrypoint
$bwrap_setup
RUN chmod +x /usr/local/bin/task-exec  \
             /usr/local/bin/task-shell  \
             /usr/local/bin/task-run    \
             /usr/local/bin/sh-wrapper  \
             /usr/local/bin/agent-entrypoint

# Static tool symlinks (PATH discoverability layer)
# These make common tools findable by shells (stat check succeeds).
# The symlinks point to task-run which forwards via SSH.
# LD_PRELOAD catches anything not covered by symlinks.
RUN $tool_symlinks_local
RUN $tool_symlinks_usr

$env_vars

RUN mkdir -p $home_dir $tmp_dir

$user_setup

# MUST BE LAST: replace /bin/sh with our wrapper.
# Docker uses /bin/sh for RUN commands, so this must come after all RUN steps.
# mv is atomic and preserves the running shell's inode.
RUN mv /bin/sh /bin/sh.real \
    && cp /usr/local/bin/sh-wrapper /bin/sh \
    && chmod +x /bin/sh

$user_directive

WORKDIR /workspace
ENTRYPOINT ["agent-entrypoint"]
CMD ["sleep", "infinity"]
