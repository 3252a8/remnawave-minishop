# Список изменений

Новые возможности, исправления и важные замечания к обновлению Remnawave Minishop.
Сначала — изменения ветки `dev`, затем опубликованные версии от новых к старым.

История собрана из [релизов GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases)
и [релизов GitHub](https://github.com/3252a8/remnawave-minishop/releases).
Даты выпуска указаны в UTC по исходным релизам GitLab; дата появления зеркала в GitHub
может быть позже. Теги без опубликованного релиза сюда не включены.

## В разработке · dev

Номер и дата следующего выпуска пока не назначены.
[Сравнить с v3.8.1](https://gitlab.com/3252a8/remnawave-minishop/-/compare/v3.8.1...dev).

### Добавлено

- **Автопродление с баланса.** Настройки баланса перенесены в платёжные системы отдельной
  карточкой с переходом в партнёрскую программу. `USER_BALANCE_RECURRING_ENABLED`, выключенный
  по умолчанию, позволяет пользователю включить автопродление в карточке оплаты, когда выбранный
  личный или партнёрский баланс покрывает весь период с гибкими лимитами. Продления списываются
  только из выбранного источника; смешанная оплата, подарки и отдельные докупки не становятся
  рекуррентными. Докупка ресурсов блокируется при включённом автопродлении с баланса.
  ([291d9e67](https://gitlab.com/3252a8/remnawave-minishop/-/commit/291d9e67da1d87e7a2ef5b831675ea67475d75ec))

- **Начисление периода за приглашение в составе триала.** Настройка
  `REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL` вместо отдельной подписки при регистрации по
  приглашению добавляет положенные дни к бесплатному пробному периоду. Бот сообщает
  общий срок при регистрации, Web App показывает его перед активацией; начисление
  отмечается использованным при выдаче триала. По умолчанию настройка выключена.
  Правила привязки Telegram сохраняются; покупка до активации триала не начисляет эти дни.
  ([ac52973f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ac52973f820c417a8a0b163a5c2310cfbc46c9e8))

- **Вход по QR-коду.** При включённом `QR_LOGIN_ENABLED` новое устройство показывает
  код магазина, а устройство с активной сессией сканирует его через Telegram или
  камеру браузера и подтверждает вход числом с экрана нового устройства. Код
  одноразовый, хранится как хеш; сессию получает только браузер, начавший вход.
  Три неверных числа отклоняют запрос. В настройках показан публичный адрес магазина.
  Камера разрешена только для самого магазина при включённом способе входа;
  закрытие окна отменяет запрос, запоздавшие ответы не меняют повторно открытый диалог.
  ([e167842b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e167842b74c591d997f75e38cfd79da15e2e95cd), [992e6168](https://gitlab.com/3252a8/remnawave-minishop/-/commit/992e616823db67eabf1b96f6ffdd4d8bccfc4201))

### Изменено

- **Приглашения и пробный период.** После окончания подписки, выданной за регистрацию
  по приглашению, доступен обычный триал. Покупка во время этой подписки и подписки,
  выданные после неё, по-прежнему закрывают триал; действующая подписка его блокирует.
  ([ac52973f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ac52973f820c417a8a0b163a5c2310cfbc46c9e8))

### Исправлено

- Публичный шлюз подписки работает с внутренним HTTP endpoint Remnawave Panel:
  служебные proxy-заголовки формируются из доверенного адреса клиента, а профиль,
  HWID и статусы отказа панели сохраняются. Оба примера внешнего Nginx принимают
  крупные заголовки настроек клиента с запасом под заголовки магазина.
  ([681a9d9d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/681a9d9d4bb38ffa6e486e6768b22c23b76088cc))

- Полоса устройств различает доступный конечный лимит, его достижение или превышение,
  безлимит и ожидание данных. Предупреждение определяется точным количеством устройств,
  сопровождается доступной подписью и обновляется после отключения или обновления списка;
  округление заполнения до 100% само по себе не означает исчерпания лимита.
  ([3a68326f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3a68326fbbd469bb540d8a4fdcb9b7838e6c7df7))

- Список документов в настройках сначала показывает ожидание ответа API.
  Иконки соответствуют роли документа; порядок и ссылки остаются стабильными.
  Старые ссылки политики и соглашения появляются после определения отсутствия
  соответствующих документов, включая пустой ответ и недоступность старого API.

- Документы без опубликованных пунктов бокового меню сохраняют всю доступную
  ширину при переходе от мобильной к десктопной разметке. Колонка навигации
  появляется только при наличии меню; ограничение ширины текста для чтения сохранено.
  ([807d2096](https://gitlab.com/3252a8/remnawave-minishop/-/commit/807d20967bf5e42edb817ca54be444e5b4c84cdb))

- Проверка SVG в импорте тем демо разбирает XML без удаления комментариев:
  некорректная разметка, чужие пространства имён и закодированные внешние ссылки
  отклоняются. Параметры возврата OAuth кодируются как данные запроса; HTTPS-клиенты
  явно требуют TLS 1.2 или новее. Проверка эмодзи использует точные диапазоны Unicode
  без неоднозначных диапазонов регулярного выражения.
  ([ce1cf256](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ce1cf256ba9848ab38458747a732eb0d9ac0b57f))

- Адреса Xray Checker, Uptime Kuma, SMTP и сервиса курсов PayKilla, сохранённые
  администратором, разрешают подключения к точному внутреннему хосту и порту без
  перезапуска. Разрешения следуют текущим настройкам; мониторинг обновляет соединения,
  а смена URL курсов исключает использование кэша прежнего источника. Отдельный worker
  подхватывает сохранённые и сброшенные настройки SMTP и платёжных провайдеров из базы.
  ([5fe9d6b8](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5fe9d6b803f24cac6d0ebd6745bcdb9d44effa9c))

### Производительность

- Зависимости локальных проверок переиспользуются вне рабочей копии. Linux-окружение
  тестов отделено от исходников и сборки фронтенда, удерживается без фонового процесса
  и использует проверенный образ Docker Hub по неизменяемому digest. Очистка старых
  окружений затрагивает только их собственные не запущенные keeper-контейнеры.
  Браузерные проверки CI разделены на два прогона; полный локальный стенд корректно
  исключает отключённые необязательные зависимости.
  ([1f2b3782](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1f2b3782d7c0c28873007905b731ae045ba1ca3d), [a507fd4b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a507fd4b5bf2bc268b0438be0d5090699c5f3a2b))

### При обновлении

- Миграция `0102` сохраняет согласие на автопродление с баланса. Разрешение
  `USER_BALANCE_RECURRING_ENABLED` включается отдельно в настройках платёжных систем;
  для автоматических списаний должен работать штатный worker.

- Приглашённые пользователи после окончания подписки, выданной за регистрацию,
  получают доступ к пробному периоду без ручного сброса триала.

## v3.8.1 — 2026-10-06

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.8.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.8.1)

### Обзор

Добавлены telegram custom emoji, цветные кнопки в телеграм бот-меню, расширена рекламная аналитика. Улучшены перенос резервных копий между серверами, управление аккаунтами пользователей, платежи, учёт трафика, уведомления и синхронизация с Remnawave; усилена безопасность.

### Изменения

* **Добавлены настройки оформления Telegram и библиотека эмодзи.** Цвета кнопок, custom emoji и предпросмотр меню доступны в админке. Эмодзи поддерживаются в рассылках, письмах и обращениях поддержки. ([a97c04e4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a97c04e4048e3dbdc60e33a08c40127f4cb9f09a), [1b192d57](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1b192d579e34d2dfba6fb9a9c662e1d75911e8e9), [df59e047](https://gitlab.com/3252a8/remnawave-minishop/-/commit/df59e04795a3add62b164dee4a4fdbdb59b63656), [148a5d94](https://gitlab.com/3252a8/remnawave-minishop/-/commit/148a5d94a5ae5a38ad26c3b5560034efa6da390c))
* **Расширена рекламная аналитика.** Кампании объединяют ссылки, UTM, контакты, расходы и источники заказов. Добавлены отчёты по периодам и когортам, импорт статистики с предпросмотром, CSV-выгрузки и кабинет рекламодателя с командой `/my_ads`. ([4b05c59f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/4b05c59fc2a3ccc78ebd3c7102c1017e14dbe330), [75cc04e5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/75cc04e5b4431a3db3847205c04965a1d679043e))
* **Расширен и проверен перенос бэкапов между серверами через админку.** Архив включает установленные плагины и пользовательские темы; удалённые пакеты и временные файлы исключены. Большие архивы отправляются в Telegram частями и собираются при восстановлении. Ручное создание работает и без Telegram. ([874f14d6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/874f14d60c2ee43bd783cdb22efcb37d22b2298f), [1566e94e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1566e94e76dd765f5f167224e63703c869d35ee5), [144e467f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/144e467f093c4127f438113a0a9b1c89bc13e874))
* **Улучшено управление аккаунтами и устройствами.** Карточка пользователя открывается в основной области админки вместо модалки и теперь лучше адаптирована для мобильных экранов. Пользователи теперь могут переименовывать устройства. Объединение аккаунтов разных провайдеров подтверждается повторным входом, passkey или email-кодом и больше не требует обязательного SMTP. ([cc10b4e3](https://gitlab.com/3252a8/remnawave-minishop/-/commit/cc10b4e3ca9099b1130151205802a4aeff5ad473), [d2684d42](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d2684d4229c0a831201d6421dc45c37d88069d2c), [33762c9f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/33762c9f7f955349fa4286b1c0757ca9a2b65c65))
* **Улучшена синхронизация с Remnawave.** Перепривязка после смены идентификаторов панели сохраняет подписки, сроки и историю; неполные привязки восстанавливаются. Дубли с одинаковым Telegram ID объединяются. Подтверждённое удаление профиля больше не блокирует выдачу оплаченной подписки. Адреса API и браузерной панели разделены. ([6b43d46f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/6b43d46fb7d1b0e2ee05307b7a3be5e9a49faf8b), [a64bc651](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a64bc65193ffd16116f57e093d482fcde405ac79), [2a1b9bd7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2a1b9bd7852124c4bfe631c7017a3d8409fb576c), [312541a8](https://gitlab.com/3252a8/remnawave-minishop/-/commit/312541a8db3862972b77f8c07898acd9c8dd0464), [331c1564](https://gitlab.com/3252a8/remnawave-minishop/-/commit/331c1564516958812d66a2c7ff97021ee4456b6a))
* **Улучшены уведомления и перевыпуск доступа.** Уведомления учитывают текущий срок подписки и настройки каналов без перезапуска worker; временные ошибки доставки повторяются отдельно по каналам. Перевыпуск восстанавливается после потери ответа без повторной смены ссылки. Шлюз корректно передаёт заголовки клиента и скрывает токены в журналах. ([a19c59d7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a19c59d7dbfaf06485188ed6acad3b364547a6a7), [320c7d2e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/320c7d2e418db6bc99e32db77e25e626c22be396), [f887ec3e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f887ec3ef8bb4d41f32c950dc8287e42767ae442))
* **Исправлены сценарии оплаты.** Оплаченные заказы YooKassa с устаревшим расчётом переходят на проверку без бесконечных повторов. При вводе кода активации автоматически выбирается совместимый способ оплаты; продление открывается на действующем тарифе. Платёжные интеграции используют настроенный оператором адрес API. ([dd397b4d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/dd397b4dc31b2eb4f311e0b07176c1e285db454c), [ed8d24e6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ed8d24e668f8d1648e5767eca0269b18dc518e3b), [8ec08e9c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8ec08e9c5bc813407e1b8273d4e545fdd74246f9), [dd20fb52](https://gitlab.com/3252a8/remnawave-minishop/-/commit/dd20fb52d0f1fe752e9913385e8430e7b04e73e7))
* **Исправлен учёт трафика.** Покупка тарифа после триала сбрасывает использованный пробный трафик. Переносимые пакеты учитываются при каждом сбросе счётчика без повторного списания. Главная показывает отдельный лимит premium-трафика триала; название блока настраивается. ([914604e1](https://gitlab.com/3252a8/remnawave-minishop/-/commit/914604e1f7499c2e2fad73dbe63207ab5301dbee), [e328463c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e328463cf30e1f0c3f4083fd1d66450762a1295a), [bd7c004c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bd7c004c81c4afc9f4f456d78255f4cd95a54726), [34143c04](https://gitlab.com/3252a8/remnawave-minishop/-/commit/34143c04a059ccd4ae3199fccaced22a70ebce90))
* **Расширены приглашения и связанные начисления.** Добавлены статистика приглашённых, начисленного периода и QR-коды ссылок. Начисления сохраняются в очереди и повторяются независимо для участников. Первая покупка учитывает только подходящие подписки; ограничения партнёрской программы применяются и к существующим связям. Действительная подарочная ссылка разрешает регистрацию в режиме только по приглашению. ([e5d2495b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e5d2495b4939eef021db575b9dc9eda8e698554c), [27217858](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2721785878c52f89c409f0a50c7ff4820a1fe5f4), [118a0f67](https://gitlab.com/3252a8/remnawave-minishop/-/commit/118a0f675f3683ec0d8294c2a27e6faabeef5f6f), [269b1023](https://gitlab.com/3252a8/remnawave-minishop/-/commit/269b1023533d9ca585c8afb3d19211461c370b59), [2cf966e6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2cf966e64bd18f53d74680dfa0dc6bf58782dc9a), [7964b5e5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/7964b5e5b390087d84ccbe81239aac89c04b1709))
* **Улучшены темы и инструкции подключения.** Администратор может отдельно разрешить эффекты темы в пользовательском Mini App. Расширена поддержка безопасного SVG. После ошибки загрузки инструкции можно получить повторно; настройка анимации цен применяется ко всем значениям checkout. ([93b0cd50](https://gitlab.com/3252a8/remnawave-minishop/-/commit/93b0cd50b85faea85287d9bd3b3289a9efdfab3b), [8e8c2ac3](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8e8c2ac3c9ef72cee1c04d691f31bbbb6184ab1a), [87adec45](https://gitlab.com/3252a8/remnawave-minishop/-/commit/87adec4534e6fed4df89be1216b3f4709a25ab5b), [c13440b3](https://gitlab.com/3252a8/remnawave-minishop/-/commit/c13440b3e12136cd382a5899033df4af92234948))
* **Усилена безопасность Mini App и интеграций.** Добавлены атомарные квоты запросов, проверка browser origin и точное доверие адресам прокси. Защищены владельцы от административной блокировки, платёжные ключи от отправки на посторонний origin, SMTP-подключения и CSV-экспорт от выполнения формул. ([f530ca1b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f530ca1b4c700bb297b8357aeaa2e31a52f08b5f), [7689c39e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/7689c39ecb939c63517d73bcb20aeaa10e4e6e02), [29a44312](https://gitlab.com/3252a8/remnawave-minishop/-/commit/29a4431201fa857b2a0fb646ded1baabc5da5899), [82735247](https://gitlab.com/3252a8/remnawave-minishop/-/commit/82735247cbf40f28dca3376296b3579cca9cfe0e), [d7d5cb3c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d7d5cb3cda59ad320970c748a78a32bb13db2a93), [c26ab8a8](https://gitlab.com/3252a8/remnawave-minishop/-/commit/c26ab8a82aac25e169d54ac980a935d04a91f41f), [bb2a88fe](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bb2a88fe7dd5dcc226d6b0e40e97e702e0959471))
* **Обновлен функционал плагинов, зависимости и документация.** Git-плагины сохраняют выбранную ветку при проверке обновлений; ленивые импорты уменьшают память launcher. Обновлены зависимости и инструменты сборки, закреплены исправленные версии пакетов. Добавлен каталог Awesome Minishop и расширены руководства. ([1c1c5f8e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1c1c5f8e0b233d5d3040c90c0366f3879b0119fa), [933bad98](https://gitlab.com/3252a8/remnawave-minishop/-/commit/933bad988da9c8fbd727b8f8db5ef4f60d4fee76), [8f90cda4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8f90cda43a6f6376a53c011bcd49d620ab3262f0), [bc337981](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bc3379812b370ed4420b97338fc24fce5c87f1a6), [5e741824](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5e7418243e40151f620b4be475fd253a62725c13), [e3b88fa9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e3b88fa9600b3f2bc303de391b9261bb0f9342d2))

### При обновлении

* Добавлены миграции `0094`–`0100` для начислений, перевыпуска доступа, названий устройств, рекламной аналитики, учёта трафика и уведомлений. Для фоновой доставки и повторов должен работать штатный worker. ([118a0f67](https://gitlab.com/3252a8/remnawave-minishop/-/commit/118a0f675f3683ec0d8294c2a27e6faabeef5f6f), [a19c59d7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a19c59d7dbfaf06485188ed6acad3b364547a6a7))
* Если API панели доступен только внутри Docker, задайте браузерный адрес отдельно через `PANEL_PUBLIC_URL`. Пустое значение сохраняет прежнее поведение ссылок. ([331c1564](https://gitlab.com/3252a8/remnawave-minishop/-/commit/331c1564516958812d66a2c7ff97021ee4456b6a))
* Для собственного reverse proxy укажите точный IP/CIDR или `host:имя-сервиса` в `TRUSTED_PROXIES`. Старое доверие всем частным сетям замените точными адресами; стандартные Docker-прокси поддерживаются без явной настройки. ([29a44312](https://gitlab.com/3252a8/remnawave-minishop/-/commit/29a4431201fa857b2a0fb646ded1baabc5da5899))
* Исторические начисления и неизвестный расход трафика не восстанавливаются предположительно. Статистика начислений начинается с новой миграции; восстановление нескольких пропущенных сбросов требует полной истории панели. Историю уведомлений вручную очищать не нужно. ([e5d2495b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e5d2495b4939eef021db575b9dc9eda8e698554c), [e328463c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e328463cf30e1f0c3f4083fd1d66450762a1295a), [a19c59d7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a19c59d7dbfaf06485188ed6acad3b364547a6a7))

Контрибьюторы: wormy09 (`e328463c`, `d2684d42`, `e5d2495b`, `27217858`) и Roycce (`75cc04e5`, `933bad98`). Автообновление списка временных email-доменов — github-actions\[bot\] (`96a1466e`).

## v3.8.0 — 2026-09-30

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.8.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.8.0)

### Обзор

Добавлены независимые от Telegram аккаунты, установка подписанных плагинов, публичный
шлюз подписки, информационные страницы и JavaScript-эффекты тем. Улучшены платежи,
уведомления, админка и производительность.

### Добавлено

- **Аккаунты без Telegram.** Core может работать как браузерный магазин с email-входом,
  независимым Minishop ID и необязательной привязкой Telegram. Права владельца и
  администраторов управляются централизованно; публичные ID используются в карточках,
  связанных записях и уведомлениях, существующие связи с панелью сохраняются при миграции. ([e060e2e9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e060e2e98577bd5f3191a0a6b18e1a302698cc38), [ca46af6d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ca46af6dcbf0098e697ed57a1ddb40ff580174b2), [2a045291](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2a045291f42980c7d884fc843fcb79fd201ae192))
- **Установка плагинов из подписанных ZIP-пакетов.** Менеджер проверяет подпись, минимальную
  версию Core и необходимые возможности API, показывает настройки и состояние пакетов,
  поддерживает удаление активных пакетов и подтверждает изменения после перезапуска процессов. ([ea82a92f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea82a92f1cc548fcc2882be30a60f180624fa53a), [d97a9358](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d97a93586aa1409800168d815c989ea767cd1abf), [a498317b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a498317bcb42ad26a956677ca1e101727e28d8d4), [98382cd6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/98382cd65d216c4280bd238f7c4c7fde5088bc2c), [5f283037](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5f28303741c96b31009c9cb8f5afa6c3f3ddba12))
- **Расширения пользовательских и административных разделов.** Плагины могут добавлять
  страницы, карточки, инструкции подключения, внешние заказы с выдачей после оплаты,
  устойчивые фоновые задачи, журналируемые права и данные для резервного копирования.
  Существующие разделы допускают композицию расширений; учитываются скрытые разделы,
  прямые ссылки, runtime-ассеты и обновление установленных расширений. ([33121363](https://gitlab.com/3252a8/remnawave-minishop/-/commit/331213638460da024df4186fc60141d4cb9607cf), [af122b9d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/af122b9d1332430e39c0fb5bc877226974c1d3f3), [bc8ca963](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bc8ca963526433493e9bb8f8375408e530c18204), [f1f91d94](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f1f91d947a6bc6836f93cb7a63e2ebcc9e6980a0))
- **Переводы плагинов в админке.** Строки плагинов вынесены из общих групп в
  отдельный подраздел с группой для каждого плагина; плагин может задать
  дополнительные вложенные группы своих строк с переводимыми названиями. ([1b5b3697](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1b5b3697ad3a34be7b4ba9d86e629ccffed346d4), [0d16c02a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0d16c02a89e09408adcf2c1acbfcc39e12322dc8))
- **Публичный шлюз подписки.** Ссылки подключения можно выдавать через домен магазина;
  режим ссылки доступен в админке, шлюз включён по умолчанию и принимает увеличенные
  заголовки ответов подписки. ([0c046b2c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0c046b2c60bf85cc7cdb316ef8f1356bc531fb2f), [8e60f1f9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8e60f1f9cb47e6b7ada0d8fe4bf964e6de0e2dea), [4969be67](https://gitlab.com/3252a8/remnawave-minishop/-/commit/4969be67e519fcf0484572ec86066bc693f509fb), [d3e63b62](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d3e63b627ad4f3bfdfe658acdbd3264341187724))
- **Аналитика кодов активации.** Добавлены поиск, фильтры статуса и области применения,
  прямые ссылки на детали и выручка подтверждённых платежей по валютам в истории активаций. ([caddef66](https://gitlab.com/3252a8/remnawave-minishop/-/commit/caddef66eea805e09cd844c593efb13e5b41e5d6))
- **Информационные страницы.** Добавлены управляемые страницы с Markdown и открытием
  документов внутри Mini App; редактирование сохраняет форматирование и состояние документов.
  Хранилище документов блокирует конкурентные изменения также при запуске Core на Windows. ([d94c943a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d94c943ae97242e45633e138204ffecd33e71029), [fc816ca6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/fc816ca6d4037b6c64fdb522c3684626a800aa37), [8ff40829](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8ff408292f7af1197a327e5f8b6d1c2bef471965), [de94f444](https://gitlab.com/3252a8/remnawave-minishop/-/commit/de94f444c3abc43251b6f49c27fbcd8c7fd01ac6))
- **JavaScript-эффекты тем.** Пакеты оформления могут содержать эффекты; расширены их настройки
  и управление темами, включая сохранение черновика при совместной записи настроек внешнего вида.
  Живой предпросмотр эффекта в библиотеке показывает реальный макет главной с наложенным
  адаптером, а открытый предпросмотр темы в Mini App сразу запускает эффект предпросматриваемой
  темы — без перезапуска сервиса. ([8c311f9a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8c311f9ab3fef0cec6823b0026a36fd0d439d7d1), [b4f02e65](https://gitlab.com/3252a8/remnawave-minishop/-/commit/b4f02e6545d640ca8f2c958982259b41b8620eba), [a8b786c9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a8b786c9ad4293bae5d4fe577a6c2e6415bb178f))
- **Диагностика рассылок.** В истории видны подробности недоставленных сообщений;
  немедленная рассылка ставится в очередь вне административного HTTP-запроса. ([355a7532](https://gitlab.com/3252a8/remnawave-minishop/-/commit/355a75324205a8a98276c97c5ee9f5dcb226f922), [ffcb90d2](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ffcb90d26842b7fbc7e2dc077c0eb411670a61a4), [bb53fb70](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bb53fb700b0f9130d23af7f827a5fb4d90c19b48))

### Изменено

- **Зависимости.** Обновлены Python- и npm-пакеты, а frontend переведён на
  стабильную ветку nginx 1.30. В сборке веб-интерфейса и сайта документации
  устранены известные уязвимости в транзитивных пакетах `brace-expansion` и `undici`. ([bd153166](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bd1531668dceb22bcb93149561cbb2e19edd5758), [ea6c8830](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea6c88308e2fd5e1f9c9ed26c81c2b0792826327), [2b975207](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2b975207e645e9b6a830e9139d863589ec7f7ba2))
- **Регистрация passkey.** При поддержке устройства предпочтение отдаётся EdDSA;
  проверка отклоняет повреждённые данные CBOR и некорректные форматы аттестации. ([e060e2e9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e060e2e98577bd5f3191a0a6b18e1a302698cc38))
- **Вход и сессии.** Способы входа адаптируются к ширине экрана: широкие кнопки располагаются
  перед компактными. Срок сессии доступен в настройках и по умолчанию составляет 30 дней. ([88992d4d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/88992d4d9e132982339ab6af09d0b41e85dc2838), [4a9aee9a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/4a9aee9ae7a4ebb842c977ee8d99dbc065fefc82), [e7f82c1a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e7f82c1ad9a1f4eb2d59aee27ea9de10cfeb8156))
- **Карточка пользователя.** Упрощён мобильный вид, доступен переход в профиль панели;
  изменения тарифа проверяются, ошибки действий показываются явно, а блокировка аккаунта
  синхронизируется с доступом к VPN в панели. ([5cd0838c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5cd0838ca0b2a3621f69d7336bc2a60afdfe8bd8), [da0e5772](https://gitlab.com/3252a8/remnawave-minishop/-/commit/da0e577259d8cd78c11219f88a067c94a956a361), [e0e3d315](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e0e3d31505681d65a8c9932de28aa84392077aa4))
- **Уведомления и поддержка.** Унифицированы данные аккаунтов и переходы из журнала,
  темы обращений показываются в уведомлениях и диалогах, оплаченные повышения тарифа
  отражаются в платёжных уведомлениях. Кнопка карточки пользователя в журнале открывает
  нужный профиль в Telegram Mini App, в том числе из рейтингов, и не создаёт ссылку
  с шаблонным именем бота. Заблокированным пользователям автоматические уведомления
  больше не отправляются ни в Telegram, ни по email. ([5c4636df](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5c4636df4a972e92b727c33bcac660cabd88ee3b), [e193e7fc](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e193e7fc3778406e467707047466a301544ef22a), [a78a8d49](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a78a8d49596634e496e68d800a371ca5aa3f2f88), [bc0f1305](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bc0f13054a8f449eb9354a05f20bc0bf351c1722), [14eebebd](https://gitlab.com/3252a8/remnawave-minishop/-/commit/14eebebda66c186465a47adbe31937983901c00b))

### Исправлено

- **Главная страница личного кабинета.** Размер логотипа ограничен доступной областью,
  поэтому нижний блок с подпиской и действиями остаётся у нижнего края без лишней прокрутки. ([a2282f31](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a2282f31da304564186aa1636caff60281521242))
- **Синхронизация с панелью.** Новые пользователи панели с Telegram ID или email
  появляются в магазине вместе с подписками без возврата на стабильную версию.
  Email из панели остаётся неподтверждённым до входа с кодом; совпадение с другим
  локальным аккаунтом требует ручной проверки. ([3e47e2b6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3e47e2b64f04836699897dfb8408230f2c5605f6))
- **Партнёрские ссылки.** При регистрации через Google, Yandex и Discord код из веб-ссылки
  сохраняется при переходе к провайдеру и учитывается при создании аккаунта. В уведомлениях
  о новой регистрации через Telegram, email и внешние сервисы теперь указывается пригласивший партнёр. ([1e329cf8](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1e329cf88037912427005a5d11a049e5ecf3ff05))
- **Журнал событий.** Кнопка карточки пользователя в групповых уведомлениях открывает личный
  чат с ботом с адресным переходом к карточке; если имя бота неизвестно, используется веб-ссылка. ([14eebebd](https://gitlab.com/3252a8/remnawave-minishop/-/commit/14eebebda66c186465a47adbe31937983901c00b))
- **Объединение аккаунтов.** Если Telegram уже привязан к другому аккаунту, после подтверждения
  профиля открывается объединение с кодом из почты. Оно работает в браузере и Telegram Mini App;
  подписки объединяются только после подтверждения обеих сторон. ([21d83ab7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/21d83ab71c805f039742eb2513d9d8de24b3f4a0))
- **Оплата и рекуррентные подписки.** Поддержаны фиксированные периоды оплаты; для пополнения
  скрыты рекуррентные способы, а при оплате балансом выбираются совместимые методы.
  Отмена Tribute Creator ведёт в бота. Администратор может сменить тариф при активном
  автопродлении Tribute: Shop Order отменяется через API, для Creator локальное
  автопродление отключается после отмены администратором в Tribute. Пользователь может
  подтвердить отмену Creator в диалоге Mini App и сразу отключить локальное
  автопродление без изменения оплаченного срока. ([523e3646](https://gitlab.com/3252a8/remnawave-minishop/-/commit/523e36467478a56a04bdc32097009a3b2e215ff2), [0ac2488a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0ac2488a1911fd68095fb03eae7d5f1703f8c5e8), [0de2db99](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0de2db9922c2054e3fe69185adb7b9d10075c34e), [1d9e6ff0](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1d9e6ff00dbcaab3885ffe31f1cfd84b767df499), [62bf0f41](https://gitlab.com/3252a8/remnawave-minishop/-/commit/62bf0f4193b708b3abf7ed3dc73289faf5093b55))
- **Mini App на мобильных устройствах.** Диалоги, выпадающие списки и другие наложения
  ограничены безопасной областью Telegram; исправлены компоновка поддержки и редактора,
  Telegram-ссылки и административные превью. ([81e7a765](https://gitlab.com/3252a8/remnawave-minishop/-/commit/81e7a765748a9b92a8f83f7a9fd3c1f8516073b4), [317b72c7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/317b72c78f8b520c54caad12e135ebba06531170), [29790339](https://gitlab.com/3252a8/remnawave-minishop/-/commit/297903391ad9211fce59945904cfbcd690dd76fa), [e027c982](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e027c982913d804b27ebbbc4878402d540a45af6))
- **Инструкции подключения.** Happ и INCY получают корректные зашифрованные ссылки в кнопках
  приложений; QR-код и копирование используют HTTP-ссылку подписки независимо от выбора
  приложения и доступны без кнопки подключения. Сбой загрузки экрана допускает
  восстановление. Начальный профиль использует публичный URL панели. ([44054551](https://gitlab.com/3252a8/remnawave-minishop/-/commit/44054551a986449fddc7b7061067626e4534358d), [01d6661b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/01d6661b61365f148cf2f42af8070037d0f6148a), [f11955cc](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f11955cc8c7c3db34943b238ae96cb0e4ca99009), [04841434](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0484143477b6f4ccb1da6f96fa93014658ca1ea7))
- **Идентификация и тарифы.** Сохраняются неразрешённые связи старых аккаунтов с панелью
  и числовые идентификаторы пользователей в вебхуках Torrent Blocker. Интерфейс тарифов
  больше не обещает сброс трафика, который панель не выполнит. ([f9fbb93c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f9fbb93cbc3dc91f7aa1e10357deafd543b65914), [9192b420](https://gitlab.com/3252a8/remnawave-minishop/-/commit/9192b420ff836b5b6342a9f3407297d37bb5430f), [be3cab79](https://gitlab.com/3252a8/remnawave-minishop/-/commit/be3cab79e615686fbda81b69fa63dec617bb7802))
- **Email-рассылки.** Доступность доставки определяется готовностью SMTP независимо
  от включённости входа по email. ([bb53fb70](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bb53fb700b0f9130d23af7f827a5fb4d90c19b48))

### Производительность

- Ускорены первый вход в админку, загрузка переводов и представлений плагинов, работа
  слайдеров. Web App ожидает bootstrap-данные и повторяет загрузку при запуске API;
  интерфейс админки появляется после готовности переводов. Большие группы переводов
  раскрываются порциями, а неизменённый файл переводов не сверяется с базой при каждом запросе. ([0b2c5f00](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0b2c5f003df18e3ea0fc9b756580f5f282a1d844), [e2b60313](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e2b603139c12f8908bf5c8cabc57581ab4592946), [0d16c02a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0d16c02a89e09408adcf2c1acbfcc39e12322dc8), [e85b6812](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e85b68122a04e62361cb9b0bf0f9190d48c668f9))
- Список бэкапов загружается по метаданным файлов без проверки содержимого всех ZIP;
  состав выбранного архива проверяется отдельно. Открытие списка больше не задерживает
  запросы остальных разделов админки. ([d67a2d85](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d67a2d855ca5d983d853d6c4a500fe8347c5d3d4))
- Локальный Linux-прогон backend-тестов на Windows использует копию исходников в QA-образе
  вместо медленного bind mount; зависимости устанавливаются при сборке образа и кешируются. ([de94f444](https://gitlab.com/3252a8/remnawave-minishop/-/commit/de94f444c3abc43251b6f49c27fbcd8c7fd01ac6))

### Документация

- Добавлен единый список изменений с разделом dev на сайте документации, ссылкой в шапке
  и отдельным пунктом внизу сайдбара. Демо поддерживает
  прямые адреса всех административных разделов и загрузку плагинов. ([859a248e](https://gitlab.com/3252a8/remnawave-minishop/-/commit/859a248e73564affe2989a0797d84fa408888fe8), [93c7ad93](https://gitlab.com/3252a8/remnawave-minishop/-/commit/93c7ad939d50dd04f4ed08d77bd86e4442dd8810), [c0bc1a06](https://gitlab.com/3252a8/remnawave-minishop/-/commit/c0bc1a06b518010dd46c507ddc68b728142ef400), [f5594777](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f559477746e080df5363a40824b74529261c79fd))

### При обновлении

- Добавлены миграции `0088`–`0093` для ссылок инструкций, данных расширений и независимой
  идентичности аккаунтов, включая последовательность ID и происхождение связи с панелью. ([0c046b2c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0c046b2c60bf85cc7cdb316ef8f1356bc531fb2f), [33121363](https://gitlab.com/3252a8/remnawave-minishop/-/commit/331213638460da024df4186fc60141d4cb9607cf), [e060e2e9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e060e2e98577bd5f3191a0a6b18e1a302698cc38))
- Для автономной работы используется `TELEGRAM_ENABLED=False`; требуются настроенные
  email-вход, SMTP и публичный адрес приложения. Первый владелец назначается доверенной
  командой `bootstrap_owner.py`, затем роли управляются в общих настройках админки.
  См. [работу без Telegram](docs/features/telegram-optional.md). ([e060e2e9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e060e2e98577bd5f3191a0a6b18e1a302698cc38))
- Перед установкой расширений проверьте требования пакета к версии и возможностям Core.
  Дождитесь подтверждения состояния после перезапуска; см. [контракт плагинов](docs/development/plugin-contract.md). ([ea82a92f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea82a92f1cc548fcc2882be30a60f180624fa53a), [a498317b](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a498317bcb42ad26a956677ca1e101727e28d8d4))
- JavaScript-эффекты тем по умолчанию выключены и требуют отдельного разрешения администратора.
  Это доверенный код страницы; разрешение не переносится при экспорте и сбрасывается при
  восстановлении резервной копии. См. [модель доверия эффектов](docs/features/theme-effects.md). ([8c311f9a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8c311f9ab3fef0cec6823b0026a36fd0d439d7d1))

## v3.7.2 — 2026-09-21

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.7.2) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.7.2)

### Обзор

Добавлены рекуррентные платежи Wata, расширены темы и настройки интерфейса, управление входом и уведомлениями. Ускорены Web App и админка, исправлены сценарии платежей, миграции и доставки архивов.

### Изменения

* Добавлены рекуррентные платежи Wata с расписанием на стороне провайдера: отдельный способ оплаты, фиксация условий подписки, обработка повторных списаний, замены и завершения подписки. ([05ae2e3f](https://github.com/3252a8/remnawave-minishop/commit/05ae2e3f426800d33f6c57ff4f70e9cb5533812c))
* Расширена система тем: управление видимостью восьми элементов главной страницы, настраиваемый разделитель метаданных, режимы списка начислений за приглашения и безопасный импорт SVG. Запись дескрипторов темы защищена от конкурентных изменений. ([8f555750](https://github.com/3252a8/remnawave-minishop/commit/8f5557506de881fe34f90ca9d802cc9945431ba6), [8793057b](https://github.com/3252a8/remnawave-minishop/commit/8793057bdbe4efdd3cd89effdddceb771000b367), [834d63d5](https://github.com/3252a8/remnawave-minishop/commit/834d63d5030913d19789f3ae082b0cfc297655bb), [c7c03157](https://github.com/3252a8/remnawave-minishop/commit/c7c0315773913a4d0b12e05982802a37eb6b96a3), [408171a9](https://github.com/3252a8/remnawave-minishop/commit/408171a901f87a63188549fcc1f0ceeeece4d30a))
* Расширены настройки входа и пробного периода: для каждого провайдера можно отдельно включить рекомендацию привязки, а активацию пробного периода — ограничить наличием Telegram или внешней OAuth-идентичности (теперь любой провайдер подходит, а не только телеграм). ([08110e21](https://github.com/3252a8/remnawave-minishop/commit/08110e219335b1ea50e9ecfff1894088388869f5), [73be790c](https://github.com/3252a8/remnawave-minishop/commit/73be790cc368079acaf857f789fd3fe2fcdd0ff2))
* Добавлены настройки UX параметров тарифа в checkout: анимацию числовых значений можно отключить, а редактор параметров — открывать сразу при входе. ([5d5d6a71](https://github.com/3252a8/remnawave-minishop/commit/5d5d6a711b29747dd3752bd706efc0ca817f974f))
* Расширены пользовательские кнопки и рассылки: видимость кнопок отдельно задаётся для меню Telegram-бота, Telegram Mini App и браузера, а URL кнопок рассылки поддерживают персонализацию для каждого получателя. ([51e2200d](https://github.com/3252a8/remnawave-minishop/commit/51e2200d8d2734a5df701f8ddbfda6c2b1357736), [7ab91e92](https://github.com/3252a8/remnawave-minishop/commit/7ab91e924513b15143ae8301d86d9aae6bb763bc))
* Добавлено управление доступом к пользовательским настройкам уведомлений и отдельный переключатель Telegram/log-уведомлений администраторам о новых тикетах поддержки и ответах. ([d059cb4c](https://github.com/3252a8/remnawave-minishop/commit/d059cb4ca60442f48bd5ecd53fc67cc7940cabae), [87b72e8f](https://github.com/3252a8/remnawave-minishop/commit/87b72e8fd78278c198551be479c091b1561f1905))
* Ускорены Web App и админка: добавлены пакетное чтение прав и тарифов, ограниченные транзакции фоновой синхронизации, версионированные кеши, объединение параллельных запросов и кеширование переводов и настроек. ([d692f179](https://github.com/3252a8/remnawave-minishop/commit/d692f17966037655d1ba58a606fff8f8bd61c529), [82c757e9](https://github.com/3252a8/remnawave-minishop/commit/82c757e984732d7823bcf5d9198059cccf6d3465), [82c17b17](https://github.com/3252a8/remnawave-minishop/commit/82c17b1769d33ddafa0943063cf7c210225f55a1))
* Добавлена доставка крупных архивов через собственный Telegram Local Bot API с общей настройкой для backend и worker. ([13c0118f](https://github.com/3252a8/remnawave-minishop/commit/13c0118f810a51db55ff6e8b257b6442041ab66c))
* Исправлены платежные сценарии: RollyPay принимает платежи без метаданных трафика и использует укороченные callback-идентификаторы, сохраняется flow приватных тарифов через Telegram invoice, а возврат платежа корректно откатывает связанные пополнения трафика. ([c00b4bbf](https://github.com/3252a8/remnawave-minishop/commit/c00b4bbffdb20273e2584960a8dd8927c42a7eac), [065e302e](https://github.com/3252a8/remnawave-minishop/commit/065e302e825ee9828ceaff023236b3c5b7f28aff), [8e376168](https://github.com/3252a8/remnawave-minishop/commit/8e3761689cc45667b52071a7b3feba757e67a62e), [c201881a](https://github.com/3252a8/remnawave-minishop/commit/c201881aef43eb18341f9b59caf35656a5ba7e8c))
* Исправлены Mini App и админка: история ping не учитывает кешированные проверки, компактная карточка показывает дату сброса трафика, checkout не оставляет устаревший баннер подарка, email-only аккаунтам не показываются недоступные действия, а сброс пользователя завершает активный пробный период. Обновление аватаров и переходы к связанным клиентам теперь работают сразу. ([9aa04ef9](https://github.com/3252a8/remnawave-minishop/commit/9aa04ef9eb8d5e0812f7c41c6958728f4d74883e), [b31602c7](https://github.com/3252a8/remnawave-minishop/commit/b31602c7b9a5fe0834398a149b7b04fdcdf58ce1), [9dbadf53](https://github.com/3252a8/remnawave-minishop/commit/9dbadf533f30a459c94a837a1cf33a9832b36581), [0e2dbf5a](https://github.com/3252a8/remnawave-minishop/commit/0e2dbf5a7d0d4ee6a8cd3ad81d1a8849f786aa1b), [36912875](https://github.com/3252a8/remnawave-minishop/commit/3691287568ff227cdc84dc564ae34e83623aab6f), [5d88dd32](https://github.com/3252a8/remnawave-minishop/commit/5d88dd321d1e7ac718329c1adfc87a177505b3a2), [35fd9ad5](https://github.com/3252a8/remnawave-minishop/commit/35fd9ad546cde195b48434847fdb86113f245328))
* Усилены установщик и legacy-миграция: ввод мастера изолирован от Compose, preflight и cutover стали безопаснее, URL панели Bedolaga нормализуется, а ссылки подписок сохраняются и проверяются после переноса. ([faf06604](https://github.com/3252a8/remnawave-minishop/commit/faf06604c35c1d5fec46fb25cc9a770dab92341b), [227399d2](https://github.com/3252a8/remnawave-minishop/commit/227399d2e135d577a38113b84eec0aea8bc03739), [f7f437e5](https://github.com/3252a8/remnawave-minishop/commit/f7f437e5bafccff48e90133e93f12616aea9b604), [39c4c11a](https://github.com/3252a8/remnawave-minishop/commit/39c4c11acf67fca7fe2a66908cba05926c43b5f8))
* Обновлена публикация Core: добавлены каналы образов в GHCR, повторные попытки для временных сбоев публикации и dev-стенда, усилены dependency/security workflows и обновлены web/docs-зависимости. ([7784bf60](https://github.com/3252a8/remnawave-minishop/commit/7784bf60848cdfad4866d91629ba55ac8dfa38a6), [cb2ecdec](https://github.com/3252a8/remnawave-minishop/commit/cb2ecdec742deb13f297ce0f13e92e581cdd25f3), [74739e1b](https://github.com/3252a8/remnawave-minishop/commit/74739e1be249ce21026a148d89b614e03a01cded), [4a9f6606](https://github.com/3252a8/remnawave-minishop/commit/4a9f6606cf5c9eb44713fe8848564d8561c9d109))

### При обновлении

* Добавлена миграция `0087_add_wata_subscriptions`, создающая таблицу состояния рекуррентных подписок Wata.
* Для рекуррентных платежей Wata требуется подключить подписки на стороне терминала и включить `WATA_SUBSCRIPTION_ENABLED`.
* Для крупных Telegram-архивов можно настроить `TELEGRAM_BOT_API_BASE_URL`; собственный Bot API должен быть отдельно запущен и доступен из backend и worker.
* Добавлены настройки `*_LOGIN_RECOMMENDED`, `USER_NOTIFICATION_PREFERENCES_ENABLED`, `SUPPORT_ADMIN_TELEGRAM_NOTIFICATIONS_ENABLED` и параметры отображения checkout. Старое имя `TRIAL_WITHOUT_TELEGRAM_ENABLED` сохранено как deprecated-алиас для `TRIAL_WITHOUT_OAUTH_ENABLED`.
* Обновления зависимостей подготовлены `dependabot[bot]`: [dfc8642c](https://github.com/3252a8/remnawave-minishop/commit/dfc8642ce9038a123fdfb8a93b07b3ca7b7e9fc5), [b98b6096](https://github.com/3252a8/remnawave-minishop/commit/b98b6096741c8988e698b6ec018003f2e43693ad), [98f80543](https://github.com/3252a8/remnawave-minishop/commit/98f8054327779664fb5549b448b626a63f09fdbb).

## v3.7.1 — 2026-09-14

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.7.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.7.1)

### Обзор

Расширены меню настройки темы WebApp, добавлена миграция из Bedolaga, ссылка для покупки скрытого тарифа, логин через Discord. Сертифицирована Remnawave Panel 3.4.4, улучшены административные сценарии и стабильность платежей.

### Изменения

* Расширены библиотека оформления и runtime тем WebApp: выбор активной темы, произвольные CSS-переменные и настройки вариантов, прозрачность, общий редактор цвета, экспорт пакетов, сохранение превью и подробная диагностика импорта. ([f84f658](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f84f658b9b0836476c4e4e484d11162f1425d492), [245e80a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/245e80a203d1da104c561f80f1314fac4a2346cb))
* Добавлен безопасный импорт из Bedolaga: переносятся учётные записи, тарифы и подписки, финансовая история, подарки, обращения поддержки, рекламные и партнёрские данные; предусмотрены dry-run, сверка результатов, резервная копия и управляемое переключение стеков. ([9c4e5f4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/9c4e5f48402980daf8adb834fae01466c8c0ed38))
* Расширен импорт из Remnashop: добавлены email-only аккаунты и OAuth identities, пользовательские балансы, squads и индивидуальные overrides, коды активации трафика, рекламные ссылки и дополнительная проверка финансовых данных. ([d16bf91](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d16bf912bf53bf23c7346c29a7c99aa54ba3c6bc))
* Добавлен доступ к скрытым тарифам по приватным ссылкам: администратор может создать, отозвать или пересоздать уникальную ссылку, не публикуя тариф на общей витрине. ([5367bb4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5367bb4b290b3d5d2694c6cad455e2ffed9dad3e))
* Добавлена синхронизация тарифных тегов пользователей с Remnawave Panel при активации, продлении и смене подписки, а также фоновая сверка существующих пользователей с сохранением вручную назначенных тегов. ([31f8735](https://gitlab.com/3252a8/remnawave-minishop/-/commit/31f87357787aadb528cc35c0379289ce5ad11318))
* Добавлен вход и привязка аккаунта через Discord OAuth2; полностью введённый email-код теперь проверяется автоматически. ([89d0289](https://gitlab.com/3252a8/remnawave-minishop/-/commit/89d028944a10d6c7df8ca92e2614ca57e4b97c0b), [08b179c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/08b179c4e162309b410eb5b7ea9c24c824f78ff7))
* Добавлен переход из карточки пользователя Minishop непосредственно в соответствующий профиль Remnawave Panel. ([9481486](https://gitlab.com/3252a8/remnawave-minishop/-/commit/94814866d2fdfb7edfb34dd08df52d435361d3ee))
* Сертифицирована совместимость с Remnawave Panel 3.4.4, включая поддержку пользовательских тегов и сценарий обновления с поколения 2.8.1. ([203d6ea](https://gitlab.com/3252a8/remnawave-minishop/-/commit/203d6ea26c751a9bb3d65e41d8140f4df2ea35f5))
* Исправлены административные сценарии: сохраняется выбранный статус обращений поддержки, из деталей платежа открывается нужная карточка пользователя, а неактивные периоды больше не возвращаются в редактор тарифа. ([e0c8c42](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e0c8c422320f2c7eb77b3e407f57f9853d1e2096), [b42b377](https://gitlab.com/3252a8/remnawave-minishop/-/commit/b42b3776b9df2d571d3ee41ea98f65e0f961010c), [e726d56](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e726d562eb52daeed5ca4cdc72b832b6719dd7eb))
* Исправлена загрузка метаданных RollyPay до инициализации локальной конфигурации; из диалогов подтверждения убрана дублирующая кнопка закрытия при наличии явного действия отмены. ([0641d2f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0641d2fcd351645ce94e79187d1336501374a67b), [595fd5d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/595fd5dcce6f2f07e7fcdcae47ba46324d11024a))

### При обновлении

* Добавлены переменные окружения `DISCORD_OIDC_ENABLED`, `DISCORD_OIDC_CLIENT_ID` и `DISCORD_OIDC_CLIENT_SECRET`.
* Добавлена append-only миграция БД `0086_panel_tariff_tag`; существующие миграции не изменялись.
* Минимальная версия Node.js повышена до 24. ([7dd95fb](https://gitlab.com/3252a8/remnawave-minishop/-/commit/7dd95fbfea89af0965f1465ad44be5a4d11017d0))
* GitLab назначен основным хостом исходного кода; после публикации dev-образов pipeline может запускать сборку downstream-потребителя. ([93c82c4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/93c82c41ac51f161bce38262387a2e8377cb99ec), [3c53718](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3c5371898e1e69237c4087f83c718e84b2e5842b))
* Обновлены OpenAPI, типы API, каталог событий и манифест настроек.
* Вклад в библиотеку оформления и переход на Node.js 24: [BADtochka](https://gitlab.com/BADtochka)

## v3.7.0 — 2026-09-09

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.7.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.7.0)

### Обзор

Добавлены личный баланс, подарочные подписки, вход через Google, Яндекс и passkey, улучшение флоу установки кастомных тем для веб апп из админки. Расширены тарифы, способы оплаты, уведомления и инструменты управления пользователями.

### Изменения

- **Добавлен личный баланс пользователя:** пополнение через платёжных провайдеров, полная или частичная оплата подписки, продления, трафика и устройств с доплатой остатка внешним способом. В админке доступны остатки, журнал операций, корректировка сумм и перевод между личным и партнёрским балансами с сохранением ограничений на вывод. [d27a105d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d27a105d85dc30e168b945177816ac8ebc662dca), [b5593216](https://gitlab.com/3252a8/remnawave-minishop/-/commit/b5593216dff2e2234beca6ade0e20d36a6b568f5).
- **Добавлены подарочные подписки:** покупка для другого пользователя, передача по ссылке, доставка на email и начало срока при активации. Оплаченные тариф, срок и лимиты сохраняются независимо от последующих изменений каталога. Администратор может создавать подарки без оплаты, просматривать их историю и отзывать неактивированные оплаченные подарки с возвратом фактически оплаченной стоимости на личный баланс покупателя. [0a0d9ce4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0a0d9ce4401f9b7283d3308c0e75bf1ed19738cd), [2634d527](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2634d52743e519de040838e4798fd945f9dd4438), [8a605b4f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8a605b4febd3bd848ef8286d2eb6cff1e6f2a9d1).
- **Расширены вход и безопасность аккаунта:** Google, Яндекс ID и passkey, привязка нескольких способов входа, выбор подтверждённой почты для уведомлений и смена основного email с подтверждением старого и нового адресов. Перевыпуск ссылки подписки доступен без привязанной почты: новая ссылка остаётся в приложении и при возможности отправляется по email или в Telegram. [3c626bc4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3c626bc42b52efdac620b9c5de917e0687823024), [6072ee38](https://gitlab.com/3252a8/remnawave-minishop/-/commit/6072ee384e98a25420c97dbaa77e955445debdab), [3b1067b9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3b1067b9c694b2632a8be6b90ddb618b920f3597).
- **Расширена настройка тарифов и пробного периода:** новые покупки поддерживают точное количество дней, а скрытый тариф можно назначить из админки и оставить доступным для продления его владельцу. Добавлены платная активация пробного периода и настройка перехода на оплаченный срок: сохранить оставшиеся дни trial либо начать срок с момента оплаты. [aad14cb4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/aad14cb42652d8f2ef79fe973e2fcf6c6f83c69d), [a666d271](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a666d271cdd970a40accc8dd9fcc6769bc2ed100), [91de1b61](https://gitlab.com/3252a8/remnawave-minishop/-/commit/91de1b612b79c6b32e0942c442d5be5cea8ff89f), [aded3a6a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/aded3a6a520420e252cb32dab4c7bf5c84095150).
- **Добавлены RollyPay, OxaPay и новые сценарии оформления покупки:** публичные ссылки на покупку тарифа с продолжением после входа, отмена поддерживаемых незавершённых платежей с освобождением кода активации, настройка порядка кнопок оплаты. В админке доступны ручное проведение платежа и отмена зафиксированных начислений с журналом действий и проверкой возможности безопасного отката. [b3a0b61a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/b3a0b61a5ac29165ad54ff9f6fe9ee5ea90184be), [2ba558dd](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2ba558dd21fe2bea10ed44e6eb33dd474e0f9969), [957a1255](https://gitlab.com/3252a8/remnawave-minishop/-/commit/957a1255f13f2fb38392709f0bc5d63e106ef7ba), [ea20ed68](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea20ed686b1438308f97c9235ce7ffa6592444d9), [51f34dcb](https://gitlab.com/3252a8/remnawave-minishop/-/commit/51f34dcb8f88b5ee1cb0ea11cc28bd8efcc7e358), [abd93f8f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/abd93f8f19f4d80f61579bd751c5dc340a70586d).
- **Добавлена библиотека тем и расширена настройка интерфейса:** установка тем из ZIP и публичных GitHub/GitLab-репозиториев, предпросмотр, обновление с сохранением настроек, откат и экспорт собственных копий. Доступны настройки светлого и тёмного режимов. 
- Для меню бота и Web App добавлены настраиваемые локализованные пользовательские кнопки (можно засунуть ссылку на канал и т.п.) с выбором иконки, ссылки, порядка и места отображения. [ea2d84dc](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea2d84dcea5f30c8fc82ad9bb55f882670e0ed29), [fc62f743](https://gitlab.com/3252a8/remnawave-minishop/-/commit/fc62f7435f2415bf40893d568f1f3a11fc59e821), [7ebdb48a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/7ebdb48a0adb74692fbfd99aaab7dd292f5d6646), [bd16c908](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bd16c90876f8808e1777f12c1d132f203fa97415), [1e276ca9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1e276ca9b606c57942b77aabf8e6fb31c30b3a9c).
- **Обновлён личный кабинет:** опциональная компактная (удобно если включили кучу фичей ЛК превратился в бутерброд) сводка подписки, трафика и баланса с датами сброса лимитов; раздел статуса серверов через Uptime Kuma, xray-checker или внешнюю страницу с отдельной настройкой карточки на главной. В списке устройств показываются название клиента и последняя активность. [5b5be71c](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5b5be71c90fb25f7edeae10ed3ea2372e7929fe5), [f5a010d5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f5a010d53a4a3612528f7c22ac570abfa3b7e10b), [d99101aa](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d99101aa1f4fed71206897e7d3fc5f0f42d58902), [98cf37be](https://gitlab.com/3252a8/remnawave-minishop/-/commit/98cf37beaeb11c31e36f5a70e1fe5967e59f4813), [b9326281](https://gitlab.com/3252a8/remnawave-minishop/-/commit/b93262816643957836130c197ed246a375bf8e4b), [360337b6](https://gitlab.com/3252a8/remnawave-minishop/-/commit/360337b6e1b71391dda531e9d097de2232dac7ae).
- **Добавлено управление уведомлениями:** администратор выбирает каналы Telegram/email по категориям, пользователь отдельно включает системные и рекламные сообщения для каждого канала. В письмах доступна ссылка управления email-уведомлениями без входа (можно отписаться от рассылок). Добавлены уведомления о подключении нового устройства и достижении лимита устройств, а также учёт пользователей, заблокировавших бота, при рассылках. [a02c9bc9](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a02c9bc9b8f26901ce3c2aaece2db01d83d35195), [7c932561](https://gitlab.com/3252a8/remnawave-minishop/-/commit/7c932561f07189d56f4d6ed7468d0063d1347089), [6fac76da](https://gitlab.com/3252a8/remnawave-minishop/-/commit/6fac76da4a3c2e514602ab8b08a036ec90ca07f5), [72bf7663](https://gitlab.com/3252a8/remnawave-minishop/-/commit/72bf76637f19e7414c3dc97714962d8112912895).
- **Расширены сообщения, рассылки и поддержка:** изображения в тикетах, ответах, внутренних заметках и личных сообщениях администратора; обновлены представление переписки, статусы тикетов и подробная история рассылок. Личные сообщения доступны пользователям без Telegram через email, а история отправки сохраняется в карточке пользователя. [0ca7680d](https://gitlab.com/3252a8/remnawave-minishop/-/commit/0ca7680de4005e3dfccdf04aaac019f093238101), [3df7d9ae](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3df7d9aeb4801e3ecd1b9cc2353ff120e432159e), [a4c4c0e0](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a4c4c0e06c2e3df29ee36339e5c498ec6b779b40), [995ab888](https://gitlab.com/3252a8/remnawave-minishop/-/commit/995ab8889eec21a7475bc0d67c65cfda140a4f32), [3592c727](https://gitlab.com/3252a8/remnawave-minishop/-/commit/3592c72753c89042a6956594f198d5ac331bf06a).
- **Улучшена админ-панель:** единые таблицы и мобильные карточки, поиск платежей по пользователю, подробный состав покупки и копирование идентификаторов одним нажатием. В карточке пользователя видны занятые места устройств; срок подписки можно увеличить, сократить или задать датой. Расширен журнал действий пользователя и платежных операций, сохранена история аудита. [03b2a770](https://gitlab.com/3252a8/remnawave-minishop/-/commit/03b2a7708b07cbdf9a50f7275d852deeadae3bfb), [cc7c06b8](https://gitlab.com/3252a8/remnawave-minishop/-/commit/cc7c06b8cdf7ed0a803ac6580b91c04c1e602f25), [ccb5f109](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ccb5f109a235fa1ddbb50f9defef7c978dd728d3), [766ec398](https://gitlab.com/3252a8/remnawave-minishop/-/commit/766ec3980852f05d0cca17052b55df31eea26c2b), [95ef32c5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/95ef32c5d22c54d1254d68c2ad0b213036de93d6), [bd17f2d5](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bd17f2d5964d999c8b290bd93e6f34a58af0bd0e), [a8f09d17](https://gitlab.com/3252a8/remnawave-minishop/-/commit/a8f09d175abd12ee5490dd79f620437c18c4414e).
- **Исправлены существующие сценарии оплаты и синхронизации:** обработка callback FreeKassa, проверка суммы и валюты платежей Platega/Pally, сброс вводимого кода активации при оформлении покупки. Изменения сквадов и лимитов тарифа применяются к действующим подпискам; синхронизация пользователей с панелью сохраняет целостность транзакций. [e7d4d02a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e7d4d02a81c2f64c67e0346a28852a30d3b49ce5), [e95f269a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e95f269ac515daa6e42ca1553ad8c5c858bddfc5), [1c20764a](https://gitlab.com/3252a8/remnawave-minishop/-/commit/1c20764a6ea50d5c4fe90a1d527ead1f72701f96), [595ffb34](https://gitlab.com/3252a8/remnawave-minishop/-/commit/595ffb342b5fdf510ac4dd27f8084f58208e04d8), [5475e944](https://gitlab.com/3252a8/remnawave-minishop/-/commit/5475e9443642a917bd98c350332140053bc20c01), [18a3fad7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/18a3fad72e6910fb6038c8d96ef4fc3a0c33114d), [c8841771](https://gitlab.com/3252a8/remnawave-minishop/-/commit/c88417713563a0b6ffb428a1d4062e0231a98674).
- **Обновлено восстановление резервных копий:** архив содержит версию приложения и историю миграций, а восстановление БД выполняется в отдельную пустую базу с применением недостающих миграций и последующим переключением. Прежняя база сохраняется. Пользовательские темы и настройки библиотеки включаются в резервные копии. [bb15f564](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bb15f56408748ac07c9dd15c9e1238e7fce884aa), [ea2d84dc](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea2d84dcea5f30c8fc82ad9bb55f882670e0ed29).

### При обновлении

- **Обновление тарифов и БД.** Добавлены миграции для новых способов входа, баланса, подарков, дневных периодов, уведомлений и аудита; существующие миграции не изменены. Перед переходом сохраните БД и каталог тарифов, приостановите создание новых оплат и обновите backend, worker и frontend согласованно. Старые счета и внешние регулярные подписки сохраняют календарные условия. Новые дневные заказы не оформляются через текущие адаптеры внешних подписок Tribute, Platega СБП и RollyPay; для них используются доступные разовые способы оплаты. После появления дневных заказов откат требует версии, понимающей новые поля и снимки покупок. [aad14cb4](https://gitlab.com/3252a8/remnawave-minishop/-/commit/aad14cb42652d8f2ef79fe973e2fcf6c6f83c69d).
- **Новые настройки.** Личный баланс (`USER_BALANCE_ENABLED`), Google/Яндекс/passkey и статус серверов (`SERVER_STATUS_ENABLED`) включаются отдельно; по умолчанию они выключены. Для платного trial предусмотрены `TRIAL_PAYMENT_ENABLED`, `TRIAL_PAYMENT_PRICE`, `TRIAL_PAYMENT_STARS_PRICE`, для перехода на оплаченный срок — `TRIAL_DAYS_STRATEGY`. Покупка подарков управляется `GIFTS_ENABLED` и по умолчанию включена. Четыре пользовательских переключателя уведомлений при миграции включены; глобальные ограничения администратора продолжают действовать.
- **Темы.** `WEBAPP_THEMES_DIR` должен находиться на постоянном томе с правами записи для backend. Уже установленные вручную темы продолжают поддерживаться; перевод под управление библиотеки выполняется отдельно при импорте. [ea2d84dc](https://gitlab.com/3252a8/remnawave-minishop/-/commit/ea2d84dcea5f30c8fc82ad9bb55f882670e0ed29), [bf362688](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bf3626887cf4f65a9bc952d14cc626a29bbf3beb).
- **Восстановление БД.** Восстановление через работающий HTTP-запрос заменено командой обслуживания `bash scripts/restore-backup.sh <архив.zip>` из целевой версии. Команда останавливает backend/worker; требуются права `CREATEDB` и место для двух БД. В админке остаются создание, загрузка и скачивание архивов, а также отдельное восстановление compose-папки. [bb15f564](https://gitlab.com/3252a8/remnawave-minishop/-/commit/bb15f56408748ac07c9dd15c9e1238e7fce884aa).
- **Поставка и документация.** Публикация образов перенесена в GitLab CI, основным реестром стал Docker Hub; установщик предпочитает GitLab и поддерживает альтернативные источники. Документация получила переключение стабильной/dev-версии и объединённые руководства по входу, оплате и новым функциям. [13e49987](https://gitlab.com/3252a8/remnawave-minishop/-/commit/13e499872134b7c2dd9191f3073bceaed7343ef4), [2f2a10d0](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2f2a10d0236dc8c0abcc66647cfc8255a501dfaf), [e8566271](https://gitlab.com/3252a8/remnawave-minishop/-/commit/e8566271d022233c62f80731195944f7c3cd8b0d), [246f8780](https://gitlab.com/3252a8/remnawave-minishop/-/commit/246f8780d467f5fbbac83f9345934d23589353a8), [d88e3215](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d88e32154e0cbf40b6ec594aa905f7246231ad50), [8ea3b18f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8ea3b18fb4b62823ce8767a8a2290526ce5b230b).
- **Контрибьюторы:** спасибо **BADtochka** за интеграцию статуса серверов, поддержку альтернативных источников установщика и возврат стоимости подарков: [d99101aa](https://gitlab.com/3252a8/remnawave-minishop/-/commit/d99101aa1f4fed71206897e7d3fc5f0f42d58902), [246f8780](https://gitlab.com/3252a8/remnawave-minishop/-/commit/246f8780d467f5fbbac83f9345934d23589353a8), [8a605b4f](https://gitlab.com/3252a8/remnawave-minishop/-/commit/8a605b4febd3bd848ef8286d2eb6cff1e6f2a9d1); автору **BAD.** — за участие в реализации подарочных подписок: [2fc89ecb](https://gitlab.com/3252a8/remnawave-minishop/-/commit/2fc89ecb1e0641fa7b7532ddd39cf9c1e3c7a8fc), [f2f1c0c7](https://gitlab.com/3252a8/remnawave-minishop/-/commit/f2f1c0c795c5e7f286d1e855aaed4ed083575532).

## v3.6.1 — 2026-08-18

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.6.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.6.1)

### Обзор

Добавлены гибкий checkout подписок, новый вариант выбора способов оплаты и история рассылок. Улучшены восстановление платежей, улучшение UI/UX.

### Изменения

- Добавлены гибкие лимиты в checkout периодных тарифов перед оплатой: выбор итоговых лимитов обычного и premium-трафика, дополнительных устройств, локальный предпросмотр цены и серверная котировка всей корзины.
- Переработан интерфейс редактора тарифов, добавлена поддержка настройки гибких лимитов.
- Добавлена возможность изменить внешний вид меню выбора способа оплаты: компактный выпадающий список по умолчанию или отдельные кнопки (как было раньше), сохранение порядка и иконок, отображение минимальной суммы для недоступных методов (если настроено). 
- Для провайдера Platega добавлена возможность настройки отдельной кнопки для оплаты картой.
- Усилено восстановление платежей и автопродлений: цикл и намерение отправки сохраняются до вызова провайдера, повторный запуск продолжает существующий платёж, а статусы внешних счетов сверяются перед активацией или освобождением checkout.
- Добавлена история рассылок: содержимое, аудитория, каналы, расписание, текущий статус и прогресс доставки; запланированную отправку можно перенести или отменить.
- Улучшен Mini App UX: учтены safe-area и оверлеи полноэкранного Telegram, добавлена возможность прислать кнопку входа в партнёрский раздел, плашка активации кодов размещена в самом верху раздела, кнопка открытия партнерского раздела перемещена в экран настроек при условии если другая программа активна.
- Улучшена админ-панель: исправлены показатели регистраций и плательщиков в рекламных кампаниях, добавлены анимации для графиков и улучшена легенда для графиков.
- Исправлена связь подписок с Remnawave: при нескольких совпадениях (один tg id привязан к нескольким профилям в панели) используется уже сохранённая локальная связь, синтетические маркеры пользователей не принимаются за реальную идентичность.
- Повышена устойчивость runtime-настроек: некорректная конфигурация одного провайдера больше не блокирует применение остальных значений.
- Обновлены документация и сборочные процессы: добавлен обзор отдельно подключаемого PRO-расширения, автоматизирован снимок интерфейса для README и введена проверка согласованности npm lock-файлов.

### При обновлении

- Добавлены миграции `0062`–`0065` для истории рассылок, сверки legacy-данных пользовательских кодов, снимков checkout и гибких лимитов. Существующие миграции не редактировались и не переупорядочивались.
- Mini App теперь по умолчанию использует выпадающий список способов оплаты. Предыдущее представление возвращается через `PAYMENT_METHODS_DISPLAY_MODE=buttons`.
- Добавлены необязательные настройки `PAYMENT_METHODS_DISPLAY_MODE`, `PLATEGA_CARD_ENABLED` и `PLATEGA_CARD_METHOD`; обязательных новых env-значений нет.

<details>
<summary>Ссылки на изменения и участники</summary>

* feat: flexible checkout, payment recovery and broadcast history by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/82


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.6.0...v3.6.1

</details>

## v3.6.0 — 2026-08-12

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.6.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.6.0)

### Обзор

Добавлена функция партнёрской программы, сертифицирована совместимость с Remnawave 3.x, расширены платежные сценарии и усилена надёжность установки, авторизации и восстановления данных.

### Изменения

- Добавлена настраиваемая партнёрская программа: заявки и модерация, отдельные ссылки, атрибуция клиентов, комиссии с периодом удержания, балансы по валютам, ручные выплаты и пользовательский раздел.
- Добавлена полная и смешанная оплата партнёрским балансом; реализованы резервирование средств, компенсация отменённых операций, повторная обработка и корректный учёт внешней выручки.
- Добавлена поддержка Remnawave API 3.0–3.2.3 с числовыми идентификаторами пользователей, безопасным обновлением с 2.8.1, адаптивными API-возможностями, пакетными операциями и индикатором совместимости в админке.
- Расширена Platega: дополнительные способы оплаты и рекуррентные СБП-подписки с отдельным учётом мандатов, продлений, отмен и повторных callback-запросов.
- Улучшена обработка платежей: повторное использование ожидающих checkout, соблюдение минимумов провайдеров, безопасная отмена старых счетов, устойчивые повторы hosted checkout и проверка готовности FreeKassa к созданию платежей.
- Расширены тарифы и premium-трафик: независимые стратегии сброса, корректные rolling-периоды от даты начала подписки, перенос докупленного остатка и явное различие нулевого и неограниченного лимита.
- Расширены коды активации и система приглашений: применение персональных кодов при продлении через бота, начисление обычного и premium-трафика, выбор тарифа для нового пользователя, управление видимостью ссылок и поиск кодов в рассылках.
- Улучшены Web App и админка: сортировка таблиц, новые диапазоны и состояния графиков выручки, адаптивные карточки устройств, улучшенные empty/loading-состояния, мобильная раскладка, контраст и покрытие дополнительных тем.
- Улучшены авторизация и работа с Telegram: SOCKS5-прокси для Bot API и OAuth, ограниченные сетевые ожидания, кеширование JWKS и корректный перенос истории поддержки при объединении учётных записей.
- Усилена эксплуатационная безопасность: атомарное восстановление БД с предварительным архивом, автоматическими миграциями и выравниванием sequence, диагностика разных `/app/data` mount и отдельные блокировки restore и синхронизации.
- Обновлён install wizard: проверка минимальных версий Docker, безопасное обновление Compose plugin, валидация конфигурации до запуска и поддержка удалённой Remnawave Panel за eGames с проверкой TLS-сертификатов.
- Улучшены некоторые разделы и элементы UI.

### При обновлении

- Добавлены append-only миграции `0057`–`0061`: подписки Platega, данные партнёрской программы, клиентские начисления трафика и оплата партнёрским балансом. Существующая миграция `0056` не изменена и не переупорядочена.
- Для партнёрской программы нужны `PARTNER_REQUISITES_ENCRYPTION_KEY` и `PARTNER_REQUISITES_KEY_ID`; функция по умолчанию выключена.
- Добавлены `TELEGRAM_BOT_PROXY_URL` и `TELEGRAM_OAUTH_USE_BOT_PROXY`.
- Минимальные требования установщика: Docker Engine 25.0+ и Docker Compose plugin 2.20.2+; отдельная команда `docker-compose` больше не считается поддерживаемым runtime.
- Обновлены OpenAPI, типы frontend, каталог событий и манифест настроек.
- Контрибьюторы: `wormy09` (`5eb78c87`) — перенос истории поддержки при объединении учётных записей; `dependabot[bot]` (`632603f9`) — обновление frontend-зависимостей.

<details>
<summary>Ссылки на изменения и участники</summary>

* fix: reassign support history when merging accounts by @wormy09 in https://github.com/3252a8/remnawave-minishop/pull/75
* build(deps): bump the npm_and_yarn group across 2 directories with 1 update by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/78
* feat: partner program, Remnawave 3.x and expanded payments by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/81


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.8...v3.6.0

</details>

## v3.5.8 — 2026-07-31

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.8) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.8)

### Обзор

Новый платёжный провайдер Tribute, безопасные повторы автопродления YooKassa, сверка и возобновление незавершённых оплат, ежемесячное начисление трафика за HWID-пакеты, быстрое применение premium-лимита с разрывом сессий, улучшения интерфейса: редактор сообщений с кнопками в рассылках/поддержке/карточке пользователя и расширяемая навигация админки.

### Изменения

- Добавлен платёжный провайдер **Tribute**: основной режим Shop API с динамическим заказом на локальную сумму (разовые и рекуррентные заказы, трафик, premium-трафик, HWID-устройства, доплата за смену тарифа), резервный режим Creator subscriptions и Digital Products, единый webhook `/webhook/tribute` с проверкой HMAC-SHA256, кнопка «Подтянуть из Tribute» в редакторе тарифа со сверкой цен и валют, логотип и раздел настроек провайдера.
- Добавлены безопасные повторы автопродления YooKassa: очередь циклов с неизменяемыми суммой, картой и телом запроса, технические повторы только с тем же `Idempotence-Key` в 30-минутном окне, не более одной финансовой попытки после подтверждённого `canceled`, dry-run по умолчанию, резервный планировщик без panel webhook, событие `subscription.auto_renew_failed` и уведомление пользователю о запланированном повторе; исправлены поля чека рекуррентного платежа.
- Добавлены сверка и возобновление оплат: карточка незавершённой оплаты в Mini App с продолжением по сохранённой ссылке, приоритет незавершённого платежа в выдаче, подстановка ранее введённого кода в checkout, воркеры сверки истёкших заказов у Wata, CryptoPay, Stripe, LAVA, Pally, PayKilla и SeverPay, включая заказы без сохранённой ссылки.
- Добавлено ежемесячное начисление трафика для HWID-пакетов (`traffic_bonus_gb` на пакет): начисление фиксируется в платеже и записи докупки, складывается по активным докупкам, живёт по `valid_from`/`valid_until` и переживает месячный сброс панели; добавлен одноразовый скрипт пересчёта основных лимитов трафика по всему парку подписок.
- Восстановлена tariff-aware докупка устройств: единый сервис доступности для бота и Web App с точной причиной блокировки (раздел выключен, нет активной подписки, тариф отсутствует/выключен/сменился, безлимит, нет пакетов), повторная проверка перед выставлением счёта и диагностика причины, по которой оплаченная докупка трафика не была зачислена.
- Улучшено применение premium-лимита: быстрая перепроверка подписок с расходом от `TARIFF_PREMIUM_FAST_WATCH_PERCENT` между полными тиками воркера, разрыв уже установленных сессий на premium-нодах через `POST /api/ip-control/drop-connections` с cooldown, защита от неполной статистики нод и предупреждение в диагностике админки о нодах без `CAP_NET_ADMIN`.
- Добавлена диагностика конфликтов с панелью: при перезаписи лимитов устройств или трафика сторонним писателем синхронизация подписки приостанавливается и попадает в health-панель; добавлен снимок payload панельных webhook-ов, дедупликация повторяемых событий по содержимому, отклонение некорректных ответов API панели и корректная трактовка статуса `LIMITED` как активной подписки.
- Расширена работа с сообщениями: общий контракт составления сообщения для рассылки, поддержки и плагинов; текст и подписи кнопок задаются на каждом языке; до четырёх кнопок — ссылка, код активации в боте, код в Mini App, произвольная цель Mini App и именованный экран приложения; добавлен маршрут checkout, открывающий выбор тарифа и периода; аудитория рассылки сгруппирована, снабжена иконками и дополнена выбором конкретного тарифа, включая аудитории от расширений; сообщение одному пользователю отправляется прямо из карточки.
- Переведены поддержка и рассылки на визуальный редактор: форматирование в подмножестве HTML, понятном Telegram, кликабельные ссылки в старых сообщениях, счётчик по видимому тексту, у администратора — переключатель исходного HTML, шорткоды персонализации, меню «Вставить» с персональными ссылками пользователя и кнопки под ответом; ожидающие тикеты видны в боковой панели.
- Расширена админ-панель и улучшен интерфейс: расширения добавляют группы навигации, вкладки в существующие разделы и вкладки карточки пользователя, изменено расположение некоторых разделов админки, отображение источника значения настройки (БД или `.env`), раздел сверки привязки подписок к тарифам с безопасным восстановлением, предпросмотр результата смены тарифа и сброс ссылки подписки из карточки; списки перерисованы карточками на узких экранах, за открытым оверлеем остаётся один живой скроллер.
- Добавлен перевыпуск ссылки подписки: маршрут Web App с отправкой новой ссылки и инструкции на email, диалог подтверждения и кнопка в настройках, а также сброс ссылки администратором из карточки пользователя.
- Разделены персональные и общие коды активации: у кода появился необязательный владелец, список группирует общие коды и помечает одноразовые, выпадающий список кнопок сообщения разделяет оба вида, а история показывает клиенту, для кого код был выпущен.
- Улучшены Mini App и API: код экрана загружается при открытии (сборка модулем с code splitting), все ответы `/api/` помечаются `no-store`, чтобы WebView Telegram не отдавал устаревшие данные, сохраняется навигация при первичной загрузке и deep-link в админке.
- Исправлены биллинг и подписки: заморозка расчёта доплаты за смену тарифа на момент оплаты, проверка фактически сохранённых прав в панели, сохранение состояния dry-run активации, сохранение даты начала подписки при продлении, снятие trial-сквадов при платной активации, синхронизация лимита устройств при смене тарифа, оплата Stars только из Telegram Mini App, корректный формат цены при вводе кода для выбранного провайдера и обновление настроек воркера torrent-блокировки.
- Обновлены установщик и эксплуатация: отдельный шаг проверки интеграции с Remnawave Panel (безопасный запрос `/system/stats`, проверка формата `PANEL_API_COOKIE`, пропуск шага вместо `change_me`), ожидание готовности upstream прокси, фильтр webhook-секрета в логах Caddy, сохранение каталога тарифов в архиве бэкапа и его восстановление; один некорректный env провайдера больше не отключает применение всех сохранённых настроек, а панель показывает список `not_applied`.
- Добавлена настройка лимита устройств для пробного периода; обновлены зависимости (astro, js-yaml, brace-expansion), ruff зафиксирован во всех quality-gate, CI уведомляет настроенных потребителей образов.
- Исправлена выдача premium-сквадов существующим владельцам тарифа, если premium_squad_uuids настроены без premium_monthly_gb и пакетов дополнительного трафика.

### При обновлении

- **Миграции БД 0046–0056** (аддитивные, существующие не менялись): атрибуция рекуррентных платежей, снимки начисления трафика HWID, владелец кода активации, rich-body сообщений поддержки, состояние webhook Tribute, снимки расчёта смены тарифа, снимки прав панели, восстановление дат начала активных подписок, жизненный цикл checkout, состояние повторов автопродления, аудит привязки тарифов.
- **Новые переменные окружения** в `.env.example`: `AUTO_RENEW_RETRY_ENABLED`, `AUTO_RENEW_RETRY_DRY_RUN`, `AUTO_RENEW_SCHEDULER_ENABLED`, `AUTO_RENEW_MAX_FINANCIAL_ATTEMPTS`, `AUTO_RENEW_MAX_TRANSPORT_REPLAYS`, `AUTO_RENEW_WORKER_TICK_SECONDS`, `AUTO_RENEW_WORKER_BATCH_SIZE`, `AUTO_RENEW_RETRY_GRACE_HOURS`, `AUTO_RENEW_SCHEDULER_LEAD_HOURS`. Включать поэтапно: сначала `AUTO_RENEW_RETRY_ENABLED=True` при `AUTO_RENEW_RETRY_DRY_RUN=True`, проверить логи воркера, затем снять dry-run.
- Задокументированы, но не добавлены в `.env.example`: `TRIBUTE_*` (настраиваются в админке), `TARIFF_PREMIUM_FAST_*`, `TARIFF_PREMIUM_DROP_CONNECTIONS*`, `HWID_DEVICE_TRAFFIC_BONUS_GB` (устаревший fallback, новые начисления — в `tariffs[].hwid_device_packages`).
- Для разрыва сессий при исчерпании premium-лимита ноды Remnawave должны быть запущены с `CAP_NET_ADMIN` (`cap_add: NET_ADMIN`), иначе уже установленные соединения продолжат работать.
- Рекуррентный Shop Order Tribute фиксирует цену на стороне Tribute: не отключайте, не удаляйте и не переименовывайте тариф и не меняйте `TRIBUTE_SHOP_ID`, пока к ним привязаны активные заказы.
- Включение начисления трафика HWID на существующем парке требует одноразового прогона `backend/scripts/resync_traffic_limits.py`.
- Контрибьюторы: @wormy09 — перевыпуск ссылки подписки (`fc73adbf`, `04f029c9`, `66c06731`), ежемесячное начисление трафика HWID и скрипт пересчёта (`fab09cb8`, `24735eee`), трактовка статуса `LIMITED` (`1ef4751b`), диагностика незачисленной докупки (`112c4b2c`), перевод подсказок оверрайдов (`c5d0d287`), приведение к текущему ruff (`240709e8`, `0439829f`). Обновления зависимостей — @dependabot (`3a94667e`, `e619c83f`).

<details>
<summary>Ссылки на изменения и участники</summary>

* feat(webapp): перевыпуск ссылки подписки из Mini App с доставкой на email by @wormy09 in https://github.com/3252a8/remnawave-minishop/pull/63
* fix(i18n): заполнить пустые admin-подсказки оверрайдов трафика by @wormy09 in https://github.com/3252a8/remnawave-minishop/pull/65
* build(deps): bump astro from 7.0.9 to 7.1.3 in /docs-site in the npm_and_yarn group across 1 directory by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/66
* feat(devices): ежемесячное начисление трафика за активные докупленные HWID-устройства by @wormy09 in https://github.com/3252a8/remnawave-minishop/pull/64
* chore(lint): satisfy current ruff on dev by @wormy09 in https://github.com/3252a8/remnawave-minishop/pull/69
* fix(sync): treat LIMITED panel status as an active subscription by @wormy09 in https://github.com/3252a8/remnawave-minishop/pull/68
* build(deps): bump astro from 7.0.9 to 7.1.4 in /docs-site in the npm_and_yarn group across 1 directory by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/67
* Tribute payments, safe auto-renew recovery, checkout resume and admin messaging by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/70
* fix(tariffs): sync unrestricted squad access by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/71

**Участники**
* @wormy09 made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/63

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.7...v3.5.8

</details>

## v3.5.7 — 2026-07-18

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.7) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.7)

### Изменения

- Добавлены opt-in уведомления по отчётам Torrent Blocker через Telegram и email: раздельное управление каналами, cooldown, опциональный вывод IP, локализованные шаблоны и настройки в админке. Webhook проверяется по типизированной схеме; устаревшие и повторные события подавляются, а сбой одного канала не повторяет успешную доставку другого (спасибо @rez-code, `6d559679`).
- Расширены фильтры пользователей в админке: зарегистрированные сегодня, приглашённые, с активной, неактивной, истёкшей, оплаченной, пробной или выданной без платежа подпиской. Счётчики дашборда открывают соответствующий список, а фильтры сохраняются в URL.
- Улучшены интерфейсы дашборда, логов и списков: унифицированы карточки и скелетоны загрузки, добавлены счётчик логов и очистка фильтра, скорректированы мобильные таблицы и высота строк.
- Исправлен опрос статусов Wata: поиск переведён на `/v2/transactions`, финальные статусы объединены в один запрос, параллельные GET-запросы группируются и кэшируются на объект, задержка из `Retry-After` соблюдается.
- Добавлены `legacy_keys` для тарифов: сохранённые платежи и подписки продолжают обрабатываться после переименования ключа. Алиасы проверяются на уникальность, редактируются в админке и включены в API-контракт.
- Нормализованы ссылки поддержки в Telegram-меню: `@username` и `t.me/username` автоматически преобразуются в полные HTTPS-ссылки.
- Исправлены фоновые интеграции: блокирующее чтение очереди Redis больше не конфликтует с таймаутом клиента, а синхронизация подписок отличает обновление `last_connected_at` от изменения основных полей.
- Обновлены документация, граф знаний и точечные тесты для новых настроек, фильтров, тарифных алиасов, Wata, Redis и доставки уведомлений.

### При обновлении

- Добавлены переменные `TORRENT_BLOCKER_NOTIFICATIONS_ENABLED`, `TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED`, `TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED`, `TORRENT_BLOCKER_NOTIFICATION_COOLDOWN_SECONDS` и `TORRENT_BLOCKER_NOTIFICATION_INCLUDE_IP`. Общий переключатель по умолчанию выключен.
- Для получения событий нужны Remnawave Panel/Node 2.7+, Xray-Core 26.3.27+, настроенный Node Plugin, `NET_ADMIN`, nftables и совпадающий `PANEL_WEBHOOK_SECRET`.
- API-контракт расширен полем `legacy_keys`; OpenAPI, frontend-типы и манифест настроек обновлены. Миграции БД не затронуты.
- Контрибьютор: @rez-code (`6d559679`) — уведомления Torrent Blocker.

<details>
<summary>Ссылки на изменения и участники</summary>

* feat(notifications): add torrent blocker alerts by @rez-code in https://github.com/3252a8/remnawave-minishop/pull/60
* Dev by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/62

**Участники**
* @rez-code made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/60

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.6...v3.5.7

</details>

## v3.5.6 — 2026-07-16

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.6) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.6)

### Обзор

Расширено управление тарифами, улучшены поддержка и согласованность подписок, усилена обработка платежей и webhook-очередей.

### Изменения

- Расширено управление тарифами: добавлена сортировка тарифов перетаскиванием, определяющая порядок на витрине, переработана секция тарифов в админке.
- Добавлена отдельная стратегия сброса трафика для каждого тарифа. Она применяется при создании пользователя панели, активации, продлении и смене тарифа; старые каталоги продолжают использовать глобальную настройку.
- Улучшена поддержка: добавлены индикатор набора текста и статусы прочтения, предотвращена повторная отправка ответа, исправлена прокрутка диалога на мобильных устройствах.
- Исправлена согласованность подписок с Remnawave: корректно выдаётся пробный доступ, проверяются сохранённые права в панели, заменяются управляемые squads при смене тарифа и пересчитывается перенос трафика после перепривязки пользователя.
- Повышена устойчивость YooKassa: worker восстанавливает платежи при задержанных или потерянных webhook-событиях, поддерживает старый сценарий автопродления, сохраняет данные платёжного метода и не допускает блокировки очереди неразрешимыми записями.
- Исправлена идентификация платежей: внешние ID теперь уникальны в пределах провайдера, а поиск выполняется с учётом провайдера; унифицированы локализованные описания.
- Усилена webhook-очередь: дедупликация постановки стала атомарной, подтверждение выполняется после обработки, а временные ошибки повторяются до помещения события в dead-letter очередь.
- Перенесено шифрование ссылок Happ Crypt4 в core: ссылки формируются локально через совместимую RSA-реализацию без зависимости от API панели.
- Восстановлены русские значения по умолчанию через locale-файлы для названий способов оплаты, описания подписки и Premium-секции; исходный код и runtime fallback оставлены на английском.
- Добавлен готовый Angie reverse-proxy профиль с автоматическим ACME/TLS, поддержкой install wizard и документацией; разделены внешний и внутренний webhook-порты. Спасибо @alldevic (`590cce65`).
- Усилена цепочка выпуска Docker-образов: проверяются источник и состояние релиза, создаётся provenance-attestation, проверяются digest и метаданные, а promotion формирует неизменяемый манифест образов.
- Обновлены Remnawave dev preset до 2.8.1, backend/frontend/docs-зависимости и архитектурные проверки; расширены точечные тесты платежей, очередей, подписок, поддержки и тарифов.

### При обновлении

- Добавлена append-only миграция `0045_scope_provider_payment_ids`, меняющая уникальность `provider_payment_id` на пару `(provider, provider_payment_id)`.
- Добавлен `WEB_SERVER_INTERNAL_PORT`. В нестандартных Compose-конфигурациях нужно проверить соответствие host-порта `WEB_SERVER_PORT` внутреннему listener-порту.
- Очередь получила параметры `WEBHOOK_QUEUE_MAX_ATTEMPTS`, `WEBHOOK_QUEUE_RETRY_BASE_SECONDS` и `WEBHOOK_QUEUE_RETRY_MAX_SECONDS`; значения по умолчанию — `5`, `1.0` и `30.0`.

<details>
<summary>Ссылки на изменения и участники</summary>

* ci: harden release image provenance by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/55
* fix(ci): publish release manifests from promotion jobs by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/56
* feat(deploy): add Angie reverse proxy profile with native ACME auto-TLS by @alldevic in https://github.com/3252a8/remnawave-minishop/pull/57
* tariff controls, support presence and resilient payments by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/58

**Участники**
* @alldevic made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/57

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.4...v3.5.6

</details>

## v3.5.4 — 2026-07-14

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.4) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.4)

### Обзор

Усилены платёжные сценарии, конкурентная обработка аккаунтов и установщик; улучшены админские превью и переходы из support-уведомлений.

### Изменения

- Усилено подтверждение платежей: перед активацией сверяются подтверждённые провайдером сумма, валюта и финальный статус; недоплата и другая валюта отклоняются, а переплата активирует только исходный заказ. Для криптоактивов сохранена точная десятичная величина, для fiat применяется корректное округление.
- Сериализовано успешное завершение платежей: блокировки и условные обновления предотвращают повторную активацию заказа и повторные уведомления при конкурентных webhook-запросах и обновлениях статуса.
- Перепроверяются актуальные расчёты и разрешённые режимы смены тарифа перед Telegram-платежом; состав заказа берётся из сохранённой записи, а не из callback-метаданных. В комбинированных платежах стоимость устройств отделена от стоимости подписки.
- Усилены операции с аккаунтами и одноразовыми действиями: слияния выполняются под стабильными блокировками, повторное применение одного пользовательского кода между аккаунтами отклоняется, оплаченные периоды сохраняются, а периоды без оплаты не суммируются. Email-коды и magic links потребляются однократно.
- Улучшен install wizard: обязательные TLS-вводы теперь прерывают сценарий при ошибке, Caddy/Nginx проверяются на публикацию портов и доступность upstream-сервисов, повреждённое сетевое подключение proxy восстанавливается. После успешного импорта исходная БД отключается от целевой сети, права на данные восстанавливаются, а старый Remnashop предлагается остановить без удаления данных.
- Расширен Plugin API: добавлена версия API v1 с проверкой диапазона совместимости до запуска hook-ов, стабильный UUID установки и строгий выбор единственного entitlement provider. Админские extension-секции могут оставаться видимыми в заблокированном состоянии.
- Улучшены админка и support-сценарии: Telegram-превью рассылки для админа теперь включает настроенные кнопки, а ссылки на тикет и карточку пользователя из групповых support/log-уведомлений открывают нужный маршрут в Mini App.
- Усилена защита web-сценариев: заблокированные пользователи больше не могут продолжать админскую сессию; за Cloudflare реальный IP webhook-клиента принимается только после проверки ближайшего proxy-hop по официальным сетям Cloudflare.
- Усилен выпуск Docker-образов: базовые образы закреплены по digest, runtime переведён на Ubuntu 24.04 с Python 3.12, добавлены SBOM/provenance и полное Trivy-сканирование. Релизные теги публикуются продвижением уже проверенного digest в GHCR и Docker Hub.

### При обновлении

- Loader теперь завершает запуск при нескольких entitlement provider или несовместимом объявленном диапазоне Plugin API. Внешним плагинам рекомендуется явно указывать диапазон, включающий v1.
- Производным Docker-образам, зависящим от деталей `python:3.12-slim`, нужно учесть переход backend/worker runtime на Ubuntu 24.04.

<details>
<summary>Ссылки на изменения и участники</summary>

* harden payments, accounts and install flow by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/54


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.3...v3.5.4

</details>

## v3.5.3 — 2026-07-10

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.3) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.3)

### Обзор

Главные темы: переработка админских рассылок (редактор, персонализация, inline-кнопки, email-канал), новый платёжный провайдер Overpay и ссылки/логотипы провайдеров в разделе настроек, поддержка раздельного (frontend/backend) деплоя с защищённым upstream, ручные squad-override'ы на пользователя, настраиваемая стратегия сброса трафика и серия фиксов переходов тарифов/квот.

### Изменения

- Переработаны админские рассылки: rich-text редактор с персонализацией через шорткоды, до 4 inline-кнопок (ссылка / применение кода активации в боте или Web App) с сортировкой, тест-аудитория «администраторы».
- Добавлены настройки email-канала в веб админке.
- Добавлен платёжный провайдер Overpay; 
- В админке и Web App показываются ссылки на сайты платежных провайдеров и их логотипы для удобства; интеграция CryptoPay переведена на собственный HTTP-клиент вместо уязвимой SDK-зависимости (снят потолок `certifi<2024`);  локализованы настройки провайдеров.
- Добавлена защита от дублирования сообщений о платежах в админских логах.
- Добавлена поддержка раздельного деплоя frontend/backend: browser-visible API base, защищённые upstream'ы через edge-токен (инъекция доверенным прокси, не браузером), новые примеры окружений `rathole` и `split-protected-upstream`, унифицированное именование docker-сетей в compose-примерах (спасибо @BADtochka, `a238319`, `c563543`).
- Добавлены ручные panel-squad-override'ы на пользователя: назначенные вручную сквады сохраняются при синхронизации с панелью, с отдельными контролами и раскладкой в карточке пользователя.
- Добавлена настраиваемая стратегия сброса трафика на пользователя с выравниванием периодов сброса; в сводке трафика Web App отображается текущая стратегия и её якоря.
- Добавлен поиск по настройкам в админке; карточка пользователя и манифест настроек разбиты на секции (danger-действия всегда последними, invite-only вынесено в общие настройки).
- Добавлены базовые сигналы активности ядра: доменные события `bot.started` и `plans.viewed` и отслеживание последнего подключения на панели (`subscription.last_connected_at`).
- Исправлены переходы тарифов и учёт квот: правила квот при смене тарифа, защита от сбоев синхронизации entitlement'ов, сохранение ручных HWID-лимитов и premium top-up баланса под override, раздельный учёт trial-квоты и трафика на панели, конверсия при переключении HWID-тарифа.
- Улучшен Web App: активация кодов, начисляющих дополнительный период, по deeplink без лишнего подтверждения (и пояснение вместо ошибки checkout для таких ссылок), отдача ассетов через Brotli, устранён зависон при загрузке, отполирована сводка трафика; восстановлены локальные напоминания об истечении подписки.
- Обновлён установщик и деплой: подключение к существующему Nginx/Caddy и переключатель Pangolin, миграция баз tgshop через дампы, защита от рассинхрона пароля БД и усиленная диагностика старта миграций.
- Обновлена документация и dev-тулинг: refresh API reference и plugin contract, воркфлоу и артефакты graphify (граф кодовой базы), CI-гард синхронизации OpenAPI.

### При обновлении

- Схема БД: добавлены append-only миграции `0042_release_archived_promo_codes`, `0043_add_user_panel_squad_overrides`, `0044_add_subscription_last_connected_at`. Существующие миграции не менялись.
- Новые переменные окружения (см. `.env.example`): `WEBAPP_API_BASE_URL`, `WEBAPP_BACKEND_UPSTREAM`, `WEBAPP_BACKEND_UPSTREAM_HOST`, `MINISHOP_EDGE_TOKEN`, `MINISHOP_EDGE_TOKEN_HEADER` — для раздельного деплоя и защищённого upstream.
- Зависимости: удалены `aiocryptopay` и пин `certifi<2024`, `certifi` поднят до `>=2024.7.4`; CryptoPay работает через собственный клиент. Обновлён frontend `package-lock.json` (tiptap-редактор).
- Docker: обновлён frontend nginx (edge-токен, split upstream) и Dockerfile; изменены compose-файлы и добавлены примеры деплоя.
- Контрибьюторы: @BADtochka — раздельный API base и именование docker-сетей (`a238319`, `85a9160`, `a122c73`, `0be145b`, `c563543`, `e9dbb18`).

<details>
<summary>Ссылки на изменения и участники</summary>

* feat: support split backend API base by @BADtochka in https://github.com/3252a8/remnawave-minishop/pull/52
* broadcast overhaul, Overpay provider and split-deploy support, plan changes fixes by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/53


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.2...v3.5.3

</details>

## v3.5.2 — 2026-07-03

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.2) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.2)

### Обзор

Релиз преимущественно архитектурный: 
- унификация платёжных провайдеров через общий link-flow, 
- полный перевод фронтенда на TypeScript + Svelte 5 runes, 
- типизация и линт всего репозитория — плюс пользовательские фиксы пополнения трафика, инструкций установки и авторизации Web App.

### Изменения

- Исправлено пополнение трафика в боте: восстановлен обработчик кнопки покупки (потерянный при разделении subscription-core), кнопка в меню теперь скрыта, пока не израсходовано ≥80% лимита (как в мини-аппе), а по устаревшей кнопке показывается остаток трафика и меню обновляется вместо тихого отказа. Добавлен общий gate доступности для обычного и premium-трафика; метки и подсказки переключателей вынесены в локализацию.
- Добавлены ссылки на инструкцию установки в карточке пользователя админки (с копированием); авторизованный роут инструкций повторно запрашивает свежий short UUID панели, если сохранённый устарел после сброса ссылки на стороне панели, — чтобы squad-специфичные конфиги не откатывались к общему дефолту.
- Исправлены Web App UI и авторизация в некоторых сценариях: скрытие неактивных вкладок и обновление кэша устройств, ограничение зависших auth-запросов, запуск listener'а Web App до стартовых обращений к Telegram, использование дат сброса из панели в предупреждениях о трафике.
- Отладочные логи действий отправляются в log chat; добавлен сервис доставки уведомлений `message_log_notifier`.
- Платёжные провайдеры переведены на общий link-flow: CloudPayments, Pally и Platega ходят через единый флоу оплаты, callback-флоу YooKassa разделены на отдельные модули, добавлены variant-aware контекст и pre-create хук колбэка, общие helper'ы безопасности вебхуков и per-profile дескрипторы Wata.
- Фронтенд полностью переведён на TypeScript и Svelte 5 runes: мигрированы оставшиеся webapp/admin/entry-модули и тест-сьюты, типизированы сторы, координаторы и компоненты, добавлен архитектурный гейт «no first-party JS», крупные компоненты разбиты (PaymentDialogs, mockApi, previewMock, AppModeContent).
- Ужесточены типобезопасность и линт: mypy покрывает весь репозиторий (`scripts`, `backend/scripts` и всё дерево `tests/`), allowlist `type: ignore` сокращён до одной граничной записи; включён полный набор ruff-семейств (UP, W, C4, SIM, PIE, PERF, RUF, LOG, G, PLE, T10); pytest переведён в warnings-as-errors, покрытие — на branch-режим с ратчетом.
- Декомпозированы крупные модули: `user_dal` разбит на reads/merge/mutations, мигратор — на пакет (chains + engine, порядок id пинится snapshot-тестом), `import_legacy` — на пакет; разделены webapp guides, каталог тем webapp, редактирование кодов активации в админке; вынесена общая доставка уведомлений о трафике тарифов для воркеров.
- Типизированы ответы admin-эндпоинтов тарифов, оставшиеся «свободные» схемы дотипизированы или помечены как non-JSON; `openapi.json` и `openapi.generated.ts` регенерированы.
- Добавлен no-op observability seam — внутренняя точка расширения без изменения поведения.
- Обновлены dev/deploy: dev-окружение поднимается одной командой, зафиксированы версии Node и инструментов, healthcheck чаще опрашивает контейнер при старте, восстановлена совместимость lockfile с npm 10.
- Обновлена документация: английские точки входа для контрибьюторов, освежённые architecture-доки, задокументирован gating пополнения трафика и требование локализованного пользовательского текста; удалён `CHANGELOG.md` (история — в коммитах и PR).

### При обновлении

- Изменений схемы БД, миграций и переменных окружения в релизе нет: мигратор только реструктурирован в пакет (41 миграция, id и порядок сохранены, зафиксированы snapshot-тестом). Ручных шагов при обновлении не требуется.
- Фронтенд теперь TypeScript-only, а версии Node и инструментов закреплены — контрибьюторам нужен соответствующий Node.

<details>
<summary>Ссылки на изменения и участники</summary>

* link-flow payments, all-TypeScript frontend, repo-wide typing & fixes by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/50


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.1...v3.5.2

</details>

## v3.5.1 — 2026-07-01

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.1)

### Изменения

- Расширена система кодов активации: процентная корректировка стоимости тарифа, множители срока и трафика, начисление дополнительного периода, режим применения только при оплате, условия применимости (минимальный срок/трафик, область применения — весь заказ или оформление) и архивирование кодов.
- Добавлена фиксация эффектов и оформления: при активации кода и при оформлении заказа сохраняются снапшоты применённых эффектов, базовая сумма, корректировка, оплачиваемый срок и объём трафика — для истории и корректных расчётов.
- Добавлены аудит активаций кодов и генерация ссылок для применения кода (для бота и webapp) в админке.
- Добавлена совместимость с Remnawave 2.8: переработан обработчик вебхуков панели, добавлены хелперы node- и HWID-API, версионированные пресеты dev-стенда (2.7.4 и 2.8.0).
- Реализован учёт настроек сброса трафика в тарифных воркерах и уведомлениях: детали сброса в предупреждениях, защита уведомлений о сбросе.
- Ускорен и стабилизирован админ-раздел: оптимизированы загрузка и отзывчивость панели, списки пользователей без лишних преобразований, модернизированы паттерны реактивности Svelte (runes).
- Улучшены редакторы тарифов и кодов: вкладки редактора тарифов, компактный редактор кодов, режим начисления периода, сохранение изменений каталога тарифов и загруженных ассетов оформления, отображение безлимитных лимитов.
- Улучшена авторизация: fallback bearer-токена сессии, требование session-токенов в контрактах.
- Исправлены UI-баги админки и webapp.
- Исправлена совместимость импорта с remnashop: безопасный разбор trial-флагов, сохранение назначения тарифа для trial-подписок, сохранение приватных полей admin-бандла, разбор ответа HWID-устройств.
- Обновлён стек тулинга и зависимостей: postgres зафиксирован на 17.6, redis-клиент 7.4.1, обновления prettier-plugin-svelte, tailwind и typescript-eslint; расширены unit/contract/integration тесты.

### При обновлении

- Изменения схемы БД: миграции `0038`–`0041` (расширение эффектов кодов, снапшоты активаций и оформления заказа, флаг режима начисления с оплатой). Append-only, применяются идемпотентным мигратором автоматически.
- Образ postgres зафиксирован на `17.6` — обновите тег, если пиннингуете образ в своём compose вручную.
- Совместимость с Remnawave 2.8; для dev-стенда добавлены пресеты 2.7.4/2.8.0. Новых обязательных production-переменных окружения нет.

<details>
<summary>Ссылки на изменения и участники</summary>

* Feature/bonus extension by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/47
* Feature/remnawave 2.8.0 by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/48
* Activation-code effects, Remnawave 2.8 support and admin panel updates by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/49


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.5.0...v3.5.1

</details>

## v3.5.0 — 2026-06-27

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.5.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.5.0)

### Обзор

Помимо нескольких пользовательских функций (контроль доступа к регистрации, premium-правила пробного периода, доступ к меню бота, уведомления о сбросе квоты трафика) релиз содержит очень крупный внутренний рефакторинг — типизация контрактов, миграция фронтенда на Svelte 5 runes, декомпозиция god-файлов и пакетирование платёжных провайдеров.

### Изменения

- Добавлен контроль доступа к регистрации (`REGISTRATION_INVITE_ONLY_ENABLED`): при включении новые публичные регистрации допускаются только по валидной пригласительной ссылке; существующие пользователи продолжают входить через Telegram, Web App, email-код, magic-link и пароль.
- Добавлены правила premium-доступа в пробном периоде: отдельный лимит premium-трафика (`TRIAL_PREMIUM_TRAFFIC_LIMIT_GB`) и список premium Internal Squads для trial (`TRIAL_PREMIUM_SQUAD_UUIDS`), с применением квоты к premium-сквадам.
- Добавлена возможность выключения меню Telegram-бота (оставляет минимальное количество кнопок и побуждает использовать веб апп).
- Добавлены уведомления о сбросе квоты трафика для regular- и premium-тарифов — для пользователей, которые потратили (или почти потратили) трафик в предыдущем периоде.
- Исправления платежей: сохранение статуса успешного платежа, детали неуспешных попыток, отображение единиц entitlement в логах, подавление устаревших уведомлений о сбое оплаты, предотвращение циклов импорта при старте провайдеров.
- Исправления Admin/Mini App: рендер строк datatable после первой загрузки, корректные surface-токены светлой темы, центрирование спиннера логотипа, уточнены подписи настроек, защита от no-op обновлений стора.
- Улучшена диагностика install-wizard.

### Рефакторинг и инфраструктура

- **Типизированные HTTP-контракты и OpenAPI:** pydantic request/response-модели для admin- и webapp-роутов (вместо «свободных» схем), генерация `docs/openapi.json` и `frontend/.../openapi.generated.ts`, типизированные path-builders API-клиента, реестр route-contracts и проверки контрактов в CI.
- **Контракты доменных событий:** одна pydantic-модель на событие (`extra="forbid"`), публикация через `emit_model`, регенерируемый каталог событий.
- **Миграция фронтенда на Svelte 5 runes:** все компоненты и сторы переведены на runes, удалён legacy-синтаксис (`export let`, `$:`, слоты и динамические компоненты → snippets), runes-only режим закреплён сборкой и линтом, убран datatable runes-bridge.
- **Декомпозиция `App.svelte`:** shell-state стор на runes и вынос десятков runtime/action/helper/view-модулей (boot, resume, auth, activation, telegram, navigation, billing-deeplink и др.), оболочка приложения переведена на TypeScript.
- **Типизация бэкенда (mypy ratchet):** handlers, services, payment providers, db, middlewares, config, keyboards и web-плагины; mypy зелёный по всему enforced-скоупу, скоуп расширен в CI.
- **Пакетирование платёжных провайдеров:** каждый провайдер — отдельный пакет (yookassa, stripe, wata, paykilla, heleket, platega, lava, severpay, freekassa, pally, cryptopay, cloudpayments, stars), общий link-flow engine + provider descriptor, общая обработка webhook'ов, import-only фасады и conformance-контракты.
- **Декомпозиция god-файлов:** разбиты admin-секции, email-шаблоны, tariff-traffic worker, panel API service, subscription lifecycle, admin sync workflow, user start flow, subscription core и billing/auth/asset-роуты.
- **Границы архитектуры:** проверки import-границ фасадов и runtime-хабов, отвязка фасадов от runtime-импортов, типизированные settings-views в `config`, гейты согласованности web-ответов, заморозка публичных поверхностей фасадов тестами.
- **Тесты и QA:** реорганизация набора по ответственности, Vitest-coverage, Playwright mock-smoke e2e-гейт, единый dev/QA compose-стенд, контракты webhook/link-flow провайдеров.
- **Инфраструктура и тулинг:** нормализация LF-окончаний через `.gitattributes`, агрегирующие команды качества, выравнивание root-check-скрипта с гейтами CI, contract-checks в CI.
- **Документация:** интерактивный API reference на docs-site, how-to рецепты (провайдер/событие/эндпоинт), гайды контрибьютора и агента, обзор архитектуры, security scaffolding.

### Зависимости и безопасность

- **Security-фикс (high):** `@playwright/test` поднят с `^1.50.1` до `^1.55.1` (lockfile резолвится в 1.61.1) — закрывает GHSA-7mvr-c777-76hp (Playwright скачивал и устанавливал браузеры без проверки подлинности SSL-сертификата). Открытых Dependabot-алертов: 0.
- **Backend:** `sqlalchemy[asyncio]` 2.0.49 → 2.0.51 (patch), YooKassa SDK 3.10.1 → 3.11.0 (minor); ранее в диапазоне — `pydantic-settings` 2.14.1 → 2.14.2.
- **Frontend dev-тулинг до актуальных версий:** eslint 10.6.0, svelte 5.56.4, vite 8.1.0, svelte-check 4.7.1, typescript-eslint 8.62.0, prettier 3.9.0, eslint-plugin-svelte 3.20.0, svelte-eslint-parser 1.8.0, @tanstack/svelte-query 6.1.35, @internationalized/date 3.12.2, tailwindcss / @tailwindcss/cli / @tailwindcss/vite 4.3.1; применено форматирование prettier 3.9.0.
- **Гигиена lockfile:** перегенерирован консистентный `frontend/package-lock.json`, чтобы `npm ci` проходил во всех фронтенд-джобах CI.

### При обновлении

- Новые переменные окружения: `REGISTRATION_INVITE_ONLY_ENABLED`, `TRIAL_PREMIUM_TRAFFIC_LIMIT_GB`, `TRIAL_PREMIUM_SQUAD_UUIDS`; dev/QA-стенд добавляет `DEV_POSTGRES_PORT` и `QA_*` переменные. **Новых миграций БД нет.**

<details>
<summary>Ссылки на изменения и участники</summary>

* chore(deps): bump the pip group across 2 directories with 1 update by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/40
* Feature/api refactor by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/41
* Feature/architecture hardening by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/42
* Feature/architecture refactoring by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/43
* Feature/provider orchestration unification by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/44
* Feature/svelte runes by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/45
* Registration gate, trial premium rules, typed API contracts + large refactor by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/46


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.10...v3.5.0

</details>

## v3.4.10 — 2026-06-19

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.10) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.10)

### Обзор

Крупная переработка скрипта установщика и миграции с Remnashop, новый платёжный провайдер Pally и расширение Wata Crypto, ускорение и кэширование гайдов по подписке, небольшие исправления гайдов, перевод админских таблиц на datatables и другие фиксы.

### Изменения

- Расширен установщик (`scripts/install.sh`): настройка DNS и TLS-сертификатов, профиль обратного прокси eGames, автоопределение учётных данных панели, предзаполнение и локализация шагов миграции, маскирование кредов БД в логах, устойчивость к EOF и сохранение путей загрузки.
- Переработан импорт из Remnashop (`import_legacy.py`): перенос настроек тарифов, снимков пользовательских кодов активации, поддержка внешних ключей пользователей и токенов ссылок на подписку, опциональный сброс целевой БД перед импортом, сохранение состояния Telegram, чтение root-owned env, отчёт о завершении и о сопоставленных платёжных провайдерах.
- Добавлен платёжный провайдер Pally .
- Расширен платежный провайдер Wata — возможность добавить кнопку оплаты wata crypto.
- Улучшены гайды по подписке: кэширование конфигурации и разрешённых гайдов, компактный payload, ускорение загрузки, разрешение гайдов для внешних squad’ов, кастомный subpage-конфиг панели и fallback на дефолтный гайд панели.
- Переведены админские таблицы (бэкапы, платежи, локальные секции) на datatables с реактивной пагинацией; добавлены actionable-подсказки и описания к ошибкам, кэш health-checks и логов, улучшены жесты drag-and-drop сортировки.
- Добавлена поддержка Cookie-заголовка для запросов к API панели (доступ через eGamesAPI/remnawave-reverse-proxy) и нормализация traffic-стратегий Remnawave.
- Исправлены платежи и биллинг: сохранение device-метаданных YooKassa и счётчиков устройств для invoice-платежей, использование валюты платежа для провайдеров в меню бота, интеграция HWID top-up.
- Исправлены уведомления: подавление уведомлений об истечении для замещённых подписок, постановка web-app уведомлений в очередь.
- Обновлены deploy-примеры (caddy/newt/nginx/no-proxy) и привязки nginx для eGames; синхронизация конфига nginx в работающий контейнер.

### При обновлении

- Новая переменная окружения `PANEL_API_COOKIE` (опциональный Cookie-заголовок для API панели).
- Добавлены настройки TTL кэша гайдов: `SUBSCRIPTION_GUIDES_CONFIG_CACHE_TTL_SECONDS`, `SUBSCRIPTION_GUIDES_RESOLVED_CACHE_TTL_SECONDS`, `SUBSCRIPTION_GUIDES_PUBLIC_CACHE_TTL_SECONDS` (по умолчанию 300с).

<details>
<summary>Ссылки на изменения и участники</summary>

* feat: add Pally payment provider by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/38
* feat: installer DNS/cert & migration overhaul, Pally/Wata payments, guide caching by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/39


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.9...v3.4.10

</details>

## v3.4.9 — 2026-06-17

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.9) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.9)

### Обзор

Добавлены платёжные провайдеры Stripe, CloudPayments и LAVA Business, внутренняя plugin/extension API с реестром фич, шина доменных событий с маршрутизацией side-effects через реакции, кастомизация темы webapp и набор улучшений админ-панели, webapp и платёжного финализирования.

### Изменения

- Добавлены платёжные провайдеры Stripe, CloudPayments и LAVA Business, включая поддержку рекуррентных списаний (Stripe/CloudPayments) и общий модуль recurring; провайдеры подключаются через реестр и настраиваются из админ-UI.
- Усилены продления YooKassa: hardening контролов автопродления, рекуррентный провайдер и общий механизм recurring/success для всех провайдеров.
- Добавлена внутренняя plugin/extension API: загрузчик и спецификация плагинов, hook-points (worker, queue, migration, locale), встроенные плагины (lknpd, telemetry), реестр feature-entitlement и документация по расширениям.
- Добавлена in-process шина доменных событий: side-effects маршрутизируются через event reactions, покрыты сценарии жизненного цикла аккаунта и пути начисления периода.
- Добавлен сервис entitlements и переработана финализация платежей: уведомления откладываются до commit, подтверждение истечения entitlement перед локальным успехом, валидация обновлений expiry в панели, логирование ошибок создания провайдера.
- Добавлена кастомизация дефолтной темы webapp, мердж темной и светлой темы.
- Улучшена админ-панель: секции управляются из реестра, диплинки в разделе настройки, назначение тарифов в админском окне пользователя, сохранение черновиков действий по пользователю, группировка контролов продления подписки, ускорение открытия админ панели, загрузка feature-flags при монтировании.
- Улучшен webapp UX: подбор install-гайдов под конкретную подписку, скрытие карточек квоты для безлимитного трафика, ссылки и подписи статуса сервера.
- Улучшены email-уведомления: безопасные inline-PNG логотипы, метаданные и favicon, локализация писем.
- Исправлен учёт приглашений: продление срока действия подписки за приглашение начисляется только один раз (добавлено поле `referral_welcome_bonus_claimed_at`); рефералы и обработка пользовательских кодов переведены на событийную модель.
- Обновлены CI/Docker/deploy: actions на Node 24, починка pip-audit, healthcheck без zombie-процессов, `curl` в runtime-образе, возврат dev-публикации в GitHub Actions, конфигурируемая задержка между страницами при полном сканировании панели, удалён `.gitlab-ci.yml`.
- Расширены тесты: Stripe/CloudPayments/LAVA провайдеры, доменные события и event reactions, плагины, entitlements, webhooks платежей, автопродление и темы webapp.

### При обновлении

- Изменение схемы БД: добавлен столбец `users.referral_welcome_bonus_claimed_at`, миграции включены.
- Dockerfile обновлён: force-upgrade `certifi` после установки (pip-audit игнорирует PYSEC-2024-230 из-за пина `aiocryptopay==0.4.8`), `curl` оставлен в runtime-образе для healthcheck.8

<details>
<summary>Ссылки на изменения и участники</summary>

* provider: lava by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/30
* chore(deps-dev): bump esbuild from 0.28.0 to 0.28.1 in /frontend in the npm_and_yarn group across 1 directory by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/31
* Feature/cloudpayments by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/33
* Feature/stripe by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/35
* New payment providers, plugin/extension API and domain event bus by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/36
* chore(deps-dev): bump the npm_and_yarn group across 1 directory with 2 updates by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/34
* chore(deps-dev): bump vite from 8.0.12 to 8.0.16 in /frontend in the npm_and_yarn group across 1 directory by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/37


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.8...v3.4.9

</details>

## v3.4.8 — 2026-06-10

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.8) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.8)

### Обзор

Изменения после релиза v3.4.7 (`v3.4.7..HEAD`): новый платёжный провайдер PayKilla, защита бота от флуда обновлений Telegram, shell-мастер установки с миграцией с legacy tg-shop и Remnashop, диагностика конфигурации в админке и большой блок улучшений платежей, тарифов и Mini App.

### Изменения

- Добавлен платёжный провайдер PayKilla: конвертация в поддерживаемые валюты, проверка минимальной суммы платежа, санитизация текста инвойсов, корректная передача валюты тарифа.
- Улучшена работа платёжных провайдеров: переиспользование незавершённых счетов и ссылок по идентичности провайдера, глобальный таймаут запросов к провайдерам с применением без рестарта, повтор и восстановление соединений провайдеров, статус «pending» в транзакциях (спасибо @BADtochka, `234fc695`, `3170b966`, `766f2a57`, `e3f35a46`).
- Добавлена защита Telegram-бота от флуда: ранний guard и лимиты по типам обновлений (сообщения, callback, inline, /start), cooldown для платёжных и trial-callback, отбрасывание не-приватных обновлений, настройки доступны в админке.
- Добавлен shell-мастер установки (`scripts/install.sh`) с переносом данных с legacy remnawave-tg-shop, а также импорт с Remnashop: пользователи, коды, настройки платежей, совместимость legacy-кодов приглашений. (! Функционал миграции с remnashop находится в стадии разработки и еще не был тщательно протестирован, делайте бэкапы !)
- Добавлена диагностика конфигурации в админ-панели: сервис проверки настроек, баннер с проблемами, актуализация алертов Telegram-webhook.
- Улучшена админ-панель: аудитории рассылок «никогда не подписывался» и «не подключался к VPN» с кешированием счётчиков, отображение активности VPN-подключений и истории trial у пользователя, переопределение лимита HWID-устройств per-user, улучшенная пагинация; исправлен жизненный цикл модального окна пользователя (спасибо @BADtochka, `9adcbf10`).
- Расширен редактор тарифов: настраиваемый порядок периодов и пакетов при покупке, унифицированные строки цен, drag-and-drop сортировка, улучшенная мобильная вёрстка.
- Улучшен Mini App: счётчик до истечения подписки, стабильная мобильная навигация, хешированные immutable-ассеты со сбросом устаревшего кеша, экран активации trial, применение акцента темы в письмах и deeplink, масштаб логотипа по viewport.
- Добавлена поддержка пользователей без Telegram (email-only): активация trial и приветственные начисления периода по приглашению, поправлены аватары по email, скрытие форм привязки и логина по email при выключенной авторизации; для начислений по кодам и приглашениям назначается тариф по умолчанию.
- Улучшены письма: встраивание загруженного логотипа, обновлённые брендированные шаблоны; 
- Добавлен пример docker-compose для локального SMTP на docker-mailserver (спасибо @austnv, `bd7361e9`).
- Повышена безопасность: корректное разрешение клиентского IP за цепочкой прокси для webhook-ов и allowlist-ов провайдеров (спасибо @BADtochka, `f07031f3`, `cc74ddec`), обновлены зависимости по security-advisories (pyjwt, certifi, aiohttp).
- Обновлены сборка и деплой: уменьшение churn слоёв Docker-образа, выкладка хешированных ассетов webapp в backend-образ, GitLab CI для dev-образов, фикс regex маршрутов в nginx; 
- Телеметрия дополнена признаком официальной/кастомной сборки образа (для анонимной статистики).

### При обновлении

- Есть изменения схемы БД — миграции включены и применяются автоматически.
- Новые настройки окружения: блок `TELEGRAM_ANTIFLOOD_*` и cooldown-настройки, `PAYMENT_REQUEST_TIMEOUT_SECONDS`, таймауты `PANEL_API_*`, настройки импорта `MIGRATION_REMNASHOP_*`, `TRIAL_WITHOUT_TELEGRAM_ENABLED`, `DISPOSABLE_EMAIL_DOMAINS`.
- Значение по умолчанию `TRUSTED_PROXIES` расширено приватными диапазонами (Docker/LAN/Kubernetes) — проверьте, что это соответствует вашей топологии.
- Контрибьюторы: @BADtochka (платежи, безопасность прокси, фиксы админки — 24 коммита), @austnv (пример docker-mailserver — `bd7361e9`, `c733d830`).

<details>
<summary>Ссылки на изменения и участники</summary>

* remnashop migration feature, install wizard by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/23
* chore(deps): bump the pip group across 2 directories with 1 update by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/25
* Добавлена поддержка локального SMTP-сервера на базе Docker Mailserver by @austnv in https://github.com/3252a8/remnawave-minishop/pull/26
* Документация платёжек и замена домена Freekassa by @BADtochka in https://github.com/3252a8/remnawave-minishop/pull/27
* feat: harden Telegram bot anti-flood handling by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/28
* PayKilla provider, Telegram anti-flood, install wizard and Remnashop migration (test) by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/29

**Участники**
* @austnv made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/26
* @BADtochka made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/27

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.7...v3.4.8

</details>

## v3.4.7 — 2026-06-01

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.7) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.7)

### Обзор

Мультивалютные тарифы с фильтрацией провайдеров по валюте (если хотите принимать оплату не в рублях), безопасный dry-run режим записи в Remnawave Panel (дле dev и тестов перед миграцией), анонимная opt-out телеметрия установок, улучшение интерфейса управления пользователями в админке, а также набор фиксов каналов, deeplink-шлюза, top-up трафика и локализации писем.

### Изменения

- Добавлены мультивалютные тарифы: JSON-каталог поддерживает `default_currency` (`usd`, `eur`, `usdt` и др.) с generic-полями цен и пакетов, legacy `*_rub`-поля остаются алиасами. Платёжные методы фильтруются по поддерживаемым провайдером валютам, а раздел **Система → Тарифы** показывает матрицу «метод/сервис/доступность» для текущей валюты.
- Добавлен dry-run режим записи в Remnawave Panel: `PANEL_WRITE_MODE=dry_run`/`auto` и `APP_RUNTIME_MODE` позволяют читать живую панель, но только валидировать и логировать мутации пользователей (`[PANEL DRY-RUN OK] would PATCH ...`); секреты и ID редактируются из логов dry-run.
- Добавлена анонимная opt-out телеметрия установок: раз в сутки worker шлёт обезличенный heartbeat (версия, OS/arch, Python, язык, включённые провайдеры, диапазон числа пользователей) в формате PostHog; выключается через `TELEMETRY_ENABLED` или тоггл **Admin → System** без перезапуска.
- Расширено управление пользователями в админке: фильтры, сортируемые колонки, метрики списка пользователей, отображение реферальных связей в карточках и модальное окно деталей пользователя (`UserDetailModal`).
- Добавлен сброс права на триал из веб-админки без удаления истории пользователя (новая отметка `trial_eligibility_reset_at`, миграция 0033).
- Добавлена цель рассылки «истёкшие подписки» (expired subscription broadcast target).
- Добавлен выбор языка на экране входа и восстановлен селектор языка в мобильной админке.
- Добавлен аудит исходящих уведомлений пользователям (`message_audit`) — фиксация фактических отправок ботом.
- Обновлены письма: локализация support-шаблонов, рендер email-превью из шаблонов, demo-секция превью в документации и отвязка генерации превью от зависимостей бота.
- Исправлены платежи и трафик: согласованы потоки top-up трафика и unlimited-оверрайды; запуск миграций после восстановления БД; восстановлены экраны ввода email-кода (pending email code).
- Исправлены проверки обязательного канала: нормализация `REQUIRED_CHANNEL_ID` (приведение к `-100…`) и устойчивое распознавание ошибок доступа к каналу.
- Исправлен UX мобильного клиента: deeplink-шлюз остаётся открытым во время prompt запуска приложения; увеличена кнопка продления.
- Обновлён CI: dev-образы тегируются только как `dev` (убраны per-commit теги `dev-<sha>`).
- Расширены тесты: мультивалютные тарифы, телеметрия, dry-run панели, метрики/гранты/сброс триала в админке, аудит сообщений, нормализация канала, реестр платёжных провайдеров.

### При обновлении

- Есть изменение схемы БД: миграция `0033_add_trial_eligibility_reset_marker` (колонка `users.trial_eligibility_reset_at`), применяется автоматически.
- Новые переменные окружения: `TELEMETRY_ENABLED`, `TELEMETRY_ENDPOINT`, `TELEMETRY_API_KEY`, `TELEMETRY_INTERVAL_HOURS`; `APP_RUNTIME_MODE`, `PANEL_WRITE_MODE`, `PANEL_DRY_RUN_VALIDATE_REMOTE`, `PANEL_DRY_RUN_SYNTHETIC_CREATE`. Для кастомных валют у Heleket/Platega/SeverPay держите в актуальном состоянии `*_SUPPORTED_CURRENCIES`.
- Телеметрия включена по умолчанию (opt-out): отключается `TELEMETRY_ENABLED=False`, пустым endpoint/ключом или тогглом в админке. Персональные данные и секреты не отправляются.

<details>
<summary>Ссылки на изменения и участники</summary>

* Feature/multicurrency by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/18
* Feature/telemetry by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/19
* Enhance admin users and subscription workflows by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/20
* Improve admin UX, trial reset behavior, and channel subscription checks by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/21
* Multicurrency (future-proof feature), panel dry-run mode (dev feature), install telemetry and admin user tools by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/22


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.6...v3.4.7

</details>

## v3.4.6 — 2026-05-30

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.6) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.6)

### Обзор

Статистика подписок разбита по типу доступа (активные / платные / пробные / бесплатные), добавлены GitHub Actions для сборки образов, PR-проверок и сканирования безопасности, исправлены probe-уведомления Telegram и маршрутизация demo-страницы документации.

### Изменения

- Разбита статистика подписок по типу доступа: добавлены отдельные счётчики «с активной подпиской», «с платной», «с пробной» и «с бесплатной подпиской»; неактивные считаются как пользователи без активной подписки. Логика классификации (provider + статус панели) реализована в `user_dal` через подзапрос с агрегацией по пользователю.
- Обновлены админская и inline-статистика под новую разбивку: новые строки и иконки в текстовом отчёте, передача `active`/`free` в inline-режим, описание inline-карточки теперь показывает число пользователей с подпиской.
- Переработана карточка статистики в Admin Panel: основной показатель — активные пользователи с долей от общего числа в бейдже, в подвале раздельно платные · бесплатные · пробные; обновлены подписи карточек.
- Исправлены probe-уведомления Telegram: проверка доступности чата теперь делается через `get_chat` вместо отправки служебного сообщения, поэтому пользователи больше не получают пробные сообщения; удалён код кнопки и текста probe.
- Исправлена маршрутизация demo-runtime в документации: runtime собирается в `app/index.html` вместо `app.html`, обновлены Cloudflare Pages rewrites и материализация маршрутов — устранён цикл редиректов между extensionless и `.html`.
- Добавлены GitHub Actions: переиспользуемый workflow сборки и публикации Docker-образов, dev- и release-сборки образов, PR-проверки (CI), security-сканирование (Trivy) и dependency review.
- Обновлены EN/RU локали под новую разбивку статистики и обновлён mock API demo (полный набор полей статистики пользователей).
- Расширены тесты для `user_dal` (разбивка подписок) и Telegram-уведомлений; обновлён dev-зависимость svelte.

### При обновлении

- Схема БД не меняется; новые env-переменные не добавлены.
- Для CI/CD появились новые GitHub Actions workflow — потребуются стандартные права на пакеты/registry в репозитории.

<details>
<summary>Ссылки на изменения и участники</summary>

* ci: add GitHub Actions for image builds, PR checks and security scans by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/13
* chore(deps-dev): bump svelte from 5.55.5 to 5.56.0 in /frontend in the npm_and_yarn group across 1 directory by @dependabot[bot] in https://github.com/3252a8/remnawave-minishop/pull/14
* Split subscription stats by access type, CI/CD pipelines and notification/docs-demo fixesDev by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/15

**Участники**
* @dependabot[bot] made their first contribution in https://github.com/3252a8/remnawave-minishop/pull/14

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.5...v3.4.6

</details>

## v3.4.5 — 2026-05-30

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.5) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.5)

### Обзор

Изменения после релиза **v3.4.4**. Ключевые темы: отслеживание доставки Telegram-уведомлений и приглашение пользователей запустить бота, зеркалирование жизненного цикла подписки через panel webhook с email-дублированием, реферальные начисления по периодам тарифа, настройки Remnawave panel webhook в админке, блокировка краулеров и заметные улучшения Mini App/Admin UI.

### Изменения

- Добавлено отслеживание статуса Telegram-уведомлений: новые поля статуса/времени проверки в `users` (миграция 0032), сервис `telegram_notifications` с состояниями `enabled/needs_start/blocked/unknown` и баннер в Mini App, предлагающий пользователю запустить бота для получения уведомлений.
- Добавлено зеркалирование жизненного цикла подписки: новый сервис `subscription_lifecycle_notifications` дублирует напоминания об истечении/просрочке через panel webhook и параллельно по email; добавлена синхронизация email-уведомлений пользователя (`user_email_notifications`).
- Улучшен email-flow продления подписки, расширены email-шаблоны (`email_templates`), добавлен флаг `SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED`.
- Реализованы реферальные начисления по периодам тарифа: поля `referral_bonus_days_inviter` / `referral_bonus_days_referee` в конфиге тарифов с валидацией, расчёт начислений по периоду и группировка отображения начислений по тарифам в боте.
- Вынесены настройки Remnawave panel webhook в Admin → System → Settings и в манифест админ-настроек; уточнены логи panel webhook и подписки, обновлена документация по настройке `WEBHOOK_URL` (`/webhook/panel`).
- Исправлена обработка panel webhook: подписки сохраняются при сбое lookup в панели, устранены deadlock'и в subscription worker, расширено логирование `panel_api_service`.
- Добавлена блокировка краулеров и AI-ботов: `robots.txt` (GPTBot, ClaudeBot, PerplexityBot и др.), заголовки `X-Robots-Tag: noindex` во всех location nginx, копирование `robots.txt` в образ frontend.
- Улучшен Mini App UX: новые UI-контролы (range/color/file input), переработанные scroll-area, обновлённые экраны Devices/Invite/Support/Auth, скрытие сводки трафика для неактивных устройств, показ Telegram-логина без email-авторизации.
- Улучшена Admin Panel: переработаны карточки пользователей в логах, стандартизированы веб-контролы и редактор тарифов.
- Исправлены платежи: форматирование лимитов premium-трафика из байтов, доработки YooKassa и shared success/webhooks.
- Обновлены docs/demo: runtime demo в dev, таблица уведомлений, примеры деплоя и compose.
- Прочее: заданы дефолтные цены `RUB_PRICE_*` (200/600/1200/2400), reload locale-overrides по содержимому файла, нормализация line endings фронтенда (`.gitattributes`).

### При обновлении

- Изменение схемы БД: миграция `0032_add_telegram_notification_status` добавляет 4 столбца в `users` (включается автоматически).
- Новые настройки: `SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED`; в конфиге тарифов — `referral_bonus_days_inviter` / `referral_bonus_days_referee`. Дефолты `RUB_PRICE_1/3/6/12_MONTH(S)` теперь 200/600/1200/2400 (ранее не заданы).
- Для работы panel webhook нужно задать `PANEL_WEBHOOK_SECRET` и указать в Remnawave Panel `WEBHOOK_URL = WEBHOOK_BASE_URL + /webhook/panel`.
- Dockerfile frontend обновлён: в образ копируется `robots.txt`.

<details>
<summary>Ссылки на изменения и участники</summary>

* Telegram delivery tracking, subscription lifecycle mirroring and per-tariff referral bonuses by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/12


**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.4...v3.4.5

</details>

## v3.4.4 — 2026-05-28

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.4) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.4)

### Обзор

Добавлены бэкапы, интерактивная demo-страница в документации, улучшения Mini App/Admin Panel, фиксы платежей/HWID и локальные уведомления по подпискам.

### Изменения

- Добавлена система бэкапов: ручное создание из админки, worker для архивов, отправка в backup/log chat, восстановление из архива, проверки безопасности ZIP и документация по настройке.
- Чтобы работал бэкап docker compose папки, нужно смонтировать в backend и worker контейнеры volume: `${COMPOSE_BACKUP_SOURCE:-.}:/app/compose-source:${COMPOSE_RESTORE_MODE:-rw}`
- Обновлены документация и demo-страница приложения: добавлен отдельный demo runtime, fullscreen demo routes, мобильная навигация, mock-сценарии Mini App/Admin Panel/Auth/Devices/Backups и актуализированные страницы docs.
- Улучшен Mini App UX: компактные карточки трафика и статуса, корректные действия по тарифам, depleted-состояния, activation dialog для forced actions, обновление устройств после billing actions.
- Улучшены авторизация и локализация: общий экран подтверждения email-кода, Telegram auth в demo flow, сохранение языка аккаунта, сохранение admin view при смене языка, обновление EN/RU переводов.
- Добавлены default brand assets и fallback favicon/logo для webapp/admin appearance.
- Улучшена поддержка: сохранение черновиков тикетов, корректные отступы/ширина сообщений и более быстрое завершение ответов.
- Исправлены платежи и HWID top-up: сериализация дат, idempotency webhook-ов, расчет paid period, edge cases провайдеров и интеграция HWID-платежей через YooKassa.
- Добавлен локальный worker уведомлений по подпискам: напоминания об истечении, expired-сценарии и уведомления о depleted trial traffic.
- Обновлены deploy/Docker настройки: оптимизация layer caching, зависимости для backup/restore и compose mounts для бэкапов.
- Расширены тесты для backup/restore, backup worker, subscription notifications, payment webhooks, HWID top-up, account language и webapp assets.

<details>
<summary>Ссылки на изменения и участники</summary>

* Update and structurize docs by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/5
* Backups, docs demo, and Mini App improvements by @3252a8 in https://github.com/3252a8/remnawave-minishop/pull/7

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.3...v3.4.4

</details>

## v3.4.3 — 2026-05-26

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.3) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.3)

### Mini App и инструкции подключения

- Добавлены встроенные install guides в Mini App: экран `/install`, публичные ссылки `/s/<token>`, QR-код, deeplink-кнопки и fallback на обычную ссылку подключения.
- Добавлена загрузка Subscription Page config из Remnawave Panel, с опциональным JSON override из админки.
- Обновлены кнопки бота после оплаты/trial/кода активации: теперь можно вести пользователя сразу в инструкции подключения.
- Добавлены webapp preview metadata, title в настройках админки и iOS home screen icons.

### Runtime-переводы

- Добавлен runtime-редактор переводов в админке.
- Переводы можно переопределять без правки `locales/*.json`; overrides хранятся в БД и зеркалируются в `data/locales-overrides.json`.
- Добавлена группировка ключей переводов по аудитории и разделам.

### Платежи

- Стабилизирован Wata provider: payment links, prepayment webhooks, retry/reuse pending links, refresh статуса, обработка истекших ссылок и корректное сохранение provider transaction id.
- TTL ссылок Wata переведен на минуты через `WATA_LINK_TTL_MINUTES`.
- Исправлены YooKassa webapp payments и HWID device top-ups.
- Исправлено открытие Telegram Stars invoice внутри Mini App.
- Добавлен режим admin-only для платежных провайдеров.
- Из success-сообщений убраны прямые ссылки подключения; вместо этого используются кнопки/инструкции.

### Тарифы, trial и HWID

- Добавлен экран активации trial в Mini App.
- Улучшены настройки trial и тарифов в админке.
- Legacy-настройки тарифов отделены от JSON-каталога и помечены предупреждением.
- HWID top-ups теперь привязаны к сроку активной подписки, поддерживают prorated price и renewal-сценарии.
- Исправлено сохранение premium squad access и лишняя синхронизация premium squad state.

### Админка

- Добавлен detail view для платежей.
- Улучшены настройки платежных провайдеров, webhook URL и группировка provider settings.
- Улучшены настройки тарифов, trial и legacy-параметров.
- Добавлено удаление Remnawave user вместе с bot account.
- Обновлены стили админки, webapp layout, custom themes и preview.

### Panel sync и профили

- Убрана inline-синхронизация панели на старте бота; ручной sync теперь ставится в очередь.
- Добавлены компактные diagnostics для panel sync.
- Исправлены лишние PATCH-запросы к панели из-за description churn.
- Исправлена очистка legacy email из panel description и восстановление linked panel email.
- Добавлен auto-merge duplicate panel identities.
- Профиль Web App обновляется после activation/payment status.

### Deploy и документация

- Обновлены deploy examples: Caddy, Nginx, Newt/Pangolin и no-proxy.
- Обновлены README и docs по Web App, install guides, env vars, deployment, tariffs и migration notes.

### При обновлении

- Добавлены миграции БД для runtime locale overrides, install share tokens и HWID validity/payment fields.
- Для Wata старый `WATA_PAYMENT_LINK_TTL_DAYS` заменен на `WATA_LINK_TTL_MINUTES`; дефолт — 15 минут.
- Install guides включены по умолчанию и пытаются читать Subscription Page config из Remnawave Panel; при ошибке есть fallback на обычную ссылку подключения.

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.2...v3.4.3

## v3.4.2 — 2026-05-22

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.2) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.2)

### Вход, связывание аккаунтов и настройки админки

[Исходный PR](https://github.com/3252a8/remnawave-minishop/pull/1) · @3252a8
#### Auth / связка аккаунтов
- Починен вход и привязка Telegram в Mini App и через Telegram OAuth.
- Исправлены сценарии объединения email-аккаунта и Telegram-аккаунта, включая случай, когда у email-аккаунта активная подписка, а у Telegram-аккаунта подписка уже истекла.
- При merge аккаунтов теперь корректно синхронизируется identity в Remnawave panel: сначала удаляется лишний panel user, затем обновляется оставшийся.
- Добавлено лог-уведомление об объединении аккаунтов.
- Исправлена логика logout в Telegram Mini App: ручной logout больше не ломает повторную авторизацию через initData.

#### Админка и настройки
- В настройках платежных провайдеров добавлен вывод webhook URL с возможностью копирования.
- Улучшена загрузка admin assets через стабильные пути и fallback, чтобы lazy-loaded админка не падала из-за stale hashed assets.
- Исправлен формат отображения версии приложения в sidebar админки: dev-сборки теперь различимы по branch/sha.
- Подправлены стили мобильной кнопки админки.

#### Платежи / panel sync / тарифный worker
- Исправлено появление pay button при включенном payment provider.
- Улучшена синхронизация panel identity, чтобы избежать повторных лишних обновлений.
- Добавлено восстановление missing panel user reference для подписок, если у пользователя уже есть актуальный panel UUID.
- Если bulk-prefetch подтверждает отсутствие panel user, подписка деактивируется без пользовательских уведомлений.

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.1...v3.4.2

## v3.4.1 — 2026-05-21

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.1)

- Раздел с созданием тикетов поддержки в веб апп
- Информация об оплачиваемом сервисе перед оплатой в веб апп и в боте
- Логин с помощью email и пароля
- Рефакторинг платежных провайдеров
- Платежный провайдер Wata
- Платежный провайдер Heleket
- Большая оптимизация производительности
- Исправление мелких багов

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.4.0...v3.4.1

## v3.4.0 — 2026-05-17

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.4.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.4.0)

- Возможность создавать кастомные [темы ](docs/features/webapp-themes.md)
- Загрузка лого и favicon через веб админку
- Разделение сервиса на отдельные контейнеры и повышение стабильности, задел на будущее
- Фикс активации триала 
- Фикс YooKassa
- Фикс показа кнопки докупки устройств когда не определены цены для докупки
- Фикс дублирования элементов покупки подписки при использовании legacy тарифов
- Другие мелкие фиксы и улучшения

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.3.0...v3.4.0

## v3.3.0 — 2026-05-13

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.3.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.3.0)

- Веб апп админка
- Возможность создания нескольких тарифов (по месяцам и по трафику, с разными сквадами и т.п.)
- Докупка трафика и устройств
- Возможность создания премиум-сквадов внутри тарифа с отдельным трекингом трафика (и его докупкой)
- Десктоп верстка веб апп
- Возможность выключить логирование действий администраторов
- Исправлена смена сквадов пользователя при начислении периода за приглашения.
- Фикс багов и другие мелкие улучшения

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.2.4...v3.3.0

## v3.2.4 — 2026-05-06

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.2.4) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.2.4)

- Исправление доступа к веб апп, когда недоступен telegram со стороны пользователя, отображение статуса на кнопке telegram oauth, показ аватара из telegram, даже если он недоступен [8783129c](https://github.com/3252a8/remnawave-minishop/commit/8783129c16b57f31ef237fc07bda903ed80a83ea)

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.2.3...v3.2.4

## v3.2.3 — 2026-05-02

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.2.3) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.2.3)

- Исправление кнопки выбора языка в веб апп на Android [50857d52](https://github.com/3252a8/remnawave-minishop/commit/50857d52835ee99003b21b1a8a7b8f893e4b7d23)

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.2.2...v3.2.3

## v3.2.2 — 2026-05-01

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.2.2) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.2.2)

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.2.1...v3.2.2

- Исправление: кнопка открытия страницы-подписки пропала из веб апп [e1223f8c](https://github.com/3252a8/remnawave-minishop/commit/e1223f8c57a0eb816c9e9d9f277af4dc0c969b87)

## v3.2.1 — 2026-05-01

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.2.1) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.2.1)

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.2.0...v3.2.1

- Переход на новый механизм Telegram OAuth [4de730bf](https://github.com/3252a8/remnawave-minishop/commit/4de730bf5a88d5a355ed614ea362fe1223680a4f)
- Улучшение меню телеграм бота [81f51687](https://github.com/3252a8/remnawave-minishop/commit/81f516872671472ea8811accd81c2cf0c5e0c390)
- Исправление кнопки выбора языка в веб апп [d15b1be3](https://github.com/3252a8/remnawave-minishop/commit/d15b1be3b9468e4dbaedcd10dc30888970749929)
- Небольшое исправление дизайна писем — убран фон под логотипом [4d0241a0](https://github.com/3252a8/remnawave-minishop/commit/4d0241a0ea8790e7584e6d7261471350c80306f8)

**Требуется настройка бота и .env для перехода на новый Telegram OAuth**

## v3.2.0 — 2026-04-30

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.2.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.2.0)

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.1.0...v3.2.0

- Web App теперь использует svelte, улучшен интерфейс
- Добавлена поддержка тарифов за ГБ в Web App
- Добавлена поддержка управлением HWID в Web App
- Добавлена поддержка триал периода в Web App
- Добавлено оформление для email с кодами т.п.
- Логирование регистрации пользователей через почту, слиянике аккаунтов и т.п.
- Прочие улучшения и исправления

## v3.1.0 — 2026-04-27

[GitLab](https://gitlab.com/3252a8/remnawave-minishop/-/releases/v3.1.0) · [GitHub](https://github.com/3252a8/remnawave-minishop/releases/tag/v3.1.0)

**Full Changelog**: https://github.com/3252a8/remnawave-minishop/compare/v3.0.0...v3.1.0

- Реализован Web App / Mini App: единый экран подписки с ссылкой подключения, остатком времени, трафиком и оплатой.
- Добавлены новые способы входа: Telegram Mini Apps `initData`, Telegram Login Widget и вход по одноразовому коду на email.
- Улучшены платежи: доработаны сценарии оплаты в Web App, добавлены несколько кнопок Platega,.
- Обновлено меню бота: по умолчанию доступны только кнопки Web App и поддержки, остальные действия вынесены в отдельную команду.
- Усилены безопасность и стабильность: доработаны Mini App auth, CSRF, CSP и проверка webhook-подписей.
- Подготовлена миграция на новый нейминг `remnawave-minishop` вместо `remnawave-tg-shop`.

**Важно при обновлении:** контейнеры, тома и GHCR-образ переименованы, поэтому для существующих установок нужна миграция.
