# Resolve the application version from .git at build time and emit a tiny
# .build-version file. The .git tree is consumed in this throwaway stage and
# never copied into the runtime image; only the tag + commit version string and
# a low-cardinality build provenance marker ship. Non-main builds include the
# branch name so they are visibly distinct from release builds. This matches the
# runtime fallback chain in _resolve_app_version (REMNAWAVE_MINISHOP_VERSION env
# > .build-version file > live git > "dev+unknown") so the admin sidebar always
# shows a tag / sha even though the runtime images have no git tooling and no
# .git tree.
FROM alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc AS version-builder
RUN apk add --no-cache git
WORKDIR /repo
ARG REMNAWAVE_MINISHOP_BRANCH=""
ARG GIT_BRANCH=""
ARG BRANCH_NAME=""
ARG GITHUB_REF_NAME=""
ARG CI_COMMIT_REF_NAME=""
ARG REMNAWAVE_MINISHOP_BUILD_PROVENANCE="custom"
ARG REMNAWAVE_MINISHOP_BUILD_TAG=""
ARG REMNAWAVE_MINISHOP_BUILD_COMMIT=""
COPY .git ./.git
RUN set -eu; \
    tag="$REMNAWAVE_MINISHOP_BUILD_TAG"; \
    sha="$REMNAWAVE_MINISHOP_BUILD_COMMIT"; \
    branch="${REMNAWAVE_MINISHOP_BRANCH:-${GIT_BRANCH:-${BRANCH_NAME:-${GITHUB_REF_NAME:-${CI_COMMIT_REF_NAME:-}}}}}"; \
    if [ -z "$sha" ]; then \
        git config --global --add safe.directory /repo; \
        if [ -z "$tag" ]; then tag=$(git describe --tags --abbrev=0 2>/dev/null || true); fi; \
        if [ -z "$sha" ]; then sha=$(git rev-parse --short HEAD 2>/dev/null || true); fi; \
        if [ -z "$branch" ]; then branch=$(git branch --show-current 2>/dev/null || true); fi; \
        if [ -z "$branch" ]; then branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true); fi; \
    fi; \
    case "$branch" in \
        refs/heads/*) branch="${branch#refs/heads/}" ;; \
        refs/remotes/origin/*) branch="${branch#refs/remotes/origin/}" ;; \
        origin/*) branch="${branch#origin/}" ;; \
        HEAD) branch="" ;; \
    esac; \
    branch_slug=$(printf '%s' "$branch" | sed -E 's/[^A-Za-z0-9._-]+/-/g; s/^-+//; s/-+$//' | cut -c1-48); \
    branch_suffix=""; \
    if [ -n "$branch_slug" ] && [ "$branch_slug" != "main" ]; then branch_suffix="-$branch_slug"; fi; \
    if [ -n "$tag" ] && [ -n "$sha" ]; then \
        version="${tag}${branch_suffix}+g${sha}"; \
    elif [ -n "$sha" ]; then \
        version="dev${branch_suffix}+g${sha}"; \
    elif [ -n "$tag" ]; then \
        version="${tag}${branch_suffix}"; \
    else \
        version="dev${branch_suffix}+unknown"; \
    fi; \
    provenance=$(printf '%s' "$REMNAWAVE_MINISHOP_BUILD_PROVENANCE" | tr '[:upper:]' '[:lower:]'); \
    case "$provenance" in \
        official|custom|unknown) ;; \
        true|1|yes|upstream|release) provenance="official" ;; \
        false|0|no|fork|modified|local|"") provenance="custom" ;; \
        *) provenance="custom" ;; \
    esac; \
    printf '%s' "$version" > /build-version; \
    printf '%s' "${tag:-unknown}" > /build-tag; \
    printf '%s' "${sha:-unknown}" > /build-commit; \
    printf '%s' "$provenance" > /build-provenance


FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90 AS python-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get upgrade -y; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      gnupg \
      python3.12 \
      python3.12-venv; \
    . /etc/os-release; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      | gpg --dearmor -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends postgresql-client-17; \
    python3.12 -m venv "$VIRTUAL_ENV"; \
    # Keep curl in the runtime image: it backs the container healthcheck. A
    # spawned curl is far cheaper than booting a full Python interpreter every
    # interval. Only gnupg (build-time key import) is purged here.
    apt-get purge -y --auto-remove gnupg; \
    rm -rf /var/lib/apt/lists/*

RUN useradd -u 10001 -m appuser

COPY backend/requirements.txt backend/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r backend/requirements.txt

COPY locales ./locales
COPY data ./data
COPY backend ./backend
RUN mkdir -p /app/logs /app/data \
    && if [ ! -f /app/data/locales-overrides.json ]; then printf '{}\n' > /app/data/locales-overrides.json; fi \
    && chown -R appuser:appuser /app/logs /app/data
COPY --from=version-builder /build-version /app/.build-version
COPY --from=version-builder /build-tag /app/.build-tag
COPY --from=version-builder /build-commit /app/.build-commit
COPY --from=version-builder /build-provenance /app/.build-provenance

USER appuser


FROM node:22-slim@sha256:53ada149d435c38b14476cb57e4a7da73c15595aba79bd6971b547ceb6d018bf AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend ./
RUN mkdir -p ../backend/bot/app/web/templates

RUN npm run build:webapp
COPY backend/bot/app/web/templates/subscription_webapp.html ../backend/bot/app/web/templates/subscription_webapp.html
RUN node ./scripts/prepare_nginx_assets.mjs --out ../frontend-nginx-dist


FROM python-base AS backend

# The Mini App shell is rendered by the backend, which rewrites the stylesheet
# and script tags to the content-hashed asset names (subscription_webapp.<hash>.css).
# Those hashed files are build artifacts and gitignored, so a clean checkout has
# none of them: without this copy the asset resolver falls back to the bare
# /subscription_webapp.css URL. That URL never changes between deploys and is
# served no-store, which iOS WebViews (WKWebView) cache aggressively and refuse to
# revalidate -> stale CSS and a broken-looking Mini App on iOS only. Pull the
# freshly built assets (the same hashes the nginx image serves) into the image so
# the shell emits immutable, cache-busting URLs.
COPY --from=frontend-builder /app/backend/bot/app/web/templates/ ./backend/bot/app/web/templates/

LABEL org.opencontainers.image.source="https://github.com/3252a8/remnawave-minishop" \
      org.opencontainers.image.title="remnawave-minishop-backend" \
      org.opencontainers.image.description="Remnawave Minishop backend (Telegram bot API, web app, webhooks)." \
      org.opencontainers.image.licenses="MIT"

EXPOSE 8080 8081
CMD ["python", "backend/main_backend.py"]


FROM python-base AS worker

LABEL org.opencontainers.image.source="https://github.com/3252a8/remnawave-minishop" \
      org.opencontainers.image.title="remnawave-minishop-worker" \
      org.opencontainers.image.description="Remnawave Minishop background worker (scheduled jobs, async tasks)." \
      org.opencontainers.image.licenses="MIT"

CMD ["python", "backend/main_worker.py"]


FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 AS nginx-brotli-builder

RUN set -eu; \
    apk upgrade --no-cache; \
    apk add --no-cache \
        build-base \
        git \
        linux-headers \
        openssl-dev \
        pcre2-dev \
        wget \
        zlib-dev; \
    nginx_version="$(nginx -v 2>&1 | sed 's#nginx version: nginx/##')"; \
    cd /tmp; \
    wget -q "https://nginx.org/download/nginx-${nginx_version}.tar.gz"; \
    tar -xzf "nginx-${nginx_version}.tar.gz"; \
    git clone --branch v1.0.0rc --depth 1 --recurse-submodules \
        https://github.com/google/ngx_brotli.git; \
    cd "nginx-${nginx_version}"; \
    ./configure \
        --with-compat \
        --with-cc-opt='-Wno-error=vla-parameter' \
        --add-dynamic-module=../ngx_brotli; \
    make modules; \
    mkdir -p /brotli-modules; \
    cp objs/ngx_http_brotli_static_module.so /brotli-modules/


FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 AS frontend

LABEL org.opencontainers.image.source="https://github.com/3252a8/remnawave-minishop" \
      org.opencontainers.image.title="remnawave-minishop-frontend" \
      org.opencontainers.image.description="Remnawave Minishop frontend (nginx serving the subscription Mini App)." \
      org.opencontainers.image.licenses="MIT"

COPY --from=nginx-brotli-builder /brotli-modules/ngx_http_brotli_static_module.so /usr/lib/nginx/modules/
RUN set -eu; \
    apk upgrade --no-cache; \
    sed -i '1i load_module modules/ngx_http_brotli_static_module.so;' /etc/nginx/nginx.conf
COPY deploy/docker/frontend/nginx.conf /etc/nginx/minishop/default.conf.template
COPY deploy/docker/frontend/00-startup-banner.sh /docker-entrypoint.d/00-startup-banner.sh
COPY deploy/docker/frontend/robots.txt /usr/share/nginx/html/robots.txt
RUN set -eu; \
    find /docker-entrypoint.d -type f -name '*.sh' -exec sed -i 's/\r$//' {} +; \
    chmod +x /docker-entrypoint.d/00-startup-banner.sh
COPY --from=frontend-builder /app/frontend-nginx-dist/ /usr/share/nginx/html/
COPY --from=version-builder /build-tag /build-tag
COPY --from=version-builder /build-commit /build-commit

EXPOSE 80
