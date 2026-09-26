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

Оболочка Web App включает только словарь начального языка. При смене языка клиент запрашивает
`/api/i18n?scope=webapp&lang=<код>`, а в админке дополнительно
`/api/i18n?scope=admin&lang=<код>`. Ответ содержит один язык; повторно выбранные словари
переиспользуются в пределах открытой страницы. Поэтому переводы плагина в `locales_dir()`
должны иметь ключи для каждого поддерживаемого языка и нужной области (`wa_`/`admin_`).

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

Секции админки поддерживают два способа подключения: build-time descriptor
и ESM-модуль подписанного runtime-пакета. Ниже описан первый вариант;
установка пакетов без пересборки описана в конце страницы.

Пользовательские страницы, инструкции, заказы, надёжные задания, награды и
бэкапы описаны в [SDK расширений v1](plugin-extensions.md).

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

### Composing an outbound message

`bot.services.message_composition` — нейтральный контракт авторского сообщения, общий для
рассылки, сообщения одному пользователю и цепочек плагина. Плагин собирает кнопки из простых
значений, без импорта админских HTTP-схем:

```python
from bot.services.message_composition import MessageButtonInput, resolve_message_buttons

buttons = resolve_message_buttons(
    [MessageButtonInput(kind="promo_webapp", label="Применить код", promo_code=code)],
    mini_app_url=settings.SUBSCRIPTION_MINI_APP_URL,
    bot_username=bot_username,
)
await outbound_messaging.send_text(session, user_id=uid, text=text, buttons=buttons)
```

Виды кнопок — `url`, `promo_bot` (`/start promo_<CODE>` в боте), `promo_webapp` (открывает Mini App
с предзаполненным кодом). Для `promo_webapp` контракт сам выбирает Telegram-кнопку `web_app`, чтобы
цель открывалась **внутри** Mini App с его авторизацией, а не во внешнем браузере; при плоском
`http`-адресе Mini App происходит откат на `t.me?startapp=`. Ошибки авторинга приходят как
`MessageValidationError` со стабильным `code`. `normalize_message_channels` валидирует набор каналов
(`telegram`, `email`), `email_links_for_buttons` даёт пары `(label, url)` для письма.

Именованный экспорт `sectionTabs` добавляет вкладку в **уже существующий** раздел админки —
свой или базовый (`promos`, `users`, `payments`, …). Так расширение дополняет базовый экран, не
патча его исходники: ядро знает только о том, что раздел *может* нести вкладки, но не о том, что
именно в них лежит.

```ts
import ExampleCodes from "./ExampleCodes.svelte";

export const sectionTabs = {
  id: "example-codes",
  sectionId: "promos",
  order: 10,
  i18nKey: "section_tab_example_codes",
  fallbackLabel: "Issued codes",
  requiredFeature: "example.codes",
  component: ExampleCodes,
};
```

Первой вкладкой всегда остаётся сам раздел, подписанный своим `titleI18nKey`. Пока ни одно
расширение не зарегистрировало вкладку для раздела, полоса вкладок не рендерится и раздел
выглядит ровно как раньше. Компонент вкладки получает тот же контракт, что и компонент секции
(`AdminSectionComponentProps`): `at`, `featureAvailable`, `featuresResolved`, `availableFeatures`,
`routePrefix`, `onNavigateSection`, `onOpenUserCard` — внутренние props конкретного раздела ему не
передаются, поэтому вкладка не привязывается к его устройству.

Компонент вкладки карточки пользователя получает `at`, `user`, `userDetail`, `featureAvailable`,
`active` и `routePrefix`.
Extension-компонент полной секции получает `featureAvailable`, отсортированный массив
`availableFeatures` и `onNavigateSection(sectionId)` вместе с общими props админки. Первый флаг
отражает `requiredFeature` самой секции, а массив позволяет проверить дополнительные возможности
внутри неё. Компонент также может использовать типизированные stores из `$lib/admin/context`. `requiredFeature` и
`visibleWhenLocked` имеют ту же семантику discovery, что и для секций. Серверная route остаётся
обязательной границей авторизации и доступности функции.

