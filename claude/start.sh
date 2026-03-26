#!/bin/bash
# Launches Claude Code in tmux with the Zulip channel active.
# Container restart policy handles crashes.
#
# Environment variables:
#   CLAUDE_PERMISSIONS_MODE - "unattended" (default) or "supervised"
#   ANTHROPIC_BASE_URL     - Points to the proxy (e.g., http://claude-code-proxy:8083)
#   ANTHROPIC_API_KEY      - API key for the proxy

set -euo pipefail

PERMISSIONS_MODE="${CLAUDE_PERMISSIONS_MODE:-unattended}"

CLAUDE_ARGS=(
  --dangerously-load-development-channels
  --channels "plugin:zulip@local"
)

if [ "$PERMISSIONS_MODE" = "unattended" ]; then
  echo "[claude-start] Running in unattended mode (--dangerously-skip-permissions)"
  CLAUDE_ARGS+=(--dangerously-skip-permissions)
else
  echo "[claude-start] Running in supervised mode (permissions relay via Zulip)"
fi

echo "[claude-start] Launching Claude Code with args: ${CLAUDE_ARGS[*]}"

# Start Claude Code in a tmux session so the container stays alive
tmux new-session -d -s claude \
  "claude ${CLAUDE_ARGS[*]}"

# Keep the container running by attaching to tmux
exec tmux attach -t claude
