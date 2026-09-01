# Stripe
Stripe использует Checkout Sessions для hosted-ссылок оплаты и PaymentIntents для автопродления, управляемого приложением.

## Особенности

- Платёж создаётся как hosted Checkout Session; внутренний ID платежа передаётся в `client_reference_id` и metadata (`payment_db_id`).
- При `STRIPE_RECURRING_ENABLED=true` Checkout создаётся с `payment_intent_data[setup_future_usage]=off_session`; успешные webhook сохраняют `customer` и `payment_method`, а автопродление создаёт off-session PaymentIntent.
- Встроенные Stripe Billing Subscriptions не используются: срок подписки, HWID-продления, отмена автопродления и повторные попытки остаются в общей логике бота.
- `STRIPE_SUPPORTED_CURRENCIES` ограничивает кнопки оплаты валютами, которые поддерживаются вашим аккаунтом Stripe и включёнными способами оплаты.

## Настройка

1. Включите `STRIPE_ENABLED`.
2. Укажите `STRIPE_SECRET_KEY` из Stripe Dashboard.
3. Скопируйте URL вебхука из админ-панели и укажите его в Stripe Dashboard.
4. Включите события `checkout.session.completed`, `checkout.session.expired`, `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.canceled`.
5. Задайте `STRIPE_WEBHOOK_SECRET` из signing secret эндпоинта (`whsec_...`).
6. При необходимости задайте `STRIPE_RETURN_URL` и `STRIPE_CANCEL_URL`.
7. Для автопродления включите `STRIPE_RECURRING_ENABLED=true`.

## Справочник

- [Stripe](../../configuration/env-vars.md#stripe)