## Release Images

Release images публикуются в Docker Hub через GitLab CI только для стабильных git-тегов вида
`vX.Y.Z`. Перед публикацией синхронизируйте `main` и создайте тег на его текущем commit:

```bash
git fetch gitlab main --tags
git tag vX.Y.Z gitlab/main
git push gitlab refs/tags/vX.Y.Z
```

Push `refs/tags/vX.Y.Z` запускает release job. Он отклоняет тег, если тот не указывает точно на
текущий `main`, собирает backend, worker и frontend и публикует в Docker Hub semver-теги без
начальной `v` (например, `v3.6.1` становится `3.6.1`) вместе с discovery-тегом `latest`.

Расширенные и production-сборки должны фиксировать точный Docker Hub digest. `latest` остаётся
только discovery-тегом и не является входом для воспроизводимой сборки.

## Установка подписанного пакета без пересборки Core

На стандартном Compose-хосте администратор открывает раздел **Плагины**, проверяет ZIP или
публичный репозиторий с готовым ZIP, сверяет SHA-256 архива с официальной публикацией автора,
подтверждает установку и затем включает пакет. При первом подтверждении ключ издателя
закрепляется автоматически. Предпросмотр не исполняет код.
Установка, включение, выключение и удаление переводят backend и worker на новое поколение через
штатные launcher-процессы; без обновлённых стандартных образов этот путь не поддерживается.
Выключенный пакет можно удалить без стирания его данных. Пакет, встроенный в образ, можно
выключить, но его удаление требует смены образа.

ZIP содержит `plugin.json`, `signatures/ed25519.sig`, файлы `backend/` и, при наличии интерфейса,
`frontend/`. Для первой установки добавьте в `plugin.json` поле `publisher_public_key` —
base64 от 32 байт открытого Ed25519-ключа. Поле `files` перечисляет SHA-256 каждого
payload-файла. Подпись охватывает
канонический JSON manifest: UTF-8, отсортированные ключи, разделители `,` и `:`, без пробелов.
`publisher_fingerprint` — SHA-256 от 32 байт открытого Ed25519-ключа. В manifest указываются
`schema_version: 1`, `id`, `version`, `publisher`, `plugin_api: 1`, `frontend_host_api: 1`,
`core_revision`, `runtime` (`python`, `system`, `machine`), `backend.entry_point` и `files`.
По умолчанию `core_revision` должен совпадать с запущенным экземпляром Core.
Для пакета только с исходным Python-кодом можно указать
`"core_compatibility":{"mode":"capabilities","requires":{"capability_name":1}}`.
Тогда `core_revision` сохраняет сведения о проверенной сборке, а установщик
проверяет версии требуемых публичных возможностей вместо точного commit.
`capability_name` здесь — пример: укажите опубликованное имя из
`bot.plugins.capabilities` и требуемую версию его контракта. Пакеты с бинарным
backend не могут использовать этот режим. Профиль Python/ОС/CPU всё равно
должен совпадать с запущенным экземпляром. При несовместимом изменении
публичной возможности Core увеличивает её версию; пакет с прежней версией
будет отклонён.
Для пакета, совместимого с текущей и последующими версиями Core, можно вместо этого указать
`"core_compatibility":{"mode":"minimum_version","version":"3.4.4"}`. Установщик сравнивает
числовые версии `X.Y.Z` по `.build-tag` или последнему Git-тегу; если версию сборки определить
нельзя, установка останавливается. `core_revision` остаётся SHA проверенной сборки, но не
используется для сравнения порядка коммитов: один SHA без истории Git этого не позволяет.
Режим минимальной версии доступен только для backend из исходных `.py`-файлов.
Если издатель не вложил ключ в ZIP, ранее доверенный пакет продолжит работать, но для
первой установки потребуется новый архив. Подпись и ключ сами по себе не удостоверяют
личность автора: сверяйте SHA-256 архива с его официальной публикацией.

Публичный GitHub/GitLab-репозиторий может содержать в корне `minishop-plugin.json`:

