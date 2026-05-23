# Запуск с Caddy

Caddy сам выпускает и продлевает HTTPS-сертификаты. На сервере должны быть открыты входящие `80/tcp` и `443/tcp`, а DNS-записи `WEBHOOK_HOST` и `MINIAPP_HOST` должны смотреть на этот сервер.

```bash
cp .env.example .env
nano .env
docker compose up -d
```

Минимально поменяйте в `.env`:

- `WEBHOOK_HOST` и `MINIAPP_HOST`;
- `BOT_TOKEN`, `ADMIN_IDS`;
- `POSTGRES_PASSWORD`;
- `WEBAPP_SESSION_SECRET`, `WEBHOOK_SECRET_TOKEN`;
- `PANEL_API_URL`, `PANEL_API_KEY`, `PANEL_WEBHOOK_SECRET`.

`Caddyfile` лежит рядом и использует домены из `.env`. Если нужна нестандартная логика Caddy, правьте его и перезапускайте:

```bash
docker compose up -d --force-recreate caddy
```

Проверка:

```bash
docker compose ps
docker compose logs -f caddy backend worker frontend
```

