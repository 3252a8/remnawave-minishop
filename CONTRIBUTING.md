# Контрибьютинг

Этот документ фиксирует архитектуру, соглашения и **проверяемые** гейты качества проекта.
Он написан для любого контрибьютора — человека или AI-агента. Главная идея:

> **Контракты — единственный источник правды, и они держатся на тулинге, а не на договорённости.**
> Типы, схемы и сгенерированные артефакты валят сборку при расхождении — поэтому ошибка
> всплывает локально или в CI, а не в проде. Сомневаешься — заставь машину это проверить.

Прочитай это один раз перед изменением кода. Большинство правил ниже защищены CI (раздел 1):
если следуешь гейтам, тебе сообщат, когда ты нарушишь правило.

---

## 1. Гейты качества — прогоняй локально перед пушем

CI (`.github/workflows/ci.yml`) прогоняет всё перечисленное; ничего не мёржится красным.

Удобная агрегирующая команда из корня репозитория:
```bash
make check
```

Та же полная проверка доступна без GNU `make`:
```bash
npm run check
```

Для быстрого локального smoke-прогона без `ruff format --check`, `mypy` и полного frontend `build`
можно использовать:
```bash
npm run check:quick
```

There is no mypy frontier: the whole repository is in scope — all backend packages, both
script roots (`backend/scripts`, `scripts`), and the whole `tests/` tree. The `type_ignore`
allowlist holds a single boundary-proven entry (`config/settings.py`: pydantic-settings
fills required fields from the environment, invisible to static analysis; the inline
comment at the call site carries the proof).

Явные команды ниже остаются источником правды для CI и ручной диагностики.

**Бэкенд** (из корня репозитория; `pytest.ini` задаёт `pythonpath = backend .`):
```bash
python -m pytest -q                 # полный прогон (в CI поднимаются Postgres + Redis; warnings-as-errors; branch-coverage ratchet: fail_under=53)
python -m ruff check .              # линт
python -m ruff format --check .     # формат
python -m mypy --explicit-package-bases backend/config backend/db backend/bot/infra \
  backend/bot/middlewares backend/bot/utils \
  backend/bot/plugins backend/bot/keyboards backend/bot/payment_providers backend/bot/services \
  backend/bot/handlers backend/bot/app/factories backend/bot/app/controllers backend/bot/app/web \
  backend/main_backend.py backend/main_worker.py backend/scripts scripts tests
```

Финальный набор ruff-семейств — `E, W, F, I, UP, B, ASYNC, DTZ, C4, SIM, PIE, PERF, RUF,
LOG, G, PLE, T10` (задан в `pyproject.toml` `[tool.ruff.lint]`); `per-file-ignores` нет,
поэтому нового lint-исключения по файлу завести нельзя. `pytest.ini` держит
`filterwarnings = error`: любой незапланированный warning валит прогон.

**Фронтенд** (`frontend/`):
```bash
npm run check        # eslint + svelte-check + prettier --check
npm run test         # Vitest unit-тесты helper'ов и store'ов
npm run build        # vite build должен проходить после type-only изменений
npm run test:e2e     # Playwright docs-demo smoke: webapp+админка, окна, вкладки, zero console errors
```

**У сгенерированных артефактов есть drift-guard — регенерируй, не правь руками:**
| Артефакт | Регенерация | Защищён |
| --- | --- | --- |
| `docs/openapi.json` | `PYTHONPATH=backend python -m bot.app.web.openapi` | `tests/contracts/test_openapi_artifact.py` |
| `docs-site/public/openapi.json` | `npm --prefix docs-site run sync:docs` | `npm run check:docs`, pre-commit, CI |
| `docs/architecture/events.md` | `PYTHONPATH=backend python -m bot.infra.event_catalog` | `tests/contracts/test_contract_docs_accuracy.py` |
| `frontend/src/lib/api/openapi.generated.ts` | `npm --prefix frontend run generate:api-types` | CI `git diff --exit-code` |
| demo settings manifest | `python scripts/export_settings_manifest.py` (+ prettier) | `tests/contracts/test_settings_manifest_demo_sync.py` |
| `backend/requirements.txt` | `python -m piptools compile --resolver=backtracking --no-emit-index-url --no-emit-trusted-host -o backend/requirements.txt backend/requirements.in` (Python 3.12) | CI install + `pip-audit` |

Меняешь контракт API — регенерируй `openapi.json` **и** `openapi.generated.ts`.

---

## 2. Золотые правила (без исключений)

