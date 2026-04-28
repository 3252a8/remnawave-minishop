# Тарифы 2.0

Бот поддерживает каталог тарифов в JSON-файле. Путь задается через `TARIFFS_CONFIG_PATH`, по умолчанию `config/tariffs.json`.

Если файл отсутствует, включается legacy fallback: используются старые `.env` поля `RUB_PRICE_*`, `STARS_PRICE_*`, `USER_TRAFFIC_LIMIT_GB`, `USER_SQUAD_UUIDS`, а также старый режим `TRAFFIC_PACKAGES`.

## Конфиг

См. пример: [`config/tariffs.example.json`](../config/tariffs.example.json).

Основные поля:

| Поле | Описание |
| --- | --- |
| `default_tariff` | Тариф для миграции существующих подписок и выбора по умолчанию |
| `topup_packages_default` | Пакеты докупки для period-тарифов без собственных пакетов |
| `tariffs[].billing_model` | `period` или `traffic` |
| `tariffs[].squad_uuids` | Internal squads Remnawave для тарифа |
| `prices_rub` / `prices_stars` | Цены period-тарифов по месяцам |
| `traffic_packages` | Пакеты GB для traffic-тарифов |

## Period-Тариф

Period-тариф продает доступ на срок и личный 30-дневный лимит трафика.

- `monthly_gb` превращается в `tier_baseline_bytes`.
- Докупленные пакеты хранятся в `topup_balance_bytes`.
- В Remnawave пушится `trafficLimitBytes = tier_baseline_bytes + topup_balance_bytes`.
- При продлении до окончания подписки дата 30-дневного сброса не меняется.
- При покупке после лапса новый период начинается с момента оплаты.

## Traffic-Тариф

Traffic-тариф продает GB без срока действия.

- `end_date` технически ставится в `2099-01-01 UTC`.
- `period_start_at = NULL`.
- `trafficLimitStrategy = NO_RESET`.
- Новая покупка добавляет GB к фактическому остатку: `limit = used + remaining + purchased`.
- Доступ ограничивается только при исчерпании купленного трафика.

## Смена Тарифа

Смена пишется в `tariff_changes`.

- `period -> period`: расчет идет от `effective_monthly_price_rub`; пересчет дней использует `floor`.
- `period -> traffic`: остаток оплаченных дней конвертируется в GB по `conversion_rate_rub_per_gb` или минимальной цене GB в RUB-пакетах.
- `traffic -> period`: пользователь покупает период, а остаток GB сохраняется как топ-ап поверх нового тарифа.

## Платежи

Новые платежи сохраняют:

- `sale_mode`: `subscription`, `traffic_package`, `topup`, `tariff_upgrade`;
- `tariff_key`;
- `purchased_gb` для GB-покупок.

Legacy поле `subscription_duration_months` остается для совместимости.

## Воркеры

`TariffTrafficWorker` запускается, только если активен `tariffs.json`.

- Раз в несколько минут проверяет 30-дневные сбросы.
- Отправляет/дедуплицирует уровни предупреждений 80/95/100 через `traffic_warnings`.
- При 100% удаляет пользователя из squad-ов тарифа и ставит `is_throttled`.
- Возвращает пользователя в squad-ы, когда лимит снова больше использованного трафика.
