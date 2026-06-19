#!/bin/sh
set -u

# Интерактивный установщик для Docker Compose серверов.

DEFAULT_REPO="${MINISHOP_INSTALL_REPO:-3252a8/remnawave-minishop}"
DEFAULT_REF="${MINISHOP_INSTALL_REF:-main}"
DEFAULT_IMAGE_TAG="${MINISHOP_IMAGE_TAG:-latest}"
DEFAULT_INSTALL_DIR="${MINISHOP_INSTALL_DIR:-/opt/remnawave-minishop}"
DOCS_SETUP_URL="https://minishop.minidoc.cc/getting-started/setup/"
DOCS_REMNASHOP_URL="https://minishop.minidoc.cc/migrations/remnashop/"
INSTALL_STATE_DIR=".installer"
IMPORTER_CACHE_PATH="$INSTALL_STATE_DIR/import_legacy.py"
APP_UID=10001
APP_GID=10001
OLD_TGSHOP_DB_VOLUME="remnawave-tg-shop-db-data"
NEW_MINISHOP_DB_VOLUME="remnawave-minishop-db-data"
OLD_TGSHOP_CADDY_DATA_VOLUME="remnawave-tg-shop-caddy-data"
OLD_TGSHOP_CADDY_CONFIG_VOLUME="remnawave-tg-shop-caddy-config"
NEW_MINISHOP_CADDY_DATA_VOLUME="remnawave-minishop-caddy-data"
NEW_MINISHOP_CADDY_CONFIG_VOLUME="remnawave-minishop-caddy-config"
KNOWN_LEGACY_CONTAINERS="remnawave-tg-shop remnawave-tg-shop-db remnawave-tg-shop-caddy remnawave-minishop remnawave-minishop-db remnawave-minishop-caddy remnawave-minishop-backend remnawave-minishop-worker remnawave-minishop-frontend remnawave-minishop-migrate remnawave-minishop-postgres remnawave-minishop-redis"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RESET="$(printf '\033[0m')"
    BOLD="$(printf '\033[1m')"
    DIM="$(printf '\033[2m')"
    RED="$(printf '\033[31m')"
    GREEN="$(printf '\033[32m')"
    YELLOW="$(printf '\033[33m')"
    BLUE="$(printf '\033[34m')"
    CYAN="$(printf '\033[36m')"
else
    RESET=""
    BOLD=""
    DIM=""
    RED=""
    GREEN=""
    YELLOW=""
    BLUE=""
    CYAN=""
fi

TARGET_DIR=""
SOURCE_REPO="$DEFAULT_REPO"
SOURCE_REF="$DEFAULT_REF"
PROFILE_KEY=""
DEPLOYMENT_PROFILE_VALUE=""
ENV_PATH=""
COMPOSE_STYLE=""
PROMPT_VALUE=""
CHOICE_VALUE=""
LEGACY_SOURCE=""
SOURCE_ENV_PATH=""

COMPOSE_PROJECT_NAME_VALUE=""
IMAGE_TAG_VALUE=""
WEBHOOK_HOST_VALUE=""
MINIAPP_HOST_VALUE=""
WEBHOOK_PUBLIC_URL_VALUE=""
MINIAPP_PUBLIC_URL_VALUE=""
HTTP_BIND_VALUE=""
HTTPS_BIND_VALUE=""
WEB_SERVER_BIND_VALUE=""
FRONTEND_BIND_VALUE=""
PANGOLIN_ENDPOINT_VALUE=""
NEWT_ID_VALUE=""
NEWT_SECRET_VALUE=""
BOT_TOKEN_VALUE=""
ADMIN_IDS_VALUE=""
POSTGRES_USER_VALUE=""
POSTGRES_PASSWORD_VALUE=""
POSTGRES_DB_VALUE=""
WEBAPP_ENABLED_VALUE=""
WEBAPP_TITLE_VALUE=""
WEBAPP_SESSION_SECRET_VALUE=""
WEBHOOK_SECRET_TOKEN_VALUE=""
TRUSTED_PROXIES_VALUE=""
PANEL_API_URL_VALUE=""
PANEL_API_KEY_VALUE=""
PANEL_API_COOKIE_VALUE=""
PANEL_WEBHOOK_SECRET_VALUE=""
TELEGRAM_OAUTH_CLIENT_ID_VALUE=""
TELEGRAM_OAUTH_CLIENT_SECRET_VALUE=""
TELEGRAM_OAUTH_REQUEST_ACCESS_VALUE=""

KNOWN_ENV_KEYS="DEPLOYMENT_PROFILE COMPOSE_PROJECT_NAME IMAGE_TAG WEBHOOK_HOST MINIAPP_HOST WEBHOOK_PUBLIC_URL MINIAPP_PUBLIC_URL HTTP_BIND HTTPS_BIND WEB_SERVER_BIND FRONTEND_BIND PANGOLIN_ENDPOINT NEWT_ID NEWT_SECRET BOT_TOKEN ADMIN_IDS POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB WEBAPP_ENABLED WEBAPP_TITLE WEBAPP_SESSION_SECRET WEBHOOK_SECRET_TOKEN TRUSTED_PROXIES PANEL_API_URL PANEL_API_KEY PANEL_API_COOKIE PANEL_WEBHOOK_SECRET TELEGRAM_OAUTH_CLIENT_ID TELEGRAM_OAUTH_CLIENT_SECRET TELEGRAM_OAUTH_REQUEST_ACCESS"

color() {
    printf '%s%s%s' "$2" "$1" "$RESET"
}

banner() {
    printf '\n'
    color "Мастер установки remnawave-minishop" "$BOLD$CYAN"
    printf '\n'
    color "Установка, настройка, запуск и миграция данных из других ботов." "$DIM"
    printf '\n'
    color "Документация: $DOCS_SETUP_URL" "$DIM"
    printf '\n\n'
}

section() {
    printf '\n'
    color "== $1 ==" "$BOLD$BLUE"
    printf '\n'
}

info() {
    color "* " "$CYAN"
    printf '%s\n' "$1"
}

warn() {
    color "! " "$YELLOW"
    printf '%s\n' "$1"
}

ok() {
    color "[ok] " "$GREEN"
    printf '%s\n' "$1"
}

fail() {
    color "[x] " "$RED"
    printf '%s\n' "$1" >&2
}

pause() {
    printf '%s' "${DIM}Нажмите Enter, чтобы продолжить...${RESET}"
    # shellcheck disable=SC2034
    if ! read -r _; then
        printf '\n'
        return 1
    fi
}

print_help() {
    cat <<EOF
Переменные окружения для значений по умолчанию:
  MINISHOP_INSTALL_DIR      папка установки ($DEFAULT_INSTALL_DIR)
  MINISHOP_INSTALL_REPO     GitHub репозиторий ($DEFAULT_REPO)
  MINISHOP_INSTALL_REF      ветка/тег/ref ($DEFAULT_REF)
  MINISHOP_IMAGE_TAG        тег Docker image ($DEFAULT_IMAGE_TAG)
  REMNASHOP_SOURCE_DSN      DSN базы Remnashop для миграции
  REMNASHOP_SOURCE_ENV_FILE путь к .env Remnashop для переноса настроек
  LEGACY_TGSHOP_SOURCE_DSN  DSN старого remnawave-tg-shop для dump/restore

Мастер интерактивный: он не перезаписывает файлы без подтверждения.
Импорт из Remnashop всегда сначала запускается в dry-run режиме.
Документация по установке: $DOCS_SETUP_URL
Документация по миграции из Remnashop: $DOCS_REMNASHOP_URL
EOF
}

mask_secret() {
    value="${1:-}"
    length=${#value}
    if [ "$length" -eq 0 ]; then
        printf ''
    elif [ "$length" -le 8 ]; then
        printf '****'
    else
        first=$(printf '%s' "$value" | cut -c 1-3)
        last=$(printf '%s' "$value" | awk '{ print substr($0, length($0)-2) }')
        printf '%s...%s' "$first" "$last"
    fi
}

is_secret_key() {
    case "$1" in
        BOT_TOKEN|POSTGRES_PASSWORD|WEBAPP_SESSION_SECRET|WEBHOOK_SECRET_TOKEN|PANEL_API_KEY|PANEL_API_COOKIE|PANEL_WEBHOOK_SECRET|TELEGRAM_OAUTH_CLIENT_SECRET|NEWT_SECRET)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

validate_value() {
    value="$1"
    validator="$2"
    case "$validator" in
        "")
            return 0
            ;;
        hostname)
            printf '%s' "$value" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9.-]{0,251}[A-Za-z0-9]$'
            ;;
        url)
            printf '%s' "$value" | grep -Eq '^https?://[^[:space:]]+$'
            ;;
        *)
            return 0
            ;;
    esac
}

prompt_value() {
    label="$1"
    default_value="${2:-}"
    required="${3:-0}"
    secret="${4:-0}"
    validator="${5:-}"
    prefilled="${6:-0}"
    while :; do
        if [ "$prefilled" = "1" ] && [ -n "$default_value" ]; then
            if [ "$secret" = "1" ]; then
                shown=$(mask_secret "$default_value")
            else
                shown="$default_value"
            fi
            printf '%s: %s\n' "$label" "$shown"
            printf 'Новое значение (Enter = оставить): '
        elif [ -n "$default_value" ]; then
            if [ "$secret" = "1" ]; then
                shown=$(mask_secret "$default_value")
            else
                shown="$default_value"
            fi
            printf '%s [%s]: ' "$label" "$shown"
        else
            printf '%s: ' "$label"
        fi
        if ! read -r raw_value; then
            if [ "$required" = "1" ] && [ -z "$default_value" ]; then
                fail "Ввод завершился во время чтения обязательного значения: $label"
                return 1
            fi
            raw_value=""
        fi
        if [ -n "$raw_value" ]; then
            value="$raw_value"
        else
            value="$default_value"
        fi
        if [ "$required" = "1" ] && [ -z "$value" ]; then
            warn "Это обязательное значение."
            continue
        fi
        if [ -n "$value" ] && ! validate_value "$value" "$validator"; then
            warn "Значение выглядит некорректным."
            continue
        fi
        PROMPT_VALUE="$value"
        return 0
    done
}

confirm() {
    label="$1"
    default="${2:-0}"
    if [ "$default" = "1" ]; then
        suffix="Да/нет"
    else
        suffix="да/Нет"
    fi
    while :; do
        printf '%s [%s]: ' "$label" "$suffix"
        if ! read -r answer; then
            printf '\n'
            [ "$default" = "1" ]
            return $?
        fi
        answer=$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')
        if [ -z "$answer" ]; then
            [ "$default" = "1" ]
            return $?
        fi
        case "$answer" in
            y|yes|д|да)
                return 0
                ;;
            n|no|н|нет)
                return 1
                ;;
            *)
                warn "Ответьте y/n или да/нет."
                ;;
        esac
    done
}

choose() {
    title="$1"
    default="$2"
    valid="$3"
    shift 3
    section "$title"
    for label in "$@"; do
        printf '  %s\n' "$label"
    done
    while :; do
        printf 'Выберите пункт [%s]: ' "$default"
        if ! read -r selected; then
            printf '\n'
            fail "Ввод завершился во время выбора пункта: $title"
            return 1
        fi
        selected="${selected:-$default}"
        case "|$valid|" in
            *"|$selected|"*)
                CHOICE_VALUE="$selected"
                return 0
                ;;
            *)
                warn "Неизвестный пункт меню."
                ;;
        esac
    done
}

