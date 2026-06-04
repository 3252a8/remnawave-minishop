# Демо-режим

Демо-режим показывает статическую сборку Remnawave Minishop с моковыми данными. Он нужен для документации и предпросмотра интерфейса: Mini App, пользовательские сценарии и админка открываются в браузере без backend, базы данных и внешних API.

[Открыть демо](/demo/home)

## Быстрые ссылки

- [Главный экран демо](/demo/home)
- [Инструкции подключения](/demo/install?mock=guides)
- [Админка: пользователи](/demo/admin/users)
- [Админка: бэкапы](/demo/admin/backups)
- [Пробный период](/demo/home?mock=trial)
- [Email-only: нужен Telegram для триала](/demo/home?mock=trial-telegram)
- [Email-only: нужен Telegram для реферального бонуса](/demo/home?mock=referral-telegram)
- [Докупка устройств](/demo/devices?mock=devices)
- [Запуск бота для Telegram-уведомлений](/demo/home?mock=notifications)
- [Вход и регистрация](/demo/login?mock=auth)

## Как собирается

При сборке сайта документации запускается `docs-site/scripts/build-demo-runtime.mjs`. Скрипт:

- собирает отдельный frontend-бандл в Vite mode `docs-demo`;
- использует entrypoint `frontend/src/docsDemoEntry.js`, где подключены моковые данные и mock API;
- дополнительно собирает обычный admin-бандл, чтобы админка работала внутри демо;
- копирует JS/CSS, темы, default-brand ассеты, локали и конфиг гайдов подключения в `docs-site/public/demo/runtime/`;
- генерирует `app/index.html`, который грузит demo runtime и встроенные переводы;
- после Astro build материализует публичные страницы `/demo/home`, `/demo/install`, `/demo/admin/stats` и другие основные demo routes как статические `index.html`;
- Cloudflare Pages rewrite-правила остаются только для внутреннего `/demo/runtime/*`, чтобы iframe мог использовать обычный History API без влияния на остальные страницы документации;
- страницы `/demo/home`, `/demo/install`, `/demo/admin/*` и другие demo routes служат полноэкранной обвязкой с верхней панелью возврата в документацию, а внешняя страница синхронизирует читаемый адрес демо.

Папка `docs-site/public/demo/runtime/` не хранится в репозитории. Она создается на build step и попадает в итоговый `docs-site/dist/`, поэтому Cloudflare Pages публикует демо вместе с остальным docs-сайтом.

## Почему это не попадает в production

Обычная production-сборка Mini App использует `frontend/src/main.js` и не импортирует `previewMock`, `mockApi` или demo entrypoint. Моковый runtime подключается только в Vite mode `docs-demo`, который вызывается из сборки документации.
