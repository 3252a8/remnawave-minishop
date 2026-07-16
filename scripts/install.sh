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
KNOWN_LEGACY_CONTAINERS="remnawave-tg-shop remnawave-tg-shop-db remnawave-tg-shop-caddy remnawave-minishop remnawave-minishop-db remnawave-minishop-caddy remnawave-minishop-backend remnawave-minishop-worker remnawave-minishop-frontend remnawave-minishop-migrate remnawave-minishop-postgres remnawave-minishop-redis"
REMNASHOP_RUNTIME_CONTAINERS="remnashop remnashop-taskiq-worker remnashop-taskiq-scheduler remnashop-db remnashop-redis"
PANGOLIN_COMPOSE_FILE="docker-compose.pangolin.yml"

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
FRONTEND_BACKEND_MODE_VALUE=""
INSTALL_NODE_ROLE_VALUE=""
WEBAPP_API_BASE_URL_VALUE=""
WEBAPP_BACKEND_UPSTREAM_VALUE=""
WEBAPP_BACKEND_UPSTREAM_HOST_VALUE=""
MINISHOP_EDGE_TOKEN_VALUE=""
MINISHOP_EDGE_TOKEN_HEADER_VALUE=""
HTTP_BIND_VALUE=""
HTTPS_BIND_VALUE=""
WEB_SERVER_BIND_VALUE=""
WEBAPP_SERVER_BIND_VALUE=""
FRONTEND_BIND_VALUE=""
RATHOLE_IMAGE_VALUE=""
RATHOLE_CONTROL_BIND_VALUE=""
RATHOLE_CONTROL_REMOTE_VALUE=""
RATHOLE_SERVICE_TOKEN_VALUE=""
RATHOLE_SERVICE_PORT_VALUE=""
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

KNOWN_ENV_KEYS="DEPLOYMENT_PROFILE COMPOSE_PROJECT_NAME IMAGE_TAG WEBHOOK_HOST MINIAPP_HOST WEBHOOK_PUBLIC_URL MINIAPP_PUBLIC_URL FRONTEND_BACKEND_MODE INSTALL_NODE_ROLE WEBAPP_API_BASE_URL WEBAPP_BACKEND_UPSTREAM WEBAPP_BACKEND_UPSTREAM_HOST MINISHOP_EDGE_TOKEN MINISHOP_EDGE_TOKEN_HEADER HTTP_BIND HTTPS_BIND WEB_SERVER_BIND WEBAPP_SERVER_BIND FRONTEND_BIND RATHOLE_IMAGE RATHOLE_CONTROL_BIND RATHOLE_CONTROL_REMOTE RATHOLE_SERVICE_TOKEN RATHOLE_SERVICE_PORT PANGOLIN_ENDPOINT NEWT_ID NEWT_SECRET BOT_TOKEN ADMIN_IDS POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB WEBAPP_ENABLED WEBAPP_TITLE WEBAPP_SESSION_SECRET WEBHOOK_SECRET_TOKEN TRUSTED_PROXIES PANEL_API_URL PANEL_API_KEY PANEL_API_COOKIE PANEL_WEBHOOK_SECRET TELEGRAM_OAUTH_CLIENT_ID TELEGRAM_OAUTH_CLIENT_SECRET TELEGRAM_OAUTH_REQUEST_ACCESS"

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
  MINISHOP_IMAGE_TAG        тег Docker-образа ($DEFAULT_IMAGE_TAG)
  REMNASHOP_SOURCE_DSN      DSN базы Remnashop для миграции
  REMNASHOP_SOURCE_ENV_FILE путь к .env Remnashop для переноса настроек
  REMNASHOP_SOURCE_SCHEMA   схема PostgreSQL базы Remnashop (public)
  LEGACY_TGSHOP_SOURCE_DSN  DSN старого remnawave-tg-shop для дампа/восстановления
  LEGACY_TGSHOP_DB_CONTAINER имя контейнера PostgreSQL старого remnawave-tg-shop

Мастер интерактивный: он не перезаписывает файлы без подтверждения.
Импорт из Remnashop всегда сначала запускается в режиме проверки без записи (dry-run).
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
        BOT_TOKEN|POSTGRES_PASSWORD|WEBAPP_SESSION_SECRET|WEBHOOK_SECRET_TOKEN|PANEL_API_KEY|PANEL_API_COOKIE|PANEL_WEBHOOK_SECRET|TELEGRAM_OAUTH_CLIENT_SECRET|NEWT_SECRET|MINISHOP_EDGE_TOKEN|RATHOLE_SERVICE_TOKEN)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

is_port_number() {
    value="$1"
    case "$value" in
        ""|*[!0-9]*)
            return 1
            ;;
    esac
    [ "$value" -ge 1 ] 2>/dev/null && [ "$value" -le 65535 ] 2>/dev/null
}

is_valid_ipv4_address() {
    awk -v ip="$1" '
        BEGIN {
            if (split(ip, parts, "\\.") != 4) {
                exit 1
            }
            for (i = 1; i <= 4; i++) {
                if (parts[i] !~ /^[0-9]+$/ || parts[i] < 0 || parts[i] > 255) {
                    exit 1
                }
            }
        }
    '
}

is_ipv6_literal() {
    printf '%s' "$1" | grep -Eq '^[0-9A-Fa-f:]+$' && printf '%s' "$1" | grep -q ':'
}

is_bind_address() {
    value="$1"
    [ -n "$value" ] || return 0
    case "$value" in
        *[[:space:]]*)
            return 1
            ;;
    esac
    case "$value" in
        \[*\]:*)
            host=${value%%]:*}
            host=${host#\[}
            port=${value##*:}
            [ -n "$host" ] && is_ipv6_literal "$host" && is_port_number "$port"
            ;;
        *:*)
            host=${value%:*}
            port=${value##*:}
            case "$host" in
                ""|*:*)
                    return 1
                    ;;
            esac
            is_valid_ipv4_address "$host" && is_port_number "$port"
            ;;
        *)
            is_port_number "$value"
            ;;
    esac
}

print_validation_hint() {
    validator="$1"
    value="${2:-}"
    case "$validator" in
        hostname)
            warn "Укажите hostname без схемы, пути и порта: app.example.com, а не https://app.example.com:443/path."
            ;;
        url)
            warn "URL должен начинаться с http:// или https:// и не содержать пробелов."
            ;;
        bind)
            warn "Формат Docker bind: PORT или IP:PORT. Примеры: 80, 0.0.0.0:80, 127.0.0.1:8080, [::1]:8080."
            if is_valid_ipv4_address "$value"; then
                warn "Похоже, указан только IP без порта. Docker Compose прочитает это неверно; добавьте порт, например $value:80."
            fi
            warn "Если не уверены, оставьте значение по умолчанию. 0.0.0.0 означает слушать все сетевые интерфейсы сервера."
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
        bind)
            is_bind_address "$value"
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
            print_validation_hint "$validator" "$value"
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
        suffix="Y/n"
    else
        suffix="y/N"
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
                warn "Ответьте y или n."
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

list_running_proxy_containers() {
    command -v docker >/dev/null 2>&1 || return 1
    docker ps --format '{{.Names}} {{.Image}}' 2>/dev/null | awk '
        {
            line = tolower($0)
            if (line !~ /nginx/ && line !~ /caddy/ && line !~ /angie/) next
            if (line ~ /minishop/ || line ~ /tg-shop/) next
            print $1
        }
    '
}

proxy_container_kind() {
    descriptor=$(docker inspect -f '{{.Name}} {{.Config.Image}}' "$1" 2>/dev/null | tr '[:upper:]' '[:lower:]')
    case "$descriptor" in
        *caddy*)
            printf 'caddy'
            ;;
        *angie*)
            printf 'angie'
            ;;
        *nginx*)
            printf 'nginx'
            ;;
        *)
            return 1
            ;;
    esac
}

container_uses_host_network() {
    [ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$1" 2>/dev/null)" = "host" ]
}

container_mount_source() {
    docker inspect -f '{{range .Mounts}}{{.Destination}}|{{.Source}}{{"\n"}}{{end}}' "$1" 2>/dev/null |
        awk -F'|' -v dest="$2" '$1 == dest { print $2; exit }'
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

detect_tgshop_db_container() {
    if [ -n "${LEGACY_TGSHOP_DB_CONTAINER:-}" ] && docker_container_exists "$LEGACY_TGSHOP_DB_CONTAINER"; then
        printf '%s' "$LEGACY_TGSHOP_DB_CONTAINER"
        return 0
    fi
    if docker_container_exists remnawave-tg-shop-db; then
        printf '%s' remnawave-tg-shop-db
        return 0
    fi
    command -v docker >/dev/null 2>&1 || return 1
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -Ei 'remnawave-tg-shop.*(db|postgres)|postgres.*remnawave-tg-shop' | head -n 1
}

detect_tgshop_source_dsn() {
    if [ -n "${LEGACY_TGSHOP_SOURCE_DSN:-}" ]; then
        printf '%s' "$LEGACY_TGSHOP_SOURCE_DSN"
        return 0
    fi
    container=$(detect_tgshop_db_container || true)
    [ -n "$container" ] || return 1
    docker exec "$container" sh -lc 'printf "postgresql://%s:%s@'"$container"':5432/%s" "$POSTGRES_USER" "$POSTGRES_PASSWORD" "$POSTGRES_DB"' 2>/dev/null
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

make_panel_api_jwt() {
    token_uuid="$1"
    jwt_secret="$2"
    [ -n "$token_uuid" ] && [ -n "$jwt_secret" ] || return 1
    command -v python3 >/dev/null 2>&1 || return 1

    PANEL_JWT_UUID="$token_uuid" PANEL_JWT_SECRET="$jwt_secret" python3 - <<'PY'
import base64
import hashlib
import hmac
import json
import os


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


token_uuid = os.environ["PANEL_JWT_UUID"]
secret = os.environ["PANEL_JWT_SECRET"].encode("utf-8")
header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
payload = b64url(
    json.dumps(
        {
            "uuid": token_uuid,
            "username": None,
            "role": "API",
            "iat": 0,
            "exp": 9999999999,
        },
        separators=(",", ":"),
    ).encode()
)
signature = b64url(hmac.new(secret, f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest())
print(f"{header}.{payload}.{signature}")
PY
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
    value=$(docker exec "$container" sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select token from api_tokens order by created_at desc limit 1;"' 2>/dev/null || true)
    if [ -n "$value" ]; then
        printf '%s' "$value"
        return 0
    fi

    value=$(docker exec "$container" sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select uuid::text from api_tokens order by created_at desc limit 1;"' 2>/dev/null || true)
    [ -n "$value" ] || return 1
    panel_env=$(detect_egames_panel_env || true)
    [ -n "$panel_env" ] && [ -f "$panel_env" ] || return 1
    jwt_secret=$(env_file_get JWT_API_TOKENS_SECRET "$panel_env")
    make_panel_api_jwt "$value" "$jwt_secret"
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
        if confirm "$target_path уже существует. Перезаписать, предварительно сохранив бэкап?" 0; then
            backup=$(backup_path "$target_path")
            cp "$target_path" "$backup"
            info "Бэкап файла $target_path сохранен как $(basename "$backup")"
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
    [ -n "$ENV_PATH" ] || ENV_PATH="$TARGET_DIR/.env"
    saved_profile=$(env_get DEPLOYMENT_PROFILE "")
    case "$saved_profile" in
        caddy) default_profile="1" ;;
        angie) default_profile="2" ;;
        nginx) default_profile="3" ;;
        newt) default_profile="4" ;;
        no-proxy) default_profile="5" ;;
        egames) default_profile="6" ;;
        *) saved_profile="" ;;
    esac
    if [ -n "$saved_profile" ]; then
        info "В $ENV_PATH уже выбран DEPLOYMENT_PROFILE=$saved_profile; предлагаю его по умолчанию."
    elif detect_egames_stack; then
        default_profile="6"
        info "Найдена установленная Remnawave/eGames связка; по умолчанию предлагаю встроиться в ее Nginx/TLS."
    else
        running_proxies=$(list_running_proxy_containers 2>/dev/null || true)
        if [ -n "$running_proxies" ]; then
            default_profile="6"
            info "Найдены уже запущенные reverse proxy контейнеры: $(printf '%s' "$running_proxies" | tr '\n' ' ' | sed 's/[[:space:]]*$//')."
            info "По умолчанию предлагаю встроиться в существующий Nginx/Angie/Caddy вместо запуска отдельного прокси."
        fi
    fi
    info "Подробнее о профилях деплоя: $DOCS_SETUP_URL"
    choose "Профиль деплоя" "$default_profile" "1|2|3|4|5|6" \
        "1. Caddy HTTPS - отдельный сервер, автоматические сертификаты." \
        "2. Angie HTTPS - форк Nginx с автоматическими сертификатами (ACME), конфигурация в Nginx-синтаксисе." \
        "3. Nginx HTTPS - свои сертификаты или помощник Certbot." \
        "4. Pangolin / Newt - без входящих портов, публичные маршруты в Pangolin." \
        "5. Без прокси / внешний TLS - прямые HTTP-порты или свой TLS-терминатор." \
        "6. Уже установленная Remnawave через eGames или другой запущенный Nginx/Angie/Caddy - встроиться в существующий reverse proxy." || return 1
    case "$CHOICE_VALUE" in
        1) PROFILE_KEY="caddy" ;;
        2) PROFILE_KEY="angie" ;;
        3) PROFILE_KEY="nginx" ;;
        4) PROFILE_KEY="newt" ;;
        5) PROFILE_KEY="no-proxy" ;;
        6) PROFILE_KEY="egames" ;;
    esac
    DEPLOYMENT_PROFILE_VALUE="$PROFILE_KEY"
}

choose_install_node_role() {
    section "Роль сервера"
    choose "Роль текущего сервера" "1" "1|2|3" \
        "1. Full stack - frontend, backend, worker и база на этом сервере." \
        "2. Backend node - webhook/backend plane и база; frontend будет отдельно." \
        "3. Frontend node - только frontend nginx, backend уже на другом сервере." || return 1
    case "$CHOICE_VALUE" in
        1) INSTALL_NODE_ROLE_VALUE="full-stack" ;;
        2) INSTALL_NODE_ROLE_VALUE="backend-node" ;;
        3) INSTALL_NODE_ROLE_VALUE="frontend-node" ;;
    esac
}

host_from_url() {
    printf '%s' "$1" | sed -n 's#^[A-Za-z][A-Za-z0-9+.-]*://\([^/:]*\).*#\1#p'
}

prompt_frontend_node_env() {
    section "Frontend node .env"
    COMPOSE_PROJECT_NAME_VALUE="$(env_get COMPOSE_PROJECT_NAME remnawave-minishop)"
    prompt_value "Имя Docker Compose проекта" "$COMPOSE_PROJECT_NAME_VALUE" 0 0 "" || return 1
    COMPOSE_PROJECT_NAME_VALUE="$PROMPT_VALUE"
    IMAGE_TAG_VALUE="$(env_get IMAGE_TAG "$DEFAULT_IMAGE_TAG")"
    prompt_value "Тег Docker-образа" "$IMAGE_TAG_VALUE" 0 0 "" || return 1
    IMAGE_TAG_VALUE="$PROMPT_VALUE"
    prompt_value "Публичный URL Mini App frontend" "$(env_get MINIAPP_PUBLIC_URL 'https://app.example.com/')" 1 0 "url" || return 1
    MINIAPP_PUBLIC_URL_VALUE="$PROMPT_VALUE"
    MINIAPP_HOST_VALUE="$(host_from_url "$MINIAPP_PUBLIC_URL_VALUE")"
    if [ -z "$MINIAPP_HOST_VALUE" ]; then
        fail "Не удалось определить hostname Mini App из $MINIAPP_PUBLIC_URL_VALUE"
        return 1
    fi
    FRONTEND_BIND_VALUE="$(env_get FRONTEND_BIND '127.0.0.1:8082')"
    prompt_value "Адрес привязки frontend container" "$FRONTEND_BIND_VALUE" 0 0 "bind" || return 1
    FRONTEND_BIND_VALUE="$PROMPT_VALUE"
    WEBAPP_API_BASE_URL_VALUE="/api"
    MINISHOP_EDGE_TOKEN_HEADER_VALUE="$(env_get MINISHOP_EDGE_TOKEN_HEADER X-Minishop-Edge-Token)"
    info "Frontend node не спрашивает BOT_TOKEN, PostgreSQL, Panel и платежные секреты; они остаются на backend node."
}

