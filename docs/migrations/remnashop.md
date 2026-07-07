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

Wizard полностью русскоязычный. В главном меню выберите:

- `Установить новый remnawave-minishop и мигрировать данные из другого бота` -
  для нового сервера;
- `Мигрировать данные в уже установленный remnawave-minishop` - если
  compose-папка и `.env` уже готовы.

Если wizard находит Remnashop на этом же сервере, он предлагает миграцию из
него по умолчанию и подставляет найденные значения в уже заполненные ответы.

Для отдельного сервера выбирайте профиль `Caddy HTTPS`: это дефолтный вариант
wizard с автоматическими сертификатами. Если Remnawave Panel уже установлена на
этом же хосте скриптом [`eGamesAPI/remnawave-reverse-proxy`](https://github.com/eGamesAPI/remnawave-reverse-proxy),
выберите профиль `Уже установленная Remnawave через eGames - использовать ее
Nginx/TLS`. В этом режиме wizard использует no-proxy compose, прописывает
`DEPLOYMENT_PROFILE=egames` и сам добавляет server-блоки для backend/webhook-домена
и Mini App в найденный `nginx.conf` eGames. После применения миграции wizard
перечитывает eGames Nginx (`nginx -t`, затем reload или restart контейнера),
чтобы Mini App/frontend не оставался за старым upstream.

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
- `REMNAWAVE_COOKIE` -> `PANEL_API_COOKIE`;
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

После успешного применения wizard в самом конце печатает раздел
`Дальнейшие шаги` со списком новых адресов webhook. В профиле `egames` он
дополнительно обновляет `WEBHOOK_URL` в найденном `.env` Remnawave Panel и
перезапускает backend панели. Остальные внешние платежные webhook нужно указать
во внешних сервисах вместо старых Remnashop URL:

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

## Сценарий wizard

Importer автоматически строит `TARIFFS_CONFIG_PATH` из Remnashop `plans`,
`plan_durations` и `plan_prices`, затем сопоставляет plan id/name/tag/public_code
с созданным `tariff_key`. Используйте `--tariff-map-json` только если нужно
переопределить это автоматическое сопоставление.

1. Wizard использует папку установки `/opt/remnawave-minishop` по умолчанию,
   скачивает выбранный compose-профиль и `backend/scripts/import_legacy.py`
   через `raw.githubusercontent.com`, без клонирования репозитория. Repository
   и ref не спрашиваются в обычном сценарии; для fork/dev-ветки задайте
   `MINISHOP_INSTALL_REPO` и `MINISHOP_INSTALL_REF` перед запуском.
2. Wizard пытается найти Remnashop PostgreSQL, `.env`, `BOT_TOKEN`,
   `BOT_OWNER_ID`/`ADMIN_IDS`, `BOT_SECRET_TOKEN`, Remnawave API URL/key/cookie
   и webhook secret, затем показывает найденные значения как уже заполненный
   ответ. Enter оставляет найденное значение.
3. Вы указываете source PostgreSQL DSN Remnashop. Schema источника по умолчанию
   `public` и не спрашивается в обычном wizard; для редкого кастомного случая
   задайте `REMNASHOP_SOURCE_SCHEMA=custom_schema`.
4. Опционально указываете путь к старому Remnashop `.env` для `APP_CRYPT_KEY`,
   Remnawave API settings, Telegram settings и переносимых provider settings.
5. Вы выбираете целевую БД: текущую compose-БД или ручной target DSN. Для
   текущей compose-БД wizard предлагает pre-migration backup в
   `backups/pre-remnashop-migration-*`; внутри будут основные файлы деплоя,
   PostgreSQL dump при доступной БД и `restore.sh`.
6. При необходимости указываете JSON map тарифов Remnashop в локальные
   `tariff_key`, например `{"basic": "standard_month"}`.
7. Wizard запускает проверку без записи (`dry-run`), показывает краткую сводку
   и сохраняет полный JSON/raw-вывод в `.installer/remnashop-dry-run-summary.json`.
8. После подтверждения `y` importer применяет изменения. У вопроса применения
   дефолт `Y`, поэтому Enter после успешной проверки означает "применить";
   `n` остановит миграцию без записи.
9. После применения wizard сохраняет apply-сводку, обновляет webhook Remnawave
   Panel для eGames-профиля, перезапускает `backend`, `worker` и `frontend`,
   перечитывает eGames Nginx при необходимости, отправляет Telegram-уведомление
   админам/лог-чату и в финальном разделе `Дальнейшие шаги` показывает новые
   webhook URL.

Если source DB находится на том же Docker host и host в DSN совпадает с именем
контейнера, например `remnashop-db`, wizard сам подключит этот контейнер к сети
`<COMPOSE_PROJECT_NAME>-network` (по умолчанию `remnawave-minishop-network`) перед dry-run. Для подключения к сервису
вне Docker по-прежнему используйте `host.docker.internal` или внешний адрес
сервера.

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
