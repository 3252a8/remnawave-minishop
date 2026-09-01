import { copyFile, mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const siteRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const repoRoot = path.resolve(siteRoot, '..');
const sourceDir = path.join(repoRoot, 'docs');
const outputDir = path.join(siteRoot, 'src', 'content', 'docs');

const descriptions = {
  'api/index.md': 'HTTP API, OpenAPI-спецификация, доменные события и точки расширения Remnawave Minishop.',
  'getting-started/demo.md': 'Как устроен статический демо-режим Remnawave Minishop и почему он собирается только вместе с документацией.',
  'index.md': 'Документация по запуску, настройке и сопровождению Telegram Mini App для Remnawave.',
  'getting-started/overview.md': 'Компоненты и основные пользовательские и административные сценарии Remnawave Minishop.',
  'getting-started/system-requirements.md': 'Требования к VPS, Docker, сети и внешним зависимостям Remnawave Minishop.',
  'getting-started/setup.md': 'Быстрый запуск Remnawave Minishop через install wizard и Docker Compose.',
  'getting-started/configuration.md': 'Первичная настройка .env, bootstrap-секретов и Web App админки.',
  'getting-started/deployment.md': 'Production-развертывание: Docker Compose, reverse proxy, TLS, образы, обновления и резервные копии.',
  'configuration/security.md': 'Секреты, публичные URL, доступ администраторов и базовые меры защиты Minishop.',
  'configuration/env-vars.md': 'Полный справочник переменных окружения Remnawave Minishop.',
  'features/minishop-pro.md': 'Бизнес-аналитика, клиентские сегменты и автоматизация продаж в minishop PRO.',
  'features/payments.md': 'Общая настройка способов оплаты, кнопок, валют, чеков и webhook-обработки.',
  'features/payments/yookassa.md': 'Подключение ЮKassa к Remnawave Minishop.',
  'features/payments/freekassa.md': 'Подключение FreeKassa к Remnawave Minishop.',
  'features/payments/platega.md': 'Подключение Platega к Remnawave Minishop.',
  'features/payments/rollypay.md': 'Подключение RollyPay к Remnawave Minishop.',
  'features/payments/severpay.md': 'Подключение SeverPay к Remnawave Minishop.',
  'features/payments/wata.md': 'Подключение WATA к Remnawave Minishop.',
  'features/payments/cryptopay.md': 'Подключение CryptoPay к Remnawave Minishop.',
  'features/payments/tribute.md': 'Подключение Tribute к Remnawave Minishop.',
  'features/payments/heleket.md': 'Подключение Heleket к Remnawave Minishop.',
  'features/payments/oxapay.md': 'Подключение OxaPay к Remnawave Minishop.',
  'features/payments/paykilla.md': 'Подключение PayKilla к Remnawave Minishop.',
  'features/payments/lava.md': 'Подключение Lava к Remnawave Minishop.',
  'features/payments/pally.md': 'Подключение Pally к Remnawave Minishop.',
  'features/payments/cloudpayments.md': 'Подключение CloudPayments к Remnawave Minishop.',
  'features/payments/overpay.md': 'Подключение Overpay к Remnawave Minishop.',
  'features/payments/stripe.md': 'Подключение Stripe к Remnawave Minishop.',
  'features/payments/telegram-stars.md': 'Подключение оплаты Telegram Stars к Remnawave Minishop.',
  'features/promocodes.md': 'Промокоды: бонусные дни, скидки, множители, checkout-активация и история применений.',
  'features/partner-program.md': 'Партнёрские заявки, атрибуция, комиссии, ручные выплаты, оплата балансом и эксплуатация.',
  'features/subscriptions.md': 'Обзор моделей тарифов, лимитов и жизненного цикла подписок Remnawave Minishop.',
  'features/notifications.md': 'Каналы Telegram и email для пользовательских, админских и сервисных уведомлений Remnawave Minishop.',
  'features/tariffs.md': 'Настройка каталога тарифов, периодов, цен, premium-сквадов, трафика и HWID-устройств.',
  'features/tariff-purchases.md': 'Докупки при оформлении и после покупки, пороги показа и безопасная смена тарифа.',
  'features/subscription-lifecycle.md': 'Первая покупка, продление, автопродление, пробный период и привязка существующей подписки.',
  'features/web-app.md': 'Telegram Mini App, публичные инструкции, проксирование и реферальные ссылки.',
  'features/server-status.md': 'Статус серверов в Mini App через внешнюю страницу, Uptime Kuma или xray-checker.',
  'features/login-methods.md': 'Email-код, email/пароль, Telegram, Google, Яндекс и passkey: настройка, связывание аккаунтов и безопасность.',
  'features/webapp-themes.md': 'Кастомные темы, CSS-токены, ассеты и пайплайн создания темы.',
  'features/admin-panel.md': 'Возможности админ-панели, управление пользователями, настройками, тарифами и поддержкой.',
  'features/backups.md': 'Автоматические бэкапы, отправка архивов в Telegram, локальное хранение и восстановление БД/compose-папки из админки.',
  'features/support.md': 'Пользовательские тикеты, список обращений в админке, уведомления и лимиты поддержки.',
  'migrations/index.md': 'Готовые сценарии миграции в Remnawave Minishop с других ботов.',
  'migrations/remnawave-tg-shop.md': 'Перенос данных со старого remnawave-tg-shop на split-архитектуру Minishop.',
  'migrations/remnashop.md': 'Импорт данных из Remnashop через install wizard или скрипт import_legacy.py.',
  'troubleshooting/issues.md': 'Короткие чеклисты для частых проблем запуска, вебхуков, Mini App и платежей.',
  'troubleshooting/logs.md': 'Какие логи смотреть при диагностике backend, worker, frontend, миграций и вебхуков.',
  'troubleshooting/maintenance.md': 'Обновления, миграции, резервные копии и проверки продакшен-стека.',
  'architecture.md': 'Краткая архитектура backend, frontend, worker и инфраструктурных сервисов.',
  'architecture/http-api.md': 'Контракты HTTP API, envelope ответов, security-схемы, OpenAPI-артефакт и правила typed-маршрутов.',
  'architecture/events.md': 'Каталог доменных событий, payload-моделей, emitters и core-реакций.',
  'development/graphify.md': 'Как пользоваться сгенерированной Graphify-картой кодовой базы и когда обновлять graphify-out.',
};

const imageExtensions = new Set(['.avif', '.gif', '.jpeg', '.jpg', '.png', '.svg', '.webp']);

function yamlString(value) {
  return JSON.stringify(value);
}

function toPosix(relativePath) {
  return relativePath.split(path.sep).join('/');
}

function outputRelativePath(sourceRelativePath) {
  if (sourceRelativePath === 'index.md') {
    return 'index.md';
  }
  if (!sourceRelativePath.includes('/')) {
    return `reference/${sourceRelativePath}`;
  }
  return sourceRelativePath;
}

function pagePathForSource(sourceRelativePath, hash = '') {
  const output = outputRelativePath(sourceRelativePath).replace(/\.md$/i, '');
  const route = output === 'index' ? '/' : `/${output.replace(/\/index$/u, '')}/`;
  return `${route}${hash}`;
}

function titleForRelativePath(relativePath) {
  const baseName = path.posix.basename(relativePath, '.md');
  return baseName;
}

function extractTitle(relativePath, content) {
  const match = content.match(/^#\s+(.+?)\s*$/m);
  return match?.[1] ?? titleForRelativePath(relativePath);
}

function stripFirstHeading(content) {
  return content.replace(/^#\s+.+?\s*\r?\n+/, '');
}

function rewriteMarkdownLinks(markdown, sourceRelativePath) {
  const sourceDirectory = path.posix.dirname(sourceRelativePath);
  return markdown.replace(/\]\((?!https?:\/\/|mailto:|tel:|\/|#)([^)\s]+\.md)(#[^)]+)?\)/g, (match, target, hash = '') => {
    const resolvedTarget = path.posix.normalize(path.posix.join(sourceDirectory, target));
    return `](${pagePathForSource(resolvedTarget, hash)})`;
  });
}

function normalizeCodeFences(markdown) {
  return markdown
    .replace(/^```env\s*$/gim, '```ini')
    .replace(/^```caddyfile\s*$/gim, '```txt');
}

function relatedLinksFor(sourceRelativePath) {
  if (sourceRelativePath === 'index.md') {
    return [
      ['Обзор продукта', '/getting-started/overview/'],
      ['Быстрый запуск', '/getting-started/setup/'],
      ['Демо-режим', '/getting-started/demo/'],
    ];
  }

  if (sourceRelativePath.startsWith('getting-started/')) {
    return [
      ['Обзор продукта', '/getting-started/overview/'],
      ['Быстрый запуск', '/getting-started/setup/'],
      ['Production-развертывание', '/getting-started/deployment/'],
      ['Первичная настройка', '/getting-started/configuration/'],
    ];
  }

  if (sourceRelativePath.startsWith('migrations/')) {
    return [
      ['Переход с других решений', '/migrations/'],
      ['Быстрый запуск', '/getting-started/setup/'],
      ['Проблемы', '/troubleshooting/issues/'],
    ];
  }

  if (sourceRelativePath.startsWith('configuration/')) {
    return [
      ['Первичная настройка', '/getting-started/configuration/'],
      ['Переменные окружения', '/configuration/env-vars/'],
      ['Админ-панель', '/features/admin-panel/'],
      ['Безопасность', '/configuration/security/'],
    ];
  }

  if (sourceRelativePath.startsWith('troubleshooting/') || sourceRelativePath === 'features/backups.md') {
    return [
      ['Обслуживание', '/troubleshooting/maintenance/'],
      ['Бэкапы и восстановление', '/features/backups/'],
      ['Проблемы', '/troubleshooting/issues/'],
      ['Логи', '/troubleshooting/logs/'],
    ];
  }

  if (sourceRelativePath === 'features/payments.md' || sourceRelativePath.startsWith('features/payments/')) {
    return [
      ['Обзор платежей', '/features/payments/'],
      ['Переменные платежей', '/configuration/env-vars/#платежи'],
      ['Тарифы и подписки', '/features/subscriptions/'],
      ['Диагностика по логам', '/troubleshooting/logs/'],
    ];
  }

  if (
    sourceRelativePath === 'features/subscriptions.md' ||
    sourceRelativePath === 'features/tariffs.md' ||
    sourceRelativePath === 'features/tariff-purchases.md' ||
    sourceRelativePath === 'features/subscription-lifecycle.md'
  ) {
    return [
      ['Тарифы и подписки', '/features/subscriptions/'],
      ['Настройка тарифов', '/features/tariffs/'],
      ['Докупки и смена тарифа', '/features/tariff-purchases/'],
      ['Жизненный цикл подписки', '/features/subscription-lifecycle/'],
      ['Платежи', '/features/payments/'],
    ];
  }

  if (sourceRelativePath.startsWith('features/')) {
    return [
      ['Веб-приложение', '/features/web-app/'],
      ['Админ-панель', '/features/admin-panel/'],
      ['Способы входа', '/features/login-methods/'],
      ['Платежи', '/features/payments/'],
      ['Поддержка пользователей', '/features/support/'],
    ];
  }

  return [
    ['Обзор API', '/api/'],
    ['HTTP-контракты', '/architecture/http-api/'],
    ['Архитектура', '/reference/architecture/'],
    ['Рецепты изменений', '/development/how-to/'],
    ['API плагинов', '/development/plugins/'],
  ];
}

function appendRelatedLinks(markdown, sourceRelativePath) {
  if (/^##\s+Связанные разделы\s*$/mu.test(markdown)) {
    return markdown;
  }

  const currentRoute = pagePathForSource(sourceRelativePath);
  const links = relatedLinksFor(sourceRelativePath).filter(([, route]) => route !== currentRoute);
  const items = links.map(([label, route]) => `- [${label}](${route})`).join('\n');
  return `${markdown.trimEnd()}\n\n## Связанные разделы\n\n${items}\n`;
}

function extraFrontmatter(sourceRelativePath) {
  if (sourceRelativePath !== 'index.md') {
    return [];
  }

  return [
    'template: splash',
    'hero:',
    '  tagline: "Telegram-бот и Mini App для продажи подписок Remnawave: платежи, тарифы, админка, поддержка и инструкции подключения."',
    '  image:',
    '    html: \'<img class="minishop-hero-screenshot" src="/remnawave-minishop.webp" alt="Интерфейс Remnawave Minishop" width="1920" height="1080" loading="eager" decoding="async" />\'',
    '  actions:',
    '    - text: "Смотреть демо"',
    '      link: /demo/home',
    '      icon: right-arrow',
    '    - text: "Купить PRO"',
    '      link: https://cloud.minidoc.cc',
    '      variant: secondary',
    '    - text: "Гайд по установке"',
    '      link: /getting-started/setup/',
    '      icon: setting',
    '      variant: minimal',
  ];
}

function frontmatter({ title, description, sourceRelativePath }) {
  const editPath = sourceRelativePath
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/');
  const editUrl = `https://github.com/3252a8/remnawave-minishop/edit/main/docs/${editPath}`;
  return [
    '---',
    `title: ${yamlString(title)}`,
    `description: ${yamlString(description)}`,
    `editUrl: ${yamlString(editUrl)}`,
    ...extraFrontmatter(sourceRelativePath),
    '---',
    '',
  ].join('\n');
}

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walk(absolutePath)));
      continue;
    }
    if (entry.isFile()) {
      files.push(absolutePath);
    }
  }
  return files;
}

