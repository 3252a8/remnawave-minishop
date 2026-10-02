export interface CommunityProject {
  id: string;
  name: string;
  author: string;
  authorUrl: string;
  repository: string;
  forge: 'GitHub' | 'GitLab';
  preview: string;
  previewAlt: string;
  cover?: boolean;
  description: string;
  tags: string[];
  details: string[];
  install?: { repository: string; branch: string; directory?: string };
}

export interface CommunityCategory {
  id: string;
  title: string;
  icon: string;
  description: string;
  guide: { label: string; href: string };
  projects: CommunityProject[];
}

export const communityCategories: CommunityCategory[] = [
  {
    id: 'themes',
    title: 'Темы',
    icon: 'themes',
    description: 'Новый характер вашего магазина — от мягкого неба до неонового мегаполиса.',
    guide: { label: 'Как установить тему', href: '/features/theme-packages/' },
    projects: [
      {
        id: 'aurora',
        name: 'Aurora',
        author: 'austnv',
        authorUrl: 'https://github.com/austnv',
        repository: 'https://github.com/austnv/minishop-themes/tree/master/themes/aurora',
        forge: 'GitHub',
        preview: '/awesome/aurora.webp',
        previewAlt: 'Aurora: интерфейс Minishop с бирюзовыми акцентами и полярным сиянием',
        description: 'Полярное сияние, мерцающие звёзды и матовое стекло. Спокойная ночная палитра с бирюзовыми акцентами.',
        tags: ['Полярное сияние', 'Матовое стекло'],
        details: ['Анимированные волны сияния, лучи и падающие звёзды.', 'Свечение навигации, кнопок и шкал трафика; поддержка уменьшения движения.'],
        install: { repository: 'https://github.com/austnv/minishop-themes', branch: 'master', directory: 'themes/aurora' },
      },
      {
        id: 'solar',
        name: 'Solar',
        author: 'austnv',
        authorUrl: 'https://github.com/austnv',
        repository: 'https://github.com/austnv/minishop-themes/tree/master/themes/solar',
        forge: 'GitHub',
        preview: '/awesome/solar.webp',
        previewAlt: 'Solar: интерфейс Minishop в тёплой солнечной палитре',
        description: 'Золотой час в вашем Mini App: солнце, янтарные поверхности и тёплые световые акценты.',
        tags: ['Тёплая палитра', 'Светлая и тёмная'],
        details: ['Солнечный диск, вращающиеся лучи и золотые частицы.', 'Светлый и тёмный варианты с янтарным стеклом и анимированными акцентами.'],
        install: { repository: 'https://github.com/austnv/minishop-themes', branch: 'master', directory: 'themes/solar' },
      },
      {
        id: 'universe',
        name: 'Universe',
        author: 'austnv',
        authorUrl: 'https://github.com/austnv',
        repository: 'https://github.com/austnv/minishop-themes/tree/master/themes/universe',
        forge: 'GitHub',
        preview: '/awesome/universe.webp',
        previewAlt: 'Universe: космический интерфейс Minishop со звёздами и стеклянными панелями',
        description: 'Глубокий космос, туманности и кометы. Стеклянные панели и голубые акценты на звёздном фоне.',
        tags: ['Космос', 'Анимация'],
        details: ['Два слоя звёзд, дрейфующие туманности и пролетающие кометы.', 'Пульсирующие акценты, переливающийся логотип и облегчённые эффекты на мобильных устройствах.'],
        install: { repository: 'https://github.com/austnv/minishop-themes', branch: 'master', directory: 'themes/universe' },
      },
      {
        id: 'liquid-glass',
        name: 'Liquid Glass',
        author: 'BADtochka',
        authorUrl: 'https://github.com/BADtochka',
        repository: 'https://github.com/BADtochka/liquid-glass-minishop-theme/tree/main',
        forge: 'GitHub',
        preview: '/awesome/liquid-glass.webp',
        previewAlt: 'Liquid Glass: полупрозрачные панели Minishop с зелёными акцентами',
        description: 'Полупрозрачные поверхности, мягкое свечение и выразительное стекло. В коллекции — зелёная и розовая версии.',
        tags: ['Glass UI', 'Две палитры'],
        details: ['Liquid Glass — тёмная тема с холодной зелёной палитрой; Liquid Pink — с розовыми акцентами.', 'Оформление Mini App и админки с сохранением стандартной структуры Minishop.'],
        install: { repository: 'https://github.com/BADtochka/liquid-glass-minishop-theme', branch: 'main' },
      },
      {
        id: 'avio-soft',
        name: 'Avio Soft',
        author: 'drobyazkome',
        authorUrl: 'https://github.com/drobyazkome',
        repository: 'https://github.com/drobyazkome/avio-soft-minishop-theme',
        forge: 'GitHub',
        preview: '/awesome/avio-soft.webp',
        previewAlt: 'Avio Soft: светлый и тёмный интерфейсы Minishop с персонажем-замком',
        description: 'Мягкое небо, округлые карточки и живой персонаж-замок, который реагирует на состояние подписки.',
        tags: ['Мягкий стиль', 'Персонаж-замок'],
        details: ['Замок меняет настроение в зависимости от подписки и остатка трафика.', 'Светлый и тёмный режимы; эффекты времени суток, сезонов и праздников.'],
        install: { repository: 'https://github.com/drobyazkome/avio-soft-minishop-theme', branch: 'main' },
      },
      {
        id: 'avio',
        name: 'Avio',
        author: 'drobyazkome',
        authorUrl: 'https://github.com/drobyazkome',
        repository: 'https://github.com/drobyazkome/avio-minishop-theme',
        forge: 'GitHub',
        preview: '/awesome/avio.webp',
        previewAlt: 'Avio: интерфейс Minishop с крупными карточками подписки и действий',
        description: 'Тема с вниманием к главному действию: подписка, трафик и нужная кнопка собраны в понятные карточки.',
        tags: ['Карточки', 'Главное действие'],
        details: ['Основное действие на главной меняется в зависимости от состояния подписки.', 'Оформление поверх стандартной разметки Core средствами темы.'],
        install: { repository: 'https://github.com/drobyazkome/avio-minishop-theme', branch: 'main' },
      },
      {
        id: 'cyberpunk2077',
        name: 'Cyberpunk 2077',
        author: 'wormy09',
        authorUrl: 'https://gitlab.com/wormy09',
        repository: 'https://gitlab.com/wormy09/minishop-theme-cyberpunk2077/-/tree/main',
        forge: 'GitLab',
        preview: '/awesome/cyberpunk2077.webp',
        previewAlt: 'Cyberpunk 2077: неоновый HUD Minishop в ночном и дневном мегаполисе',
        description: 'Неоновый мегаполис, HUD со срезанными углами и дрон-талисман. Неофициальная фан-тема в духе Cyberpunk 2077.',
        tags: ['Неоновый HUD', 'Светлая и тёмная'],
        details: ['Ночной и дневной мегаполис; интерфейс реагирует на состояние подписки и трафика.', 'Дрон-талисман и необязательные эффекты помех. Требуется Minishop 3.8.0 или новее.'],
        install: { repository: 'https://gitlab.com/wormy09/minishop-theme-cyberpunk2077', branch: 'main' },
      },
    ],
  },
  {
    id: 'plugins',
    title: 'Плагины',
    icon: 'plugins',
    description: 'Дополнительные сценарии и возможности внутри Minishop.',
    guide: { label: 'О плагинах Minishop', href: '/development/plugins/' },
    projects: [
      {
        id: 'kiro-wheel',
        name: 'Kiro Wheel',
        author: 'kiroproject',
        authorUrl: 'https://github.com/kiroproject',
        repository: 'https://github.com/kiroproject/kiro-wheel',
        forge: 'GitHub',
        preview: '/awesome/kiro-wheel.svg',
        previewAlt: 'Обложка Kiro Wheel: колесо удачи с призовыми секторами',
        cover: true,
        description: 'Колесо удачи для Minishop: призы для пользователей и настройка колеса в административной панели.',
        tags: ['Колесо удачи', 'Бонусы'],
        details: ['Клиентский экран колеса, карточка и пункт в настройках.', 'Административный интерфейс для призов, шансов и статистики. Пакет установки — в репозитории.'],
      },
    ],
  },
  {
    id: 'tools',
    title: 'Инструменты',
    icon: 'tools',
    description: 'Сервисы и утилиты, которые помогают в ежедневной работе.',
    guide: { label: 'Поддержка в Minishop', href: '/features/support/' },
    projects: [
      {
        id: 'ai-support',
        name: 'AI Support',
        author: 'tagashi666',
        authorUrl: 'https://github.com/tagashi666',
        repository: 'https://github.com/tagashi666/ai-support',
        forge: 'GitHub',
        preview: '/awesome/ai-support.svg',
        previewAlt: 'Обложка AI Support: обращения, база знаний и AI-помощник в едином центре поддержки',
        cover: true,
        description: 'Собственный центр поддержки с единой очередью обращений, операторами, базой знаний и AI-помощником.',
        tags: ['Техподдержка', 'AI-помощник'],
        details: ['Интеграции с Minishop, Telegram и Bedolaga; двусторонние ответы и статусы тикетов.', 'SLA, шаблоны, вложения, статистика и AI-помощник с OpenAI-совместимым провайдером.'],
      },
    ],
  },
];

// Public API snapshot, used until the browser refreshes the count or when offline.
export const starsVerifiedAt = '2026-10-02';
export const repositoryStars: Record<string, number> = {
  'austnv/minishop-themes': 1,
  'BADtochka/liquid-glass-minishop-theme': 0,
  'drobyazkome/avio-soft-minishop-theme': 1,
  'drobyazkome/avio-minishop-theme': 0,
  'kiroproject/kiro-wheel': 0,
  'tagashi666/ai-support': 25,
  'wormy09/minishop-theme-cyberpunk2077': 0,
};