- **Никогда не правь сгенерированный артефакт руками.** Запусти его генератор (раздел 1).
- **Никогда не редактируй, не переупорядочивай и не перенумеровывай существующую миграцию БД.**
  Миграции append-only и идемпотентны (раздел 5).
- **Никогда не глуши тайпчекер на своём коде.** Не `# type: ignore` / `any` ради компиляции —
  чини тип. `mypy` по всему бэкенду должен оставаться зелёным.
- **Никогда не ломай wire-контракты:** HTTP-конверт `{"ok": …}`, flat-dict payload'ы событий,
  сигнатуру подписчика плагина `(event_name, dict)`.
- **Фасады (`admin_api`, `subscription_webapp`, `subscription_service`) используем только для
  совместимости. Новый код имплементирует через конкретные внутренние модули (`*_impl`, domain,
  service/route modules) и не опирается на фасады как на дефолтный внутренний API; любые
  исключения фиксируем в контрактных тестах.
- **Весь first-party код фронтенда — TypeScript** (`.ts` / `<script lang="ts">`). Новые `.js`
  и `<script>` без `lang="ts"` в `frontend/src` запрещены архитектурными гейтами
  (`first_party_js`, `svelte_lang_ts` в `scripts/architecture_gates.json`); исключение — только
  сгенерированные артефакты из allowlist. Глобальный `checkJs` не включаем.
- **Не хардкодь пользовательский или админский текст.** Любая новая или изменённая видимая строка
  (бот, Web App, админка, email/уведомления, aria/placeholder/title) должна идти через локализацию
  и иметь минимум базовые варианты в `locales/ru.json` и `locales/en.json`. Fallback-строка в
  компоненте или helper'е — только страховка для разработки, а не замена ключа в базовых локалях.
- **Сначала декомпозиция, потом типизация** — см. раздел 5. Не типизируй god-файл «на месте».
- **Отличай «совместимость с другими ботами» (фича — оставить) от «остатков рефакторинга»
  (убрать)** — см. раздел 6.

---

## 3. Соглашения бэкенда

Бэкенд — рукописный `aiohttp` + `aiogram` + SQLAlchemy (async) + pydantic v2. **FastAPI нет** —
не вводи его. Обзор архитектуры: [docs/architecture.md](docs/architecture.md).

Пошаговые рецепты для типовых задач (добавить платёжного провайдера, доменное событие или
HTTP-эндпоинт) — [docs/development/how-to.md](docs/development/how-to.md); каждый заканчивается
прогоном гейтов раздела 1.

### 3.1 HTTP API (типизированные контракты)
- Роуты регистрируются явно в `setup_subscription_webapp_routes`
  (`bot/app/web/webapp/routes.py`) и `setup_admin_routes`
  (`bot/app/web/admin_api_impl/routes.py`). Плагины добавляют роуты в рантайме через
  `Plugin.setup_web`.
- **Тела запросов:** парси через `parse_body` / `parse_body_or_400`
  (`bot/app/web/request_parsing.py`) против `HttpBodyModel` — не возвращай сырой `_read_json`
  для новых эндпоинтов. `parse_body_or_400` чисто сужает тип для mypy.
- **Ответы:** собирай `HttpResponseModel` через явный classmethod `from_orm_*`, который читает
  **только уже загруженные скалярные атрибуты** (например `obj.__dict__.get("user")`).
  **Никогда не включай ORM-автоскан `from_attributes`** — он триггерит lazy-load после
  закрытия сессии. Оборачивай конвертом `_ok` / `_error`; имена/типы полей не меняй.
- **Регистрируй контракт каждого роута** в `bot/app/web/route_contracts.py`, чтобы он попал в
  `openapi.json`. Не-JSON роуты (CSV/бинарь/multipart) объявляют content-type, а не JSON-модель.
- Справочник HTTP: [docs/architecture/http-api.md](docs/architecture/http-api.md).

### 3.2 Доменные события (типизированные payload'ы)
- Одна pydantic-модель на событие в `bot/infra/event_payloads.py` (`extra="forbid"`). Публикуй
  через `events.emit_model(Model(...))`; сама шина остаётся dict-based, а `emit` **никогда не
  кидает исключений**.
- Payload'ы — **flat-dict из примитивов + ISO-8601 datetime**, никогда не ORM-объекты.
  Подписчики перечитывают богатые данные по id. Payload — это уведомление, не гарантия, что
  строка уже закоммичена.
- Добавил/изменил событие → обнови модель, регенерируй каталог событий.
- Каталог: [docs/architecture/events.md](docs/architecture/events.md).

