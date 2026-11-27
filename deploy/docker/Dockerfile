# Official builds receive verified Git metadata from CI. Only a local source
# build needs Git or the checkout history in its build context.
ARG VERSION_SOURCE=git
FROM alpine:3.24@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf AS version-input-ci
WORKDIR /repo

FROM version-input-ci AS version-input-git
COPY deploy/docker/retry_apk.sh /tmp/retry_apk.sh
RUN sh /tmp/retry_apk.sh add --no-cache git
RUN --mount=type=bind,source=.git,target=/repo/.git \
    git config --global --add safe.directory /repo && \
    { git describe --tags --abbrev=0 2>/dev/null || true; } > /git-tag && \
    { git rev-parse --short HEAD 2>/dev/null || true; } > /git-commit && \
    { git symbolic-ref --quiet --short HEAD 2>/dev/null || true; } > /git-branch

FROM version-input-${VERSION_SOURCE} AS version-builder
ARG REMNAWAVE_MINISHOP_BRANCH=""
ARG GIT_BRANCH=""
ARG BRANCH_NAME=""
ARG GITHUB_REF_NAME=""
ARG CI_COMMIT_REF_NAME=""
ARG REMNAWAVE_MINISHOP_BUILD_PROVENANCE="custom"
ARG REMNAWAVE_MINISHOP_BUILD_TAG=""
ARG REMNAWAVE_MINISHOP_BUILD_COMMIT=""
RUN set -eu; \
    tag="$REMNAWAVE_MINISHOP_BUILD_TAG"; \
    sha="$REMNAWAVE_MINISHOP_BUILD_COMMIT"; \
    branch="${REMNAWAVE_MINISHOP_BRANCH:-${GIT_BRANCH:-${BRANCH_NAME:-${GITHUB_REF_NAME:-${CI_COMMIT_REF_NAME:-}}}}}"; \
    if [ -z "$sha" ] && [ -f /git-commit ]; then \
        sha=$(cat /git-commit); \
        tag=${tag:-$(cat /git-tag)}; \
        branch=${branch:-$(cat /git-branch)}; \
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


FROM ubuntu:24.04@sha256:562111b88caa79c71391c0c4d3c2114a7d5c35915c20561fd893cb1e07929e6b AS python-dependencies

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# The publisher rotates this cache key daily and forces a fresh release or retry.
ARG REMNAWAVE_MINISHOP_APK_REFRESH=""