strip_quotes() {
    value="$1"
    case "$value" in
        \"*\")
            value=${value#\"}
            value=${value%\"}
            ;;
        \'*\')
            value=${value#\'}
            value=${value%\'}
            ;;
    esac
    printf '%s' "$value"
}

env_get() {
    key="$1"
    default_value="${2:-}"
    if [ -f "$ENV_PATH" ]; then
        line=$(grep -E "^${key}=" "$ENV_PATH" 2>/dev/null | tail -n 1 || true)
        if [ -n "$line" ]; then
            strip_quotes "${line#*=}"
            return 0
        fi
    fi
    printf '%s' "$default_value"
}

known_env_key() {
    case " $KNOWN_ENV_KEYS " in
        *" $1 "*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

secret_hex() {
    bytes="${1:-32}"
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex "$bytes"
        return 0
    fi
    if [ -r /dev/urandom ] && command -v od >/dev/null 2>&1; then
        dd if=/dev/urandom bs="$bytes" count=1 2>/dev/null | od -An -tx1 | tr -d ' \n'
        return 0
    fi
    fail "Не удалось сгенерировать безопасный secret. Установите openssl и повторите."
    exit 1
}

generated_password() {
    secret_hex 24
}

raw_url() {
    repo=$(printf '%s' "$1" | sed 's#^/*##; s#/*$##')
    ref=$(printf '%s' "$2" | sed 's#^/*##; s#/*$##')
    path=$(printf '%s' "$3" | sed 's#^/*##')
    printf 'https://raw.githubusercontent.com/%s/%s/%s' "$repo" "$ref" "$path"
}

download_to() {
    download_url="$1"
    download_target="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$download_url" -o "$download_target"
        return $?
    fi
    if command -v wget >/dev/null 2>&1; then
        wget -qO "$download_target" "$download_url"
        return $?
    fi
    fail "Для скачивания файлов нужен curl или wget."
    exit 1
}

backup_path() {
    path="$1"
    stamp=$(date -u '+%Y%m%d-%H%M%S')
    printf '%s.bak-%s' "$path" "$stamp"
}

first_existing_file() {
    for path in "$@"; do
        if [ -f "$path" ]; then
            printf '%s' "$path"
            return 0
        fi
    done
    return 1
}

docker_container_exists() {
    command -v docker >/dev/null 2>&1 || return 1
    docker inspect --type container "$1" >/dev/null 2>&1
}

detect_egames_nginx_conf() {
    if [ -n "${EGAMES_NGINX_CONF:-}" ] && [ -f "$EGAMES_NGINX_CONF" ]; then
        printf '%s' "$EGAMES_NGINX_CONF"
        return 0
    fi
    first_existing_file \
        /opt/remnawave/nginx.conf \
        /opt/remnawave-reverse-proxy/nginx.conf \
        /opt/remnawave/nginx/nginx.conf \
        2>/dev/null && return 0
    find /opt -maxdepth 4 -type f -name nginx.conf -path '*remnawave*' 2>/dev/null | head -n 1
}

detect_egames_panel_env() {
    if [ -n "${EGAMES_REMNAWAVE_ENV:-}" ] && [ -f "$EGAMES_REMNAWAVE_ENV" ]; then
        printf '%s' "$EGAMES_REMNAWAVE_ENV"
        return 0
    fi
    first_existing_file \
        /opt/remnawave/.env \
        /opt/remnawave-reverse-proxy/.env \
        2>/dev/null && return 0
    find /opt -maxdepth 4 -type f -name .env -path '*remnawave*' 2>/dev/null | head -n 1
}

detect_egames_nginx_container() {
    if [ -n "${EGAMES_NGINX_CONTAINER:-}" ] && docker_container_exists "$EGAMES_NGINX_CONTAINER"; then
        printf '%s' "$EGAMES_NGINX_CONTAINER"
        return 0
    fi
    if docker_container_exists remnawave-nginx; then
        printf '%s' remnawave-nginx
        return 0
    fi
    command -v docker >/dev/null 2>&1 || return 1
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -Ei 'remnawave.*nginx|nginx.*remnawave' | head -n 1
}

detect_egames_stack() {
    nginx_conf=$(detect_egames_nginx_conf || true)
    nginx_container=$(detect_egames_nginx_container || true)
    [ -n "$nginx_conf" ] && [ -n "$nginx_container" ]
}

detect_remnawave_db_container() {
    if [ -n "${EGAMES_REMNAWAVE_DB_CONTAINER:-}" ] && docker_container_exists "$EGAMES_REMNAWAVE_DB_CONTAINER"; then
        printf '%s' "$EGAMES_REMNAWAVE_DB_CONTAINER"
        return 0
    fi
    if docker_container_exists remnawave-db; then
        printf '%s' remnawave-db
        return 0
    fi
    command -v docker >/dev/null 2>&1 || return 1
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -Ei 'remnawave.*(db|postgres)|postgres.*remnawave' | head -n 1
}

detect_remnashop_env_file() {
    if [ -n "${REMNASHOP_SOURCE_ENV_FILE:-}" ] && [ -f "$REMNASHOP_SOURCE_ENV_FILE" ]; then
        printf '%s' "$REMNASHOP_SOURCE_ENV_FILE"
        return 0
    fi
    first_existing_file \
        /opt/remnashop/.env \
        /opt/remnashop/.env.prod \
        /opt/remnashop/.env.production \
        2>/dev/null && return 0
    find /opt -maxdepth 4 -type f -name .env -path '*remnashop*' 2>/dev/null | head -n 1
}

detect_remnashop_db_container() {
    if [ -n "${REMNASHOP_DB_CONTAINER:-}" ] && docker_container_exists "$REMNASHOP_DB_CONTAINER"; then
        printf '%s' "$REMNASHOP_DB_CONTAINER"
        return 0
    fi
    if docker_container_exists remnashop-db; then
        printf '%s' remnashop-db
        return 0
    fi
    command -v docker >/dev/null 2>&1 || return 1
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -Ei 'remnashop.*(db|postgres)|postgres.*remnashop' | head -n 1
}

detect_remnashop_source_dsn() {
    if [ -n "${REMNASHOP_SOURCE_DSN:-}" ]; then
        printf '%s' "$REMNASHOP_SOURCE_DSN"
        return 0
    fi
    container=$(detect_remnashop_db_container || true)
    [ -n "$container" ] || return 1
    docker exec "$container" sh -lc 'printf "postgresql://%s:%s@'"$container"':5432/%s" "$POSTGRES_USER" "$POSTGRES_PASSWORD" "$POSTGRES_DB"' 2>/dev/null
}

detect_remnashop_stack() {
    env_file=$(detect_remnashop_env_file || true)
    db_container=$(detect_remnashop_db_container || true)
    [ -n "$env_file" ] || [ -n "$db_container" ]
}

detect_remnashop_env_value() {
    key="$1"
    env_file=$(detect_remnashop_env_file || true)
    [ -n "$env_file" ] && [ -f "$env_file" ] || return 1
    env_file_get "$key" "$env_file"
}

detect_bot_token() {
    detect_remnashop_env_value BOT_TOKEN
}

detect_admin_ids() {
    value=$(detect_remnashop_env_value BOT_OWNER_ID || true)
    [ -n "$value" ] || value=$(detect_remnashop_env_value ADMIN_IDS || true)
    [ -n "$value" ] || return 1
    printf '%s' "$value" | tr ';' ','
}

detect_webhook_secret_token() {
    detect_remnashop_env_value BOT_SECRET_TOKEN
}

normalize_panel_api_url() {
    value="$1"
    [ -n "$value" ] || return 1
    case "$value" in
        http://*|https://*)
            base="$value"
            ;;
        *)
            base="https://$value"
            ;;
    esac
    base=$(printf '%s' "$base" | sed 's:/*$::')
    case "$base" in
        */api)
            printf '%s' "$base"
            ;;
        *)
            printf '%s/api' "$base"
            ;;
    esac
}

detect_panel_api_url() {
    value=$(detect_remnashop_env_value REMNAWAVE_HOST || true)
    if [ -n "$value" ]; then
        normalize_panel_api_url "$value"
        return 0
    fi

    panel_env=$(detect_egames_panel_env || true)
    if [ -n "$panel_env" ] && [ -f "$panel_env" ]; then
        value=$(env_file_get REMNAWAVE_PANEL_URL "$panel_env")
        [ -n "$value" ] || value=$(env_file_get FRONT_END_DOMAIN "$panel_env")
        if [ -n "$value" ]; then
            normalize_panel_api_url "$value"
            return 0
        fi
    fi
    return 1
}

detect_panel_api_key() {
    value=$(detect_remnashop_env_value REMNAWAVE_TOKEN || true)
    if [ -n "$value" ]; then
        printf '%s' "$value"
        return 0
    fi

    container=$(detect_remnawave_db_container || true)
    [ -n "$container" ] || return 1
    docker exec "$container" sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select token from api_tokens order by created_at desc limit 1;"' 2>/dev/null
}

detect_panel_api_cookie() {
    env_cookie=$(detect_remnashop_env_value REMNAWAVE_COOKIE || true)
    case "$env_cookie" in
        *=*)
            printf '%s' "$env_cookie"
            return 0
            ;;
    esac

    nginx_conf=$(detect_egames_nginx_conf || true)
    [ -n "$nginx_conf" ] && [ -f "$nginx_conf" ] || return 1
    if [ -n "$env_cookie" ]; then
        cookie=$(sed -n "s/.*\\($env_cookie=[^\"; ]*\\).*/\\1/p" "$nginx_conf" | head -n 1)
        if [ -n "$cookie" ]; then
            printf '%s' "$cookie"
            return 0
        fi
    fi
    sed -n 's/.*"~\*\([^"]*=[^"]*\)".*/\1/p' "$nginx_conf" | head -n 1
}

detect_panel_webhook_secret() {
    value=$(detect_remnashop_env_value REMNAWAVE_WEBHOOK_SECRET || true)
    if [ -n "$value" ]; then
        printf '%s' "$value"
        return 0
    fi

    panel_env=$(detect_egames_panel_env || true)
    [ -n "$panel_env" ] && [ -f "$panel_env" ] || return 1
    env_file_get WEBHOOK_SECRET_HEADER "$panel_env"
}

write_downloaded_file() {
    source_path="$1"
    target_path="$2"
    mkdir -p "$(dirname "$target_path")"
    if [ -e "$target_path" ]; then
        if confirm "$target_path уже существует. Перезаписать, предварительно сохранив backup?" 0; then
            backup=$(backup_path "$target_path")
            cp "$target_path" "$backup"
            info "Backup файла $target_path сохранен как $(basename "$backup")"
        else
            warn "Оставляю существующий файл $target_path"
            rm -f "$source_path"
            return 0
        fi
    fi
    mv "$source_path" "$target_path"
    ok "Записан файл $target_path"
}

download_raw_file() {
    source="$1"
    target="$2"
    required="${3:-1}"
    url=$(raw_url "$SOURCE_REPO" "$SOURCE_REF" "$source")
    tmp="$TARGET_DIR/.download.$$.$(basename "$target")"
    if download_to "$url" "$tmp"; then
        write_downloaded_file "$tmp" "$TARGET_DIR/$target"
        return 0
    fi
    rm -f "$tmp"
    if [ "$required" = "1" ]; then
        fail "Не удалось скачать $url"
        return 1
    fi
    warn "Пропускаю необязательный файл $source"
    return 0
}

choose_profile() {
    default_profile="1"
    if detect_egames_stack; then
        default_profile="5"
        info "Найдена установленная Remnawave/eGames связка; по умолчанию предлагаю встроиться в ее Nginx/TLS."
    fi
    info "Подробнее о профилях деплоя: $DOCS_SETUP_URL"
    choose "Профиль деплоя" "$default_profile" "1|2|3|4|5" \
        "1. Caddy HTTPS - отдельный сервер, автоматические сертификаты." \
        "2. Nginx HTTPS - свои сертификаты или помощник Certbot." \
        "3. Pangolin / Newt - без входящих портов, публичные маршруты в Pangolin." \
        "4. Без proxy / внешний TLS - прямые HTTP-порты или свой TLS-терминатор." \
        "5. Уже установленная Remnawave через eGames - использовать ее Nginx/TLS." || return 1
    case "$CHOICE_VALUE" in
        1) PROFILE_KEY="caddy" ;;
        2) PROFILE_KEY="nginx" ;;
        3) PROFILE_KEY="newt" ;;
        4) PROFILE_KEY="no-proxy" ;;
        5) PROFILE_KEY="egames" ;;
    esac
    DEPLOYMENT_PROFILE_VALUE="$PROFILE_KEY"
}

download_profile_files() {
    section "Скачивание файлов деплоя"
    case "$PROFILE_KEY" in
        caddy)
            download_raw_file "deploy/examples/caddy/docker-compose.yml" "docker-compose.yml" 1 || return 1
            download_raw_file "deploy/examples/caddy/Caddyfile" "Caddyfile" 1 || return 1
            download_raw_file "deploy/examples/caddy/.env.example" ".env.example" 1 || return 1
            ;;
        nginx)
            download_raw_file "deploy/examples/nginx/docker-compose.yml" "docker-compose.yml" 1 || return 1
            download_raw_file "deploy/examples/nginx/nginx.conf.template" "nginx.conf.template" 1 || return 1
            download_raw_file "deploy/examples/nginx/.env.example" ".env.example" 1 || return 1
            download_raw_file "deploy/examples/nginx/ssl/README.md" "ssl/README.md" 1 || return 1
            ;;
        newt)
            download_raw_file "deploy/examples/newt/docker-compose.yml" "docker-compose.yml" 1 || return 1
            download_raw_file "deploy/examples/newt/.env.example" ".env.example" 1 || return 1
            ;;
        no-proxy)
            download_raw_file "deploy/examples/no-proxy/docker-compose.yml" "docker-compose.yml" 1 || return 1
            download_raw_file "deploy/examples/no-proxy/.env.example" ".env.example" 1 || return 1
            ;;
        egames)
            download_raw_file "deploy/examples/no-proxy/docker-compose.yml" "docker-compose.yml" 1 || return 1
            download_raw_file "deploy/examples/no-proxy/.env.example" ".env.example" 1 || return 1
            ;;
    esac
}

