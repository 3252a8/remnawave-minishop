# Миграция из Bedolaga

Minishop умеет переносить данные из PostgreSQL
[Bedolaga](https://docs.bedolagam.ru/) через общий importer.
Поддерживаются проверенные ревизии Alembic `0110` и `0118`. Для неизвестной
ревизии разрешены inventory и dry-run, но применение блокируется.

## Что переносится

- Telegram- и email-учетные записи, подтвержденные email и OAuth-идентичности;
- реферальные связи и коды;
- тарифы с точными периодами в днях, ценами, трафиком, устройствами и squads;
- все подписки, включая истекшие, отключенные и использованные trial;
- история транзакций и баланс в целочисленных minor units;
- оплаченные и доставленные подарки; неоплаченные записи архивируются без entitlement;
- совместимые промокоды и их использования;
- обращения поддержки и сообщения;
- рекламные кампании и атрибуции;
- партнерские профили и заявки;
- безопасно сопоставимые настройки и порядок платежных методов.

Пароли, refresh/session tokens, коды подтверждения, временные OAuth-состояния и
другие активные секреты пользователей не переносятся. Значения секретных
настроек никогда не попадают в JSON-отчеты.

## Безопасность

Source и target должны быть разными базами. Source-соединение переводится в
read-only transaction. `--dry-run` не запускает миграции схемы target и подавляет
любые ORM/SQL-записи в target. Повторный apply идемпотентен благодаря
`legacy_import_mappings`, provider/idempotency keys платежей и ledger.

Перед apply wizard предлагает сделать бэкап Minishop. Исходный стек не меняется
во время inventory, dry-run и импорта. После успешного apply отдельное
подтверждение запускает автоматический cutover; при неуспешном запуске или
healthcheck Minishop wizard восстанавливает прежний `.env` и пытается вернуть
Bedolaga в работу.

## Ручной запуск

Сначала выполните проверку:

```bash
python backend/scripts/import_legacy.py \
  --source-type bedolaga \
  --source-dsn 'postgresql://source_user:source_password@source-db:5432/bedolaga' \
  --target-dsn 'postgresql://target_user:target_password@target-db:5432/minishop' \
  --source-env-file /opt/bedolaga/.env \
  --dry-run \
  --inventory-output .installer/bedolaga-inventory.json \
  --config-plan-output .installer/bedolaga-config-plan.json \
  --summary-output .installer/bedolaga-dry-run-summary.json \
  --reconciliation-output .installer/bedolaga-dry-run-reconciliation.json
```

Убедитесь, что `blockers` пуст, `balance_total_matches` равен `true`, а
`identity_conflicts` и `unresolved_panel_subscriptions` разобраны. Затем повторите
команду без `--dry-run`, сохранив apply-отчеты под отдельными именами.

Для управляемого сценария запустите `scripts/install.sh`, выберите миграцию и
источник Bedolaga. Wizard находит локальный `.env`, PostgreSQL-контейнер и
compose-проект, создает pre-migration backup, выполняет dry-run и просит
подтверждение apply. Перед записью он показывает замаскированный план и может
автоматически перенести в `.env` Minishop совместимые bootstrap-настройки:

- `BOT_TOKEN`, `ADMIN_IDS` и Telegram webhook secret;
- URL/API key Remnawave Panel;
- Telegram и Google OAuth/OIDC client credentials;
- публичные hostnames из Bedolaga webhook/cabinet URL;
- язык, log level, timezone и совместимые параметры локальных бэкапов.

Пароли PostgreSQL/Redis, session/JWT secrets Bedolaga и несовместимые runtime
параметры не копируются. Существующий `.env` Minishop сохраняется рядом как
бэкап. Inventory, config plan, summary и reconciliation остаются в
`.installer/`; после apply там же создается `bedolaga-post-migration.md`.

## Сопоставление учетных записей

Importer объединяет пользователя только по устойчивой идентичности: Telegram,
подтвержденному email, OAuth subject или panel id. Если признаки указывают на
разные учетные записи Minishop, запись попадает в `identity_conflicts` и не
объединяется автоматически. Для email-only записей используется стабильный
отрицательный внутренний id из отдельного диапазона; старые password hashes и
сессии не копируются.

## Финансовая сверка

Завершенные пополнения, реферальные начисления, списания подписок и подарков
переносятся в append-only ledger в копейках. Для каждой учетной записи создается
идемпотентная opening-balance adjustment, которая сводит ledger к текущему
`balance_kopeks` источника. Исторические операции `new`, `change` и `renew`
сохраняются как платежная история, но не меняют баланс повторно.

После apply сравните количество пользователей/подписок/платежей и итог minor
units в reconciliation. Отдельно проверьте активные подписки с синтетическим
`bedolaga-unresolved:*`: они сохранены, но требуют ручной привязки к пользователю
актуальной Remnawave Panel до запуска runtime sync.

## Настройки и cutover

Config plan показывает только allowlist-сопоставления. Секреты помечаются как
`<redacted>`. После успешного apply wizard предлагает выполнить cutover. При
подтверждении он:

1. проверяет, что Bedolaga не запускается через cron;
2. останавливает весь исходный compose-проект без удаления контейнеров, volume
   или БД;
3. выставляет исходным контейнерам Docker restart policy `no`, отключает
   подтвержденные systemd units Bedolaga и проверяет, что старый стек не работает;
4. запускает Minishop, ждет готовности backend/worker/frontend и выполняет
   штатную проверку стека и Panel API;
5. для профиля eGames переключает webhook Remnawave Panel;
6. еще раз проверяет, что Bedolaga не перезапустилась.

При ручном target DSN автоматический cutover не выполняется, потому что wizard
не может безопасно управлять удаленным Minishop. Платежные provider credentials,
их webhook URLs, обязательные каналы, юридические страницы и кастомное меню все
равно нужно проверить вручную: у этих значений нет универсального безопасного
сопоставления между проектами.

## Внешние кабинеты после миграции

В конце сценария wizard печатает адреса для нового Minishop. Он не может сам
изменить redirect/callback или webhook URL в кабинетах сторонних сервисов, поэтому
обновите адреса вручную для каждой включенной интеграции.

OIDC callback строятся от frontend-адреса `MINIAPP_PUBLIC_URL`:

- Telegram BotFather Web Login / OIDC: `/auth/telegram/callback`;
- Google Cloud, **Authorized redirect URIs**: `/auth/google/callback`;
- Yandex OAuth, **Redirect URI**: `/auth/yandex/callback`.

Платежные webhook строятся от backend-адреса `WEBHOOK_BASE_URL`:

| Провайдер | Путь webhook |
| --- | --- |
| YooKassa | `/webhook/yookassa` |
| FreeKassa | `/webhook/freekassa` |
| Platega | `/webhook/platega` |
| RollyPay | `/webhook/rollypay` |
| SeverPay | `/webhook/severpay` |
| WATA | `/webhook/wata` |
| Crypto Pay | `/webhook/cryptopay` |
| Heleket | `/webhook/heleket` |
| OxaPay | `/webhook/oxapay` |
| PayKilla | `/webhook/paykilla` |
| LAVA | `/webhook/lava` |
| Pally / PayPalych | `/webhook/pally` |
| CloudPayments | `/webhook/cloudpayments` |
| Overpay | `/webhook/overpay` |
| Stripe | `/webhook/stripe` |
| Tribute | `/webhook/tribute` |

OxaPay передает callback автоматически при создании счета, а LAVA передает
`hookUrl`, но после смены домена их также стоит проверить. Telegram Stars
использует общий webhook бота `/tg/webhook` и отдельной настройки платежного
webhook не требует.

После изменения адресов выполните тестовый вход через каждый включенный
OIDC-провайдер и тестовый платеж через каждый включенный платежный провайдер.
Подробные требования к событиям, подписям и allowlist описаны в разделах
[способы входа](../features/login-methods.md) и
[платежные провайдеры](../features/payments.md).
