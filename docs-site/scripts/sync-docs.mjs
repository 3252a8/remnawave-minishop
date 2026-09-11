import { copyFile, mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const siteRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const repoRoot = path.resolve(siteRoot, '..');
const sourceDir = path.join(repoRoot, 'docs');
const outputDir = path.join(siteRoot, 'src', 'content', 'docs');

const descriptions = {
  'api/index.md': 'HTTP API, OpenAPI-спецификация, доменные события и точки расширения Remnawave Minishop.',
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
  'features/gifts.md': 'Покупка, передача и активация подарочных подписок, сохранение условий, доставка и администрирование.',
  'features/promocodes.md': 'Промокоды: бонусные дни, скидки, множители, checkout-активация и история применений.',
  'features/partner-program.md': 'Партнёрские заявки, атрибуция, комиссии, ручные выплаты, оплата балансом и эксплуатация.',
  'features/subscriptions.md': 'Обзор моделей тарифов, лимитов и жизненного цикла подписок Remnawave Minishop.',
  'features/notifications.md': 'Каналы Telegram и email для пользовательских, админских и сервисных уведомлений Remnawave Minishop.',
  'features/tariffs.md': 'Настройка каталога тарифов, периодов, цен, premium-сквадов, трафика и HWID-устройств.',
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
  'migrations/bedolaga.md': 'Идемпотентный импорт данных из Bedolaga с dry-run и финансовой сверкой.',
  'troubleshooting/issues.md': 'Короткие чеклисты для частых проблем запуска, вебхуков, Mini App и платежей.',
  'troubleshooting/logs.md': 'Какие логи смотреть при диагностике backend, worker, frontend, миграций и вебхуков.',
  'troubleshooting/maintenance.md': 'Обновления, миграции, резервные копии и проверки продакшен-стека.',
  'architecture.md': 'Краткая архитектура backend, frontend, worker и инфраструктурных сервисов.',
  'architecture/http-api.md': 'Контракты HTTP API, envelope ответов, security-схемы, OpenAPI-артефакт и правила typed-маршрутов.',
  'architecture/events.md': 'Каталог доменных событий, payload-моделей, emitters и core-реакций.',
  'development/graphify.md': 'Как пользоваться сгенерированной Graphify-картой кодовой базы и когда обновлять graphify-out.',
};

const imageExtensions = new Set(['.avif', '.gif', '.jpeg', '.jpg', '.png', '.svg', '.webp']);
const inlineContentsMinHeadings = 8;
const inlineContentsMinLines = 180;

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

function plainHeading(heading) {
  return heading
    .replace(/`([^`]+)`/gu, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/gu, '$1')
    .replace(/[*~]/gu, '')
    .trim();
}

function addInlineContents(markdown) {
  if (/^##\s+(?:Навигация по справочнику|На этой странице|Содержание|Оглавление)\s*$/imu.test(markdown)) {
    return markdown;
  }

  const headings = [...markdown.matchAll(/^##\s+(.+?)\s*$/gmu)];
  const lineCount = markdown.split(/\r?\n/u).length;
  if (headings.length < inlineContentsMinHeadings || lineCount < inlineContentsMinLines) {
    return markdown;
  }

  const slugOccurrences = new Map();
  const items = headings.map((match) => {
    const label = plainHeading(match[1]);
    const baseSlug = label
      .toLocaleLowerCase('ru')
      .replace(/[^\p{L}\p{M}\p{N}_\-\s]/gu, '')
      .replace(/\s/gu, '-');
    const occurrence = slugOccurrences.get(baseSlug) ?? 0;
    slugOccurrences.set(baseSlug, occurrence + 1);
    const slug = occurrence === 0 ? baseSlug : `${baseSlug}-${occurrence}`;
    return `- [${label}](#${slug})`;
  });

  const firstHeadingIndex = headings[0].index;
  const before = markdown.slice(0, firstHeadingIndex).trimEnd();
  const after = markdown.slice(firstHeadingIndex).trimStart();
  return `${before}\n\n## На этой странице\n\n${items.join('\n')}\n\n${after}`;
}

