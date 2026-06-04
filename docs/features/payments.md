# Платежи

Платежные методы включаются настройками и отображаются пользователю как кнопки оплаты в Mini App и Telegram-сценариях. Настройки можно задавать через `.env` или через админку, если параметр есть в allowlist настроек.

## Типовой порядок настройки

1. Включите нужный провайдер в админке или через `.env`.
2. Заполните публичные параметры, секреты и URL возврата.
3. Настройте URL вебхука у провайдера, если это требуется.
4. Проверьте порядок методов в `PAYMENT_METHODS_ORDER`.
5. Проверьте подписи и иконки кнопок оплаты.
6. Выполните тестовый платеж и проверьте логи `backend`.

Общие ссылки:

- [Справочник `.env`](../configuration/env-vars.md) содержит все ключи провайдеров.
- [Админ-панель](admin-panel.md) описывает UI-настройки платежей.
- [Тарифы](tariffs.md) описывают цены, Telegram Stars и сценарии покупки.
- [Логи](../troubleshooting/logs.md) помогают проверить webhook и создание платежных ссылок.

## Webhook URL провайдеров

Все платежные webhook URL строятся от `WEBHOOK_BASE_URL` - публичного HTTPS-адреса backend/webhook-домена. Это должен быть домен, который проксируется на backend-сервер вебхуков (`backend:8080`), а не `SUBSCRIPTION_MINI_APP_URL` frontend/Mini App. Если `WEBHOOK_BASE_URL=https://bot.example.com`, то полный адрес получается как `https://bot.example.com` + путь из таблицы.

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
| Telegram Stars | Отдельный платежный webhook не нужен | Stars-события приходят через webhook Telegram-бота: `WEBHOOK_BASE_URL` + `/tg/webhook`. |

После настройки сделайте тестовый платеж и проверьте, что в логах `backend` видно входящий `POST` на нужный путь. Если провайдер сообщает, что адрес недоступен, сначала проверьте DNS/HTTPS и reverse proxy для `WEBHOOK_BASE_URL`, затем убедитесь, что путь начинается ровно с `/webhook/...` без `/api`, `/auth` и frontend-домена.

## YooKassa

YooKassa используется для рублевых оплат и может участвовать в сценариях автопродления period-подписок.

Что настроить:

- включение провайдера: `YOOKASSA_ENABLED`;
- идентификаторы и секреты магазина;
- URL вебхука: `WEBHOOK_BASE_URL` + `/webhook/yookassa`;
- отображение кнопки оплаты и порядок платежных методов.

