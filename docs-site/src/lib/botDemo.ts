import { storeBotDemoPayments } from '../../../frontend/src/lib/webapp/previewMock/telegramBotDemoHistory';
import { BotDemoConversation, parseScenario, type BotRole, type ChatMessage, type Language, type Messages, type Popup } from './botDemoConversation';
import type { BotDemoData } from './botDemoData';

const labels = {
  ru: {
    role: 'бот', today: 'Сегодня', menu: 'Меню', webapp: 'Личный кабинет', start: 'Запустить',
    placeholder: 'Сообщение', reset: 'Сбросить чат', send: 'Отправить', commands: 'Команды бота',
    history: 'Сообщения', close: 'Закрыть', checkout: 'Оплата', receipt: 'Квитанция',
    demoPayment: 'Тестовый платёж', confirmPayment: 'Оплатить', confirmProvider: 'Подтвердить тестовый платёж',
    support: 'Демонстрационный чат поддержки',
  },
  en: {
    role: 'bot', today: 'Today', menu: 'Menu', webapp: 'My account', start: 'Start',
    placeholder: 'Message', reset: 'Reset chat', send: 'Send', commands: 'Bot commands',
    history: 'Messages', close: 'Close', checkout: 'Checkout', receipt: 'Receipt',
    demoPayment: 'Demo payment', confirmPayment: 'Pay', confirmProvider: 'Confirm demo payment',
    support: 'Sample support chat',
  },
};

function chatText(text: string, outgoing: boolean) {
  const content = document.createElement('span');
  content.className = 'bot-chat-message-text';
  if (outgoing) {
    content.textContent = text;
    return content;
  }

  const template = document.createElement('template');
  template.innerHTML = text;
  const formatting = new Set(['B', 'I', 'CODE', 'BLOCKQUOTE', 'PRE', 'BR']);
  function copyFormatting(source: Node, target: HTMLElement) {
    for (const child of Array.from(source.childNodes)) {
      if (child.nodeType === Node.TEXT_NODE) target.append(child.cloneNode());
      if (!(child instanceof HTMLElement)) continue;
      if (formatting.has(child.tagName)) {
        const element = document.createElement(child.tagName);
        copyFormatting(child, element);
        target.append(element);
      } else {
        copyFormatting(child, target);
      }
    }
  }
  copyFormatting(template.content, content);
  return content;
}

