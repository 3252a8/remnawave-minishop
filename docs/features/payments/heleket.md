# Heleket
Heleket используется для крипто-инвойсов с merchant ID, ключом платежного API, валютой инвойса и настройками проверки webhook.

## Настройка

1. Включите `HELEKET_ENABLED`.
2. Укажите `HELEKET_BASE_URL`, `HELEKET_MERCHANT_ID` и `HELEKET_API_KEY`.
3. Настройте `HELEKET_CURRENCY`.
4. При необходимости задайте `HELEKET_TO_CURRENCY` и `HELEKET_NETWORK`.
5. Проверьте `HELEKET_RETURN_URL` и `HELEKET_SUCCESS_URL`.
6. Настройте `HELEKET_LIFETIME_SECONDS`.
7. Скопируйте URL вебхука из админ-панели и укажите его в кабинете Heleket.
8. При необходимости включите `HELEKET_VERIFY_WEBHOOK_SIGNATURE`.
9. Для IP-фильтрации заполните `HELEKET_TRUSTED_IPS`.

## Ограничения

- `HELEKET_LIFETIME_SECONDS` должен быть от `300` до `43200`.
- Заказы со статусами `paid` и `paid_over` активируются только при `is_final=true`.
  Для `paid_over` начисляется исходный фиксированный объём заказа, без доплаты за переплату.

## Справочник

- [Heleket](../../configuration/env-vars.md#heleket)