Справочник переменных: [YooKassa](../configuration/env-vars.md#yookassa).

## FreeKassa

FreeKassa подключается как отдельный платежный метод и обрабатывает входящие webhook-события через `backend`.

Что настроить:

- включение провайдера: `FREEKASSA_ENABLED`;
- ID магазина, API/secret-ключи и настройки подписи;
- список доверенных IP, если используется;
- публичный URL вебхука: `WEBHOOK_BASE_URL` + `/webhook/freekassa`.

Справочник переменных: [FreeKassa](../configuration/env-vars.md#freekassa).

## Platega

Platega подключается как отдельный платежный провайдер, но внутри Minishop может дать несколько кнопок: основную устаревшую кнопку, СБП/карту и крипто-кнопку. Общие параметры мерчанта задаются один раз, а ID методов оплаты и подписи кнопок настраиваются отдельно.

Что включить:

- `PLATEGA_ENABLED` - общий флаг провайдера;
- `PLATEGA_SBP_ENABLED` - отдельная кнопка СБП/карта;
- `PLATEGA_CRYPTO_ENABLED` - отдельная crypto-кнопка Platega;
- `PLATEGA_PAYMENT_METHOD` - устаревший/резервный ID метода оплаты для старых callback-запросов и старых установок.

Что настроить:

1. Укажите `PLATEGA_BASE_URL`, `PLATEGA_MERCHANT_ID` и `PLATEGA_SECRET`.
2. Заполните `PLATEGA_SBP_METHOD` и/или `PLATEGA_CRYPTO_METHOD`, если используете отдельные кнопки.
3. Проверьте `PLATEGA_RETURN_URL` и `PLATEGA_FAILED_URL`.
4. Укажите URL вебхука: `WEBHOOK_BASE_URL` + `/webhook/platega`.
5. Настройте тексты и иконки кнопок через `PAYMENT_PLATEGA_SBP_*` и `PAYMENT_PLATEGA_CRYPTO_*`.
6. Добавьте нужные методы в `PAYMENT_METHODS_ORDER`.

Справочник переменных: [Platega](../configuration/env-vars.md#platega).

## SeverPay

SeverPay подключается как отдельный платежный метод с собственным MID, token и сроком жизни платежной ссылки.

Что настроить:

1. Включите `SEVERPAY_ENABLED`.
2. Укажите `SEVERPAY_BASE_URL`.
3. Заполните `SEVERPAY_MID` и `SEVERPAY_TOKEN`.
4. Настройте `SEVERPAY_RETURN_URL`.
5. Укажите URL вебхука: `WEBHOOK_BASE_URL` + `/webhook/severpay`.
6. При необходимости задайте `SEVERPAY_LIFETIME_MINUTES`.
7. Добавьте `severpay` в `PAYMENT_METHODS_ORDER`.

Справочник переменных: [SeverPay](../configuration/env-vars.md#severpay).

## Wata

Wata подключается как отдельный провайдер с bearer token, платежными ссылками и опциональной проверкой подписи webhook.

Что настроить:

1. Включите `WATA_ENABLED`.
2. Укажите `WATA_BASE_URL` и `WATA_API_TOKEN`.
3. Проверьте `WATA_RETURN_URL` и `WATA_FAILED_URL`.
4. Настройте `WATA_LINK_TTL_MINUTES`: минимум 15 минут, максимум 43200.
5. Укажите URL вебхука: `WEBHOOK_BASE_URL` + `/webhook/wata`.
6. Если включаете проверку подписи, задайте `WATA_WEBHOOK_VERIFY_SIGNATURE` и при необходимости `WATA_PUBLIC_KEY`.
7. Для дополнительной защиты заполните `WATA_TRUSTED_IPS`.
8. Добавьте `wata` в `PAYMENT_METHODS_ORDER`.

Справочник переменных: [Wata](../configuration/env-vars.md#wata).

## CryptoPay

CryptoPay используется для криптовалютных платежей через отдельный токен и сеть Crypto Bot API.

Что настроить:

1. Включите `CRYPTOPAY_ENABLED`.
2. Укажите `CRYPTOPAY_TOKEN`.
3. Выберите `CRYPTOPAY_NETWORK`: `mainnet` или `testnet`.
4. Задайте `CRYPTOPAY_CURRENCY_TYPE`: `fiat` или `crypto`.
5. Проверьте `CRYPTOPAY_ASSET`, например `RUB`, `USDT` или `BTC`.
6. Укажите URL вебхука: `WEBHOOK_BASE_URL` + `/webhook/cryptopay`.
7. Добавьте `cryptopay` в `PAYMENT_METHODS_ORDER`.

Для тестов используйте соответствующую сеть: testnet-токен не должен попадать в mainnet-настройки. Если сумма или asset выглядят неверно, проверьте сочетание `CRYPTOPAY_CURRENCY_TYPE` и `CRYPTOPAY_ASSET`.

Справочник переменных: [CryptoPay](../configuration/env-vars.md#cryptopay).

## Heleket

Heleket используется для крипто-инвойсов с отдельными merchant ID, ключом платежного API, валютой инвойса и настройками проверки webhook.

Что настроить:

1. Включите `HELEKET_ENABLED`.
2. Укажите `HELEKET_BASE_URL`, `HELEKET_MERCHANT_ID` и `HELEKET_API_KEY`.
3. Настройте `HELEKET_CURRENCY`.
4. При необходимости задайте `HELEKET_TO_CURRENCY` и `HELEKET_NETWORK`.
5. Проверьте `HELEKET_RETURN_URL` и `HELEKET_SUCCESS_URL`.
6. Настройте `HELEKET_LIFETIME_SECONDS`: допустимый диапазон 300..43200.
7. Укажите URL вебхука: `WEBHOOK_BASE_URL` + `/webhook/heleket`.
8. Если включаете проверку webhook, задайте `HELEKET_VERIFY_WEBHOOK_SIGNATURE`.
9. Для IP-фильтрации заполните `HELEKET_TRUSTED_IPS`.
10. Добавьте `heleket` в `PAYMENT_METHODS_ORDER`.

Справочник переменных: [Heleket](../configuration/env-vars.md#heleket).

## PayKilla

PayKilla используется для крипто-инвойсов V2 через hosted checkout `https://gopay.paykilla.com/{invoice_id}`. API-запросы подписываются HMAC-SHA256, webhook проверяется по заголовку `X-API-SIGN` и raw body.

PayKilla строго валидирует текстовые поля invoice. Поэтому Minishop отправляет в `purpose` и `description` простой английский текст `<WEBAPP_TITLE> payment <id>`, а локализованное описание платежа оставляет только внутри Minishop. Дополнительно эти поля проходят ASCII-safe sanitizer: допускаются ASCII-буквы, цифры, пробелы, `_`, `.`, `,`.

Minishop создает invoice в валюте, которую PayKilla принимает в поле `currency`. Если валюта тарифа входит в `PAYKILLA_INVOICE_CURRENCIES`, сумма отправляется как есть. Если валюта тарифа не входит в этот список, сумма конвертируется в `PAYKILLA_CURRENCY`; по умолчанию рублевые тарифы конвертируются в `USD` через no-key endpoint ExchangeRate-API `https://open.er-api.com/v6/latest/{source}` с кэшем `PAYKILLA_EXCHANGE_RATE_CACHE_SECONDS`. Перед созданием invoice Minishop читает `GET /api/v2/currency` и проверяет `invoiceMin`/`invoiceMax` для валюты инвойса.

Payload создания invoice содержит обязательные поля `type`, `purpose`, `currency`, `totalPrice`, `paymentCurrencies`, служебный `clientOrderId`, а также полезные optional поля `description`, `expiredAt`, `userPaysServiceFee`, `userPaysNetworkFee`. Redirect URLs в PayKilla не отправляются; завершение платежа обрабатывается через webhook.

Какие полномочия нужны API key:

1. В PayKilla Dashboard откройте **Settings -> API keys**.
2. Создайте ключ типа **HMAC**.
3. Для приема оплат включите permission **INVOICE**.
4. Permission **WITHDRAWAL** не нужен для Minishop-платежей; не включайте его без отдельной необходимости выплат.
5. Сохраните `publicKey` в `PAYKILLA_API_KEY`, а `secretKey` в `PAYKILLA_SECRET_KEY`.

Как настроить webhook в PayKilla:

1. Откройте **Settings -> Webhooks**.
2. В URL укажите `WEBHOOK_BASE_URL` + `/webhook/paykilla`, например `https://bot.example.com/webhook/paykilla`.
3. Минимальные галочки: `INVOICE_PAID`, `INVOICE_EXPIRED`.
4. Рекомендуемые галочки для production: `INVOICE_PAID`, `PAYMENT_COMPLETED`, `PAYMENT_FAILED`, `PAYMENT_OVERPAID`, `PAYMENT_UNDERPAID`, `PAYMENT_PARTIAL`, `INVOICE_EXPIRED`, `COMPLIANCE_FAILED`.
5. Опционально включите `INVOICE_CREATED`, `PAYMENT_PENDING`, `TRANSACTION_CONFIRMED` и `TRANSACTION_FINAL`, если нужны промежуточные события в логах.
6. Оставьте `PAYKILLA_VERIFY_WEBHOOK_SIGNATURE=True`. Если публичный URL у PayKilla отличается от `WEBHOOK_BASE_URL` + `/webhook/paykilla`, задайте точное значение в `PAYKILLA_WEBHOOK_URL`.

Что настроить в Minishop:

1. Включите `PAYKILLA_ENABLED`.
2. Укажите `PAYKILLA_API_KEY` и `PAYKILLA_SECRET_KEY`.
3. Оставьте `PAYKILLA_CURRENCY=USD`, если PayKilla не принимает валюту тарифов как invoice currency. В `PAYKILLA_INVOICE_CURRENCIES` укажите валюты, доступные в PayKilla для поля `currency`, например `USD,EUR`.
4. В `PAYKILLA_PAYMENT_CURRENCIES` начните с `USDTTRC`, а `BTC`, `ETH` и другие тикеры добавляйте только если они доступны в PayKilla Dashboard.
5. Убедитесь, что webhook `/webhook/paykilla` настроен в PayKilla: Minishop не отправляет redirect URLs в PayKilla и полагается на webhook для активации платежа.
6. Добавьте `paykilla` в `PAYMENT_METHODS_ORDER`, если хотите задать явный порядок кнопок.

Справочник переменных: [PayKilla](../configuration/env-vars.md#paykilla).

## Telegram Stars

Telegram Stars используются напрямую и поддерживаются в legacy-ценах и JSON-каталоге тарифов.

Где применяются Stars:

- цены периодов подписки;
- пакеты трафика;
- premium-докупки;
- HWID-докупки, если они включены в каталоге тарифов.

Что проверить:

- `STARS_ENABLED`;
- отдельный платежный webhook не настраивается: Telegram Stars приходят через webhook Telegram-бота `WEBHOOK_BASE_URL` + `/tg/webhook`;
- Stars-цены в legacy-настройках или JSON-каталоге;
- корректное округление цены до целого количества Stars;
- сценарии смены тарифа: XTR/Stars-докупки не конвертируются без явного курса.

См. также [переменные платежей](../configuration/env-vars.md#платежи) и [тарифы](tariffs.md).
