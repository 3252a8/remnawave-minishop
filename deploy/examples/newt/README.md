# Запуск через Newt / Pangolin

Этот вариант не открывает входящие порты на сервере приложения. Newt подключается к Pangolin, а публичные домены настраиваются ресурсами в панели Pangolin.

```bash
cp .env.example .env
nano .env
docker compose up -d
```

В `.env` заполните:

- `WEBHOOK_HOST` и `MINIAPP_HOST` - публичные домены ресурсов в Pangolin;
- `PANGOLIN_ENDPOINT`, `NEWT_ID`, `NEWT_SECRET` - значения из настроек site/client в Pangolin;
- обычные переменные приложения: `BOT_TOKEN`, `ADMIN_IDS`, `POSTGRES_PASSWORD`, секреты и доступ к Remnawave.

Официальная инструкция Pangolin по установке Newt site: <https://docs.pangolin.net/manage/sites/install-site>.

В Pangolin создайте два HTTP-ресурса для этого Newt site:

| Публичный домен | Upstream |
| --- | --- |
| `https://webhooks.example.com` | `http://backend:8080` |
| `https://app.example.com` | `http://frontend:80` |

Домены в Pangolin должны совпадать с `WEBHOOK_HOST` и `MINIAPP_HOST`.

Проверка:

```bash
docker compose ps
docker compose logs -f newt backend worker frontend
```
