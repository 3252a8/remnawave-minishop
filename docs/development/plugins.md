# API плагинов и расширений

API плагинов позволяет отдельному Python-пакету расширять Remnawave Minishop
без форка основного репозитория. Контракт пока экспериментальный: API может
меняться между minor-версиями, пока поверхность расширений стабилизируется.

## Обнаружение

Внешние плагины обнаруживаются через Python entry point group
`minishop.plugins`. Entry point должен возвращать наследника
`bot.plugins.spec.Plugin` или готовый экземпляр `Plugin`.

Встроенные плагины поставляются вместе с приложением и всегда активны.
Настройка `PLUGINS_ENABLED` отключает только поиск внешних entry point.
`PLUGINS_STRICT=true` делает ошибки загрузки или выполнения хуков
фатальными; по умолчанию они логируются, а ядро продолжает запуск.

Минимальный `pyproject.toml`:

```toml
[project]
name = "minishop-example-plugin"
version = "0.1.0"
dependencies = []

[project.entry-points."minishop.plugins"]
example = "minishop_example_plugin:plugin"
```

Пакет нужно установить в то же Python-окружение, где запускается backend, чтобы
ему были доступны пакеты ядра `bot`, `config` и `db`.

Минимальный плагин:

```python
from bot.plugins.spec import Plugin, PluginContext


class ExamplePlugin(Plugin):
    name = "example"
    version = "0.1.0"

    def setup(self, ctx: PluginContext) -> None:
        ctx.services["example_service"] = object()


plugin = ExamplePlugin()
```

В репозитории также есть runnable sample:
[`examples/plugins/audit_logger_plugin`](../../examples/plugins/audit_logger_plugin). Его можно поставить
в dev-окружение командой `pip install -e examples/plugins/audit_logger_plugin`; entry point
`minishop.plugins` вернёт готовый объект `plugin`.

## Контракт Plugin

`PluginContext` передаёт плагину общие объекты текущего процесса:

- `settings`: настройки приложения.
- `session_factory`: SQLAlchemy session factory, если доступна.
- `bot`: экземпляр aiogram bot, если доступен.
- `i18n`: каталог `JsonI18n`, если доступен.
- `dispatcher`: aiogram dispatcher, если доступен.
- `services`: изменяемый реестр сервисов текущего процесса.
- `audience_segmentation_service`: типизированная точка регистрации дополнительных аудиторий
  рассылки; обязательный вариант доступен как `require_audience_segmentation_service()`.

Все хуки опциональны: базовый класс `Plugin` даёт no-op реализацию.

- `setup(ctx)`: общая инициализация, вызывается первой один раз на процесс.
  Здесь удобно подписываться на доменные события и добавлять сервисы.
- `setup_bot(ctx, *, user_root, admin_root)`: регистрация aiogram-роутеров.
  `admin_root` уже защищён admin-фильтром.
- `setup_web(ctx, app, *, scope)`: регистрация aiohttp routes. `scope`
  принимает значения `webhooks` или `webapp`.
- `worker_tasks(ctx) -> list[WorkerTaskSpec]`: добавление долгоживущих задач
  worker-процесса.
- `queue_handlers(ctx) -> dict[str, QueueHandler]`: добавление обработчиков
  webhook-очереди по имени provider. Имена, занятые ядром или другим плагином,
  отклоняются.
- `migrations() -> list[Migration]`: добавление цепочки миграций БД.
- `locales_dir() -> Path | None`: добавление JSON-файлов локализации.
- `entitlements_provider() -> EntitlementsProvider | None`: публикация feature
  flags для ядра и админского frontend.

## Доменные события

Плагины подписываются на события внутри `setup()` через
`bot.infra.events.subscribe`. Обработчик получает `(event_name, payload)`.
`emit()` вызывает подписчиков последовательно, логирует ошибки подписчиков и
не пробрасывает исключения в основной поток ядра.

Payload события - плоский словарь примитивов: id, числа, строки и даты в
ISO-формате. ORM-объекты в payload не передаются; если нужны подробные данные,
плагин перечитывает их из БД по id.

Публикуемые события:

- `payment.succeeded`: `user_id`, `payment_db_id`, `provider`, `amount`,
  `currency`, `sale_mode`, `months`, `traffic_gb`, `end_date`,
  `is_auto_renew`.
