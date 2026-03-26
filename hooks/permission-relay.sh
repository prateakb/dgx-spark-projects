#!/bin/bash
# pre_tool_use hook: Relays permission prompts to Zulip and waits for approval.
#
# Claude Code invokes this script before executing a tool. The script:
# 1. Posts a permission request to the configured Zulip stream/topic
# 2. Polls for a reply containing "APPROVE" or "DENY"
# 3. Exits 0 (approved) or 1 (denied)
#
# Environment variables (set in docker-compose):
#   ZULIP_URL       - Zulip server URL
#   ZULIP_EMAIL     - Bot email for authentication
#   ZULIP_API_KEY   - Bot API key
#   ZULIP_STREAM    - Stream to post permission requests to
#   ZULIP_TOPIC     - Topic for permission requests
#   APPROVAL_TIMEOUT - Seconds to wait for approval (default: 60)
#
# Hook receives tool info via stdin as JSON:
#   { "tool_name": "Bash", "tool_input": { "command": "git status" } }

set -euo pipefail

TIMEOUT="${APPROVAL_TIMEOUT:-60}"
ZULIP_AUTH=$(echo -n "${ZULIP_EMAIL}:${ZULIP_API_KEY}" | base64)
ZULIP_API="${ZULIP_URL}/api/v1"

# Read tool info from stdin
TOOL_INFO=$(cat)
TOOL_NAME=$(echo "$TOOL_INFO" | jq -r '.tool_name // "unknown"')
TOOL_INPUT=$(echo "$TOOL_INFO" | jq -r '.tool_input | tostring' 2>/dev/null || echo "$TOOL_INFO")

# Truncate long tool inputs for readability
if [ ${#TOOL_INPUT} -gt 500 ]; then
  TOOL_INPUT="${TOOL_INPUT:0:500}..."
fi

# Post permission request to Zulip
PERMISSION_MSG="**Permission Request**

Claude wants to use tool: \`${TOOL_NAME}\`

\`\`\`
${TOOL_INPUT}
\`\`\`

Reply with **APPROVE** or **DENY** (auto-denies in ${TIMEOUT}s)"

SEND_RESPONSE=$(curl -s -X POST "${ZULIP_API}/messages" \
  -H "Authorization: Basic ${ZULIP_AUTH}" \
  -d "type=stream" \
  -d "to=${ZULIP_STREAM}" \
  -d "topic=${ZULIP_TOPIC}" \
  --data-urlencode "content=${PERMISSION_MSG}")

MESSAGE_ID=$(echo "$SEND_RESPONSE" | jq -r '.id // empty')

if [ -z "$MESSAGE_ID" ]; then
  echo "[permission-relay] Failed to post permission request to Zulip" >&2
  exit 1
fi

# Register an event queue to listen for replies
QUEUE_RESPONSE=$(curl -s -X POST "${ZULIP_API}/register" \
  -H "Authorization: Basic ${ZULIP_AUTH}" \
  -d "event_types=[\"message\"]" \
  -d "narrow=[[\"stream\",\"${ZULIP_STREAM}\"],[\"topic\",\"${ZULIP_TOPIC}\"]]")

QUEUE_ID=$(echo "$QUEUE_RESPONSE" | jq -r '.queue_id // empty')
LAST_EVENT_ID=$(echo "$QUEUE_RESPONSE" | jq -r '.last_event_id // -1')

if [ -z "$QUEUE_ID" ]; then
  echo "[permission-relay] Failed to register event queue" >&2
  exit 1
fi

# Poll for approval/denial
START_TIME=$(date +%s)

while true; do
  ELAPSED=$(( $(date +%s) - START_TIME ))
  if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
    echo "[permission-relay] Timeout waiting for approval — denying" >&2
    # Clean up the event queue
    curl -s -X DELETE "${ZULIP_API}/events" \
      -H "Authorization: Basic ${ZULIP_AUTH}" \
      -d "queue_id=${QUEUE_ID}" > /dev/null 2>&1
    exit 1
  fi

  EVENTS_RESPONSE=$(curl -s "${ZULIP_API}/events?queue_id=${QUEUE_ID}&last_event_id=${LAST_EVENT_ID}&dont_block=true" \
    -H "Authorization: Basic ${ZULIP_AUTH}")

  EVENTS=$(echo "$EVENTS_RESPONSE" | jq -r '.events // []')
  EVENT_COUNT=$(echo "$EVENTS" | jq 'length')

  for i in $(seq 0 $((EVENT_COUNT - 1))); do
    EVENT=$(echo "$EVENTS" | jq ".[$i]")
    EVENT_TYPE=$(echo "$EVENT" | jq -r '.type')
    LAST_EVENT_ID=$(echo "$EVENT" | jq -r '.id')

    if [ "$EVENT_TYPE" != "message" ]; then
      continue
    fi

    SENDER=$(echo "$EVENT" | jq -r '.message.sender_email')
    CONTENT=$(echo "$EVENT" | jq -r '.message.content' | tr '[:lower:]' '[:upper:]')

    # Skip bot's own messages
    if [ "$SENDER" = "$ZULIP_EMAIL" ]; then
      continue
    fi

    if echo "$CONTENT" | grep -q "APPROVE"; then
      echo "[permission-relay] Approved by ${SENDER}" >&2
      curl -s -X DELETE "${ZULIP_API}/events" \
        -H "Authorization: Basic ${ZULIP_AUTH}" \
        -d "queue_id=${QUEUE_ID}" > /dev/null 2>&1
      exit 0
    fi

    if echo "$CONTENT" | grep -q "DENY"; then
      echo "[permission-relay] Denied by ${SENDER}" >&2
      curl -s -X DELETE "${ZULIP_API}/events" \
        -H "Authorization: Basic ${ZULIP_AUTH}" \
        -d "queue_id=${QUEUE_ID}" > /dev/null 2>&1
      exit 1
    fi
  done

  # Short sleep before next poll
  sleep 2
done
