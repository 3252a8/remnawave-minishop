# SeverPay
SeverPay подключается как отдельный платежный метод с собственным MID, token и сроком жизни платежной ссылки.

## Настройка

1. Включите `SEVERPAY_ENABLED`.
2. Укажите `SEVERPAY_BASE_URL`.
3. Заполните `SEVERPAY_MID` и `SEVERPAY_TOKEN`.
4. Скопируйте URL вебхука из админ-панели и укажите его в кабинете SeverPay.
5. При необходимости задайте `SEVERPAY_LIFETIME_MINUTES`.

## Справочник

- [SeverPay](../../configuration/env-vars.md#severpay)
