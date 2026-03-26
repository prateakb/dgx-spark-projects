#!/bin/bash
# Launches Claude Code in tmux with the Zulip channel plugin.
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

set -euo pipefail

PERMISSIONS_MODE="${CLAUDE_PERMISSIONS_MODE:-unattended}"

# --- Auth check ---
if [ -f /root/.claude/credentials.json ]; then
  echo "[claude-start] Found mounted credentials at /root/.claude/credentials.json"
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[claude-start] Using ANTHROPIC_API_KEY (channels may require 'claude auth login')"
  echo "[claude-start] To auth interactively: docker exec -it claude-code-zulip claude auth login"
else
  echo "[claude-start] WARNING: No auth found. Run: docker exec -it claude-code-zulip claude auth login"
fi

# --- Build Claude args ---
CLAUDE_ARGS=(
  --dangerously-load-development-channels
  --channels "plugin:zulip@local"
)

if [ "$PERMISSIONS_MODE" = "unattended" ]; then
  echo "[claude-start] Mode: unattended (--dangerously-skip-permissions)"
  CLAUDE_ARGS+=(--dangerously-skip-permissions)
else
  echo "[claude-start] Mode: supervised (permission relay via Zulip)"
fi

echo "[claude-start] Channel plugin: /opt/zulip-channel/index.ts"
echo "[claude-start] Proxy: ${ANTHROPIC_BASE_URL:-not set}"
echo "[claude-start] Zulip: ${ZULIP_URL:-not set} → #${ZULIP_STREAM:-claude-code} > ${ZULIP_TOPIC:-tasks}"
echo "[claude-start] Launching Claude Code..."

# Start Claude Code in a tmux session so the container stays alive
tmux new-session -d -s claude \
  "claude ${CLAUDE_ARGS[*]}"

# Keep the container running by attaching to tmux
exec tmux attach -t claude
