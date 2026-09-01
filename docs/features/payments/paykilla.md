# PayKilla
PayKilla используется для крипто-инвойсов V2 через hosted checkout `https://gopay.paykilla.com/{invoice_id}`.

API-запросы подписываются HMAC-SHA256. Webhook проверяется по заголовку `X-API-SIGN` и raw body.

## Особенности

- PayKilla строго валидирует текстовые поля invoice.
- В `purpose` и `description` Minishop отправляет простой английский текст `<WEBAPP_TITLE> payment <id>`.
- Локализованное описание платежа остается только внутри Minishop.
- ASCII-safe sanitizer допускает ASCII-буквы, цифры, пробелы, `_`, `.`, `,`.
- Минимальная сумма платежа задается настройками `PAYKILLA_MIN_PAYMENT_AMOUNT` и `PAYKILLA_MIN_PAYMENT_CURRENCY`; по умолчанию это `10 USD`.
- Если выбранный тариф/пакет ниже этого порога после конвертации, Telegram bot не показывает кнопку PayKilla, WebApp показывает метод неактивным, а API создания платежа возвращает ошибку `payment_amount_below_minimum`.

## Валюта invoice

Minishop создает invoice в валюте, которую PayKilla принимает в поле `currency`.

Для fiat-invoice сумма округляется до двух знаков; для криптоактивов сохраняется точная
десятичная величина. При успешном webhook Minishop сверяет сумму и валюту с
аутентифицированным invoice PayKilla до активации заказа.

Если валюта тарифа входит в `PAYKILLA_INVOICE_CURRENCIES`, сумма отправляется как есть.

Если валюта тарифа не входит в список, сумма конвертируется в `PAYKILLA_CURRENCY`. По умолчанию рублевые тарифы конвертируются в `USD` через ExchangeRate-API с кэшем `PAYKILLA_EXCHANGE_RATE_CACHE_SECONDS`.

Перед созданием invoice Minishop читает `GET /api/v2/currency` и проверяет `invoiceMin`/`invoiceMax` для валюты инвойса. Этот endpoint также показывает актуальные currency/payment-method ограничения конкретного merchant account.

## Payload invoice

Payload создания invoice содержит обязательные поля `type`, `purpose`, `currency`, `totalPrice` и `paymentCurrencies`.

Дополнительно отправляются `clientOrderId`, `description`, `expiredAt`, `userPaysServiceFee` и `userPaysNetworkFee`.

Redirect URLs в PayKilla не отправляются. Завершение платежа обрабатывается через webhook.

## API key

1. В PayKilla Dashboard откройте **Settings -> API keys**.
2. Создайте ключ типа **HMAC**.
3. Для приема оплат включите permission **INVOICE**.
4. Permission **WITHDRAWAL** не нужен для Minishop-платежей.
5. Сохраните `publicKey` в `PAYKILLA_API_KEY`.
6. Сохраните `secretKey` в `PAYKILLA_SECRET_KEY`.

## Webhook

1. В PayKilla Dashboard откройте **Settings -> Webhooks**.
2. Скопируйте URL вебхука из админ-панели и укажите его в PayKilla.
3. Включите минимальные события: `INVOICE_PAID`, `INVOICE_EXPIRED`.
4. Для production также включите `PAYMENT_COMPLETED`, `PAYMENT_FAILED`, `PAYMENT_OVERPAID`, `PAYMENT_UNDERPAID`, `PAYMENT_PARTIAL`, `COMPLIANCE_FAILED`.
5. Если нужны промежуточные статусы в логах, дополнительно включите `INVOICE_CREATED`, `PAYMENT_PENDING`, `TRANSACTION_CONFIRMED` и `TRANSACTION_FINAL`.
6. Оставьте `PAYKILLA_VERIFY_WEBHOOK_SIGNATURE=True`.

## Настройка

1. Включите `PAYKILLA_ENABLED`.
2. Укажите `PAYKILLA_API_KEY` и `PAYKILLA_SECRET_KEY`.
3. Оставьте `PAYKILLA_CURRENCY=USD`, если PayKilla не принимает валюту тарифов как invoice currency. В `PAYKILLA_INVOICE_CURRENCIES` укажите валюты, доступные в PayKilla для поля `currency`, например `USD,EUR`.
4. В `PAYKILLA_PAYMENT_CURRENCIES` оставьте `USDTTRC,BTC,ETH,USDTBSC,USDTTON` или укажите другой список тикеров, доступных в PayKilla Dashboard; `USDTTRC` должен идти первым.
5. Оставьте `PAYKILLA_MIN_PAYMENT_AMOUNT=10` и `PAYKILLA_MIN_PAYMENT_CURRENCY=USD`, если минимальный invoice PayKilla равен `10 USD`.
6. Убедитесь, что webhook `/webhook/paykilla` настроен в PayKilla: Minishop не отправляет redirect URLs в PayKilla и полагается на webhook для активации платежа.
7. Добавьте `paykilla` в `PAYMENT_METHODS_ORDER`, если хотите задать явный порядок кнопок.

## Справочник

- [PayKilla](../../configuration/env-vars.md#paykilla)
