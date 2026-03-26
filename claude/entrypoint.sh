#!/bin/bash
# Entrypoint: runs as root to fix volume ownership, then drops to user 'claude'.
#
# Mounted volumes (host dirs, named volumes) may be owned by root or the host
# user. This script ensures the 'claude' user can write to all required paths
# before handing off to start.sh.

set -e

# Fix ownership on mounted volumes
chown -R claude:claude \
  /workspace \
  /data \
  2>/dev/null || true

# /hooks is read-only mount — skip chown, just ensure it's readable
chmod -R a+r /hooks 2>/dev/null || true

# Ensure /tmp is writable by claude (for tmux socket)
chmod 1777 /tmp 2>/dev/null || true

# Drop to claude user and run start.sh
exec gosu claude /usr/local/bin/start.sh "$@"