# A 502 from an Ubuntu mirror fails the image build outright, so index refreshes
# retry instead of taking the release down with them.
RUN set -eux; \
    : "$REMNAWAVE_MINISHOP_APK_REFRESH"; \
    printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n' \
      > /etc/apt/apt.conf.d/99-minishop-retries; \
    apt_update_with_retries() { \
      for attempt in 1 2 3 4 5; do \
        if apt-get update; then return 0; fi; \
        echo "apt-get update failed (attempt ${attempt}/5), retrying" >&2; \
        sleep "$((attempt * 10))"; \
      done; \
      return 1; \
    }; \
    apt_update_with_retries; \
    DEBIAN_FRONTEND=noninteractive apt-get upgrade -y; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      python3.12 \
      python3.12-venv; \
    # CVE-2026-111497: require the fixed Noble Brotli decoder used by curl.
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libbrotli1)" ge '1.1.0-2ubuntu0.1'; \
    . /etc/os-release; \
    install -d /usr/share/postgresql-common/pgdg; \
    # APT accepts the upstream ASCII-armored key directly.
    curl --fail --silent --show-error --location \
      --retry 4 --retry-all-errors --retry-max-time 150 --connect-timeout 15 --max-time 45 \
      --output /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list; \
    apt_update_with_retries; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends postgresql-client-17; \
    python3.12 -m venv "$VIRTUAL_ENV"; \
    # Python 3.12 seeds only pip. Keep Ubuntu's matching ensurepip module for
    # new virtual environments, then supply the same pip wheel used below.
    cp -a /usr/lib/python3.12/ensurepip /tmp/ensurepip; \
    apt-get purge -y python3.12-venv python3-pip-whl python3-setuptools-whl; \
    mv /tmp/ensurepip /usr/lib/python3.12/ensurepip; \
    rm -rf /var/lib/apt/lists/*

RUN useradd -u 10001 -m appuser

COPY backend/requirements.txt backend/requirements.txt
RUN --mount=type=bind,source=deploy/docker/refresh_pip_vendor.py,target=/tmp/refresh_pip_vendor.py \
    --mount=type=cache,target=/root/.cache/pip \
    set -eu; \
    tools=/tmp/pip-wheel; \
    pip_version=26.3; \
    pip install --only-binary=:all: --no-compile --target "$tools" "wheel==0.48.0" "packaging==26.3"; \
    pip download --only-binary=:all: --no-deps --dest "$tools" "pip==$pip_version"; \
    PYTHONPATH="$tools" python -m wheel unpack --dest "$tools" "$tools"/pip-*.whl; \
    python /tmp/refresh_pip_vendor.py "$tools/pip-$pip_version"; \
    SOURCE_DATE_EPOCH=315532800 PYTHONPATH="$tools" python -m wheel pack --dest-dir "$tools" "$tools/pip-$pip_version"; \
    pip install --no-index --no-deps --no-compile "$tools"/pip-*.whl; \
    install -D -m 0644 -t /usr/share/python-wheels "$tools"/pip-*.whl; \
    rm -rf "$tools"; \
    python -m pip install --no-compile -r backend/requirements.txt; \
    python -m pip check

FROM python-dependencies AS python-base

COPY --link locales ./locales
COPY --chown=appuser:appuser data ./data
RUN mkdir -p /app/logs /app/data \
    && if [ ! -f /app/data/locales-overrides.json ]; then printf '{}\n' > /app/data/locales-overrides.json; fi \
    && chown appuser:appuser /app/logs /app/data /app/data/locales-overrides.json
COPY --link backend ./backend
COPY --from=version-builder /build-version /app/.build-version
COPY --from=version-builder /build-tag /app/.build-tag
COPY --from=version-builder /build-commit /app/.build-commit
COPY --from=version-builder /build-provenance /app/.build-provenance

USER appuser


FROM node:26.13.1-slim@sha256:abe7e5a82b61a8ef67b315b85497c9e65173387ccf2f4a029248184b8e020be5 AS node-runtime

FROM node-runtime AS blacklist-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

COPY frontend/plugins/blacklist ./plugins/blacklist
COPY frontend/scripts/build-blacklist.mjs ./scripts/build-blacklist.mjs
COPY backend/bot/plugins/builtin/blacklist ../backend/bot/plugins/builtin/blacklist
RUN npm run build:blacklist

FROM blacklist-builder AS frontend-builder
COPY frontend ./
COPY backend/config/defaults/svg_policy.json ../backend/config/defaults/svg_policy.json
RUN npm run build:webapp
COPY backend/bot/app/web/templates/subscription_webapp.html ../backend/bot/app/web/templates/subscription_webapp.html
RUN node ./scripts/prepare_nginx_assets.mjs --out ../frontend-nginx-dist


FROM python-base AS backend

COPY --link --from=blacklist-builder /app/backend/bot/plugins/builtin/blacklist/dist/ ./backend/bot/plugins/builtin/blacklist/dist/

USER root

# The Mini App shell is rendered by the backend, which rewrites the stylesheet
# and script tags to the content-hashed asset names (subscription_webapp.<hash>.css).
# Those hashed files are build artifacts and gitignored, so a clean checkout has
# none of them: without this copy the asset resolver falls back to the bare
# /subscription_webapp.css URL. That URL never changes between deploys and is
# served no-store, which iOS WebViews (WKWebView) cache aggressively and refuse to
# revalidate -> stale CSS and a broken-looking Mini App on iOS only. Pull the
# freshly built assets (the same hashes the nginx image serves) into the image so
# the shell emits immutable, cache-busting URLs.
COPY --link --from=frontend-builder /app/backend/bot/app/web/templates/ ./backend/bot/app/web/templates/
COPY --chmod=755 deploy/docker/backend-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["/usr/local/bin/backend-entrypoint.sh"]

# GitHub source URL (disabled): https://github.com/3252a8/remnawave-minishop
LABEL org.opencontainers.image.source="https://gitlab.com/3252a8/remnawave-minishop" \
      org.opencontainers.image.title="remnawave-minishop-backend" \
      org.opencontainers.image.description="Remnawave Minishop backend (Telegram bot API, web app, webhooks)." \
      org.opencontainers.image.licenses="MIT"

EXPOSE 8080 8081
CMD ["python", "backend/plugin_launcher.py", "backend"]


FROM docker:29.9.3-cli@sha256:5a7af0dcb0e46c803efe9b45371dd21cb500e5b4453250394ac6f06d49b6e6f1 AS docker-test-tools

FROM python-dependencies AS qa-deps

# The optional test image supplies POSIX shell tools on Windows hosts too.
# It is never used as an application runtime image.
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      bash \
      git \
      libatomic1 \
      openssl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements-dev.txt
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=docker-test-tools /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-test-tools /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins
COPY --from=node-runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node --version && npm --version
LABEL minishop.test.runtime="core" minishop.local.keep="true"
WORKDIR /workspace
CMD ["python", "-m", "pytest"]

FROM qa-deps AS qa
# Keep Git history out of the QA layer on supported Docker 25 builders too.
RUN --mount=type=bind,target=/src \
    find /src -mindepth 1 -maxdepth 1 ! -name .git -exec cp -a -t /workspace -- {} +
CMD ["python", "-m", "pytest"]


FROM python-base AS worker

COPY --link --from=blacklist-builder /app/backend/bot/plugins/builtin/blacklist/dist/ ./backend/bot/plugins/builtin/blacklist/dist/

# GitHub source URL (disabled): https://github.com/3252a8/remnawave-minishop
LABEL org.opencontainers.image.source="https://gitlab.com/3252a8/remnawave-minishop" \
      org.opencontainers.image.title="remnawave-minishop-worker" \
      org.opencontainers.image.description="Remnawave Minishop background worker (scheduled jobs, async tasks)." \
      org.opencontainers.image.licenses="MIT"

CMD ["python", "backend/plugin_launcher.py", "worker"]


FROM nginx:1.30.7-alpine@sha256:caf4e1e032a20f9c3c5e28fc7f25ffd768ad8677b4975c54193075997b3a97e3 AS nginx-brotli-builder

# Only the static module ships: it serves files compressed by the web build.
# The pinned nginx base determines its ABI. Release builds refresh the tools.
COPY deploy/docker/retry_apk.sh /tmp/retry_apk.sh
RUN sh /tmp/retry_apk.sh add --no-cache gcc linux-headers make musl-dev pcre2-dev zlib-dev
RUN set -eu; \
    nginx_version="$(nginx -v 2>&1 | sed 's#nginx version: nginx/##')"; \
    cd /tmp; \
    curl -fsSL --retry 4 --retry-all-errors -o nginx.tar.gz "https://nginx.org/download/nginx-${nginx_version}.tar.gz"; \
    tar -xzf nginx.tar.gz; \
    curl -fsSL --retry 4 --retry-all-errors -o ngx_brotli.tar.gz \
      https://codeload.github.com/google/ngx_brotli/tar.gz/25f86f0bac1101b6512135eac5f93c49c63609e3; \
    echo 'd044ea1393d0a5cf6ddfaf44bd0f5df3e295ab8f02fd45be8da4c868524e0c93  ngx_brotli.tar.gz' | sha256sum -c -; \
    mkdir ngx_brotli; tar -xzf ngx_brotli.tar.gz -C ngx_brotli --strip-components=1; \
    cd "nginx-${nginx_version}"; \
    ./configure \
        --with-compat \
        --with-cc-opt='-Wno-error=vla-parameter -Wno-error=unterminated-string-initialization' \
        --add-dynamic-module=../ngx_brotli/static; \
    make modules; \
    mkdir -p /brotli-modules; \
    strip -o /brotli-modules/ngx_http_brotli_static_module.so objs/ngx_http_brotli_static_module.so


FROM nginx:1.30.7-alpine@sha256:caf4e1e032a20f9c3c5e28fc7f25ffd768ad8677b4975c54193075997b3a97e3 AS frontend

ARG REMNAWAVE_MINISHOP_APK_REFRESH=""
COPY deploy/docker/retry_apk.sh /tmp/retry_apk.sh
# GitHub source URL (disabled): https://github.com/3252a8/remnawave-minishop
LABEL org.opencontainers.image.source="https://gitlab.com/3252a8/remnawave-minishop" \
      org.opencontainers.image.title="remnawave-minishop-frontend" \
      org.opencontainers.image.description="Remnawave Minishop frontend (nginx serving the subscription Mini App)." \
      org.opencontainers.image.licenses="MIT"

COPY --from=nginx-brotli-builder /brotli-modules/ngx_http_brotli_static_module.so /usr/lib/nginx/modules/
RUN set -eu; \
    : "$REMNAWAVE_MINISHOP_APK_REFRESH"; \
    sh /tmp/retry_apk.sh upgrade --no-cache; \
    rm /tmp/retry_apk.sh; \
    sed -i '1i load_module modules/ngx_http_brotli_static_module.so;' /etc/nginx/nginx.conf
COPY deploy/docker/frontend/nginx.conf /etc/nginx/minishop/default.conf.template
COPY --chmod=755 deploy/docker/frontend/00-startup-banner.sh /docker-entrypoint.d/00-startup-banner.sh
COPY deploy/docker/frontend/robots.txt /usr/share/nginx/html/robots.txt
COPY --link --from=frontend-builder /app/frontend-nginx-dist/ /usr/share/nginx/html/
COPY --from=version-builder /build-tag /build-tag
COPY --from=version-builder /build-commit /build-commit

EXPOSE 80
