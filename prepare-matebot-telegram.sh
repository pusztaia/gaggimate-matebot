#!/bin/sh
set -eu

# MATEbot Telegram secret preparation
#
# Default files:
#   /mnt/ssd/secrets/telegram_token
#   /mnt/ssd/secrets/telegram_chat_ids.json
#
# The chat ID file is stored as a JSON array because the Portainer
# example stack extracts the first entry and exports it as TELEGRAM_CHAT_ID.
#
# Permissions:
#   secrets directory: root:<PGID> 750
#   secret files:      root:<PGID> 640
#
# MATEbot runs as GID 1000 by default, so PGID defaults to 1000.

SECRETS_DIR="${1:-/mnt/ssd/secrets}"
PGID="${PGID:-1000}"

TOKEN_FILE="$SECRETS_DIR/telegram_token"
CHAT_IDS_FILE="$SECRETS_DIR/telegram_chat_ids.json"

echo "Preparing Telegram secret directory..."
sudo install -d -m 750 -o root -g "$PGID" "$SECRETS_DIR"

echo
printf "Telegram bot token: "

# Read the token without echoing it to the terminal.
OLD_STTY=""
if [ -t 0 ]; then
    OLD_STTY="$(stty -g)"
    trap 'stty "$OLD_STTY" 2>/dev/null || true' EXIT HUP INT TERM
    stty -echo
fi

IFS= read -r TELEGRAM_TOKEN

if [ -n "$OLD_STTY" ]; then
    stty "$OLD_STTY"
    trap - EXIT HUP INT TERM
fi

printf "\nTelegram chat ID: "
IFS= read -r TELEGRAM_CHAT_ID

if [ -z "$TELEGRAM_TOKEN" ]; then
    echo "Error: Telegram bot token must not be empty." >&2
    exit 1
fi

# Telegram chat IDs are signed integers. Validate without requiring jq/python.
case "$TELEGRAM_CHAT_ID" in
    -*)
        CHAT_ID_DIGITS="${TELEGRAM_CHAT_ID#-}"
        ;;
    *)
        CHAT_ID_DIGITS="$TELEGRAM_CHAT_ID"
        ;;
esac

if [ -z "$CHAT_ID_DIGITS" ]; then
    echo "Error: Telegram chat ID must not be empty." >&2
    exit 1
fi

case "$CHAT_ID_DIGITS" in
    *[!0-9]*)
        echo "Error: Telegram chat ID must be numeric, optionally starting with '-'." >&2
        exit 1
        ;;
esac

TMP_TOKEN="$(mktemp)"
TMP_CHAT="$(mktemp)"
trap 'rm -f "$TMP_TOKEN" "$TMP_CHAT"' EXIT HUP INT TERM

umask 077
printf '%s\n' "$TELEGRAM_TOKEN" > "$TMP_TOKEN"
printf '["%s"]\n' "$TELEGRAM_CHAT_ID" > "$TMP_CHAT"

sudo install -m 640 -o root -g "$PGID" "$TMP_TOKEN" "$TOKEN_FILE"
sudo install -m 640 -o root -g "$PGID" "$TMP_CHAT" "$CHAT_IDS_FILE"

rm -f "$TMP_TOKEN" "$TMP_CHAT"
trap - EXIT HUP INT TERM

unset TELEGRAM_TOKEN

echo
echo "Telegram secret files are ready:"
ls -ld "$SECRETS_DIR"
ls -l "$TOKEN_FILE" "$CHAT_IDS_FILE"

echo
echo "Chat ID file content:"
cat "$CHAT_IDS_FILE"

echo
echo "The bot token itself was not printed."
