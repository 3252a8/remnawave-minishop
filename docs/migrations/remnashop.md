# Миграция из Remnashop

Remnashop импортируется через общий скрипт импорта `backend/scripts/import_legacy.py`.
Самый удобный путь - интерактивный install wizard:

```bash
curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/install.sh -o install.sh
sh install.sh
```

Та же ссылка на install-скрипт в GitLab:

```bash
curl -fsSL https://gitlab.com/3252a8/remnawave-minishop/-/raw/main/scripts/install.sh -o install.sh
sh install.sh
```

В меню выберите `Install new stack and run migration` для нового сервера
или `Run migration only`, если compose-папка и `.env` уже готовы.

## Что переносится

- пользователи Telegram, username, email, Remnawave UUID и метаданные профиля;
- старые referral codes и связи рефералов;
- подписки, сроки, лимиты трафика, HWID/device limit и UUID подписок панели;
- платежи и статусы платежей;
- промокоды на дни подписки и их активации, если таблицы есть в source DB;
- служебные mappings, чтобы повторный запуск мог работать в режиме `merge`;
- настройки совместимости Remnashop в админке: старые ref-ссылки и promo codes.

Данные, которые не имеют прямого аналога, сохраняются в служебных таблицах миграции или
message logs как заметки, чтобы администратор мог проверить их после переноса.

## Настройки и платежные провайдеры

Если указать старый Remnashop `.env`, importer дополнительно переносит часть
настроек в админские overrides:

- `REMNAWAVE_HOST` -> `PANEL_API_URL`;
- `REMNAWAVE_TOKEN` -> `PANEL_API_KEY`;
- `REMNAWAVE_WEBHOOK_SECRET` -> `PANEL_WEBHOOK_SECRET`;
- `BOT_SUPPORT_USERNAME` -> `SUPPORT_LINK`;
- `APP_DEFAULT_LOCALE` -> `DEFAULT_LANGUAGE`.

`BOT_MINI_APP` из Remnashop не переносится автоматически. В Remnashop эта
переменная управляет кнопкой подключения к subscription page или внешнему Mini
App, а не веб-кабинетом Remnashop. В Minishop `SUBSCRIPTION_MINI_APP_URL`
должен указывать на текущий frontend/Mini App этого стека; wizard настраивает
его из `WEBHOOK_HOST`/`MINIAPP_HOST` или `MINIAPP_PUBLIC_URL`.

Значения-заглушки вроде `change_me` importer пропускает, чтобы случайно не
записать шаблонные секреты в рабочую конфигурацию.

Платежные провайдеры берутся из таблицы Remnashop `payment_gateways`.
Поддерживаются и автоматически маппятся: Telegram Stars, YooKassa, WATA,
CryptoPay, Heleket, PayKilla, FreeKassa и Platega. Для них importer переносит флаги
включения, API-ключи/merchant IDs и прямые технические параметры, без которых
провайдер не сможет работать: YooKassa receipt email/VAT, FreeKassa second
secret/payment method/server IP и Platega payment method.

Provider currency и supported-currency ограничения не переносятся автоматически:
в Minishop валюта платежа управляется тарифами и `DEFAULT_CURRENCY_SYMBOL`.
Если старый gateway Remnashop был настроен на нестандартную валюту, importer
оставит предупреждение в JSON-сводке; проверьте `CRYPTOPAY_ASSET`,
`HELEKET_CURRENCY`, `HELEKET_SUPPORTED_CURRENCIES`, `PAYKILLA_CURRENCY`,
`PAYKILLA_PAYMENT_CURRENCIES` или
`PLATEGA_SUPPORTED_CURRENCIES` вручную.

Провайдеры YooMoney, Cryptomus, MulenPay, PayMaster, RoboKassa и UrlPay сейчас
не имеют прямого аналога в Minishop. Если они были в Remnashop, importer
оставит предупреждение в JSON-сводке и notes миграции, а настроить их нужно
вручную или через будущий отдельный provider.

Remnashop может хранить секреты в формате `enc_...`. Для расшифровки нужен
старый `APP_CRYPT_KEY`; проще всего указать путь к старому `.env` в wizard или
передать `--source-env-file`. Если ключ не передан или неверный, зашифрованные
значения будут пропущены с предупреждением, остальные данные продолжат
импортироваться.

После успешного применения wizard печатает список новых адресов webhook. Их
нужно указать во внешних сервисах вместо старых Remnashop URL:

- Remnawave Panel -> `WEBHOOK_URL`: `WEBHOOK_BASE_URL` + `/webhook/panel`;
- YooKassa HTTP notifications URL: `WEBHOOK_BASE_URL` + `/webhook/yookassa`;
- WATA webhook/callback URL: `WEBHOOK_BASE_URL` + `/webhook/wata`;
- CryptoBot/Crypto Pay webhook URL: `WEBHOOK_BASE_URL` + `/webhook/cryptopay`;
- Heleket payment webhook/callback URL: `WEBHOOK_BASE_URL` + `/webhook/heleket`;
- PayKilla webhook URL: `WEBHOOK_BASE_URL` + `/webhook/paykilla`;
- FreeKassa notification/result URL: `WEBHOOK_BASE_URL` + `/webhook/freekassa`;
- Platega webhook URL: `WEBHOOK_BASE_URL` + `/webhook/platega`;
- Telegram webhook `WEBHOOK_BASE_URL` + `/tg/webhook` выставляется ботом
  автоматически при старте.

## Flow wizard

1. Wizard скачивает compose-профиль и `backend/scripts/import_legacy.py` через
   `raw.githubusercontent.com`, без клонирования репозитория.
2. Вы указываете source PostgreSQL DSN Remnashop и schema, обычно `public`.
3. Опционально указываете путь к старому Remnashop `.env` для `APP_CRYPT_KEY`,
   Remnawave API settings и переносимых settings.
4. Вы выбираете целевую БД: текущую compose-БД или ручной target DSN.
5. При необходимости указываете JSON map тарифов Remnashop в локальные
   `tariff_key`, например `{"basic": "standard_month"}`.
6. Wizard запускает `dry-run` и показывает JSON-сводку.
7. После подтверждения `y` importer применяет изменения, печатает список новых
   webhook URL для Remnawave Panel и платежных провайдеров, затем перезапускает
   `backend`/`worker`, чтобы настройки совместимости перечитались.

Если source DB находится на том же Docker host, помните, что DSN выполняется
из backend-контейнера. Для подключения к сервису вне compose-сети может
понадобиться host name вроде `host.docker.internal`, внешний адрес сервера или
ручное подключение контейнеров к общей Docker network.

## Ручной запуск

Если нужно запустить importer без wizard:

```bash
docker compose run --rm backend \
  python backend/scripts/import_legacy.py \
    --source-type remnashop \
    --source-dsn 'postgresql://old_user:old_password@old_host:5432/remnashop' \
    --source-schema public \
    --source-env-file /path/to/remnashop/.env \
    --dry-run
```

После успешного `dry-run` повторите команду без `--dry-run`. По умолчанию
режим конфликтов `merge`: существующие пользователи и платежи сопоставляются,
а новые записи добавляются. Для узкого импорта используйте `--only`, например
`--only users,referrals,promocodes`.
