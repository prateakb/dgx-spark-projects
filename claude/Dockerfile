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
    apt-get install -y --no-install-recommends curl git jq sudo && \
    rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Copy pre-built channel plugin (with node_modules) from stage 1
COPY --from=channel-deps /app /opt/zulip-channel

# Copy Bun binary from stage 1 (needed at runtime to run the plugin)
COPY --from=channel-deps /usr/local/bin/bun /usr/local/bin/bun
COPY --from=channel-deps /usr/local/bin/bunx /usr/local/bin/bunx

# Create non-root user (Claude Code refuses --dangerously-skip-permissions as root)
RUN useradd -m -s /bin/bash claude && \
    mkdir -p /home/claude/.claude /workspace /data /hooks && \
    chown -R claude:claude /home/claude /opt/zulip-channel /workspace /data /hooks

# Copy startup script
COPY claude/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

USER claude
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/start.sh"]
