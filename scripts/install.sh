#!/bin/sh
set -u

# Interactive installer for fresh Docker Compose hosts.

DEFAULT_REPO="${MINISHOP_INSTALL_REPO:-3252a8/remnawave-minishop}"
DEFAULT_REF="${MINISHOP_INSTALL_REF:-main}"
DEFAULT_IMAGE_TAG="${MINISHOP_IMAGE_TAG:-latest}"
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
SOURCE_REPO=""
SOURCE_REF=""
PROFILE_KEY=""
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
WEBAPP_SESSION_SECRET_VALUE=""
WEBHOOK_SECRET_TOKEN_VALUE=""
TRUSTED_PROXIES_VALUE=""
PANEL_API_URL_VALUE=""
PANEL_API_KEY_VALUE=""
PANEL_WEBHOOK_SECRET_VALUE=""

KNOWN_ENV_KEYS="COMPOSE_PROJECT_NAME IMAGE_TAG WEBHOOK_HOST MINIAPP_HOST WEBHOOK_PUBLIC_URL MINIAPP_PUBLIC_URL HTTP_BIND HTTPS_BIND WEB_SERVER_BIND FRONTEND_BIND PANGOLIN_ENDPOINT NEWT_ID NEWT_SECRET BOT_TOKEN ADMIN_IDS POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB WEBAPP_ENABLED WEBAPP_SESSION_SECRET WEBHOOK_SECRET_TOKEN TRUSTED_PROXIES PANEL_API_URL PANEL_API_KEY PANEL_WEBHOOK_SECRET"

color() {
    printf '%s%s%s' "$2" "$1" "$RESET"
}

banner() {
    printf '\n'
    color "Remnawave MiniShop Install Wizard" "$BOLD$CYAN"
    printf '\n'
    color "Install, configure, start, and migrate existing bot data." "$DIM"
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
    printf '%s' "${DIM}Press Enter to continue...${RESET}"
    # shellcheck disable=SC2034
    read -r _
}

print_help() {
    cat <<EOF
Environment overrides:
  MINISHOP_INSTALL_DIR    default install directory
  MINISHOP_INSTALL_REPO   default repository ($DEFAULT_REPO)
  MINISHOP_INSTALL_REF    default ref ($DEFAULT_REF)
  MINISHOP_IMAGE_TAG      default image tag ($DEFAULT_IMAGE_TAG)
  REMNASHOP_SOURCE_DSN    default source DSN for migration
  REMNASHOP_SOURCE_ENV_FILE default source Remnashop .env path for migration
  LEGACY_TGSHOP_SOURCE_DSN default remnawave-tg-shop source DSN for dump/restore

The wizard is interactive by design. It never overwrites files without
confirmation. Remnashop imports always run dry-run first; remnawave-tg-shop
can be migrated from Docker volumes or a PostgreSQL DSN.
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
        BOT_TOKEN|POSTGRES_PASSWORD|WEBAPP_SESSION_SECRET|WEBHOOK_SECRET_TOKEN|PANEL_API_KEY|PANEL_WEBHOOK_SECRET|NEWT_SECRET)
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
    while :; do
        if [ -n "$default_value" ]; then
            if [ "$secret" = "1" ]; then
                shown=$(mask_secret "$default_value")
            else
                shown="$default_value"
            fi
            printf '%s [%s]: ' "$label" "$shown"
        else
            printf '%s: ' "$label"
        fi
        read -r raw_value
        if [ -n "$raw_value" ]; then
            value="$raw_value"
        else
            value="$default_value"
        fi
        if [ "$required" = "1" ] && [ -z "$value" ]; then
            warn "Value is required."
            continue
        fi
        if [ -n "$value" ] && ! validate_value "$value" "$validator"; then
            warn "Value does not look valid."
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
        read -r answer
        answer=$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')
        if [ -z "$answer" ]; then
            [ "$default" = "1" ]
            return $?
        fi
        case "$answer" in
            y|yes)
                return 0
                ;;
            n|no)
                return 1
                ;;
            *)
                warn "Answer y or n."
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
        printf 'Choose [%s]: ' "$default"
        read -r selected
        selected="${selected:-$default}"
        case "|$valid|" in
            *"|$selected|"*)
                CHOICE_VALUE="$selected"
                return 0
                ;;
            *)
                warn "Unknown menu item."
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
    fail "Could not generate a secure secret. Install openssl and retry."
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
    url="$1"
    target="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$url" -o "$target"
        return $?
    fi
    if command -v wget >/dev/null 2>&1; then
        wget -qO "$target" "$url"
        return $?
    fi
    fail "curl or wget is required to download files."
    exit 1
}

