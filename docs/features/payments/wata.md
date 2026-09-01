# Wata
Wata подключается как отдельный провайдер с bearer token, платежными ссылками и опциональной проверкой подписи webhook.

## Настройка

1. Включите `WATA_ENABLED`.
2. Укажите `WATA_BASE_URL` и `WATA_API_TOKEN`.
3. Настройте `WATA_LINK_TTL_MINUTES`.
4. Скопируйте URL вебхука из админ-панели и укажите его в кабинете Wata.
5. При необходимости включите `WATA_WEBHOOK_VERIFY_SIGNATURE`.
6. Если используется проверка подписи, задайте `WATA_PUBLIC_KEY`.
7. Для IP-фильтрации заполните `WATA_TRUSTED_IPS`.

## Ограничения

- `WATA_LINK_TTL_MINUTES` должен быть от `15` до `43200`.

## Справочник

- [Wata](../../configuration/env-vars.md#wata)
