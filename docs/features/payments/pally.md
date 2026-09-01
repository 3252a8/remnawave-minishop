# Pally
Pally / PayPalych используется для оплат через hosted-страницу счета `https://pally.info`. Minishop создает счет через `POST /api/v1/bill/create`, сохраняет `bill_id`, а завершение платежа обрабатывает через Result URL `/webhook/pally`.

## Особенности

- Поддерживаемые валюты счета: `RUB`, `USD`, `EUR`.
- API-запросы отправляются как form-urlencoded поля с `Authorization: Bearer <PALLY_API_TOKEN>`.
- Подпись postback проверяется по формуле `strtoupper(md5(OutSum:InvId:token))`; `token` берется из `PALLY_SIGNATURE_TOKEN`, а если он пустой - из `PALLY_API_TOKEN`.
- `OutSum` входит в подпись postback и строго сверяется с локальным счетом. При `PALLY_PAYER_PAYS_COMMISSION=1` допускается только подписанный `OutSum` больше суммы счета (комиссия сверху); начисление всегда берется из локального заказа.
- Статусы `SUCCESS` и `OVERPAID` активируют покупку, `FAIL` помечает платеж неуспешным, `NEW`, `PROCESS` и `UNDERPAID` остаются pending.

## Настройка

1. Включите `PALLY_ENABLED`.
2. Укажите `PALLY_API_TOKEN`, `PALLY_SHOP_ID` и при необходимости отдельный `PALLY_SIGNATURE_TOKEN`.
3. В кабинете Pally укажите Result URL: `WEBHOOK_BASE_URL` + `/webhook/pally`.
4. При необходимости задайте `PALLY_RETURN_URL`, `PALLY_SUCCESS_URL`, `PALLY_FAIL_URL`, `PALLY_TTL_SECONDS` и `PALLY_PAYER_PAYS_COMMISSION`.
   Для рублевых счетов действует минимальная внешняя сумма `PALLY_MIN_PAYMENT_AMOUNT_RUB=30`:
   смешанная оплата партнерским балансом оставляет Pally не меньше этого значения. Отдельные
   лимиты для USD и EUR задаются через `PALLY_MIN_PAYMENT_AMOUNT_USD` и
   `PALLY_MIN_PAYMENT_AMOUNT_EUR`.
5. Если нужна жесткая кнопка конкретного метода на стороне Pally, задайте `PALLY_PAYMENT_METHOD=BANK_CARD` или `PALLY_PAYMENT_METHOD=SBP`.

## Справочник

- [Pally](../../configuration/env-vars.md#pally)
