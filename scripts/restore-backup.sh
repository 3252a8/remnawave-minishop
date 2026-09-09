#!/usr/bin/env bash
# Run from the installation directory. Extra arguments are Docker Compose options.
set -euo pipefail
if [[ $# -lt 1 ]]; then
    echo 'Usage: bash scripts/restore-backup.sh ARCHIVE.zip [--env-file .env] [-f compose.yml]' >&2
    exit 2
fi
archive=$1
shift
compose=(docker compose "$@")
# Serialize the stop/start lifecycle, including the preflight, on this host.
exec 9>.minishop-restore.lock
flock -n 9 || { echo 'Another restore is running in this directory.' >&2; exit 1; }
"${compose[@]}" run --rm --no-deps backend python -m scripts.restore_backup --check "$archive"
trap 'echo "Restore failed. Check service status and data/backups/restore-*.json before restarting." >&2' ERR
trap '"${compose[@]}" stop --timeout 60 backend worker; exit 130' INT TERM
"${compose[@]}" stop --timeout 60 backend worker migrate
"${compose[@]}" run --rm --no-deps backend python -m scripts.restore_backup "$archive"
if ! "${compose[@]}" up -d --no-deps --wait backend worker; then
    "${compose[@]}" stop --timeout 60 backend worker
    echo 'Database restored, but service healthcheck failed. Services were stopped; inspect logs.' >&2
    exit 1
fi
trap - ERR INT TERM
echo 'Restore completed. The previous database and tariff snapshot are retained for rollback.'
