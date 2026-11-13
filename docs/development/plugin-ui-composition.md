# Разделы и карточки плагинов: UI composition v1

В capability-режиме добавьте `"ui_composition": 1` в
`core_compatibility.requires`. Для ЛК также требуется `"user_ui": 1`.
Plugin API, frontend host API и schema version остаются 1: новые поля аддитивны.
Старые страницы, слоты, секции и панели продолжают работать.

## ЛК: карточка и подраздел в существующем разделе

`frontend.user.pages` добавляет страницы; `frontend.user.slots` встраивает виды.
Например, карточка инструмента находится в «Бонусах», а её полный экран открывается
из того же раздела и не занимает ещё одно место в нижней навигации:

```json
{
  "frontend": {
    "user": {
      "entry": "customer/index.js",
      "pages": [
        {"id": "tool", "view": "tool", "label": "Дополнительный инструмент", "parent": "invite", "navigation": "section", "order": 20},
        {"id": "resources", "view": "resources", "label": "Материалы", "parent": "support", "navigation": "section", "order": 10}
      ],
      "slots": [
        {"id": "tool-card", "view": "tool-card", "label": "Дополнительный инструмент", "target": "user.invite.codes", "placement": "after", "order": 20},
        {"id": "help-card", "view": "help-card", "label": "Материалы", "target": "user.support.cards", "order": 10}
      ]
    }
  }
}
```

Все entry/styles/assets по-прежнему должны присутствовать в подписанном `files`.
Содержимое карточек и подразделов реализует плагин; Core предоставляет размещение и навигацию.
`id` и `view` различаются: маршрут использует `id`, `mountView` получает `view`.

- `navigation: "primary"` — отдельный пункт общей навигации (старый default).
- `navigation: "section"` + обязательный `parent` — кнопка внутри родительского
  раздела; на полном экране остаётся активным родитель и есть возврат в него.
- `navigation: "hidden"` — только прямая ссылка или переход из карточки.
  Необязательный `parent` сохраняет возврат в родительский раздел.
- Прямая ссылка: `/extensions/<owner>/<page-id>`; префикс установки сохраняется.
  Название и иконка принадлежат плагину, маршруты Core не переопределяются.
- `host.navigate("tool")` открывает свою страницу; `host.navigateSection("support")`
  возвращает в раздел Core. `admin` и произвольные URL для этого метода запрещены.
- Разделы «Бонусы» и «Поддержка» остаются в навигации при наличии вкладов плагина,
  даже если встроенная реферальная программа или тикеты выключены.

## ЛК: провайдер на странице входа

Плагин может добавить кнопку входа, вернув `LoginProvider` в `ExtensionContributions.login_providers`.
Для подписанного пакета укажите `"login_providers": 1` в `core_compatibility.requires`.
Core добавляет кнопку рядом со штатными способами входа. В Telegram Mini App кабинет предлагает
открыть страницу входа в браузере. В публичную конфигурацию попадают только идентификатор,
название и локальный путь запуска. JavaScript и стили пакета загружаются после входа на обычных
экранах расширений.

```python
from aiohttp import web

from bot.plugins import Plugin, PluginContext, WEB_SCOPE_WEBAPP
from bot.plugins.extensions import ExtensionContributions, LoginProvider
from bot.plugins.extensions.auth import complete_login

from .sso import begin_authorization, verify_and_resolve_account


class WorkLogin(Plugin):
    name = "work-login"
    version = "1.0.0"

    def extensions(self, ctx: PluginContext) -> ExtensionContributions:
        return ExtensionContributions(
            login_providers=(LoginProvider("sso", "Work SSO", begin_authorization),),
        )

    def setup_web(self, ctx: PluginContext, app: web.Application, *, scope: str) -> None:
        if scope == WEB_SCOPE_WEBAPP:
            app.router.add_get(
                "/auth/plugins/work-login/sso/callback", self.callback, allow_head=False
            )

    async def callback(self, request: web.Request) -> web.Response:
        user_id = await verify_and_resolve_account(request)
        if user_id is None:
            raise web.HTTPForbidden()
        return await complete_login(request, owner=self.name, provider="sso", user_id=user_id)
```

