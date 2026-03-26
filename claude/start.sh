#!/bin/bash
# Launches Claude Code inside tmux with the Zulip channel plugin.
#
# Usage from host:
#   docker exec -it claude-code-zulip tmux -S /tmp/claude-tmux attach -t claude
#   (detach: Ctrl+B, D)
#
#   Open a shell alongside Claude:
#   docker exec -it claude-code-zulip tmux -S /tmp/claude-tmux new-window -t claude
#
#   Run one-off commands:
#   docker exec -it claude-code-zulip bash
#
# Auth:
#   docker exec -it claude-code-zulip claude auth login

TMUX_SOCK="/tmp/claude-tmux"
LOG="/tmp/claude-start.log"

log() { echo "[claude-start] $*" | tee -a "$LOG"; }

PERMISSIONS_MODE="${CLAUDE_PERMISSIONS_MODE:-unattended}"

# --- Auth check ---
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  log "Auth: ANTHROPIC_API_KEY set (routing to proxy at ${ANTHROPIC_BASE_URL:-default})"
else
  log "WARNING: ANTHROPIC_API_KEY not set"
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
log "  docker exec -it claude-code-zulip tmux -S $TMUX_SOCK attach -t claude"
log "  (detach: Ctrl+B, D)"
log "=================="

# Clean up stale socket
rm -f "$TMUX_SOCK"

# Start tmux in the FOREGROUND with a known socket path.
# -S uses a shared socket so docker exec can find it.
# The foreground tmux process keeps the container alive.
# No pipes — claude needs a direct PTY for interactive stdin.
exec tmux -S "$TMUX_SOCK" new-session -s claude -n code \
  "claude ${CLAUDE_ARGS[*]}; echo; echo '[claude-start] Claude exited. Press Enter to restart or Ctrl+C to stop.'; read; exec $0"
