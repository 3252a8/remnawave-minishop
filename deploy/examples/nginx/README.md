# Запуск с Nginx

Этот пример поднимает Nginx в той же Docker-сети, что и приложение:

- `WEBHOOK_HOST` проксируется в `backend:8080`;
- `MINIAPP_HOST` проксируется в `frontend:80`;
- `frontend` сам проксирует внутренние `/api`, `/auth` и ассеты тем в `backend:8081`.

## Подготовка

```bash
cp .env.example .env
nano .env
```

Положите TLS-сертификаты в `ssl/`:

```text
ssl/
  webhooks.example.com/
    fullchain.pem
    privkey.pem
  app.example.com/
    fullchain.pem
    privkey.pem
```

Имена папок должны совпадать с `WEBHOOK_HOST` и `MINIAPP_HOST` в `.env`.

## Запуск

```bash
docker compose up -d
docker compose logs -f nginx backend worker frontend
```

Если нужно поменять заголовки, лимиты или TLS-настройки, правьте `nginx.conf.template` рядом с compose и перезапускайте Nginx:

```bash
docker compose up -d --force-recreate nginx
```

