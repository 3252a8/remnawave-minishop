# CloudPayments
CloudPayments используется для оплат картами через Orders API `https://api.cloudpayments.ru/orders/create`.

Исходящие запросы авторизуются HTTP Basic auth: логин — `CLOUDPAYMENTS_PUBLIC_ID`, пароль — `CLOUDPAYMENTS_API_SECRET`. Уведомления Pay/Fail приходят как `application/x-www-form-urlencoded` и подписываются HMAC-SHA256 (base64) от raw body на `CLOUDPAYMENTS_API_SECRET` в заголовке `Content-HMAC` (старые интеграции — `X-Content-HMAC`).

## Особенности

- Платёж создаётся как заказ (order) со ссылкой `https://orders.cloudpayments.ru/...`; `InvoiceId` — это внутренний ID платежа.
- Поддерживаемые валюты: `RUB`, `USD`, `EUR`, `GBP`, `KZT`, `UAH`, `BYN`, `AZN`, `AMD`, `KGS`.
- При успешной оплате сумма из webhook сверяется с суммой платежа; расхождение отклоняется кодом `12`.
- При `CLOUDPAYMENTS_RECURRING_ENABLED=true` Pay webhook сохраняет CloudPayments `Token` как способ оплаты пользователя, а автопродление выполняет merchant-initiated запрос `/payments/tokens/charge` с `TrInitiatorCode=0` и `PaymentScheduled=1`.
- Встроенные CloudPayments subscriptions не используются: срок подписки, HWID-продления, отмена автопродления и повторная активация остаются в общей логике бота.
- Backend отвечает CloudPayments телом `{"code": 0}` при успешной обработке.

## Настройка

1. Включите `CLOUDPAYMENTS_ENABLED`.
2. Укажите `CLOUDPAYMENTS_PUBLIC_ID` и `CLOUDPAYMENTS_API_SECRET` из кабинета CloudPayments.
3. При необходимости задайте `CLOUDPAYMENTS_RETURN_URL` и `CLOUDPAYMENTS_FAILED_URL`.
4. Скопируйте URL вебхука из админ-панели и укажите его в CloudPayments как адрес уведомлений Pay и Fail.
5. Для автопродления включите получение `Token` в уведомлении Pay на стороне CloudPayments и задайте `CLOUDPAYMENTS_RECURRING_ENABLED=true`.
6. Для IP-фильтрации при необходимости заполните `CLOUDPAYMENTS_TRUSTED_IPS`.

## Справочник

- [CloudPayments](../../configuration/env-vars.md#cloudpayments)
