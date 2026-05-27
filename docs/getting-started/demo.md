# Демо-режим

Демо-режим показывает статическую сборку Remnawave Minishop с моковыми данными. Он нужен для документации и предпросмотра интерфейса: Mini App, пользовательские сценарии и админка открываются в браузере без backend, базы данных и внешних API.

[Открыть демо](/demo/)

## Как собирается

При сборке сайта документации запускается `docs-site/scripts/build-demo-runtime.mjs`. Скрипт:

- собирает отдельный frontend-бандл в Vite mode `docs-demo`;
- использует entrypoint `frontend/src/docsDemoEntry.js`, где подключены моковые данные и mock API;
- дополнительно собирает обычный admin-бандл, чтобы админка работала внутри демо;
- копирует JS/CSS, темы, default-brand ассеты и локали в `docs-site/public/demo/runtime/`;
- генерирует `app.html`, который грузит demo runtime и встроенные переводы.

Папка `docs-site/public/demo/runtime/` не хранится в репозитории. Она создается на build step и попадает в итоговый `docs-site/dist/`, поэтому Cloudflare Pages публикует демо вместе с остальным docs-сайтом.

## Почему это не попадает в production

Обычная production-сборка Mini App использует `frontend/src/main.js` и не импортирует `previewMock`, `mockApi` или demo entrypoint. Моковый runtime подключается только в Vite mode `docs-demo`, который вызывается из сборки документации.

## Быстрые ссылки

- [Главный экран демо](/demo/)
- [Админка: пользователи](/demo/?screen=admin&admin_section=users&mock=tariffs)
- [Пробный период](/demo/?screen=trial&mock=trial)
- [Устройства](/demo/?screen=devices&mock=devices)
