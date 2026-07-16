# Примеры Docker Compose

Каноничная документация по вариантам запуска живет в [docs/getting-started/deployment.md](../../docs/getting-started/deployment.md).

Эта папка хранит только рабочие compose-примеры и конфиги. Подробное описание не дублируется здесь, чтобы сайт документации и навигация из README использовали один источник.

Файлы приложения (`/app/data`: тарифы, темы, логотипы) монтируются из папки `data` рядом с выбранным `docker-compose.yml` в `migrate`, `backend` и `worker`. Для кастомных тем создайте `data/themes`; для ручного каталога тарифов используйте `data/tariffs.json`.

| Папка   | Документация                                                                                                                                           |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `caddy`    | [Развертывание с Caddy](../../docs/getting-started/deployment.md#caddy-рекомендуемый-вариант)                                       |
| `angie`    | [Развертывание с Angie](../../docs/getting-started/deployment.md#angie)                                                                                 |
| `nginx`    | [Развертывание с Nginx](../../docs/getting-started/deployment.md#nginx)                                                                                 |
| `newt`     | [Развертывание через Pangolin / Newt](../../docs/getting-started/deployment.md#pangolin--newt)                                                      |
| `no-proxy` | [Запуск без обратного прокси](../../docs/getting-started/deployment.md#без-обратного-прокси)                                |
| `mail`     | [Развертывание локального SMTP-сервера](../../docs/features/email-login.md#настройка-локального-smtp-сервера) |
