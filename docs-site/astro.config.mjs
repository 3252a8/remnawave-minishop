import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightThemeNova from 'starlight-theme-nova';

export default defineConfig({
  site: 'https://minishop.minidoc.cc',
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
            { label: 'Установка', href: '/getting-started/setup/' },
            { label: 'GitHub', href: 'https://github.com/3252a8/remnawave-minishop' },
            { label: 'Telegram', href: 'https://t.me/remnawave_minishop' }
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
            { label: 'Обзор', slug: 'getting-started/overview' },
            { label: 'Демо-режим', slug: 'getting-started/demo' },
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
            { label: 'Основные', slug: 'features/core' },
            { label: 'Платежи', slug: 'features/payments' },
            { label: 'Подписки', slug: 'features/subscriptions' },
            { label: 'Уведомления', slug: 'features/notifications' },
            { label: 'Тарифы', slug: 'features/tariffs' },
            { label: 'Веб-приложение / Mini App', slug: 'features/web-app' },
            { label: 'Telegram-авторизация', slug: 'features/telegram-auth' },
            { label: 'Вход по email', slug: 'features/email-login' },
            { label: 'Темы Web App', slug: 'features/webapp-themes' },
            { label: 'Админ-панель', slug: 'features/admin-panel' },
            { label: 'Бэкапы и восстановление', slug: 'features/backups' },
            { label: 'Поддержка пользователей / тикеты', slug: 'features/support' },
          ],
        },
        {
          label: 'Миграции',
          items: [
            { label: 'Обзор миграций', slug: 'migrations' },
            { label: 'remnawave-tg-shop', slug: 'migrations/remnawave-tg-shop' },
          ],
        },
        {
          label: 'Справка',
          items: [
            { label: 'Проблемы', slug: 'troubleshooting/issues' },
            { label: 'Логи', slug: 'troubleshooting/logs' },
            { label: 'Обслуживание', slug: 'troubleshooting/maintenance' },
            { label: 'Архитектура', slug: 'reference/architecture' },
          ],
        },
      ],
    }),
  ],
});