function relatedLinksFor(sourceRelativePath) {
  const relatedByOverview = {
    'index.md': [
      ['Обзор', '/getting-started/overview/'],
      ['Быстрый запуск', '/getting-started/setup/'],
      ['Демо-режим', '/getting-started/overview/#демо-режим'],
    ],
    'getting-started/overview.md': [
      ['Быстрый запуск', '/getting-started/setup/'],
      ['Production-развертывание', '/getting-started/deployment/'],
      ['Первичная настройка', '/getting-started/configuration/'],
      ['Миграции из других ботов', '/migrations/'],
    ],
    'getting-started/configuration.md': [
      ['Справочник переменных .env', '/configuration/env-vars/'],
      ['Безопасность', '/configuration/security/'],
      ['Веб админ-панель', '/features/admin-panel/'],
    ],
    'configuration/security.md': [
      ['Способы входа', '/features/login-methods/'],
      ['Production-развертывание', '/getting-started/deployment/'],
      ['Справочник переменных .env', '/configuration/env-vars/'],
    ],
    'configuration/telemetry.md': [
      ['Логи', '/troubleshooting/logs/'],
      ['Обслуживание', '/troubleshooting/maintenance/'],
      ['Веб админ-панель', '/features/admin-panel/'],
    ],
    'migrations/index.md': [
      ['Миграция с remnawave-tg-shop', '/migrations/remnawave-tg-shop/'],
      ['Миграция с Remnashop', '/migrations/remnashop/'],
      ['Миграция с Bedolaga', '/migrations/bedolaga/'],
      ['Быстрый запуск', '/getting-started/setup/'],
    ],
    'features/payments.md': [
      ['Переменные платежей', '/configuration/env-vars/#платежи'],
      ['Тарифы и подписки', '/features/subscriptions/'],
      ['Диагностика по логам', '/troubleshooting/logs/'],
    ],
    'features/subscriptions.md': [
      ['Настройка тарифов', '/features/tariffs/'],
      ['Платежи', '/features/payments/'],
      ['Веб-приложение', '/features/web-app/'],
    ],
    'features/login-methods.md': [
      ['Безопасность', '/configuration/security/'],
      ['Справочник переменных .env', '/configuration/env-vars/#smtp-и-вход-по-email'],
      ['Веб-приложение', '/features/web-app/'],
    ],
    'features/admin-panel.md': [
      ['Бэкапы', '/features/backups/'],
      ['Телеметрия', '/configuration/telemetry/'],
      ['Справочник переменных .env', '/configuration/env-vars/'],
    ],
    'troubleshooting/logs.md': [
      ['Проблемы', '/troubleshooting/issues/'],
      ['Обслуживание', '/troubleshooting/maintenance/'],
      ['Телеметрия', '/configuration/telemetry/'],
    ],
    'troubleshooting/maintenance.md': [
      ['Бэкапы', '/features/backups/'],
      ['Production-развертывание', '/getting-started/deployment/'],
      ['Логи', '/troubleshooting/logs/'],
    ],
    'architecture.md': [
      ['Обзор API', '/api/'],
      ['Доменные события', '/architecture/events/'],
      ['Рецепты изменений', '/development/how-to/'],
    ],
    'architecture/http-api.md': [
      ['Обзор API', '/api/'],
      ['Доменные события', '/architecture/events/'],
      ['API плагинов', '/development/plugins/'],
    ],
    'development/dev-stand.md': [
      ['Рецепты изменений', '/development/how-to/'],
      ['Карта Graphify', '/development/graphify/'],
      ['Runes QA', '/development/runes-migration-qa/'],
    ],
    'development/how-to.md': [
      ['Архитектура', '/reference/architecture/'],
      ['Единый dev stand', '/development/dev-stand/'],
      ['Карта Graphify', '/development/graphify/'],
    ],
    'development/graphify.md': [
      ['Рецепты изменений', '/development/how-to/'],
      ['Архитектура', '/reference/architecture/'],
      ['Единый dev stand', '/development/dev-stand/'],
    ],
    'development/runes-migration-qa.md': [
      ['Единый dev stand', '/development/dev-stand/'],
      ['Рецепты изменений', '/development/how-to/'],
      ['Карта Graphify', '/development/graphify/'],
    ],
    'api/index.md': [
      ['Интерактивная спецификация', '/api/reference/'],
      ['HTTP-контракты', '/architecture/http-api/'],
      ['API плагинов', '/development/plugins/'],
    ],
  };

  return relatedByOverview[sourceRelativePath] ?? [];
}

function appendRelatedLinks(markdown, sourceRelativePath) {
  if (/^##\s+Связанные разделы\s*$/mu.test(markdown)) {
    return markdown;
  }

  const currentRoute = pagePathForSource(sourceRelativePath);
  const links = relatedLinksFor(sourceRelativePath).filter(([, route]) => route !== currentRoute);
  if (links.length === 0) {
    return markdown;
  }

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
      addInlineContents(
        normalizeCodeFences(
          rewriteMarkdownLinks(stripFirstHeading(content).trimStart(), sourceRelativePath),
        ),
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