prompt_common_env() {
    section "Основные настройки .env"
    prompt_value "Имя Docker Compose проекта" "$(env_get COMPOSE_PROJECT_NAME remnawave-minishop)" 0 0 ""
    COMPOSE_PROJECT_NAME_VALUE="$PROMPT_VALUE"
    prompt_value "Тег Docker image" "$(env_get IMAGE_TAG "$DEFAULT_IMAGE_TAG")" 0 0 ""
    IMAGE_TAG_VALUE="$PROMPT_VALUE"
    detected_bot_token=$(env_get BOT_TOKEN "")
    detected_bot_token_prefilled=0
    if [ -n "$detected_bot_token" ]; then
        detected_bot_token_prefilled=1
    else
        detected_bot_token=$(detect_bot_token || true)
        if [ -n "$detected_bot_token" ]; then
            detected_bot_token_prefilled=1
            info "Нашел BOT_TOKEN в .env Remnashop и подставил его по умолчанию."
        fi
    fi
    prompt_value "Токен Telegram бота" "$detected_bot_token" 1 1 "" "$detected_bot_token_prefilled"
    BOT_TOKEN_VALUE="$PROMPT_VALUE"
    detected_admin_ids=$(env_get ADMIN_IDS "")
    detected_admin_ids_prefilled=0
    if [ -n "$detected_admin_ids" ]; then
        detected_admin_ids_prefilled=1
    else
        detected_admin_ids=$(detect_admin_ids || true)
        if [ -n "$detected_admin_ids" ]; then
            detected_admin_ids_prefilled=1
            info "Нашел BOT_OWNER_ID/ADMIN_IDS в .env Remnashop и подставил администраторов по умолчанию."
        fi
    fi
    prompt_value "Telegram ID администраторов через запятую" "$detected_admin_ids" 1 0 "" "$detected_admin_ids_prefilled"
    ADMIN_IDS_VALUE="$PROMPT_VALUE"
    prompt_value "Пользователь PostgreSQL" "$(env_get POSTGRES_USER remnawave_minishop)" 1 0 ""
    POSTGRES_USER_VALUE="$PROMPT_VALUE"
    existing_postgres_password=$(env_get POSTGRES_PASSWORD "")
    if [ -z "$existing_postgres_password" ]; then
        existing_postgres_password=$(generated_password)
    fi
    prompt_value "Пароль PostgreSQL" "$existing_postgres_password" 1 1 ""
    POSTGRES_PASSWORD_VALUE="$PROMPT_VALUE"
    prompt_value "База PostgreSQL" "$(env_get POSTGRES_DB remnawave_minishop)" 1 0 ""
    POSTGRES_DB_VALUE="$PROMPT_VALUE"

    WEBAPP_ENABLED_VALUE="$(env_get WEBAPP_ENABLED True)"
    prompt_value "Название Web App" "$(env_get WEBAPP_TITLE remnawave-minishop)" 0 0 ""
    WEBAPP_TITLE_VALUE="$PROMPT_VALUE"
    WEBAPP_SESSION_SECRET_VALUE="$(env_get WEBAPP_SESSION_SECRET "")"
    if [ -z "$WEBAPP_SESSION_SECRET_VALUE" ]; then
        WEBAPP_SESSION_SECRET_VALUE="$(secret_hex 32)"
    fi
    WEBHOOK_SECRET_TOKEN_VALUE="$(env_get WEBHOOK_SECRET_TOKEN "")"
    if [ -z "$WEBHOOK_SECRET_TOKEN_VALUE" ]; then
        WEBHOOK_SECRET_TOKEN_VALUE="$(detect_webhook_secret_token || true)"
        if [ -n "$WEBHOOK_SECRET_TOKEN_VALUE" ]; then
            info "Нашел BOT_SECRET_TOKEN в .env Remnashop и использую его для WEBHOOK_SECRET_TOKEN."
        fi
    fi
    if [ -z "$WEBHOOK_SECRET_TOKEN_VALUE" ]; then
        WEBHOOK_SECRET_TOKEN_VALUE="$(secret_hex 32)"
    fi

    detected_panel_api_url=$(env_get PANEL_API_URL "")
    detected_panel_api_url_prefilled=0
    if [ -n "$detected_panel_api_url" ]; then
        detected_panel_api_url_prefilled=1
    else
        detected_panel_api_url=$(detect_panel_api_url || true)
        [ -n "$detected_panel_api_url" ] && detected_panel_api_url_prefilled=1
    fi
    [ -n "$detected_panel_api_url" ] || detected_panel_api_url="https://panel.example.com/api"
    if [ "$detected_panel_api_url" != "https://panel.example.com/api" ]; then
        info "Нашел URL API Remnawave Panel и подставил его по умолчанию."
    fi
    prompt_value "URL API Remnawave Panel" "$detected_panel_api_url" 0 0 "url" "$detected_panel_api_url_prefilled"
    PANEL_API_URL_VALUE="$PROMPT_VALUE"
    detected_panel_api_key=$(env_get PANEL_API_KEY "")
    detected_panel_api_key_prefilled=0
    if [ -n "$detected_panel_api_key" ]; then
        detected_panel_api_key_prefilled=1
    else
        detected_panel_api_key=$(detect_panel_api_key || true)
        [ -n "$detected_panel_api_key" ] && detected_panel_api_key_prefilled=1
    fi
    [ -n "$detected_panel_api_key" ] || detected_panel_api_key="change_me"
    if [ "$detected_panel_api_key" != "change_me" ]; then
        info "Нашел API key Remnawave Panel и подставил его по умолчанию."
    fi
    prompt_value "API key Remnawave Panel" "$detected_panel_api_key" 0 1 "" "$detected_panel_api_key_prefilled"
    PANEL_API_KEY_VALUE="$PROMPT_VALUE"
    detected_panel_api_cookie=$(env_get PANEL_API_COOKIE "")
    detected_panel_api_cookie_prefilled=0
    if [ -n "$detected_panel_api_cookie" ]; then
        detected_panel_api_cookie_prefilled=1
    else
        detected_panel_api_cookie=$(detect_panel_api_cookie || true)
        [ -n "$detected_panel_api_cookie" ] && detected_panel_api_cookie_prefilled=1
    fi
    if [ -n "$detected_panel_api_cookie" ]; then
        info "Нашел Cookie header eGames reverse proxy и подставил его по умолчанию."
    fi
    prompt_value "Cookie header reverse proxy Remnawave (если нужен)" "$detected_panel_api_cookie" 0 1 "" "$detected_panel_api_cookie_prefilled"
    PANEL_API_COOKIE_VALUE="$PROMPT_VALUE"
    existing_panel_webhook_secret=$(env_get PANEL_WEBHOOK_SECRET "")
    existing_panel_webhook_secret_prefilled=0
    if [ -n "$existing_panel_webhook_secret" ]; then
        existing_panel_webhook_secret_prefilled=1
    else
        existing_panel_webhook_secret=$(detect_panel_webhook_secret || true)
        [ -n "$existing_panel_webhook_secret" ] && existing_panel_webhook_secret_prefilled=1
    fi
    if [ -n "$existing_panel_webhook_secret" ]; then
        info "Нашел webhook secret Remnawave Panel и подставил его по умолчанию."
    fi
    if [ -z "$existing_panel_webhook_secret" ]; then
        existing_panel_webhook_secret=$(secret_hex 24)
    fi
    prompt_value "Webhook secret Remnawave Panel" "$existing_panel_webhook_secret" 0 1 "" "$existing_panel_webhook_secret_prefilled"
    PANEL_WEBHOOK_SECRET_VALUE="$PROMPT_VALUE"

    prompt_value "Telegram OAuth client ID (пусто = ID бота)" "$(env_get TELEGRAM_OAUTH_CLIENT_ID '')" 0 0 ""
    TELEGRAM_OAUTH_CLIENT_ID_VALUE="$PROMPT_VALUE"
    prompt_value "Telegram OAuth client secret из BotFather Web Login (пусто = пропустить browser OAuth)" "$(env_get TELEGRAM_OAUTH_CLIENT_SECRET '')" 0 1 ""
    TELEGRAM_OAUTH_CLIENT_SECRET_VALUE="$PROMPT_VALUE"
    prompt_value "Telegram OAuth request access (пусто/write/phone)" "$(env_get TELEGRAM_OAUTH_REQUEST_ACCESS '')" 0 0 ""
    TELEGRAM_OAUTH_REQUEST_ACCESS_VALUE="$PROMPT_VALUE"

    case "$PROFILE_KEY" in
        caddy|nginx|newt|egames)
            prompt_value "Публичный hostname для API/webhook бота" "$(env_get WEBHOOK_HOST webhooks.example.com)" 1 0 "hostname"
            WEBHOOK_HOST_VALUE="$PROMPT_VALUE"
            prompt_value "Публичный hostname для Mini App" "$(env_get MINIAPP_HOST app.example.com)" 1 0 "hostname"
            MINIAPP_HOST_VALUE="$PROMPT_VALUE"
            TRUSTED_PROXIES_VALUE="$(env_get TRUSTED_PROXIES '127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7')"
            ;;
    esac

    case "$PROFILE_KEY" in
        caddy|nginx)
            prompt_value "Адрес привязки HTTP" "$(env_get HTTP_BIND '0.0.0.0:80')" 0 0 ""
            HTTP_BIND_VALUE="$PROMPT_VALUE"
            prompt_value "Адрес привязки HTTPS" "$(env_get HTTPS_BIND '0.0.0.0:443')" 0 0 ""
            HTTPS_BIND_VALUE="$PROMPT_VALUE"
            ;;
        newt)
            prompt_value "Endpoint Pangolin" "$(env_get PANGOLIN_ENDPOINT https://pangolin.example.com)" 1 0 "url"
            PANGOLIN_ENDPOINT_VALUE="$PROMPT_VALUE"
            prompt_value "Newt ID" "$(env_get NEWT_ID '')" 1 0 ""
            NEWT_ID_VALUE="$PROMPT_VALUE"
            prompt_value "Newt secret" "$(env_get NEWT_SECRET '')" 1 1 ""
            NEWT_SECRET_VALUE="$PROMPT_VALUE"
            ;;
        no-proxy)
            prompt_value "Адрес привязки backend" "$(env_get WEB_SERVER_BIND '0.0.0.0:8080')" 0 0 ""
            WEB_SERVER_BIND_VALUE="$PROMPT_VALUE"
            prompt_value "Адрес привязки frontend" "$(env_get FRONTEND_BIND '0.0.0.0:8082')" 0 0 ""
            FRONTEND_BIND_VALUE="$PROMPT_VALUE"
            prompt_value "Публичный URL webhook/API" "$(env_get WEBHOOK_PUBLIC_URL 'http://127.0.0.1:8080')" 1 0 "url"
            WEBHOOK_PUBLIC_URL_VALUE="$PROMPT_VALUE"
            prompt_value "Публичный URL Mini App" "$(env_get MINIAPP_PUBLIC_URL 'http://127.0.0.1:8082/')" 1 0 "url"
            MINIAPP_PUBLIC_URL_VALUE="$PROMPT_VALUE"
            TRUSTED_PROXIES_VALUE="$(env_get TRUSTED_PROXIES '127.0.0.1,::1')"
            ;;
        egames)
            prompt_value "Адрес привязки backend для eGames Nginx" "$(env_get WEB_SERVER_BIND '127.0.0.1:8080')" 0 0 ""
            WEB_SERVER_BIND_VALUE="$PROMPT_VALUE"
            prompt_value "Адрес привязки frontend для eGames Nginx" "$(env_get FRONTEND_BIND '127.0.0.1:8082')" 0 0 ""
            FRONTEND_BIND_VALUE="$PROMPT_VALUE"
            WEBHOOK_PUBLIC_URL_VALUE="$(env_get WEBHOOK_PUBLIC_URL "https://$WEBHOOK_HOST_VALUE")"
            MINIAPP_PUBLIC_URL_VALUE="$(env_get MINIAPP_PUBLIC_URL "https://$MINIAPP_HOST_VALUE/")"
            ;;
    esac
}

env_line() {
    key="$1"
    value="$2"
    file="$3"
    if [ -n "$value" ]; then
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

show_env_value() {
    key="$1"
    value="$2"
    if [ -z "$value" ]; then
        return 0
    fi
    if is_secret_key "$key"; then
        value=$(mask_secret "$value")
    fi
    printf '  %s=%s\n' "$key" "$value"
}

display_env_summary() {
    show_env_value COMPOSE_PROJECT_NAME "$COMPOSE_PROJECT_NAME_VALUE"
    show_env_value DEPLOYMENT_PROFILE "$DEPLOYMENT_PROFILE_VALUE"
    show_env_value IMAGE_TAG "$IMAGE_TAG_VALUE"
    show_env_value WEBHOOK_HOST "$WEBHOOK_HOST_VALUE"
    show_env_value MINIAPP_HOST "$MINIAPP_HOST_VALUE"
    show_env_value WEBHOOK_PUBLIC_URL "$WEBHOOK_PUBLIC_URL_VALUE"
    show_env_value MINIAPP_PUBLIC_URL "$MINIAPP_PUBLIC_URL_VALUE"
    show_env_value WEB_SERVER_BIND "$WEB_SERVER_BIND_VALUE"
    show_env_value FRONTEND_BIND "$FRONTEND_BIND_VALUE"
    show_env_value BOT_TOKEN "$BOT_TOKEN_VALUE"
    show_env_value ADMIN_IDS "$ADMIN_IDS_VALUE"
    show_env_value POSTGRES_USER "$POSTGRES_USER_VALUE"
    show_env_value POSTGRES_PASSWORD "$POSTGRES_PASSWORD_VALUE"
    show_env_value POSTGRES_DB "$POSTGRES_DB_VALUE"
    show_env_value WEBAPP_TITLE "$WEBAPP_TITLE_VALUE"
    show_env_value WEBAPP_SESSION_SECRET "$WEBAPP_SESSION_SECRET_VALUE"
    show_env_value WEBHOOK_SECRET_TOKEN "$WEBHOOK_SECRET_TOKEN_VALUE"
    show_env_value PANEL_API_URL "$PANEL_API_URL_VALUE"
    show_env_value PANEL_API_KEY "$PANEL_API_KEY_VALUE"
    show_env_value PANEL_API_COOKIE "$PANEL_API_COOKIE_VALUE"
    show_env_value PANEL_WEBHOOK_SECRET "$PANEL_WEBHOOK_SECRET_VALUE"
    show_env_value TELEGRAM_OAUTH_CLIENT_ID "$TELEGRAM_OAUTH_CLIENT_ID_VALUE"
    show_env_value TELEGRAM_OAUTH_CLIENT_SECRET "$TELEGRAM_OAUTH_CLIENT_SECRET_VALUE"
    show_env_value TELEGRAM_OAUTH_REQUEST_ACCESS "$TELEGRAM_OAUTH_REQUEST_ACCESS_VALUE"
}

append_preserved_env() {
    output="$1"
    [ -f "$ENV_PATH" ] || return 0
    wrote_header=0
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ""|\#*)
                continue
                ;;
            *=*)
                key=${line%%=*}
                if known_env_key "$key"; then
                    continue
                fi
                if [ "$wrote_header" = "0" ]; then
                    printf '\n# Preserved from previous .env\n' >> "$output"
                    wrote_header=1
                fi
                printf '%s\n' "$line" >> "$output"
                ;;
        esac
    done < "$ENV_PATH"
}

