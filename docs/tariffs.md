# Тарифы 2.0

Бот поддерживает каталог тарифов в JSON-файле. Путь задается через `TARIFFS_CONFIG_PATH`, по умолчанию используется `config/tariffs.json`.

Если файл отсутствует, включается legacy-режим: используются старые `.env` поля `RUB_PRICE_*`, `STARS_PRICE_*`, `USER_TRAFFIC_LIMIT_GB`, `USER_SQUAD_UUIDS`, а также старый режим продажи трафика через `TRAFFIC_PACKAGES`.

## Конфиг

Пример конфига: [`config/tariffs.example.json`](../config/tariffs.example.json).

Основные поля:

| Поле | Описание |
| --- | --- |
| `default_tariff` | Тариф по умолчанию для миграции существующих подписок и первичного выбора |
| `topup_packages_default` | Пакеты докупки трафика для period-тарифов без собственных пакетов |
| `tariffs[].billing_model` | Модель тарификации: `period` или `traffic` |
| `tariffs[].squad_uuids` | Internal Squads Remnawave, которые получает пользователь на этом тарифе |
| `tariffs[].hwid_device_limit` | Базовый лимит HWID-устройств для тарифа; `0` означает без ограничений, отсутствие поля использует `USER_HWID_DEVICE_LIMIT` |
| `tariffs[].hwid_device_packages` | Пакеты докупки HWID-устройств, например `{ "count": 1, "price": 99 }` |
| `prices_rub` / `prices_stars` | Цены period-тарифов по месяцам |
| `traffic_packages` | Пакеты GB для traffic-тарифов |

## Period-Тариф

Period-тариф продает доступ на срок и лимит трафика с календарным ежемесячным сбросом.

- `monthly_gb` превращается в `tier_baseline_bytes`.
- Докупленные пакеты трафика хранятся в `topup_balance_bytes`.
- В Remnawave отправляется `trafficLimitBytes = tier_baseline_bytes + topup_balance_bytes`.
- Для period-тарифов бот выставляет `trafficLimitStrategy = MONTH`, а дальнейший сброс выполняет сама панель.
- Дата сброса больше не считается в боте.
- Если покупка или продление были в середине месяца, сброс все равно произойдет по правилам панели для `MONTH`.
- Бот меняет только лимиты в GB и следит за предупреждениями на основе текущего usage из панели.

## Traffic-Тариф

Traffic-тариф продает GB без срока действия.

- `end_date` технически ставится в `2099-01-01 UTC`.
- `period_start_at = NULL`.
- `trafficLimitStrategy = NO_RESET`.
- Новая покупка добавляет GB к фактическому остатку: `limit = used + remaining + purchased`.
- Доступ ограничивается только при исчерпании купленного трафика.

## HWID-Устройства

Тарифы поддерживают лимит HWID-устройств и платную докупку устройств.

- При покупке или продлении тарифа бот отправляет в Remnawave `hwidDeviceLimit`.
- `subscriptions.hwid_device_limit` хранит базовый лимит тарифа.
- `subscriptions.extra_hwid_devices` хранит количество докупленных устройств.
- Эффективный лимит равен `hwid_device_limit + extra_hwid_devices`.
- Если базовый лимит равен `0`, это безлимит; докупка не нужна, а в панель отправляется `0`.
- Докупка устройств использует `sale_mode=hwid_devices`.
- Количество купленных устройств сохраняется в `payments.purchased_hwid_devices`.
- История докупок пишется в `hwid_device_purchases`.
- Докупка доступна в Web App через `/api/devices/topup-options` и `/api/payments`.
- Докупка доступна в Telegram-боте из раздела устройств.
- При смене тарифа базовый HWID-лимит берется из нового тарифа, а уже докупленные устройства сохраняются.

## Смена Тарифа

Смена тарифа пишется в `tariff_changes`.

- `period -> period`: расчет идет от `effective_monthly_price_rub`; пересчет дней использует `floor`.
- `period -> traffic`: остаток оплаченных дней конвертируется в GB по `conversion_rate_rub_per_gb` или по минимальной цене GB в RUB-пакетах.
- `traffic -> period`: пользователь покупает период, а остаток GB сохраняется как top-up поверх нового тарифа.
- При смене тарифа обновляются Internal Squads, лимит трафика, стратегия сброса и базовый HWID-лимит.

## Платежи

Новые платежи сохраняют:

- `sale_mode`: `subscription`, `traffic_package`, `topup`, `tariff_upgrade`, `hwid_devices`;
- `tariff_key`;
- `purchased_gb` для GB-покупок;
- `purchased_hwid_devices` для докупки HWID-устройств.

Legacy-поле `subscription_duration_months` остается для совместимости с существующими платежными обработчиками.

## Поведение При Исчерпании Трафика

Remnawave сама ограничивает пользователя при достижении `trafficLimitBytes`: панель переводит пользователя в статус `LIMITED`. Бот не должен удалять пользователя из Internal Squads при 100% использования трафика.

Текущее поведение воркера:

- синхронизирует из панели `status`, `trafficLimitBytes`, `usedTrafficBytes` и `trafficLimitStrategy`;
- отправляет предупреждения на уровнях из `TARIFF_TRAFFIC_WARNING_LEVELS` (по умолчанию `85,90,95`);
- оставляет блокировку и разблокировку доступа штатной логике Remnawave.

## Воркеры

`TariffTrafficWorker` запускается только при активном `tariffs.json`.

- Раз в несколько минут синхронизирует `trafficLimitStrategy = MONTH` для period-тарифов, если панель еще не переключена.
- При синхронизации стратегии не отправляет `status=ACTIVE`, чтобы случайно не снять статус `LIMITED`, выставленный Remnawave.
- Дедуплицирует предупреждения через таблицу `traffic_warnings`.
- Для traffic-тарифов дедупликация предупреждений учитывает текущий `trafficLimitBytes`, чтобы новая покупка трафика могла создать новый набор предупреждений.