configure_frontend_backend_mode() {
    section "Связь frontend -> backend WebApp API"
    [ -n "$INSTALL_NODE_ROLE_VALUE" ] || INSTALL_NODE_ROLE_VALUE="full-stack"
    case "$INSTALL_NODE_ROLE_VALUE" in
        backend-node)
            prompt_value "Адрес привязки WebApp API plane 8081 (только loopback/private)" "$(env_get WEBAPP_SERVER_BIND '127.0.0.1:8081')" 0 0 "bind" || return 1
            WEBAPP_SERVER_BIND_VALUE="$PROMPT_VALUE"
            ;;
        frontend-node)
            info "Frontend node использует MINIAPP_PUBLIC_URL и server-side upstream; WEBHOOK_PUBLIC_URL остается backend node."
            ;;
    esac

    if [ "$INSTALL_NODE_ROLE_VALUE" = "full-stack" ]; then
        choose "Как frontend будет обращаться к backend WebApp API?" "1" "1|2|3" \
            "1. Same-origin / тот же compose - browser API base /api, upstream http://backend:8081." \
            "2. Защищенный backend upstream - browser API base /api, frontend nginx проксирует к backend." \
            "3. Приватный tunnel Rathole - browser API base /api, upstream http://rathole-server:18081." || return 1
        frontend_backend_choice="$CHOICE_VALUE"
    else
        choose "Как frontend будет обращаться к backend WebApp API?" "1" "1|2" \
            "1. Защищенный backend upstream - browser API base /api, frontend nginx проксирует к backend." \
            "2. Приватный tunnel Rathole - browser API base /api, upstream http://rathole-server:18081." || return 1
        case "$CHOICE_VALUE" in
            1) frontend_backend_choice="2" ;;
            2) frontend_backend_choice="3" ;;
        esac
    fi

    case "$frontend_backend_choice" in
        1)
            FRONTEND_BACKEND_MODE_VALUE="same-origin"
            WEBAPP_API_BASE_URL_VALUE="/api"
            WEBAPP_BACKEND_UPSTREAM_VALUE="http://backend:8081"
            WEBAPP_BACKEND_UPSTREAM_HOST_VALUE="backend"
            MINISHOP_EDGE_TOKEN_HEADER_VALUE="$(env_get MINISHOP_EDGE_TOKEN_HEADER X-Minishop-Edge-Token)"
            ;;
        2)
            FRONTEND_BACKEND_MODE_VALUE="protected-upstream"
            WEBAPP_API_BASE_URL_VALUE="/api"
            choose "Protected upstream вариант" "1" "1|2" \
                "1. Один backend-домен: /api и /auth на WEBHOOK_PUBLIC_URL защищены edge-token." \
                "2. Приватный IP/VPN: frontend nginx ходит к http://<private-ip>:8081." || return 1
            if [ "$CHOICE_VALUE" = "1" ]; then
                default_upstream="${WEBHOOK_PUBLIC_URL_VALUE:-$(env_get WEBHOOK_PUBLIC_URL 'https://bot.example.com')}"
                prompt_value "Backend upstream URL" "$default_upstream" 1 0 "url" || return 1
                WEBAPP_BACKEND_UPSTREAM_VALUE="$PROMPT_VALUE"
                upstream_host=$(host_from_url "$WEBAPP_BACKEND_UPSTREAM_VALUE")
                prompt_value "Backend upstream Host/SNI" "${upstream_host:-bot.example.com}" 1 0 "hostname" || return 1
                WEBAPP_BACKEND_UPSTREAM_HOST_VALUE="$PROMPT_VALUE"
                if [ "$INSTALL_NODE_ROLE_VALUE" = "frontend-node" ]; then
                    WEBHOOK_PUBLIC_URL_VALUE="$WEBAPP_BACKEND_UPSTREAM_VALUE"
                    WEBHOOK_HOST_VALUE="$WEBAPP_BACKEND_UPSTREAM_HOST_VALUE"
                fi
                current_edge_token="$(env_get MINISHOP_EDGE_TOKEN '')"
                [ -n "$current_edge_token" ] || current_edge_token="$(secret_hex 32)"
                prompt_value "Minishop edge token (только server-side proxy header)" "$current_edge_token" 1 1 "" || return 1
                MINISHOP_EDGE_TOKEN_VALUE="$PROMPT_VALUE"
            else
                prompt_value "Private backend WebApp API upstream" "$(env_get WEBAPP_BACKEND_UPSTREAM 'http://10.0.0.5:8081')" 1 0 "url" || return 1
                WEBAPP_BACKEND_UPSTREAM_VALUE="$PROMPT_VALUE"
                WEBAPP_BACKEND_UPSTREAM_HOST_VALUE="$(env_get WEBAPP_BACKEND_UPSTREAM_HOST '')"
                MINISHOP_EDGE_TOKEN_VALUE="$(env_get MINISHOP_EDGE_TOKEN '')"
            fi
            MINISHOP_EDGE_TOKEN_HEADER_VALUE="$(env_get MINISHOP_EDGE_TOKEN_HEADER X-Minishop-Edge-Token)"
            warn "WEBHOOK_PUBLIC_URL остается webhook/backend plane 8080. Платежные и panel webhook не идут через frontend и не требуют Minishop edge token."
            ;;
        3)
            FRONTEND_BACKEND_MODE_VALUE="rathole"
            WEBAPP_API_BASE_URL_VALUE="/api"
            WEBAPP_BACKEND_UPSTREAM_VALUE="http://rathole-server:18081"
            WEBAPP_BACKEND_UPSTREAM_HOST_VALUE="rathole-server"
            RATHOLE_IMAGE_VALUE="$(env_get RATHOLE_IMAGE rapiz1/rathole:v0.5.0)"
            RATHOLE_CONTROL_BIND_VALUE="$(env_get RATHOLE_CONTROL_BIND 0.0.0.0:2333)"
            RATHOLE_CONTROL_REMOTE_VALUE="$(env_get RATHOLE_CONTROL_REMOTE frontend.example.com:2333)"
            RATHOLE_SERVICE_PORT_VALUE="$(env_get RATHOLE_SERVICE_PORT 18081)"
            current_rathole_token="$(env_get RATHOLE_SERVICE_TOKEN '')"
            [ -n "$current_rathole_token" ] || current_rathole_token="$(secret_hex 32)"
            prompt_value "Rathole service token" "$current_rathole_token" 1 1 "" || return 1
            RATHOLE_SERVICE_TOKEN_VALUE="$PROMPT_VALUE"
            ;;
    esac
}

download_profile_files() {
    section "Скачивание файлов деплоя"
    case "$INSTALL_NODE_ROLE_VALUE" in
        frontend-node)
            case "$FRONTEND_BACKEND_MODE_VALUE" in
                rathole)
                    download_raw_file "deploy/examples/rathole/frontend-server.docker-compose.yml" "docker-compose.yml" 1 || return 1
                    download_raw_file "deploy/examples/rathole/.env.example" ".env.example" 1 || return 1
                    ;;
                *)
                    download_raw_file "deploy/examples/split-protected-upstream/frontend.docker-compose.yml" "docker-compose.yml" 1 || return 1
                    download_raw_file "deploy/examples/split-protected-upstream/.env.frontend.example" ".env.example" 1 || return 1
                    ;;
            esac
            return 0
            ;;
        backend-node)
            download_raw_file "deploy/examples/split-protected-upstream/backend.docker-compose.yml" "docker-compose.yml" 1 || return 1
            download_raw_file "deploy/examples/split-protected-upstream/.env.backend.example" ".env.example" 1 || return 1
            return 0
            ;;
    esac

    case "$PROFILE_KEY" in
        caddy)
            download_raw_file "deploy/examples/caddy/docker-compose.yml" "docker-compose.yml" 1 || return 1
            download_raw_file "deploy/examples/caddy/Caddyfile" "Caddyfile" 1 || return 1
            download_raw_file "deploy/examples/caddy/.env.example" ".env.example" 1 || return 1
            ;;
        angie)
            download_raw_file "deploy/examples/angie/docker-compose.yml" "docker-compose.yml" 1 || return 1
            download_raw_file "deploy/examples/angie/angie.conf.template" "angie.conf.template" 1 || return 1
            download_raw_file "deploy/examples/angie/.env.example" ".env.example" 1 || return 1
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
    prompt_value "Тег Docker-образа" "$(env_get IMAGE_TAG "$DEFAULT_IMAGE_TAG")" 0 0 ""
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
        info "Нашел API-ключ Remnawave Panel и подставил его по умолчанию."
    fi
    prompt_value "API-ключ Remnawave Panel" "$detected_panel_api_key" 0 1 "" "$detected_panel_api_key_prefilled"
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
        info "Нашел заголовок Cookie обратного прокси eGames и подставил его по умолчанию."
    fi
    prompt_value "Заголовок Cookie обратного прокси Remnawave (если нужен)" "$detected_panel_api_cookie" 0 1 "" "$detected_panel_api_cookie_prefilled"
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
        info "Нашел webhook-секрет Remnawave Panel и подставил его по умолчанию."
    fi
    if [ -z "$existing_panel_webhook_secret" ]; then
        existing_panel_webhook_secret=$(secret_hex 24)
    fi
    prompt_value "Webhook-секрет Remnawave Panel" "$existing_panel_webhook_secret" 0 1 "" "$existing_panel_webhook_secret_prefilled"
    PANEL_WEBHOOK_SECRET_VALUE="$PROMPT_VALUE"

    prompt_value "Идентификатор клиента Telegram OAuth (пусто = ID бота)" "$(env_get TELEGRAM_OAUTH_CLIENT_ID '')" 0 0 ""
    TELEGRAM_OAUTH_CLIENT_ID_VALUE="$PROMPT_VALUE"
    prompt_value "Секрет клиента Telegram OAuth из BotFather Web Login (пусто = пропустить OAuth в браузере)" "$(env_get TELEGRAM_OAUTH_CLIENT_SECRET '')" 0 1 ""
    TELEGRAM_OAUTH_CLIENT_SECRET_VALUE="$PROMPT_VALUE"
    TELEGRAM_OAUTH_REQUEST_ACCESS_VALUE="$(env_get TELEGRAM_OAUTH_REQUEST_ACCESS write)"
    info "Параметр Telegram OAuth request_access: $TELEGRAM_OAUTH_REQUEST_ACCESS_VALUE. Значение write позволяет боту написать пользователю после входа через Web Login."

    case "$PROFILE_KEY" in
        caddy|angie|nginx|newt|egames)
            prompt_value "Публичный hostname для API/webhook бота" "$(env_get WEBHOOK_HOST webhooks.example.com)" 1 0 "hostname"
            WEBHOOK_HOST_VALUE="$PROMPT_VALUE"
            prompt_value "Публичный hostname для Mini App" "$(env_get MINIAPP_HOST app.example.com)" 1 0 "hostname"
            MINIAPP_HOST_VALUE="$PROMPT_VALUE"
            WEBHOOK_PUBLIC_URL_VALUE="$(env_get WEBHOOK_PUBLIC_URL "https://$WEBHOOK_HOST_VALUE")"
            MINIAPP_PUBLIC_URL_VALUE="$(env_get MINIAPP_PUBLIC_URL "https://$MINIAPP_HOST_VALUE/")"
            TRUSTED_PROXIES_VALUE="$(env_get TRUSTED_PROXIES '127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7')"
            ;;
    esac

    case "$PROFILE_KEY" in
        caddy|angie|nginx)
            prompt_value "Адрес привязки HTTP" "$(env_get HTTP_BIND '0.0.0.0:80')" 0 0 "bind"
            HTTP_BIND_VALUE="$PROMPT_VALUE"
            prompt_value "Адрес привязки HTTPS" "$(env_get HTTPS_BIND '0.0.0.0:443')" 0 0 "bind"
            HTTPS_BIND_VALUE="$PROMPT_VALUE"
            ;;
        newt)
            prompt_value "Endpoint Pangolin" "$(env_get PANGOLIN_ENDPOINT https://pangolin.example.com)" 1 0 "url"
            PANGOLIN_ENDPOINT_VALUE="$PROMPT_VALUE"
            prompt_value "Newt ID" "$(env_get NEWT_ID '')" 1 0 ""
            NEWT_ID_VALUE="$PROMPT_VALUE"
            prompt_value "Секрет Newt" "$(env_get NEWT_SECRET '')" 1 1 ""
            NEWT_SECRET_VALUE="$PROMPT_VALUE"
            ;;
        no-proxy)
            prompt_value "Адрес привязки backend" "$(env_get WEB_SERVER_BIND '0.0.0.0:8080')" 0 0 "bind"
            WEB_SERVER_BIND_VALUE="$PROMPT_VALUE"
            prompt_value "Адрес привязки frontend" "$(env_get FRONTEND_BIND '0.0.0.0:8082')" 0 0 "bind"
            FRONTEND_BIND_VALUE="$PROMPT_VALUE"
            prompt_value "Публичный URL webhook/API" "$(env_get WEBHOOK_PUBLIC_URL 'http://127.0.0.1:8080')" 1 0 "url"
            WEBHOOK_PUBLIC_URL_VALUE="$PROMPT_VALUE"
            prompt_value "Публичный URL Mini App" "$(env_get MINIAPP_PUBLIC_URL 'http://127.0.0.1:8082/')" 1 0 "url"
            MINIAPP_PUBLIC_URL_VALUE="$PROMPT_VALUE"
            TRUSTED_PROXIES_VALUE="$(env_get TRUSTED_PROXIES '127.0.0.1,::1')"
            ;;
        egames)
            prompt_value "Адрес привязки backend для eGames Nginx" "$(env_get WEB_SERVER_BIND '127.0.0.1:8080')" 0 0 "bind"
            WEB_SERVER_BIND_VALUE="$PROMPT_VALUE"
            prompt_value "Адрес привязки frontend для eGames Nginx" "$(env_get FRONTEND_BIND '127.0.0.1:8082')" 0 0 "bind"
            FRONTEND_BIND_VALUE="$PROMPT_VALUE"
            WEBHOOK_PUBLIC_URL_VALUE="$(env_get WEBHOOK_PUBLIC_URL "https://$WEBHOOK_HOST_VALUE")"
            MINIAPP_PUBLIC_URL_VALUE="$(env_get MINIAPP_PUBLIC_URL "https://$MINIAPP_HOST_VALUE/")"
            ;;
    esac
}

download_split_reference_files() {
    case "$FRONTEND_BACKEND_MODE_VALUE" in
        protected-upstream)
            mkdir -p "$TARGET_DIR/split-protected-upstream"
            download_raw_file "deploy/examples/split-protected-upstream/frontend.docker-compose.yml" "split-protected-upstream/frontend.docker-compose.yml" 0 || return 1
            download_raw_file "deploy/examples/split-protected-upstream/backend.docker-compose.yml" "split-protected-upstream/backend.docker-compose.yml" 0 || return 1
            download_raw_file "deploy/examples/split-protected-upstream/.env.frontend.example" "split-protected-upstream/.env.frontend.example" 0 || return 1
            download_raw_file "deploy/examples/split-protected-upstream/.env.backend.example" "split-protected-upstream/.env.backend.example" 0 || return 1
            download_raw_file "deploy/examples/split-protected-upstream/README.md" "split-protected-upstream/README.md" 0 || return 1
            ;;
        rathole)
            mkdir -p "$TARGET_DIR/rathole"
            download_raw_file "deploy/examples/rathole/frontend-server.docker-compose.yml" "rathole/frontend-server.docker-compose.yml" 0 || return 1
            download_raw_file "deploy/examples/rathole/backend-server.override.yml" "rathole/backend-server.override.yml" 0 || return 1
            download_raw_file "deploy/examples/rathole/README.md" "rathole/README.md" 0 || return 1
            render_rathole_configs
            ;;
    esac
}