- `payment.canceled`: `user_id`, `payment_db_id`, `provider`,
  `provider_payment_id`, `status`.
- `subscription.created` / `subscription.extended`: `user_id`,
  `subscription_id`, `tariff_key`, `end_date`, `provider`, `months`,
  `payment_db_id`.
- `trial.activated`: `user_id`, `end_date`, `days`, `traffic_gb`.
- `user.registered`: `user_id`, `language`, `referred_by_id`,
  `registered_via`.
- `account.email_linked`: `user_id`, `email`.
- `account.telegram_linked`: `user_id`, `telegram_id`.
- `account.merged`: `source_user_id`, `target_user_id`.
- `promo_code.applied`: `user_id`, `code`, `bonus_days`, `new_end_date`.
- `referral.bonus_granted`: `referee_user_id`, `referee_bonus_days`,
  `referee_new_end_date`, `inviter_bonus_applied`, `payment_db_id`, `reason`.
- `support.ticket_created`: `user_id`, `ticket_id`, `category`, `priority`.
- `panel.webhook_received`: `event`, `panel_user_uuid`, `telegram_id`.

Пример подписки:

```python
from bot.infra import events


async def on_payment(event_name: str, payload: dict) -> None:
    user_id = payload.get("user_id")
    # При необходимости загрузите дополнительные данные по id.


class ExamplePlugin(Plugin):
    name = "example"
    version = "0.1.0"

    def setup(self, ctx: PluginContext) -> None:
        events.subscribe(events.PAYMENT_SUCCEEDED, on_payment)
```

Контракт подписчика закреплён тестами: публичная сигнатура остаётся `(event_name, payload)`, где
`payload` — обычный плоский `dict`.

## Checkout, промокоды и гранты

Плагины могут расширять три цепочки, которые используются checkout-промокодами:

- `bot.infra.pricing.register_price_modifier` добавляет модификатор цены. На вход приходит
  `PriceContext`, на выходе - набор `PriceAdjustment`; итоговая скидка суммируется и
  ограничивается `100%`.
- `bot.infra.grants.register_grant_modifier` добавляет модификатор выдачи. На вход приходит
  `GrantContext`, на выходе - `GrantAdjustment` с дополнительными днями или множителем трафика.
- `bot.infra.promo_policies.register_promo_redemption_policy` добавляет политику погашения
  промокода. Политика получает `PromoRedemptionContext` и возвращает
  `PromoRedemptionDecision.allow()` или `deny("reason_key")`.

Ядро всегда запускает свои проверки первым: активность и срок действия промокода, общий лимит,
повторное использование пользователем, pending-платеж с тем же кодом и минимальные требования
к покупке. Плагиновые политики выполняются после core-политик и могут только дополнительно
запретить или расширить поведение через отдельные price/grant modifiers.

## Миграции БД

Плагин использует тот же dataclass `db.migrator.Migration`, что и ядро.
Каждый плагин возвращает отдельную цепочку через `migrations()`.

Правила:

- Id миграции должен начинаться с `"<plugin name>."`, например
  `example.0001_initial`.
- Все цепочки используют общую таблицу `schema_migrations`.
- Таблицы плагина должны использовать префикс `ext_<plugin>_`, например
  `ext_example_events`.
- Миграции должны быть идемпотентны относительно целевой схемы.

## Локали

`locales_dir()` может вернуть каталог с JSON-файлами в той же структуре, что
и основной каталог локалей, например `en.json` и `ru.json`.

Ключи плагинов не перезаписывают ключи, уже определённые в базовом каталоге
ядра. Runtime overrides из слоя настроек админки применяются после слияния
базовых каталогов.

Для новых ключей используйте префикс плагина, например `example_title` или
`admin_example_section_title`.

## Feature Flags

Плагин может опубликовать feature flags, вернув `EntitlementsProvider` из
`entitlements_provider()`. Активный provider отвечает на `has_feature(name)` и
`features()`.

