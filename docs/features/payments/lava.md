# LAVA
LAVA Business используется для рублевых оплат картами и СБП через счета `https://api.lava.ru`.

Исходящие API-запросы подписываются HMAC-SHA256 от raw body, подпись передается в заголовке `Signature`. Webhook проверяется по заголовку `Authorization`: принимается подпись raw body или sorted-keys JSON (legacy PHP SDK).

## Особенности

- Счета выставляются только в рублях (`RUB`).
- `hookUrl` передается автоматически при создании счета, если задан `WEBHOOK_BASE_URL`.
- `LAVA_INCLUDE_SERVICES` ограничивает способы оплаты на странице счета, например `card,sbp`.
- При успешной оплате сумма из webhook сверяется с суммой платежа; расхождение отклоняется.

## Настройка

1. Включите `LAVA_ENABLED`.
2. Укажите `LAVA_SHOP_ID` и `LAVA_SECRET_KEY` из кабинета LAVA Business.
3. Если магазин использует отдельный дополнительный ключ для вебхуков, задайте `LAVA_WEBHOOK_SECRET`; пустое значение означает использование `LAVA_SECRET_KEY`.
4. При необходимости задайте `LAVA_LIFETIME_MINUTES` (1..7200) и `LAVA_RETURN_URL`.
5. Скопируйте URL вебхука из админ-панели и при необходимости укажите его в кабинете LAVA.

## Справочник

- [LAVA](../../configuration/env-vars.md#lava)
