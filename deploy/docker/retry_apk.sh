#!/bin/sh
set -eu

attempt=1
while [ "$attempt" -le 5 ]; do
    if apk "$@"; then
        exit 0
    else
        apk_exit=$?
    fi
    if [ "$attempt" -eq 5 ]; then
        exit "$apk_exit"
    fi
    echo "apk failed (attempt $attempt/5); retrying" >&2
    sleep "$((attempt * 2))"
    attempt="$((attempt + 1))"
done