render_env_file() {
    output="$1"
    : > "$output"
    printf '# Deployment\n' >> "$output"
    env_line COMPOSE_PROJECT_NAME "$COMPOSE_PROJECT_NAME_VALUE" "$output"
    env_line DEPLOYMENT_PROFILE "$DEPLOYMENT_PROFILE_VALUE" "$output"
    env_line IMAGE_TAG "$IMAGE_TAG_VALUE" "$output"
    env_line WEBHOOK_HOST "$WEBHOOK_HOST_VALUE" "$output"
    env_line MINIAPP_HOST "$MINIAPP_HOST_VALUE" "$output"
    env_line WEBHOOK_PUBLIC_URL "$WEBHOOK_PUBLIC_URL_VALUE" "$output"
    env_line MINIAPP_PUBLIC_URL "$MINIAPP_PUBLIC_URL_VALUE" "$output"
    env_line HTTP_BIND "$HTTP_BIND_VALUE" "$output"
    env_line HTTPS_BIND "$HTTPS_BIND_VALUE" "$output"
    env_line WEB_SERVER_BIND "$WEB_SERVER_BIND_VALUE" "$output"
    env_line FRONTEND_BIND "$FRONTEND_BIND_VALUE" "$output"
    env_line PANGOLIN_ENDPOINT "$PANGOLIN_ENDPOINT_VALUE" "$output"
    env_line NEWT_ID "$NEWT_ID_VALUE" "$output"
    env_line NEWT_SECRET "$NEWT_SECRET_VALUE" "$output"

    printf '\n# Telegram\n' >> "$output"
    env_line BOT_TOKEN "$BOT_TOKEN_VALUE" "$output"
    env_line ADMIN_IDS "$ADMIN_IDS_VALUE" "$output"

    printf '\n# PostgreSQL\n' >> "$output"
    env_line POSTGRES_USER "$POSTGRES_USER_VALUE" "$output"
    env_line POSTGRES_PASSWORD "$POSTGRES_PASSWORD_VALUE" "$output"
    env_line POSTGRES_DB "$POSTGRES_DB_VALUE" "$output"

    printf '\n# Application\n' >> "$output"
    env_line WEBAPP_ENABLED "$WEBAPP_ENABLED_VALUE" "$output"
    env_line WEBAPP_TITLE "$WEBAPP_TITLE_VALUE" "$output"
    env_line WEBAPP_SESSION_SECRET "$WEBAPP_SESSION_SECRET_VALUE" "$output"
    env_line WEBHOOK_SECRET_TOKEN "$WEBHOOK_SECRET_TOKEN_VALUE" "$output"
    env_line TRUSTED_PROXIES "$TRUSTED_PROXIES_VALUE" "$output"

    printf '\n# Remnawave Panel\n' >> "$output"
    env_line PANEL_API_URL "$PANEL_API_URL_VALUE" "$output"
    env_line PANEL_API_KEY "$PANEL_API_KEY_VALUE" "$output"
    env_line PANEL_API_COOKIE "$PANEL_API_COOKIE_VALUE" "$output"
    env_line PANEL_WEBHOOK_SECRET "$PANEL_WEBHOOK_SECRET_VALUE" "$output"

    printf '\n# Telegram OAuth / OpenID Connect\n' >> "$output"
    env_line TELEGRAM_OAUTH_CLIENT_ID "$TELEGRAM_OAUTH_CLIENT_ID_VALUE" "$output"
    env_line TELEGRAM_OAUTH_CLIENT_SECRET "$TELEGRAM_OAUTH_CLIENT_SECRET_VALUE" "$output"
    env_line TELEGRAM_OAUTH_REQUEST_ACCESS "$TELEGRAM_OAUTH_REQUEST_ACCESS_VALUE" "$output"

    append_preserved_env "$output"
}

write_env_file() {
    section "Review .env"
    display_env_summary
    if ! confirm "Write .env now?" 1; then
        warn "Skipped .env write."
        return 0
    fi
    tmp="$TARGET_DIR/.env.tmp.$$"
    render_env_file "$tmp"
    if [ -e "$ENV_PATH" ]; then
        backup=$(backup_path "$ENV_PATH")
        cp "$ENV_PATH" "$backup"
        info "Backed up $ENV_PATH to $(basename "$backup")"
    fi
    mv "$tmp" "$ENV_PATH"
    ok "Wrote $ENV_PATH"
}

prepare_data_mount() {
    section "Prepare data mount"
    data_dir="$TARGET_DIR/data"
    created=0
    if [ ! -d "$data_dir" ]; then
        mkdir -p "$data_dir" || return 1
        created=1
    fi

    if [ "$created" = "1" ]; then
        if command -v chown >/dev/null 2>&1; then
            if ! chown "$APP_UID:$APP_GID" "$data_dir" 2>/dev/null; then
                warn "Не удалось выполнить chown для $data_dir. Выполните вручную: sudo chown $APP_UID:$APP_GID data"
            fi
        fi
        chmod u+rwx "$data_dir" 2>/dev/null || true
        ok "Created writable $data_dir"
        return 0
    fi

    info "$data_dir already exists."
    if confirm "Adjust $data_dir owner to $APP_UID:$APP_GID for container writes?" 0; then
        if command -v chown >/dev/null 2>&1; then
            if ! chown "$APP_UID:$APP_GID" "$data_dir" 2>/dev/null; then
                warn "Не удалось выполнить chown для $data_dir. Выполните вручную: sudo chown $APP_UID:$APP_GID data"
            fi
        fi
        chmod u+rwx "$data_dir" 2>/dev/null || true
    fi
}

is_ipv4_address() {
    printf '%s' "$1" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'
}

is_local_hostname() {
    case "$1" in
        ""|localhost|127.*|0.0.0.0|::1)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

unique_public_hosts() {
    first=""
    for host in "$WEBHOOK_HOST_VALUE" "$MINIAPP_HOST_VALUE"; do
        [ -n "$host" ] || continue
        is_local_hostname "$host" && continue
        if [ "$host" = "$first" ]; then
            continue
        fi
        printf '%s\n' "$host"
        [ -z "$first" ] && first="$host"
    done
}

public_ipv4() {
    for url in https://api.ipify.org https://ifconfig.me https://ipv4.icanhazip.com; do
        if command -v curl >/dev/null 2>&1; then
            ip=$(curl -fsS --max-time 10 "$url" 2>/dev/null | tr -d '[:space:]')
        elif command -v wget >/dev/null 2>&1; then
            ip=$(wget -qO- --timeout=10 "$url" 2>/dev/null | tr -d '[:space:]')
        else
            return 1
        fi
        if is_ipv4_address "$ip"; then
            printf '%s\n' "$ip"
            return 0
        fi
    done
    return 1
}

resolve_ipv4_records() {
    host="$1"
    if is_ipv4_address "$host"; then
        printf '%s\n' "$host"
        return 0
    fi
    if command -v dig >/dev/null 2>&1; then
        dig +short A "$host" 2>/dev/null | grep -E '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' | sort -u
        return 0
    fi
    if command -v getent >/dev/null 2>&1; then
        getent ahostsv4 "$host" 2>/dev/null | awk '{print $1}' | grep -E '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' | sort -u
        return 0
    fi
    if command -v host >/dev/null 2>&1; then
        host -t A "$host" 2>/dev/null | awk '/has address/ {print $4}' | grep -E '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' | sort -u
        return 0
    fi
    if command -v nslookup >/dev/null 2>&1; then
        nslookup -type=A "$host" 2>/dev/null | awk '/^Address: / {print $2}' | grep -E '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' | sort -u
        return 0
    fi
    return 1
}

check_public_dns_records() {
    case "$PROFILE_KEY" in
        caddy|nginx|egames)
            ;;
        *)
            return 0
            ;;
    esac

    hosts=$(unique_public_hosts)
    [ -n "$hosts" ] || return 0

    section "Проверка DNS"
    if ! confirm "Проверить A-records для WEBHOOK_HOST и MINIAPP_HOST сейчас?" 1; then
        warn "Проверка DNS пропущена."
        return 0
    fi

    server_ip=$(public_ipv4 || true)
    if [ -z "$server_ip" ]; then
        warn "Не удалось определить публичный IPv4 этого сервера; проверка DNS будет только информационной."
    else
        info "Публичный IPv4 сервера: $server_ip"
    fi

    dns_ok=1
    printf '%s\n' "$hosts" | while IFS= read -r host; do
        records=$(resolve_ipv4_records "$host" || true)
        if [ -z "$records" ]; then
            warn "У $host не видно A-record."
            printf '%s\n' "$host" >> "$TARGET_DIR/$INSTALL_STATE_DIR/dns-preflight-warnings.tmp"
            continue
        fi
        one_line=$(printf '%s' "$records" | tr '\n' ' ' | sed 's/[[:space:]]*$//')
        if [ -n "$server_ip" ] && printf '%s\n' "$records" | grep -Fxq "$server_ip"; then
            ok "$host указывает на этот сервер ($one_line)."
        elif [ -n "$server_ip" ]; then
            warn "$host указывает на $one_line, а не на этот сервер ($server_ip)."
            printf '%s\n' "$host" >> "$TARGET_DIR/$INSTALL_STATE_DIR/dns-preflight-warnings.tmp"
        else
            info "$host указывает на $one_line."
        fi
    done

    if [ -f "$TARGET_DIR/$INSTALL_STATE_DIR/dns-preflight-warnings.tmp" ]; then
        rm -f "$TARGET_DIR/$INSTALL_STATE_DIR/dns-preflight-warnings.tmp"
        dns_ok=0
    fi
    if [ "$dns_ok" = "0" ]; then
        warn "Сертификаты и публичные webhook могут не заработать, пока DNS не указывает на этот сервер или proxy перед ним."
        if ! confirm "Продолжить несмотря на предупреждение?" 0; then
            return 1
        fi
    fi
}

base_domain_guess() {
    printf '%s\n' "$1" | awk -F. '{ if (NF > 2) print $(NF-1)"."$NF; else print $0 }'
}

shell_quote() {
    printf '%s' "$1" | sed "s/'/'\\\\''/g; s/^/'/; s/$/'/"
}

nginx_cert_files_exist() {
    host="$1"
    [ -f "$TARGET_DIR/ssl/$host/fullchain.pem" ] && [ -f "$TARGET_DIR/ssl/$host/privkey.pem" ]
}

ensure_certbot_available() {
    method="$1"
    if command -v certbot >/dev/null 2>&1; then
        if [ "$method" != "cloudflare" ] || certbot plugins 2>/dev/null | grep -q 'dns-cloudflare'; then
            return 0
        fi
    fi

    if ! command -v apt-get >/dev/null 2>&1; then
        fail "certbot недоступен. Установите certbot перед автоматической настройкой сертификатов."
        return 1
    fi
    if ! confirm "Установить пакеты certbot через apt-get сейчас?" 1; then
        fail "Для этого способа выпуска сертификата нужен certbot."
        return 1
    fi
    packages="certbot"
    if [ "$method" = "cloudflare" ]; then
        packages="$packages python3-certbot-dns-cloudflare"
    fi
    apt-get update && apt-get install -y $packages
}

copy_letsencrypt_cert_to_nginx_ssl() {
    cert_name="$1"
    host="$2"
    live_dir="/etc/letsencrypt/live/$cert_name"
    if [ ! -f "$live_dir/fullchain.pem" ] || [ ! -f "$live_dir/privkey.pem" ]; then
        fail "Файлы сертификата не найдены в $live_dir."
        return 1
    fi
    mkdir -p "$TARGET_DIR/ssl/$host"
    cp "$live_dir/fullchain.pem" "$TARGET_DIR/ssl/$host/fullchain.pem"
    cp "$live_dir/privkey.pem" "$TARGET_DIR/ssl/$host/privkey.pem"
    chmod 600 "$TARGET_DIR/ssl/$host/privkey.pem" 2>/dev/null || true
    ok "Файлы сертификата установлены для $host."
}

remember_nginx_cert_mapping() {
    cert_name="$1"
    host="$2"
    printf '%s %s\n' "$cert_name" "$host" >> "$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-map.tmp"
}

install_nginx_certbot_deploy_hook() {
    hook="/etc/letsencrypt/renewal-hooks/deploy/remnawave-minishop-${COMPOSE_PROJECT_NAME_VALUE:-default}-nginx.sh"
    mkdir -p "$(dirname "$hook")" || return 0
    tmp="$hook.tmp.$$"
    map_file="$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-map.tmp"
    {
        printf '#!/bin/sh\nset -eu\n'
        printf 'TARGET_DIR=%s\n' "$(shell_quote "$TARGET_DIR")"
        printf 'copy_cert() {\n'
        printf '  cert_name="$1"; host="$2"; live_dir="/etc/letsencrypt/live/$cert_name"\n'
        printf '  [ -f "$live_dir/fullchain.pem" ] && [ -f "$live_dir/privkey.pem" ] || return 0\n'
        printf '  mkdir -p "$TARGET_DIR/ssl/$host"\n'
        printf '  cp "$live_dir/fullchain.pem" "$TARGET_DIR/ssl/$host/fullchain.pem"\n'
        printf '  cp "$live_dir/privkey.pem" "$TARGET_DIR/ssl/$host/privkey.pem"\n'
        printf '}\n'
        if [ -f "$map_file" ]; then
            while IFS=' ' read -r cert_name host; do
                [ -n "$cert_name" ] && [ -n "$host" ] || continue
                printf 'copy_cert %s %s\n' "$(shell_quote "$cert_name")" "$(shell_quote "$host")"
            done < "$map_file"
        else
            unique_public_hosts | while IFS= read -r host; do
                cert_name=$(base_domain_guess "$host")
                printf 'copy_cert %s %s\n' "$(shell_quote "$cert_name")" "$(shell_quote "$host")"
            done
        fi
        printf 'cd "$TARGET_DIR" || exit 0\n'
        printf 'if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then\n'
        printf '  docker compose exec -T nginx nginx -s reload >/dev/null 2>&1 || true\n'
        printf 'elif command -v docker-compose >/dev/null 2>&1; then\n'
        printf '  docker-compose exec -T nginx nginx -s reload >/dev/null 2>&1 || true\n'
        printf 'fi\n'
    } > "$tmp"
    mv "$tmp" "$hook"
    chmod 700 "$hook" 2>/dev/null || true
    ok "Установлен certbot deploy hook: $hook"
}

