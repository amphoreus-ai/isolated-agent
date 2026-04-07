name: $project_name

services:
  task-env:
    build:
      context: .
      dockerfile: Dockerfile.task
    container_name: ${project_name}-task-env
    working_dir: /workspace
    init: true
    volumes:
      - $workspace_path:/workspace
    healthcheck:
      test: ["CMD-SHELL", "python3 --version && pgrep -x sshd"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 5s

  agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
    container_name: ${project_name}-agent
    working_dir: /workspace
    depends_on:
      task-env:
        condition: service_healthy
    environment:
      $api_key_env: $${$api_key_env:-}
      ANTHROPIC_API_KEY: $${ANTHROPIC_API_KEY:-}
      LD_PRELOAD: /lib/libexec_forward.so
      EXEC_FORWARD_LOCAL: $forward_local
    command: ["sleep", "infinity"]
    init: true
    volumes:
      - $workspace_path:/workspace
$agent_extra_volumes