render_rathole_configs() {
    [ "$FRONTEND_BACKEND_MODE_VALUE" = "rathole" ] || return 0
    mkdir -p "$TARGET_DIR/rathole"
    token="${RATHOLE_SERVICE_TOKEN_VALUE:-$(env_get RATHOLE_SERVICE_TOKEN '')}"
    [ -n "$token" ] || token="$(secret_hex 32)"
    remote="${RATHOLE_CONTROL_REMOTE_VALUE:-$(env_get RATHOLE_CONTROL_REMOTE frontend.example.com:2333)}"
    service_port="${RATHOLE_SERVICE_PORT_VALUE:-$(env_get RATHOLE_SERVICE_PORT 18081)}"
    cat > "$TARGET_DIR/rathole/rathole.server.toml" <<EOF
[server]
bind_addr = "0.0.0.0:2333"

[server.services.webapp-api]
token = "$token"
bind_addr = "0.0.0.0:$service_port"
EOF
    cat > "$TARGET_DIR/rathole/rathole.client.toml" <<EOF
[client]
remote_addr = "$remote"

[client.services.webapp-api]
token = "$token"
local_addr = "backend:8081"
EOF
    if [ "$INSTALL_NODE_ROLE_VALUE" = "frontend-node" ]; then
        cp "$TARGET_DIR/rathole/rathole.server.toml" "$TARGET_DIR/rathole.server.toml"
    fi
    ok "Rathole TOML сохранены в $TARGET_DIR/rathole/."
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
    show_env_value INSTALL_NODE_ROLE "$INSTALL_NODE_ROLE_VALUE"
    show_env_value FRONTEND_BACKEND_MODE "$FRONTEND_BACKEND_MODE_VALUE"
    show_env_value WEBAPP_API_BASE_URL "$WEBAPP_API_BASE_URL_VALUE"
    show_env_value WEBAPP_BACKEND_UPSTREAM "$WEBAPP_BACKEND_UPSTREAM_VALUE"
    show_env_value WEBAPP_BACKEND_UPSTREAM_HOST "$WEBAPP_BACKEND_UPSTREAM_HOST_VALUE"
    show_env_value MINISHOP_EDGE_TOKEN "$MINISHOP_EDGE_TOKEN_VALUE"
    show_env_value MINISHOP_EDGE_TOKEN_HEADER "$MINISHOP_EDGE_TOKEN_HEADER_VALUE"
    show_env_value WEB_SERVER_BIND "$WEB_SERVER_BIND_VALUE"
    show_env_value WEBAPP_SERVER_BIND "$WEBAPP_SERVER_BIND_VALUE"
    show_env_value FRONTEND_BIND "$FRONTEND_BIND_VALUE"
    show_env_value RATHOLE_IMAGE "$RATHOLE_IMAGE_VALUE"
    show_env_value RATHOLE_CONTROL_BIND "$RATHOLE_CONTROL_BIND_VALUE"
    show_env_value RATHOLE_CONTROL_REMOTE "$RATHOLE_CONTROL_REMOTE_VALUE"
    show_env_value RATHOLE_SERVICE_TOKEN "$RATHOLE_SERVICE_TOKEN_VALUE"
    show_env_value RATHOLE_SERVICE_PORT "$RATHOLE_SERVICE_PORT_VALUE"
    [ "$INSTALL_NODE_ROLE_VALUE" = "frontend-node" ] && return 0
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
    env_line INSTALL_NODE_ROLE "$INSTALL_NODE_ROLE_VALUE" "$output"
    env_line FRONTEND_BACKEND_MODE "$FRONTEND_BACKEND_MODE_VALUE" "$output"
    env_line WEBAPP_API_BASE_URL "$WEBAPP_API_BASE_URL_VALUE" "$output"
    env_line WEBAPP_BACKEND_UPSTREAM "$WEBAPP_BACKEND_UPSTREAM_VALUE" "$output"
    env_line WEBAPP_BACKEND_UPSTREAM_HOST "$WEBAPP_BACKEND_UPSTREAM_HOST_VALUE" "$output"
    env_line MINISHOP_EDGE_TOKEN "$MINISHOP_EDGE_TOKEN_VALUE" "$output"
    env_line MINISHOP_EDGE_TOKEN_HEADER "$MINISHOP_EDGE_TOKEN_HEADER_VALUE" "$output"
    env_line HTTP_BIND "$HTTP_BIND_VALUE" "$output"
    env_line HTTPS_BIND "$HTTPS_BIND_VALUE" "$output"
    env_line WEB_SERVER_BIND "$WEB_SERVER_BIND_VALUE" "$output"
    env_line WEBAPP_SERVER_BIND "$WEBAPP_SERVER_BIND_VALUE" "$output"
    env_line FRONTEND_BIND "$FRONTEND_BIND_VALUE" "$output"
    env_line RATHOLE_IMAGE "$RATHOLE_IMAGE_VALUE" "$output"
    env_line RATHOLE_CONTROL_BIND "$RATHOLE_CONTROL_BIND_VALUE" "$output"
    env_line RATHOLE_CONTROL_REMOTE "$RATHOLE_CONTROL_REMOTE_VALUE" "$output"
    env_line RATHOLE_SERVICE_TOKEN "$RATHOLE_SERVICE_TOKEN_VALUE" "$output"
    env_line RATHOLE_SERVICE_PORT "$RATHOLE_SERVICE_PORT_VALUE" "$output"
    env_line PANGOLIN_ENDPOINT "$PANGOLIN_ENDPOINT_VALUE" "$output"
    env_line NEWT_ID "$NEWT_ID_VALUE" "$output"
    env_line NEWT_SECRET "$NEWT_SECRET_VALUE" "$output"

    if [ "$INSTALL_NODE_ROLE_VALUE" = "frontend-node" ]; then
        append_preserved_env "$output"
        return 0
    fi

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
    section "Проверка .env"
    display_env_summary
    if ! confirm "Записать .env сейчас?" 1; then
        warn "Запись .env пропущена."
        return 0
    fi
    tmp="$TARGET_DIR/.env.tmp.$$"
    render_env_file "$tmp"
    if [ -e "$ENV_PATH" ]; then
        backup=$(backup_path "$ENV_PATH")
        cp "$ENV_PATH" "$backup"
        info "Бэкап $ENV_PATH сохранен как $(basename "$backup")"
    fi
    mv "$tmp" "$ENV_PATH"
    ok "Файл $ENV_PATH записан."
}

adjust_data_mount_permissions() {
    data_dir="$1"
    if command -v chown >/dev/null 2>&1; then
        if ! chown -R "$APP_UID:$APP_GID" "$data_dir" 2>/dev/null; then
            warn "Не удалось выполнить chown для $data_dir. Выполните вручную: sudo chown -R $APP_UID:$APP_GID $data_dir"
        else
            ok "Владелец $data_dir обновлен на $APP_UID:$APP_GID."
        fi
    fi
    chmod u+rwx "$data_dir" 2>/dev/null || true
}

prepare_data_mount() {
    section "Подготовка каталога data"
    data_dir="$TARGET_DIR/data"
    created=0
    if [ ! -d "$data_dir" ]; then
        mkdir -p "$data_dir" || return 1
        created=1
    fi

    info "Контейнеры Minishop пишут runtime-файлы в $data_dir от пользователя $APP_UID:$APP_GID."
    info "Если владелец другой, могут не сохраняться бэкапы, тарифы, загрузки и другие данные приложения."

    if [ "$created" = "1" ]; then
        adjust_data_mount_permissions "$data_dir"
        ok "Каталог $data_dir создан и подготовлен для записи из контейнеров."
        return 0
    fi

    info "Каталог $data_dir уже существует."
    if confirm "Обновить владельца $data_dir на $APP_UID:$APP_GID для записи из контейнеров?" 1; then
        adjust_data_mount_permissions "$data_dir"
    fi
}

is_ipv4_address() {
    is_valid_ipv4_address "$1"
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
        caddy|angie|nginx|egames)
            ;;
        *)
            return 0
            ;;
    esac

    hosts=$(unique_public_hosts)
    [ -n "$hosts" ] || return 0

    section "Проверка DNS"
    if ! confirm "Проверить A-записи для WEBHOOK_HOST и MINIAPP_HOST сейчас?" 1; then
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
            warn "У $host не видно A-записи."
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
        warn "Сертификаты и публичные webhook могут не заработать, пока DNS не указывает на этот сервер или прокси перед ним."
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
    ok "Установлен deploy hook certbot: $hook"
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
            prompt_value "Email аккаунта Let's Encrypt" "$(env_get LETSENCRYPT_EMAIL '')" 1 0 "" || return 1
            le_email="$PROMPT_VALUE"
            prompt_value "Cloudflare DNS API token" "$(env_get CLOUDFLARE_DNS_API_TOKEN '')" 1 1 "" || return 1
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
                PYTHONWARNINGS=ignore::PendingDeprecationWarning certbot certonly \
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
            prompt_value "Email аккаунта Let's Encrypt" "$(env_get LETSENCRYPT_EMAIL '')" 1 0 "" || return 1
            le_email="$PROMPT_VALUE"
            printf '%s\n' "$hosts" | while IFS= read -r host; do
                info "Запрашиваю сертификат для $host через standalone HTTP-01."
                PYTHONWARNINGS=ignore::PendingDeprecationWarning certbot certonly \
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

run_privileged() {
    if [ "$(id -u 2>/dev/null || printf '1')" = "0" ]; then
        "$@"
        return $?
    fi
    if command -v sudo >/dev/null 2>&1; then
        sudo "$@"
        return $?
    fi
    fail "Нужны права root, но sudo не найден. Запустите команду от root или установите sudo."
    return 1
}

detect_compose_command() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        COMPOSE_STYLE="docker"
        return 0
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_STYLE="docker-compose"
        return 0
    fi
    return 1
}

ensure_docker_daemon() {
    if ! command -v docker >/dev/null 2>&1; then
        return 0
    fi

    if docker info >/dev/null 2>&1; then
        return 0
    fi

    warn "Docker установлен, но daemon сейчас недоступен."
    if command -v systemctl >/dev/null 2>&1 && confirm "Попробовать запустить docker.service сейчас?" 1; then
        run_privileged systemctl enable --now docker >/dev/null 2>&1 || run_privileged systemctl start docker >/dev/null 2>&1 || true
        if docker info >/dev/null 2>&1; then
            ok "Docker daemon запущен."
            return 0
        fi
    fi

    fail "Docker daemon не отвечает."
    info "Проверьте сервис: sudo systemctl status docker"
    current_user="${USER:-${LOGNAME:-your_user}}"
    info "Если Docker работает, но не хватает прав, добавьте пользователя в группу docker: sudo usermod -aG docker $current_user"
    info "После добавления в группу нужно перелогиниться или открыть новую SSH-сессию."
    return 1
}

install_compose_with_package_manager() {
    if command -v apt-get >/dev/null 2>&1; then
        info "Найден apt-get. Пробую установить Docker Compose через пакеты."
        run_privileged apt-get update || warn "apt-get update завершился с предупреждением; всё равно пробую установку пакетов."
        for package_set in "docker-compose-plugin" "docker-compose-v2" "docker.io docker-compose-v2" "docker.io docker-compose-plugin" "docker-compose"; do
            info "Пробую: apt-get install -y $package_set"
            if run_privileged apt-get install -y $package_set; then
                detect_compose_command && return 0
            fi
        done
        return 1
    fi

    if command -v dnf >/dev/null 2>&1; then
        info "Найден dnf. Пробую установить Docker Compose через пакеты."
        for package_set in "docker-compose-plugin" "docker-compose"; do
            if run_privileged dnf install -y $package_set; then
                detect_compose_command && return 0
            fi
        done
        return 1
    fi

    if command -v yum >/dev/null 2>&1; then
        info "Найден yum. Пробую установить Docker Compose через пакеты."
        for package_set in "docker-compose-plugin" "docker-compose"; do
            if run_privileged yum install -y $package_set; then
                detect_compose_command && return 0
            fi
        done
        return 1
    fi

    if command -v apk >/dev/null 2>&1; then
        info "Найден apk. Пробую установить Docker Compose через пакеты."
        for package_set in "docker-cli-compose" "docker-compose"; do
            if run_privileged apk add --no-cache $package_set; then
                detect_compose_command && return 0
            fi
        done
        return 1
    fi

    if command -v pacman >/dev/null 2>&1; then
        info "Найден pacman. Пробую установить Docker Compose через пакеты."
        if run_privileged pacman -Sy --noconfirm docker-compose; then
            detect_compose_command && return 0
        fi
        return 1
    fi

    return 1
}

compose_binary_arch() {
    case "$(uname -m 2>/dev/null)" in
        x86_64|amd64)
            printf 'x86_64'
            ;;
        aarch64|arm64)
            printf 'aarch64'
            ;;
        armv7l|armv7*)
            printf 'armv7'
            ;;
        *)
            return 1
            ;;
    esac
}

install_compose_binary_plugin() {
    if ! command -v docker >/dev/null 2>&1; then
        warn "Docker CLI не найден, поэтому скачать Compose как docker-плагин не получится."
        return 1
    fi
    arch=$(compose_binary_arch || true)
    if [ -z "$arch" ]; then
        warn "Не удалось определить архитектуру CPU для binary-install Docker Compose."
        return 1
    fi
    os_name=$(uname -s 2>/dev/null | tr '[:upper:]' '[:lower:]')
    [ -n "$os_name" ] || os_name="linux"
    if [ -n "${DOCKER_CONFIG:-}" ]; then
        plugin_dir="$DOCKER_CONFIG/cli-plugins"
    elif [ -n "${HOME:-}" ]; then
        plugin_dir="$HOME/.docker/cli-plugins"
    else
        warn "Не удалось определить HOME/DOCKER_CONFIG для установки Docker CLI plugin."
        return 1
    fi

    mkdir -p "$plugin_dir" || return 1
    plugin_path="$plugin_dir/docker-compose"
    tmp="$plugin_path.tmp.$$"
    url="https://github.com/docker/compose/releases/latest/download/docker-compose-$os_name-$arch"
    info "Пробую скачать Docker Compose CLI plugin: $url"
    if ! download_to "$url" "$tmp"; then
        rm -f "$tmp"
        return 1
    fi
    chmod +x "$tmp" || {
        rm -f "$tmp"
        return 1
    }
    mv "$tmp" "$plugin_path" || return 1
    docker compose version >/dev/null 2>&1
}

install_docker_compose() {
    section "Установка Docker Compose"
    warn "Docker Compose не найден: нет команды docker compose и fallback docker-compose."
    if ! confirm "Попробовать установить Docker Compose автоматически?" 1; then
        fail "Без Docker Compose wizard не сможет скачать образы, запустить стек или выполнить миграции."
        info "Установите Docker Engine и Docker Compose plugin, затем запустите wizard повторно."
        return 1
    fi

    if install_compose_with_package_manager || install_compose_binary_plugin; then
        if detect_compose_command; then
            ok "Docker Compose установлен: $(compose version 2>/dev/null | head -n 1)"
            return 0
        fi
    fi

    fail "Автоматически установить Docker Compose не удалось."
    info "Установите Docker Compose вручную и повторите запуск. Для Ubuntu/Debian обычно подходит: sudo apt-get update && sudo apt-get install -y docker-compose-plugin"
    info "Если Docker Engine тоже не установлен, сначала установите Docker Engine, затем Compose plugin."
    return 1
}

require_docker() {
    if ! detect_compose_command; then
        install_docker_compose || return 1
    fi
    detect_compose_command || {
        fail "Docker Compose не найден после установки."
        return 1
    }
    ensure_docker_daemon || return 1
}