backup_path() {
    path="$1"
    stamp=$(date -u '+%Y%m%d-%H%M%S')
    printf '%s.bak-%s' "$path" "$stamp"
}

write_downloaded_file() {
    source_path="$1"
    target_path="$2"
    mkdir -p "$(dirname "$target_path")"
    if [ -e "$target_path" ]; then
        if confirm "$target_path exists. Overwrite with backup?" 0; then
            backup=$(backup_path "$target_path")
            cp "$target_path" "$backup"
            info "Backed up $target_path to $(basename "$backup")"
        else
            warn "Keeping existing $target_path"
            rm -f "$source_path"
            return 0
        fi
    fi
    mv "$source_path" "$target_path"
    ok "Wrote $target_path"
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
        fail "Could not download $url"
        return 1
    fi
    warn "Skipping optional file $source"
    return 0
}

choose_profile() {
    choose "Deployment profile" "1" "1|2|3|4" \
        "1. Caddy HTTPS - recommended public HTTPS with automatic certificates." \
        "2. Nginx HTTPS - TLS certificates are managed manually." \
        "3. Pangolin / Newt - no inbound ports; public routes are configured in Pangolin." \
        "4. No proxy / external TLS - direct HTTP ports or an external TLS terminator."
    case "$CHOICE_VALUE" in
        1) PROFILE_KEY="caddy" ;;
        2) PROFILE_KEY="nginx" ;;
        3) PROFILE_KEY="newt" ;;
        4) PROFILE_KEY="no-proxy" ;;
    esac
}

download_profile_files() {
    section "Download deployment files"
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
    esac
}

