import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightThemeNova from 'starlight-theme-nova';

const stableDocsUrl = 'https://minishop.minidoc.cc';
const devDocsUrl = 'https://dev.minishop.minidoc.cc';
const docsBranch =
  process.env.DOCS_BRANCH ??
  process.env.CF_PAGES_BRANCH ??
  process.env.CI_COMMIT_BRANCH ??
  process.env.GITHUB_REF_NAME ??
  process.env.VERCEL_GIT_COMMIT_REF ??
  process.env.BRANCH ??
  '';
const isDevDocs = docsBranch === 'dev';
const docsSiteUrl = isDevDocs ? devDocsUrl : stableDocsUrl;
const otherDocsVersion = isDevDocs
  ? { label: 'Смотреть stable доки', href: stableDocsUrl }
  : { label: 'Смотреть dev доки', href: devDocsUrl };

export default defineConfig({
  site: docsSiteUrl,
  redirects: {
    '/features/core': '/getting-started/overview/',
    '/getting-started/demo': '/getting-started/overview/#демо-режим',
  },
  integrations: [
    starlight({
      title: 'minishop',
      favicon: '/favicon.png',
      description:
        'Документация по настройке, развертыванию и эксплуатации Remnawave Minishop.',
      plugins: [
        starlightThemeNova({
          nav: [
            { label: 'Демо', href: '/demo/home' },
            { label: 'Документация', href: '/getting-started/overview/' },
            { label: 'minishop PRO', href: 'https://cloud.minidoc.cc' },
            { label: 'API', href: '/api/' },
            { label: 'GitHub', href: 'https://github.com/3252a8/remnawave-minishop' },
            { label: 'GitLab', href: 'https://gitlab.com/3252a8/remnawave-minishop' },
            { label: 'Telegram', href: 'https://t.me/remnawave_minishop' },
            otherDocsVersion,
          ],
        }),
      ],
      customCss: ['./src/styles/custom.css'],
      components: {
        Header: './src/components/Header.astro',
      },
      lastUpdated: false,
      locales: {
        root: {
          label: 'Русский',
          lang: 'ru',
        },
      },
      head: [
        {
          tag: 'link',
          attrs: {
            rel: 'icon',
            href: '/favicon.webp',
            type: 'image/webp',
          },
        },
        {
          tag: 'meta',
          attrs: {
            name: 'theme-color',
            content: '#00fe7a',
          },
        },
        {
          tag: 'meta',
          attrs: {
            property: 'og:site_name',
            content: 'Remnawave Minishop Docs',
          },
        },
      ],
      sidebar: [
        {
          label: 'Начало работы',
          items: [
            { label: 'Главная', link: '/' },
            { label: 'Обзор', slug: 'getting-started/overview' },
            { label: 'minishop PRO', slug: 'features/minishop-pro' },
            { label: 'Системные требования', slug: 'getting-started/system-requirements' },
            { label: 'Быстрый запуск', slug: 'getting-started/setup' },
            { label: 'Production-развертывание', slug: 'getting-started/deployment' },
            { label: 'Первичная настройка', slug: 'getting-started/configuration' },
            {
              label: 'Миграции из других ботов',
              collapsed: true,
              items: [
                { label: 'Обзор', slug: 'migrations' },
                { label: 'remnawave-tg-shop', slug: 'migrations/remnawave-tg-shop' },
                { label: 'Remnashop', slug: 'migrations/remnashop' },
                { label: 'Bedolaga', slug: 'migrations/bedolaga' },
              ],
            },
          ],
        },
        {
          label: 'Возможности',
          items: [
            {
              label: 'Продажи и подписки',
              collapsed: false,
              items: [
                { label: 'Тарифы и подписки', slug: 'features/subscriptions' },
                { label: 'Настройка тарифов', slug: 'features/tariffs' },
                { label: 'Платежи', slug: 'features/payments' },
                { label: 'Подарочные подписки', slug: 'features/gifts' },
                { label: 'Баланс пользователя', slug: 'features/user-balance' },
                { label: 'Промокоды', slug: 'features/promocodes' },
                { label: 'Партнёрская программа', slug: 'features/partner-program' },
              ],
            },
            { label: 'Веб-приложение', slug: 'features/web-app' },
            { label: 'Веб админ-панель', slug: 'features/admin-panel' },
            { label: 'Способы входа', slug: 'features/login-methods' },
            { label: 'Темы и внешний вид', slug: 'features/webapp-themes' },
            { label: 'Создание и публикация тем', slug: 'features/theme-packages' },
            { label: 'Уведомления', slug: 'features/notifications' },
            { label: 'Поддержка/тикеты', slug: 'features/support' },
            { label: 'Статус серверов', slug: 'features/server-status' },
            { label: 'Бэкапы', slug: 'features/backups' },
          ],
        },
        {
          label: 'Эксплуатация и диагностика',
          collapsed: true,
          items: [
            { label: 'Справочник переменных .env', slug: 'configuration/env-vars' },
            { label: 'Безопасность', slug: 'configuration/security' },
            { label: 'Телеметрия', slug: 'configuration/telemetry' },
            { label: 'Обслуживание', slug: 'troubleshooting/maintenance' },
            { label: 'Проблемы', slug: 'troubleshooting/issues' },
            { label: 'Логи', slug: 'troubleshooting/logs' },
          ],
        },
        {
          label: 'API и разработка',
          collapsed: true,
          items: [
            { label: 'Обзор API', slug: 'api' },
            { label: 'Интерактивная спецификация', link: '/api/reference/' },
            { label: 'HTTP-контракты', slug: 'architecture/http-api' },
            { label: 'Публичный шлюз подписки', slug: 'architecture/subscription-gateway' },
            {
              label: 'Совместимость Remnawave API',
              slug: 'architecture/remnawave-api-compatibility',
            },
            { label: 'Доменные события', slug: 'architecture/events' },
            { label: 'API плагинов', slug: 'development/plugins' },
            { label: 'SDK расширений', slug: 'development/plugin-extensions' },
            { label: 'Контракт плагинов', slug: 'development/plugin-contract' },
            { label: 'Архитектура', slug: 'reference/architecture' },
            { label: 'Единый dev stand', slug: 'development/dev-stand' },
            { label: 'Рецепты изменений', slug: 'development/how-to' },
            { label: 'Карта Graphify', slug: 'development/graphify' },
            { label: 'Runes QA', slug: 'development/runes-migration-qa' },
          ],
        },
      ],
    }),
  ],
});