configure_nginx_certificates() {
    [ "$PROFILE_KEY" = "nginx" ] || return 0
    hosts=$(unique_public_hosts)
    [ -n "$hosts" ] || return 0

    section "TLS-сертификаты Nginx"
    missing=0
    printf '%s\n' "$hosts" | while IFS= read -r host; do
        if nginx_cert_files_exist "$host"; then
            ok "Найдены ssl/$host/fullchain.pem и privkey.pem."
        else
            warn "Не хватает ssl/$host/fullchain.pem или privkey.pem."
            printf '%s\n' "$host" >> "$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-missing.tmp"
        fi
    done
    if [ -f "$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-missing.tmp" ]; then
        rm -f "$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-missing.tmp"
        missing=1
    fi
    [ "$missing" = "0" ] && return 0

    rm -f "$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-map.tmp"

    choose "Настройка сертификатов Nginx" "1" "1|2|3|4" \
        "1. Certbot Cloudflare DNS-01 - wildcard-сертификат для зоны." \
        "2. Certbot standalone HTTP-01 - отдельный сертификат для каждого hostname." \
        "3. Я уже положил файлы сертификатов в ssl/<hostname>/ вручную." \
        "4. Пропустить сейчас (Nginx может не стартовать без сертификатов)." || return 1

    case "$CHOICE_VALUE" in
        1)
            ensure_certbot_available cloudflare || return 1
            prompt_value "Email аккаунта Let's Encrypt" "$(env_get LETSENCRYPT_EMAIL '')" 1 0 ""
            le_email="$PROMPT_VALUE"
            prompt_value "Cloudflare DNS API token" "$(env_get CLOUDFLARE_DNS_API_TOKEN '')" 1 1 ""
            cf_token="$PROMPT_VALUE"
            mkdir -p "$HOME/.secrets/certbot"
            credentials="$HOME/.secrets/certbot/remnawave-minishop-cloudflare.ini"
            {
                printf 'dns_cloudflare_api_token = %s\n' "$cf_token"
            } > "$credentials"
            chmod 600 "$credentials"
            bases=""
            printf '%s\n' "$hosts" | while IFS= read -r host; do
                base=$(base_domain_guess "$host")
                if ! printf '%s\n' "$bases" | grep -Fxq "$base"; then
                    printf '%s\n' "$base" >> "$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-bases.tmp"
                fi
            done
            sort -u "$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-bases.tmp" > "$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-bases.sorted"
            rm -f "$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-bases.tmp"
            while IFS= read -r base; do
                [ -n "$base" ] || continue
                info "Запрашиваю wildcard-сертификат для $base через Cloudflare DNS-01."
                certbot certonly \
                    --dns-cloudflare \
                    --dns-cloudflare-credentials "$credentials" \
                    --dns-cloudflare-propagation-seconds 60 \
                    -d "$base" \
                    -d "*.$base" \
                    --email "$le_email" \
                    --agree-tos \
                    --non-interactive \
                    --key-type ecdsa \
                    --elliptic-curve secp384r1 || return 1
            done < "$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-bases.sorted"
            rm -f "$TARGET_DIR/$INSTALL_STATE_DIR/nginx-cert-bases.sorted"
            printf '%s\n' "$hosts" | while IFS= read -r host; do
                cert_name=$(base_domain_guess "$host")
                copy_letsencrypt_cert_to_nginx_ssl "$cert_name" "$host" || exit 1
                remember_nginx_cert_mapping "$cert_name" "$host"
            done || return 1
            install_nginx_certbot_deploy_hook
            ;;
        2)
            ensure_certbot_available http || return 1
            prompt_value "Email аккаунта Let's Encrypt" "$(env_get LETSENCRYPT_EMAIL '')" 1 0 ""
            le_email="$PROMPT_VALUE"
            printf '%s\n' "$hosts" | while IFS= read -r host; do
                info "Запрашиваю сертификат для $host через standalone HTTP-01."
                certbot certonly \
                    --standalone \
                    --preferred-challenges http \
                    -d "$host" \
                    --email "$le_email" \
                    --agree-tos \
                    --non-interactive \
                    --key-type ecdsa \
                    --elliptic-curve secp384r1 || exit 1
                copy_letsencrypt_cert_to_nginx_ssl "$host" "$host" || exit 1
                remember_nginx_cert_mapping "$host" "$host"
            done || return 1
            install_nginx_certbot_deploy_hook
            ;;
        3)
            printf '%s\n' "$hosts" | while IFS= read -r host; do
                if ! nginx_cert_files_exist "$host"; then
                    fail "Все еще не хватает ssl/$host/fullchain.pem или privkey.pem."
                    exit 1
                fi
            done || return 1
            ;;
        4)
            warn "Пропускаю настройку сертификатов. Nginx не стартует, пока не появятся ssl/<hostname>/fullchain.pem и privkey.pem."
            ;;
    esac
}

require_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        COMPOSE_STYLE="docker"
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_STYLE="docker-compose"
    else
        fail "Docker Compose не найден."
        return 1
    fi
    if command -v docker >/dev/null 2>&1 && ! docker info >/dev/null 2>&1; then
        fail "Docker установлен, но недоступен. Проверьте сервис Docker и права пользователя."
        return 1
    fi
}

compose() {
    if [ "$COMPOSE_STYLE" = "docker" ]; then
        docker compose "$@"
    else
        docker-compose "$@"
    fi
}

mask_compose_log_args() {
    printf '%s' "$*" | sed -E 's#((postgres|postgresql)://[^:/[:space:]@]+:)[^@[:space:]]+@#\1***@#g'
}

run_compose() {
    log_args=$(mask_compose_log_args "$@")
    if [ "$COMPOSE_STYLE" = "docker" ]; then
        color "+ docker compose $log_args" "$DIM"
    else
        color "+ docker-compose $log_args" "$DIM"
    fi
    printf '\n'
    compose "$@"
}

start_stack() {
    pull="${1:-1}"
    section "Запуск Docker stack"
    require_docker || return 1
    if [ "$pull" = "1" ]; then
        (cd "$TARGET_DIR" && run_compose pull) || return 1
    fi
    (cd "$TARGET_DIR" && run_compose up -d) || return 1
    (cd "$TARGET_DIR" && run_compose ps) || true
    ok "Команда stack выполнена."
}

validate_stack() {
    section "Проверка stack"
    require_docker || return 1
    (cd "$TARGET_DIR" && run_compose ps) || true
    (cd "$TARGET_DIR" && run_compose logs --tail 80 migrate) || true
    ok "Команды проверки выполнены."
}

env_file_get() {
    key="$1"
    file="$2"
    [ -f "$file" ] || return 0
    awk -v key="$key" '
        BEGIN { q = sprintf("%c", 39) }
        $0 ~ "^[[:space:]]*" key "=" {
            sub(/^[^=]*=/, "")
            gsub(/^[[:space:]]+|[[:space:]]+$/, "")
            if ((substr($0, 1, 1) == "\"" && substr($0, length($0), 1) == "\"") ||
                (substr($0, 1, 1) == q && substr($0, length($0), 1) == q)) {
                $0 = substr($0, 2, length($0) - 2)
            }
            print
            exit
        }
    ' "$file"
}

set_env_file_value() {
    file="$1"
    key="$2"
    value="$3"
    tmp="$file.tmp.$$"
    awk -v key="$key" -v value="$value" '
        BEGIN { done = 0 }
        $0 ~ "^[[:space:]]*" key "=" {
            print key "=" value
            done = 1
            next
        }
        { print }
        END {
            if (!done) {
                print key "=" value
            }
        }
    ' "$file" > "$tmp" || {
        rm -f "$tmp"
        return 1
    }
    mv "$tmp" "$file"
}

egames_remove_managed_and_conflicting_servers() {
    input="$1"
    output="$2"
    webhook_host="$3"
    miniapp_host="$4"
    awk -v webhook_host="$webhook_host" -v miniapp_host="$miniapp_host" '
        /^# BEGIN remnawave-minishop managed by install.sh$/ {
            managed = 1
            next
        }
        /^# END remnawave-minishop managed by install.sh$/ {
            managed = 0
            next
        }
        managed {
            next
        }
        !capture && $0 ~ /^[[:space:]]*server[[:space:]]*\{/ {
            capture = 1
            depth = 0
            block = ""
            skip = 0
        }
        capture {
            block = block $0 ORS
            line = $0
            if (line ~ /^[[:space:]]*server_name[[:space:]]/) {
                sub(/;.*/, "", line)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
                n = split(line, names, /[[:space:]]+/)
                for (i = 2; i <= n; i++) {
                    if (names[i] == webhook_host || names[i] == miniapp_host) {
                        skip = 1
                    }
                }
            }
            open_line = $0
            close_line = $0
            opens = gsub(/\{/, "", open_line)
            closes = gsub(/\}/, "", close_line)
            depth += opens - closes
            if (depth == 0) {
                if (!skip) {
                    printf "%s", block
                }
                capture = 0
                block = ""
                skip = 0
            }
            next
        }
        { print }
        END {
            if (capture && !skip) {
                printf "%s", block
            }
        }
    ' "$input" > "$output"
}

bind_port() {
    value="$1"
    case "$value" in
        *:*) printf '%s' "${value##*:}" ;;
        *) printf '%s' "$value" ;;
    esac
}