Если несколько плагинов возвращают provider, запуск завершается ошибкой
конфигурации: entitlement authority должен быть ровно один. Базовый provider
ядра возвращает пустой набор features, когда provider не вернул ни один
плагин. Admin
settings API отдаёт отсортированный список как `features: string[]`; админский
frontend скрывает секции, у которых в descriptor указан `feature`, отсутствующий
в этом списке.

## Секции админки

Секции админки сейчас являются build-time точкой расширения frontend, а не
Python-хуком.

Базовые descriptor'ы лежат в `frontend/src/admin/sections/registry.ts`.
Расширенные сборки могут добавлять файлы
`frontend/src/admin/sections/extensions/*.ts`, экспортирующие по умолчанию один
descriptor или массив descriptor'ов:

```ts
import ExampleSection from "./ExampleSection.svelte";
import { Sparkles } from "$components/ui/icons.js";

export default {
  id: "example",
  group: "operations",
  order: 90,
  i18nKey: "nav_example",
  fallbackLabel: "Example",
  titleI18nKey: "section_example_title",
  fallbackTitle: "Example",
  subtitleI18nKey: "section_example_subtitle",
  fallbackSubtitle: "Extension section",
  icon: Sparkles,
  component: ExampleSection,
  requiredFeature: "example.admin",
  visibleWhenLocked: true,
};
```

Registry сортирует extension-модули по пути, а descriptor'ы - по `group`,
`order` и `id`, чтобы сборка была детерминированной. Если секция должна быть
видна всегда, не указывайте `requiredFeature`.

Extension-модуль может добавить новую группу навигации именованным экспортом
`sectionGroups` (один descriptor или массив). Идентификаторы базовых групп
зарезервированы за ядром:

```ts
export const sectionGroups = {
  id: "reports",
  order: 35,
  i18nKey: "nav_reports",
  fallbackLabel: "Reports",
};
```

Новые extension descriptor'ы используют `requiredFeature` вместо legacy
`feature`. Если `visibleWhenLocked: true`, секция остается в навигации без
feature, чтобы сам extension-компонент отрисовал нейтральное locked-состояние.
Эти поля управляют только frontend-discovery: серверная авторизация остается
обязанностью extension route/API.

Тот же extension-модуль может именованно экспортировать `userDetailPanels` — descriptor или массив
descriptor'ов дополнительных вкладок карточки пользователя:

```ts
import ExampleTimeline from "./ExampleTimeline.svelte";

export const userDetailPanels = {
  id: "example-timeline",
  order: 90,
  i18nKey: "user_tab_example_timeline",
  fallbackLabel: "Timeline",
  requiredFeature: "example.timeline",
  component: ExampleTimeline,
};
```

Компонент вкладки получает `at`, `user`, `userDetail`, `featureAvailable`, `active` и `routePrefix`.
Extension-компонент полной секции получает `featureAvailable`, отсортированный массив
`availableFeatures` и `onNavigateSection(sectionId)` вместе с общими props админки. Первый флаг
отражает `requiredFeature` самой секции, а массив позволяет проверить дополнительные возможности
внутри неё. Компонент также может использовать типизированные stores из `$lib/admin/context`. `requiredFeature` и
`visibleWhenLocked` имеют ту же семантику discovery, что и для секций. Серверная route остаётся
обязательной границей авторизации и доступности функции.

## Release Images

Release images публикуются только для стабильных git-тегов вида `vX.Y.Z`.
Сначала создайте draft Release, привязанный к текущему `main`:

```bash
gh release create vX.Y.Z --target main --draft --generate-notes --title vX.Y.Z
git fetch origin main --tags
git tag vX.Y.Z origin/main
git push origin refs/tags/vX.Y.Z
```

Draft Release сам по себе не создаёт remote git-тег. Push `refs/tags/vX.Y.Z`
запускает release workflow, который собирает и сканирует три candidate-образа, проверяет их OCI
provenance, последовательно публикует semver-теги без начальной `v` (например,
`v3.4.5` становится `3.4.5`) и только затем публикует draft Release. В Release
прикладываются `release-images.json` и его SHA-256: в них указаны source commit,
проверяемые image digests и готовые `@sha256` references для GHCR и Docker Hub.

Расширенные и production-сборки должны использовать reference из manifest с
точным digest. `latest` остаётся только discovery-тегом и не является входом для
воспроизводимой сборки.
