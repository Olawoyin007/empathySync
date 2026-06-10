#!/bin/sh
# Drop from root to PUID:PGID before starting the app.
#
# Without this the container runs as root and writes root-owned files into
# the bind-mounted ./data and ./logs dirs. Any later non-root run (or the
# host user trying to edit conversation history) then fails silently on EPERM.
#
# Set PUID/PGID in docker-compose.yml or your .env to match your host user:
#   id -u   # find your PUID
#   id -g   # find your PGID
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if ! getent group "$PGID" >/dev/null 2>&1; then
    groupadd -g "$PGID" empathysync
fi
if ! getent passwd "$PUID" >/dev/null 2>&1; then
    useradd -u "$PUID" -g "$PGID" -M -s /bin/sh -d /app empathysync
fi

# Repair ownership on writable paths so files written by a previous
# root run don't block the non-root user on restart.
for dir in /app/data /app/logs; do
    if [ -d "$dir" ]; then
        find "$dir" -not -uid "$PUID" -print0 2>/dev/null \
            | xargs -0 -r chown "$PUID:$PGID" 2>/dev/null || true
    fi
done

# exec + gosu: no extra shell layer, so SIGTERM from `docker stop`
# reaches Streamlit directly instead of being swallowed by a wrapper.
exec gosu "$PUID:$PGID" "$@"
