# Платежи

Платежные методы включаются через `.env` или админ-панель, если параметр добавлен в allowlist настроек. В Mini App способы оплаты по умолчанию собраны в компактный выпадающий список; настройка `PAYMENT_METHODS_DISPLAY_MODE=buttons` возвращает отдельные кнопки. Telegram-сценарии продолжают использовать кнопки.

## Общий порядок настройки

1. Включите нужный провайдер.
2. Заполните публичные параметры, секреты и URL возврата.
3. Настройте webhook URL у провайдера, если он используется.
4. Проверьте порядок способов оплаты в `PAYMENT_METHODS_ORDER`.
5. Выберите выпадающий список или отдельные кнопки в **Платежи → Оформление оплаты**.
6. Проверьте подписи и иконки способов оплаты.
7. Выполните тестовый платеж.
8. Проверьте логи `backend`.

> [!NOTE]
> Если URL возврата не задан явно, используется ссылка на Telegram-бота.

## Выбор способа оплаты в Mini App

`PAYMENT_METHODS_DISPLAY_MODE=dropdown` используется по умолчанию и показывает компактный
выпадающий список. Значение `buttons` возвращает отдельные кнопки. В обоих режимах сохраняются
порядок из `PAYMENT_METHODS_ORDER`, название и иконка провайдера; настройка находится в
**Платежи → Оформление оплаты**.

Если провайдер доступен для текущей валюты, но итоговая корзина меньше его минимальной суммы,
он остаётся в списке заблокированным. Наведение, фокус, нажатие или tap показывают подсказку с
точным минимумом. Доступность пересчитывается по полной цене подписки и выбранных дополнений
после процентной скидки промокода. Backend независимо повторяет проверку и возвращает
`payment_amount_below_minimum`, если клиент отправил устаревшую или изменённую сумму.

Поддержка дополнений проверяется отдельно от минимальной суммы. Провайдеры с внешним управлением
ценой и рекуррентные методы, которые не умеют включить дополнения в первый платёж, разрешают
обычную подписку, но блокируют checkout с выбранными устройствами или гибкими лимитами.

## Общие ссылки

- [Справочник `.env`](../configuration/env-vars.md) — все ключи платежных провайдеров.
- [Админ-панель](admin-panel.md) — UI-настройки платежей.
- [Тарифы](tariffs.md) — цены, Telegram Stars и сценарии покупки.
- [Промокоды](promocodes.md) — скидки, множители и checkout-активация.
- [Партнёрская программа](partner-program.md) — комиссии с внешних платежей и полная/частичная
  оплата покупок из баланса.
- [Баланс пользователя](user-balance.md) — пополнение через провайдера, внутренние списания,
  конвертация и обработка возвратов.
- [Логи](../troubleshooting/logs.md) — проверка webhook и создания платежных ссылок.

## Проверка расчёта

Для period-тарифа checkout может включать устройства и гибкие итоговые лимиты обычного и premium-трафика из тарифного каталога. Гибкий лимит действует в каждом периоде сброса оплаченного срока; он не пополняет несгораемый баланс отдельной докупки трафика. Во время перетаскивания слайдера Mini App меняет цену локально, после завершения запрашивает серверную котировку всей корзины, а создание платежа пересчитывает её повторно. Процентная скидка промокода применяется к полному subtotal — базовой подписке и всем выбранным дополнениям, включая пропорциональную доплату за немедленное повышение активной подписки, — и только затем рассчитывается внешняя часть платежа после партнёрского баланса.

При раннем продлении того же тарифа полный выбранный пакет оплачивается на новый срок, а увеличение над уже оплаченными активными устройствами/лимитами рассчитывается пропорционально остатку текущего окна. Понижение не возвращает деньги и применяется со следующей границы подписки. Котировка привязана к ID и дате окончания активной подписки: параллельное продление делает старый счёт неактуальным и не позволяет повторно выдать права. Смена тарифа не маскируется под обычное продление и выполняется отдельным сценарием.

Заказ активируется только по аутентифицированному успешному подтверждению в той же валюте.
Подтверждённая сумма, равная цене счёта или больше неё, активирует ровно один исходный
заказ: переплата не добавляет месяцы, трафик или устройства. Недоплата и другая валюта не
активируют заказ. Ответ webhook отклоняет такое подтверждение; если провайдер уже захватил
средства, возврат или отдельная доплата оформляются через этого провайдера, а не выдачей
полного заказа за меньшую сумму.

