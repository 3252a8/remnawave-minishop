# Рецепты для контрибьюторов

Пошаговые рецепты для трёх самых частых изменений. Каждый рецепт заканчивается
одинаково: **прогоните гейты** (CONTRIBUTING §1) и дайте контрактному тесту /
drift-guard подтвердить, что всё связано правильно.

Это рецепты, а не справочник. Справочник лежит здесь:

- [docs/architecture.md](../architecture.md) — обзор системы
- [docs/architecture/http-api.md](../architecture/http-api.md) — справочник HTTP-контракта
- [docs/architecture/events.md](../architecture/events.md) — сгенерированный каталог событий
- [docs/development/plugins.md](plugins.md), [plugin-contract.md](plugin-contract.md) — API плагинов
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — соглашения и неприкосновенные правила

---

## Добавить платёжного провайдера

Провайдер — это один пакет в `backend/bot/payment_providers/<name>/`. Файл пакета
`__init__.py` — это **тонкий фасад** (явный `__all__`, без реэкспорта
stdlib/фреймворка); реализация живёт в сфокусированных модулях. Тест на
конформность (`tests/providers/test_provider_conformance.py`) — это ваш чеклист:
он падает с конкретным сообщением, пока каждый пункт ниже не выполнен.

1. **Создайте `config.py`** — подкласс `ProviderEnvConfig` со своим `env_prefix`
   (например, `MYPAY_`) и полями, плюс опциональную presentation-модель. Модуль
   провайдера — единственный источник истины для своих env-переменных; глобальный
   `Settings` править **не нужно**.

2. **Создайте `service.py`** — класс `Service`. Для провайдера с hosted-link
   наследуйтесь от `HttpClientMixin`; реализуйте `create_payment(...)`,
   `try_reuse_pending_payment(...)`, подпись и (если он принимает колбэки)
   `webhook_route(self, request)`. Держите границу безопасности явной:
   отключён → `503`, неверная подпись / неавторизованный IP → `403`, платёж не
   найден → `404`.

3. **Свяжите поток callback/webapp.** Если провайдер — это *единообразный
   hosted-link редирект*, оркестрацию руками писать не нужно: объявите
   `LinkPaymentDescriptor` (`shared/link_flow.py`) и делегируйте:

   ```python
   async def create_webapp_payment(ctx):       # SPEC.create_webapp_payment
       return await run_webapp_payment(_DESCRIPTOR, ctx)

   async def reuse_webapp_payment(ctx, payment):
       return await run_reuse_webapp_payment(_DESCRIPTOR, ctx, payment)

   @router.callback_query(F.data.startswith("pay_mypay:"))
   async def pay_mypay_callback_handler(callback, settings, i18n_data, mypay_service, session):
       await run_callback_payment(_DESCRIPTOR, callback, settings, i18n_data, mypay_service, session)
   ```

   Смотрите `severpay`/`lava`/`heleket` как образец. Если тайминг колбэка,
   семантика инвойса или контракт create-вызова действительно отличаются —
   оставьте поток bespoke и добавьте имя провайдера в `LINKFLOW_BESPOKE` в тесте
   на конформность с однострочной причиной, называющей расхождение; не подгоняйте
   движок под исключение.

4. **Объявите `SPEC`** (`PaymentProviderSpec`) со стабильными `id`,
   `provider_key`, `pending_status`, webhook-путём, точками входа и manifest-полями.
   **Строки `id` / `provider_key` / webhook-path персистятся** — выберите их один
   раз и никогда не переименовывайте.

5. **Зарегистрируйте провайдера** в
   `backend/bot/payment_providers/registry.py` (`PAYMENT_PROVIDER_SPECS`).

6. **Держите `__init__.py` тонким фасадом** — реэкспортируйте только `SPEC`
   (+ варианты specs), классы `Service`/`Config`/`Presentation`, `create_service`,
   webapp-фабрики, webhook-маршрут, callback-обработчик и `router`. Объявите явный
   `__all__`. Ratchet на гигиену фасадов отвергает протёкшие
   stdlib/фреймворк/type-символы.

