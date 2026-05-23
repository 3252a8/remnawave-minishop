# Готовые варианты запуска

В этой папке лежат самодостаточные compose-примеры. Каждый вариант запускается из своей директории обычной командой:

```bash
cp .env.example .env
nano .env
docker compose up -d
```

После старта полезно проверить:

```bash
docker compose ps
docker compose logs -f backend worker frontend
```

## Какой вариант выбрать

| Папка | Когда использовать | Что править |
| --- | --- | --- |
| [`caddy`](caddy) | Нужен самый простой публичный HTTPS с автоматическими сертификатами Let's Encrypt. | `.env`; при нестандартной схеме можно поправить `Caddyfile`. |
| [`nginx`](nginx) | Уже используете Nginx и готовы положить TLS-сертификаты рядом с примером. | `.env`, `nginx.conf.template`, файлы в `ssl/`. |
| [`newt`](newt) | Публикуете сервисы через Pangolin/Newt без входящих портов на сервере приложения. | `.env` и ресурсы в панели Pangolin. |
| [`no-proxy`](no-proxy) | Нужно напрямую открыть порты backend/frontend или проверить стек без reverse proxy. | `.env`. |

Для всех вариантов нужны два публичных URL:

- webhook/backend URL для Telegram, платежных систем и Remnawave webhooks;
- Mini App/frontend URL для Telegram Mini App и Web App.

Обычно это два домена, например `webhooks.example.com` и `app.example.com`.