prompt_common_env() {
    section "Minimal .env"
    prompt_value "Compose project name" "$(env_get COMPOSE_PROJECT_NAME remnawave-minishop)" 0 0 ""
    COMPOSE_PROJECT_NAME_VALUE="$PROMPT_VALUE"
    prompt_value "Image tag" "$(env_get IMAGE_TAG "$DEFAULT_IMAGE_TAG")" 0 0 ""
    IMAGE_TAG_VALUE="$PROMPT_VALUE"
    prompt_value "Telegram bot token" "$(env_get BOT_TOKEN '')" 1 1 ""
    BOT_TOKEN_VALUE="$PROMPT_VALUE"
    prompt_value "Admin Telegram IDs, comma-separated" "$(env_get ADMIN_IDS '')" 1 0 ""
    ADMIN_IDS_VALUE="$PROMPT_VALUE"
    prompt_value "Postgres user" "$(env_get POSTGRES_USER remnawave_minishop)" 1 0 ""
    POSTGRES_USER_VALUE="$PROMPT_VALUE"
    existing_postgres_password=$(env_get POSTGRES_PASSWORD "")
    if [ -z "$existing_postgres_password" ]; then
        existing_postgres_password=$(generated_password)
    fi
    prompt_value "Postgres password" "$existing_postgres_password" 1 1 ""
    POSTGRES_PASSWORD_VALUE="$PROMPT_VALUE"
    prompt_value "Postgres database" "$(env_get POSTGRES_DB remnawave_minishop)" 1 0 ""
    POSTGRES_DB_VALUE="$PROMPT_VALUE"

    WEBAPP_ENABLED_VALUE="$(env_get WEBAPP_ENABLED True)"
    WEBAPP_SESSION_SECRET_VALUE="$(env_get WEBAPP_SESSION_SECRET "")"
    if [ -z "$WEBAPP_SESSION_SECRET_VALUE" ]; then
        WEBAPP_SESSION_SECRET_VALUE="$(secret_hex 32)"
    fi
    WEBHOOK_SECRET_TOKEN_VALUE="$(env_get WEBHOOK_SECRET_TOKEN "")"
    if [ -z "$WEBHOOK_SECRET_TOKEN_VALUE" ]; then
        WEBHOOK_SECRET_TOKEN_VALUE="$(secret_hex 32)"
    fi

    prompt_value "Remnawave Panel API URL" "$(env_get PANEL_API_URL https://panel.example.com/api)" 0 0 "url"
    PANEL_API_URL_VALUE="$PROMPT_VALUE"
    prompt_value "Remnawave Panel API key" "$(env_get PANEL_API_KEY change_me)" 0 1 ""
    PANEL_API_KEY_VALUE="$PROMPT_VALUE"
    existing_panel_webhook_secret=$(env_get PANEL_WEBHOOK_SECRET "")
    if [ -z "$existing_panel_webhook_secret" ]; then
        existing_panel_webhook_secret=$(secret_hex 24)
    fi
    prompt_value "Remnawave Panel webhook secret" "$existing_panel_webhook_secret" 0 1 ""
    PANEL_WEBHOOK_SECRET_VALUE="$PROMPT_VALUE"

    case "$PROFILE_KEY" in
        caddy|nginx|newt)
            prompt_value "Webhook/API public hostname" "$(env_get WEBHOOK_HOST webhooks.example.com)" 1 0 "hostname"
            WEBHOOK_HOST_VALUE="$PROMPT_VALUE"
            prompt_value "Mini App public hostname" "$(env_get MINIAPP_HOST app.example.com)" 1 0 "hostname"
            MINIAPP_HOST_VALUE="$PROMPT_VALUE"
            TRUSTED_PROXIES_VALUE="$(env_get TRUSTED_PROXIES '127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7')"
            ;;
    esac

    case "$PROFILE_KEY" in
        caddy|nginx)
            prompt_value "HTTP bind" "$(env_get HTTP_BIND '0.0.0.0:80')" 0 0 ""
            HTTP_BIND_VALUE="$PROMPT_VALUE"
            prompt_value "HTTPS bind" "$(env_get HTTPS_BIND '0.0.0.0:443')" 0 0 ""
            HTTPS_BIND_VALUE="$PROMPT_VALUE"
            ;;
        newt)
            prompt_value "Pangolin endpoint" "$(env_get PANGOLIN_ENDPOINT https://pangolin.example.com)" 1 0 "url"
            PANGOLIN_ENDPOINT_VALUE="$PROMPT_VALUE"
            prompt_value "Newt ID" "$(env_get NEWT_ID '')" 1 0 ""
            NEWT_ID_VALUE="$PROMPT_VALUE"
            prompt_value "Newt secret" "$(env_get NEWT_SECRET '')" 1 1 ""
            NEWT_SECRET_VALUE="$PROMPT_VALUE"
            ;;
        no-proxy)
            prompt_value "Backend bind" "$(env_get WEB_SERVER_BIND '0.0.0.0:8080')" 0 0 ""
            WEB_SERVER_BIND_VALUE="$PROMPT_VALUE"
            prompt_value "Frontend bind" "$(env_get FRONTEND_BIND '0.0.0.0:8082')" 0 0 ""
            FRONTEND_BIND_VALUE="$PROMPT_VALUE"
            prompt_value "Webhook public URL" "$(env_get WEBHOOK_PUBLIC_URL 'http://127.0.0.1:8080')" 1 0 "url"
            WEBHOOK_PUBLIC_URL_VALUE="$PROMPT_VALUE"
            prompt_value "Mini App public URL" "$(env_get MINIAPP_PUBLIC_URL 'http://127.0.0.1:8082/')" 1 0 "url"
            MINIAPP_PUBLIC_URL_VALUE="$PROMPT_VALUE"
            TRUSTED_PROXIES_VALUE="$(env_get TRUSTED_PROXIES '127.0.0.1,::1')"
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
    show_env_value IMAGE_TAG "$IMAGE_TAG_VALUE"
    show_env_value WEBHOOK_HOST "$WEBHOOK_HOST_VALUE"
    show_env_value MINIAPP_HOST "$MINIAPP_HOST_VALUE"
    show_env_value WEBHOOK_PUBLIC_URL "$WEBHOOK_PUBLIC_URL_VALUE"
    show_env_value MINIAPP_PUBLIC_URL "$MINIAPP_PUBLIC_URL_VALUE"
    show_env_value BOT_TOKEN "$BOT_TOKEN_VALUE"
    show_env_value ADMIN_IDS "$ADMIN_IDS_VALUE"
    show_env_value POSTGRES_USER "$POSTGRES_USER_VALUE"
    show_env_value POSTGRES_PASSWORD "$POSTGRES_PASSWORD_VALUE"
    show_env_value POSTGRES_DB "$POSTGRES_DB_VALUE"
    show_env_value WEBAPP_SESSION_SECRET "$WEBAPP_SESSION_SECRET_VALUE"
    show_env_value WEBHOOK_SECRET_TOKEN "$WEBHOOK_SECRET_TOKEN_VALUE"
    show_env_value PANEL_API_URL "$PANEL_API_URL_VALUE"
    show_env_value PANEL_API_KEY "$PANEL_API_KEY_VALUE"
    show_env_value PANEL_WEBHOOK_SECRET "$PANEL_WEBHOOK_SECRET_VALUE"
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
    env_line WEBAPP_SESSION_SECRET "$WEBAPP_SESSION_SECRET_VALUE" "$output"
    env_line WEBHOOK_SECRET_TOKEN "$WEBHOOK_SECRET_TOKEN_VALUE" "$output"
    env_line TRUSTED_PROXIES "$TRUSTED_PROXIES_VALUE" "$output"

    printf '\n# Remnawave Panel\n' >> "$output"
    env_line PANEL_API_URL "$PANEL_API_URL_VALUE" "$output"
    env_line PANEL_API_KEY "$PANEL_API_KEY_VALUE" "$output"
    env_line PANEL_WEBHOOK_SECRET "$PANEL_WEBHOOK_SECRET_VALUE" "$output"

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
                warn "Could not chown $data_dir. Run: sudo chown $APP_UID:$APP_GID data"
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
                warn "Could not chown $data_dir. Run: sudo chown $APP_UID:$APP_GID data"
            fi
        fi
        chmod u+rwx "$data_dir" 2>/dev/null || true
    fi
}