### 3.3 Типобезопасность
- `mypy` покрывает весь бэкенд и контрактные тесты (`tests/contracts`) и должен оставаться
  зелёным. Новые backend-модули попадают в скоуп автоматически (по каталогам). Строгость
  поднимай помодульно через `[[tool.mypy.overrides]]`, а не глобальным `strict`.

### 3.4 Миграции
- Рукописный **идемпотентный** мигратор (пакет `db/migrator/`): интроспекция схемы, затем условный
  DDL (`IF NOT EXISTS`, проверки колонок). Применённые id трекаются в `schema_migrations`.
- **Append-only.** Добавляй новую миграцию; никогда не правь/переупорядочивай существующие.
  Цепочки плагинов неймспейснуты (`<plugin>.0001_*`).
- Совместимость импорта с других ботов (remnashop / старые сборки) живёт здесь намеренно —
  см. раздел 6.

### 3.5 Плагины
- Расширение через ABC `Plugin` + `PluginContext` (`bot/plugins/spec.py`), обнаруживаются через
  entry-point группу `minishop.plugins`. Хуки: `setup`, `setup_bot`, `setup_web`,
  `worker_tasks`, `queue_handlers`, `migrations`, `locales_dir`, `entitlements_provider`.
- Plugin API — это публичная поверхность расширения, держи её стабильной. Подписчики получают
  сырой `(event_name, dict)`; типизированные модели — additive-удобство, не обязательный
  интерфейс.
- Контракт: [docs/development/plugin-contract.md](docs/development/plugin-contract.md),
  [docs/development/plugins.md](docs/development/plugins.md).

---

## 4. Соглашения фронтенда

Svelte + Vite. API-клиент **типизирован из OpenAPI-спека**.

- Зови API через типизированный клиент `lib/webapp/publicApi.ts` (`createApiClient`):
  `api("/api/...")` выводит ответ из `paths`; `publicApi` выводит тело запроса. **Используй
  литеральные строки путей** — переменная расширяет тип и теряет инференс. Распаковывай конверт
  `{ok,…}` через `unwrap(...)`.
- `openapi.generated.ts` генерируется из `docs/openapi.json` и **защищён drift-guard в CI** —
  регенерируй при любом изменении контракта на бэке.
- Весь first-party код — TypeScript: новые модули пиши в `.ts`, компоненты — с
  `<script lang="ts">`; типизируй сторы (`writable<State>`), чтобы изменение контракта на бэке
  валило `check:svelte` ровно у потребителя. Архитектурные гейты (`first_party_js`,
  `svelte_lang_ts`) не пропустят новый нетипизированный файл. **Не** включай глобальный
  `checkJs` — он не нужен, когда JS-файлов нет.
- Для UI-текста используй `t(...)`/`at(...)` и добавляй реальные ключи в обе базовые локали:
  `locales/ru.json` и `locales/en.json`. В админке `at("tariff_title", ...)` ищет
  `admin_tariff_title`, поэтому проверяй итоговое имя ключа. Если добавляешь новую группу строк,
  добавь узкий тест или существующий locale guard, чтобы ключи не остались только fallback'ами.
- Frontend first-party Svelte code is Svelte 5 runes-only. Do not reintroduce `export let`,
  `$:`, `$$props`, `$$restProps`, `<slot>`, `<svelte:component>`, `createEventDispatcher`, or
  class API `$set`. `frontend/vite.config.mjs` and `frontend/vitest.config.mjs` enable
  `runes: true` for `frontend/src`, while `npm run check:runes`, `svelte-check`, builds, and
  Vitest fail if legacy syntax comes back.

---

## 5. Принципы рефакторинга

- **Сначала декомпозиция, потом типизация.** Для любого крупного/запутанного файла выноси
  связные срезы в маленькие типизированные модули, а не типизируй на месте — одно усилие, два
  выигрыша (типы + размер), без двойной работы. Цель — **ни одного модуля > ~1000 строк** без
  задокументированной причины. Единственная принятая причина — сгенерированный артефакт:
  `module_size.allowlist` в `scripts/architecture_gates.json` держит только выходы генераторов
  (`templates/*.js`, `openapi.generated.ts`, `demoDataset.js`), и это зафиксировано тестом
  `tests/contracts/test_architecture_gates.py::test_module_size_allowlist_is_generated_artifacts_only`.
  Разросшийся рукописный файл — режь, а не вноси в allowlist.