Core вызывает `begin_authorization(request)` по адресу `/auth/plugins/<owner>/<id>/start`.
Параметр `lang` позволяет выбрать язык страницы провайдера. Название отображается как текст
в локализованной кнопке Core. ID уникален внутри плагина и использует строчные латинские буквы,
цифры, дефис и подчёркивание. Первый символ должен быть буквой.

Плагин отвечает за протокол и хранение привязок. Для OAuth сохраните короткоживущий одноразовый
`state`, привязанный к браузеру, и используйте PKCE S256. При OIDC также проверяйте подпись,
issuer, audience, срок действия и `nonce`. Обмен кода выполняется на сервере. По подтверждённой
паре issuer/subject найдите заранее привязанный внутренний ID Core. Не используйте ID из
запроса браузера или совпадение неподтверждённого email. `complete_login` принимает только ID
существующего незаблокированного пользователя и выдаёт штатные cookie сессии и CSRF.
Создание, привязка и восстановление аккаунтов остаются отдельными действиями.

Регистрируйте callback у провайдера по публичному HTTPS URL кабинета. При установке в подкаталоге
укажите этот префикс в `SUBSCRIPTION_MINI_APP_URL` и настройте прокси так, чтобы он передавал
запросы `<префикс>/auth/…` в backend без префикса. Core отправляет браузер на фиксированный
локальный корень кабинета после входа. Произвольный `return_to` из браузера не используется.

## Экраны в кнопках и данные в сообщениях

В `core_compatibility.requires` пакет может объявить `"message_composition": 1`.
Страницы активных пакетов из `frontend.user.pages` доступны в выборе экрана во
всех редакторах кнопок сообщений и меню. `GET /api/admin/message/targets` возвращает
локализованные названия и владельцев; выключенные в настройках представления
страницы не предлагаются. Админские секции и слоты не становятся целями клиентских
кнопок. Доступ конкретного получателя по-прежнему определяет политика страницы.

Сохраняемая цель — `/extensions/<owner>/<page-id>`. Telegram Mini App получает
`startapp=ext_<owner>__<page-id>`; разделитель читается справа, поскольку `page-id`
не содержит подчёркиваний. Удалённый или отключённый плагин не подменяет цель
другим экраном: редактор сохраняет её как недоступную, а отправка отклоняется.

Данные сообщений объявляются через `ExtensionContributions.message_shortcodes`:

```python
from bot.plugins.extensions import (
    ExtensionContributions,
    MessageShortcode,
    MessageShortcodeContext,
)


async def remaining(context: MessageShortcodeContext) -> dict[int, str | None]:
    # Query the plugin's own data once for this recipient batch.
    return {user_id: "10" for user_id in context.user_ids}


def extensions(self, ctx):
    return ExtensionContributions(
        message_shortcodes=(
            MessageShortcode("remaining", "sample_remaining_description", remaining),
        )
    )
```

Для владельца `sample` токен имеет вид `{sample.remaining}`. Название локализуется
плагином через `description_key`; `cost` принимает `db` или `panel`. Core загружает
только использованные токены и существующих получателей, вызывает обработчик
один раз на пакет, проверяет принадлежность значений получателям и экранирует HTML.
Текстовые значения ограничены 8192 символами. Обработчик не должен завершать
транзакцию сессии; его ошибка откатывается к savepoint, а отсутствующее значение
показывается как `—`. Тайм-аут составляет 5 секунд для `db` и 15 для `panel`.
Неизвестные токены сохраняются буквально. Реестр и подстановка общие для
рассылок, личных сообщений и прочих потребителей общей композиции сообщений.

## Стабильные цели ЛК

Для каждого раздела `home`, `invite`, `support`, `settings`, `install`, `devices`,
`partner`, `notifications`, `security`, `status`, `trial` доступны:

