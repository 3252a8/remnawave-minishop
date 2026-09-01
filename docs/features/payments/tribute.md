# Tribute
Интеграция работает в двух режимах. Если включены `TRIBUTE_ENABLED` и
`TRIBUTE_SHOP_ENABLED` **и указан `TRIBUTE_SHOP_ID`**, Minishop в первую очередь создаёт
динамический заказ через
[Tribute Shop API](https://wiki.tribute.tg/for-shops/api/methods): сумма и валюта заказа
точно соответствуют локальному расчёту Minishop. Заранее опубликованные подписки и
Digital Products из Creator API остаются резервным вариантом для неподдерживаемого
Shop-сценария или полностью заменяют Shop API, когда `TRIBUTE_SHOP_ENABLED=false`.

## Настройка

1. В кабинете Tribute создайте Shop, разрешите recurrent payments, получите API key и
   скопируйте числовой ID этого Shop.
2. В **Система -> Настройки -> Платежи** включите `TRIBUTE_ENABLED`, сохраните
   `TRIBUTE_API_KEY`, укажите `TRIBUTE_SHOP_ID` и включите `TRIBUTE_SHOP_ENABLED`.
3. Добавьте в Tribute webhook `WEBHOOK_BASE_URL` + `/webhook/tribute`. Один URL принимает
   [Shop-события](https://wiki.tribute.tg/for-shops/api/webhooks) и
   [Creator-события](https://wiki.tribute.tg/for-content-creators/api-documentation/webhooks);
   заголовок `trbt-signature` проверяется HMAC-SHA256 по исходному body с API key.
4. Если нужен Creator fallback, заранее создайте подписки и Digital Products и заполните
   их ссылки и ID в редакторе тарифа.
5. Проверьте тестовый `shop_order`, рекуррентный `shop_order_charge_success` и отмену
   `shop_order_cancelled`. Для fallback отдельно проверьте `new_subscription`,
   `renewed_subscription`, `cancelled_subscription` и `new_digital_product`.

## Основной режим: Shop API

- Для обычной period-подписки Minishop создаёт рекуррентный Shop Order только на локальные
  сроки 1, 3, 6 или 12 месяцев (`monthly`, `quarterly`, `halfyearly`, `yearly`).
  Другие сроки, включая поддерживаемый самим Tribute `weekly`, через Shop-интеграцию
  Minishop не создаются.
- Одноразовый Shop Order поддерживает обычный и premium-трафик, докупку трафика,
  отдельную покупку HWID-устройств и рассчитанную Minishop доплату за смену тарифа.
  В заказ передаётся точная локальная сумма в `RUB`, `EUR` или `USD`; несовпадение суммы,
  валюты или пользователя в webhook помещает событие в quarantine без выдачи доступа.
- Каждый заказ создаётся строго для настроенного `TRIBUTE_SHOP_ID`; Shop webhook с другим
  ID или без него отклоняется. Допустимая сумма заказа — от `100` до `300000` копеек/центов.
- Shop API считается настроенным только вместе с `TRIBUTE_SHOP_ID`. Пока ID не указан,
  включённый флаг ничего не меняет: провайдер продаёт только настроенные Creator-подписки и
  Digital Products, а покупка устройств и доплата за смену тарифа через Tribute недоступны —
  их сумму способен передать только Shop Order.
- Для этих сценариев поля `tribute` у тарифа не нужны. Они используются только при
  переходе на Creator fallback.
- Для рекуррентной подписки с ценовой скидкой Minishop передаёт полную цену следующих
  циклов в `amount`, а скидочную цену первого списания — в `firstPeriodAmount`.
  Webhook первого платежа обязан подтвердить обе суммы; все продления учитываются уже
  по полной цене. Для рекуррентного Shop Order разрешён только промокод со скидкой цены:
  бонусные дни, множитель срока или трафика отклоняются, поскольку расписанием списаний
  и авторитетной датой окончания управляет Tribute. Для одноразовых Shop Order это
  ограничение не применяется.
  Комбинированный checkout «продление подписки + HWID-устройства» (`hwid_renewal`)
  по-прежнему не поддерживается; устройства можно купить отдельным одноразовым заказом.
- Цена рекуррентного Shop Order фиксируется Tribute при его создании. Последующее
  изменение цены тарифа в Minishop не меняет уже оформленное списание: такой пользователь
  остаётся на прежней цене до отмены и новой подписки. Не отключайте, не удаляйте и не
  переименовывайте тариф, пока к нему привязаны активные рекуррентные заказы.
  Не меняйте `TRIBUTE_SHOP_ID`, пока такие заказы активны: сначала отмените их и дождитесь
  `shop_order_cancelled`, иначе последующие webhook не пройдут проверку Shop ID.

Minishop не использует Shop-оплату в Telegram Stars, `paymentToken`/Token Charging или
предоплаченный баланс Tribute. Если внешний Creator Digital Product предлагает свои
способы оплаты, их выбор и проведение остаются на стороне Tribute.

## Резервный режим: Creator subscriptions и Digital Products

- Tribute публикует отдельную подписку под каждое предложение, поэтому ссылка,
  `subscription_id` и `period_id` задаются **у каждого локального срока отдельно** — в
  редакторе тарифа, в разделе «Подписка Tribute». Ссылка вида
  `https://t.me/tribute/app?startapp=ep_...` должна вести именно на ту подписку, которая
  продаёт этот срок. Если все сроки продаёт одна подписка, достаточно повторить её ссылку
  и `subscription_id` в каждой строке.
- Числовых ID нет ни в кабинете Tribute, ни в share-ссылке: их выдаёт только Creator API.
  Поэтому кнопка **«Подтянуть из Tribute»** в редакторе тарифа читает
  [Subscriptions API](https://wiki.tribute.tg/for-content-creators/api-documentation/subscriptions)
  и [Products API](https://wiki.tribute.tg/for-content-creators/info-products-and-content/api-integration)
  тем же `TRIBUTE_API_KEY`. Выбор подписки подставляет `subscription_id` и `period_id`
  во все локальные сроки: Tribute-периоды `monthly`, `quarterly`, `halfyearly` и `yearly`
  сопоставляются с 1, 3, 6 и 12 месяцами. Периоды, которых нет в подписке, остаются
  незаполненными и попадают в список расхождений. Share-ссылку API не отдаёт — её
  по-прежнему копируют из кабинета вручную.
- Для фиксированных пакетов обычного и premium-трафика можно указать `product_id` и
  ссылку заранее созданного
  [Digital Product](https://wiki.tribute.tg/for-content-creators/info-products-and-content/api-integration).
  После загрузки каталога поле ID товара становится списком, а выбор подставляет ещё и
  ссылку — её Products API, в отличие от подписок, публикует.
- Цена и цикл таких подписок/товаров задаются в Tribute. Локальная цена отображается в
  Minishop, но не отправляется по Creator-ссылке, поэтому администратор должен вручную
  поддерживать цены одинаковыми. Загруженный каталог сверяется с текущим тарифом:
  редактор показывает расхождение цены и валюты, а также ID, которых больше нет в Tribute
  или которые продают другой срок.
- Не удаляйте и не переиспользуйте `subscription_id`, `period_id` и `product_id`, пока
  возможна доставка отложенных webhook или возвратов по этим продажам. Сначала уберите
  ссылку из новых checkout, дождитесь окончания расчётного/возвратного окна Tribute и
  только затем удаляйте mapping.

Creator donations намеренно не используются для продаж: донатор сам выбирает сумму, а
webhook не даёт устойчивой корреляции с конкретным внутренним заказом Minishop. События
`new_donation` и `recurrent_donation` поэтому не активируют тариф, трафик или устройства.

## Lifecycle, отмена и возвраты

- Доступ меняется только после webhook с корректной подписью. Повторные доставки
  дедуплицируются, а устаревшее событие не может откатить уже обработанное продление.
- `new_subscription`/`renewed_subscription` и
  `shop_order`/`shop_order_charge_success` продлевают доступ по подтверждённому событию.
  Промежуточные Shop-события `shop_order_payment_received` и `shop_order_prepaid`
  подтверждаются без выдачи доступа: Minishop ждёт финальный `shop_order`.
  Creator `expires_at` считается авторитетной датой; `trial` и `gift` поддерживаются без
  локального реферального бонуса за бесплатный период.
- Пока у пользователя активно рекуррентное списание Tribute, Minishop не разрешает
  заменить тариф или оформить другую period-подписку. Сначала пользователь должен
  отменить рекуррентность в Tribute, а Minishop — получить `shop_order_cancelled` или
  `cancelled_subscription`. Отмена выключает следующие списания, но оплаченный доступ
  сохраняется до текущей даты окончания.
- Если два рекуррентных Shop Order всё же были оплачены конкурентно до первого webhook,
  Minishop отменяет второй заказ, инициирует возврат его первого списания и не выдаёт по
  нему доступ. Пока Tribute не подтвердит возврат, событие остаётся в quarantine для
  ручной проверки.
- `shop_order_charge_failed` не выдаёт новый срок. Minishop ждёт предусмотренные Tribute
  повторные попытки и отключает локальное автопродление после третьей неудачи; более
  поздний успешный charge снова синхронизирует состояние.
- `digital_product_refunded` помечает связанный платёж как возвращённый.
  `shop_order_refunded` помечает возвращённым завершённый одноразовый платёж, а возврат
  рекуррентного заказа требует ручной проверки учёта и entitlement. Уже израсходованный
  трафик и выданные/использованные устройства автоматически не отзываются.

## Справочник

- [Tribute Shop API](https://wiki.tribute.tg/for-shops/api)
- [Методы Shop API](https://wiki.tribute.tg/for-shops/api/methods)
- [Shop webhooks](https://wiki.tribute.tg/for-shops/api/webhooks)
- [Creator API](https://wiki.tribute.tg/for-content-creators/api-documentation)
- [Creator webhooks](https://wiki.tribute.tg/for-content-creators/api-documentation/webhooks)
- [Переменные Tribute](../../configuration/env-vars.md#tribute)
