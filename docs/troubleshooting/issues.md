# Проблемы

Начинайте диагностику с состояния контейнеров и логов, затем проверяйте публичные URL и секреты.

## Стек не стартует

- Проверьте `docker compose ps`.
- Посмотрите `docker compose logs migrate`.
- Убедитесь, что PostgreSQL и Redis здоровы.
- Проверьте обязательные переменные в `.env`.

Если в логах есть `password authentication failed for user "remnawave_minishop"` или
`InvalidPasswordError`, значит текущий `POSTGRES_PASSWORD` из `.env` не совпадает с уже
созданным Docker volume PostgreSQL. Для настоящей чистой установки удалите старый DB volume через
wizard или `docker compose down -v`; если данные нужны, верните старый пароль в `.env`.

## Вебхук Telegram не работает

- Проверьте `WEBHOOK_BASE_URL`.
- Убедитесь, что домен доступен по HTTPS.
- Проверьте `WEBHOOK_SECRET_TOKEN`.
- Посмотрите backend-логи на момент входящего события.

## Mini App не открывается

- Проверьте `SUBSCRIPTION_MINI_APP_URL`.
- Убедитесь, что URL указывает на frontend, а не на `/api` или webhook-домен.
- Проверьте настройки BotFather.
- Посмотрите frontend и backend-логи.

## Платеж не засчитался

- Проверьте включение провайдера.
- Проверьте URL вебхука и секреты.
- Посмотрите backend-логи.
- Сверьте статус платежа в админке и кабинете провайдера.

Подробности: [логи](logs.md) и [развертывание](../getting-started/deployment.md).
