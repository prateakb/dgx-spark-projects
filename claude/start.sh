#!/bin/bash
# Launches Claude Code inside tmux with the Zulip channel plugin.
#
# Usage from host:
#   docker exec -it claude-code-zulip tmux attach -t claude
#   (detach: Ctrl+B, D)
#
#   Open a shell alongside Claude:
#   docker exec -it claude-code-zulip tmux new-window -t claude
#
#   Run one-off commands:
#   docker exec -it claude-code-zulip bash
#
# Auth:
#   docker exec -it claude-code-zulip claude auth login

LOG="/tmp/claude-start.log"

log() { echo "[claude-start] $*" | tee -a "$LOG"; }

PERMISSIONS_MODE="${CLAUDE_PERMISSIONS_MODE:-unattended}"

# --- Auth check ---
CLAUDE_HOME="$HOME/.claude"
if [ -f "$CLAUDE_HOME/credentials.json" ]; then
  log "Found mounted credentials at $CLAUDE_HOME/credentials.json"
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  log "Using ANTHROPIC_API_KEY (channels may require 'claude auth login')"
else
  log "WARNING: No auth found. Run: docker exec -it claude-code-zulip claude auth login"
fi

# --- Build Claude args ---
# Development channels are passed directly to --dangerously-load-development-channels
# (not via --channels, which is for official allowlisted plugins only)
CLAUDE_ARGS=(
  --dangerously-load-development-channels "plugin:zulip@local"
)

if [ "$PERMISSIONS_MODE" = "unattended" ]; then
  log "Mode: unattended (--dangerously-skip-permissions)"
  CLAUDE_ARGS+=(--dangerously-skip-permissions)
else
  log "Mode: supervised (permission relay via Zulip)"
fi

log "Running as: $(whoami) (uid=$(id -u))"
log "Channel plugin: /opt/zulip-channel/index.ts"
log "Proxy: ${ANTHROPIC_BASE_URL:-not set}"
log "Zulip: ${ZULIP_URL:-not set} → #${ZULIP_STREAM:-claude-code} > ${ZULIP_TOPIC:-tasks}"

# --- Verify claude is installed ---
if ! command -v claude &>/dev/null; then
  log "ERROR: claude command not found"
  exit 1
fi
log "Claude Code version: $(claude --version 2>&1 || echo 'unknown')"

# --- Launch in tmux ---
log "Launching: claude ${CLAUDE_ARGS[*]}"
log ""
log "=== To connect ==="
log "  docker exec -it claude-code-zulip tmux attach -t claude"
log "  (detach: Ctrl+B, D)"
log "  (new shell: docker exec -it claude-code-zulip tmux new-window -t claude)"
log "=================="

# Start tmux with Claude Code in the first window
tmux new-session -d -s claude -n code \
  "claude ${CLAUDE_ARGS[*]} 2>&1 | tee -a $LOG; echo '[claude-start] Claude exited. Press Enter to restart or Ctrl+C to stop.'; read; exec $0"

# Keep the container alive by waiting on the tmux server.
# If tmux dies, the container exits and docker restarts it.
exec tmux wait-for claude-exit