first_nginx_value() {
    key="$1"
    file="$2"
    awk -v key="$key" '
        $1 == key {
            value = $2
            gsub(/[";]/, "", value)
            print value
            exit
        }
    ' "$file"
}

egames_container_has_routes() {
    container="$1"
    webhook_host="$2"
    miniapp_host="$3"
    backend_port="$4"
    frontend_port="$5"
    docker exec "$container" sh -c '
        grep -Fq "server_name $1;" /etc/nginx/conf.d/default.conf &&
        grep -Fq "server_name $2;" /etc/nginx/conf.d/default.conf &&
        grep -Fq "proxy_pass http://127.0.0.1:$3;" /etc/nginx/conf.d/default.conf &&
        grep -Fq "proxy_pass http://127.0.0.1:$4;" /etc/nginx/conf.d/default.conf
    ' sh "$webhook_host" "$miniapp_host" "$backend_port" "$frontend_port"
}

is_egames_profile() {
    [ "$PROFILE_KEY" = "egames" ] && return 0
    [ "$(env_get DEPLOYMENT_PROFILE '')" = "egames" ]
}

configure_egames_reverse_proxy() {
    is_egames_profile || return 0
    section "Настройка reverse proxy eGames"
    require_docker || return 1

    detected_nginx_conf=$(detect_egames_nginx_conf || true)
    [ -n "$detected_nginx_conf" ] || detected_nginx_conf="/opt/remnawave/nginx.conf"
    prompt_value "Путь к nginx.conf eGames" "$detected_nginx_conf" 1 0 ""
    nginx_conf="$PROMPT_VALUE"
    if [ ! -f "$nginx_conf" ]; then
        fail "nginx.conf eGames не найден: $nginx_conf"
        return 1
    fi
    detected_nginx_container=$(detect_egames_nginx_container || true)
    [ -n "$detected_nginx_container" ] || detected_nginx_container="remnawave-nginx"
    prompt_value "Имя Nginx контейнера eGames" "$detected_nginx_container" 1 0 ""
    nginx_container="$PROMPT_VALUE"

    webhook_host="${WEBHOOK_HOST_VALUE:-$(env_get WEBHOOK_HOST '')}"
    miniapp_host="${MINIAPP_HOST_VALUE:-$(env_get MINIAPP_HOST '')}"
    if [ -z "$webhook_host" ] || [ -z "$miniapp_host" ]; then
        fail "Для настройки eGames reverse proxy нужны WEBHOOK_HOST и MINIAPP_HOST."
        return 1
    fi

    cert_path=$(first_nginx_value ssl_certificate "$nginx_conf")
    key_path=$(first_nginx_value ssl_certificate_key "$nginx_conf")
    trusted_path=$(first_nginx_value ssl_trusted_certificate "$nginx_conf")
    [ -n "$trusted_path" ] || trusted_path="$cert_path"
    if [ -z "$cert_path" ] || [ -z "$key_path" ]; then
        fail "Не удалось найти ssl_certificate и ssl_certificate_key в $nginx_conf"
        return 1
    fi

    backend_port=$(bind_port "${WEB_SERVER_BIND_VALUE:-$(env_get WEB_SERVER_BIND '127.0.0.1:8080')}")
    frontend_port=$(bind_port "${FRONTEND_BIND_VALUE:-$(env_get FRONTEND_BIND '127.0.0.1:8082')}")
    backup=$(backup_path "$nginx_conf")
    cp "$nginx_conf" "$backup" || return 1
    tmp="$nginx_conf.tmp.$$"
    egames_remove_managed_and_conflicting_servers "$backup" "$tmp" "$webhook_host" "$miniapp_host" || {
        rm -f "$tmp"
        return 1
    }

    cat >> "$tmp" <<EOF

# BEGIN remnawave-minishop managed by install.sh
server {
    server_name $webhook_host;
    listen unix:/dev/shm/nginx.sock ssl proxy_protocol;
    http2 on;

    ssl_certificate "$cert_path";
    ssl_certificate_key "$key_path";
    ssl_trusted_certificate "$trusted_path";

    client_max_body_size 20m;

    location / {
        proxy_http_version 1.1;
        proxy_pass http://127.0.0.1:$backend_port;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$proxy_protocol_addr;
        proxy_set_header X-Forwarded-For \$proxy_protocol_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}

server {
    server_name $miniapp_host;
    listen unix:/dev/shm/nginx.sock ssl proxy_protocol;
    http2 on;

    ssl_certificate "$cert_path";
    ssl_certificate_key "$key_path";
    ssl_trusted_certificate "$trusted_path";

    client_max_body_size 20m;

    location / {
        proxy_http_version 1.1;
        proxy_pass http://127.0.0.1:$frontend_port;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$proxy_protocol_addr;
        proxy_set_header X-Forwarded-For \$proxy_protocol_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
# END remnawave-minishop managed by install.sh
EOF

    if ! cat "$tmp" > "$nginx_conf"; then
        rm -f "$tmp"
        return 1
    fi
    rm -f "$tmp"
    if docker inspect "$nginx_container" >/dev/null 2>&1; then
        if ! egames_container_has_routes "$nginx_container" "$webhook_host" "$miniapp_host" "$backend_port" "$frontend_port"; then
            warn "Перезапускаю $nginx_container, чтобы он увидел обновленный eGames config."
            if ! docker restart "$nginx_container" >/dev/null; then
                warn "Перезапуск Nginx не удался; восстанавливаю $backup"
                cp "$backup" "$nginx_conf"
                docker restart "$nginx_container" >/dev/null || true
                return 1
            fi
        fi
        if docker exec "$nginx_container" nginx -t; then
            docker exec "$nginx_container" nginx -s reload || docker restart "$nginx_container" >/dev/null
            ok "Маршруты eGames Nginx настроены: $webhook_host -> 127.0.0.1:$backend_port и $miniapp_host -> 127.0.0.1:$frontend_port"
        else
            warn "Проверка nginx config не прошла; восстанавливаю $backup"
            cp "$backup" "$nginx_conf"
            docker restart "$nginx_container" >/dev/null || true
            return 1
        fi
    else
        warn "Nginx контейнер $nginx_container не найден; восстанавливаю $backup"
        cp "$backup" "$nginx_conf"
        return 1
    fi
}

configure_egames_panel_webhook() {
    is_egames_profile || return 0
    section "Настройка webhook Remnawave Panel"
    detected_panel_env=$(detect_egames_panel_env || true)
    [ -n "$detected_panel_env" ] || detected_panel_env="/opt/remnawave/.env"
    prompt_value "Путь к .env Remnawave Panel для обновления webhook" "$detected_panel_env" 0 0 ""
    panel_env="$PROMPT_VALUE"
    if [ -z "$panel_env" ]; then
        warn "Путь к .env панели пустой; пропускаю обновление webhook в Remnawave Panel."
        return 0
    fi
    panel_dir=$(dirname "$panel_env")
    if [ ! -f "$panel_env" ]; then
        warn "Пропускаю обновление webhook Remnawave Panel: $panel_env не найден."
        return 0
    fi

    base_url=$(target_webhook_base_url)
    if [ -z "$base_url" ]; then
        warn "Пропускаю обновление webhook Remnawave Panel: не удалось определить WEBHOOK_BASE_URL."
        return 0
    fi
    panel_webhook_secret=""
    if [ -n "$SOURCE_ENV_PATH" ]; then
        panel_webhook_secret=$(env_file_get REMNAWAVE_WEBHOOK_SECRET "$SOURCE_ENV_PATH")
    fi
    [ -n "$panel_webhook_secret" ] || panel_webhook_secret=$(env_get PANEL_WEBHOOK_SECRET "")

    backup=$(backup_path "$panel_env")
    cp "$panel_env" "$backup" || return 1
    set_env_file_value "$panel_env" WEBHOOK_URL "$base_url/webhook/panel" || return 1
    if [ -n "$panel_webhook_secret" ]; then
        set_env_file_value "$panel_env" WEBHOOK_SECRET_HEADER "$panel_webhook_secret" || return 1
    fi

    if [ -d "$panel_dir" ]; then
        (cd "$panel_dir" && run_compose up -d remnawave) || warn "Не удалось перезапустить backend Remnawave; перезапустите его вручную."
    fi
    ok "Webhook Remnawave Panel указывает на $base_url/webhook/panel"
}

telegram_bot_profile_checklist() {
    bot_token=$(env_get BOT_TOKEN "")
    title=$(env_get WEBAPP_TITLE "remnawave-minishop")
    [ -n "$bot_token" ] || return 0
    section "Профиль Telegram бота"
    info "Installer не меняет отображаемое имя и short description Telegram бота."
    if [ -n "$title" ]; then
        info "Можно оставить текущие имя/описание в BotFather или вручную упомянуть там: $title"
    fi
}

telegram_oauth_checklist() {
    section "Telegram OAuth / OpenID Connect"
    miniapp_url="${MINIAPP_PUBLIC_URL_VALUE:-$(env_get MINIAPP_PUBLIC_URL '')}"
    [ -n "$miniapp_url" ] || miniapp_url="https://${MINIAPP_HOST_VALUE:-$(env_get MINIAPP_HOST app.example.com)}/"
    oauth_secret=$(env_get TELEGRAM_OAUTH_CLIENT_SECRET "")
    if [ -z "$oauth_secret" ]; then
        warn "Telegram OAuth client secret пустой. Настройка BotFather Web Login/OIDC недоступна через Bot API."
    else
        ok "Telegram OAuth client secret есть в .env."
    fi
    info "В BotFather укажите Mini App URL/domain: $miniapp_url"
    info "В BotFather Web Login / OpenID Connect разрешите:"
    printf '  %s\n' "$miniapp_url"
    printf '  %sauth/telegram/callback\n' "$(printf '%s' "$miniapp_url" | sed 's:/*$:/:' )"
}

volume_exists() {
    docker volume inspect "$1" >/dev/null 2>&1
}

volume_is_empty() {
    docker run --rm -v "$1:/data" alpine sh -c \
        'test -z "$(find /data -mindepth 1 -print -quit)"' >/dev/null 2>&1
}

copy_volume_if_safe() {
    source_volume="$1"
    target_volume="$2"
    required="${3:-0}"

    if ! volume_exists "$source_volume"; then
        if [ "$required" = "1" ]; then
            fail "Исходный Docker volume не найден: $source_volume"
            return 1
        fi
        warn "Пропускаю $source_volume: исходный volume не найден."
        return 0
    fi

    if ! volume_exists "$target_volume"; then
        if [ "$required" = "1" ]; then
            fail "Целевой Docker volume не найден: $target_volume"
            return 1
        fi
        warn "Пропускаю $target_volume: целевой volume не был создан этим профилем."
        return 0
    fi

    if ! volume_is_empty "$target_volume"; then
        if [ "$required" = "1" ]; then
            warn "Целевой volume $target_volume уже не пустой."
            warn "Возможно, миграция уже была выполнена или stack уже стартовал с пустой базой."
            if confirm "Продолжить без копирования старого database volume?" 0; then
                return 0
            fi
            return 1
        fi
        warn "Пропускаю $target_volume: целевой volume уже не пустой."
        return 0
    fi

    run_label="docker run --rm -v $source_volume:/from:ro -v $target_volume:/to alpine sh -c 'cd /from && cp -a . /to/'"
    color "+ $run_label" "$DIM"
    printf '\n'
    docker run --rm \
        -v "$source_volume:/from:ro" \
        -v "$target_volume:/to" \
        alpine sh -c 'cd /from && cp -a . /to/' || return 1
    ok "Скопировано $source_volume -> $target_volume"
}

stop_known_legacy_containers() {
    section "Остановка старых контейнеров"
    stopped=0
    for container in $KNOWN_LEGACY_CONTAINERS; do
        if docker inspect "$container" >/dev/null 2>&1; then
            if docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -q '^true$'; then
                docker stop "$container" >/dev/null || true
            fi
            docker rm "$container" >/dev/null || true
            info "Остановлен/удален $container"
            stopped=1
        fi
    done
    if [ "$stopped" = "0" ]; then
        info "Известные старые контейнеры не найдены."
    fi
}

wait_target_postgres() {
    section "Ожидание целевого PostgreSQL"
    attempt=1
    while [ "$attempt" -le 30 ]; do
        if (cd "$TARGET_DIR" && compose exec -T postgres sh -c \
            'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1); then
            ok "PostgreSQL готов."
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    fail "Целевой PostgreSQL не стал готовым."
    return 1
}

download_importer() {
    importer="$TARGET_DIR/$IMPORTER_CACHE_PATH"
    mkdir -p "$(dirname "$importer")"
    url=$(raw_url "$SOURCE_REPO" "$SOURCE_REF" "backend/scripts/import_legacy.py")
    tmp="$TARGET_DIR/.import_legacy.$$"
    download_to "$url" "$tmp" || {
        rm -f "$tmp"
        fail "Не удалось скачать $url"
        return 1
    }
    if [ -f "$importer" ]; then
        backup=$(backup_path "$importer")
        cp "$importer" "$backup"
        info "Backup importer сохранен как $(basename "$backup")" >&2
    fi
    mv "$tmp" "$importer"
    ok "Importer сохранен в cache: $importer" >&2
    printf '%s' "$importer"
}

local_target_dsn() {
    printf 'postgresql://%s:%s@postgres:5432/%s' "$POSTGRES_USER_VALUE" "$POSTGRES_PASSWORD_VALUE" "$POSTGRES_DB_VALUE"
}

target_webhook_base_url() {
    public_url=$(env_get WEBHOOK_PUBLIC_URL "")
    if [ -n "$public_url" ]; then
        printf '%s' "$public_url" | sed 's:/*$::'
        return 0
    fi
    host=$(env_get WEBHOOK_HOST "")
    if [ -n "$host" ]; then
        printf 'https://%s' "$host" | sed 's:/*$::'
        return 0
    fi
    printf ''
}

dsn_hostname() {
    dsn="$1"
    printf '%s\n' "$dsn" | sed -n 's#^[^:][^:]*://\([^@/]*@\)\{0,1\}\(\[[^]]*\]\|[^:/?]*\).*#\2#p' | sed 's/^\[//; s/\]$//'
}

target_compose_project() {
    project=$(env_get COMPOSE_PROJECT_NAME "")
    [ -n "$project" ] || project=$(basename "$TARGET_DIR")
    printf '%s' "$project"
}

connect_local_source_db_to_target_network() {
    source_host=$(dsn_hostname "$SOURCE_DSN")
    [ -n "$source_host" ] || return 0
    case "$source_host" in
        localhost|127.*|::1|postgres|host.docker.internal)
            return 0
            ;;
    esac
    if ! docker inspect --type container "$source_host" >/dev/null 2>&1; then
        return 0
    fi

    target_network="$(target_compose_project)_remnawave-shop"
    if ! docker network inspect "$target_network" >/dev/null 2>&1; then
        warn "Целевая Docker network $target_network не найдена; source container $source_host не подключен автоматически."
        return 0
    fi

    if docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$source_host" | grep -Fx "$target_network" >/dev/null 2>&1; then
        ok "Source container $source_host уже подключен к $target_network."
        return 0
    fi

    docker network connect "$target_network" "$source_host" || {
        warn "Не удалось подключить source container $source_host к $target_network. Dry-run может упасть, если backend его не видит."
        return 0
    }
    ok "Source container $source_host подключен к $target_network для импорта Remnashop."
}

remnashop_webhook_checklist() {
    section "Обновление внешних webhook"
    base_url=$(target_webhook_base_url)
    if [ -z "$base_url" ]; then
        warn "Не удалось определить webhook base URL из .env. Укажите WEBHOOK_HOST или WEBHOOK_PUBLIC_URL и используйте WEBHOOK_BASE_URL + пути ниже."
        base_url="WEBHOOK_BASE_URL"
    fi

    info "После миграции проверьте эти URL во внешних кабинетах:"
    printf '  Remnawave Panel -> WEBHOOK_URL: %s/webhook/panel\n' "$base_url"
    panel_secret=$(env_get PANEL_WEBHOOK_SECRET "")
    if [ -n "$panel_secret" ]; then
        printf '  Remnawave Panel -> webhook secret: %s\n' "$(mask_secret "$panel_secret")"
    else
        warn "PANEL_WEBHOOK_SECRET пустой; задайте его в Minishop и Remnawave Panel."
    fi
    printf '  YooKassa merchant cabinet -> HTTP notifications URL: %s/webhook/yookassa\n' "$base_url"
    printf '  WATA merchant dashboard -> webhook/callback URL: %s/webhook/wata\n' "$base_url"
    printf '  CryptoBot/Crypto Pay app -> webhook URL: %s/webhook/cryptopay\n' "$base_url"
    printf '  Heleket merchant dashboard -> payment webhook/callback URL: %s/webhook/heleket\n' "$base_url"
    printf '  PayKilla Dashboard -> Settings -> Webhooks URL: %s/webhook/paykilla\n' "$base_url"
    printf '  FreeKassa shop settings -> notification/result URL: %s/webhook/freekassa\n' "$base_url"
    printf '  Platega merchant/project settings -> webhook URL: %s/webhook/platega\n' "$base_url"
    printf '  Telegram webhook: %s/tg/webhook (backend ставит его автоматически при старте)\n' "$base_url"
}

extract_import_summary() {
    output_path="$1"
    summary_path="$2"
    command -v python3 >/dev/null 2>&1 || {
        warn "python3 not found; could not save migration summary JSON."
        return 1
    }
    python3 - "$output_path" "$summary_path" <<'PY'
import json
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
summary = None
for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
    candidate = line.strip()
    if not (candidate.startswith("{") and candidate.endswith("}")):
        continue
    try:
        decoded = json.loads(candidate)
    except ValueError:
        continue
    if isinstance(decoded, dict) and decoded.get("source") == "remnashop":
        summary = decoded
if summary is None:
    raise SystemExit("No Remnashop summary JSON found in importer output")
summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(
    json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
}

notify_remnashop_migration_success() {
    summary_path="$1"
    [ -f "$summary_path" ] || {
        warn "Migration summary was not saved; skipping Telegram success notification."
        return 0
    }
    command -v python3 >/dev/null 2>&1 || {
        warn "python3 not found; skipping Telegram success notification."
        return 0
    }
    bot_token=$(env_get BOT_TOKEN "")
    [ -n "$bot_token" ] || {
        warn "BOT_TOKEN is empty; skipping Telegram success notification."
        return 0
    }

    message_path="$TARGET_DIR/$INSTALL_STATE_DIR/remnashop-post-migration-message.txt"
    mkdir -p "$(dirname "$message_path")"
    export BOT_TOKEN_VALUE="$bot_token"
    export ADMIN_IDS_VALUE="$(env_get ADMIN_IDS "")"
    export LOG_CHAT_ID_VALUE="$(env_get LOG_CHAT_ID "")"
    export LOG_THREAD_ID_VALUE="$(env_get LOG_THREAD_ID "")"
    export MINIAPP_PUBLIC_URL_VALUE="$(env_get MINIAPP_PUBLIC_URL "")"
    export WEBHOOK_BASE_URL_VALUE="$(target_webhook_base_url)"
    export TELEGRAM_OAUTH_CLIENT_SECRET_VALUE="$(env_get TELEGRAM_OAUTH_CLIENT_SECRET "")"
    export REMNASHOP_MESSAGE_PATH="$message_path"

    python3 - "$summary_path" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
message_path = Path(os.environ["REMNASHOP_MESSAGE_PATH"])
miniapp_url = os.environ.get("MINIAPP_PUBLIC_URL_VALUE") or ""
webhook_base_url = os.environ.get("WEBHOOK_BASE_URL_VALUE") or ""
oauth_secret = os.environ.get("TELEGRAM_OAUTH_CLIENT_SECRET_VALUE") or ""


def section(name):
    value = summary.get(name)
    return value if isinstance(value, dict) else {}


def counter_line(title, key, fields):
    data = section(key)
    parts = [f"{label}: {int(data.get(field, 0) or 0)}" for field, label in fields]
    return f"- {title}: " + ", ".join(parts)


warnings = summary.get("warnings") if isinstance(summary.get("warnings"), list) else []
post_actions = summary.get("post_migration_actions") or {}
payment_actions = post_actions.get("payment_providers") or []
settings = section("settings")
notification_overrides = settings.get("notification_overrides") or {}

lines = [
    "Миграция Remnashop в remnawave-minishop успешно завершена.",
    "",
    "Статистика:",
    counter_line(
        "Пользователи",
        "users",
        [
            ("created", "создано"),
            ("updated", "обновлено"),
            ("profile_preserved", "профиль сохранен"),
            ("skipped", "пропущено"),
        ],
    ),
    counter_line(
        "Подписки",
        "subscriptions",
        [("created", "создано"), ("updated", "обновлено"), ("skipped", "пропущено")],
    ),
    counter_line(
        "Платежи",
        "payments",
        [("created", "создано"), ("updated", "обновлено"), ("skipped", "пропущено")],
    ),
    counter_line(
        "Промокоды",
        "promocodes",
        [
            ("created", "создано"),
            ("updated", "обновлено"),
            ("activation_imported", "активаций"),
            ("unsupported_reward", "неподдержано"),
        ],
    ),
    counter_line(
        "Тарифы",
        "tariffs",
        [
            ("catalog_written", "каталог записан"),
            ("generated", "сгенерировано"),
            ("skipped", "пропущено"),
        ],
    ),
    counter_line(
        "Платежные настройки",
        "payment_provider_settings",
        [
            ("providers_mapped", "перенесено"),
            ("unsupported", "неподдержано"),
            ("skipped", "пропущено"),
        ],
    ),
]

if warnings:
    lines.extend(["", f"Предупреждения: {len(warnings)}"])
    for warning in warnings:
        lines.append(f"- {warning}")

lines.extend(
    [
        "",
        "Дальнейшие шаги:",
        "- Имя и short description Telegram-бота installer не менял. Если нужно, меняйте их вручную в BotFather.",
        "- Старые команды Remnashop очищаются при старте backend; Minishop оставляет только свои команды.",
    ]
)
if miniapp_url:
    callback_url = miniapp_url.rstrip("/") + "/auth/telegram/callback"
    lines.append(f"- В BotFather укажите Mini App URL/domain: {miniapp_url}")
    lines.append(f"- Для Web Login / OpenID Connect разрешите: {miniapp_url} и {callback_url}")
else:
    lines.append("- В BotFather укажите Mini App URL/domain из MINIAPP_PUBLIC_URL.")
if oauth_secret:
    lines.append("- TELEGRAM_OAUTH_CLIENT_SECRET заполнен; после BotFather-проверки перезапустите backend.")
else:
    lines.append(
        "- TELEGRAM_OAUTH_CLIENT_SECRET пустой: если нужен browser OAuth, создайте Web Login/OIDC client в BotFather, заполните secret и перезапустите backend."
    )
if webhook_base_url:
    lines.append(f"- Telegram webhook: {webhook_base_url.rstrip('/')}/tg/webhook, он ставится backend автоматически.")
    lines.append(f"- Remnawave Panel webhook: {webhook_base_url.rstrip('/')}/webhook/panel.")
if payment_actions:
    lines.append("- Проверьте webhook URL у платежных провайдеров:")
    for action in payment_actions[:8]:
        provider = action.get("provider") or "provider"
        new_url = action.get("new_url") or ""
        if new_url:
            lines.append(f"  {provider}: {new_url}")

text = "\n".join(lines)
message_path.write_text(text + "\n", encoding="utf-8")
print(text)


def split_telegram_messages(value, limit=3900):
    chunks = []
    current = []
    current_len = 0
    for line in value.splitlines():
        if len(line) > limit:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for start in range(0, len(line), limit):
                chunks.append(line[start : start + limit])
            continue

        extra = len(line) + (1 if current else 0)
        if current and current_len + extra > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += extra

    if current:
        chunks.append("\n".join(current))
    return chunks or [""]


def parse_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


targets = []
for raw_id in (os.environ.get("ADMIN_IDS_VALUE") or "").replace(";", ",").split(","):
    chat_id = parse_int(raw_id)
    if chat_id is not None:
        targets.append({"chat_id": chat_id, "label": "админу"})

log_chat_id = parse_int(os.environ.get("LOG_CHAT_ID_VALUE")) or parse_int(
    notification_overrides.get("LOG_CHAT_ID")
)
log_thread_id = parse_int(os.environ.get("LOG_THREAD_ID_VALUE")) or parse_int(
    notification_overrides.get("LOG_THREAD_ID")
)
if log_chat_id is not None:
    targets.append({"chat_id": log_chat_id, "thread_id": log_thread_id, "label": "лог-чату"})

unique_targets = []
seen = set()
for target in targets:
    key = (target.get("chat_id"), target.get("thread_id"))
    if key in seen:
        continue
    seen.add(key)
    unique_targets.append(target)

bot_token = os.environ.get("BOT_TOKEN_VALUE") or ""
if not unique_targets:
    print("Не найдены ADMIN_IDS или LOG_CHAT_ID для отправки уведомления об успешной миграции.")
    raise SystemExit(0)

for target in unique_targets:
    chunks = split_telegram_messages(text)
    try:
        for chunk in chunks:
            payload = {
                "chat_id": str(target["chat_id"]),
                "text": chunk,
                "disable_web_page_preview": "true",
            }
            if target.get("thread_id") is not None:
                payload["message_thread_id"] = str(target["thread_id"])
            data = urllib.parse.urlencode(payload).encode("utf-8")
            request = urllib.request.Request(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                data=data,
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                response.read()
        suffix = f" ({len(chunks)} сообщений)" if len(chunks) > 1 else ""
        print(
            f"Уведомление об успешной миграции отправлено {target['label']} {target['chat_id']}{suffix}."
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(
            f"Предупреждение: не удалось отправить уведомление об успешной миграции {target['label']} {target['chat_id']}: {exc}",
            file=sys.stderr,
        )
PY
}

run_import_command() {
    dry="$1"
    summary_output_path="${2:-}"
    set -- run --rm -T \
        --user 0:0 \
        -v "$IMPORTER_PATH:/app/backend/scripts/import_legacy.py:ro"
    if [ -n "$SOURCE_ENV_PATH" ]; then
        set -- "$@" -v "$SOURCE_ENV_PATH:/tmp/remnashop.env:ro"
    fi
    if [ -n "$TARIFF_MAP_PATH" ]; then
        set -- "$@" -v "$TARIFF_MAP_PATH:/tmp/tariff-map.json:ro"
    fi
    set -- "$@" backend python backend/scripts/import_legacy.py \
        --source-type remnashop \
        --source-dsn "$SOURCE_DSN" \
        --source-schema "$SOURCE_SCHEMA" \
        --target-dsn "$TARGET_DSN"
    if [ -n "$SOURCE_ENV_PATH" ]; then
        set -- "$@" --source-env-file /tmp/remnashop.env
    fi
    if [ -n "$TARIFF_MAP_PATH" ]; then
        set -- "$@" --tariff-map-json /tmp/tariff-map.json
    fi
    if [ "$dry" = "1" ]; then
        set -- "$@" --dry-run
    fi
    if [ -n "$summary_output_path" ]; then
        mkdir -p "$(dirname "$summary_output_path")"
        raw_output="$summary_output_path.raw"
        if (cd "$TARGET_DIR" && run_compose "$@" < /dev/null) > "$raw_output" 2>&1; then
            cat "$raw_output"
            extract_import_summary "$raw_output" "$summary_output_path" || true
            return 0
        fi
        status=$?
        cat "$raw_output"
        return "$status"
    fi
    (cd "$TARGET_DIR" && run_compose "$@" < /dev/null)
}

reset_target_compose_database() {
    section "Сброс целевой базы Minishop"
    require_docker || return 1
    (cd "$TARGET_DIR" && run_compose stop backend worker migrate) || true
    (cd "$TARGET_DIR" && run_compose up -d postgres redis) || return 1
    wait_target_postgres || return 1
    (cd "$TARGET_DIR" && run_compose exec -T postgres sh -c \
        'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"') || return 1
    ok "Целевая база Minishop сброшена."
}

create_pre_migration_backup() {
    label="$1"
    if ! confirm "Сделать backup текущего Minishop перед миграцией? Это позволит откатить целевую базу и конфиги." 1; then
        warn "Backup перед миграцией пропущен по вашему выбору."
        return 0
    fi

    section "Backup перед миграцией"
    require_docker || return 1
    stamp=$(date -u '+%Y%m%d-%H%M%S')
    backup_dir="$TARGET_DIR/backups/pre-${label}-migration-$stamp"
    mkdir -p "$backup_dir/files" "$backup_dir/dumps"
    chmod 700 "$backup_dir" 2>/dev/null || true

    for file in .env docker-compose.yml compose.yml Caddyfile nginx.conf.template .env.example; do
        if [ -f "$TARGET_DIR/$file" ]; then
            mkdir -p "$backup_dir/files/$(dirname "$file")"
            cp "$TARGET_DIR/$file" "$backup_dir/files/$file"
        fi
    done

    if (cd "$TARGET_DIR" && compose exec -T postgres sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1); then
        if (cd "$TARGET_DIR" && compose exec -T postgres sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl') > "$backup_dir/dumps/minishop-postgres.sql"; then
            ok "Dump PostgreSQL сохранен: $backup_dir/dumps/minishop-postgres.sql"
        else
            warn "Не удалось сохранить dump PostgreSQL. Backup конфигов сохранен, но откат базы будет недоступен."
            rm -f "$backup_dir/dumps/minishop-postgres.sql"
        fi
    else
        warn "PostgreSQL целевого stack пока недоступен; сохраняю только конфиги."
    fi

    cat > "$backup_dir/restore.sh" <<EOF
#!/bin/sh
set -eu
TARGET_DIR=$(shell_quote "$TARGET_DIR")
BACKUP_DIR=$(shell_quote "$backup_dir")

compose_cmd() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose "\$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "\$@"
  else
    echo "Docker Compose не найден." >&2
    exit 1
  fi
}

cd "\$TARGET_DIR"
if [ -f "\$BACKUP_DIR/files/.env" ]; then
  cp "\$BACKUP_DIR/files/.env" "\$TARGET_DIR/.env"
fi
for file in docker-compose.yml compose.yml Caddyfile nginx.conf.template .env.example; do
  if [ -f "\$BACKUP_DIR/files/\$file" ]; then
    cp "\$BACKUP_DIR/files/\$file" "\$TARGET_DIR/\$file"
  fi
done
if [ -f "\$BACKUP_DIR/dumps/minishop-postgres.sql" ]; then
  compose_cmd up -d postgres redis
  compose_cmd exec -T postgres sh -lc 'dropdb -U "\$POSTGRES_USER" --if-exists "\$POSTGRES_DB" && createdb -U "\$POSTGRES_USER" "\$POSTGRES_DB"'
  compose_cmd exec -T postgres sh -lc 'psql -U "\$POSTGRES_USER" -d "\$POSTGRES_DB" -v ON_ERROR_STOP=1' < "\$BACKUP_DIR/dumps/minishop-postgres.sql"
fi
compose_cmd up -d
echo "Откат из backup завершен: \$BACKUP_DIR"
EOF
    chmod 700 "$backup_dir/restore.sh" 2>/dev/null || true

    cat > "$backup_dir/README.md" <<EOF
# Backup перед миграцией

Создан: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
Целевой каталог: $TARGET_DIR
Источник миграции: $label

Для отката выполните:

    $backup_dir/restore.sh

Backup содержит копии основных файлов деплоя и, если PostgreSQL был доступен, logical dump целевой базы Minishop.
EOF
    ok "Backup перед миграцией сохранен: $backup_dir"
}

choose_legacy_source() {
    default_source="1"
    if detect_remnashop_stack; then
        default_source="1"
        info "Найден Remnashop; по умолчанию предлагаю миграцию из него."
    elif volume_exists "$OLD_TGSHOP_DB_VOLUME" 2>/dev/null; then
        default_source="2"
        info "Найден старый Docker volume remnawave-tg-shop; по умолчанию предлагаю миграцию из него."
    fi
    info "Документация по миграции из Remnashop: $DOCS_REMNASHOP_URL"
    choose "Откуда мигрировать данные" "$default_source" "1|2|3" \
        "1. Remnashop - пользователи, подписки, платежи, тарифы, промокоды и настройки провайдеров." \
        "2. Старый remnawave-tg-shop - перенос совместимой базы/volume." \
        "3. Не мигрировать данные" || return 1
    case "$CHOICE_VALUE" in
        1) LEGACY_SOURCE="remnashop" ;;
        2) LEGACY_SOURCE="remnawave-tg-shop" ;;
        3) LEGACY_SOURCE="skip" ;;
    esac
}

ensure_github_source_for_importer() {
    if [ -n "$SOURCE_REPO" ] && [ -n "$SOURCE_REF" ]; then
        return 0
    fi
    install_source
}

run_remnashop_migration() {
    section "Миграция из Remnashop"
    info "Сначала будет dry-run без записи данных. Документация: $DOCS_REMNASHOP_URL"
    ENV_PATH="$TARGET_DIR/.env"
    if [ ! -f "$ENV_PATH" ]; then
        fail ".env не найден. Сначала установите stack или сгенерируйте конфигурацию."
        return 1
    fi
    ensure_github_source_for_importer || return 1
    require_docker || return 1
    POSTGRES_USER_VALUE="$(env_get POSTGRES_USER '')"
    POSTGRES_PASSWORD_VALUE="$(env_get POSTGRES_PASSWORD '')"
    POSTGRES_DB_VALUE="$(env_get POSTGRES_DB '')"

    detected_source_dsn=$(detect_remnashop_source_dsn || true)
    if [ -n "$detected_source_dsn" ]; then
        info "Нашел Remnashop PostgreSQL и подставил DSN по умолчанию."
    fi
    prompt_value "DSN PostgreSQL базы Remnashop" "$detected_source_dsn" 1 0 ""
    SOURCE_DSN="$PROMPT_VALUE"
    prompt_value "Schema источника" "public" 1 0 ""
    SOURCE_SCHEMA="$PROMPT_VALUE"
    detected_source_env=$(detect_remnashop_env_file || true)
    if [ -n "$detected_source_env" ]; then
        info "Нашел .env Remnashop и подставил путь по умолчанию."
    fi
    prompt_value "Путь к .env Remnashop для переноса настроек (пусто = пропустить)" "$detected_source_env" 0 0 ""
    SOURCE_ENV_PATH="$PROMPT_VALUE"
    if [ -n "$SOURCE_ENV_PATH" ]; then
        source_env_dir=$(dirname "$SOURCE_ENV_PATH")
        if [ ! -d "$source_env_dir" ]; then
            fail "Каталог source .env не найден: $source_env_dir"
            return 1
        fi
        SOURCE_ENV_PATH=$(cd "$source_env_dir" && pwd)/$(basename "$SOURCE_ENV_PATH")
        if [ ! -f "$SOURCE_ENV_PATH" ]; then
            fail ".env Remnashop не найден: $SOURCE_ENV_PATH"
            return 1
        fi
    fi

    choose "Целевая база Minishop" "1" "1|2" \
        "1. База текущего Docker Compose stack (рекомендуется)." \
        "2. Ввести target DSN вручную." || return 1
    if [ "$CHOICE_VALUE" = "1" ]; then
        TARGET_DSN="$(local_target_dsn)"
        info "Target DSN указывает на postgres service текущего Compose stack."
        create_pre_migration_backup remnashop || return 1
        if confirm "Сбросить целевую базу Minishop перед импортом? Это удалит текущие данные Minishop." 0; then
            reset_target_compose_database || return 1
        fi
    else
        warn "Для ручного target DSN автоматический backup целевой базы не выполняется."
        prompt_value "Target PostgreSQL DSN" "" 1 0 ""
        TARGET_DSN="$PROMPT_VALUE"
    fi

    prompt_value "Путь к JSON map тарифов (пусто = пропустить)" "" 0 0 ""
    TARIFF_MAP_PATH="$PROMPT_VALUE"
    if [ -n "$TARIFF_MAP_PATH" ]; then
        tariff_map_dir=$(dirname "$TARIFF_MAP_PATH")
        if [ ! -d "$tariff_map_dir" ]; then
            fail "Каталог tariff map не найден: $tariff_map_dir"
            return 1
        fi
        TARIFF_MAP_PATH=$(cd "$tariff_map_dir" && pwd)/$(basename "$TARIFF_MAP_PATH")
        if [ ! -f "$TARIFF_MAP_PATH" ]; then
            fail "Tariff map не найден: $TARIFF_MAP_PATH"
            return 1
        fi
    fi

    IMPORTER_PATH="$(download_importer)" || return 1
    connect_local_source_db_to_target_network

    section "Dry-run импорт"
    if ! run_import_command 1; then
        fail "Dry-run не прошел. Исправьте подключение или настройки перед импортом."
        return 1
    fi
    if ! confirm "Применить эту миграцию по-настоящему?" 0; then
        warn "Миграция не применена."
        return 0
    fi

    section "Применение импорта"
    mkdir -p "$TARGET_DIR/$INSTALL_STATE_DIR"
    APPLY_SUMMARY_PATH="$TARGET_DIR/$INSTALL_STATE_DIR/remnashop-apply-summary.json"
    run_import_command 0 "$APPLY_SUMMARY_PATH" || return 1
    configure_egames_panel_webhook || return 1
    telegram_bot_profile_checklist
    telegram_oauth_checklist
    remnashop_webhook_checklist
    if confirm "Перезапустить backend и worker, чтобы они перечитали настройки?" 1; then
        (cd "$TARGET_DIR" && run_compose restart backend worker) || true
    fi
    notify_remnashop_migration_success "$APPLY_SUMMARY_PATH"
    ok "Миграция завершена."
}

run_target_schema_migrations() {
    section "Применение schema migrations целевого stack"
    require_docker || return 1
    (cd "$TARGET_DIR" && run_compose run --rm migrate) || return 1
    ok "Schema migrations выполнены."
}

prepare_compose_without_starting_apps() {
    section "Подготовка целевого Compose stack"
    require_docker || return 1
    (cd "$TARGET_DIR" && run_compose up --no-start) || return 1
}

run_tgshop_volume_migration() {
    section "Миграция volume старого remnawave-tg-shop"
    warn "Этот путь копирует старый PostgreSQL Docker volume в новый volume Minishop."
    warn "Старые volumes не удаляются; сохраните их до проверки нового stack."

    if confirm "Остановить известные старые/текущие контейнеры перед копированием volumes?" 1; then
        stop_known_legacy_containers || return 1
        (cd "$TARGET_DIR" && run_compose down) || true
    fi

    prepare_compose_without_starting_apps || return 1
    copy_volume_if_safe "$OLD_TGSHOP_DB_VOLUME" "$NEW_MINISHOP_DB_VOLUME" 1 || return 1
    copy_volume_if_safe "$OLD_TGSHOP_CADDY_DATA_VOLUME" "$NEW_MINISHOP_CADDY_DATA_VOLUME" 0 || return 1
    copy_volume_if_safe "$OLD_TGSHOP_CADDY_CONFIG_VOLUME" "$NEW_MINISHOP_CADDY_CONFIG_VOLUME" 0 || return 1

    if confirm "Запустить новый stack и применить schema changes сейчас?" 1; then
        start_stack 0 || return 1
        (cd "$TARGET_DIR" && run_compose logs --tail 120 migrate) || true
    else
        warn "Stack подготовлен, но не запущен. Позже выполните docker compose up -d."
    fi
}

run_tgshop_dsn_migration() {
    section "DSN-миграция старого remnawave-tg-shop"
    warn "Этот путь делает dump старой PostgreSQL базы, восстанавливает его в целевую Compose PostgreSQL и запускает schema migrations Minishop."
    warn "Целевая база будет удалена и создана заново перед restore."

    if ! confirm "Заменить целевую базу dump'ом источника?" 0; then
        warn "Миграция не применена."
        return 0
    fi

    prompt_value "DSN PostgreSQL старого remnawave-tg-shop" "${LEGACY_TGSHOP_SOURCE_DSN:-}" 1 0 ""
    SOURCE_DSN="$PROMPT_VALUE"

    require_docker || return 1
    POSTGRES_USER_VALUE="$(env_get POSTGRES_USER '')"
    POSTGRES_PASSWORD_VALUE="$(env_get POSTGRES_PASSWORD '')"
    POSTGRES_DB_VALUE="$(env_get POSTGRES_DB '')"
    TARGET_DSN="$(local_target_dsn)"

    section "Запуск целевого PostgreSQL"
    (cd "$TARGET_DIR" && run_compose stop backend worker frontend migrate) || true
    (cd "$TARGET_DIR" && run_compose up -d postgres redis) || return 1
    wait_target_postgres || return 1

    section "Сброс целевой базы"
    (cd "$TARGET_DIR" && run_compose exec -T postgres sh -c \
        'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"') || return 1

    section "Dump и restore старой базы"
    (cd "$TARGET_DIR" && run_compose run --rm --no-deps \
        -e "SOURCE_DSN=$SOURCE_DSN" \
        -e "TARGET_DSN=$TARGET_DSN" \
        backend sh -lc \
        'pg_dump --clean --if-exists --no-owner --no-privileges "$SOURCE_DSN" | psql "$TARGET_DSN"') || return 1

    run_target_schema_migrations || return 1
    if confirm "Запустить полный stack сейчас?" 1; then
        start_stack 0 || return 1
    fi
}

run_remnawave_tg_shop_migration() {
    section "Миграция старого remnawave-tg-shop"
    ENV_PATH="$TARGET_DIR/.env"
    if [ ! -f "$ENV_PATH" ]; then
        fail ".env не найден. Сначала установите stack или сгенерируйте конфигурацию."
        return 1
    fi
    require_docker || return 1

    choose "Способ миграции" "1" "1|2|3" \
        "1. Скопировать старые Docker volumes на этом сервере (рекомендуется для старых compose install)." \
        "2. Сделать dump из source PostgreSQL DSN и восстановить в этот compose stack." \
        "3. Пропустить миграцию" || return 1
    case "$CHOICE_VALUE" in
        1) run_tgshop_volume_migration ;;
        2) run_tgshop_dsn_migration ;;
        3) return 0 ;;
    esac
}

run_selected_legacy_migration() {
    case "$LEGACY_SOURCE" in
        remnashop)
            run_remnashop_migration
            ;;
        remnawave-tg-shop)
            run_remnawave_tg_shop_migration
            ;;
        skip|"")
            return 0
            ;;
    esac
}

