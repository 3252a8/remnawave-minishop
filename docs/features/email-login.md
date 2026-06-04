# Вход по email

Email-вход позволяет пользователю зарегистрироваться или войти в Mini App без Telegram. Пользователь вводит email, получает одноразовый код и может подтвердить вход кодом или magic link из письма. После входа email можно связать с Telegram-аккаунтом в настройках профиля.

Аккаунты только с email не получают права администратора: админка проверяет Telegram ID из `ADMIN_IDS`.

## Когда форма появляется

Кнопка входа по email показывается только если заполнены все обязательные SMTP-настройки:

```ini
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USERNAME=<smtp-login>
SMTP_PASSWORD=<smtp-password-or-api-key>
SMTP_FROM_EMAIL=no-reply@domain.com
```

Если хотя бы одно из этих полей пустое, backend вернет `email_auth_enabled=false` в bootstrap, а frontend скроет email-login.

Для magic link также нужен корректный `SUBSCRIPTION_MINI_APP_URL`, потому что ссылка в письме строится на его основе.

## SMTP-настройка

Типовой пример:

```ini
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_FALLBACK_PORTS=2525,465
SMTP_TIMEOUT_SECONDS=30
SMTP_STARTTLS=True
SMTP_USE_SSL=False
SMTP_USERNAME=<smtp-login>
SMTP_PASSWORD=<smtp-password-or-api-key>
SMTP_FROM_EMAIL=no-reply@domain.com
SMTP_FROM_NAME=Remnawave Minishop

EMAIL_CODE_TTL_SECONDS=600
EMAIL_CODE_RESEND_SECONDS=60
EMAIL_CODE_MAX_ATTEMPTS=5
BRUTE_FORCE_MAX_FAILURES=5
BRUTE_FORCE_WINDOW_SECONDS=900
BRUTE_FORCE_LOCK_SECONDS=900
```

## Брендинг писем

HTML-письма используют тот же бренд, что и Mini App: название из `WEBAPP_TITLE`, accent из внешнего вида и логотип из раздела **Внешний вид**. Если логотип загружен через админку файлом, backend прикладывает его к письму как inline image (`cid:webapp-logo`), поэтому получателю не нужен доступ к внутреннему `/webapp-uploaded-logo/...`.

Если в качестве логотипа задан публичный `https://` URL, письмо использует его как обычный внешний `<img>`. В этом режиме некоторые почтовые клиенты могут скрыть картинку, пока получатель не разрешит загрузку внешних изображений.

Для Brevo обычно подходит порт `587` с STARTTLS. Если основной порт недоступен, приложение пробует порты из `SMTP_FALLBACK_PORTS`; порт `465` используется через SSL wrapper автоматически.

`SMTP_FROM_EMAIL` должен быть подтвержден у SMTP-провайдера, иначе письмо часто отклоняется или попадает в спам. `SMTP_FROM_NAME` можно оставить пустым, тогда используется название Web App.

Полный справочник переменных: [SMTP и вход по email](../configuration/env-vars.md#smtp-и-вход-по-email).

## Как работает вход

1. Пользователь вводит email в форме входа.
2. Backend проверяет rate limit и создает одноразовый код.
3. Письмо отправляется через SMTP. Если `SUBSCRIPTION_MINI_APP_URL` валиден, в письме также есть magic link.
4. Пользователь вводит код в Mini App или открывает magic link.
5. Backend создает нового email-пользователя или находит существующего по email.
6. Если в URL был referral-параметр, он применяется к новой или существующей записи.
7. Пользователь получает Web App-сессию.

Коды хранятся в базе в хешированном виде, устаревают по `EMAIL_CODE_TTL_SECONDS`, повторная отправка ограничена `EMAIL_CODE_RESEND_SECONDS`, а количество попыток ввода ограничено `EMAIL_CODE_MAX_ATTEMPTS` и общими brute-force настройками.

## Парольный вход

После подтверждения email пользователь может задать пароль в настройках профиля. Пароль хранится как PBKDF2-SHA256 hash с солью.

После установки пароля доступен путь:

```text
https://app.domain.com/login/password
```

Если парольный вход не удался, frontend предлагает fallback на обычный email-код. Установка или изменение пароля тоже подтверждается email-кодом.

## Привязка аккаунтов

В настройках профиля пользователь может:

- привязать email к Telegram-аккаунту через код;
- привязать Telegram к email-аккаунту через Telegram Mini Apps `initData` или Telegram OAuth;
- задать или сменить пароль для email-входа.

Если email уже принадлежит другой записи, backend выполняет безопасное объединение по существующим правилам аккаунтов и инвалидирует старые Web App-кеши.

## Проверка после настройки

1. Перезапустите backend/frontend после изменения `.env`.
2. Откройте `https://app.domain.com/` вне Telegram.
3. Убедитесь, что форма email-входа видна.
4. Запросите код на тестовый адрес.
5. Проверьте письмо, magic link и ручной ввод 6-значного кода.
6. Проверьте логи backend, если письмо не пришло:

```bash
docker compose logs -f backend
```

## Частые ошибки

- Форма email не видна: не заполнены `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` или `SMTP_FROM_EMAIL`.
- Письмо не отправляется: проверьте порт, STARTTLS/SSL режим, SMTP login/API key и подтверждение отправителя.
- Magic link ведет не туда: исправьте `SUBSCRIPTION_MINI_APP_URL`, он должен быть публичным HTTPS URL Mini App без `/api` и `/auth`.
- Код сразу устаревает: проверьте `EMAIL_CODE_TTL_SECONDS` и время на сервере.
- Пользователь получает `rate_limited`: подождите `EMAIL_CODE_RESEND_SECONDS` или проверьте brute-force настройки.

Email-уведомления поддержки, платежей и жизненного цикла подписки используют тот же SMTP-контур. Сценарий поддержки описан в [разделе тикетов](support.md), сводка по каналам - в разделе [уведомления](notifications.md).