- **Ловушка monkeypatch / re-export.** Тесты часто делают `monkeypatch.setattr(module, "name", …)`.
  Перенос `name` в подмодуль с ре-экспортом восстанавливает *импорты*, но **не** семантику
  monkeypatch — пропатченная и вызываемая копии расходятся, и патч молча не срабатывает
  (зелёно-но-неверно). Прежде чем резать шов, `grep tests/` на патч-цель; если пропатченный
  символ и его вызов расходятся по модулям — **сначала обнови тест патчить новый модуль**
  (test-first), потом переноси. Всегда проверяй, что фейк реально вызывается.
- **Раскладка провайдеров:** один провайдер = один пакет с единым интерфейсом
  (`__init__` экспортит `SPEC` + фабричные точки входа; `config` + `service` есть всегда;
  `webhook`/`callbacks`/`payment_methods`/`router` — только когда существенны, не плоди
  5-строчный webhook-модуль). Строки `id` / `provider_key` / webhook-path не меняй (они
  персистятся и настроены в панели).
- **Гигиена импортов:** после разбиения прогони `ruff check --fix --select F401,F811` — не
  копипасть исходный блок импортов. Повторять фреймворк-импорты в модулях — нормально; **не**
  централизуй их за star-import общим модулем (тот самый антипаттерн, который мы убрали).

---

## 6. Что намеренно, а что removable

**Оставить — это фичи, а не легаси:**
- Кросс-бот **совместимость миграций** (`MIGRATION_REMNASHOP_*`, `backend/scripts/import_legacy.py`,
  `legacy_referral_codes` / `legacy_import_mappings`, reconcile-миграции). Это и есть «миграция
  с другого бота» + install wizard (`scripts/install.sh`). Порядок применяемых миграций
  (ядро + плагинные, неймспейснутые) пинуется снапшот-тестом
  `tests/contracts/test_migration_chain_snapshot.py`: любой reorder/renumber падает в CI, а не
  только на ревью, поэтому append-only-правило теперь машинно-проверяемо.
- **Deprecated env-алиасы** в `config/settings.py` (`ignore_deprecated_*`) — защищают
  существующие деплои. Удалять только с окном депрекации.
- Внутрипакетные общие хабы `_runtime.py` — load-bearing, не мёртвый код.

**Убрать (сначала проверь импортёров / патч-цели):** ре-экспорт-шимы рефактора, deprecated-хелперы
с пометкой «kept for compatibility» без вызовов, сериализаторы, осиротевшие после перехода на
типизированные контракты.

---

## 7. Ключевые решения («почему»)

- **Рукописные типизированные контракты вместо смены фреймворка.** Остались на aiohttp и добавили
  pydantic request/response + модели событий, затем сгенерировали OpenAPI из живого роутера.
  Резон: enforce-ить контракт там, где код уже работает, без переписывания.
- **mypy/svelte-check как рачеты.** Покрытие типами только растёт и должно оставаться зелёным;
  оно вскрыло реальные латентные баги (например aiogram `Message | InaccessibleMessage`).
- **Сначала декомпозиция, потом типизация.** God-файлы сначала режутся на сфокусированные модули;
  типизировать маленькие единицы дешевле и безопаснее, чем запутанные большие.
- **Сгенерированные артефакты + drift-guards** (`openapi.json`, `events.md`, `openapi.generated.ts`)
  делают контракт фронт↔бэк машинопроверяемым через границу.

---

## 8. Рабочий процесс

- Ветка от `dev` (или как укажет мейнтейнер); PR'ы целятся в `dev`/`main` и должны проходить все
  гейты раздела 1.
- **Сообщения коммитов:** префиксы Conventional Commits (`fix:`, `feat:`, `refactor:`, `chore:`,
  `docs:`, `ci:`, `build:`, `perf:`, `test:`, `style:`), на английском. Трейлер `Co-Authored-By`
  **не добавлять**.
- **`CHANGELOG.md` в проекте нет намеренно — не создавать и не вести.** История изменений живёт
  в Conventional Commits и описаниях PR; ручной журнал изменений дублирует их и мгновенно
  устаревает.
- Одно связное изменение на коммит; для рефакторов предпочитай move-only диффы для ревью.
- После любого изменения контракта регенерируй затронутые артефакты (раздел 1) в том же изменении.
- Compatibility facades (`admin_api`, `subscription_webapp`, `subscription_service`) are compatibility-only layers.
  Implementation code must import concrete `*_impl`/domain modules first; avoid adding new first-party dependencies on facade modules
  unless a public compatibility contract requires it.
