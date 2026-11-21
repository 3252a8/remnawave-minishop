#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 2 || ${1:-} != /* || ! ${2:-} =~ ^(dev|[a-f0-9]{7,40})$ ]]; then
  echo "Usage: sudo bash install-updater.sh /absolute/path/to/minishop DEV_OR_COMMIT" >&2
  exit 2
fi
if (( EUID != 0 )); then
  echo "Run this installer with sudo." >&2
  exit 1
fi
if [[ ! -f "$1/docker-compose.yml" || ! -f "$1/.env" ]]; then
  echo "Choose a Minishop directory containing docker-compose.yml and .env." >&2
  exit 1
fi

umask 077
exec 9>/run/lock/minishop-updater-install.lock
if ! flock -n 9; then
  echo "Another Minishop updater installation is in progress." >&2
  exit 1
fi
if systemctl is-active --quiet minishop-updater.service; then
  echo "Minishop updater is running. Stop the service before enrolling again." >&2
  exit 1
fi

workdir=$(mktemp -d)
trap 'rm -rf -- "$workdir"' EXIT
archive_url="https://gitlab.com/api/v4/projects/3252a8%2Fremnawave-minishop/repository/archive.tar.gz"
curl -fsSL --proto '=https' --retry 2 -G --data-urlencode "sha=$2" \
  --data-urlencode 'path=deploy/docker' -o "$workdir/source.tar.gz" "$archive_url"
tar -xzf "$workdir/source.tar.gz" -C "$workdir" --wildcards --strip-components=3 -- \
  '*/deploy/docker/core-updater.py' '*/deploy/docker/minishop-updater.service'

/usr/bin/python3 -I "$workdir/core-updater.py" --enroll "$1"
install -m 0755 "$workdir/core-updater.py" /usr/local/sbin/minishop-updater
install -m 0644 "$workdir/minishop-updater.service" /etc/systemd/system/minishop-updater.service
systemctl daemon-reload
systemctl enable --now minishop-updater.service
