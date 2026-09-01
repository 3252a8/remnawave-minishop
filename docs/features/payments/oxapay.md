# OxaPay
OxaPay подключён через актуальный Merchant API v1 и создаёт hosted-ссылку методом
`Generate Invoice`. Сумма и валюта берутся из локального заказа, `order_id` содержит ID
платежа Minishop, а `callback_url` собирается из `WEBHOOK_BASE_URL`.

## Настройка

1. Создайте Merchant API key в кабинете OxaPay.
2. Включите `OXAPAY_ENABLED` и сохраните ключ в `OXAPAY_MERCHANT_API_KEY`.
3. Проверьте публичный `WEBHOOK_BASE_URL`; готовый адрес должен оканчиваться на
   `/webhook/oxapay`.
4. При необходимости настройте `OXAPAY_RETURN_URL` и срок счёта
   `OXAPAY_LIFETIME_MINUTES` от `15` до `2880` минут.
5. Для тестового платежа временно включите `OXAPAY_SANDBOX`.

## Комиссия, недоплата и расчёты

- Пустые `OXAPAY_FEE_PAID_BY_PAYER`, `OXAPAY_UNDER_PAID_COVERAGE`,
  `OXAPAY_AUTO_WITHDRAWAL` и `OXAPAY_MIXED_PAYMENT` оставляют соответствующее решение
  настройкам Merchant Service в OxaPay.
- `OXAPAY_TO_CURRENCY=USDT` включает поддерживаемую OxaPay автоматическую конвертацию;
  другие target currencies API не принимает.
- OxaPay может выставлять invoice как в fiat, так и в crypto currency. Локальный список
  намеренно не зафиксирован: окончательную доступность валюты проверяет API для конкретного
  merchant account.

## Webhook и восстановление

- OxaPay подписывает точные сырые байты JSON заголовком `HMAC`, используя Merchant API key
  как секрет HMAC-SHA512. Проверку нельзя отключить.
- Первый callback со статусом `Paying` означает только отправку транзакции. Доступ выдаётся
  после `Paid`; `manual_accept` также считается завершённым статусом Merchant Service.
- Перед активацией Minishop сверяет `type=invoice`, `track_id`, `order_id`, сумму и валюту.
  Повторный callback идемпотентен и получает обязательный для OxaPay ответ `200 ok`.
- Если callback потерян, общий reconciliation worker читает
  `GET /v1/payment/{track_id}` и безопасно завершает `paid` invoice либо закрывает `expired`.
- `OXAPAY_TRUSTED_IPS` — дополнительная необязательная защита. Актуальный список IP OxaPay
  выдаёт через поддержку; без списка обязательная HMAC-проверка продолжает работать.

## Справочник

- [Generate Invoice](https://docs.oxapay.com/api-reference/payment/generate-invoice)
- [Payment Information](https://docs.oxapay.com/api-reference/payment/payment-information)
- [Webhook](https://docs.oxapay.com/webhook)
- [Payment status table](https://docs.oxapay.com/api-reference/payment/payment-status-table)
- [Переменные OxaPay](../../configuration/env-vars.md#oxapay)