compose_bind_value() {
    key="$1"
    value=""
    case "$key" in
        HTTP_BIND) value="$HTTP_BIND_VALUE" ;;
        HTTPS_BIND) value="$HTTPS_BIND_VALUE" ;;
        WEB_SERVER_BIND) value="$WEB_SERVER_BIND_VALUE" ;;
        WEBAPP_SERVER_BIND) value="$WEBAPP_SERVER_BIND_VALUE" ;;
        FRONTEND_BIND) value="$FRONTEND_BIND_VALUE" ;;
        RATHOLE_CONTROL_BIND) value="$RATHOLE_CONTROL_BIND_VALUE" ;;
    esac
    if [ -z "$value" ]; then
        value=$(env_get "$key" "")
    fi
    printf '%s' "$value"
}

print_current_bind_settings() {
    printed=0
    for key in HTTP_BIND HTTPS_BIND WEB_SERVER_BIND WEBAPP_SERVER_BIND FRONTEND_BIND RATHOLE_CONTROL_BIND; do
        value=$(compose_bind_value "$key")
        [ -n "$value" ] || continue
        if [ "$printed" = "0" ]; then
            info "Текущие значения публикации портов:"
            printed=1
        fi
        info "  $key=$value"
    done
}

validate_bind_settings() {
    failed=0
    for key in HTTP_BIND HTTPS_BIND WEB_SERVER_BIND WEBAPP_SERVER_BIND FRONTEND_BIND RATHOLE_CONTROL_BIND; do
        value=$(compose_bind_value "$key")
        [ -n "$value" ] || continue
        if ! is_bind_address "$value"; then
            fail "Некорректное значение $key=$value"
            print_validation_hint bind "$value"
            failed=1
        fi
    done
    if [ "$failed" != "0" ]; then
        info "Исправьте значения в $ENV_PATH или перезапустите wizard и оставьте рекомендованные значения по умолчанию."
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

host_user_spec() {
    uid=$(id -u 2>/dev/null || printf '')
    gid=$(id -g 2>/dev/null || printf '')
    if [ -n "$uid" ] && [ -n "$gid" ]; then
        printf '%s:%s' "$uid" "$gid"
    else
        printf '%s:%s' "$APP_UID" "$APP_GID"
    fi
}

explain_compose_failure() {
    output_file="$1"
    shift
    log_args=$(mask_compose_log_args "$@")
    fail "Docker Compose вернул ошибку на команде: $log_args"

    if grep -Eiq 'invalid hostPort|invalid host port|invalid.*published.*port|invalid.*containerPort|invalid port' "$output_file"; then
        fail "Docker Compose не смог разобрать публикацию порта."
        info "Самая частая причина: в HTTP_BIND, HTTPS_BIND, WEB_SERVER_BIND, WEBAPP_SERVER_BIND, FRONTEND_BIND или RATHOLE_CONTROL_BIND указан только IP без порта."
        info "Нужно указать PORT или IP:PORT: 80, 0.0.0.0:80, <IP_СЕРВЕРА>:80, 127.0.0.1:8080."
        info "Если хотите слушать все интерфейсы сервера, оставьте 0.0.0.0:PORT."
        print_current_bind_settings
        return 0
    fi

    if grep -Eiq 'address already in use|port is already allocated|Ports are not available|bind: address already in use' "$output_file"; then
        fail "Один из портов уже занят другим процессом или контейнером."
        print_current_bind_settings
        info "Проверьте занятые порты: sudo ss -ltnp | grep -E ':80|:443|:8080|:8082'"
        info "Либо остановите конфликтующий сервис, либо задайте другой порт в соответствующем *_BIND."
        return 0
    fi

    if grep -Eiq 'cannot assign requested address|bind: cannot assign requested' "$output_file"; then
        fail "Указанный IP-адрес не назначен ни одному сетевому интерфейсу этого сервера."
        print_current_bind_settings
        info "Проверьте адреса сервера: ip addr"
        info "Используйте 0.0.0.0:PORT, 127.0.0.1:PORT или реальный IP из вывода ip addr."
        return 0
    fi

    if grep -Eiq 'permission denied.*docker|permission denied while trying to connect|Got permission denied while trying to connect' "$output_file"; then
        fail "Не хватает прав на Docker socket."
        current_user="${USER:-${LOGNAME:-your_user}}"
        info "Запустите wizard от root или добавьте пользователя в группу docker: sudo usermod -aG docker $current_user"
        info "После изменения группы откройте новую SSH-сессию."
        return 0
    fi

    if grep -Eiq 'Cannot connect to the Docker daemon|docker daemon is not running|Is the docker daemon running' "$output_file"; then
        fail "Docker daemon не запущен или недоступен."
        info "Проверьте сервис: sudo systemctl status docker"
        info "Попробуйте запустить: sudo systemctl enable --now docker"
        return 0
    fi

    if grep -Eiq 'pull access denied|requested access to the resource is denied|manifest unknown|no matching manifest|not found: manifest' "$output_file"; then
        fail "Не удалось скачать Docker-образ."
        info "Проверьте IMAGE_TAG в .env. Для стабильного запуска обычно оставляют latest или опубликованный тег релиза."
        info "Если образы находятся в приватном registry, сначала выполните docker login."
        return 0
    fi

    if grep -Eiq 'temporary failure|i/o timeout|TLS handshake timeout|Could not resolve|network is unreachable|connection refused|proxyconnect tcp' "$output_file"; then
        fail "Похоже на сетевую ошибку при обращении к registry или Docker API."
        info "Проверьте DNS, доступ в интернет с сервера, proxy/firewall и повторите команду."
        return 0
    fi

    if grep -Eiq 'variable is not set|required variable|set .+ in \.env' "$output_file"; then
        fail "Docker Compose не нашел обязательную переменную окружения."
        info "Проверьте файл $ENV_PATH: обязательные значения не должны быть пустыми."
        info "Проще всего снова пройти wizard и разрешить ему записать .env."
        return 0
    fi

    if grep -Eiq 'postgres.*unhealthy|dependency failed.*postgres|container .*postgres.*unhealthy' "$output_file"; then
        fail "PostgreSQL не прошел healthcheck."
        explain_postgres_password_mismatch
        return 0
    fi

    if grep -Eiq "service \"migrate\" didn't complete successfully|service \"migrate\" did not complete successfully|migrate.*exit [1-9]" "$output_file"; then
        fail "Сервис migrate завершился с ошибкой."
        info "Ниже последние строки логов migrate; в них обычно указана реальная причина: настройки, тарифы или схема БД."
        migrate_logs=$(compose logs --tail 120 migrate 2>/dev/null || true)
        [ -n "$migrate_logs" ] && printf '%s\n' "$migrate_logs"
        if printf '%s\n' "$migrate_logs" | grep -Eiq 'InvalidPasswordError|password authentication failed'; then
            explain_postgres_password_mismatch
        fi
        return 0
    fi

    if grep -Eiq 'yaml:|mapping values are not allowed|did not find expected key|found character that cannot start any token' "$output_file"; then
        fail "Compose-файл выглядит синтаксически некорректным."
        info "Если файл редактировался вручную, сравните его с исходным примером или заново скачайте профиль через пункт меню обновления файлов."
        return 0
    fi

    info "Подсказка: посмотрите полный вывод выше. Если причина не очевидна, сохраните его и проверьте docker compose config в каталоге установки."
}

run_compose_checked() {
    if [ -n "$TARGET_DIR" ]; then
        mkdir -p "$TARGET_DIR/$INSTALL_STATE_DIR" 2>/dev/null || true
        output_file="$TARGET_DIR/$INSTALL_STATE_DIR/compose-last-error.log"
    else
        output_file="${TMPDIR:-/tmp}/remnawave-minishop-compose-last-error.log"
    fi
    tmp="$output_file.tmp.$$"
    if run_compose "$@" > "$tmp" 2>&1; then
        cat "$tmp"
        rm -f "$tmp"
        return 0
    fi
    status=$?
    cat "$tmp"
    mv "$tmp" "$output_file" 2>/dev/null || cp "$tmp" "$output_file" 2>/dev/null || true
    [ -f "$tmp" ] && rm -f "$tmp"
    explain_compose_failure "$output_file" "$@"
    if [ -f "$output_file" ]; then
        info "Полный вывод последней ошибки сохранен: $output_file"
    fi
    return "$status"
}

explain_postgres_password_mismatch() {
    fail "PostgreSQL не принимает POSTGRES_USER/POSTGRES_PASSWORD из текущего .env."
    info "Чаще всего это значит, что Docker volume базы уже был создан раньше с другим паролем."
    info "Для настоящей чистой установки удалите старый DB volume через wizard или смените COMPOSE_PROJECT_NAME."
    info "Если в базе есть нужные данные, верните старый POSTGRES_PASSWORD в .env и не удаляйте volume."
}

target_postgres_volume() {
    printf '%s-db-data' "$(target_compose_project)"
}

check_target_postgres_auth() {
    (cd "$TARGET_DIR" && compose exec -T postgres sh -lc \
        'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT 1" | grep -qx 1')
}

wait_target_postgres_auth() {
    attempt=1
    while [ "$attempt" -le 30 ]; do
        if check_target_postgres_auth >/dev/null 2>&1; then
            ok "PostgreSQL принимает логин/пароль из .env."
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    return 1
}

preflight_existing_postgres_volume() {
    volume=$(target_postgres_volume)
    if ! volume_exists "$volume"; then
        return 0
    fi
    if volume_is_empty "$volume"; then
        return 0
    fi

    warn "Найден существующий Docker volume PostgreSQL: $volume"
    warn "Если вы проходите wizard заново, это может быть не чистая установка: данные БД живут вне папки $TARGET_DIR."

    (cd "$TARGET_DIR" && run_compose_checked up -d postgres redis) || return 1
    if wait_target_postgres_auth; then
        return 0
    fi

    explain_postgres_password_mismatch
    if confirm "Удалить volume $volume и начать с пустой БД? Все данные в этой БД будут удалены." 0; then
        (cd "$TARGET_DIR" && run_compose down) || true
        docker volume rm "$volume" >/dev/null || {
            fail "Не удалось удалить Docker volume: $volume"
            return 1
        }
        ok "Docker volume $volume удален. При следующем старте PostgreSQL создаст пустую БД с текущим .env."
        return 0
    fi

    fail "Запуск остановлен, чтобы не продолжать с несовпадающим паролем PostgreSQL."
    return 1
}

reset_target_postgres_volume() {
    section "Пересоздание целевого PostgreSQL volume"
    volume=$(target_postgres_volume)
    (cd "$TARGET_DIR" && run_compose down) || true
    if volume_exists "$volume"; then
        docker volume rm "$volume" >/dev/null || {
            fail "Не удалось удалить Docker volume: $volume"
            return 1
        }
        ok "Docker volume $volume удален. PostgreSQL будет создан заново с текущими POSTGRES_* из .env."
    else
        info "Целевой DB volume $volume еще не создан."
    fi
    (cd "$TARGET_DIR" && run_compose_checked up -d postgres redis) || return 1
    wait_target_postgres || return 1
}

start_stack() {
    pull="${1:-1}"
    skip_existing_volume_preflight="${2:-0}"
    section "Запуск Docker Compose стека"
    [ -n "$ENV_PATH" ] || ENV_PATH="$TARGET_DIR/.env"
    validate_bind_settings || return 1
    require_docker || return 1
    if [ "$pull" = "1" ]; then
        (cd "$TARGET_DIR" && run_compose_checked pull) || return 1
    fi
    if [ "$INSTALL_NODE_ROLE_VALUE" != "frontend-node" ] && [ "$skip_existing_volume_preflight" != "1" ]; then
        preflight_existing_postgres_volume || return 1
    fi
    (cd "$TARGET_DIR" && run_compose_checked up -d) || return 1
    (cd "$TARGET_DIR" && run_compose ps) || true
    validate_reverse_proxy_runtime || return 1
    ok "Команда запуска стека выполнена."
}

validate_stack() {
    section "Проверка стека"
    [ -n "$ENV_PATH" ] || ENV_PATH="$TARGET_DIR/.env"
    validate_bind_settings || return 1
    require_docker || return 1
    (cd "$TARGET_DIR" && run_compose_checked ps) || true
    (cd "$TARGET_DIR" && run_compose logs --tail 80 migrate) || true
    validate_reverse_proxy_runtime || return 1
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

unset_env_file_value() {
    file="$1"
    key="$2"
    [ -f "$file" ] || return 0
    tmp="$file.tmp.$$"
    awk -v key="$key" '
        $0 ~ "^[[:space:]]*" key "=" { next }
        { print }
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
    section "Настройка обратного прокси eGames"
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
        fail "Для настройки обратного прокси eGames нужны WEBHOOK_HOST и MINIAPP_HOST."
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
            warn "Проверка конфига Nginx не прошла; восстанавливаю $backup"
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

ensure_target_network_exists() {
    target_network="$(target_network_name)"
    if docker network inspect "$target_network" >/dev/null 2>&1; then
        return 0
    fi
    info "Docker-сеть $target_network еще не создана; подготавливаю стек без запуска, чтобы Docker Compose создал ее."
    prepare_compose_without_starting_apps || return 1
    docker network inspect "$target_network" >/dev/null 2>&1 || {
        fail "Docker-сеть $target_network не появилась после подготовки стека."
        return 1
    }
}

connect_proxy_to_target_network() {
    proxy_name="$1"
    target_network="$(target_network_name)"
    if docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$proxy_name" 2>/dev/null | grep -Fx "$target_network" >/dev/null 2>&1; then
        ok "Контейнер $proxy_name уже подключен к Docker-сети $target_network."
        return 0
    fi
    docker network connect "$target_network" "$proxy_name" || {
        fail "Не удалось подключить $proxy_name к Docker-сети $target_network."
        return 1
    }
    ok "Контейнер $proxy_name подключен к Docker-сети $target_network."
}

strip_managed_block() {
    awk '
        /^# BEGIN remnawave-minishop managed by install.sh$/ { managed = 1; next }
        /^# END remnawave-minishop managed by install.sh$/ { managed = 0; next }
        managed { next }
        { print }
    ' "$1" > "$2"
}

container_nginx_first_value() {
    proxy_name="$1"
    nginx_key="$2"
    docker exec "$proxy_name" sh -c "grep -rhE '^[[:space:]]*$nginx_key[[:space:]]' /etc/nginx 2>/dev/null | head -n 1" 2>/dev/null |
        awk '{ value = $2; gsub(/[";]/, "", value); print value; exit }'
}

nginx_container_confd_host_dir() {
    confd_source=$(container_mount_source "$1" /etc/nginx/conf.d)
    if [ -n "$confd_source" ] && [ -d "$confd_source" ]; then
        printf '%s' "$confd_source"
        return 0
    fi
    etc_source=$(container_mount_source "$1" /etc/nginx)
    if [ -n "$etc_source" ] && [ -d "$etc_source/conf.d" ]; then
        printf '%s/conf.d' "$etc_source"
        return 0
    fi
    return 1
}

nginx_container_confd_file_mount() {
    docker inspect -f '{{range .Mounts}}{{.Destination}}|{{.Source}}{{"\n"}}{{end}}' "$1" 2>/dev/null |
        awk -F'|' '$1 ~ /^\/etc\/nginx\/conf\.d\/.+/ { print $2; exit }'
}

render_generic_nginx_server_block() {
    server_host="$1"
    server_upstream="$2"
    listen_directive="$3"
    ssl_lines="$4"
    use_resolver="$5"
    upstream_var="$6"
    if [ "$use_resolver" = "1" ]; then
        proxy_lines="        resolver 127.0.0.11 valid=30s ipv6=off;
        set \$$upstream_var $server_upstream;
        proxy_pass \$$upstream_var;"
    else
        proxy_lines="        proxy_pass $server_upstream;"
    fi
    cat <<EOF
server {
    server_name $server_host;
    $listen_directive
$ssl_lines
    client_max_body_size 20m;

    location / {
$proxy_lines
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
EOF
}

render_generic_nginx_servers() {
    render_output="$1"
    webhook_host="$2"
    miniapp_host="$3"
    backend_upstream="$4"
    frontend_upstream="$5"
    ssl_cert="$6"
    ssl_key="$7"
    use_resolver="$8"
    if [ -n "$ssl_cert" ]; then
        listen_directive="listen 443 ssl;"
        ssl_lines="    ssl_certificate \"$ssl_cert\";
    ssl_certificate_key \"$ssl_key\";
"
    else
        listen_directive="listen 80;"
        ssl_lines=""
    fi
    {
        printf '# BEGIN remnawave-minishop managed by install.sh\n'
        render_generic_nginx_server_block "$webhook_host" "$backend_upstream" "$listen_directive" "$ssl_lines" "$use_resolver" minishop_backend
        printf '\n'
        render_generic_nginx_server_block "$miniapp_host" "$frontend_upstream" "$listen_directive" "$ssl_lines" "$use_resolver" minishop_frontend
        printf '# END remnawave-minishop managed by install.sh\n'
    } >> "$render_output"
}

render_generic_caddy_block() {
    cat >> "$1" <<EOF

# BEGIN remnawave-minishop managed by install.sh
$2 {
    encode zstd gzip
    reverse_proxy $4
}

$3 {
    encode zstd gzip
    reverse_proxy $5
}
# END remnawave-minishop managed by install.sh
EOF
}

apply_nginx_container_config() {
    if ! docker exec "$1" nginx -t; then
        return 1
    fi
    docker exec "$1" nginx -s reload || docker restart "$1" >/dev/null
}

attach_generic_nginx_proxy() {
    proxy_name="$1"
    webhook_host="$2"
    miniapp_host="$3"

    if container_uses_host_network "$proxy_name"; then
        backend_upstream="http://127.0.0.1:$(bind_port "${WEB_SERVER_BIND_VALUE:-$(env_get WEB_SERVER_BIND '127.0.0.1:8080')}")"
        frontend_upstream="http://127.0.0.1:$(bind_port "${FRONTEND_BIND_VALUE:-$(env_get FRONTEND_BIND '127.0.0.1:8082')}")"
        use_resolver=0
        info "Контейнер $proxy_name использует host-сеть; проксирую на локальные порты Minishop."
    else
        ensure_target_network_exists || return 1
        connect_proxy_to_target_network "$proxy_name" || return 1
        backend_upstream="http://backend:8080"
        frontend_upstream="http://frontend:80"
        use_resolver=1
        info "Проксирую на сервисы backend/frontend по именам внутри общей Docker-сети."
    fi

    ssl_cert=$(container_nginx_first_value "$proxy_name" ssl_certificate || true)
    ssl_key=$(container_nginx_first_value "$proxy_name" ssl_certificate_key || true)
    if [ -n "$ssl_cert" ] && [ -n "$ssl_key" ]; then
        info "Использую существующий сертификат Nginx: $ssl_cert"
        warn "Убедитесь, что сертификат покрывает $webhook_host и $miniapp_host (например, wildcard)."
    else
        warn "Не нашел ssl_certificate в конфиге контейнера $proxy_name."
        prompt_value "Путь к fullchain.pem внутри контейнера (пусто = слушать HTTP :80 без TLS)" "" 0 0 ""
        ssl_cert="$PROMPT_VALUE"
        if [ -n "$ssl_cert" ]; then
            prompt_value "Путь к privkey.pem внутри контейнера" "" 1 0 ""
            ssl_key="$PROMPT_VALUE"
        else
            ssl_key=""
            warn "Серверные блоки будут слушать порт 80: TLS должен терминироваться выше по цепочке."
        fi
    fi

    confd_dir=$(nginx_container_confd_host_dir "$proxy_name" || true)
    if [ -n "$confd_dir" ]; then
        snippet_path="$confd_dir/remnawave-minishop.conf"
        snippet_backup=""
        if [ -e "$snippet_path" ]; then
            snippet_backup=$(backup_path "$snippet_path")
            cp "$snippet_path" "$snippet_backup"
            info "Бэкап $snippet_path сохранен как $(basename "$snippet_backup")"
        fi
        tmp="$snippet_path.tmp.$$"
        : > "$tmp"
        render_generic_nginx_servers "$tmp" "$webhook_host" "$miniapp_host" "$backend_upstream" "$frontend_upstream" "$ssl_cert" "$ssl_key" "$use_resolver"
        mv "$tmp" "$snippet_path" || {
            rm -f "$tmp"
            return 1
        }
        if apply_nginx_container_config "$proxy_name"; then
            ok "Маршруты Nginx настроены: $webhook_host -> $backend_upstream и $miniapp_host -> $frontend_upstream"
            ok "Записан конфиг $snippet_path"
            return 0
        fi
        warn "Проверка конфига Nginx не прошла; откатываю $snippet_path"
        if [ -n "$snippet_backup" ] && [ -f "$snippet_backup" ]; then
            cp "$snippet_backup" "$snippet_path"
        else
            rm -f "$snippet_path"
        fi
        docker exec "$proxy_name" nginx -s reload >/dev/null 2>&1 || true
        return 1
    fi

    conf_file=$(nginx_container_confd_file_mount "$proxy_name" || true)
    if [ -n "$conf_file" ] && [ -f "$conf_file" ]; then
        conf_backup=$(backup_path "$conf_file")
        cp "$conf_file" "$conf_backup" || return 1
        info "Бэкап $conf_file сохранен как $(basename "$conf_backup")"
        tmp="$conf_file.tmp.$$"
        egames_remove_managed_and_conflicting_servers "$conf_backup" "$tmp" "$webhook_host" "$miniapp_host" || {
            rm -f "$tmp"
            return 1
        }
        printf '\n' >> "$tmp"
        render_generic_nginx_servers "$tmp" "$webhook_host" "$miniapp_host" "$backend_upstream" "$frontend_upstream" "$ssl_cert" "$ssl_key" "$use_resolver"
        if ! cat "$tmp" > "$conf_file"; then
            rm -f "$tmp"
            return 1
        fi
        rm -f "$tmp"
        if apply_nginx_container_config "$proxy_name"; then
            ok "Маршруты Nginx настроены: $webhook_host -> $backend_upstream и $miniapp_host -> $frontend_upstream"
            return 0
        fi
        warn "Проверка конфига Nginx не прошла; восстанавливаю $conf_backup"
        cp "$conf_backup" "$conf_file"
        docker restart "$proxy_name" >/dev/null || true
        return 1
    fi

    mkdir -p "$TARGET_DIR/$INSTALL_STATE_DIR"
    manual_conf="$TARGET_DIR/$INSTALL_STATE_DIR/remnawave-minishop-nginx.conf"
    : > "$manual_conf"
    render_generic_nginx_servers "$manual_conf" "$webhook_host" "$miniapp_host" "$backend_upstream" "$frontend_upstream" "$ssl_cert" "$ssl_key" "$use_resolver"
    warn "Не нашел host-mounted конфиг (conf.d) у контейнера $proxy_name, поэтому не могу записать его автоматически."
    warn "Готовые server-блоки сохранены: $manual_conf"
    info "Добавьте их в http-контекст вашего Nginx (например, скопируйте файл в его conf.d) и выполните nginx -s reload."
    return 0
}

container_angie_first_value() {
    proxy_name="$1"
    angie_key="$2"
    docker exec "$proxy_name" sh -c "grep -rhE '^[[:space:]]*$angie_key[[:space:]]' /etc/angie 2>/dev/null | head -n 1" 2>/dev/null |
        awk '{ value = $2; gsub(/[";]/, "", value); print value; exit }'
}

angie_container_httpd_host_dir() {
    httpd_source=$(container_mount_source "$1" /etc/angie/http.d)
    if [ -n "$httpd_source" ] && [ -d "$httpd_source" ]; then
        printf '%s' "$httpd_source"
        return 0
    fi
    etc_source=$(container_mount_source "$1" /etc/angie)
    if [ -n "$etc_source" ] && [ -d "$etc_source/http.d" ]; then
        printf '%s/http.d' "$etc_source"
        return 0
    fi
    return 1
}

angie_container_httpd_file_mount() {
    docker inspect -f '{{range .Mounts}}{{.Destination}}|{{.Source}}{{"\n"}}{{end}}' "$1" 2>/dev/null |
        awk -F'|' '$1 ~ /^\/etc\/angie\/http\.d\/.+/ { print $2; exit }'
}

apply_angie_container_config() {
    if ! docker exec "$1" angie -t; then
        return 1
    fi
    docker exec "$1" angie -s reload || docker restart "$1" >/dev/null
}

attach_generic_angie_proxy() {
    proxy_name="$1"
    webhook_host="$2"
    miniapp_host="$3"

    if container_uses_host_network "$proxy_name"; then
        backend_upstream="http://127.0.0.1:$(bind_port "${WEB_SERVER_BIND_VALUE:-$(env_get WEB_SERVER_BIND '127.0.0.1:8080')}")"
        frontend_upstream="http://127.0.0.1:$(bind_port "${FRONTEND_BIND_VALUE:-$(env_get FRONTEND_BIND '127.0.0.1:8082')}")"
        use_resolver=0
        info "Контейнер $proxy_name использует host-сеть; проксирую на локальные порты Minishop."
    else
        ensure_target_network_exists || return 1
        connect_proxy_to_target_network "$proxy_name" || return 1
        backend_upstream="http://backend:8080"
        frontend_upstream="http://frontend:80"
        use_resolver=1
        info "Проксирую на сервисы backend/frontend по именам внутри общей Docker-сети."
    fi

    ssl_cert=$(container_angie_first_value "$proxy_name" ssl_certificate || true)
    ssl_key=$(container_angie_first_value "$proxy_name" ssl_certificate_key || true)
    if [ -n "$ssl_cert" ] && [ -n "$ssl_key" ]; then
        info "Использую существующий сертификат Angie: $ssl_cert"
        warn "Убедитесь, что сертификат покрывает $webhook_host и $miniapp_host (например, wildcard)."
    else
        warn "Не нашел ssl_certificate в конфиге контейнера $proxy_name."
        prompt_value "Путь к fullchain.pem внутри контейнера (пусто = слушать HTTP :80 без TLS)" "" 0 0 ""
        ssl_cert="$PROMPT_VALUE"
        if [ -n "$ssl_cert" ]; then
            prompt_value "Путь к privkey.pem внутри контейнера" "" 1 0 ""
            ssl_key="$PROMPT_VALUE"
        else
            ssl_key=""
            warn "Серверные блоки будут слушать порт 80: TLS должен терминироваться выше по цепочке."
        fi
    fi

    httpd_dir=$(angie_container_httpd_host_dir "$proxy_name" || true)
    if [ -n "$httpd_dir" ]; then
        snippet_path="$httpd_dir/remnawave-minishop.conf"
        snippet_backup=""
        if [ -e "$snippet_path" ]; then
            snippet_backup=$(backup_path "$snippet_path")
            cp "$snippet_path" "$snippet_backup"
            info "Бэкап $snippet_path сохранен как $(basename "$snippet_backup")"
        fi
        tmp="$snippet_path.tmp.$$"
        : > "$tmp"
        render_generic_nginx_servers "$tmp" "$webhook_host" "$miniapp_host" "$backend_upstream" "$frontend_upstream" "$ssl_cert" "$ssl_key" "$use_resolver"
        mv "$tmp" "$snippet_path" || {
            rm -f "$tmp"
            return 1
        }
        if apply_angie_container_config "$proxy_name"; then
            ok "Маршруты Angie настроены: $webhook_host -> $backend_upstream и $miniapp_host -> $frontend_upstream"
            ok "Записан конфиг $snippet_path"
            return 0
        fi
        warn "Проверка конфига Angie не прошла; откатываю $snippet_path"
        if [ -n "$snippet_backup" ] && [ -f "$snippet_backup" ]; then
            cp "$snippet_backup" "$snippet_path"
        else
            rm -f "$snippet_path"
        fi
        docker exec "$proxy_name" angie -s reload >/dev/null 2>&1 || true
        return 1
    fi

    conf_file=$(angie_container_httpd_file_mount "$proxy_name" || true)
    if [ -n "$conf_file" ] && [ -f "$conf_file" ]; then
        conf_backup=$(backup_path "$conf_file")
        cp "$conf_file" "$conf_backup" || return 1
        info "Бэкап $conf_file сохранен как $(basename "$conf_backup")"
        tmp="$conf_file.tmp.$$"
        egames_remove_managed_and_conflicting_servers "$conf_backup" "$tmp" "$webhook_host" "$miniapp_host" || {
            rm -f "$tmp"
            return 1
        }
        printf '\n' >> "$tmp"
        render_generic_nginx_servers "$tmp" "$webhook_host" "$miniapp_host" "$backend_upstream" "$frontend_upstream" "$ssl_cert" "$ssl_key" "$use_resolver"
        if ! cat "$tmp" > "$conf_file"; then
            rm -f "$tmp"
            return 1
        fi
        rm -f "$tmp"
        if apply_angie_container_config "$proxy_name"; then
            ok "Маршруты Angie настроены: $webhook_host -> $backend_upstream и $miniapp_host -> $frontend_upstream"
            return 0
        fi
        warn "Проверка конфига Angie не прошла; восстанавливаю $conf_backup"
        cp "$conf_backup" "$conf_file"
        docker restart "$proxy_name" >/dev/null || true
        return 1
    fi

    mkdir -p "$TARGET_DIR/$INSTALL_STATE_DIR"
    manual_conf="$TARGET_DIR/$INSTALL_STATE_DIR/remnawave-minishop-angie.conf"
    : > "$manual_conf"
    render_generic_nginx_servers "$manual_conf" "$webhook_host" "$miniapp_host" "$backend_upstream" "$frontend_upstream" "$ssl_cert" "$ssl_key" "$use_resolver"
    warn "Не нашел host-mounted конфиг (http.d) у контейнера $proxy_name, поэтому не могу записать его автоматически."
    warn "Готовые server-блоки сохранены: $manual_conf"
    info "Добавьте их в http-контекст вашего Angie (например, скопируйте файл в его http.d) и выполните angie -s reload."
    return 0
}

attach_generic_caddy_proxy() {
    proxy_name="$1"
    webhook_host="$2"
    miniapp_host="$3"

    if container_uses_host_network "$proxy_name"; then
        backend_upstream="127.0.0.1:$(bind_port "${WEB_SERVER_BIND_VALUE:-$(env_get WEB_SERVER_BIND '127.0.0.1:8080')}")"
        frontend_upstream="127.0.0.1:$(bind_port "${FRONTEND_BIND_VALUE:-$(env_get FRONTEND_BIND '127.0.0.1:8082')}")"
        info "Контейнер $proxy_name использует host-сеть; проксирую на локальные порты Minishop."
    else
        ensure_target_network_exists || return 1
        connect_proxy_to_target_network "$proxy_name" || return 1
        backend_upstream="backend:8080"
        frontend_upstream="frontend:80"
        info "Проксирую на сервисы backend/frontend по именам внутри общей Docker-сети."
    fi
    info "Caddy сам выпустит сертификаты для $webhook_host и $miniapp_host, если DNS уже указывает на этот сервер."

    caddyfile=$(container_mount_source "$proxy_name" /etc/caddy/Caddyfile)
    if [ -z "$caddyfile" ]; then
        caddy_dir=$(container_mount_source "$proxy_name" /etc/caddy)
        if [ -n "$caddy_dir" ] && [ -f "$caddy_dir/Caddyfile" ]; then
            caddyfile="$caddy_dir/Caddyfile"
        fi
    fi
    if [ -z "$caddyfile" ] || [ ! -f "$caddyfile" ]; then
        mkdir -p "$TARGET_DIR/$INSTALL_STATE_DIR"
        manual_conf="$TARGET_DIR/$INSTALL_STATE_DIR/remnawave-minishop-caddy.conf"
        : > "$manual_conf"
        render_generic_caddy_block "$manual_conf" "$webhook_host" "$miniapp_host" "$backend_upstream" "$frontend_upstream"
        warn "Не нашел host-mounted Caddyfile у контейнера $proxy_name, поэтому не могу записать его автоматически."
        warn "Готовые site-блоки сохранены: $manual_conf"
        info "Добавьте их в ваш Caddyfile и выполните caddy reload."
        return 0
    fi

    caddy_backup=$(backup_path "$caddyfile")
    cp "$caddyfile" "$caddy_backup" || return 1
    info "Бэкап $caddyfile сохранен как $(basename "$caddy_backup")"
    tmp="$caddyfile.tmp.$$"
    strip_managed_block "$caddy_backup" "$tmp" || {
        rm -f "$tmp"
        return 1
    }
    render_generic_caddy_block "$tmp" "$webhook_host" "$miniapp_host" "$backend_upstream" "$frontend_upstream"
    if ! cat "$tmp" > "$caddyfile"; then
        rm -f "$tmp"
        return 1
    fi
    rm -f "$tmp"
    if docker exec "$proxy_name" caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
        docker exec "$proxy_name" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || docker restart "$proxy_name" >/dev/null
        ok "Маршруты Caddy настроены: $webhook_host -> $backend_upstream и $miniapp_host -> $frontend_upstream"
        return 0
    fi
    warn "Проверка Caddyfile не прошла; восстанавливаю $caddy_backup"
    cp "$caddy_backup" "$caddyfile"
    docker exec "$proxy_name" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || docker restart "$proxy_name" >/dev/null || true
    return 1
}

attach_existing_reverse_proxy_container() {
    section "Подключение к существующему Nginx/Angie/Caddy"
    require_docker || return 1
    webhook_host="${WEBHOOK_HOST_VALUE:-$(env_get WEBHOOK_HOST '')}"
    miniapp_host="${MINIAPP_HOST_VALUE:-$(env_get MINIAPP_HOST '')}"
    if [ -z "$webhook_host" ] || [ -z "$miniapp_host" ]; then
        fail "Для подключения к существующему reverse proxy нужны WEBHOOK_HOST и MINIAPP_HOST."
        return 1
    fi

    candidates=$(list_running_proxy_containers || true)
    default_proxy=""
    if [ -n "$candidates" ]; then
        info "Найдены запущенные reverse proxy контейнеры:"
        printf '%s\n' "$candidates" | while IFS= read -r candidate; do
            info "  - $candidate ($(proxy_container_kind "$candidate" || printf 'неизвестный тип'))"
        done
        default_proxy=$(printf '%s\n' "$candidates" | head -n 1)
    else
        warn "Не нашел запущенные Nginx/Angie/Caddy контейнеры автоматически; введите имя вручную."
    fi
    prompt_value "Имя контейнера reverse proxy" "$default_proxy" 1 0 ""
    proxy_name="$PROMPT_VALUE"
    if ! docker_container_exists "$proxy_name"; then
        fail "Контейнер не найден: $proxy_name"
        return 1
    fi

    proxy_kind=$(proxy_container_kind "$proxy_name" || true)
    if [ -z "$proxy_kind" ]; then
        choose "Тип reverse proxy в контейнере $proxy_name" "1" "1|2|3" \
            "1. Nginx" \
            "2. Angie" \
            "3. Caddy" || return 1
        case "$CHOICE_VALUE" in
            1) proxy_kind="nginx" ;;
            2) proxy_kind="angie" ;;
            3) proxy_kind="caddy" ;;
        esac
    fi

    case "$proxy_kind" in
        nginx)
            attach_generic_nginx_proxy "$proxy_name" "$webhook_host" "$miniapp_host"
            ;;
        angie)
            attach_generic_angie_proxy "$proxy_name" "$webhook_host" "$miniapp_host"
            ;;
        caddy)
            attach_generic_caddy_proxy "$proxy_name" "$webhook_host" "$miniapp_host"
            ;;
    esac
}