| Цель | Назначение |
| --- | --- |
| `user.<section>.content` | Вокруг всего содержимого раздела; допустима замена |
| `user.<section>.cards` | Дополнительные карточки после содержимого |
| `user.invite.gifts`, `.codes`, `.referrals` | Отдельные встроенные блоки «Бонусов» |
| `user.home.summary` | Сводная карточка в компактном режиме |
| `user.home.balance`, `.subscription`, `.traffic` | Карточки обычного режима главной |
| `user.home.status` | Карточка состояния серверов |
| `user.settings.profile`, `.codes` | Профиль и активация кода в настройках |
| `user.devices.card` | Каждая карточка подключённого устройства целиком (`ui_composition=4`) |
| `user.devices.card.header`, `.details`, `.actions` | Заголовок, сведения и действия внутри каждой карточки (`ui_composition=4`) |

Старые `user.home.cards`, `user.profile.actions`, `user.subscription.actions`,
`user.install.blocks` сохраняют прежнее добавление после соответствующего экрана.
Карточная цель существует только при рендере её встроенного контейнера: например,
`user.home.traffic` относится к обычному режиму активной подписки. Если вклад должен
показываться независимо от режима или подписки, используйте `.cards` или `.content`.
Неизвестная цель ЛК отклоняется при установке.

### Карточки подключённых устройств

Пакет объявляет `"user_ui": 1, "ui_composition": 4` в
`core_compatibility.requires`. Все четыре цели карточки поддерживают `before`,
`after` и `replace`; `user.devices.cards` по-прежнему добавляет блоки после всего
экрана, а `user.devices.content` заменяет весь экран.

```json
{"id": "router-info", "view": "router-info", "label": "Router info", "target": "user.devices.card.details", "placement": "after", "device_types": ["router"]}
```

Вид монтируется отдельно для каждого устройства. `props.context.device` содержит
снимок его `WebAppDeviceOut`: `token`, имена, `device_model`, `device_type`,
`router_platform`, платформу, клиент и доступность отключения. Исходный HWID и
IP не добавляются. Снимок обновляется при обновлении списка или переименовании;
это не store и его изменение не меняет устройство. Общие `screen`, `subscription`
и метаданные вида сохраняются. Для поведения только на роутерах проверяйте
`device.device_type === "router"` в своём виде либо добавьте `device_types: ["router"]`
в descriptor. Этот необязательный непустой список принимает значения `device_type`
без повторов и доступен только четырём целям карточки. Фильтр применяется до
разрешения конфликтов: другие устройства сохраняют Core, а замены с разными
типами не конфликтуют. Без фильтра `replace` заменяет область каждого устройства.
Не скрывайте стандартные действия без собственной реализации.

Core определяет тип до передачи данных плагину по исходным `deviceModel`,
`platform`, `osVersion` и `userAgent` панели, независимо от пользовательского
имени. `device_type` принимает `phone`, `tablet`, `laptop`, `desktop`, `tv`,
`router`, `unknown`. `router_platform` содержит `openwrt`, `keenetic`, `routeros`,
`dd-wrt`, `asuswrt`, `tomato` или `null`; `device_model` сохраняет исходную модель.
Явные признаки OpenWrt/LEDE, Keenetic/KeeneticOS/NDMS и других поддержанных
прошивок имеют приоритет над Linux. Обычные Linux, curl, Mihomo или sing-box
без признаков роутера не доказывают его тип. Если клиент не передаёт подходящих
данных, надёжное определение невозможно. Это подсказка для интерфейса, не
доверенная аппаратная идентификация и не основание для ограничения доступа.

Порядок, конфликт замен и возврат к Core при ошибке импорта, mount или update
работают для каждого экземпляра карточки независимо. DOM-селекторы не нужны.

## Админка: карточки, вкладки и замена содержимого

Админский descriptor находится в `frontend` рядом с `entry`. Вкладки существующих
разделов уже поддерживаются; пакету с одними вкладками отдельная секция не нужна:

```json
{
  "frontend": {
    "entry": "admin/index.js",
    "section_tabs": [
      {"id": "resources", "view": "resources-editor", "sectionId": "support", "label": "Материалы", "order": 10}
    ],
    "slots": [
      {"id": "help-summary", "view": "help-summary", "label": "Материалы", "target": "admin.support.content", "placement": "before", "order": 0},
      {"id": "tariff-card", "view": "tariff-editor", "label": "Тариф", "target": "admin.users.detail.tariff", "placement": "replace"}
    ]
  }
}
```

