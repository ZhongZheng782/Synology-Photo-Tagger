#!/bin/sh
set -eu

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

exec gunicorn --bind "0.0.0.0:${PORT:-5000}" --workers 1 --timeout "${GUNICORN_TIMEOUT:-1020}" app:app