require_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        COMPOSE_STYLE="docker"
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_STYLE="docker-compose"
    else
        fail "Docker Compose was not found."
        return 1
    fi
    if command -v docker >/dev/null 2>&1 && ! docker info >/dev/null 2>&1; then
        fail "Docker is installed but not reachable. Check service/user permissions."
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

run_compose() {
    if [ "$COMPOSE_STYLE" = "docker" ]; then
        color "+ docker compose $*" "$DIM"
    else
        color "+ docker-compose $*" "$DIM"
    fi
    printf '\n'
    compose "$@"
}

start_stack() {
    pull="${1:-1}"
    section "Start Docker stack"
    require_docker || return 1
    if [ "$pull" = "1" ]; then
        (cd "$TARGET_DIR" && run_compose pull) || return 1
    fi
    (cd "$TARGET_DIR" && run_compose up -d) || return 1
    (cd "$TARGET_DIR" && run_compose ps) || true
    ok "Stack command completed."
}

validate_stack() {
    section "Validate stack"
    require_docker || return 1
    (cd "$TARGET_DIR" && run_compose ps) || true
    (cd "$TARGET_DIR" && run_compose logs --tail 80 migrate) || true
    ok "Validation commands completed."
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
            fail "Source Docker volume not found: $source_volume"
            return 1
        fi
        warn "Skipping $source_volume: source volume was not found."
        return 0
    fi

    if ! volume_exists "$target_volume"; then
        if [ "$required" = "1" ]; then
            fail "Target Docker volume not found: $target_volume"
            return 1
        fi
        warn "Skipping $target_volume: target volume was not created by this profile."
        return 0
    fi

    if ! volume_is_empty "$target_volume"; then
        if [ "$required" = "1" ]; then
            warn "Target volume $target_volume is already not empty."
            warn "It may already be migrated, or the target stack may have been started with an empty database."
            if confirm "Continue without copying the old database volume?" 0; then
                return 0
            fi
            return 1
        fi
        warn "Skipping $target_volume: target volume is already not empty."
        return 0
    fi

    run_label="docker run --rm -v $source_volume:/from:ro -v $target_volume:/to alpine sh -c 'cd /from && cp -a . /to/'"
    color "+ $run_label" "$DIM"
    printf '\n'
    docker run --rm \
        -v "$source_volume:/from:ro" \
        -v "$target_volume:/to" \
        alpine sh -c 'cd /from && cp -a . /to/' || return 1
    ok "Copied $source_volume -> $target_volume"
}