`admin.<section-id>.content` доступен во всех разделах, включая зарегистрированные
плагинами. Неизвестный раздел не рендерит вклад; его slug не перенаправляется на
другой экран. Внутренние вкладки (настройки, фильтры тикетов и т.п.) остаются
собственностью своего раздела. Вклад `section_tabs` расширяет внешний уровень.
Прямая ссылка: `/admin/support?extensionTab=<owner>:resources`. Выбор сохраняет прочие
параметры и hash; работают Back/Forward и клавиатурная навигация вкладок.
После удаления или блокировки плагина недоступная вкладка возвращает базовый экран.

В карточке пользователя, вкладке «Действия», доступны
`admin.users.detail.tariff`, `.balance`, `.traffic-strategy`, `.premium-traffic`,
`.regular-traffic`, `.hwid`, `.traffic-grant`, `.squads`. Цель
`admin.users.detail.actions` добавляет самостоятельные карточки после базовых действий.
Условные карточки существуют при наличии соответствующих данных/подписки.

Для расширений, включаемых в сборку, экспортируйте `uiSlots` из модуля
`admin/sections/extensions/*.ts` как `AdminUiSlotDescriptor[]`; используйте тот же
`target`, `placement`, `order`, feature-поля и Svelte-компонент. Новые встроенные
границы добавляются через общий `AdminExtensionPoint` / `UserExtensionPoint`.
DOM-селекторы и внутренние классы не являются API плагинов.

## Порядок, конфликты, отказ и права

- `placement`: `before`, `after` (default), `replace`. Сортировка внутри группы:
  целый `order` от −10000 до 10000, затем `<owner>:<id>`; ноль сохраняется.
  `before`/`after` добавляют виды вокруг Core, `replace` заменяет содержимое указанной
  границы. Для изменения текста используйте локализацию; для изменения карточки —
  её явную замену. Плагин сам отвечает за действия и сохранение данных своего вида.
- Две активные замены одной цели не выбираются по случайному порядку пакетов:
  Core показывает сообщение о конфликте и исходный блок. Добавления сохраняются.
- Исходный блок доступен, пока replacement загружается. Ошибка импорта, mount или
  update пакетного вида возвращает Core. Один неисправный вид не ломает соседние.
  У встроенного Svelte-вида синхронные ошибки покрывает boundary; асинхронные
  операции собственного компонента требуют своего обработчика ошибок.
- `.cards`, старые additive-цели, `user.security.content`, `admin.plugins.content`
  и `admin.users.detail.actions` не допускают `replace`. Это сохраняет добавление
  карточек, доступ к восстановлению аккаунта и управлению неисправным пакетом.
- Идентификаторы вкладок, панелей и слотов runtime получают namespace владельца;
  два пакета могут использовать локальное `resources`. Существующие section ids и aliases
  не перекрывают Core. При новой регистрации удаляются прежние runtime-дескрипторы,
  aliases и styles; descriptor-only пакеты работают без `sections`.
- Видимость ЛК проходит `view_policy` и сохранённые `view:<id>` предпочтения.
  При ошибке policy вид скрывается. Admin feature-поля работают как у обычных
  вкладок; locked replacement не скрывает Core. Скрытый элемент не означает
  запрет серверной операции: каждый endpoint обязан проверить пользователя,
  владельца данных, админские права и текущую generation.
- Customer `props.context` содержит screen, subscription, ticketId и метаданные
  вида (`target`, `viewId`, `parent`). Admin slots получают `context.sectionId`,
  `context.target`, а карточки действий — снимки `context.user` и `context.userDetail`.
  Это входные снимки, не ORM, не store и не команда на изменение тарифа.
- Пользовательские и админские bundles/assets остаются раздельными и требуют
  соответствующей сессии. Доверенный JS не является sandbox. Ограничивайте CSS
  своим контейнером и очищайте timers, listeners и порталы в `unmountView`.
