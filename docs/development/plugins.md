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

Если несколько плагинов возвращают provider, выигрывает последний активный
provider. Базовый provider ядра возвращает пустой набор features. Admin
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
  feature: "example.admin",
};
```

Registry сортирует extension-модули по пути, а descriptor'ы - по `group`,
`order` и `id`, чтобы сборка была детерминированной. Если секция должна быть
видна всегда, не указывайте `feature`.

## Release Images

Release images публикуются из git-тегов вида `v*`. Release workflow тегирует
образы как `latest` и как semver без начальной `v`: например, `v3.4.5`
становится `3.4.5`. Расширенные сборки должны пинить `FROM` image на semver
tag, а не на `latest`.
