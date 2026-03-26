#!/bin/bash
# Launches Claude Code with the Zulip channel plugin.
#
# Runs as non-root user "claude" (required: --dangerously-skip-permissions
# is blocked when running as root).
#
# Auth strategy (in order of precedence):
#   1. Mounted credentials: mount host ~/.claude to /home/claude/.claude
#      Run `claude auth login` on the DGX host once, then mount the dir.
#   2. Interactive auth: `docker exec -it claude-code-zulip claude auth login`
#   3. API key only: set ANTHROPIC_API_KEY.
#
# Environment variables:
#   CLAUDE_PERMISSIONS_MODE - "unattended" (default) or "supervised"
#   ANTHROPIC_BASE_URL      - Points to the proxy
#   ANTHROPIC_API_KEY       - API key for the proxy
#   ZULIP_URL               - Zulip server URL
#   ZULIP_EMAIL             - Bot email
#   ZULIP_API_KEY           - Bot API key
#   ZULIP_STREAM            - Target stream (default: claude-code)
#   ZULIP_TOPIC             - Target topic (default: tasks)

CLAUDE_HOME="$HOME/.claude"
LOG="/tmp/claude-start.log"

log() { echo "[claude-start] $*" | tee -a "$LOG"; }

PERMISSIONS_MODE="${CLAUDE_PERMISSIONS_MODE:-unattended}"

# --- Auth check ---
if [ -f "$CLAUDE_HOME/credentials.json" ]; then
  log "Found mounted credentials at $CLAUDE_HOME/credentials.json"
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  log "Using ANTHROPIC_API_KEY (channels may require 'claude auth login')"
  log "To auth interactively: docker exec -it claude-code-zulip claude auth login"
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

# --- Launch ---
# Run claude directly so stdout/stderr go to docker logs.
# To attach: docker attach claude-code-zulip
# To detach without stopping: Ctrl+P, Ctrl+Q
log "Launching: claude ${CLAUDE_ARGS[*]}"
exec claude "${CLAUDE_ARGS[@]}"
