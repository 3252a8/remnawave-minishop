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
          label: 'Начало',
          items: [
            { label: 'Главная', link: '/' },
            { label: 'Обзор', slug: 'getting-started/overview' },
            { label: 'Демо-режим', slug: 'getting-started/demo' },
            { label: 'Системные требования', slug: 'getting-started/system-requirements' },
            { label: 'Установка', slug: 'getting-started/setup' },
            { label: 'Развертывание', slug: 'getting-started/deployment' },
            { label: 'Настройка окружения', slug: 'getting-started/configuration' },
          ],
        },
        {
          label: 'Конфигурация',
          items: [
            { label: 'Переменные окружения', slug: 'configuration/env-vars' },
            { label: 'Безопасность', slug: 'configuration/security' },
            { label: 'Телеметрия', slug: 'configuration/telemetry' },
          ],
        },
        {
          label: 'Возможности',
          items: [
            { label: 'minishop PRO', slug: 'features/minishop-pro' },
            { label: 'Основные', slug: 'features/core' },
            { label: 'Платежи', slug: 'features/payments' },
            { label: 'Промокоды', slug: 'features/promocodes' },
            { label: 'Партнёрская программа', slug: 'features/partner-program' },
            { label: 'Баланс пользователя', slug: 'features/user-balance' },
            { label: 'Подписки', slug: 'features/subscriptions' },
            { label: 'Уведомления', slug: 'features/notifications' },
            { label: 'Тарифы', slug: 'features/tariffs' },
            { label: 'Веб-приложение / Mini App', slug: 'features/web-app' },
            { label: 'Статус серверов', slug: 'features/server-status' },
            { label: 'Способы входа', slug: 'features/login-methods' },
            { label: 'Темы Web App', slug: 'features/webapp-themes' },
            { label: 'Админ-панель', slug: 'features/admin-panel' },
            { label: 'Бэкапы и восстановление', slug: 'features/backups' },
            { label: 'Поддержка пользователей / тикеты', slug: 'features/support' },
          ],
        },
        {
          label: 'API',
          items: [
            { label: 'Обзор API', slug: 'api' },
            { label: 'Интерактивная спецификация', link: '/api/reference/' },
            { label: 'HTTP-контракты', slug: 'architecture/http-api' },
            {
              label: 'Совместимость Remnawave API',
              slug: 'architecture/remnawave-api-compatibility',
            },
            { label: 'Доменные события', slug: 'architecture/events' },
            { label: 'API плагинов', slug: 'development/plugins' },
            { label: 'Контракт плагинов', slug: 'development/plugin-contract' },
          ],
        },
        {
          label: 'Миграции',
          items: [
            { label: 'Обзор миграций', slug: 'migrations' },
            { label: 'remnawave-tg-shop', slug: 'migrations/remnawave-tg-shop' },
            { label: 'remnashop', slug: 'migrations/remnashop' },
          ],
        },
        {
          label: 'Справка',
          items: [
            { label: 'Проблемы', slug: 'troubleshooting/issues' },
            { label: 'Логи', slug: 'troubleshooting/logs' },
            { label: 'Обслуживание', slug: 'troubleshooting/maintenance' },
            { label: 'Архитектура', slug: 'reference/architecture' },
            {
              label: 'Разработка',
              items: [
                { label: 'Карта Graphify', slug: 'development/graphify' },
                { label: 'Единый dev stand', slug: 'development/dev-stand' },
                { label: 'Рецепты изменений', slug: 'development/how-to' },
                { label: 'Runes QA', slug: 'development/runes-migration-qa' },
              ],
            },
          ],
        },
      ],
    }),
  ],
});
