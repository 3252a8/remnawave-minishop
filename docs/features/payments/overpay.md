# Overpay
Overpay построен на платформе BeGateway: платёж создаётся как hosted-checkout через `POST https://checkout.overpay.io/ctp/api/checkouts`, пользователь перенаправляется на `redirect_url`, а завершение обрабатывается через notification URL `/webhook/overpay`.

Исходящие запросы авторизуются HTTP Basic auth: логин — `OVERPAY_SHOP_ID`, пароль — `OVERPAY_SECRET_KEY`. Суммы передаются в минимальных единицах валюты (копейки/центы). Уведомления приходят JSON POST'ом и авторизуются теми же HTTP Basic-кредами; `tracking_id` — это внутренний ID платежа.

## Особенности

- Checkout создаётся с `transaction_type=payment`; в ответе сохраняется `token`, а ссылка `redirect_url` показывается пользователю.
- Поддерживаемые валюты: `USD`, `EUR`, `RUB`, `GBP` и другие в зависимости от контракта магазина.
- При успешной оплате сумма из webhook (в минимальных единицах) должна покрывать сумму платежа; недоплата отклоняется кодом `400`, а переплата активирует исходный фиксированный заказ.
- При `OVERPAY_RECURRING_ENABLED=true` checkout создаётся с `additional_data.contract=["recurring"]`; успешный webhook сохраняет `credit_card.token` как способ оплаты пользователя, а автопродление выполняет списание `POST https://gateway.overpay.io/transactions/payments` по сохранённому токену.
- Встроенные Overpay subscriptions не используются: срок подписки, HWID-продления, отмена автопродления и повторная активация остаются в общей логике бота.

## Настройка

1. Включите `OVERPAY_ENABLED`.
2. Укажите `OVERPAY_SHOP_ID` и `OVERPAY_SECRET_KEY` из кабинета Overpay.
3. При необходимости задайте `OVERPAY_RETURN_URL`, `OVERPAY_SUCCESS_URL`, `OVERPAY_DECLINE_URL`, `OVERPAY_FAIL_URL`.
4. Скопируйте URL вебхука (`WEBHOOK_BASE_URL` + `/webhook/overpay`) и укажите его в кабинете Overpay как notification URL.
5. Для автопродления задайте `OVERPAY_RECURRING_ENABLED=true`.
6. Для IP-фильтрации при необходимости заполните `OVERPAY_TRUSTED_IPS`.

## Справочник

- [Overpay](../../configuration/env-vars.md#overpay)
