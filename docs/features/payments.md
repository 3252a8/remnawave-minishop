# Платежи

Платежные методы включаются через `.env` или админ-панель, если параметр добавлен в allowlist настроек. В Mini App и Telegram-сценариях включённые методы отображаются как кнопки оплаты.

## Общий порядок настройки

1. Включите нужный провайдер.
2. Заполните публичные параметры, секреты и URL возврата.
3. Настройте webhook URL у провайдера, если он используется.
4. Проверьте порядок методов в `PAYMENT_METHODS_ORDER`.
5. Проверьте подписи и иконки кнопок оплаты.
6. Выполните тестовый платеж.
7. Проверьте логи `backend`.

> [!NOTE]
> Если URL возврата не задан явно, используется ссылка на Telegram-бота.

## Общие ссылки

- [Справочник `.env`](../configuration/env-vars.md) — все ключи платежных провайдеров.
- [Админ-панель](admin-panel.md) — UI-настройки платежей.
- [Тарифы](tariffs.md) — цены, Telegram Stars и сценарии покупки.
- [Логи](../troubleshooting/logs.md) — проверка webhook и создания платежных ссылок.

## Webhook URL провайдеров
> [!TIP]
> Готовый URL вебхука отображается вверху раздела каждого провайдера в админ-панели.

Все платежные webhook URL строятся от `WEBHOOK_BASE_URL` - публичного HTTPS-адреса backend/webhook-домена. Это должен быть домен, который проксируется на backend-сервер вебхуков (`backend:8080`), а не `SUBSCRIPTION_MINI_APP_URL` frontend/Mini App. Если `WEBHOOK_BASE_URL=https://bot.example.com`, то полный адрес получается как `https://bot.example.com` + путь из таблицы.

Если у провайдера включена IP-фильтрация (`FREEKASSA_TRUSTED_IPS`, `WATA_TRUSTED_IPS`,
`HELEKET_TRUSTED_IPS`, `PAYKILLA_TRUSTED_IPS` или встроенный allowlist YooKassa),
reverse proxy должен прокидывать `X-Forwarded-For`, а его IP/CIDR должен входить в
`TRUSTED_PROXIES`. Иначе backend увидит IP proxy/Docker gateway и может отклонить
валидный webhook с ошибкой `403`.

| Провайдер | Что указать в кабинете провайдера | Комментарий |
| --- | --- | --- |
| YooKassa | `WEBHOOK_BASE_URL` + `/webhook/yookassa` | Например `https://bot.example.com/webhook/yookassa`. |
| FreeKassa | `WEBHOOK_BASE_URL` + `/webhook/freekassa` | Используйте как notification/webhook URL; при IP-фильтрации заполните `FREEKASSA_TRUSTED_IPS`. |
| Platega | `WEBHOOK_BASE_URL` + `/webhook/platega` | Один общий webhook для основной, СБП/карты и crypto-кнопки Platega. |
| SeverPay | `WEBHOOK_BASE_URL` + `/webhook/severpay` | Укажите как callback/webhook URL, если поле есть в кабинете мерчанта. |
| Wata | `WEBHOOK_BASE_URL` + `/webhook/wata` | Если включена проверка подписи, настройте `WATA_WEBHOOK_VERIFY_SIGNATURE` и `WATA_PUBLIC_KEY`. |
| CryptoPay | `WEBHOOK_BASE_URL` + `/webhook/cryptopay` | Указывается в настройках Crypto Bot / CryptoPay webhook. |
| Heleket | `WEBHOOK_BASE_URL` + `/webhook/heleket` | При необходимости включите `HELEKET_VERIFY_WEBHOOK_SIGNATURE` и `HELEKET_TRUSTED_IPS`. |
| PayKilla | `WEBHOOK_BASE_URL` + `/webhook/paykilla` | Указывается в PayKilla Dashboard -> Settings -> Webhooks; включите события оплаты инвойсов. |
| LAVA | `WEBHOOK_BASE_URL` + `/webhook/lava` | Передается автоматически как `hookUrl` при создании счета; можно также указать в кабинете LAVA Business. |
| CloudPayments | `WEBHOOK_BASE_URL` + `/webhook/cloudpayments` | Укажите как адрес уведомлений Pay и Fail в кабинете CloudPayments. При IP-фильтрации заполните `CLOUDPAYMENTS_TRUSTED_IPS`. |
| Telegram Stars | Отдельный платежный webhook не нужен | Stars-события приходят через webhook Telegram-бота: `WEBHOOK_BASE_URL` + `/tg/webhook`. |

