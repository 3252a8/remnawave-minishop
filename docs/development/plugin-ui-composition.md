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

Старые `user.home.cards`, `user.profile.actions`, `user.subscription.actions`,
`user.install.blocks` сохраняют прежнее добавление после соответствующего экрана.
Карточная цель существует только при рендере её встроенного контейнера: например,
`user.home.traffic` относится к обычному режиму активной подписки. Если вклад должен
показываться независимо от режима или подписки, используйте `.cards` или `.content`.
Неизвестная цель ЛК отклоняется при установке.

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
