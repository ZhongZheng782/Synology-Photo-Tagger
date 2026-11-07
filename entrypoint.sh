#!/bin/sh
set -eu

# Keep Flask's signed browser session stable across container recreation.
# The file lives on the persistent /data volume; NAS passwords and OTP codes
# are never written here.
if [ -z "${APP_SECRET_KEY:-}" ]; then
    APP_SECRET_KEY_FILE="${APP_SECRET_KEY_FILE:-/data/app-secret-key}"
    APP_SECRET_KEY_DIR="$(dirname "$APP_SECRET_KEY_FILE")"
    mkdir -p "$APP_SECRET_KEY_DIR"
    if [ ! -s "$APP_SECRET_KEY_FILE" ]; then
        APP_SECRET_KEY_TMP="${APP_SECRET_KEY_FILE}.tmp"
        (umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(64))' > "$APP_SECRET_KEY_TMP")
        mv "$APP_SECRET_KEY_TMP" "$APP_SECRET_KEY_FILE"
    fi
    chmod 600 "$APP_SECRET_KEY_FILE"
    APP_SECRET_KEY="$(cat "$APP_SECRET_KEY_FILE")"
    export APP_SECRET_KEY
fi

# Keep persistent job data writable by Gunicorn without giving the web app root.
# Copy existing files once when moving the volume into its app-owned directory.
APP_UID="${APP_UID:-1026}"
APP_GID="${APP_GID:-100}"
case "${APP_UID}:${APP_GID}" in
    *[!0-9:]*|:*)
        echo "APP_UID and APP_GID must be numeric." >&2
        exit 1
        ;;
esac
if [ "$APP_UID" = "0" ]; then
    echo "APP_UID must not be root." >&2
    exit 1
fi

TAGGER_DB_PATH="${TAGGER_DB_PATH:-/data/app/photo-tagger.sqlite3}"
NAS_SCHEDULE_CREDENTIALS_PATH="${NAS_SCHEDULE_CREDENTIALS_PATH:-/data/app/nas-schedule-credentials.enc}"
APP_DATA_DIR="${APP_DATA_DIR:-/data/app}"
mkdir -p "$APP_DATA_DIR" "$(dirname "$TAGGER_DB_PATH")" "$(dirname "$NAS_SCHEDULE_CREDENTIALS_PATH")"

LEGACY_DB_PATH="/data/photo-tagger.sqlite3"
if [ "$TAGGER_DB_PATH" != "$LEGACY_DB_PATH" ] && [ -f "$LEGACY_DB_PATH" ] && [ ! -e "$TAGGER_DB_PATH" ]; then
    for suffix in "" "-wal" "-shm"; do
        if [ -f "${LEGACY_DB_PATH}${suffix}" ]; then
            cp -p "${LEGACY_DB_PATH}${suffix}" "${TAGGER_DB_PATH}${suffix}"
        fi
    done
fi
LEGACY_SCHEDULE_CREDENTIALS="/data/nas-schedule-credentials.enc"
if [ "$NAS_SCHEDULE_CREDENTIALS_PATH" != "$LEGACY_SCHEDULE_CREDENTIALS" ] \
    && [ -f "$LEGACY_SCHEDULE_CREDENTIALS" ] \
    && [ ! -e "$NAS_SCHEDULE_CREDENTIALS_PATH" ]; then
    cp -p "$LEGACY_SCHEDULE_CREDENTIALS" "$NAS_SCHEDULE_CREDENTIALS_PATH"
fi

chown -R "$APP_UID:$APP_GID" "$APP_DATA_DIR"
chmod 700 "$APP_DATA_DIR"
for writable_file in "$TAGGER_DB_PATH" "${TAGGER_DB_PATH}-wal" "${TAGGER_DB_PATH}-shm" "$NAS_SCHEDULE_CREDENTIALS_PATH"; do
    if [ -e "$writable_file" ]; then
        chown "$APP_UID:$APP_GID" "$writable_file"
    fi
done

# Read secret mounts as root, then pass only the MLX and schedule keys to the
# web process. The Tailscale auth key is removed before Gunicorn starts.
MLX_SERVER_API_KEY_FILE="${MLX_SERVER_API_KEY_FILE:-/run/secrets/mlx-server-api-key}"
if [ -z "${MLX_SERVER_API_KEY:-}" ] && [ -s "$MLX_SERVER_API_KEY_FILE" ]; then
    MLX_SERVER_API_KEY="$(cat "$MLX_SERVER_API_KEY_FILE")"
fi
if [ -z "${MLX_SERVER_API_KEY:-}" ]; then
    MLX_SERVER_API_KEY="${MLX_SERVER_API_KEY_LEGACY:-}"