После настройки сделайте тестовый платеж и проверьте, что в логах `backend` видно входящий `POST` на нужный путь. Если провайдер сообщает, что адрес недоступен, сначала проверьте DNS/HTTPS и reverse proxy для `WEBHOOK_BASE_URL`, затем убедитесь, что путь начинается ровно с `/webhook/...` без `/api`, `/auth` и frontend-домена.

## YooKassa

YooKassa используется для рублевых оплат. Провайдер также может участвовать в сценариях автопродления period-подписок.

### Настройка

1. Включите `YOOKASSA_ENABLED`.
2. Заполните `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` и `YOOKASSA_RETURN_URL`.
3. Скопируйте URL вебхука из админ-панели и укажите его в кабинете YooKassa.

### Справочник

- [YooKassa](../configuration/env-vars.md#yookassa)

## FreeKassa

FreeKassa подключается как отдельный платежный метод. Входящие webhook-события обрабатываются через `backend`.

### Настройка

1. Включите `FREEKASSA_ENABLED`.
2. Заполните `FREEKASSA_MERCHANT_ID`, `FREEKASSA_FIRST_SECRET`, `FREEKASSA_SECOND_SECRET` и `FREEKASSA_API_KEY`.
3. Проверьте настройки подписи.
4. Скопируйте URL вебхука из админ-панели и укажите его в кабинете FreeKassa.
5. При необходимости заполните `FREEKASSA_TRUSTED_IPS`.

### Справочник

- [FreeKassa](../configuration/env-vars.md#freekassa)

## Platega

Platega подключается как отдельный платежный провайдер. Внутри Minishop он может создавать несколько кнопок: основную legacy-кнопку, СБП/карту и crypto-кнопку.

### Настройка

1. Включите `PLATEGA_ENABLED`.
3. Укажите `PLATEGA_MERCHANT_ID` и `PLATEGA_SECRET`.
2. Включите необходимые кнопки `PLATEGA_SBP_ENABLED`, `PLATEGA_CRYPTO_ENABLED`.
4. Скопируйте URL вебхука из админ-панели и укажите его в кабинете Platega.

### Справочник

- [Platega](../configuration/env-vars.md#platega)

## SeverPay

SeverPay подключается как отдельный платежный метод с собственным MID, token и сроком жизни платежной ссылки.

### Настройка

1. Включите `SEVERPAY_ENABLED`.
2. Укажите `SEVERPAY_BASE_URL`.
3. Заполните `SEVERPAY_MID` и `SEVERPAY_TOKEN`.
4. Скопируйте URL вебхука из админ-панели и укажите его в кабинете SeverPay.
5. При необходимости задайте `SEVERPAY_LIFETIME_MINUTES`.

### Справочник

- [SeverPay](../configuration/env-vars.md#severpay)

## Wata

Wata подключается как отдельный провайдер с bearer token, платежными ссылками и опциональной проверкой подписи webhook.

### Настройка

1. Включите `WATA_ENABLED`.
2. Укажите `WATA_BASE_URL` и `WATA_API_TOKEN`.
3. Настройте `WATA_LINK_TTL_MINUTES`.
4. Скопируйте URL вебхука из админ-панели и укажите его в кабинете Wata.
5. При необходимости включите `WATA_WEBHOOK_VERIFY_SIGNATURE`.
6. Если используется проверка подписи, задайте `WATA_PUBLIC_KEY`.
7. Для IP-фильтрации заполните `WATA_TRUSTED_IPS`.

### Ограничения

- `WATA_LINK_TTL_MINUTES` должен быть от `15` до `43200`.

### Справочник

- [Wata](../configuration/env-vars.md#wata)

## CryptoPay

CryptoPay используется для криптовалютных платежей через отдельный токен и сеть Crypto Bot API.

### Настройка

1. Включите `CRYPTOPAY_ENABLED`.
2. Укажите `CRYPTOPAY_TOKEN`.
3. Выберите `CRYPTOPAY_NETWORK`: `mainnet` или `testnet`.
4. Задайте `CRYPTOPAY_CURRENCY_TYPE`: `fiat` или `crypto`.
5. Проверьте `CRYPTOPAY_ASSET`, например `RUB`, `USDT` или `BTC`.
6. Скопируйте URL вебхука из админ-панели и укажите его в CryptoPay.

### Проверка

- Testnet-токен должен использоваться только с `testnet`.
- Mainnet-токен должен использоваться только с `mainnet`.
- Если сумма или asset выглядят неверно, проверьте сочетание `CRYPTOPAY_CURRENCY_TYPE` и `CRYPTOPAY_ASSET`.

### Справочник

- [CryptoPay](../configuration/env-vars.md#cryptopay)

## Heleket

Heleket используется для крипто-инвойсов с merchant ID, ключом платежного API, валютой инвойса и настройками проверки webhook.

### Настройка

1. Включите `HELEKET_ENABLED`.
2. Укажите `HELEKET_BASE_URL`, `HELEKET_MERCHANT_ID` и `HELEKET_API_KEY`.
3. Настройте `HELEKET_CURRENCY`.
4. При необходимости задайте `HELEKET_TO_CURRENCY` и `HELEKET_NETWORK`.
5. Проверьте `HELEKET_RETURN_URL` и `HELEKET_SUCCESS_URL`.
6. Настройте `HELEKET_LIFETIME_SECONDS`.
7. Скопируйте URL вебхука из админ-панели и укажите его в кабинете Heleket.
8. При необходимости включите `HELEKET_VERIFY_WEBHOOK_SIGNATURE`.
9. Для IP-фильтрации заполните `HELEKET_TRUSTED_IPS`.

### Ограничения

- `HELEKET_LIFETIME_SECONDS` должен быть от `300` до `43200`.

### Справочник

- [Heleket](../configuration/env-vars.md#heleket)

## PayKilla

PayKilla используется для крипто-инвойсов V2 через hosted checkout `https://gopay.paykilla.com/{invoice_id}`.

API-запросы подписываются HMAC-SHA256. Webhook проверяется по заголовку `X-API-SIGN` и raw body.

### Особенности

- PayKilla строго валидирует текстовые поля invoice.
- В `purpose` и `description` Minishop отправляет простой английский текст `<WEBAPP_TITLE> payment <id>`.
- Локализованное описание платежа остается только внутри Minishop.
- ASCII-safe sanitizer допускает ASCII-буквы, цифры, пробелы, `_`, `.`, `,`.
- Минимальная сумма платежа задается настройками `PAYKILLA_MIN_PAYMENT_AMOUNT` и `PAYKILLA_MIN_PAYMENT_CURRENCY`; по умолчанию это `10 USD`.
- Если выбранный тариф/пакет ниже этого порога после конвертации, Telegram bot не показывает кнопку PayKilla, WebApp показывает метод неактивным, а API создания платежа возвращает ошибку `payment_amount_below_minimum`.

### Валюта invoice

Minishop создает invoice в валюте, которую PayKilla принимает в поле `currency`.

Если валюта тарифа входит в `PAYKILLA_INVOICE_CURRENCIES`, сумма отправляется как есть.

Если валюта тарифа не входит в список, сумма конвертируется в `PAYKILLA_CURRENCY`. По умолчанию рублевые тарифы конвертируются в `USD` через ExchangeRate-API с кэшем `PAYKILLA_EXCHANGE_RATE_CACHE_SECONDS`.

Перед созданием invoice Minishop читает `GET /api/v2/currency` и проверяет `invoiceMin`/`invoiceMax` для валюты инвойса. Этот endpoint также показывает актуальные currency/payment-method ограничения конкретного merchant account.

### Payload invoice

Payload создания invoice содержит обязательные поля `type`, `purpose`, `currency`, `totalPrice` и `paymentCurrencies`.

Дополнительно отправляются `clientOrderId`, `description`, `expiredAt`, `userPaysServiceFee` и `userPaysNetworkFee`.

Redirect URLs в PayKilla не отправляются. Завершение платежа обрабатывается через webhook.

### API key

1. В PayKilla Dashboard откройте **Settings -> API keys**.
2. Создайте ключ типа **HMAC**.
3. Для приема оплат включите permission **INVOICE**.
4. Permission **WITHDRAWAL** не нужен для Minishop-платежей.
5. Сохраните `publicKey` в `PAYKILLA_API_KEY`.
6. Сохраните `secretKey` в `PAYKILLA_SECRET_KEY`.

### Webhook

1. В PayKilla Dashboard откройте **Settings -> Webhooks**.
2. Скопируйте URL вебхука из админ-панели и укажите его в PayKilla.
3. Включите минимальные события: `INVOICE_PAID`, `INVOICE_EXPIRED`.
4. Для production также включите `PAYMENT_COMPLETED`, `PAYMENT_FAILED`, `PAYMENT_OVERPAID`, `PAYMENT_UNDERPAID`, `PAYMENT_PARTIAL`, `COMPLIANCE_FAILED`.
5. Если нужны промежуточные статусы в логах, дополнительно включите `INVOICE_CREATED`, `PAYMENT_PENDING`, `TRANSACTION_CONFIRMED` и `TRANSACTION_FINAL`.
6. Оставьте `PAYKILLA_VERIFY_WEBHOOK_SIGNATURE=True`.

### Настройка

1. Включите `PAYKILLA_ENABLED`.
2. Укажите `PAYKILLA_API_KEY` и `PAYKILLA_SECRET_KEY`.
3. Оставьте `PAYKILLA_CURRENCY=USD`, если PayKilla не принимает валюту тарифов как invoice currency. В `PAYKILLA_INVOICE_CURRENCIES` укажите валюты, доступные в PayKilla для поля `currency`, например `USD,EUR`.
4. В `PAYKILLA_PAYMENT_CURRENCIES` оставьте `USDTTRC,BTC,ETH,USDTBSC,USDTTON` или укажите другой список тикеров, доступных в PayKilla Dashboard; `USDTTRC` должен идти первым.
5. Оставьте `PAYKILLA_MIN_PAYMENT_AMOUNT=10` и `PAYKILLA_MIN_PAYMENT_CURRENCY=USD`, если минимальный invoice PayKilla равен `10 USD`.
6. Убедитесь, что webhook `/webhook/paykilla` настроен в PayKilla: Minishop не отправляет redirect URLs в PayKilla и полагается на webhook для активации платежа.
7. Добавьте `paykilla` в `PAYMENT_METHODS_ORDER`, если хотите задать явный порядок кнопок.

### Справочник

- [PayKilla](../configuration/env-vars.md#paykilla)

## LAVA

LAVA Business используется для рублевых оплат картами и СБП через счета `https://api.lava.ru`.

Исходящие API-запросы подписываются HMAC-SHA256 от raw body, подпись передается в заголовке `Signature`. Webhook проверяется по заголовку `Authorization`: принимается подпись raw body или sorted-keys JSON (legacy PHP SDK).

### Особенности

- Счета выставляются только в рублях (`RUB`).
- `hookUrl` передается автоматически при создании счета, если задан `WEBHOOK_BASE_URL`.
- `LAVA_INCLUDE_SERVICES` ограничивает способы оплаты на странице счета, например `card,sbp`.
- При успешной оплате сумма из webhook сверяется с суммой платежа; расхождение отклоняется.

### Настройка

1. Включите `LAVA_ENABLED`.
2. Укажите `LAVA_SHOP_ID` и `LAVA_SECRET_KEY` из кабинета LAVA Business.
3. Если магазин использует отдельный дополнительный ключ для вебхуков, задайте `LAVA_WEBHOOK_SECRET`; пустое значение означает использование `LAVA_SECRET_KEY`.
4. При необходимости задайте `LAVA_LIFETIME_MINUTES` (1..7200) и `LAVA_RETURN_URL`.
5. Скопируйте URL вебхука из админ-панели и при необходимости укажите его в кабинете LAVA.

### Справочник

- [LAVA](../configuration/env-vars.md#lava)

## CloudPayments

CloudPayments используется для оплат картами через Orders API `https://api.cloudpayments.ru/orders/create`.

Исходящие запросы авторизуются HTTP Basic auth: логин — `CLOUDPAYMENTS_PUBLIC_ID`, пароль — `CLOUDPAYMENTS_API_SECRET`. Уведомления Pay/Fail приходят как `application/x-www-form-urlencoded` и подписываются HMAC-SHA256 (base64) от raw body на `CLOUDPAYMENTS_API_SECRET` в заголовке `Content-HMAC` (старые интеграции — `X-Content-HMAC`).

### Особенности

- Платёж создаётся как заказ (order) со ссылкой `https://orders.cloudpayments.ru/...`; `InvoiceId` — это внутренний ID платежа.
- Поддерживаемые валюты: `RUB`, `USD`, `EUR`, `GBP`, `KZT`, `UAH`, `BYN`, `AZN`, `AMD`, `KGS`.
- При успешной оплате сумма из webhook сверяется с суммой платежа; расхождение отклоняется кодом `12`.
- При `CLOUDPAYMENTS_RECURRING_ENABLED=true` Pay webhook сохраняет CloudPayments `Token` как способ оплаты пользователя, а автопродление выполняет merchant-initiated запрос `/payments/tokens/charge` с `TrInitiatorCode=0` и `PaymentScheduled=1`.
- Встроенные CloudPayments subscriptions не используются: срок подписки, HWID-продления, отмена автопродления и повторная активация остаются в общей логике бота.
- Backend отвечает CloudPayments телом `{"code": 0}` при успешной обработке.

### Настройка

1. Включите `CLOUDPAYMENTS_ENABLED`.
2. Укажите `CLOUDPAYMENTS_PUBLIC_ID` и `CLOUDPAYMENTS_API_SECRET` из кабинета CloudPayments.
3. При необходимости задайте `CLOUDPAYMENTS_RETURN_URL` и `CLOUDPAYMENTS_FAILED_URL`.
4. Скопируйте URL вебхука из админ-панели и укажите его в CloudPayments как адрес уведомлений Pay и Fail.
5. Для автопродления включите получение `Token` в уведомлении Pay на стороне CloudPayments и задайте `CLOUDPAYMENTS_RECURRING_ENABLED=true`.
6. Для IP-фильтрации при необходимости заполните `CLOUDPAYMENTS_TRUSTED_IPS`.

### Справочник

- [CloudPayments](../configuration/env-vars.md#cloudpayments)

## Telegram Stars

Telegram Stars используются напрямую и поддерживаются в legacy-ценах и JSON-каталоге тарифов.

### Где используются

- Цены period-подписок.
- Пакеты трафика.
- Premium-докупки.
- HWID-докупки, если они включены в каталоге тарифов.

### Настройка

1. Включите `STARS_ENABLED`.
2. Проверьте Stars-цены в legacy-настройках или JSON-каталоге.
3. Убедитесь, что цена округляется до целого количества Stars.
4. Проверьте сценарии смены тарифа.

### Ограничения

- Отдельный платежный webhook не нужен.
- Stars-события приходят через webhook Telegram-бота: `WEBHOOK_BASE_URL` + `/tg/webhook`.
- XTR/Stars-докупки не конвертируются без явно заданного курса.

### Справочник

- [Переменные платежей](../configuration/env-vars.md#платежи)
- [Тарифы](tariffs.md)
