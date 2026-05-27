# Демо

Это статический демо-режим Remnawave Minishop для документации. Он собирается вместе с docs-сайтом, использует моковые данные в браузере и не подключается к backend.

<div class="demo-shell">
  <div class="demo-shell__bar">
    <div>
      <strong>Remnawave Minishop demo</strong>
      <span>Статическая сборка, моковые данные, без backend</span>
    </div>
    <a class="demo-shell__exit" href="/getting-started/overview/">Выйти в документацию</a>
  </div>
  <nav class="demo-shell__nav" aria-label="Сценарии демо">
    <a href="/demo/runtime/app.html?screen=home&mock=tariffs" target="minishop-demo-frame">Главная</a>
    <a href="/demo/runtime/app.html?screen=home&mock=traffic" target="minishop-demo-frame">Трафик</a>
    <a href="/demo/runtime/app.html?screen=trial&mock=trial" target="minishop-demo-frame">Пробный период</a>
    <a href="/demo/runtime/app.html?screen=devices&mock=devices" target="minishop-demo-frame">Устройства</a>
    <a href="/demo/runtime/app.html?screen=install&mock=guides" target="minishop-demo-frame">Инструкции</a>
    <a href="/demo/runtime/app.html?screen=support&mock=tariffs" target="minishop-demo-frame">Поддержка</a>
    <a href="/demo/runtime/app.html?screen=settings&mock=tariffs" target="minishop-demo-frame">Настройки</a>
  </nav>
  <nav class="demo-shell__nav demo-shell__nav--admin" aria-label="Сценарии админки">
    <a href="/demo/runtime/app.html?screen=admin&admin_section=stats&mock=tariffs" target="minishop-demo-frame">Админка</a>
    <a href="/demo/runtime/app.html?screen=admin&admin_section=users&mock=tariffs" target="minishop-demo-frame">Пользователи</a>
    <a href="/demo/runtime/app.html?screen=admin&admin_section=payments&mock=tariffs" target="minishop-demo-frame">Платежи</a>
    <a href="/demo/runtime/app.html?screen=admin&admin_section=tariffs&mock=tariffs" target="minishop-demo-frame">Тарифы</a>
    <a href="/demo/runtime/app.html?screen=admin&admin_section=support&mock=tariffs" target="minishop-demo-frame">Тикеты</a>
    <a href="/demo/runtime/app.html?screen=admin&admin_section=appearance&mock=tariffs" target="minishop-demo-frame">Внешний вид</a>
    <a href="/demo/runtime/app.html?screen=admin&admin_section=translations&mock=tariffs" target="minishop-demo-frame">Переводы</a>
    <a href="/demo/runtime/app.html?screen=admin&admin_section=backups&mock=tariffs" target="minishop-demo-frame">Бэкапы</a>
    <a href="/demo/runtime/app.html?screen=admin&admin_section=settings&mock=tariffs" target="minishop-demo-frame">Настройки админки</a>
  </nav>
  <iframe
    class="demo-shell__frame"
    name="minishop-demo-frame"
    title="Remnawave Minishop static demo"
    src="/demo/runtime/app.html?screen=home&mock=tariffs"
    loading="eager"
  ></iframe>
</div>

Демо-рантайм генерируется во время сборки сайта документации и не является частью продовой сборки Mini App.
