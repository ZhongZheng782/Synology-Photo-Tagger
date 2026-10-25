#!/bin/sh
set -eu

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
