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
  'getting-started/overview.md': 'Что входит в Remnawave Minishop и как связаны бот, Mini App, backend, worker и Remnawave Panel.',
  'getting-started/setup.md': 'Минимальный путь запуска Remnawave Minishop через Docker Compose.',
  'getting-started/configuration.md': 'Минимальный .env, bootstrap-секреты и настройка через Web App админку.',
  'getting-started/deployment.md': 'Docker Compose, обратный прокси, TLS, образы, обновления и резервные копии.',
  'configuration/security.md': 'Секреты, публичные URL, доступ администраторов и базовые меры защиты Minishop.',
  'configuration/env-vars.md': 'Полный справочник переменных окружения Remnawave Minishop.',
  'features/core.md': 'Пользовательские и админские сценарии Remnawave Minishop.',
  'features/payments.md': 'Платежные провайдеры, кнопки оплаты и webhook-обработка.',
  'features/promocodes.md': 'Промокоды: бонусные дни, скидки, множители, checkout-активация и история применений.',
  'features/subscriptions.md': 'Тарифы на срок и по трафику, premium-сквады, HWID-устройства и жизненный цикл подписки.',
  'features/notifications.md': 'Каналы Telegram и email для пользовательских, админских и сервисных уведомлений Remnawave Minishop.',
  'features/tariffs.md': 'Каталог тарифов, модели на срок/по трафику, premium-сквады и HWID-устройства.',
  'features/web-app.md': 'Telegram Mini App, публичные инструкции, проксирование и реферальные ссылки.',
  'features/telegram-auth.md': 'Telegram Mini Apps initData, Telegram OAuth, BotFather и настройка входа через Telegram.',
  'features/email-login.md': 'SMTP, одноразовые коды, magic link, парольный вход и привязка email-аккаунтов.',
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
    '    - text: "Демо"',
    '      link: /demo/home',
    '      icon: right-arrow',
    '    - text: "Установка"',
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
    const body = normalizeCodeFences(
      rewriteMarkdownLinks(stripFirstHeading(content).trimStart(), sourceRelativePath),
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

async function syncOpenApiArtifact() {
  await copyFile(path.join(sourceDir, 'openapi.json'), path.join(siteRoot, 'public', 'openapi.json'));
}

await rm(outputDir, { recursive: true, force: true });
await mkdir(outputDir, { recursive: true });

const files = await walk(sourceDir);
await syncMarkdown(files);
await syncAssets(files);
await syncOpenApiArtifact();

console.log(`Synced documentation from ${path.relative(repoRoot, sourceDir)} to ${path.relative(repoRoot, outputDir)}`);
