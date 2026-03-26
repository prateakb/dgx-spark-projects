# Stage 1: Install channel plugin dependencies using official Bun image
FROM oven/bun:1.1 AS channel-deps
WORKDIR /app
COPY channel/package.json channel/bun.lock ./
RUN bun install
COPY channel/ ./

# Stage 2: Final image with Claude Code + channel plugin
FROM node:22-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl git jq gosu tmux && \
    rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Copy pre-built channel plugin (with node_modules) from stage 1
COPY --from=channel-deps /app /opt/zulip-channel

# Copy Bun binary from stage 1 (needed at runtime to run the plugin)
COPY --from=channel-deps /usr/local/bin/bun /usr/local/bin/bun
COPY --from=channel-deps /usr/local/bin/bunx /usr/local/bin/bunx

# Rename the existing node user (uid 1000) to claude
# (Claude Code refuses --dangerously-skip-permissions as root)
RUN usermod -l claude -d /home/claude -m node && \
    groupmod -n claude node

# Create all directories the user needs and set ownership
RUN mkdir -p /home/claude/.config \
             /home/claude/.npm \
             /home/claude/.cache \
             /workspace \
             /data \
             /hooks && \
    chown -R claude:claude \
      /home/claude \
      /opt/zulip-channel \
      /workspace \
      /data \
      /hooks

# No ~/.claude mount needed — ANTHROPIC_API_KEY env var is sufficient.
# Claude Code checks env vars before looking for credential files.
ENV DISABLE_AUTOUPDATER=1

# Copy scripts
COPY claude/start.sh /usr/local/bin/start.sh
COPY claude/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/start.sh /usr/local/bin/entrypoint.sh

WORKDIR /workspace

# entrypoint.sh runs as root to fix volume ownership, then drops to claude user
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
