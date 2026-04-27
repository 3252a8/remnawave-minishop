#!/usr/bin/env bash
set -euo pipefail

ROOT=""

OLD_PREFIX="remnawave-tg-shop"
NEW_PREFIX="remnawave-minishop"
OLD_DB_VOLUME="${OLD_PREFIX}-db-data"
NEW_DB_VOLUME="${NEW_PREFIX}-db-data"
OLD_CADDY_VOLUMES=("${OLD_PREFIX}-caddy-data" "${OLD_PREFIX}-caddy-config")
NEW_CADDY_VOLUMES=("${NEW_PREFIX}-caddy-data" "${NEW_PREFIX}-caddy-config")
KNOWN_CONTAINERS=(
  "${OLD_PREFIX}"
  "${OLD_PREFIX}-db"
  "${OLD_PREFIX}-caddy"
  "${NEW_PREFIX}"
  "${NEW_PREFIX}-db"
  "${NEW_PREFIX}-caddy"
)

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'Ошибка: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Не найдено обязательное средство \`$1\` в PATH."
}

resolve_root() {
  if [[ -n "${PROJECT_ROOT:-}" ]]; then
    [[ -d "$PROJECT_ROOT" ]] || die "PROJECT_ROOT не существует: $PROJECT_ROOT"
    (cd -- "$PROJECT_ROOT" >/dev/null && pwd -P)
    return
  fi

  local git_root
  if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    printf '%s\n' "$git_root"
    return
  fi

  pwd -P
}

run() {
  log "+ $*"
  "$@"
}

container_exists() {
  docker inspect "$1" >/dev/null 2>&1
}

container_running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" == "true" ]]
}

stop_container() {
  local name="$1"

  if ! container_exists "$name"; then
    return 1
  fi

  if container_running "$name"; then
    docker stop "$name" >/dev/null
  fi
  docker rm "$name" >/dev/null
}

volume_exists() {
  docker volume inspect "$1" >/dev/null 2>&1
}

volume_is_empty() {
  docker run --rm -v "$1:/data" alpine sh -c 'test -z "$(find /data -mindepth 1 -print -quit)"' >/dev/null 2>&1
}

copy_volume() {
  local source="$1"
  local target="$2"

  if ! volume_exists "$source"; then
    log "  - Пропускаю том \`$source\`: исходный том не найден."
    return 1
  fi

  if volume_exists "$target" && ! volume_is_empty "$target"; then
    log "  - Пропускаю том \`$target\`: он уже не пустой."
    return 1
  fi

  if ! volume_exists "$target"; then
    die "Целевой том \`$target\` не создан Compose. Сначала нужно подготовить новый стек в режиме \`--no-start\`."
  fi

  docker run --rm -v "$source:/from:ro" -v "$target:/to" alpine sh -c 'cd /from && cp -a . /to/'
}

is_old_postgres_host() {
  grep -Eq "^[[:space:]]*POSTGRES_HOST[[:space:]]*=[[:space:]]*${OLD_PREFIX}-db[[:space:]]*(#.*)?$" "$ROOT/.env"
}

is_new_postgres_host() {
  grep -Eq "^[[:space:]]*POSTGRES_HOST[[:space:]]*=[[:space:]]*${NEW_PREFIX}-db[[:space:]]*(#.*)?$" "$ROOT/.env"
}

update_postgres_host() {
  if is_old_postgres_host; then
    sed -i.bak -E "s|^([[:space:]]*POSTGRES_HOST[[:space:]]*=[[:space:]]*)${OLD_PREFIX}-db([[:space:]]*(#.*)?)$|\\1${NEW_PREFIX}-db\\2|" "$ROOT/.env"
    log "  - \`.env\` обновлён, резервная копия сохранена в \`.env.bak\`."
  elif is_new_postgres_host; then
    log "  - \`POSTGRES_HOST\` уже указывает на новый контейнер, ничего менять не нужно."
  else
    log "  - \`POSTGRES_HOST\` не похож на старую схему, пропускаю изменение."
  fi
}

