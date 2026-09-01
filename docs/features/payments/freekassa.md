# FreeKassa
FreeKassa подключается как отдельный платежный метод. Входящие webhook-события обрабатываются через `backend`.

## Настройка

1. Включите `FREEKASSA_ENABLED`.
2. Заполните `FREEKASSA_MERCHANT_ID`, `FREEKASSA_FIRST_SECRET`, `FREEKASSA_SECOND_SECRET` и `FREEKASSA_API_KEY`.
3. В `FREEKASSA_PAYMENT_METHOD_ID` укажите ID подключённого способа оплаты из кабинета FreeKassa.
4. Определите публичный исходящий IPv4 контейнера `backend`:

   ```bash
   docker compose exec backend sh -lc 'curl -4fsS https://api.ipify.org; echo'
   ```

5. Запишите полученный адрес в `FREEKASSA_PAYMENT_IP`. Если меняете `.env`, пересоздайте `backend`; сохранённый через админ-панель override применяется штатным механизмом настроек.
6. Проверьте настройки подписи.
7. Скопируйте URL вебхука из админ-панели и укажите его в кабинете FreeKassa.
8. При необходимости заполните `FREEKASSA_TRUSTED_IPS`.

## Зачем нужен `FREEKASSA_PAYMENT_IP`

Метод FreeKassa `POST /v1/orders/create` требует поле `ip` и описывает его как IP покупателя. Telegram Bot API не передаёт боту IP пользователя, поэтому Minishop использует стабильный публичный исходящий IP `backend` как резервное значение. Это не IP из `FREEKASSA_TRUSTED_IPS` и не обязательно адрес домена или reverse proxy.

Определяйте адрес именно из контейнера `backend`: при Docker NAT, VPN, отдельном шлюзе или Kubernetes egress внешний адрес хоста и контейнера может различаться. Не используйте внутренние адреса `10.x.x.x`, `172.16-31.x.x` или `192.168.x.x`. При динамическом адресе обновите настройку после его смены. Для подтверждения допустимости одного серверного IP для всех Telegram-платежей обратитесь в поддержку FreeKassa.

Требование поля `ip` зафиксировано в [официальной документации FreeKassa](https://docs.freekassa.net/). Без `FREEKASSA_PAYMENT_IP` или `FREEKASSA_PAYMENT_METHOD_ID` провайдер считается не готовым к созданию платежей; при этом webhook и сверка ранее созданных заказов продолжают работать.

## Справочник

- [FreeKassa](../../configuration/env-vars.md#freekassa)
