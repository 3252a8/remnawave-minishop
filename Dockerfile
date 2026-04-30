FROM python:3.12-slim AS python-builder

WORKDIR /app

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt


FROM node:22-slim AS webapp-builder

WORKDIR /webapp

COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY bot/app/web/frontend ./bot/app/web/frontend
COPY bot/app/web/templates ./bot/app/web/templates
COPY scripts/build_subscription_webapp_js.mjs ./scripts/build_subscription_webapp_js.mjs

RUN npm run build:webapp


FROM python:3.12-slim

WORKDIR /app

LABEL org.opencontainers.image.source="https://github.com/3252a8/remnawave-minishop"

RUN useradd -u 10001 -m appuser

COPY --from=python-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

COPY . .

# Replace template assets with freshly built ones
RUN rm -f bot/app/web/templates/subscription_webapp.css \
          bot/app/web/templates/subscription_webapp.js \
          bot/app/web/templates/subscription_webapp.min.*.js
COPY --from=webapp-builder /webapp/bot/app/web/templates/subscription_webapp.css \
                           bot/app/web/templates/subscription_webapp.css
COPY --from=webapp-builder /webapp/bot/app/web/templates/subscription_webapp.js \
                           bot/app/web/templates/subscription_webapp.js
COPY --from=webapp-builder /webapp/bot/app/web/templates/subscription_webapp.min.*.js \
                           bot/app/web/templates/

RUN rm -rf /root/.cache

RUN mkdir -p /app/logs /app/data && chown -R appuser:appuser /app/logs /app/data

USER appuser

CMD ["python", "main.py"]