stop_known_legacy_containers() {
    section "Stop old containers"
    stopped=0
    for container in $KNOWN_LEGACY_CONTAINERS; do
        if docker inspect "$container" >/dev/null 2>&1; then
            if docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -q '^true$'; then
                docker stop "$container" >/dev/null || true
            fi
            docker rm "$container" >/dev/null || true
            info "Stopped/removed $container"
            stopped=1
        fi
    done
    if [ "$stopped" = "0" ]; then
        info "No known old containers found."
    fi
}

wait_target_postgres() {
    section "Wait for target PostgreSQL"
    attempt=1
    while [ "$attempt" -le 30 ]; do
        if (cd "$TARGET_DIR" && compose exec -T postgres sh -c \
            'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1); then
            ok "PostgreSQL is ready."
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    fail "Target PostgreSQL did not become ready."
    return 1
}

download_importer() {
    importer="$TARGET_DIR/$IMPORTER_CACHE_PATH"
    mkdir -p "$(dirname "$importer")"
    if [ -f "$importer" ] && confirm "Use cached importer at $importer?" 1 >&2; then
        printf '%s' "$importer"
        return 0
    fi
    url=$(raw_url "$SOURCE_REPO" "$SOURCE_REF" "backend/scripts/import_legacy.py")
    tmp="$TARGET_DIR/.import_legacy.$$"
    download_to "$url" "$tmp" || {
        rm -f "$tmp"
        fail "Could not download $url"
        return 1
    }
    if [ -f "$importer" ]; then
        backup=$(backup_path "$importer")
        cp "$importer" "$backup"
        info "Backed up $importer to $(basename "$backup")" >&2
    fi
    mv "$tmp" "$importer"
    ok "Cached importer at $importer" >&2
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

remnashop_webhook_checklist() {
    section "Update external webhooks"
    base_url=$(target_webhook_base_url)
    if [ -z "$base_url" ]; then
        warn "Could not determine webhook base URL from .env. Set WEBHOOK_HOST or WEBHOOK_PUBLIC_URL, then use WEBHOOK_BASE_URL + paths below."
        base_url="WEBHOOK_BASE_URL"
    fi

    info "Set these URLs in external dashboards after the migration:"
    printf '  Remnawave Panel -> WEBHOOK_URL: %s/webhook/panel\n' "$base_url"
    panel_secret=$(env_get PANEL_WEBHOOK_SECRET "")
    if [ -n "$panel_secret" ]; then
        printf '  Remnawave Panel -> webhook secret: %s\n' "$(mask_secret "$panel_secret")"
    else
        warn "PANEL_WEBHOOK_SECRET is empty; set it in Minishop and in Remnawave Panel."
    fi
    printf '  YooKassa merchant cabinet -> HTTP notifications URL: %s/webhook/yookassa\n' "$base_url"
    printf '  WATA merchant dashboard -> webhook/callback URL: %s/webhook/wata\n' "$base_url"
    printf '  CryptoBot/Crypto Pay app -> webhook URL: %s/webhook/cryptopay\n' "$base_url"
    printf '  Heleket merchant dashboard -> payment webhook/callback URL: %s/webhook/heleket\n' "$base_url"
    printf '  PayKilla Dashboard -> Settings -> Webhooks URL: %s/webhook/paykilla\n' "$base_url"
    printf '  FreeKassa shop settings -> notification/result URL: %s/webhook/freekassa\n' "$base_url"
    printf '  Platega merchant/project settings -> webhook URL: %s/webhook/platega\n' "$base_url"
    printf '  Telegram webhook: %s/tg/webhook (configured automatically on bot startup)\n' "$base_url"
}

run_import_command() {
    dry="$1"
    set -- run --rm \
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
    (cd "$TARGET_DIR" && run_compose "$@")
}

choose_legacy_source() {
    choose "Source bot" "1" "1|2|3" \
        "1. Remnashop - import users, subscriptions, payments, provider settings and promo codes." \
        "2. Old remnawave-tg-shop - upgrade an old compatible database/volume." \
        "3. Skip migration"
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
    github_source
}

run_remnashop_migration() {
    section "Remnashop migration"
    ENV_PATH="$TARGET_DIR/.env"
    if [ ! -f "$ENV_PATH" ]; then
        fail ".env not found. Install or generate configuration first."
        return 1
    fi
    ensure_github_source_for_importer || return 1
    require_docker || return 1
    POSTGRES_USER_VALUE="$(env_get POSTGRES_USER '')"
    POSTGRES_PASSWORD_VALUE="$(env_get POSTGRES_PASSWORD '')"
    POSTGRES_DB_VALUE="$(env_get POSTGRES_DB '')"

    prompt_value "Source Remnashop PostgreSQL DSN" "${REMNASHOP_SOURCE_DSN:-}" 1 0 ""
    SOURCE_DSN="$PROMPT_VALUE"
    prompt_value "Source schema" "public" 1 0 ""
    SOURCE_SCHEMA="$PROMPT_VALUE"
    prompt_value "Optional source Remnashop .env path (empty to skip)" "${REMNASHOP_SOURCE_ENV_FILE:-}" 0 0 ""
    SOURCE_ENV_PATH="$PROMPT_VALUE"
    if [ -n "$SOURCE_ENV_PATH" ]; then
        source_env_dir=$(dirname "$SOURCE_ENV_PATH")
        if [ ! -d "$source_env_dir" ]; then
            fail "Source .env directory not found: $source_env_dir"
            return 1
        fi
        SOURCE_ENV_PATH=$(cd "$source_env_dir" && pwd)/$(basename "$SOURCE_ENV_PATH")
        if [ ! -f "$SOURCE_ENV_PATH" ]; then
            fail "Source Remnashop .env not found: $SOURCE_ENV_PATH"
            return 1
        fi
    fi

    choose "Target database" "1" "1|2" \
        "1. This Docker Compose stack database (recommended)" \
        "2. Manual target DSN"
    if [ "$CHOICE_VALUE" = "1" ]; then
        TARGET_DSN="$(local_target_dsn)"
        info "Target DSN points to the Compose postgres service."
    else
        prompt_value "Target PostgreSQL DSN" "" 1 0 ""
        TARGET_DSN="$PROMPT_VALUE"
    fi

    prompt_value "Optional tariff map JSON path (empty to skip)" "" 0 0 ""
    TARIFF_MAP_PATH="$PROMPT_VALUE"
    if [ -n "$TARIFF_MAP_PATH" ]; then
        tariff_map_dir=$(dirname "$TARIFF_MAP_PATH")
        if [ ! -d "$tariff_map_dir" ]; then
            fail "Tariff map directory not found: $tariff_map_dir"
            return 1
        fi
        TARIFF_MAP_PATH=$(cd "$tariff_map_dir" && pwd)/$(basename "$TARIFF_MAP_PATH")
        if [ ! -f "$TARIFF_MAP_PATH" ]; then
            fail "Tariff map not found: $TARIFF_MAP_PATH"
            return 1
        fi
    fi

    IMPORTER_PATH="$(download_importer)" || return 1

    section "Dry-run import"
    if ! run_import_command 1; then
        fail "Dry-run failed. Fix the connection/settings before importing."
        return 1
    fi
    if ! confirm "Apply this migration for real?" 0; then
        warn "Migration not applied."
        return 0
    fi

    section "Apply import"
    run_import_command 0 || return 1
    remnashop_webhook_checklist
    if confirm "Restart backend and worker so setting overrides are reloaded?" 1; then
        (cd "$TARGET_DIR" && run_compose restart backend worker) || true
    fi
    ok "Migration completed."
}

run_target_schema_migrations() {
    section "Apply target schema migrations"
    require_docker || return 1
    (cd "$TARGET_DIR" && run_compose run --rm migrate) || return 1
    ok "Schema migrations completed."
}

prepare_compose_without_starting_apps() {
    section "Prepare target Compose stack"
    require_docker || return 1
    (cd "$TARGET_DIR" && run_compose up --no-start) || return 1
}

run_tgshop_volume_migration() {
    section "Old remnawave-tg-shop volume migration"
    warn "This path copies the old PostgreSQL Docker volume into the new Minishop volume."
    warn "Old volumes are not deleted; keep them until you verify the new stack."

    if confirm "Stop known old/current containers before copying volumes?" 1; then
        stop_known_legacy_containers || return 1
        (cd "$TARGET_DIR" && run_compose down) || true
    fi

    prepare_compose_without_starting_apps || return 1
    copy_volume_if_safe "$OLD_TGSHOP_DB_VOLUME" "$NEW_MINISHOP_DB_VOLUME" 1 || return 1
    copy_volume_if_safe "$OLD_TGSHOP_CADDY_DATA_VOLUME" "$NEW_MINISHOP_CADDY_DATA_VOLUME" 0 || return 1
    copy_volume_if_safe "$OLD_TGSHOP_CADDY_CONFIG_VOLUME" "$NEW_MINISHOP_CADDY_CONFIG_VOLUME" 0 || return 1

    if confirm "Start the new stack and let migrate apply schema changes now?" 1; then
        start_stack 0 || return 1
        (cd "$TARGET_DIR" && run_compose logs --tail 120 migrate) || true
    else
        warn "Stack was prepared but not started. Run docker compose up -d later."
    fi
}

run_tgshop_dsn_migration() {
    section "Old remnawave-tg-shop DSN migration"
    warn "This wizard path dumps the old PostgreSQL database, restores it into target Compose PostgreSQL, then runs Minishop schema migrations."
    warn "The target database will be dropped and recreated before restore."

    if ! confirm "Replace target database with the source dump?" 0; then
        warn "Migration not applied."
        return 0
    fi

    prompt_value "Source remnawave-tg-shop PostgreSQL DSN" "${LEGACY_TGSHOP_SOURCE_DSN:-}" 1 0 ""
    SOURCE_DSN="$PROMPT_VALUE"

    require_docker || return 1
    POSTGRES_USER_VALUE="$(env_get POSTGRES_USER '')"
    POSTGRES_PASSWORD_VALUE="$(env_get POSTGRES_PASSWORD '')"
    POSTGRES_DB_VALUE="$(env_get POSTGRES_DB '')"
    TARGET_DSN="$(local_target_dsn)"

    section "Start target PostgreSQL"
    (cd "$TARGET_DIR" && run_compose stop backend worker frontend migrate) || true
    (cd "$TARGET_DIR" && run_compose up -d postgres redis) || return 1
    wait_target_postgres || return 1

    section "Reset target database"
    (cd "$TARGET_DIR" && run_compose exec -T postgres sh -c \
        'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"') || return 1

    section "Dump and restore old database"
    (cd "$TARGET_DIR" && run_compose run --rm --no-deps \
        -e "SOURCE_DSN=$SOURCE_DSN" \
        -e "TARGET_DSN=$TARGET_DSN" \
        backend sh -lc \
        'pg_dump --clean --if-exists --no-owner --no-privileges "$SOURCE_DSN" | psql "$TARGET_DSN"') || return 1

    run_target_schema_migrations || return 1
    if confirm "Start the full stack now?" 1; then
        start_stack 0 || return 1
    fi
}

run_remnawave_tg_shop_migration() {
    section "Old remnawave-tg-shop migration"
    ENV_PATH="$TARGET_DIR/.env"
    if [ ! -f "$ENV_PATH" ]; then
        fail ".env not found. Install or generate configuration first."
        return 1
    fi
    require_docker || return 1

    choose "Migration method" "1" "1|2|3" \
        "1. Copy old Docker volumes on this host (recommended for old compose installs)." \
        "2. Dump from a source PostgreSQL DSN and restore into this compose stack." \
        "3. Skip migration"
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
    prompt_value "Install directory" "${MINISHOP_INSTALL_DIR:-$(pwd)}" 1 0 ""
    mkdir -p "$(dirname "$PROMPT_VALUE")"
    TARGET_DIR=$(cd "$(dirname "$PROMPT_VALUE")" && pwd)/$(basename "$PROMPT_VALUE")
    mkdir -p "$TARGET_DIR"
}

github_source() {
    prompt_value "GitHub repository" "$DEFAULT_REPO" 1 0 ""
    SOURCE_REPO="$PROMPT_VALUE"
    prompt_value "Git ref/branch/tag for raw files" "$DEFAULT_REF" 1 0 ""
    SOURCE_REF="$PROMPT_VALUE"
}

install_flow() {
    with_migration="$1"
    LEGACY_SOURCE=""
    installation_directory || return 1
    github_source || return 1
    choose_profile
    ENV_PATH="$TARGET_DIR/.env"
    if [ -f "$ENV_PATH" ]; then
        warn "Existing .env found at $ENV_PATH; wizard will preserve unknown values."
    fi
    prompt_common_env || return 1
    download_profile_files || return 1
    write_env_file || return 1
    mkdir -p "$TARGET_DIR/$INSTALL_STATE_DIR"
    prepare_data_mount || return 1
    if [ "$with_migration" = "1" ]; then
        choose_legacy_source
    elif confirm "Run a migration from another bot now?" 0; then
        choose_legacy_source
    fi

    case "$LEGACY_SOURCE" in
        remnawave-tg-shop)
            run_selected_legacy_migration
            ;;
        remnashop)
            if confirm "Start Docker Compose stack before Remnashop import?" 1; then
                start_stack || return 1
            else
                warn "Remnashop import needs the target stack database. Skipping import."
                return 0
            fi
            run_selected_legacy_migration
            ;;
        *)
            if confirm "Start Docker Compose stack now?" 1; then
                start_stack || return 1
            fi
            ;;
    esac
}

