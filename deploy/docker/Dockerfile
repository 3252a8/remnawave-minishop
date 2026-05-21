# Resolve the application version from .git at build time and emit a single
# tiny ``.build-version`` file. The .git tree is consumed in this throwaway
# stage and never copied into the runtime image — only the resulting one-line
# version string ships. This matches the runtime fallback chain in
# ``_resolve_app_version`` (REMNAWAVE_MINISHOP_VERSION env > .build-version
# file > live git > "dev+unknown") so the admin sidebar always shows a tag /
# sha even though the runtime images have no git tooling and no .git tree.
FROM alpine:3.20 AS version-builder
RUN apk add --no-cache git
WORKDIR /repo
COPY .git ./.git
RUN set -eu; \
    git config --global --add safe.directory /repo; \
    tag=$(git describe --tags --abbrev=0 2>/dev/null || true); \
    sha=$(git rev-parse --short HEAD 2>/dev/null || true); \
    dirty=$(git status --porcelain 2>/dev/null | head -c1 || true); \
    if [ -n "$tag" ] && [ -n "$sha" ]; then \
        commits_since_tag=$(git rev-list "$tag..HEAD" --count 2>/dev/null || true); \
        if [ -n "$commits_since_tag" ] && [ "$commits_since_tag" != "0" ]; then \
            version="${tag}+${commits_since_tag}.g${sha}"; \
        else \
            version="$tag"; \
        fi; \
    elif [ -n "$sha" ]; then \
        version="dev+g${sha}"; \
    else \
        version="dev+unknown"; \
    fi; \
    if [ -n "$dirty" ]; then version="${version}-dirty"; fi; \
    printf '%s' "$version" > /build-version; \
    printf '%s' "${tag:-unknown}" > /build-tag; \
    printf '%s' "${sha:-unknown}" > /build-commit


FROM python:3.12-slim AS python-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

RUN useradd -u 10001 -m appuser

COPY backend/requirements.txt backend/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY locales ./locales
COPY data ./data
COPY --from=version-builder /build-version /app/.build-version
COPY --from=version-builder /build-tag /app/.build-tag
COPY --from=version-builder /build-commit /app/.build-commit
RUN mkdir -p /app/logs /app/data && chown -R appuser:appuser /app/logs /app/data

USER appuser


FROM python-base AS backend

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


FROM node:22-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend ./
COPY backend/bot/app/web/templates ../backend/bot/app/web/templates

RUN npm run build:webapp


FROM nginx:1.27-alpine AS frontend

LABEL org.opencontainers.image.source="https://github.com/3252a8/remnawave-minishop" \
      org.opencontainers.image.title="remnawave-minishop-frontend" \
      org.opencontainers.image.description="Remnawave Minishop frontend (nginx serving the subscription Mini App)." \
      org.opencontainers.image.licenses="MIT"

COPY deploy/docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/docker/frontend/00-startup-banner.sh /docker-entrypoint.d/00-startup-banner.sh
COPY --from=version-builder /build-tag /build-tag
COPY --from=version-builder /build-commit /build-commit
COPY backend/bot/app/web/templates/subscription_webapp.html /usr/share/nginx/html/index.html
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp.css /usr/share/nginx/html/subscription_webapp.css
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp.*.css /usr/share/nginx/html/
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp.*.css.gz /usr/share/nginx/html/
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp_admin.css /usr/share/nginx/html/subscription_webapp_admin.css
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp_admin.*.css /usr/share/nginx/html/
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp_admin.*.css.gz /usr/share/nginx/html/
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp.js /usr/share/nginx/html/subscription_webapp.js
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp.min.*.js /usr/share/nginx/html/
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp.min.*.js.gz /usr/share/nginx/html/
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp_admin.js /usr/share/nginx/html/subscription_webapp_admin.js
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp_admin.min.*.js /usr/share/nginx/html/
COPY --from=frontend-builder /app/backend/bot/app/web/templates/subscription_webapp_admin.min.*.js.gz /usr/share/nginx/html/

RUN set -eu; \
    find /docker-entrypoint.d -type f -name '*.sh' -exec sed -i 's/\r$//' {} +; \
    HASHED=$(ls /usr/share/nginx/html/subscription_webapp.min.*.js 2>/dev/null | sort | tail -n1 | xargs -n1 basename || true); \
    JS_NAME="${HASHED:-subscription_webapp.js}"; \
    CSS_NAME="subscription_webapp.css"; \
    ADMIN_HASHED=$(ls /usr/share/nginx/html/subscription_webapp_admin.min.*.js 2>/dev/null | sort | tail -n1 | xargs -n1 basename || true); \
    ADMIN_CSS_NAME="subscription_webapp_admin.css"; \
    for candidate in /usr/share/nginx/html/subscription_webapp.*.css; do \
      name="$(basename "$candidate")"; \
      case "$name" in \
        subscription_webapp.[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f].css) CSS_NAME="$name" ;; \
      esac; \
    done; \
    for candidate in /usr/share/nginx/html/subscription_webapp_admin.*.css; do \
      name="$(basename "$candidate")"; \
      case "$name" in \
        subscription_webapp_admin.[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f].css) ADMIN_CSS_NAME="$name" ;; \
      esac; \
    done; \
    if [ -n "$ADMIN_HASHED" ]; then \
      cp "/usr/share/nginx/html/${ADMIN_HASHED}" /usr/share/nginx/html/subscription_webapp_admin.js; \
      if [ -f "/usr/share/nginx/html/${ADMIN_HASHED}.gz" ]; then cp "/usr/share/nginx/html/${ADMIN_HASHED}.gz" /usr/share/nginx/html/subscription_webapp_admin.js.gz; fi; \
    fi; \
    if [ "$ADMIN_CSS_NAME" != "subscription_webapp_admin.css" ]; then \
      cp "/usr/share/nginx/html/${ADMIN_CSS_NAME}" /usr/share/nginx/html/subscription_webapp_admin.css; \
      if [ -f "/usr/share/nginx/html/${ADMIN_CSS_NAME}.gz" ]; then cp "/usr/share/nginx/html/${ADMIN_CSS_NAME}.gz" /usr/share/nginx/html/subscription_webapp_admin.css.gz; fi; \
    fi; \
    sed -i \
      -e '/WEBAPP_I18N_SCRIPT/d' \
      -e '/WEBAPP_CONFIG_SCRIPT/d' \
      -e "s|href=\"/subscription_webapp.css\"|href=\"/${CSS_NAME}\"|" \
      -e "/WEBAPP_JS_SCRIPT/c\\  <script src=\"/${JS_NAME}\" type=\"module\"></script>" \
      -e '/WEBAPP_DEV_MOCK_START/d' \
      -e '/WEBAPP_DEV_MOCK_END/d' \
      -e '/subscription_webapp.js" defer/d' \
      /usr/share/nginx/html/index.html; \
    chmod +x /docker-entrypoint.d/00-startup-banner.sh

EXPOSE 80