installation_directory() {
    prompt_value "Папка установки" "$DEFAULT_INSTALL_DIR" 1 0 ""
    mkdir -p "$(dirname "$PROMPT_VALUE")"
    TARGET_DIR=$(cd "$(dirname "$PROMPT_VALUE")" && pwd)/$(basename "$PROMPT_VALUE")
    mkdir -p "$TARGET_DIR"
}

install_source() {
    [ -n "$SOURCE_REPO" ] || SOURCE_REPO="$DEFAULT_REPO"
    [ -n "$SOURCE_REF" ] || SOURCE_REF="$DEFAULT_REF"
    info "Файлы установки будут скачаны из GitHub: $SOURCE_REPO@$SOURCE_REF."
    info "Для fork, dev-ветки или тега задайте MINISHOP_INSTALL_REPO и MINISHOP_INSTALL_REF перед запуском."
}

install_flow() {
    with_migration="$1"
    LEGACY_SOURCE=""
    installation_directory || return 1
    install_source || return 1
    choose_profile || return 1
    if [ "$with_migration" = "1" ]; then
        choose_legacy_source || return 1
    fi
    ENV_PATH="$TARGET_DIR/.env"
    if [ -f "$ENV_PATH" ]; then
        warn "Найден существующий .env: $ENV_PATH; неизвестные значения будут сохранены."
    fi
    prompt_common_env || return 1
    mkdir -p "$TARGET_DIR/$INSTALL_STATE_DIR"
    check_public_dns_records || return 1
    download_profile_files || return 1
    write_env_file || return 1
    configure_nginx_certificates || return 1
    configure_egames_reverse_proxy || return 1
    prepare_data_mount || return 1
    if [ "$with_migration" != "1" ] && confirm "Мигрировать данные из другого бота после установки?" 0; then
        choose_legacy_source || return 1
    fi

    case "$LEGACY_SOURCE" in
        remnawave-tg-shop)
            run_selected_legacy_migration
            ;;
        remnashop)
            if confirm "Запустить Docker Compose stack перед импортом из Remnashop?" 1; then
                start_stack || return 1
            else
                warn "Импорту из Remnashop нужна целевая база stack. Импорт пропущен."
                return 0
            fi
            run_selected_legacy_migration
            ;;
        *)
            if confirm "Запустить Docker Compose stack сейчас?" 1; then
                start_stack || return 1
            fi
            ;;
    esac
}

