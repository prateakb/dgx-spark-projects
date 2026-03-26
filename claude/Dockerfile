# Stage 1: Install channel plugin dependencies using official Bun image
FROM oven/bun:1.1 AS channel-deps
WORKDIR /app
COPY channel/package.json channel/bun.lock ./
RUN bun install
COPY channel/ ./

# Stage 2: Final image with Claude Code + channel plugin
FROM node:22-slim

# Install system dependencies (tmux, curl, git, jq for hooks)
RUN apt-get update && \
    apt-get install -y --no-install-recommends tmux curl git jq && \
    rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Copy pre-built channel plugin (with node_modules) from stage 1
COPY --from=channel-deps /app /opt/zulip-channel

# Copy Bun binary from stage 1 (needed at runtime to run the plugin)
COPY --from=channel-deps /usr/local/bin/bun /usr/local/bin/bun
COPY --from=channel-deps /usr/local/bin/bunx /usr/local/bin/bunx

# Copy startup script
COPY claude/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/start.sh"]