async function syncMarkdown(files) {
  for (const sourcePath of files.filter((file) => file.endsWith('.md'))) {
    const sourceRelativePath = toPosix(path.relative(sourceDir, sourcePath));
    const outputRelative = outputRelativePath(sourceRelativePath);
    const outputPath = path.join(outputDir, ...outputRelative.split('/'));
    const content = await readFile(sourcePath, 'utf8');
    const title = extractTitle(sourceRelativePath, content);
    const body = appendRelatedLinks(
      normalizeCodeFences(
        rewriteMarkdownLinks(stripFirstHeading(content).trimStart(), sourceRelativePath),
      ),
      sourceRelativePath,
    );
    const output = frontmatter({
      title,
      description: descriptions[sourceRelativePath] ?? title,
      sourceRelativePath,
    });

    await mkdir(path.dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${output}${body}\n`, 'utf8');
  }
}

async function syncAssets(files) {
  for (const sourcePath of files.filter((file) => imageExtensions.has(path.extname(file).toLowerCase()))) {
    const sourceRelativePath = toPosix(path.relative(sourceDir, sourcePath));
    const outputRelative = !sourceRelativePath.includes('/')
      ? sourceRelativePath
      : sourceRelativePath;
    const outputPath = path.join(outputDir, ...outputRelative.split('/'));
    await mkdir(path.dirname(outputPath), { recursive: true });
    await copyFile(sourcePath, outputPath);

    if (!sourceRelativePath.includes('/')) {
      const referenceOutputPath = path.join(outputDir, 'reference', sourceRelativePath);
      await mkdir(path.dirname(referenceOutputPath), { recursive: true });
      await copyFile(sourcePath, referenceOutputPath);
    }
  }
}

async function syncPublicArtifacts() {
  const publicDir = path.join(siteRoot, 'public');
  await Promise.all([
    copyFile(path.join(sourceDir, 'openapi.json'), path.join(publicDir, 'openapi.json')),
    copyFile(
      path.join(sourceDir, 'remnawave-minishop.webp'),
      path.join(publicDir, 'remnawave-minishop.webp'),
    ),
  ]);
}

await rm(outputDir, { recursive: true, force: true });
await mkdir(outputDir, { recursive: true });

const files = await walk(sourceDir);
await syncMarkdown(files);
await syncAssets(files);
await syncPublicArtifacts();

console.log(`Synced documentation from ${path.relative(repoRoot, sourceDir)} to ${path.relative(repoRoot, outputDir)}`);