7. **Покройте тестами.** Добавьте тесты провайдера рядом с остальными; патчите
   внутренние символы (`payment_dal`, `finalize_successful_payment`, …) на
   **подмодуле `.service`**, а не через фасад (CONTRIBUTING §5 — патч фасада молча
   ничего не делает).

8. **Прогоните гейты.** `python -m pytest tests/providers -q` — тест на
   конформность подскажет, должны ли вы ещё добавить descriptor/bespoke-причину,
   webhook-профиль или поправить фасад. Затем полный `make check`.

---

## Добавить доменное событие

События — это плоские dict-уведомления на внутрипроцессной шине. Шина никогда не
кидает исключений и намеренно не валидируется; расхождение ловит типизированная
модель.

1. **Добавьте payload-модель** в `backend/bot/infra/event_payloads.py` — подкласс
   `EventPayload` (он задаёт `extra="forbid"`), объявите `EVENT_NAME` и типизируйте
   каждое поле. Для меток времени используйте `datetime` (сериализуется в ISO-8601
   автоматически) и `Optional[...] = None`, где `None` — валидное значение.
   **Payload'ы — только примитивы, никогда не ORM-объекты.** Подписчики
   перечитывают богатые данные по id.

2. **Опубликуйте** в источнике: `await events.emit_model(MyEvent(...))`. `emit`
   никогда не кидает исключений, поэтому падение подписчика не может сломать
   вызывающий код.

3. **Подпишитесь** (опционально) — подписчики получают сырую сигнатуру
   `(event_name: str, payload: dict)`; этот контракт заморожен, типизированная
   модель — additive-удобство.

4. **Регенерируйте каталог** в том же коммите:
   `PYTHONPATH=backend python -m bot.infra.event_catalog` →
   `docs/architecture/events.md`. Никогда не правьте его руками.

5. **Прогоните гейты.** `tests/contracts/test_domain_events.py` и тест на точность
   документации падают, если модель и каталог разошлись.

---

## Добавить HTTP-эндпоинт

API — это рукописный `aiohttp` с типизированными request/response-моделями и
сгенерированным OpenAPI-контрактом. **FastAPI нет** — не вводите его. Конверт
`{"ok": …}` — это wire-инвариант.

1. **Зарегистрируйте маршрут** явно в `setup_subscription_webapp_routes`
   (`bot/app/web/webapp/routes.py`) или `setup_admin_routes`
   (`bot/app/web/admin_api_impl/routes.py`). Плагины добавляют маршруты в рантайме
   через `Plugin.setup_web`.

2. **Распарсите тело** против `HttpBodyModel` через
   `parse_body_or_400(request, MyRequest)` (`bot/app/web/request_parsing.py`) —
   не `_read_json` для новых эндпоинтов.

3. **Соберите ответ** через подкласс `HttpResponseModel` и явный classmethod
   `from_orm_*`, который читает **только уже загруженные скалярные атрибуты**
   (например `obj.__dict__.get("field")`). **Никогда** не включайте автоскан
   `from_attributes` — он триггерит lazy-load после закрытия сессии. Оборачивайте
   результат конвертом `_ok(...)` / `_error(...)`.

4. **Зарегистрируйте контракт** в `bot/app/web/route_contracts.py`, чтобы маршрут
   попал в `openapi.json`. Не-JSON маршруты (CSV/бинарь/multipart) объявляют
   content-type вместо JSON-модели.

5. **Регенерируйте оба артефакта** в том же коммите:
   `PYTHONPATH=backend python -m bot.app.web.openapi` (→ `docs/openapi.json`),
   затем `npm --prefix frontend run generate:api-types`
   (→ `frontend/src/lib/api/openapi.generated.ts`).

6. **Потребляйте на фронтенде** через типизированный клиент
   (`lib/webapp/publicApi.ts`): зовите `api("/api/...")` с **литеральной** строкой
   пути и распаковывайте конверт через `unwrap(...)`.

7. **Прогоните гейты.** `tests/test_openapi_artifact.py` и frontend drift-guard
   (`git diff --exit-code` по сгенерированным типам) падают, если контракт и
   артефакты разошлись.