migration_only_flow() {
    LEGACY_SOURCE=""
    installation_directory || return 1
    choose_legacy_source || return 1
    [ "$LEGACY_SOURCE" = "skip" ] && return 0
    prepare_data_mount || return 1
    case "$LEGACY_SOURCE" in
        remnashop) install_source || return 1 ;;
    esac
    run_selected_legacy_migration
}

download_only_flow() {
    installation_directory || return 1
    install_source || return 1
    choose_profile || return 1
    download_profile_files
}

health_flow() {
    installation_directory || return 1
    validate_stack
}

main_menu() {
    while :; do
        banner
        choose "Главное меню" "1" "1|2|3|4|5|6" \
            "1. Установить новый remnawave-minishop." \
            "2. Установить новый remnawave-minishop и мигрировать данные из другого бота." \
            "3. Мигрировать данные в уже установленный remnawave-minishop." \
            "4. Только скачать/обновить файлы деплоя." \
            "5. Проверить текущий stack." \
            "6. Выйти." || return 1
        case "$CHOICE_VALUE" in
            1) install_flow 0 ;;
            2) install_flow 1 ;;
            3) migration_only_flow ;;
            4) download_only_flow ;;
            5) health_flow ;;
            6) printf 'Готово, выходим.\n'; return 0 ;;
        esac
        status=$?
        if [ "$status" -ne 0 ]; then
            fail "Шаг завершился с ошибкой: $status."
        fi
        pause || return 0
    done
}

case "${1:-}" in
    -h|--help)
        print_help
        exit 0
        ;;
esac

main_menu