main() {
  require_cmd git
  require_cmd docker
  docker info >/dev/null

  ROOT="$(resolve_root)"

  local compose_file="${COMPOSE_FILE:-docker-compose.yml}"
  local target_branch="${TARGET_BRANCH:-main}"
  local git_remote="${GIT_REMOTE:-origin}"
  local new_origin_url="${NEW_ORIGIN_URL:-}"
  local assume_yes="${ASSUME_YES:-0}"
  local current_origin
  local current_branch
  local remote_ref
  local head_commit
  local compose_has_build=0
  local compose_has_caddy=0
  local -a compose_cmd
  local -a running_containers=()
  local -a summary=()
  local -a up_args
  local name
  local source
  local target
  local answer

  if [[ $compose_file != /* ]]; then
    compose_file="$ROOT/$compose_file"
  fi
  [[ -f "$compose_file" ]] || die "Compose-файл не найден: $compose_file"
  [[ -e "$ROOT/.git" ]] || die "Скрипт нужно запускать из корня git-репозитория."
  [[ -f "$ROOT/.env" ]] || die "Не найден \`.env\` в корне репозитория."

  if docker compose version >/dev/null 2>&1; then
    compose_cmd=(docker compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    compose_cmd=(docker-compose)
  else
    die "Не найден ни \`docker compose\`, ни \`docker-compose\`."
  fi

  if [[ -n "$(git -C "$ROOT" status --porcelain=v1)" ]]; then
    die "В рабочем дереве есть незакоммиченные изменения. Сначала сохраните их, чтобы миграция не затёрла чужие правки."
  fi

  if grep -Eq '^[[:space:]]*build:[[:space:]]*' "$compose_file"; then
    compose_has_build=1
  fi
  if grep -Eq '^[[:space:]]*caddy:[[:space:]]*$' "$compose_file"; then
    compose_has_caddy=1
  fi

  for name in "${KNOWN_CONTAINERS[@]}"; do
    if container_exists "$name"; then
      running_containers+=("$name")
    fi
  done

  current_origin="$(git -C "$ROOT" remote get-url "$git_remote")"
  if [[ -n "$new_origin_url" && "$current_origin" != "$new_origin_url" ]]; then
    summary+=( "обновить $git_remote с \`$current_origin\` на \`$new_origin_url\`" )
  fi
  summary+=( "скачать ветку \`$target_branch\` из \`$git_remote\`" )
  if volume_exists "$OLD_DB_VOLUME"; then
    summary+=( "проверить том БД \`$OLD_DB_VOLUME\` и перенести в \`$NEW_DB_VOLUME\` при необходимости" )
  fi
  if ((compose_has_caddy)); then
    for i in 0 1; do
      source="${OLD_CADDY_VOLUMES[$i]}"
      target="${NEW_CADDY_VOLUMES[$i]}"
      if volume_exists "$source"; then
        summary+=( "проверить том \`$source\` и перенести в \`$target\` при необходимости" )
      fi
    done
  fi
  if is_old_postgres_host; then
    summary+=( "обновить \`POSTGRES_HOST\` в \`.env\`" )
  fi
  summary+=( "подготовить новый стек через Compose в режиме \`--no-start\`" )
  summary+=( "запустить compose-файл \`$(basename "$compose_file")\`" )

  if [[ "$assume_yes" != "1" ]]; then
    if [[ ! -t 0 ]]; then
      die "Скрипт ожидает интерактивное подтверждение. Запустите с \`ASSUME_YES=1\` для неинтерактивного режима."
    fi
    log "План миграции:"
    for name in "${summary[@]}"; do
      log "  - $name"
    done
    read -r -p "Продолжить? [y/N]: " answer
    case "$answer" in
      y|Y|yes|YES|Yes)
        ;;
      *)
        die "Миграция отменена пользователем."
        ;;
    esac
  fi

  log "1. Останавливаю старый стек"
  if ((${#running_containers[@]})); then
    for name in "${running_containers[@]}"; do
      stop_container "$name"
      log "  - контейнер \`$name\` остановлен/удалён"
    done
  else
    log "  - запущенных контейнеров старой схемы не найдено"
  fi

  if [[ -n "$new_origin_url" && "$current_origin" != "$new_origin_url" ]]; then
    log "2. Обновляю origin"
    run git -C "$ROOT" remote set-url "$git_remote" "$new_origin_url"
  else
    log "2. Origin уже актуален, пропускаю"
  fi

  log "3. Обновляю git до ветки \`$target_branch\`"
  run git -C "$ROOT" fetch "$git_remote" "$target_branch"

  current_branch="$(git -C "$ROOT" branch --show-current || true)"
  if [[ -z "$current_branch" ]]; then
    current_branch="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
  fi

  if [[ "$current_branch" != "$target_branch" ]]; then
    if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$target_branch"; then
      run git -C "$ROOT" switch "$target_branch"
    else
      run git -C "$ROOT" switch -c "$target_branch" --track "$git_remote/$target_branch"
    fi
  else
    log "  - уже на ветке \`$target_branch\`"
  fi

  remote_ref="$(git -C "$ROOT" rev-parse "$git_remote/$target_branch")"
  head_commit="$(git -C "$ROOT" rev-parse HEAD)"
  if [[ "$head_commit" != "$remote_ref" ]]; then
    run git -C "$ROOT" pull --ff-only "$git_remote" "$target_branch"
  else
    log "  - локальная ветка уже совпадает с удалённой, \`git pull\` не нужен"
  fi

  log "4. Обновляю \`.env\`"
  update_postgres_host

  log "5. Подготавливаю новый стек через Compose"
  if ((compose_has_build)); then
    run "${compose_cmd[@]}" -f "$compose_file" up --no-start --build
  else
    run "${compose_cmd[@]}" -f "$compose_file" up --no-start
  fi

  log "6. Переношу тома"
  if copy_volume "$OLD_DB_VOLUME" "$NEW_DB_VOLUME"; then
    log "  - БД перенесена в \`$NEW_DB_VOLUME\`"
  fi
  if ((compose_has_caddy)); then
    for i in 0 1; do
      source="${OLD_CADDY_VOLUMES[$i]}"
      target="${NEW_CADDY_VOLUMES[$i]}"
      if copy_volume "$source" "$target"; then
        log "  - \`$source\` перенесён в \`$target\`"
      fi
    done
  fi

  log "7. Запускаю новый стек"
  if ((compose_has_build)); then
    up_args=(up -d --build --remove-orphans)
  else
    up_args=(up -d --remove-orphans)
  fi
  run "${compose_cmd[@]}" -f "$compose_file" "${up_args[@]}"
  run "${compose_cmd[@]}" -f "$compose_file" ps

  log "Готово."
}

main "$@"
