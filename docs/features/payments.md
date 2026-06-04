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

> [!TIP]
> URL вебхука отображается вверху раздела каждого провайдера в админ-панели.

## Общие ссылки

- [Справочник `.env`](../configuration/env-vars.md) — все ключи платежных провайдеров.
- [Админ-панель](admin-panel.md) — UI-настройки платежей.
- [Тарифы](tariffs.md) — цены, Telegram Stars и сценарии покупки.
- [Логи](../troubleshooting/logs.md) — проверка webhook и создания платежных ссылок.

## Webhook URL провайдеров

Все платежные webhook URL строятся от `WEBHOOK_BASE_URL` — публичного HTTPS-адреса backend/webhook-домена.

Это должен быть домен, который проксируется на backend-сервер вебхуков (`backend:8080`), а не frontend/Mini App домен из `SUBSCRIPTION_MINI_APP_URL`.

Если `WEBHOOK_BASE_URL=https://bot.example.com`, полный webhook URL получается как `https://bot.example.com` + путь из таблицы.

| Провайдер | URL |
| --- | --- |
| YooKassa | `WEBHOOK_BASE_URL` + `/webhook/yookassa` |
| FreeKassa | `WEBHOOK_BASE_URL` + `/webhook/freekassa` |
| Platega | `WEBHOOK_BASE_URL` + `/webhook/platega` |
| SeverPay | `WEBHOOK_BASE_URL` + `/webhook/severpay` |
| Wata | `WEBHOOK_BASE_URL` + `/webhook/wata` |
| CryptoPay | `WEBHOOK_BASE_URL` + `/webhook/cryptopay` |
| Heleket | `WEBHOOK_BASE_URL` + `/webhook/heleket` |
| PayKilla | `WEBHOOK_BASE_URL` + `/webhook/paykilla` |
| Telegram Stars | `WEBHOOK_BASE_URL` + `/tg/webhook` |

После настройки сделайте тестовый платеж и проверьте, что в логах `backend` виден входящий `POST` на нужный путь.

Если провайдер сообщает, что адрес недоступен, проверьте DNS, HTTPS и reverse proxy для `WEBHOOK_BASE_URL`. Путь должен начинаться с `/webhook/...` без `/api`, `/auth` и frontend-домена.

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
2. Укажите `PLATEGA_BASE_URL`, `PLATEGA_MERCHANT_ID` и `PLATEGA_SECRET`.
3. Скопируйте URL вебхука из админ-панели и укажите его в кабинете Platega.
4. Проверьте `PLATEGA_RETURN_URL` и `PLATEGA_FAILED_URL`.
5. При необходимости укажите `PLATEGA_PAYMENT_METHOD`.

### Дополнительные кнопки

- `PLATEGA_SBP_ENABLED` — отдельная кнопка СБП/карта.
- `PLATEGA_SBP_METHOD` — ID метода для СБП/карты.
- `PLATEGA_CRYPTO_ENABLED` — отдельная crypto-кнопка Platega.
- `PLATEGA_CRYPTO_METHOD` — ID метода для crypto-кнопки.
- `PAYMENT_PLATEGA_SBP_*` — текст и иконка кнопки СБП/карта.
- `PAYMENT_PLATEGA_CRYPTO_*` — текст и иконка crypto-кнопки.

### Справочник

- [Platega](../configuration/env-vars.md#platega)

## SeverPay

SeverPay подключается как отдельный платежный метод с собственным MID, token и сроком жизни платежной ссылки.

### Настройка

1. Включите `SEVERPAY_ENABLED`.
2. Укажите `SEVERPAY_BASE_URL`.
3. Заполните `SEVERPAY_MID` и `SEVERPAY_TOKEN`.
4. Проверьте `SEVERPAY_RETURN_URL`.
5. Скопируйте URL вебхука из админ-панели и укажите его в кабинете SeverPay.
6. При необходимости задайте `SEVERPAY_LIFETIME_MINUTES`.

### Справочник

- [SeverPay](../configuration/env-vars.md#severpay)

## Wata

Wata подключается как отдельный провайдер с bearer token, платежными ссылками и опциональной проверкой подписи webhook.

### Настройка

1. Включите `WATA_ENABLED`.
2. Укажите `WATA_BASE_URL` и `WATA_API_TOKEN`.
3. Проверьте `WATA_RETURN_URL` и `WATA_FAILED_URL`.
4. Настройте `WATA_LINK_TTL_MINUTES`.
5. Скопируйте URL вебхука из админ-панели и укажите его в кабинете Wata.
6. При необходимости включите `WATA_WEBHOOK_VERIFY_SIGNATURE`.
7. Если используется проверка подписи, задайте `WATA_PUBLIC_KEY`.
8. Для IP-фильтрации заполните `WATA_TRUSTED_IPS`.

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

### Валюта invoice

Minishop создает invoice в валюте, которую PayKilla принимает в поле `currency`.

Если валюта тарифа входит в `PAYKILLA_INVOICE_CURRENCIES`, сумма отправляется как есть.

Если валюта тарифа не входит в список, сумма конвертируется в `PAYKILLA_CURRENCY`. По умолчанию рублевые тарифы конвертируются в `USD` через ExchangeRate-API с кэшем `PAYKILLA_EXCHANGE_RATE_CACHE_SECONDS`.

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
5. Оставьте `PAYKILLA_VERIFY_WEBHOOK_SIGNATURE=True`.

### Настройка

1. Включите `PAYKILLA_ENABLED`.
2. Укажите `PAYKILLA_API_KEY` и `PAYKILLA_SECRET_KEY`.
3. Оставьте `PAYKILLA_CURRENCY=USD`, если PayKilla не принимает валюту тарифов как invoice currency.
4. В `PAYKILLA_INVOICE_CURRENCIES` укажите валюты invoice, например `USD,EUR`.
5. В `PAYKILLA_PAYMENT_CURRENCIES` начните с `USDTTRC`.

### Справочник

- [PayKilla](../configuration/env-vars.md#paykilla)

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