export function mountBotDemo(demo: HTMLElement) {
  const element = <T extends HTMLElement = HTMLElement>(name: string) =>
    demo.querySelector<T>(`[data-${name}]`)!;
  const messages = JSON.parse(demo.dataset.messages ?? '{}') as Record<Language, Messages>;
  const fixtures = JSON.parse(element('fixtures').textContent!) as BotDemoData;
  const search = new URLSearchParams(location.search);
  const role = search.get('role');
  const bot = new BotDemoConversation(
    messages, fixtures, search.get('lang') === 'en' ? 'en' : 'ru', parseScenario(search.get('scenario')),
    role === 'admin' || role === 'owner' ? role : 'user',
    search.get('menu') === 'admin' && (role === 'admin' || role === 'owner') ? 'admin'
      : search.get('menu') === 'bot' ? 'bot' : 'main',
    search.get('admin_data') === 'empty', demo.dataset.captcha ?? '',
  );
  const chat = demo.querySelector<HTMLElement>('.bot-chat')!;
  const options = element<HTMLDetailsElement>('demo-options');
  const narrow = matchMedia('(max-width: 47.99rem)');
  options.open = !narrow.matches;
  narrow.addEventListener('change', ({ matches }) => { options.open = !matches; });
  const scenarioSelect = element<HTMLSelectElement>('scenario');
  const roleSelect = element<HTMLSelectElement>('role');
  const adminDataSelect = element<HTMLSelectElement>('admin-data');
  const attachmentInput = element<HTMLInputElement>('attachment-input');
  const appMode = demo.querySelector<HTMLInputElement>('input[name="bot-menu"][value="webapp"]')!;
  const commandsMode = demo.querySelector<HTMLInputElement>('input[name="bot-menu"][value="commands"]')!;
  const history = element('history');
  const commandInput = element<HTMLInputElement>('command-input');
  const menuButton = element<HTMLButtonElement>('chat-menu');
  const webappButton = element<HTMLButtonElement>('chat-webapp');
  const composer = element<HTMLFormElement>('composer');
  const commandList = element('commands');
  const notice = element('notice');
  const dialog = element<HTMLDialogElement>('dialog');
  const frame = element<HTMLIFrameElement>('embed');
  const confirmButton = element<HTMLButtonElement>('dialog-confirm');
  const resetButton = demo.querySelector<HTMLButtonElement>('[data-action="reset"]')!;
  const sendButton = composer.querySelector<HTMLButtonElement>('[type="submit"]')!;
  let popup: Popup | undefined;
  let trialWatcher: MutationObserver | undefined;
  let previousFocus: HTMLElement | null = null;
  let noticeTimer = 0;
  scenarioSelect.value = bot.scenario;
  roleSelect.value = bot.role;
  adminDataSelect.value = bot.emptyAdmin ? 'empty' : 'sample';
  appMode.checked = bot.settings.app && search.get('button') === 'webapp';
  commandsMode.checked = !appMode.checked;

  const docsRoot = document.documentElement;
  const theme = () => docsRoot.dataset.theme === 'dark' ? 'dark' : 'light';
  const link = element<HTMLAnchorElement>('web-link');
  const webParams = (mock = bot.webMock) => new URLSearchParams({
    mock, theme_preview: theme(), lang: bot.language,
  });

  function updateWebLink() {
    link.href = `/demo/home?${webParams()}`;
  }
  new MutationObserver(updateWebLink).observe(docsRoot, { attributes: true, attributeFilter: ['data-theme'] });

  function syncUrl() {
    const url = new URL(location.href);
    const choices = {
      scenario: bot.scenario === 'new' ? '' : bot.scenario,
      role: bot.role === 'user' ? '' : bot.role,
      admin_data: bot.canAdmin && bot.emptyAdmin ? 'empty' : '',
      button: appMode.checked ? 'webapp' : '',
      lang: bot.language === 'en' ? 'en' : '',
      menu: bot.menu === 'main' ? '' : bot.menu,
    };
    for (const [name, value] of Object.entries(choices)) {
      if (value) url.searchParams.set(name, value);
      else url.searchParams.delete(name);
    }
    if (url.href !== location.href) window.history.replaceState(null, '', url);
  }

  function showCommands(open: boolean) {
    commandList.hidden = !open;
    menuButton.setAttribute('aria-expanded', String(open));
  }

  function showNotice() {
    clearTimeout(noticeTimer);
    notice.textContent = bot.notice;
    notice.hidden = !bot.notice;
    if (bot.notice) noticeTimer = window.setTimeout(() => { notice.hidden = true; }, 2700);
    bot.notice = '';
  }

  function frameUrl(target: Extract<Popup, { kind: 'app' | 'browser' }>) {
    let mock = bot.webMock;
    if (target.route === '/status') mock = 'server-status';
    const paymentHistory = target.route === '/settings/payments';
    if (paymentHistory && !bot.settings.active) mock = 'payment-history-empty';
    const params = webParams(mock);
    params.set('bot_demo_role', bot.role);
    if (paymentHistory && bot.completedPayments.length && storeBotDemoPayments(bot.completedPayments)) {
      params.set('bot_demo_history', '1');
    }
    if (target.route) params.set('path', target.route);
    if (target.kind === 'app' && target.start) params.set('startapp', target.start);
    const telegram = target.kind === 'app'
      ? '#tgWebAppVersion=8.0&tgWebAppPlatform=android&tgWebAppData=demo&tgWebAppFullscreen=1' : '';
    return `/demo/runtime/app/index.html?${params}${telegram}`;
  }

  function downloadFile(target: Extract<Popup, { kind: 'download' }>) {
    const url = URL.createObjectURL(new Blob(['\ufeff', target.content], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = target.filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function openPopup(target: Exclude<Popup, { kind: 'download' }>, trigger: HTMLElement) {
    const label = labels[bot.language];
    const heading = element('dialog-title');
    const address = element('dialog-address');
    const body = element('dialog-body');
    const total = element('dialog-total');
    const note = element('dialog-note');
    trialWatcher?.disconnect();
    popup = target;
    previousFocus = trigger;
    dialog.dataset.kind = target.kind;
    dialog.lang = bot.language;
    heading.textContent = target.kind === 'stars' ? target.confirm ? label.checkout : label.receipt : target.title;
    address.hidden = !('address' in target);
    address.textContent = 'address' in target ? target.address : '';
    body.textContent = target.kind === 'stars' ? target.title
      : target.kind === 'support' ? label.support
        : target.kind === 'profile' ? target.username ? `@${target.username}` : ''
        : target.kind === 'browser' ? target.body ?? '' : '';
    body.hidden = !body.textContent;
    const charge = target.kind === 'stars' ? `⭐ ${target.total}` : 'total' in target ? target.total : undefined;
    total.textContent = charge ?? '';
    total.hidden = !charge;
    note.textContent = label.demoPayment;
    note.hidden = !charge;
    confirmButton.hidden = !('confirm' in target && target.confirm);
    confirmButton.textContent = target.kind === 'stars'
      ? `${label.confirmPayment} ${charge}` : label.confirmProvider;
    element('dialog-close').setAttribute('aria-label', label.close);
    frame.hidden = !('route' in target && target.route);
    if (!frame.hidden && (target.kind === 'app' || target.kind === 'browser')) {
      frame.title = target.title;
      frame.src = frameUrl(target);
    }
    showCommands(false);
    dialog.showModal();
  }

  function renderMessage(message: ChatMessage) {
    const row = document.createElement('div');
    const bubble = document.createElement('div');
    const clock = document.createElement('span');
    bubble.className = 'bot-chat-bubble';
    clock.className = 'bot-chat-time';
    clock.textContent = message.outgoing ? '12:00 ✓✓' : '12:00';
    if (message.outgoing) bubble.classList.add('bot-chat-bubble-out');
    if (message.invoice) bubble.classList.add('bot-chat-invoice');
    if (!message.outgoing && !message.rows) row.classList.add('bot-chat-simple');
    else row.classList.add(message.outgoing ? 'bot-chat-outgoing' : 'bot-chat-reply');
    if (message.image) {
      const image = document.createElement('img');
      image.className = 'bot-chat-captcha';
      image.src = message.image;
      image.alt = bot.t('trial_captcha_bot_prompt');
      bubble.append(image);
    }
    bubble.append(chatText(message.text, Boolean(message.outgoing)), clock);
    row.append(bubble);
    if (message.rows?.length) {
      const keyboard = document.createElement('div');
      keyboard.className = 'bot-chat-keyboard';
      keyboard.dataset.keyboard = '';
      for (const buttons of message.rows) {
        const group = document.createElement('div');
        group.className = 'bot-chat-keyboard-row';
        for (const button of Array.isArray(buttons) ? buttons : [buttons]) {
          const control = document.createElement('button');
          control.type = 'button';
          control.textContent = button.label;
          if (button.external) {
            control.classList.add('bot-chat-external');
            control.setAttribute('aria-label', button.label);
          }
          if (button.pay) control.classList.add('bot-chat-pay');
          control.addEventListener('click', () => {
            const count = bot.messages.length;
            const target = button.activate();
            if (!target) {
              render(bot.messages.length > count ? bot.messages.at(-1) : message);
            } else if (target.kind === 'download') {
              downloadFile(target);
            } else {
              openPopup(target, control);
            }
          });
          group.append(control);
        }
        keyboard.append(group);
      }
      row.append(keyboard);
    }
    return row;
  }

  function render(focusMessage?: ChatMessage) {
    const label = labels[bot.language];
    const initial = bot.messages.length === 0;
    chat.lang = bot.language;
    element('admin-entry').hidden = !bot.canAdmin;
    element('admin-data-group').hidden = !bot.canAdmin;
    element('attachment').hidden = !bot.canAttach;
    attachmentInput.setAttribute('aria-label', bot.language === 'ru' ? 'Прикрепить файл' : 'Attach file');
    element('scenario-description').textContent = bot.settings.description;
    if (!bot.settings.app && appMode.checked) commandsMode.checked = true;
    appMode.disabled = !bot.settings.app;
    menuButton.hidden = initial || appMode.checked;
    webappButton.hidden = initial || !appMode.checked;
    commandInput.hidden = initial;
    element('start').hidden = !initial;
    element('chat-role').textContent = label.role;
    element('menu-label').textContent = label.menu;
    element('webapp-label').textContent = label.webapp;
    element('start').textContent = label.start;
    element('start-description').textContent = bot.t('bot_command_start_description');
    element('bot-description').textContent = bot.t('bot_command_tg_description');
    resetButton.title = label.reset;
    resetButton.setAttribute('aria-label', label.reset);
    sendButton.title = label.send;
    sendButton.setAttribute('aria-label', label.send);
    sendButton.hidden = initial;
    commandInput.placeholder = label.placeholder;
    commandInput.setAttribute('aria-label', label.placeholder);
    commandList.setAttribute('aria-label', label.commands);
    history.setAttribute('aria-label', label.history);
    const day = document.createElement('div');
    day.className = 'bot-chat-day';
    day.textContent = label.today;
    const rows = bot.messages.map(renderMessage);
    history.replaceChildren(...(initial ? [] : [day, ...rows]));
    const row = focusMessage ? rows[bot.messages.indexOf(focusMessage)] : undefined;
    if (row) {
      const focus = row.querySelector('button') ?? commandInput;
      focus.focus({ preventScroll: true });
      if (focusMessage === bot.messages.at(-1)) history.scrollTop = history.scrollHeight;
      else row.scrollIntoView({ block: 'nearest', container: 'nearest' } as ScrollIntoViewOptions);
    } else {
      history.scrollTop = history.scrollHeight;
    }
    updateWebLink();
    showNotice();
    syncUrl();
  }

  function send(value: string) {
    if (!value) return;
    bot.send(value);
    commandInput.value = '';
    showCommands(false);
    render(bot.messages.at(-1));
  }

  function syncTrialResult() {
    if (bot.subscribed || popup?.kind !== 'app' || popup.route !== '/trial') return;
    const headings = frame.contentDocument?.querySelectorAll('h1, h2') ?? [];
    if (Array.from(headings).some((heading) => heading.textContent?.trim() === bot.t('wa_trial_activated'))) {
      bot.activateTrial();
      updateWebLink();
      trialWatcher?.disconnect();
    }
  }

  frame.addEventListener('load', () => {
    if (popup?.kind !== 'app' || popup.route !== '/trial' || !frame.contentDocument) return;
    trialWatcher?.disconnect();
    trialWatcher = new MutationObserver(syncTrialResult);
    trialWatcher.observe(frame.contentDocument, { childList: true, subtree: true });
    syncTrialResult();
  });
  dialog.addEventListener('close', () => {
    if (dialog.open) return;
    syncTrialResult();
    trialWatcher?.disconnect();
    trialWatcher = undefined;
    frame.removeAttribute('src');
    popup = undefined;
    if (previousFocus?.isConnected && document.activeElement === document.body) {
      previousFocus.focus({ preventScroll: true });
    }
    previousFocus = null;
  });
  confirmButton.addEventListener('click', () => {
    if (popup && 'confirm' in popup && popup.confirm) {
      popup.confirm();
      dialog.close();
      render(bot.messages.at(-1));
    }
  });

  demo.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) return;
    const action = event.target.closest<HTMLElement>('[data-action]')?.dataset.action;
    switch (action) {
      case 'commands': {
        const open = commandList.hidden === true;
        showCommands(open);
        if (open) commandList.querySelector('button')?.focus();
        break;
      }
      case 'main':
      case 'bot':
        send(action === 'main' ? '/start' : '/tg');
        break;
      case 'admin':
        if (bot.canAdmin) send('/admin');
        break;
      case 'open-app':
        openPopup({ kind: 'app', title: labels[bot.language].webapp, route: '/home' }, webappButton);
        break;
      case 'reset':
        bot.reset();
        showCommands(false);
        render();
        element('start').focus({ preventScroll: true });
        break;
      default:
        if (!composer.contains(event.target)) showCommands(false);
    }
  });
  composer.addEventListener('submit', (event) => {
    event.preventDefault();
    send(commandInput.value.trim());
  });
  composer.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !commandList.hidden) {
      showCommands(false);
      menuButton.focus();
    }
  });
  commandInput.addEventListener('input', () => {
    showCommands(!appMode.checked && commandInput.value === '/');
  });
  attachmentInput.addEventListener('change', () => {
    const file = attachmentInput.files?.[0];
    if (!file || !bot.canAttach) return;
    bot.sendAttachment(file.name, commandInput.value.trim());
    attachmentInput.value = '';
    commandInput.value = '';
    render(bot.messages.at(-1));
  });
  demo.addEventListener('change', (event) => {
    if (event.target === scenarioSelect || event.target === roleSelect || event.target === adminDataSelect) {
      bot.role = roleSelect.value as BotRole;
      bot.emptyAdmin = adminDataSelect.value === 'empty';
      const command = bot.menu === 'admin' && bot.canAdmin ? '/admin' : bot.menu === 'bot' ? '/tg' : '/start';
      if (event.target === scenarioSelect) {
        bot.reset(parseScenario(scenarioSelect.value));
      } else {
        bot.clearConversation();
        if (event.target === adminDataSelect) bot.resetAdmin();
      }
      bot.send(command);
      render();
    } else if (event.target === appMode || event.target === commandsMode) {
      showCommands(false);
      menuButton.hidden = !commandsMode.checked;
      webappButton.hidden = !appMode.checked;
      syncUrl();
    }
  });

  render();
}