migration_only_flow() {
    LEGACY_SOURCE=""
    installation_directory || return 1
    choose_legacy_source
    [ "$LEGACY_SOURCE" = "skip" ] && return 0
    prepare_data_mount || return 1
    case "$LEGACY_SOURCE" in
        remnashop)
            github_source || return 1
            ;;
    esac
    run_selected_legacy_migration
}

download_only_flow() {
    installation_directory || return 1
    github_source || return 1
    choose_profile
    download_profile_files
}

health_flow() {
    installation_directory || return 1
    validate_stack
}

main_menu() {
    while :; do
        banner
        choose "Main menu" "1" "1|2|3|4|5|6" \
            "1. Install new stack" \
            "2. Install new stack and run migration" \
            "3. Run migration only" \
            "4. Download/update deployment files only" \
            "5. Validate current stack" \
            "6. Exit"
        case "$CHOICE_VALUE" in
            1) install_flow 0 ;;
            2) install_flow 1 ;;
            3) migration_only_flow ;;
            4) download_only_flow ;;
            5) health_flow ;;
            6) printf 'Bye.\n'; return 0 ;;
        esac
        status=$?
        if [ "$status" -ne 0 ]; then
            fail "Step failed with status $status."
        fi
        pause
    done
}

case "${1:-}" in
    -h|--help)
        print_help
        exit 0
        ;;
esac

main_menu