configure_existing_reverse_proxy() {
    is_egames_profile || return 0
    default_proxy_mode="2"
    if detect_egames_stack; then
        default_proxy_mode="1"
    fi
    choose "Подключение к существующему reverse proxy" "$default_proxy_mode" "1|2|3" \
        "1. Remnawave/eGames Nginx - правка nginx.conf по схеме eGames (unix socket)." \
        "2. Другой запущенный Nginx, Angie или Caddy - универсальное подключение к контейнеру." \
        "3. Пропустить - настрою reverse proxy вручную." || return 1
    case "$CHOICE_VALUE" in
        1)
            configure_egames_reverse_proxy
            ;;
        2)
            attach_existing_reverse_proxy_container
            ;;
        3)
            warn "Настройка reverse proxy пропущена. Направьте WEBHOOK_HOST на backend-порт и MINIAPP_HOST на frontend-порт вручную."
            return 0
            ;;
    esac
}

refresh_egames_nginx_after_migration() {
    is_egames_profile || return 0
    section "Перезапуск eGames Nginx"
    require_docker || {
        warn "Docker недоступен; пропускаю перезапуск eGames Nginx."
        return 0
    }

    nginx_container=$(detect_egames_nginx_container || true)
    if [ -z "$nginx_container" ]; then
        warn "Nginx контейнер eGames не найден; если Mini App отвечает 502, перезапустите Nginx вручную."
        return 0
    fi
    if ! docker inspect "$nginx_container" >/dev/null 2>&1; then
        warn "Nginx контейнер $nginx_container не найден; если Mini App отвечает 502, перезапустите Nginx вручную."
        return 0
    fi

    if ! docker exec "$nginx_container" nginx -t; then
        warn "Проверка конфига Nginx не прошла; оставляю $nginx_container без перезапуска."
        return 0
    fi
    if docker exec "$nginx_container" nginx -s reload; then
        ok "Nginx контейнер $nginx_container перечитал конфиг."
        return 0
    fi
    warn "Reload Nginx не прошел; пробую перезапустить контейнер $nginx_container."
    if docker restart "$nginx_container" >/dev/null; then
        ok "Nginx контейнер $nginx_container перезапущен."
    else
        warn "Не удалось перезапустить $nginx_container. Проверьте его вручную, если Mini App отвечает 502."
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
    info "Мастер установки не меняет отображаемое имя и короткое описание Telegram-бота."
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
        warn "Секрет клиента Telegram OAuth пустой. Настройка BotFather Web Login/OIDC недоступна через Bot API."
    else
        ok "Секрет клиента Telegram OAuth есть в .env."
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
    docker run --rm -v "$1:/data:ro" alpine sh -c \
        'test -z "$(find /data -mindepth 1 -print -quit)"' >/dev/null 2>&1
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

remnashop_source_compose_dir() {
    source_env="$SOURCE_ENV_PATH"
    [ -n "$source_env" ] || source_env=$(detect_remnashop_env_file || true)
    if [ -n "$source_env" ]; then
        source_dir=$(dirname "$source_env")
        if [ -f "$source_dir/docker-compose.yml" ] || [ -f "$source_dir/compose.yml" ] || [ -f "$source_dir/docker-compose.yaml" ]; then
            (cd "$source_dir" && pwd)
            return 0
        fi
    fi
    return 1
}

stop_remnashop_source_stack() {
    section "Остановка старого Remnashop"
    warn "Старый Remnashop использует тот же BOT_TOKEN и может продолжать выполнять фоновые задачи после миграции."
    if ! confirm "Остановить старые контейнеры Remnashop без удаления данных?" 1; then
        warn "Старые контейнеры Remnashop оставлены как есть. Остановите их вручную после проверки Minishop."
        return 0
    fi

    source_dir=$(remnashop_source_compose_dir || true)
    if [ -n "$source_dir" ]; then
        if (cd "$source_dir" && run_compose stop); then
            ok "Docker Compose stack Remnashop остановлен: $source_dir"
            return 0
        fi
        warn "Не удалось остановить Remnashop через docker compose в $source_dir; пробую известные имена контейнеров."
    fi

    stopped=0
    for container in $REMNASHOP_RUNTIME_CONTAINERS; do
        if docker inspect "$container" >/dev/null 2>&1; then
            if docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -q '^true$'; then
                docker stop "$container" >/dev/null || warn "Не удалось остановить $container"
                stopped=1
            fi
        fi
    done
    if [ "$stopped" = "1" ]; then
        ok "Известные контейнеры Remnashop остановлены."
    else
        info "Запущенные контейнеры Remnashop не найдены."
    fi
}

wait_target_postgres() {
    section "Ожидание целевого PostgreSQL"
    if wait_target_postgres_auth; then
        return 0
    fi
    explain_postgres_password_mismatch
    fail "Целевой PostgreSQL не стал готовым с текущими настройками .env."
    return 1
}

reverse_proxy_service_name() {
    profile="$PROFILE_KEY"
    [ -n "$profile" ] || profile=$(env_get DEPLOYMENT_PROFILE "")
    case "$profile" in
        caddy)
            printf 'caddy'
            ;;
        angie)
            printf 'angie'
            ;;
        nginx)
            printf 'nginx'
            ;;
        *)
            return 1
            ;;
    esac
}