```json
{"schema_version":1,"artifact":"dist/example-plugin.zip","sha256":"<64 lowercase hex characters>","version":"1.2.3"}
```

Менеджер разрешает branch/tag в точный commit, скачивает только готовый ZIP, сверяет хеш и
подпись. Он не запускает `pip`, `npm`, компилятор или скрипт сборки из репозитория. Нельзя
загружать пакет без вложенного или ранее закреплённого ключа, использовать `.pth`, вложенные
wheels, пути вне ZIP или
занимать служебные Python namespaces Core. Выполненный код имеет права приложения; подпись
устанавливает происхождение, но не создаёт sandbox.

Пакетный frontend — отдельный ESM-модуль с `mountView(view, target, props)` и
`unmountView(instance)`. Descriptor может добавлять секции, вкладки и панель пользователя.
Модуль получает обычные props host API и не использует внутренние Svelte-компоненты Core как
контракт. Asset URLs привязаны к digest пакета и требуют админской сессии.

Для карточек и подразделов внутри существующих экранов используйте
[UI composition v1](plugin-ui-composition.md): пользовательские section-pages,
именованные customer/admin slots, явные замены и безопасный fallback в Core.

### Карточка и настройки плагина

Менеджер показывает одну карточку на `id`: если пакет одновременно установлен и зарегистрирован
как entry point образа, записи объединяются. Источник виден по нажатию на бейдж версии.
Необязательные поля `name` и `description` берутся из подписанного `plugin.json`.
Для изображения добавьте `frontend.preview` с относительным путём внутри `frontend/` и включите
этот файл в подписанный `files`. Изображение загружается только в открытом разделе плагинов;
для пакетов без него используется нейтральная заглушка. Рекомендуется WebP 16:10 до 100 КБ.

Плагин может объявить `frontend.settings_tabs` как массив объектов с `id`, `view`, `label` и
необязательными `i18nKey` и `order`. `view` передаётся в тот же `mountView`, что и остальные виды
плагина; несколько вкладок загружаются по одной при выборе. Ключ локализации должен быть
доступен в каталогах плагина и сборки frontend.
Админ открывает **Плагины → карточка → Настройки**; интерфейс плагина загружается только при
открытии его настроек. Все действия в нём обязаны проверять полномочия на сервере. Если
настроек нет, Core показывает пустое состояние. Старая отдельная секция может оставаться
доступной по прямой ссылке: у соответствующего объекта в `frontend.sections` укажите
`"hideInNavigation": true`. Core сохранит маршрут, но уберёт секцию из бокового меню.

Вкладка **Обновления** различает источник. Пакет из образа обновляется новым образом и не
перезаписывается ZIP в работающем контейнере. Для установленного из публичного GitHub/GitLab
репозитория Core фоново проверяет только `minishop-plugin.json` закреплённой при установке ветки
раз в десять минут. Необязательное `version` в индексе позволяет показать красную точку, если стабильная
семантическая версия строго новее установленной и SHA-256 архива изменился. Без версии в индексе
ручная проверка остаётся доступной, но точка не показывается. Ошибка сети не блокирует
раздел. Установка всё равно проходит полный предпросмотр, проверку хеша, подписи, издателя и
совместимости. Для ZIP без репозитория доступна ручная загрузка новой версии. Менеджер не
опросит частные репозитории без явного безопасного контракта доступа и не выводит точку для
образа по одному лишь номеру версии. Для такого уведомления поставщик образа должен дать
авторизованный версионированный канал обновлений; до этого ложное обещание обновления скрыто.
Для стабильных обновлений укажите при установке ветку релизного канала, а не ветку разработки.

Плагин должен проверять поколение перед внешними side effects и сохранять идемпотентность
фоновых задач. Если новый код или миграция не запустились, Core переходит в безопасный режим:
данные и ограничительные записи сохраняются, а внешние плагины не загружаются. Откат после
применённой несовместимой миграции требует
проверки схемы и восстановления по отдельному runbook; простая смена файлов его не заменяет.
