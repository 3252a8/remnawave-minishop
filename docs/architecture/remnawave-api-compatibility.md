# Совместимость с API Remnawave

<!-- Сгенерировано командой `PYTHONPATH=backend python -m bot.services.panel_api_catalog`. -->

Этот каталог формируется из того же типизированного реестра, который использует
клиент во время работы. Не редактируйте файл вручную: обновите
`panel_api_contracts.py` или `remnawave_support.json`, запустите генератор и
контрактные тесты.

## Политика поддержки

Core одновременно сертифицирует 2 поколения API:
текущее и одно поддерживаемое. Сертификация относится к точным версиям; новый
патч- или минорный релиз известного поколения помечается как **непроверенный**, пока
live-проверки CI не завершатся успешно. Об удалении поддержки предупреждают минимум
за 90 дней и за
2 выпуска Core; само удаление возможно
только в несовместимом выпуске Core.

Неизвестные будущие мажорные версии Remnawave работают в режиме максимальной
совместимости: существующие операции чтения и записи остаются доступны, поскольку
смена мажорной версии не обязательно меняет API. До сертификации такие версии
помечаются как непроверенные, а резервные варианты эндпоинтов и возможностей
ограничивают предположения клиента. Если эндпоинт метаданных временно недоступен, Core
сохраняет этот режим и опирается на наблюдаемые идентификаторы и эндпоинты вместо
кеширования ошибочного результата определения версии.

## Сертифицированные версии

