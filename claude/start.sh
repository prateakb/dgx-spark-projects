#!/bin/bash
# Launches Claude Code with the Zulip channel plugin.
#
# The channel plugin runs as a subprocess of Claude Code (MCP stdio transport).
# Claude Code spawns `bun run /opt/zulip-channel/index.ts` and communicates
# via stdin/stdout.
#
# Auth strategy (in order of precedence):
#   1. Mounted credentials: mount host ~/.claude to /root/.claude (recommended)
#      Run `claude auth login` on the DGX host once, then mount the dir.
#   2. Interactive auth: `docker exec -it claude-code-zulip claude auth login`
#      Opens OAuth flow — prints a URL you open on your Mac.
#   3. API key only: set ANTHROPIC_API_KEY. May not work with --channels
#      if the feature requires OAuth. Works fine for inference via the proxy.
#
# Environment variables:
#   CLAUDE_PERMISSIONS_MODE - "unattended" (default) or "supervised"
#   ANTHROPIC_BASE_URL      - Points to the proxy (e.g., http://claude-code-proxy:8083)
#   ANTHROPIC_API_KEY       - API key for the proxy
#   ZULIP_URL               - Zulip server URL (used by channel plugin)
#   ZULIP_EMAIL             - Bot email
#   ZULIP_API_KEY           - Bot API key
#   ZULIP_STREAM            - Target stream (default: claude-code)
#   ZULIP_TOPIC             - Target topic (default: tasks)

LOG="/var/log/claude-start.log"

log() { echo "[claude-start] $*" | tee -a "$LOG"; }

PERMISSIONS_MODE="${CLAUDE_PERMISSIONS_MODE:-unattended}"

# --- Auth check ---
if [ -f /root/.claude/credentials.json ]; then
  log "Found mounted credentials at /root/.claude/credentials.json"
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  log "Using ANTHROPIC_API_KEY (channels may require 'claude auth login')"
  log "To auth interactively: docker exec -it claude-code-zulip claude auth login"
else
  log "WARNING: No auth found. Run: docker exec -it claude-code-zulip claude auth login"
fi

# --- Build Claude args ---
CLAUDE_ARGS=(
  --dangerously-load-development-channels
  --channels "plugin:zulip@local"
)

if [ "$PERMISSIONS_MODE" = "unattended" ]; then
  log "Mode: unattended (--dangerously-skip-permissions)"
  CLAUDE_ARGS+=(--dangerously-skip-permissions)
else
  log "Mode: supervised (permission relay via Zulip)"
fi

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
# Run claude directly (no tmux) so stdout/stderr go to docker logs.
# The container's tty: true + stdin_open: true in compose keep it interactive.
# To attach: docker attach claude-code-zulip
# To detach without stopping: Ctrl+P, Ctrl+Q
log "Launching: claude ${CLAUDE_ARGS[*]}"
exec claude "${CLAUDE_ARGS[@]}" 2>&1 | tee -a "$LOG"