Обычный или партнёрский баланс можно применить к покупке полностью или частично. При смешанной
оплате провайдеру передаётся только остаток после выбранного баланса, а `Payment` хранит также
полный checkout total и сумму внутреннего списания. В денежную выручку попадает только внешний
остаток. Полностью покрытая балансом покупка создаёт внутренний `Payment` для аудита и общей
активации, но не увеличивает денежную выручку и не порождает новую комиссию или реферальный бонус.
Одновременно списывается только один явно выбранный источник. Подробности, ограничения и
восстановление отменённых операций описаны в руководствах по
[балансу пользователя](user-balance.md#оплата-из-баланса) и
[партнёрской программе](partner-program.md#оплата-из-баланса).

## Webhook URL провайдеров
> [!TIP]
> Готовый URL вебхука отображается вверху раздела каждого провайдера в админ-панели.

Все платежные webhook URL строятся от `WEBHOOK_BASE_URL` - публичного HTTPS-адреса backend/webhook-домена. Это должен быть домен, который проксируется на backend-сервер вебхуков (`backend:8080`), а не `SUBSCRIPTION_MINI_APP_URL` frontend/Mini App. Если `WEBHOOK_BASE_URL=https://bot.example.com`, то полный адрес получается как `https://bot.example.com` + путь из таблицы.

Если у провайдера включена IP-фильтрация (`FREEKASSA_TRUSTED_IPS`, `WATA_TRUSTED_IPS`,
`HELEKET_TRUSTED_IPS`, `OXAPAY_TRUSTED_IPS`, `PAYKILLA_TRUSTED_IPS` или встроенный allowlist
YooKassa),
reverse proxy должен прокидывать `X-Forwarded-For`, а его IP/CIDR должен входить в
`TRUSTED_PROXIES`. Иначе backend увидит IP proxy/Docker gateway и может отклонить
валидный webhook с ошибкой `403`. Для webhook-домена за Cloudflare backend использует
`CF-Connecting-IP`, предварительно проверив, что ближайший внешний proxy-hop принадлежит
официальной сети Cloudflare.

| Провайдер | Что указать в кабинете провайдера | Комментарий |
| --- | --- | --- |
| YooKassa | `WEBHOOK_BASE_URL` + `/webhook/yookassa` | Например `https://bot.example.com/webhook/yookassa`. |
| FreeKassa | `WEBHOOK_BASE_URL` + `/webhook/freekassa` | Используйте как notification/webhook URL; при IP-фильтрации заполните `FREEKASSA_TRUSTED_IPS`. |
| Platega | `WEBHOOK_BASE_URL` + `/webhook/platega` | Один общий webhook для всех разовых методов и рекуррентной подписки Platega. |
| RollyPay | `WEBHOOK_BASE_URL` + `/webhook/rollypay` | Один подписанный webhook для разовых и всех регулярных списаний RollyPay. |
| SeverPay | `WEBHOOK_BASE_URL` + `/webhook/severpay` | Укажите как callback/webhook URL, если поле есть в кабинете мерчанта. |
| Wata | `WEBHOOK_BASE_URL` + `/webhook/wata` | Если включена проверка подписи, настройте `WATA_WEBHOOK_VERIFY_SIGNATURE` и `WATA_PUBLIC_KEY`. |
| CryptoPay | `WEBHOOK_BASE_URL` + `/webhook/cryptopay` | Указывается в настройках Crypto Bot / CryptoPay webhook. |
| Heleket | `WEBHOOK_BASE_URL` + `/webhook/heleket` | При необходимости включите `HELEKET_VERIFY_WEBHOOK_SIGNATURE` и `HELEKET_TRUSTED_IPS`. |
| OxaPay | `WEBHOOK_BASE_URL` + `/webhook/oxapay` | Передаётся автоматически как `callback_url` при Generate Invoice. HMAC-SHA512 по raw body проверяется всегда. |
| PayKilla | `WEBHOOK_BASE_URL` + `/webhook/paykilla` | Указывается в PayKilla Dashboard -> Settings -> Webhooks; включите события оплаты инвойсов. |
| LAVA | `WEBHOOK_BASE_URL` + `/webhook/lava` | Передается автоматически как `hookUrl` при создании счета; можно также указать в кабинете LAVA Business. |
| Pally | `WEBHOOK_BASE_URL` + `/webhook/pally` | Укажите как Result URL в настройках магазина Pally / PayPalych. Postback приходит в формате `application/x-www-form-urlencoded`. |
| CloudPayments | `WEBHOOK_BASE_URL` + `/webhook/cloudpayments` | Укажите как адрес уведомлений Pay и Fail в кабинете CloudPayments. При IP-фильтрации заполните `CLOUDPAYMENTS_TRUSTED_IPS`. |
| Overpay | `WEBHOOK_BASE_URL` + `/webhook/overpay` | Укажите как notification URL в кабинете Overpay. Уведомление приходит JSON POST'ом с HTTP Basic auth (Shop ID / Secret Key). |
| Stripe | `WEBHOOK_BASE_URL` + `/webhook/stripe` | Укажите этот адрес в Stripe Dashboard и включите события `checkout.session.completed`, `checkout.session.expired`, `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.canceled`. |
| Tribute | `WEBHOOK_BASE_URL` + `/webhook/tribute` | Укажите URL в настройках API Tribute. Подпись проверяется API key по raw body. |
| Telegram Stars | Отдельный платежный webhook не нужен | Stars-события приходят через webhook Telegram-бота: `WEBHOOK_BASE_URL` + `/tg/webhook`. |

После настройки сделайте тестовый платеж и проверьте, что в логах `backend` видно входящий `POST` на нужный путь. Если провайдер сообщает, что адрес недоступен, сначала проверьте DNS/HTTPS и reverse proxy для `WEBHOOK_BASE_URL`, затем убедитесь, что путь начинается ровно с `/webhook/...` без `/api`, `/auth` и frontend-домена.

## Платёжные провайдеры

Подробная настройка каждого провайдера вынесена на отдельную страницу. Старые ссылки на
якоря этой страницы сохранены и ведут к соответствующей строке каталога.

| Провайдер | Сценарий |
| --- | --- |
| <span id="yookassa"></span>[YooKassa](payments/yookassa.md) | Рублёвые платежи и автопродление period-подписок. |
| <span id="freekassa"></span>[FreeKassa](payments/freekassa.md) | Рублёвые платежи с выбором способа оплаты. |
| <span id="platega"></span>[Platega](payments/platega.md) | Разовые способы оплаты и рекуррентные СБП-подписки. |
| <span id="rollypay"></span>[RollyPay](payments/rollypay.md) | Разовые платежи и регулярные СБП-списания. |
| <span id="severpay"></span>[SeverPay](payments/severpay.md) | Платёжные ссылки и callback-обработка. |
| <span id="wata"></span>[Wata](payments/wata.md) | Платежи с подписью и проверкой входящих webhook. |
| <span id="cryptopay"></span>[CryptoPay](payments/cryptopay.md) | Криптовалютные платежи через Crypto Bot / Crypto Pay. |
| <span id="tribute"></span>[Tribute](payments/tribute.md) | Shop API, Creator subscriptions и Digital Products. |
| <span id="heleket"></span>[Heleket](payments/heleket.md) | Криптовалютные инвойсы и webhook-подтверждения. |
| <span id="oxapay"></span>[OxaPay](payments/oxapay.md) | Криптовалютные инвойсы, комиссии и восстановление webhook. |
| <span id="paykilla"></span>[PayKilla](payments/paykilla.md) | Криптовалютные инвойсы V2 через hosted checkout. |
| <span id="lava"></span>[LAVA](payments/lava.md) | Рублёвые платежи картами и через СБП. |
| <span id="pally"></span>[Pally](payments/pally.md) | Hosted-счета Pally / PayPalych. |
| <span id="cloudpayments"></span>[CloudPayments](payments/cloudpayments.md) | Карточные платежи через Orders API. |
| <span id="overpay"></span>[Overpay](payments/overpay.md) | Hosted checkout и рекуррентные карточные платежи. |
| <span id="stripe"></span>[Stripe](payments/stripe.md) | Stripe Checkout и события Payment Intent. |
| <span id="telegram-stars"></span>[Telegram Stars](payments/telegram-stars.md) | Оплата цифровых покупок в Telegram Stars. |
