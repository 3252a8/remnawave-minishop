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
            { label: 'Обзор продукта', slug: 'getting-started/overview' },
            { label: 'minishop PRO', slug: 'features/minishop-pro' },
            { label: 'Демо-режим', slug: 'getting-started/demo' },
            { label: 'Системные требования', slug: 'getting-started/system-requirements' },
            { label: 'Быстрый запуск', slug: 'getting-started/setup' },
            { label: 'Production-развертывание', slug: 'getting-started/deployment' },
            { label: 'Первичная настройка', slug: 'getting-started/configuration' },
            {
              label: 'Переход с других решений',
              collapsed: true,
              items: [
                { label: 'Обзор', slug: 'migrations' },
                { label: 'remnawave-tg-shop', slug: 'migrations/remnawave-tg-shop' },
                { label: 'Remnashop', slug: 'migrations/remnashop' },
              ],
            },
          ],
        },
        {
          label: 'Продажи и подписки',
          items: [
            {
              label: 'Тарифы и подписки',
              items: [
                { label: 'Обзор и модели', slug: 'features/subscriptions' },
                { label: 'Настройка тарифов', slug: 'features/tariffs' },
                { label: 'Докупки и смена тарифа', slug: 'features/tariff-purchases' },
                { label: 'Жизненный цикл подписки', slug: 'features/subscription-lifecycle' },
              ],
            },
            {
              label: 'Платежи',
              items: [
                { label: 'Обзор и общая настройка', slug: 'features/payments' },
                {
                  label: 'Платёжные провайдеры',
                  collapsed: true,
                  items: [
                    { label: 'YooKassa', slug: 'features/payments/yookassa' },
                    { label: 'FreeKassa', slug: 'features/payments/freekassa' },
                    { label: 'Platega', slug: 'features/payments/platega' },
                    { label: 'RollyPay', slug: 'features/payments/rollypay' },
                    { label: 'SeverPay', slug: 'features/payments/severpay' },
                    { label: 'WATA', slug: 'features/payments/wata' },
                    { label: 'CryptoPay', slug: 'features/payments/cryptopay' },
                    { label: 'Tribute', slug: 'features/payments/tribute' },
                    { label: 'Heleket', slug: 'features/payments/heleket' },
                    { label: 'OxaPay', slug: 'features/payments/oxapay' },
                    { label: 'PayKilla', slug: 'features/payments/paykilla' },
                    { label: 'Lava', slug: 'features/payments/lava' },
                    { label: 'Pally', slug: 'features/payments/pally' },
                    { label: 'CloudPayments', slug: 'features/payments/cloudpayments' },
                    { label: 'Overpay', slug: 'features/payments/overpay' },
                    { label: 'Stripe', slug: 'features/payments/stripe' },
                    { label: 'Telegram Stars', slug: 'features/payments/telegram-stars' },
                  ],
                },
              ],
            },
            { label: 'Баланс пользователя', slug: 'features/user-balance' },
            { label: 'Промокоды', slug: 'features/promocodes' },
            { label: 'Партнёрская программа', slug: 'features/partner-program' },
          ],
        },
        {
          label: 'Mini App и пользователи',
          items: [
            { label: 'Веб-приложение', slug: 'features/web-app' },
            { label: 'Способы входа', slug: 'features/login-methods' },
            { label: 'Темы и внешний вид', slug: 'features/webapp-themes' },
            { label: 'Уведомления', slug: 'features/notifications' },
            { label: 'Поддержка пользователей', slug: 'features/support' },
            { label: 'Статус серверов', slug: 'features/server-status' },
          ],
        },
        {
          label: 'Администрирование',
          items: [
            { label: 'Админ-панель', slug: 'features/admin-panel' },
            { label: 'Справочник переменных .env', slug: 'configuration/env-vars' },
            { label: 'Безопасность', slug: 'configuration/security' },
            { label: 'Телеметрия', slug: 'configuration/telemetry' },
          ],
        },
        {
          label: 'Эксплуатация и диагностика',
          items: [
            { label: 'Обслуживание', slug: 'troubleshooting/maintenance' },
            { label: 'Бэкапы и восстановление', slug: 'features/backups' },
            { label: 'Проблемы', slug: 'troubleshooting/issues' },
            { label: 'Логи', slug: 'troubleshooting/logs' },
          ],
        },
        {
          label: 'API и разработка',
          items: [
            {
              label: 'API Mini Shop',
              items: [
                { label: 'Обзор', slug: 'api' },
                { label: 'Интерактивная спецификация', link: '/api/reference/' },
                { label: 'HTTP-контракты', slug: 'architecture/http-api' },
              ],
            },
            {
              label: 'Интеграции',
              items: [
                {
                  label: 'Совместимость Remnawave API',
                  slug: 'architecture/remnawave-api-compatibility',
                },
                { label: 'Доменные события', slug: 'architecture/events' },
              ],
            },
            {
              label: 'Плагины',
              items: [
                { label: 'API плагинов', slug: 'development/plugins' },
                { label: 'Контракт плагинов', slug: 'development/plugin-contract' },
              ],
            },
            {
              label: 'Для контрибьюторов',
              collapsed: true,
              items: [
                { label: 'Архитектура', slug: 'reference/architecture' },
                { label: 'Единый dev stand', slug: 'development/dev-stand' },
                { label: 'Рецепты изменений', slug: 'development/how-to' },
                { label: 'Карта Graphify', slug: 'development/graphify' },
                { label: 'Runes QA', slug: 'development/runes-migration-qa' },
              ],
            },
          ],
        },
      ],
    }),
  ],
});