| Статус | Поколение API | Точные версии | Пресет | Возможности | Покрытие | Источник |
| --- | --- | --- | --- | --- | --- | --- |
| текущая | rw3-numeric-user-id | 3.4.3, 3.4.2, 3.4.1, 3.3.2, 3.3.0, 3.2.3, 3.2.1, 3.2.0, 3.1.0, 3.0.0 | 3.4.3 | numeric-user-ids, user-stream, user-stream-filters, targeted-squad-bulk, connections-drop, hwid-user-id-selector, empty-success-body, multi-node-usage, multi-node-top-users, bulk-squad-update, user-tag | fixture, live-read, live-write, upgrade | [примечания к выпуску](https://github.com/remnawave/backend/releases/tag/3.4.3) |
| поддерживаемая | rw2-uuid-user-id | 2.8.1 | 2.8.1 | multi-node-top-users, bulk-squad-update, user-tag | fixture, live-read, live-write, upgrade | [примечания к выпуску](https://f.docs.rw/t/topic/178) |

Исторические пресеты остаются полезными для ручной диагностики, но не
поддерживаются и не запускаются в матрице сертификации:

- `2.8.0` — Исторический пресет для ручной диагностики; не входит в сертифицированную матрицу CI.
- `2.7.4` — Исторический пресет для ручной диагностики; не входит в сертифицированную матрицу CI.

## Исходящие операции API

В версии 2.8.1 `{userRef}` — это UUID пользователя, а начиная с 3.0.0 — десятичная
запись числового идентификатора. Остальные UUID (узлов, сквадов, хостов и
подписок) остаются UUID.

| Операция | Метод | Шаблон пути | Поколения | Успешные коды | Ответ | Совместимость | Покрытие |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `system.metadata` | GET | `/system/metadata` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильный запрос версии; сбой не считается результатом проверки возможности. | unit, live-read |
| `users.stream` | GET | `/users/stream` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | В 3.x каноническим источником служит поток с курсором и фильтрами поиска; поток 2.8 может возвращать UUID пользователей или игнорировать новые фильтры, поэтому Core проверяет результаты. | unit, live-read, upgrade |
| `users.list` | GET | `/users` | rw2-uuid-user-id | 200 | JSON-конверт с полем `response` | Устаревшая offset-пагинация используется, когда поток отсутствует или работает с UUID. | unit, live-read |
| `users.get` | GET | `/users/{userRef}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | В 2.8.1 {userRef} — UUID, а в 3.x — числовой идентификатор. | unit, live-read, upgrade |
| `users.lookup.telegram` | GET | `/users/by-telegram-id/{telegramId}` | rw2-uuid-user-id | 200 | JSON-конверт с полем `response` | В 3.x вместо этого используется `/users/stream?telegramId=...`. | unit, live-read |
| `users.lookup.username` | GET | `/users/by-username/{username}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Маршрут поиска по username остаётся стабильным до 3.4.3 включительно; начиная с 3.1 отсутствие пользователя возвращается как 404/A063. | unit, live-read |
| `users.lookup.email` | GET | `/users/by-email/{email}` | rw2-uuid-user-id | 200 | JSON-конверт с полем `response` | В 3.x вместо этого используется `/users/stream?email=...`. | unit, live-read |
| `users.create` | POST | `/users` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 201 | JSON-конверт с полем `response` | Core не отправляет UUID пользователя, переданный вызывающей стороной; 3.x возвращает числовой идентификатор. | unit, live-write |
| `users.update` | PATCH | `/users` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | Поле селектора — uuid в 2.8.1 и целочисленный id в 3.x. | unit, live-write |
| `users.bulk-update-squads` | POST | `/users/bulk/update-squads` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | Точное состояние сквадов обновляется пакетами по 500 пользователей. В 2.8.1 UUID передаются в uuids, а ответ содержит affectedRows; в 3.x передаются числовые userIds и возвращается 204. Для пустого целевого состояния используется PATCH каждого пользователя, потому что 3.0.0 возвращает A088/500. | unit, live-write |
| `users.status` | POST | `/users/{userRef}/actions/{enable\|disable}` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | Идентификатор в пути соответствует поколению UUID/числового id. | unit, live-write |
| `users.connections.drop-v2` | POST | `/ip-control/drop-connections` | rw2-uuid-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | В теле запроса 2.8 пользователи выбираются через userUuids. | unit, live-write |
| `users.connections.drop-v3` | POST | `/connections/drop` | rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | В теле запроса 3.x пользователи выбираются по числовым userIds. | unit, live-write |
| `users.delete` | DELETE | `/users/{userRef}` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | 404 для отсутствующей сущности считается идемпотентным успехом; отсутствие самого маршрута обрабатывается отдельно. | unit, live-write |
| `users.revoke` | POST | `/users/{userRef}/actions/revoke` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | Идентификатор в пути соответствует поколению UUID/числового id. | unit, live-write |
| `users.reset-traffic` | POST | `/users/{userRef}/actions/reset-traffic` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | Идентификатор в пути соответствует поколению UUID/числового id. | unit, live-write |
| `subscription.config.resolved` | GET | `/subscriptions/subpage-config/{shortUuid}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | GET намеренно передаёт requestHeaders в JSON-теле, как требует upstream. | unit, live-read |
| `subscription-page-config.list` | GET | `/subscription-page-configs` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `subscription-page-config.get` | GET | `/subscription-page-configs/{uuid}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `external-squads.get` | GET | `/external-squads/{uuid}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `hwid.devices.get` | GET | `/hwid/devices/{userRef}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | userRef в пути — UUID в 2.8.1 и числовой id в 3.x. | unit, live-read |
| `hwid.devices.delete` | POST | `/hwid/devices/delete` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | Селектор тела запроса — userUuid в 2.8.1 и userId в 3.x. | unit, live-write |
| `hwid.devices.stats` | GET | `/hwid/devices/stats` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `hwid.devices.top-users` | GET | `/hwid/devices/top-users` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `nodes.restart` | POST | `/nodes/{uuid}/actions/restart` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | Идентификаторы узлов остаются UUID в 3.x. | unit |
| `nodes.restart-all` | POST | `/nodes/actions/restart-all` | rw2-uuid-user-id, rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | Не запускается в live CI, потому что прерывает работу всех зарегистрированных узлов. | unit |
| `nodes.list` | GET | `/nodes` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `nodes.stats` | GET | `/system/stats/nodes` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `system.stats` | GET | `/system/stats` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `system.stats.bandwidth` | GET | `/system/stats/bandwidth` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `bandwidth.nodes` | GET | `/bandwidth-stats/nodes` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `bandwidth.users` | GET | `/bandwidth-stats/users/{userRef}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | userRef в пути — UUID в 2.8.1 и числовой id в 3.x. | unit, live-read |
| `bandwidth.node-users` | GET | `/bandwidth-stats/nodes/{nodeUuid}/users` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `bandwidth.nodes-users` | POST | `/bandwidth-stats/nodes/users` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Совместимый с 2.8.1 агрегированный запрос top-users для набора узлов; прежде чем считать отсутствующих пользователей нулевыми, Core проверяет достижение topUsersLimit. | unit, live-read |
| `bandwidth.nodes-usage` | POST | `/bandwidth-stats/nodes/usage` | rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | 3.x возвращает числовые id пользователей и итоги по каждому запрошенному узлу. Снимки потребления обновляются не чаще периода агрегации upstream. | unit, live-read |
| `internal-squads.list` | GET | `/internal-squads` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `internal-squads.get` | GET | `/internal-squads/{uuid}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |
| `internal-squads.nodes` | GET | `/internal-squads/{uuid}/{accessible-nodes\|nodes}` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Core пробует оба варианта маршрута upstream и проверяет форму ответа. | unit, live-read |
| `internal-squads.add-users` | POST | `/internal-squads/{uuid}/bulk-actions/add-many-users` | rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | В 3.x целевая пакетная операция с числовыми id выполняется блоками по 1000. В 2.8.1 похожий маршрут add-users применяется ко всем пользователям, поэтому Core обновляет указанных пользователей через PATCH. | unit, live-write |
| `internal-squads.remove-users` | DELETE | `/internal-squads/{uuid}/bulk-actions/remove-many-users` | rw3-numeric-user-id | 200, 202, 204 | JSON-конверт с полем `response`; пустое тело ответа 2xx считается успешным результатом | В 3.x целевая пакетная операция с числовыми id выполняется блоками по 1000; в 2.8.1 используется PATCH каждого пользователя. | unit, live-write |
| `hosts.list` | GET | `/hosts` | rw2-uuid-user-id, rw3-numeric-user-id | 200 | JSON-конверт с полем `response` | Стабильно для всех сертифицированных поколений API. | unit, live-read |

## Входящие вебхуки

| Событие | Поколения | Обработка идентификатора | Поведение Core | Покрытие |
| --- | --- | --- | --- | --- |
| user.expires_in_72_hours / 48_hours / 24_hours | rw2-uuid-user-id, rw3-numeric-user-id | user.uuid в 2.8.1; в 3.x user.id нормализуется во внутренний псевдоним uuid | Уведомление об окончании подписки и необязательная обработка автопродления. | unit |
| user.expiration | rw2-uuid-user-id, rw3-numeric-user-id | объект user вместе с meta.expirationHours | Событие совместимости сопоставляется с этапами уведомлений до и после окончания. | unit |
| user.expired / user.expired_24_hours_ago | rw2-uuid-user-id, rw3-numeric-user-id | нормализованный идентификатор пользователя | Уведомление об истёкшей подписке с подавлением устаревших данных о подписке. | unit |
| torrent_blocker.report | rw2-uuid-user-id, rw3-numeric-user-id | типизированное тело torrent-blocker; идентификатор пользователя определяется отдельно | Типизированное уведомление безопасности; некорректные или слишком большие тела отклоняются. | unit |
| прочие события (например, user.modified) | rw2-uuid-user-id, rw3-numeric-user-id | нормализованный идентификатор пользователя при наличии объекта user | Публикуются в шину событий Core и плагинов, но не используются для уведомлений жизненного цикла. | unit |

## Сертифицированные обновления

| Откуда | Куда | Стратегия | Проверка |
| --- | --- | --- | --- |
| 2.8.1 | 3.4.3 | с сохранением базы панели | `tests/qa/test_remnawave_upgrade.py` |

## Правила совместимости и особые случаи

- Результат успешного определения версии панели кешируется на пять минут. Ошибки
  не кешируются, поэтому гонки при запуске и временные сбои авторизации устраняются
  автоматически.
- Пользователи 3.x нормализуются на границе: числовой `id` также доступен внутри
  системы как строковый десятичный псевдоним `uuid`. Это намеренно сохраняет
  исторические столбцы БД и имена методов сервисов при обновлении панели на месте.
- После определения поколения запросы, относящиеся к пользователю, локально
  отклоняют идентификаторы другого поколения. Это предотвращает поток ошибок
  валидации 3.x и не позволяет принять устаревший UUID за удалённого пользователя.
- Фоновая синхронизация тарифов отложенно перепривязывает устаревшие UUID 2.8 по
  Telegram, email или детерминированному username до деактивации подписки.
  Неудачный или неоднозначный поиск никогда не создаёт дубликат пользователя.
- В 2.8.1 используются offset-пагинация `/users` и маршруты поиска по UUID. В 3.x
  используются поток с курсором и его фильтры. Перед запоминанием возможности Core
  проверяет форму ответа.
- Ответы об отсутствии пользователя A025, A062, A063 и обычный 404 нормализуются
  в пустой результат поиска. Сначала обрабатывается 404 отсутствующего маршрута,
  чтобы при обновлении 2.8 до 3.x Core переключился на фильтры потока без перезапуска.
- Пустые ответы 202/204 принимаются для операций изменения, где это предусмотрено
  контрактом; непустой некорректный JSON с кодом 2xx остаётся ошибкой протокола.
- В 2.8.1 маршрут сквада `add-users` означает всех пользователей. Core не вызывает
  его для целевого запроса, а обновляет каждого указанного UUID-пользователя через
  PATCH. В 3.x используются пакетные запросы с числовыми идентификаторами.
- В логах используются метки реестра вместо сырых путей, поэтому идентификаторы из
  сегментов маршрута и строки запроса не становятся метками логов и метрик.

## Чеклист для нового выпуска Remnawave

1. Изучите изменения выпуска и API upstream и определите поколение API. Будущие
   мажорные версии остаются в режиме максимальной совместимости, но не считаются
   сертифицированными без проверок на живом стенде.
2. Добавьте или обновите точную запись в `remnawave_support.json` и пресет
   dev-стенда. Явно отделяйте исторические пресеты от матрицы сертификации.
3. Обновите все затронутые контракты операций, адаптеры совместимости,
   нормализаторы вебхуков, фикстуры версий и задачи проверки сертифицированных
   версий на живом стенде.
4. Запустите smoke-тесты чтения и записи для текущей и поддерживаемой версий. При
   смене поколения также выполните обновление с той же базой данных и проверьте
   сохранённые идентификаторы пользователей после синхронизации.
5. Перегенерируйте этот каталог и публичные артефакты API, затем запустите все
   проверки бэкенда и фронтенда.
6. Чтобы прекратить поддержку поколения, объявите об устаревании на весь срок
   политики, удалите поддержку только в несовместимом выпуске Core и переведите
   пресеты в исторический статус.

Дата проверки манифеста: `2026-09-12`.
