#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

directory=
channel=
if [[ $# == 2 && "$1" == /* && "$2" == dev ]]; then
  # The original dev dashboard used these two positional arguments.
  directory=$1
  channel=$2
  shift 2
fi
while (($#)); do
  case $1 in
    --directory) directory=${2:?Missing path after --directory} ;;
    --channel) channel=${2:?Missing channel after --channel} ;;
    -h|--help) echo 'Usage: sudo bash install-updater.sh [--channel dev|latest] [--directory PATH]'; exit 0 ;;
    *) fail "Unknown argument: $1" ;;
  esac
  shift 2
done
[[ -z $channel || $channel == dev || $channel == latest ]] || fail 'Use --channel dev or --channel latest.'
(( EUID == 0 )) || fail 'Run this installer with sudo.'
command -v systemctl >/dev/null && [[ -d /run/systemd/system ]] || fail 'A running systemd host is required.'
command -v docker >/dev/null || fail 'A running Minishop Docker deployment is required.'
systemctl is-active --quiet minishop-updater.service &&
  fail 'Minishop updater is already running. Stop it before enrolling again.'

find_python() {
  local interpreter
  for interpreter in /usr/{bin,local/bin}/python3{,.14,.13,.12,.11,.10}; do
    if [[ -x $interpreter ]] && "$interpreter" -I -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
      printf '%s\n' "$interpreter"
      return
    fi
  done
  return 1
}

enrolled_directory=
state=/var/lib/minishop-updater
if [[ -r $state/enrollment.json ]] && python=$(find_python); then
  enrolled_directory=$("$python" -I -c 'import json, sys; print(json.load(sys.stdin)["directory"])' \
    < "$state/enrollment.json") || enrolled_directory=
fi

containers=$(docker ps --no-trunc --filter label=com.docker.compose.service=backend \
  --format '{{.Image}}\t{{.Label "com.docker.compose.project.working_dir"}}\t{{.Label "com.docker.compose.project.config_files"}}')
declare -A deployments=()
while IFS=$'\t' read -r image path config; do
  case ${image%%[@:]*} in
    3252a8/remnawave-minishop-backend|docker.io/3252a8/remnawave-minishop-backend|ghcr.io/3252a8/remnawave-minishop-backend) ;;
    *) continue ;;
  esac
  if [[ $config == "$state/target.json" && -n $enrolled_directory ]]; then
    path=$enrolled_directory
  else
    [[ $config == "$path/docker-compose.yml" ]] || continue
  fi
  [[ $path == /* && -f $path/docker-compose.yml && -f $path/.env ]] || continue
  resolved=$(cd -- "$path" && pwd -P) || continue
  deployments["$resolved"]=$image
done <<<"$containers"

if [[ -n $directory ]]; then
  directory=$(cd -- "$directory" && pwd -P) || fail 'The specified directory does not exist.'
else
  candidate=$(pwd -P)
  while [[ $candidate != / ]]; do
    if [[ -n ${deployments[$candidate]:-} ]]; then
      directory=$candidate
      break
    fi
    candidate=$(dirname -- "$candidate")
  done
  if [[ -z $directory && ${#deployments[@]} == 1 ]]; then
    for directory in "${!deployments[@]}"; do break; done
  fi
fi
[[ -n $directory ]] || fail 'Could not select one running Core Minishop deployment. Open its directory or pass --directory PATH.'
[[ -n ${deployments[$directory]:-} ]] ||
  fail 'The directory must contain .env and the single docker-compose.yml of a running official Core Minishop.'
if [[ -z $channel ]]; then
  channel=latest
  image=${deployments[$directory]}
  if [[ $image == *:dev ]]; then
    channel=dev
  elif [[ $image == *@sha256:* ]]; then
    image_ref=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.ref.name"}}' "$image")
    if [[ $image_ref == dev ]]; then channel=dev; fi
  fi
fi
ref=main
if [[ $channel == dev ]]; then ref=dev; fi

package_manager=
if command -v apt-get >/dev/null; then
  package_manager=apt
elif command -v dnf >/dev/null; then
  package_manager=dnf
fi
packages_refreshed=false
refresh_packages() {
  [[ -n $package_manager ]] || fail 'Install the missing dependencies using your system package manager.'
  if [[ $package_manager == apt && $packages_refreshed == false ]]; then
    apt-get update
    packages_refreshed=true
  fi
}
install_packages() {
  (($#)) || return 0
  refresh_packages
  if [[ $package_manager == apt ]]; then
    apt-get install -y --no-install-recommends "$@"
  else
    dnf install -y "$@"
  fi
}
package_exists() {
  if [[ $package_manager == apt ]]; then
    apt-cache show "$1" >/dev/null 2>&1
  else
    dnf -q list --available "$1" >/dev/null 2>&1
  fi
}

dependencies=()
command -v curl >/dev/null || dependencies+=(curl)
command -v tar >/dev/null || dependencies+=(tar)
command -v gzip >/dev/null || dependencies+=(gzip)
command -v flock >/dev/null || dependencies+=(util-linux)
[[ -s /etc/ssl/certs/ca-certificates.crt || -s /etc/pki/tls/certs/ca-bundle.crt ]] ||
  dependencies+=(ca-certificates)
install_packages "${dependencies[@]}"

if ! python=$(find_python); then
  refresh_packages
  for version in 3.12 3.11 3.10 3.13 3.14; do
    if package_exists "python$version"; then
      install_packages "python$version"
      break
    fi
  done
  python=$(find_python) || fail 'Install Python 3.10 or newer from your distribution and rerun this command.'
fi

compose_ready() {
  local help
  help=$(docker compose up --help 2>/dev/null) && [[ $help == *--wait* ]]
}
if ! compose_ready; then
  refresh_packages
  for package in docker-compose-plugin docker-compose-v2 docker-compose; do
    if package_exists "$package"; then
      install_packages "$package"
      if compose_ready; then break; fi
    fi
  done
  compose_ready || fail 'Docker Compose v2 with the --wait option is required.'
fi

umask 077
exec 9>/run/lock/minishop-updater-install.lock
flock -n 9 || fail 'Another Minishop updater installation is in progress.'
systemctl is-active --quiet minishop-updater.service &&
  fail 'Minishop updater is already running. Stop it before enrolling again.'

workdir=$(mktemp -d)
trap 'rm -rf -- "$workdir"' EXIT
archive_url="https://gitlab.com/api/v4/projects/3252a8%2Fremnawave-minishop/repository/archive.tar.gz"
curl -fsSL --proto '=https' --retry 2 -G --data-urlencode "sha=$ref" \
  --data-urlencode 'path=deploy/docker' -o "$workdir/source.tar.gz" "$archive_url"
tar -xzf "$workdir/source.tar.gz" -C "$workdir" --wildcards --strip-components=3 -- \
  '*/deploy/docker/core-updater.py' '*/deploy/docker/minishop-updater.service'

"$python" -I "$workdir/core-updater.py" --enroll "$directory"
install -m 0755 "$workdir/core-updater.py" /usr/local/sbin/minishop-updater
sed "s|^ExecStart=/usr/bin/python3 |ExecStart=$python |" "$workdir/minishop-updater.service" > "$workdir/updater.service"
install -m 0644 "$workdir/updater.service" /etc/systemd/system/minishop-updater.service
systemctl daemon-reload
systemctl enable --now minishop-updater.service