fi
if [ -n "${MLX_SERVER_API_KEY:-}" ]; then
    export MLX_SERVER_API_KEY
fi

NAS_SCHEDULE_KEY_FILE="${NAS_SCHEDULE_KEY_FILE:-/run/secrets/nas-schedule-key}"
if [ -z "${NAS_SCHEDULE_KEY:-}" ] && [ -s "$NAS_SCHEDULE_KEY_FILE" ]; then
    NAS_SCHEDULE_KEY="$(cat "$NAS_SCHEDULE_KEY_FILE")"
    export NAS_SCHEDULE_KEY
fi

TAILSCALE_AUTHKEY_FILE="${TAILSCALE_AUTHKEY_FILE:-/run/secrets/tailscale-authkey}"
if [ -z "${TAILSCALE_AUTHKEY:-}" ] && [ -s "$TAILSCALE_AUTHKEY_FILE" ]; then
    TAILSCALE_AUTHKEY="$(cat "$TAILSCALE_AUTHKEY_FILE")"
fi
if [ -z "${TAILSCALE_AUTHKEY:-}" ]; then
    TAILSCALE_AUTHKEY="${TAILSCALE_AUTHKEY_LEGACY:-}"
fi

# Run a dedicated Tailscale node in userspace mode. The HTTP proxy is used only
# by the MLX request, so Synology API traffic keeps its normal network route.
mkdir -p /var/run/tailscale /var/lib/tailscale
tailscaled \
    --tun=userspace-networking \
    --outbound-http-proxy-listen=127.0.0.1:1055 \
    --state=/var/lib/tailscale/tailscaled.state \
    --socket=/var/run/tailscale/tailscaled.sock \
    >/var/log/tailscaled.log 2>&1 &
TAILSCALED_PID=$!

TAILSCALE_READY=false
for _ in $(seq 1 30); do
    if tailscale --socket=/var/run/tailscale/tailscaled.sock status >/dev/null 2>&1; then
        TAILSCALE_READY=true
        break
    fi
    if ! kill -0 "$TAILSCALED_PID" 2>/dev/null; then
        break
    fi
    sleep 1
done

if [ "$TAILSCALE_READY" = "true" ]; then
    TAILSCALE_SOCKET="/var/run/tailscale/tailscaled.sock"
    TAILSCALE_IP="$(tailscale --socket="$TAILSCALE_SOCKET" ip -4 2>/dev/null || true)"
    if [ -n "$TAILSCALE_IP" ]; then
        tailscale --socket="$TAILSCALE_SOCKET" set \
            --hostname="${TAILSCALE_HOSTNAME:-synology-photo-tagger}" \
            --accept-dns=true
        echo "Tailscale is connected."
    elif [ -n "${TAILSCALE_AUTHKEY:-}" ]; then
        tailscale --socket="$TAILSCALE_SOCKET" up \
            --authkey="$TAILSCALE_AUTHKEY" \
            --hostname="${TAILSCALE_HOSTNAME:-synology-photo-tagger}" \
            --accept-dns=true
        echo "Tailscale is connected."
    else
        echo "Warning: TAILSCALE_AUTHKEY is not set and this container has no saved Tailscale login."
    fi
else
    if [ -n "${TAILSCALE_AUTHKEY:-}" ]; then
        echo "Error: tailscaled did not become ready; inspect /var/log/tailscaled.log." >&2
        exit 1
    fi
    echo "Warning: Tailscale is unavailable; continuing without tailnet access."
fi

# The auth key is only needed to join a fresh Tailscale state. Do not pass it
# to the long-running web application process.
unset TAILSCALE_AUTHKEY TAILSCALE_AUTHKEY_LEGACY

if [ "${DEBUG_SHELL:-false}" = "true" ]; then
    if [ ! -s /run/ssh/authorized_keys ]; then
        echo "DEBUG_SHELL=true requires a non-empty /run/ssh/authorized_keys file." >&2
        exit 1
    fi
    mkdir -p /run/sshd
    ssh-keygen -A
    /usr/sbin/sshd -t
    /usr/sbin/sshd
fi

if ! setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups test -r /Photos; then
    echo "Gunicorn UID/GID cannot read /Photos; set APP_UID and APP_GID to a NAS account with photo access." >&2
    exit 1
fi

exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups \
    gunicorn --bind "0.0.0.0:${PORT:-5000}" --workers 1 --threads "${GUNICORN_THREADS:-4}" --timeout "${GUNICORN_TIMEOUT:-1020}" app:app