compose_service_container_id() {
    service="$1"
    (cd "$TARGET_DIR" && compose ps -q "$service" 2>/dev/null | head -n 1)
}

container_running() {
    [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = "true" ]
}

container_attached_to_target_network() {
    container="$1"
    target_network="$(target_network_name)"
    docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$container" 2>/dev/null |
        grep -Fx "$target_network" >/dev/null 2>&1
}

reverse_proxy_runtime_ready() {
    service="$1"
    container=$(compose_service_container_id "$service" || true)
    [ -n "$container" ] || return 1
    container_running "$container" || return 1
    container_attached_to_target_network "$container" || return 1
    docker port "$container" 80/tcp >/dev/null 2>&1 || return 1
    docker port "$container" 443/tcp >/dev/null 2>&1 || return 1
}

reverse_proxy_upstreams_ready() {
    service="$1"
    container=$(compose_service_container_id "$service" || true)
    [ -n "$container" ] || return 1
    docker exec "$container" sh -lc \
        'wget -qO- http://backend:8080/healthz >/dev/null && wget -qO- http://frontend/health >/dev/null' \
        >/dev/null 2>&1
}

validate_reverse_proxy_runtime() {
    service=$(reverse_proxy_service_name || true)
    [ -n "$service" ] || return 0

    section "Проверка reverse proxy"
    if ! reverse_proxy_runtime_ready "$service"; then
        warn "Контейнер $service не выглядит полностью подключенным: проверяю published ports 80/443 и Docker-сеть."
        warn "Пересоздаю $service, чтобы восстановить публикацию портов и подключение к $(target_network_name)."
        (cd "$TARGET_DIR" && run_compose_checked up -d --force-recreate "$service") || return 1
        sleep 3
    fi

    if ! reverse_proxy_runtime_ready "$service"; then
        fail "Контейнер $service всё еще не публикует 80/443 или не подключен к $(target_network_name)."
        (cd "$TARGET_DIR" && run_compose ps "$service") || true
        info "Проверьте docker inspect, занятые порты и состояние Docker network перед повторным запуском wizard."
        return 1
    fi
    ok "$service публикует 80/443 и подключен к $(target_network_name)."

    if reverse_proxy_upstreams_ready "$service"; then
        ok "$service видит backend:8080 и frontend:80 внутри Docker-сети."
        return 0
    fi

    warn "$service не смог достучаться до backend/frontend по Docker DNS; пересоздаю proxy еще раз."
    (cd "$TARGET_DIR" && run_compose_checked up -d --force-recreate "$service") || return 1
    sleep 3
    if reverse_proxy_upstreams_ready "$service"; then
        ok "$service видит backend:8080 и frontend:80 внутри Docker-сети."
        return 0
    fi

    fail "$service запущен, но не видит backend/frontend внутри Docker-сети."
    info "Проверьте: docker compose ps; docker network inspect $(target_network_name); docker compose logs $service"
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
        info "Бэкап скрипта импорта сохранен как $(basename "$backup")" >&2
    fi
    mv "$tmp" "$importer"
    ok "Скрипт импорта сохранен в кэше: $importer" >&2
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

target_network_name() {
    printf '%s-network' "$(target_compose_project)"
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

    target_network="$(target_network_name)"
    if ! docker network inspect "$target_network" >/dev/null 2>&1; then
        warn "Целевая Docker-сеть $target_network не найдена; исходный контейнер $source_host не подключен автоматически."
        return 0
    fi

    if docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$source_host" | grep -Fx "$target_network" >/dev/null 2>&1; then
        ok "Исходный контейнер $source_host уже подключен к $target_network."
        return 0
    fi

    docker network connect "$target_network" "$source_host" || {
        warn "Не удалось подключить исходный контейнер $source_host к $target_network. Импорт может завершиться ошибкой, если сервис backend его не видит."
        return 0
    }
    ok "Исходный контейнер $source_host подключен к $target_network для импорта."
}

disconnect_local_source_db_from_target_network() {
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

    target_network="$(target_network_name)"
    if ! docker network inspect "$target_network" >/dev/null 2>&1; then
        return 0
    fi
    if ! docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$source_host" | grep -Fx "$target_network" >/dev/null 2>&1; then
        return 0
    fi

    if docker network disconnect "$target_network" "$source_host"; then
        ok "Исходный контейнер $source_host отключен от $target_network после импорта."
    else
        warn "Не удалось отключить исходный контейнер $source_host от $target_network. Проверьте Docker network вручную."
    fi
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
        printf '  Remnawave Panel -> webhook-секрет: %s\n' "$(mask_secret "$panel_secret")"
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

remnashop_post_migration_next_steps() {
    section "Дальнейшие шаги"
    title=$(env_get WEBAPP_TITLE "remnawave-minishop")
    info "Мастер установки не меняет отображаемое имя и короткое описание Telegram-бота."
    if [ -n "$title" ]; then
        info "Можно оставить текущие имя/описание в BotFather или вручную упомянуть там: $title"
    fi

    miniapp_url="${MINIAPP_PUBLIC_URL_VALUE:-$(env_get MINIAPP_PUBLIC_URL '')}"
    [ -n "$miniapp_url" ] || miniapp_url="https://${MINIAPP_HOST_VALUE:-$(env_get MINIAPP_HOST app.example.com)}/"
    oauth_secret=$(env_get TELEGRAM_OAUTH_CLIENT_SECRET "")
    info "В BotFather укажите Mini App URL/domain: $miniapp_url"
    info "Для Web Login / OpenID Connect разрешите:"
    printf '  %s\n' "$miniapp_url"
    printf '  %sauth/telegram/callback\n' "$(printf '%s' "$miniapp_url" | sed 's:/*$:/:' )"
    if [ -z "$oauth_secret" ]; then
        warn "TELEGRAM_OAUTH_CLIENT_SECRET пустой. Если нужен OAuth в браузере, создайте Web Login/OIDC клиент в BotFather и заполните секрет."
    fi

    base_url=$(target_webhook_base_url)
    if [ -z "$base_url" ]; then
        warn "Не удалось определить webhook base URL из .env. Укажите WEBHOOK_HOST или WEBHOOK_PUBLIC_URL и используйте WEBHOOK_BASE_URL + пути ниже."
        base_url="WEBHOOK_BASE_URL"
    fi

    info "Новые URL webhook после миграции:"
    printf '  Telegram: %s/tg/webhook (backend ставит автоматически при старте)\n' "$base_url"
    printf '  Remnawave Panel -> WEBHOOK_URL: %s/webhook/panel\n' "$base_url"
    panel_secret=$(env_get PANEL_WEBHOOK_SECRET "")
    if [ -n "$panel_secret" ]; then
        printf '  Remnawave Panel -> webhook-секрет: %s\n' "$(mask_secret "$panel_secret")"
    else
        warn "PANEL_WEBHOOK_SECRET пустой; задайте его в Minishop и Remnawave Panel."
    fi
    printf '  YooKassa: %s/webhook/yookassa\n' "$base_url"
    printf '  WATA: %s/webhook/wata\n' "$base_url"
    printf '  Crypto Pay: %s/webhook/cryptopay\n' "$base_url"
    printf '  Heleket: %s/webhook/heleket\n' "$base_url"
    printf '  PayKilla: %s/webhook/paykilla\n' "$base_url"
    printf '  FreeKassa: %s/webhook/freekassa\n' "$base_url"
    printf '  Platega: %s/webhook/platega\n' "$base_url"
}

extract_import_summary() {
    output_path="$1"
    summary_path="$2"
    command -v python3 >/dev/null 2>&1 || {
        warn "python3 не найден; не удалось сохранить JSON-итог миграции."
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
    raise SystemExit("JSON-итог Remnashop не найден в выводе скрипта импорта")
summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(
    json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
}

print_remnashop_import_summary() {
    summary_path="$1"
    mode="${2:-dry-run}"
    [ -f "$summary_path" ] || return 0
    command -v python3 >/dev/null 2>&1 || return 0
    python3 - "$summary_path" "$mode" <<'PY'
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
mode = sys.argv[2]
summary = json.loads(summary_path.read_text(encoding="utf-8"))


def section(name):
    value = summary.get(name)
    return value if isinstance(value, dict) else {}


def count_values(name, keys):
    data = section(name)
    total = 0
    for key in keys:
        value = data.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            total += int(value)
    return total


def changed_count(name, primary_keys, fallback_keys=()):
    total = count_values(name, primary_keys)
    if total:
        return total
    return count_values(name, fallback_keys)


tariff_data = section("tariffs")
provider_data = section("payment_provider_settings")
users = changed_count("users", ("created", "updated"), ("profile_preserved",))
subscriptions = count_values("subscriptions", ("created", "updated"))
payments = count_values("payments", ("created", "updated"))
tariffs = int(tariff_data.get("generated") or 0)
tariff_map = int(tariff_data.get("auto_map_entries") or 0)
providers = int(provider_data.get("providers_mapped") or 0)
settings = count_values(
    "settings",
    (
        "overrides_written",
        "admin_overrides_written",
        "notification_overrides_written",
        "source_env_overrides_written",
    ),
)
warnings = summary.get("warnings")
warnings_count = len(warnings) if isinstance(warnings, list) else 0

if mode == "dry-run":
    print("Проверка без записи прошла успешно: база Minishop еще не менялась.")
    title = "План импорта"
else:
    print("Импорт применен успешно.")
    title = "Итог импорта"

print(f"{title}:")
print(f"- Пользователи: {users}")
print(f"- Подписки: {subscriptions}")
print(f"- Платежи: {payments}")
print(f"- Тарифы: {tariffs}")
print(f"- Автосопоставления тарифов: {tariff_map}")
print(f"- Платежные провайдеры: {providers}")
print(f"- Настройки: {settings}")
if warnings_count:
    print(f"- Предупреждения: {warnings_count}; они не блокируют импорт, подробности сохранены в JSON-итоге.")
else:
    print("- Предупреждения: нет.")
PY
    info "JSON-итог сохранен: $summary_path"
    [ -f "$summary_path.raw" ] && info "Полный сырой вывод скрипта импорта сохранен: $summary_path.raw"
}

notify_remnashop_migration_success() {
    summary_path="$1"
    [ -f "$summary_path" ] || {
        warn "JSON-итог миграции не сохранен; пропускаю Telegram-уведомление об успешной миграции."
        return 0
    }
    command -v python3 >/dev/null 2>&1 || {
        warn "python3 не найден; пропускаю Telegram-уведомление об успешной миграции."
        return 0
    }
    bot_token=$(env_get BOT_TOKEN "")
    [ -n "$bot_token" ] || {
        warn "BOT_TOKEN пустой; пропускаю Telegram-уведомление об успешной миграции."
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
        "- Имя и короткое описание Telegram-бота мастер установки не менял. Если нужно, меняйте их вручную в BotFather.",
        "- Старые команды Remnashop очищаются при старте сервиса backend; Minishop оставляет только свои команды.",
    ]
)
if miniapp_url:
    callback_url = miniapp_url.rstrip("/") + "/auth/telegram/callback"
    lines.append(f"- В BotFather укажите Mini App URL/domain: {miniapp_url}")
    lines.append(f"- Для Web Login / OpenID Connect разрешите: {miniapp_url} и {callback_url}")
else:
    lines.append("- В BotFather укажите Mini App URL/domain из MINIAPP_PUBLIC_URL.")
if oauth_secret:
    lines.append("- TELEGRAM_OAUTH_CLIENT_SECRET заполнен; после проверки в BotFather перезапустите backend.")
else:
    lines.append(
        "- TELEGRAM_OAUTH_CLIENT_SECRET пустой: если нужен OAuth в браузере, создайте Web Login/OIDC клиент в BotFather, заполните секрет и перезапустите backend."
    )
if webhook_base_url:
    base = webhook_base_url.rstrip("/")
    lines.extend(
        [
            "",
            "Новые URL webhook:",
            f"- Telegram: {base}/tg/webhook, сервис backend ставит его автоматически.",
            f"- Remnawave Panel -> WEBHOOK_URL: {base}/webhook/panel.",
        ]
    )
if payment_actions:
    if not webhook_base_url:
        lines.extend(["", "Новые URL webhook:"])
    for action in payment_actions:
        provider = action.get("provider") or "provider"
        new_url = action.get("new_url") or ""
        where = action.get("where") or ""
        if new_url:
            suffix = f" ({where})" if where else ""
            lines.append(f"- {provider}: {new_url}{suffix}")

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
    show_raw_output="${3:-1}"
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
            summary_extracted=0
            if extract_import_summary "$raw_output" "$summary_output_path"; then
                summary_extracted=1
            fi
            if [ "$show_raw_output" = "1" ] || [ "$summary_extracted" != "1" ]; then
                cat "$raw_output"
            fi
            return 0
        fi
        status=$?
        cat "$raw_output"
        return "$status"
    fi
    (cd "$TARGET_DIR" && run_compose "$@" < /dev/null)
}

restore_app_data_permissions() {
    (cd "$TARGET_DIR" && run_compose run --rm --no-deps \
        --user 0:0 \
        backend sh -lc "chown -R $APP_UID:$APP_GID /app/data") || {
        warn "Не удалось вернуть владельца /app/data на $APP_UID:$APP_GID. Если админка не сможет менять тарифы или файлы, выполните: docker compose run --rm --no-deps --user 0:0 backend chown -R $APP_UID:$APP_GID /app/data"
        return 1
    }
}

reset_target_compose_database() {
    section "Сброс целевой базы Minishop"
    [ -n "$ENV_PATH" ] || ENV_PATH="$TARGET_DIR/.env"
    validate_bind_settings || return 1
    require_docker || return 1
    (cd "$TARGET_DIR" && run_compose stop backend worker migrate) || true
    (cd "$TARGET_DIR" && run_compose_checked up -d postgres redis) || return 1
    wait_target_postgres || return 1
    (cd "$TARGET_DIR" && run_compose exec -T postgres sh -c \
        'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"') || return 1
    ok "Целевая база Minishop сброшена."
}

create_pre_migration_backup() {
    label="$1"
    ask="${2:-1}"
    if [ "$ask" = "1" ]; then
        if ! confirm "Сделать бэкап текущего Minishop перед миграцией? Это позволит откатить целевую базу и конфиги." 1; then
            warn "Бэкап перед миграцией пропущен по вашему выбору."
            return 0
        fi
    fi

    section "Бэкап перед миграцией"
    require_docker || return 1
    stamp=$(date -u '+%Y%m%d-%H%M%S')
    backup_dir="$TARGET_DIR/backups/pre-${label}-migration-$stamp"
    mkdir -p "$backup_dir/files" "$backup_dir/dumps"
    chmod 700 "$backup_dir" 2>/dev/null || true

    for file in .env docker-compose.yml compose.yml Caddyfile angie.conf.template nginx.conf.template .env.example; do
        if [ -f "$TARGET_DIR/$file" ]; then
            mkdir -p "$backup_dir/files/$(dirname "$file")"
            cp "$TARGET_DIR/$file" "$backup_dir/files/$file"
        fi
    done

    if check_target_postgres_auth >/dev/null 2>&1; then
        if (cd "$TARGET_DIR" && compose exec -T postgres sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl') > "$backup_dir/dumps/minishop-postgres.sql"; then
            ok "Дамп PostgreSQL сохранен: $backup_dir/dumps/minishop-postgres.sql"
        else
            warn "Не удалось сохранить дамп PostgreSQL. Бэкап конфигов сохранен, но откат базы будет недоступен."
            rm -f "$backup_dir/dumps/minishop-postgres.sql"
        fi
    else
        warn "PostgreSQL целевого стека пока недоступен; сохраняю только конфиги."
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
for file in docker-compose.yml compose.yml Caddyfile angie.conf.template nginx.conf.template .env.example; do
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
echo "Откат из бэкапа завершен: \$BACKUP_DIR"
EOF
    chmod 700 "$backup_dir/restore.sh" 2>/dev/null || true

    cat > "$backup_dir/README.md" <<EOF
# Бэкап перед миграцией

Создан: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
Целевой каталог: $TARGET_DIR
Источник миграции: $label

Для отката выполните:

    $backup_dir/restore.sh

Бэкап содержит копии основных файлов деплоя и, если PostgreSQL был доступен, логический дамп целевой базы Minishop.
EOF
    ok "Бэкап перед миграцией сохранен: $backup_dir"
}

create_tgshop_source_backup() {
    section "Бэкап источника remnawave-tg-shop"
    stamp=$(date -u '+%Y%m%d-%H%M%S')
    backup_dir="$TARGET_DIR/backups/pre-remnawave-tg-shop-source-$stamp"
    dump_dir="$backup_dir/dumps"
    dump_path="$dump_dir/remnawave-tg-shop-source.sql"
    mkdir -p "$dump_dir"
    chmod 700 "$backup_dir" 2>/dev/null || true

    if volume_exists "$OLD_TGSHOP_DB_VOLUME"; then
        info "Старый Docker volume $OLD_TGSHOP_DB_VOLUME не удаляется и остается на хосте для отката."
    else
        info "Старый Docker volume $OLD_TGSHOP_DB_VOLUME не найден; сохраняю backup по source DSN."
    fi

    if (cd "$TARGET_DIR" && run_compose run --rm --no-deps \
        --user "$(host_user_spec)" \
        -v "$dump_dir:/backup" \
        -e "SOURCE_DSN=$SOURCE_DSN" \
        backend sh -lc \
        'pg_dump --clean --if-exists --no-owner --no-privileges "$SOURCE_DSN" > /backup/remnawave-tg-shop-source.sql'); then
        ok "Дамп источника сохранен: $dump_path"
    else
        fail "Не удалось сохранить дамп старого remnawave-tg-shop. Целевой DB volume не удалялся."
        return 1
    fi

    cat > "$backup_dir/README.md" <<EOF
# Backup источника remnawave-tg-shop

Создан: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
Source DSN: $(mask_compose_log_args "$SOURCE_DSN")
Старый Docker volume: $OLD_TGSHOP_DB_VOLUME

Wizard не удаляет старый Docker volume. Этот SQL dump сохранен до пересоздания
целевого Minishop DB volume и может использоваться для ручного восстановления.
EOF
    TGSHOP_SOURCE_DUMP_PATH="$dump_path"
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
        "2. Старый remnawave-tg-shop - перенос совместимой базы или Docker volume." \
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
    info "Сначала будет проверка без записи данных. Документация: $DOCS_REMNASHOP_URL"
    ENV_PATH="$TARGET_DIR/.env"
    if [ ! -f "$ENV_PATH" ]; then
        fail ".env не найден. Сначала установите стек или сгенерируйте конфигурацию."
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
    SOURCE_SCHEMA="${REMNASHOP_SOURCE_SCHEMA:-public}"
    info "Схема PostgreSQL источника Remnashop: $SOURCE_SCHEMA. Для другой схемы задайте REMNASHOP_SOURCE_SCHEMA перед запуском."
    detected_source_env=$(detect_remnashop_env_file || true)
    if [ -n "$detected_source_env" ]; then
        info "Нашел .env Remnashop и подставил путь по умолчанию."
    fi
    prompt_value "Путь к .env Remnashop для переноса настроек (пусто = пропустить)" "$detected_source_env" 0 0 ""
    SOURCE_ENV_PATH="$PROMPT_VALUE"
    if [ -n "$SOURCE_ENV_PATH" ]; then
        source_env_dir=$(dirname "$SOURCE_ENV_PATH")
        if [ ! -d "$source_env_dir" ]; then
            fail "Каталог .env источника не найден: $source_env_dir"
            return 1
        fi
        SOURCE_ENV_PATH=$(cd "$source_env_dir" && pwd)/$(basename "$SOURCE_ENV_PATH")
        if [ ! -f "$SOURCE_ENV_PATH" ]; then
            fail ".env Remnashop не найден: $SOURCE_ENV_PATH"
            return 1
        fi
    fi

    choose "Целевая база Minishop" "1" "1|2" \
        "1. База текущего Docker Compose стека (рекомендуется)." \
        "2. Ввести целевой DSN вручную." || return 1
    if [ "$CHOICE_VALUE" = "1" ]; then
        TARGET_DSN="$(local_target_dsn)"
        info "Целевой DSN указывает на сервис postgres текущего Docker Compose стека."
        create_pre_migration_backup remnashop || return 1
        if confirm "Сбросить целевую базу Minishop перед импортом? Это удалит текущие данные Minishop." 0; then
            reset_target_compose_database || return 1
        fi
    else
        warn "Для ручного целевого DSN автоматический бэкап целевой базы не выполняется."
        prompt_value "Целевой PostgreSQL DSN" "" 1 0 ""
        TARGET_DSN="$PROMPT_VALUE"
    fi

    prompt_value "Путь к JSON-карте тарифов (пусто = пропустить)" "" 0 0 ""
    TARIFF_MAP_PATH="$PROMPT_VALUE"
    if [ -n "$TARIFF_MAP_PATH" ]; then
        tariff_map_dir=$(dirname "$TARIFF_MAP_PATH")
        if [ ! -d "$tariff_map_dir" ]; then
            fail "Каталог JSON-карты тарифов не найден: $tariff_map_dir"
            return 1
        fi
        TARIFF_MAP_PATH=$(cd "$tariff_map_dir" && pwd)/$(basename "$TARIFF_MAP_PATH")
        if [ ! -f "$TARIFF_MAP_PATH" ]; then
            fail "JSON-карта тарифов не найдена: $TARIFF_MAP_PATH"
            return 1
        fi
    fi

    IMPORTER_PATH="$(download_importer)" || return 1
    connect_local_source_db_to_target_network

    section "Проверка импорта без записи"
    mkdir -p "$TARGET_DIR/$INSTALL_STATE_DIR"
    DRY_RUN_SUMMARY_PATH="$TARGET_DIR/$INSTALL_STATE_DIR/remnashop-dry-run-summary.json"
    if ! run_import_command 1 "$DRY_RUN_SUMMARY_PATH" 0; then
        disconnect_local_source_db_from_target_network
        fail "Проверка без записи не прошла. Исправьте подключение или настройки перед импортом."
        return 1
    fi
    print_remnashop_import_summary "$DRY_RUN_SUMMARY_PATH" "dry-run"
    if ! confirm "Применить эту миграцию по-настоящему?" 1; then
        disconnect_local_source_db_from_target_network
        warn "Миграция не применена."
        return 0
    fi

    section "Применение импорта"
    APPLY_SUMMARY_PATH="$TARGET_DIR/$INSTALL_STATE_DIR/remnashop-apply-summary.json"
    import_status=0
    run_import_command 0 "$APPLY_SUMMARY_PATH" 0 || import_status=$?
    restore_app_data_permissions || true
    disconnect_local_source_db_from_target_network
    [ "$import_status" = "0" ] || return "$import_status"
    print_remnashop_import_summary "$APPLY_SUMMARY_PATH" "apply"
    configure_egames_panel_webhook || return 1
    if confirm "Перезапустить backend, worker и frontend, чтобы они перечитали настройки?" 1; then
        (cd "$TARGET_DIR" && run_compose restart backend worker frontend) || true
    fi
    refresh_egames_nginx_after_migration
    notify_remnashop_migration_success "$APPLY_SUMMARY_PATH"
    ok "Миграция завершена."
    stop_remnashop_source_stack
    remnashop_post_migration_next_steps
}

run_target_schema_migrations() {
    section "Применение миграций схемы целевого стека"
    [ -n "$ENV_PATH" ] || ENV_PATH="$TARGET_DIR/.env"
    validate_bind_settings || return 1
    require_docker || return 1
    (cd "$TARGET_DIR" && run_compose_checked run --rm migrate) || return 1
    ok "Миграции схемы выполнены."
}

prepare_compose_without_starting_apps() {
    section "Подготовка целевого Docker Compose стека"
    [ -n "$ENV_PATH" ] || ENV_PATH="$TARGET_DIR/.env"
    validate_bind_settings || return 1
    require_docker || return 1
    (cd "$TARGET_DIR" && run_compose_checked up --no-start) || return 1
}

run_tgshop_dsn_migration() {
    section "Миграция старого remnawave-tg-shop через pg_dump"
    warn "Wizard пересоздаст целевой PostgreSQL volume, чтобы target DB осталась на новых POSTGRES_* из .env."
    warn "Старая база будет прочитана через source DSN, затем восстановлена в чистую целевую БД."

    detected_source_dsn=$(detect_tgshop_source_dsn || true)
    if [ -n "$detected_source_dsn" ]; then
        info "Нашел PostgreSQL старого remnawave-tg-shop и подставил source DSN по умолчанию."
        info "Source DSN: $(mask_compose_log_args "$detected_source_dsn")"
        SOURCE_DSN="$detected_source_dsn"
    else
        prompt_value "DSN PostgreSQL старого remnawave-tg-shop" "" 1 0 ""
        SOURCE_DSN="$PROMPT_VALUE"
    fi

    if ! confirm "Удалить целевой DB volume и заменить его дампом старого remnawave-tg-shop?" 1; then
        warn "Миграция не применена."
        return 0
    fi

    require_docker || return 1
    POSTGRES_USER_VALUE="$(env_get POSTGRES_USER '')"
    POSTGRES_PASSWORD_VALUE="$(env_get POSTGRES_PASSWORD '')"
    POSTGRES_DB_VALUE="$(env_get POSTGRES_DB '')"
    TARGET_DSN="$(local_target_dsn)"
    validate_bind_settings || return 1

    prepare_compose_without_starting_apps || return 1
    connect_local_source_db_to_target_network
    create_tgshop_source_backup || return 1
    create_pre_migration_backup remnawave-tg-shop 0 || return 1
    reset_target_postgres_volume || return 1

    section "Восстановление старой базы"
    (cd "$TARGET_DIR" && run_compose run --rm --no-deps \
        --user "$(host_user_spec)" \
        -v "$TGSHOP_SOURCE_DUMP_PATH:/backup/remnawave-tg-shop-source.sql:ro" \
        -e "TARGET_DSN=$TARGET_DSN" \
        backend sh -lc \
        'psql "$TARGET_DSN" -v ON_ERROR_STOP=1 < /backup/remnawave-tg-shop-source.sql') || return 1

    run_target_schema_migrations || return 1
    if confirm "Запустить полный стек сейчас?" 1; then
        start_stack 0 1 || return 1
    fi
}

run_remnawave_tg_shop_migration() {
    section "Миграция старого remnawave-tg-shop"
    ENV_PATH="$TARGET_DIR/.env"
    if [ ! -f "$ENV_PATH" ]; then
        fail ".env не найден. Сначала установите стек или сгенерируйте конфигурацию."
        return 1
    fi
    require_docker || return 1

    info "Для старого remnawave-tg-shop wizard использует безопасный pg_dump-перенос вместо копирования raw PostgreSQL volume."
    info "Так целевой стек сохраняет новые POSTGRES_* из .env и не наследует старый пароль базы."
    run_tgshop_dsn_migration
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

base_compose_file_name() {
    if [ -f "$TARGET_DIR/docker-compose.yml" ]; then
        printf 'docker-compose.yml'
        return 0
    fi
    if [ -f "$TARGET_DIR/compose.yml" ]; then
        printf 'compose.yml'
        return 0
    fi
    return 1
}

write_pangolin_compose_file() {
    pangolin_output="$TARGET_DIR/$PANGOLIN_COMPOSE_FILE"
    tmp="$pangolin_output.tmp.$$"
    cat > "$tmp" <<'EOF'
# Дополнительный Docker Compose файл: публикация Web App через Pangolin (Newt).
# Подключается через COMPOSE_FILE в .env; отключается мастером установки
# пунктом меню "Отключить Web App от Pangolin (Newt)".
services:
  newt:
    image: fosrl/newt:latest
    restart: unless-stopped
    environment:
      PANGOLIN_ENDPOINT: ${PANGOLIN_ENDPOINT:?set PANGOLIN_ENDPOINT in .env}
      NEWT_ID: ${NEWT_ID:?set NEWT_ID in .env}
      NEWT_SECRET: ${NEWT_SECRET:?set NEWT_SECRET in .env}
      HEALTH_FILE: /tmp/healthy
    networks:
      - remnawave-minishop
    healthcheck:
      test: ["CMD-SHELL", "test -f /tmp/healthy"]
      interval: 30s
      timeout: 5s
      retries: 5

networks:
  remnawave-minishop:
EOF
    mv "$tmp" "$pangolin_output" || {
        rm -f "$tmp"
        return 1
    }
    ok "Записан файл $pangolin_output"
}

enable_pangolin_compose_file() {
    base_compose=$(base_compose_file_name) || {
        fail "Не найден docker-compose.yml или compose.yml в $TARGET_DIR."
        return 1
    }
    current_compose_file=$(env_get COMPOSE_FILE "")
    if [ -z "$current_compose_file" ]; then
        new_compose_file="$base_compose:$PANGOLIN_COMPOSE_FILE"
    else
        case ":$current_compose_file:" in
            *":$PANGOLIN_COMPOSE_FILE:"*)
                new_compose_file="$current_compose_file"
                ;;
            *)
                new_compose_file="$current_compose_file:$PANGOLIN_COMPOSE_FILE"
                ;;
        esac
    fi
    set_env_file_value "$ENV_PATH" COMPOSE_FILE "$new_compose_file"
}

disable_pangolin_compose_file() {
    current_compose_file=$(env_get COMPOSE_FILE "")
    [ -n "$current_compose_file" ] || return 0
    new_compose_file=$(printf '%s' "$current_compose_file" | awk -F: -v skip="$PANGOLIN_COMPOSE_FILE" '
        {
            out = ""
            for (i = 1; i <= NF; i++) {
                if ($i == skip || $i == "") continue
                out = out (out == "" ? "" : ":") $i
            }
            print out
        }
    ')
    base_compose=$(base_compose_file_name || printf '')
    if [ -z "$new_compose_file" ] || [ "$new_compose_file" = "$base_compose" ]; then
        unset_env_file_value "$ENV_PATH" COMPOSE_FILE
    else
        set_env_file_value "$ENV_PATH" COMPOSE_FILE "$new_compose_file"
    fi
}

pangolin_resources_checklist() {
    info "В Pangolin создайте HTTP-ресурсы для этого Newt site:"
    printf '  Mini App (%s) -> http://frontend:80\n' "$(env_get MINIAPP_HOST app.example.com)"
    printf '  API/webhook (%s) -> http://backend:8080\n' "$(env_get WEBHOOK_HOST webhooks.example.com)"
    info "Если Web App уже опубликован другим способом, ресурсы Pangolin станут дополнительным путем доступа."
}

pangolin_connect_in_target() {
    section "Подключение Web App к Pangolin (Newt)"
    ENV_PATH="$TARGET_DIR/.env"
    if [ ! -f "$ENV_PATH" ]; then
        fail ".env не найден: $ENV_PATH. Сначала установите стек."
        return 1
    fi
    if [ "$(env_get DEPLOYMENT_PROFILE '')" = "newt" ]; then
        info "Стек уже развернут по профилю Pangolin/Newt; отдельное подключение не требуется."
        return 0
    fi
    base_compose_file_name >/dev/null || {
        fail "Не найден docker-compose.yml или compose.yml в $TARGET_DIR. Сначала установите стек."
        return 1
    }
    require_docker || return 1

    info "Newt сам подключается к Pangolin наружу; открывать входящие порты не нужно."
    prompt_value "Endpoint Pangolin" "$(env_get PANGOLIN_ENDPOINT https://pangolin.example.com)" 1 0 "url"
    PANGOLIN_ENDPOINT_VALUE="$PROMPT_VALUE"
    prompt_value "Newt ID" "$(env_get NEWT_ID '')" 1 0 ""
    NEWT_ID_VALUE="$PROMPT_VALUE"
    newt_secret_prefilled=0
    existing_newt_secret=$(env_get NEWT_SECRET "")
    [ -n "$existing_newt_secret" ] && newt_secret_prefilled=1
    prompt_value "Секрет Newt" "$existing_newt_secret" 1 1 "" "$newt_secret_prefilled"
    NEWT_SECRET_VALUE="$PROMPT_VALUE"

    env_backup=$(backup_path "$ENV_PATH")
    cp "$ENV_PATH" "$env_backup" || return 1
    info "Бэкап $ENV_PATH сохранен как $(basename "$env_backup")"
    set_env_file_value "$ENV_PATH" PANGOLIN_ENDPOINT "$PANGOLIN_ENDPOINT_VALUE" || return 1
    set_env_file_value "$ENV_PATH" NEWT_ID "$NEWT_ID_VALUE" || return 1
    set_env_file_value "$ENV_PATH" NEWT_SECRET "$NEWT_SECRET_VALUE" || return 1
    write_pangolin_compose_file || return 1
    enable_pangolin_compose_file || return 1

    if confirm "Запустить контейнер newt сейчас?" 1; then
        (cd "$TARGET_DIR" && run_compose_checked up -d newt) || return 1
        (cd "$TARGET_DIR" && run_compose ps newt) || true
    else
        info "Контейнер newt не запущен. Позже выполните docker compose up -d newt в $TARGET_DIR."
    fi

    ok "Web App подключен к Pangolin через Newt."
    pangolin_resources_checklist
    info "Отключить публикацию можно пунктом меню \"Отключить Web App от Pangolin (Newt)\"."
}

pangolin_disconnect_in_target() {
    section "Отключение Web App от Pangolin (Newt)"
    ENV_PATH="$TARGET_DIR/.env"
    if [ ! -f "$ENV_PATH" ]; then
        fail ".env не найден: $ENV_PATH."
        return 1
    fi
    if [ "$(env_get DEPLOYMENT_PROFILE '')" = "newt" ]; then
        fail "Стек развернут по профилю Pangolin/Newt: Newt здесь единственный вход в приложение."
        info "Отключение возможно только сменой профиля деплоя (повторная установка с другим профилем)."
        return 1
    fi
    current_compose_file=$(env_get COMPOSE_FILE "")
    pangolin_enabled=0
    case ":$current_compose_file:" in
        *":$PANGOLIN_COMPOSE_FILE:"*)
            pangolin_enabled=1
            ;;
    esac
    if [ "$pangolin_enabled" = "0" ] && [ ! -f "$TARGET_DIR/$PANGOLIN_COMPOSE_FILE" ]; then
        info "Подключение к Pangolin не найдено; отключать нечего."
        return 0
    fi
    require_docker || return 1

    if [ "$pangolin_enabled" = "1" ]; then
        (cd "$TARGET_DIR" && run_compose rm -sf newt) || warn "Не удалось остановить контейнер newt; проверьте его вручную."
    fi

    env_backup=$(backup_path "$ENV_PATH")
    cp "$ENV_PATH" "$env_backup" || return 1
    info "Бэкап $ENV_PATH сохранен как $(basename "$env_backup")"
    disable_pangolin_compose_file || return 1
    if [ -f "$TARGET_DIR/$PANGOLIN_COMPOSE_FILE" ]; then
        pangolin_backup=$(backup_path "$TARGET_DIR/$PANGOLIN_COMPOSE_FILE")
        mv "$TARGET_DIR/$PANGOLIN_COMPOSE_FILE" "$pangolin_backup"
        info "Файл $PANGOLIN_COMPOSE_FILE сохранен как $(basename "$pangolin_backup") на случай возврата."
    fi
    info "Значения PANGOLIN_ENDPOINT/NEWT_ID/NEWT_SECRET оставлены в .env для быстрого повторного подключения."
    ok "Web App отключен от Pangolin."
}

pangolin_connect_flow() {
    installation_directory || return 1
    pangolin_connect_in_target
}

pangolin_disconnect_flow() {
    installation_directory || return 1
    pangolin_disconnect_in_target
}

offer_pangolin_connect_after_install() {
    [ "$PROFILE_KEY" = "newt" ] && return 0
    [ -f "$TARGET_DIR/.env" ] || return 0
    if confirm "Дополнительно опубликовать Web App через Pangolin (Newt)?" 0; then
        pangolin_connect_in_target || return 1
    fi
    return 0
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
    ENV_PATH="$TARGET_DIR/.env"
    if [ -f "$ENV_PATH" ]; then
        warn "Найден существующий .env: $ENV_PATH; неизвестные значения будут сохранены."
    fi
    choose_install_node_role || return 1
    if [ "$with_migration" = "1" ] && [ "$INSTALL_NODE_ROLE_VALUE" = "frontend-node" ]; then
        fail "Frontend node не запускает backend migration/import. Выберите full stack или backend node."
        return 1
    fi
    if [ "$INSTALL_NODE_ROLE_VALUE" = "frontend-node" ]; then
        PROFILE_KEY="frontend-node"
        DEPLOYMENT_PROFILE_VALUE="frontend-node"
    else
        choose_profile || return 1
    fi
    if [ "$with_migration" = "1" ]; then
        choose_legacy_source || return 1
    fi
    if [ "$INSTALL_NODE_ROLE_VALUE" = "frontend-node" ]; then
        prompt_frontend_node_env || return 1
    else
        prompt_common_env || return 1
    fi
    configure_frontend_backend_mode || return 1
    mkdir -p "$TARGET_DIR/$INSTALL_STATE_DIR"
    check_public_dns_records || return 1
    download_profile_files || return 1
    download_split_reference_files || return 1
    write_env_file || return 1
    configure_nginx_certificates || return 1
    configure_existing_reverse_proxy || return 1
    if [ "$INSTALL_NODE_ROLE_VALUE" != "frontend-node" ]; then
        prepare_data_mount || return 1
    fi
    if [ "$INSTALL_NODE_ROLE_VALUE" != "frontend-node" ] && [ "$with_migration" != "1" ] && confirm "Мигрировать данные из другого бота после установки?" 0; then
        choose_legacy_source || return 1
    fi

    case "$LEGACY_SOURCE" in
        remnawave-tg-shop)
            run_selected_legacy_migration
            ;;
        remnashop)
            info "Запускаю Docker Compose стек перед импортом из Remnashop: скрипт импорта использует целевую базу Minishop."
            start_stack || return 1
            run_selected_legacy_migration
            ;;
        *)
            if confirm "Запустить Docker Compose стек сейчас?" 1; then
                start_stack || return 1
            fi
            ;;
    esac
    offer_pangolin_connect_after_install || return 1
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
    ENV_PATH="$TARGET_DIR/.env"
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
        choose "Главное меню" "1" "1|2|3|4|5|6|7|8" \
            "1. Установить новый remnawave-minishop." \
            "2. Установить новый remnawave-minishop и мигрировать данные из другого бота." \
            "3. Мигрировать данные в уже установленный remnawave-minishop." \
            "4. Только скачать/обновить файлы деплоя." \
            "5. Проверить текущий стек." \
            "6. Подключить Web App к Pangolin (Newt)." \
            "7. Отключить Web App от Pangolin (Newt)." \
            "8. Выйти." || return 1
        case "$CHOICE_VALUE" in
            1) install_flow 0 ;;
            2) install_flow 1 ;;
            3) migration_only_flow ;;
            4) download_only_flow ;;
            5) health_flow ;;
            6) pangolin_connect_flow ;;
            7) pangolin_disconnect_flow ;;
            8) printf 'Готово, выходим.\n'; return 0 ;;
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
