# Запуск без reverse proxy

Этот вариант напрямую публикует два HTTP-порта:

- backend/webhooks: `WEB_SERVER_BIND`, по умолчанию `0.0.0.0:8080`;
- frontend/Mini App: `FRONTEND_BIND`, по умолчанию `0.0.0.0:8082`.

```bash
cp .env.example .env
nano .env
docker compose up -d
```

Важно: контейнеры приложения сами не выпускают TLS-сертификаты. Для реального Telegram webhook и Mini App публичные URL должны быть HTTPS. Используйте этот вариант для локальной проверки, внутренней сети или когда HTTPS уже завершается внешней платформой и дальше трафик приходит на эти порты.

Проверка локально:

```bash
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8082/health
docker compose logs -f backend worker frontend
```

