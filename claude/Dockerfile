FROM node:22-slim

# Install system dependencies (tmux, curl, git, jq for hooks)
RUN apt-get update && \
    apt-get install -y --no-install-recommends tmux curl git jq unzip && \
    rm -rf /var/lib/apt/lists/*

# Install Bun (needed to run the channel plugin as a subprocess)
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Copy and install the channel plugin
COPY channel/ /opt/zulip-channel/
WORKDIR /opt/zulip-channel
RUN bun install

# Copy startup script
COPY claude/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/start.sh"]
