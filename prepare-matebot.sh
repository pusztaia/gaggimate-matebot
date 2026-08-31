#!/bin/sh
set -eu

# MATEbot host preparation
#
# Default layout:
#   /mnt/ssd/matebot/state
#
# The Portainer stack maps:
#   /mnt/ssd/matebot/state -> /data/state
#
# MATEbot runs as UID/GID 1000 by default.

MATEBOT_DIR="${1:-/mnt/ssd/matebot}"
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

STATE_DIR="$MATEBOT_DIR/state"

echo "Preparing MATEbot directories..."
echo "  Base:  $MATEBOT_DIR"
echo "  State: $STATE_DIR"
echo "  UID:   $PUID"
echo "  GID:   $PGID"

sudo install -d -m 755 -o "$PUID" -g "$PGID" "$MATEBOT_DIR"
sudo install -d -m 755 -o "$PUID" -g "$PGID" "$STATE_DIR"

echo
echo "MATEbot state directory is ready:"
ls -ld "$MATEBOT_DIR" "$STATE_DIR"
