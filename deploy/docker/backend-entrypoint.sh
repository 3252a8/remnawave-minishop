#!/bin/sh
# Prepare only the directories owned by the information-page feature before
# dropping privileges.  Existing installations can have these directories in
# their persisted /app/data mount with the UID from an older image; the
# application itself deliberately runs as the unprivileged appuser.
set -eu

for directory in /app/data/legal /app/data/pages /app/data/docs; do
    if [ -L "$directory" ]; then
        echo "refusing symbolic link for information-page storage: $directory" >&2
        exit 1
    fi
    mkdir -p "$directory"
    chown --no-dereference -R appuser:appuser "$directory"
done

export HOME=/home/appuser
export USER=appuser
export LOGNAME=appuser
exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
