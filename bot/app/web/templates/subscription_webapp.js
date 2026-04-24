/* WEBAPP_DEV_MOCK_START */
window.__WEBAPP_DEV_MOCK__ = {
      config: {
        title: 'Моя подписка',
        primaryColor: '#00fe7a',
        logoUrl: '',
        apiBase: '/api',
        supportUrl: 'https://t.me/support',
        privacyPolicyUrl: 'https://example.com/privacy',
        userAgreementUrl: 'https://example.com/agreement',
        currency: 'RUB',
        language: 'ru',
        emailAuthEnabled: true,
        telegramLoginBotUsername: 'preview_bot'
      },
      data: {
        ok: true,
        user: {
          id: 100200300,
          username: 'preview',
          email: '',
          email_verified: false,
          telegram_id: 100200300,
          telegram_linked: true,
          first_name: 'Preview',
          language_code: 'ru'
        },
        subscription: {
          active: true,
          status: 'ACTIVE',
          remaining_text: '27 д. 5 ч.',
          end_date_text: '19.05.2026 22:40',
          days_left: 27,
          config_link: 'https://sub.example.com/sub/preview-token',
          connect_url: 'https://sub.example.com/connect/preview-token',
          traffic_used: '18.42 GB',
          traffic_limit: '500.00 GB',
          auto_renew_enabled: false,
          provider: null
        },
        plans: [
          {months: 1, price: 190, currency: 'RUB', title: '1 месяц'},
          {months: 3, price: 550, currency: 'RUB', title: '3 месяца'},
          {months: 6, price: 1100, currency: 'RUB', title: '6 месяцев'},
          {months: 12, price: 2000, currency: 'RUB', title: '12 месяцев'}
        ],
        payment_methods: [
          {id: 'cryptopay', name: 'CryptoPay'},
          {id: 'platega', name: 'Platega'},
          {id: 'freekassa', name: 'FreeKassa / СБП'}
        ],
        referral: {
          code: 'AB12CD34E',
          bot_link: 'https://t.me/preview_bot?start=ref_uAB12CD34E',
          webapp_link: 'https://app.example.com/?ref=uAB12CD34E',
          invited_count: 3,
          purchased_count: 1,
          bonus_details: [
            {months: 1, title: '1 месяц', inviter_days: 3, friend_days: 3},
            {months: 3, title: '3 месяца', inviter_days: 10, friend_days: 7}
          ]
        },
        settings: {
          support_url: 'https://t.me/support',
          traffic_mode: false,
          email_auth_enabled: true
        }
      }
    };
/* WEBAPP_DEV_MOCK_END */

const MOCK = (() => {
      const mock = window.__WEBAPP_DEV_MOCK__;
      const host = window.location.hostname;
      const isLocal = window.location.protocol === 'file:' || host === 'localhost' || host === '127.0.0.1' || host === '';
      return mock && isLocal ? mock : null;
    })();
    const CFG = window.__WEBAPP_CONFIG__ || (MOCK && MOCK.config) || {};
    const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
    const TELEGRAM_LOGIN_WIDGET_URL = './telegram-widget.js';
    const state = {
      token: MOCK ? 'local-preview' : (localStorage.getItem('rw_webapp_token') || ''),
      data: null,
      selectedPlan: null,
      selectedMethod: null,
      referralParam: readReferralParam(),
      promoApplying: false,
      payment: null,
      paymentFlowOpen: false,
      promoModalOpen: false,
      referralModalOpen: false,
      paymentStep: 'plan',
      creatingPayment: false,
      authInProgress: false,
      authMode: (CFG.emailAuthEnabled === false ? 'telegram' : 'email'),
      emailLoginPending: false,
      emailLoginEmail: '',
      emailLoginCodeModalOpen: false,
      emailLoginVerifying: false,
      emailLoginResending: false,
      emailLinkPending: false,
      emailLinkEmail: '',
      promoStatusTimer: null,
      promoStatusType: '',
      promoStatusText: '',
      telegramLinkRendered: false,
      telegramLinkInProgress: false,
      toastTimer: null
    };

    const I18N = {
      ru: {
        page_title: 'Моя подписка',
        loading: 'Загрузка...',
        refresh: 'Обновить',
        logout: 'Выйти',
        subscription: 'Подписка',
        subscription_subtitle: 'Ваша ссылка подключения и срок доступа',
        ends_at: 'Окончание',
        traffic: 'Трафик',
        connect: 'Подключиться',
        copy_link: 'Скопировать ссылку',
        extend_subscription: 'Купить подписку / Добавить дни',
        payment_title: 'Оплата подписки',
        payment_caption: 'Выберите срок, способ оплаты и создайте платеж.',
        close: 'Закрыть',
        close_payment: 'Закрыть оплату',
        payment_steps: 'Шаги оплаты',
        step_plan: 'Срок',
        step_method: 'Метод',
        step_result: 'Платеж',
        select_period: 'Выберите срок',
        select_method: 'Выберите способ оплаты',
        payment_status: 'Статус платежа',
        choose_payment_method: 'Выбрать способ оплаты',
        back: 'Назад',
        create_payment: 'Создать платеж',
        open_payment: 'Открыть оплату',
        check_payment: 'Проверить оплату',
        choose_other_method: 'Выбрать другой способ',
        support: 'Поддержка',
        account_title: 'Аккаунт',
        account_caption: 'Способы входа',
        email_label: 'Email',
        telegram_label: 'Telegram',
        linked: 'Привязан',
        not_linked: 'Не привязан',
        email_login_tab: 'Email',
        telegram_login_tab: 'Telegram',
        email_placeholder: 'mail@example.com',
        code_placeholder: '000000',
        send_code: 'Отправить код',
        resend_code: 'Отправить еще раз',
        confirm: 'Подтвердить',
        login: 'Войти',
        email_code_title: 'Подтвердите вход',
        email_code_caption: 'Введите 6-значный код из письма.',
        email_code_aria: 'Код подтверждения',
        email_auth_disabled: 'Вход по email пока не настроен.',
        email_required: 'Введите email',
        email_invalid: 'Введите корректный email',
        email_code_sending: 'Отправляю код...',
        email_code_sent: 'Код отправлен на почту',
        email_code_send_failed: 'Не удалось отправить код',
        email_code_invalid: 'Неверный код',
        email_code_expired: 'Код устарел',
        email_rate_limited: 'Повторная отправка доступна через {seconds} сек.',
        email_linked: 'Email привязан',
        telegram_linked: 'Telegram привязан',
        account_merge_conflict: 'Этот аккаунт уже связан с другими данными.',
        telegram_auth: 'Telegram auth',
        telegram_auth_verifying: 'Проверяю вход...',
        telegram_auth_failed: 'Не удалось подтвердить Telegram-вход. Попробуйте еще раз.',
        telegram_auth_unavailable: 'Telegram Login Widget недоступен. Проверьте username бота и доступ к telegram.org.',
        telegram_auth_access_denied: 'Доступ запрещен.',
        active: 'Активна',
        inactive: 'Не активна',
        no_active_subscription: 'Нет активной подписки',
        not_available: 'N/A',
        no_plans: 'Тарифы не настроены.',
        access_period: 'Срок доступа',
        choose_plan_first: 'Сначала выберите срок подписки.',
        no_methods: 'Нет доступных способов оплаты.',
        payment_not_created: 'Платеж еще не создан.',
        invoice_sent: 'Счет отправлен в чат с ботом. После оплаты вернитесь сюда и проверьте статус.',
        payment_created: 'Платеж создан. Откройте оплату, завершите ее у провайдера и затем проверьте статус.',
        updating: 'Обновляю данные',
        choose_plan_toast: 'Выберите срок подписки',
        choose_method_toast: 'Выберите способ оплаты',
        create_payment_toast: 'Создайте платеж',
        payment_confirmed: 'Оплата подтверждена',
        payment_pending: 'Платеж пока не подтвержден',
        link_copied: 'Ссылка скопирована',
        no_link: 'Ссылка пока недоступна',
        payment_error: 'Ошибка оплаты',
        privacy_policy: 'Политика конфиденциальности',
        user_agreement: 'Пользовательское соглашение',
        promo_title: 'Промокод',
        promo_caption: 'Введите код, чтобы начислить бонусные дни.',
        promo_placeholder: 'PROMO2026',
        apply_promo: 'Применить',
        promo_applied: 'Промокод применен',
        promo_applied_ok: 'Промокод применен, всё ок.',
        promo_empty: 'Введите промокод',
        promo_invalid: 'Промокод не найден или недействителен.',
        referral_title: 'Пригласить друга',
        referral_caption: 'Поделитесь кодом или ссылкой и получайте бонусы.',
        referral_code: 'Ваш код',
        invited_friends: 'Приглашено',
        purchased_friends: 'Оплатили',
        copy_code: 'Скопировать код',
        copy_webapp_link: 'Скопировать ссылку Web App',
        copy_bot_link: 'Скопировать ссылку бота',
        referral_copied: 'Ссылка скопирована',
        code_copied: 'Код скопирован',
        referral_site_label: 'Пригласить через сайт',
        referral_telegram_label: 'Пригласить через телеграм',
        referral_bonus_title: 'Бонусы',
        referral_bonus_pair: 'Вы: {inviter} дн. / друг: {friend} дн.',
        referral_no_bonuses: 'Бонусы пока не настроены.'
      },
      en: {
        page_title: 'My subscription',
        loading: 'Loading...',
        refresh: 'Refresh',
        logout: 'Log out',
        subscription: 'Subscription',
        subscription_subtitle: 'Your connection link and access time',
        ends_at: 'Ends at',
        traffic: 'Traffic',
        connect: 'Connect',
        copy_link: 'Copy link',
        extend_subscription: 'Renew subscription/Add days',
        payment_title: 'Subscription payment',
        payment_caption: 'Choose a period, payment method, and create a payment.',
        close: 'Close',
        close_payment: 'Close payment',
        payment_steps: 'Payment steps',
        step_plan: 'Period',
        step_method: 'Method',
        step_result: 'Payment',
        select_period: 'Select period',
        select_method: 'Select payment method',
        payment_status: 'Payment status',
        choose_payment_method: 'Choose payment method',
        back: 'Back',
        create_payment: 'Create payment',
        open_payment: 'Open payment',
        check_payment: 'Check payment',
        choose_other_method: 'Choose another method',
        support: 'Support',
        account_title: 'Account',
        account_caption: 'Sign-in methods',
        email_label: 'Email',
        telegram_label: 'Telegram',
        linked: 'Linked',
        not_linked: 'Not linked',
        email_login_tab: 'Email',
        telegram_login_tab: 'Telegram',
        email_placeholder: 'mail@example.com',
        code_placeholder: '000000',
        send_code: 'Send code',
        resend_code: 'Send again',
        confirm: 'Confirm',
        login: 'Log in',
        email_code_title: 'Confirm login',
        email_code_caption: 'Enter the 6-digit code from the email.',
        email_code_aria: 'Verification code',
        email_auth_disabled: 'Email sign-in is not configured yet.',
        email_required: 'Enter your email',
        email_invalid: 'Enter a valid email address',
        email_code_sending: 'Sending code...',
        email_code_sent: 'Code sent to email',
        email_code_send_failed: 'Could not send code',
        email_code_invalid: 'Invalid code',
        email_code_expired: 'Code expired',
        email_rate_limited: 'Try again in {seconds} sec.',
        email_linked: 'Email linked',
        telegram_linked: 'Telegram linked',
        account_merge_conflict: 'This account is already linked to different data.',
        telegram_auth: 'Telegram auth',
        telegram_auth_verifying: 'Verifying login...',
        telegram_auth_failed: 'Could not verify Telegram login. Try again.',
        telegram_auth_unavailable: 'Telegram Login Widget is unavailable. Check the bot username and access to telegram.org.',
        telegram_auth_access_denied: 'Access denied.',
        active: 'Active',
        inactive: 'Inactive',
        no_active_subscription: 'No active subscription',
        not_available: 'N/A',
        no_plans: 'Plans are not configured.',
        access_period: 'Access period',
        choose_plan_first: 'Choose a subscription period first.',
        no_methods: 'No payment methods available.',
        payment_not_created: 'Payment has not been created yet.',
        invoice_sent: 'The invoice was sent to the bot chat. Pay it, then return here and check the status.',
        payment_created: 'Payment was created. Open it, complete payment with the provider, then check the status.',
        updating: 'Refreshing data',
        choose_plan_toast: 'Choose a subscription period',
        choose_method_toast: 'Choose a payment method',
        create_payment_toast: 'Create a payment',
        payment_confirmed: 'Payment confirmed',
        payment_pending: 'Payment is not confirmed yet',
        link_copied: 'Link copied',
        no_link: 'Link is not available yet',
        payment_error: 'Payment error',
        privacy_policy: 'Privacy policy',
        user_agreement: 'User agreement',
        promo_title: 'Promo code',
        promo_caption: 'Enter a code to add bonus days.',
        promo_placeholder: 'PROMO2026',
        apply_promo: 'Apply',
        promo_applied: 'Promo code applied',
        promo_applied_ok: 'Promo code applied, all good.',
        promo_empty: 'Enter promo code',
        promo_invalid: 'Promo code was not found or is not valid.',
        referral_title: 'Invite friend',
        referral_caption: 'Share your code or link and receive bonuses.',
        referral_code: 'Your code',
        invited_friends: 'Invited',
        purchased_friends: 'Purchased',
        copy_code: 'Copy code',
        copy_webapp_link: 'Copy Web App link',
        copy_bot_link: 'Copy bot link',
        referral_copied: 'Link copied',
        code_copied: 'Code copied',
        referral_site_label: 'Invite via site',
        referral_telegram_label: 'Invite via Telegram',
        referral_bonus_title: 'Bonuses',
        referral_bonus_pair: 'You: {inviter} d. / friend: {friend} d.',
        referral_no_bonuses: 'Bonuses are not configured yet.'
      }
    };

    const accent = CFG.primaryColor || '#00fe7a';
    document.documentElement.style.setProperty('--accent', accent);
    setBrand();
    applyI18n();
    applyLegalLinks();
    if (CFG.supportUrl) {
      const support = document.getElementById('support-link');
      support.href = CFG.supportUrl;
      support.classList.remove('hidden');
    }

    if (tg) {
      try {
        tg.ready();
        tg.expand();
        const canSetColors = typeof tg.isVersionAtLeast === 'function' && tg.isVersionAtLeast('6.1');
        if (canSetColors) {
          tg.setHeaderColor('#05070a');
          tg.setBackgroundColor('#05070a');
        }
      } catch (e) { }
    }

    bindEmailLoginInput();
    bindEmailCodeInput();
    bindPromoInput();

    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      if (state.emailLoginCodeModalOpen) {
        closeEmailLoginCodeModal();
      } else if (state.promoModalOpen) {
        closePromoModal();
      } else if (state.referralModalOpen) {
        closeReferralModal();
      } else if (state.paymentFlowOpen) {
        closePaymentFlow();
      }
    });

    boot();

    async function boot() {
      showLoader();
      if (MOCK) {
        await loadData();
        return;
      }

      const widgetAuthData = readTelegramLoginWidgetAuthData();
      if (widgetAuthData) {
        const authenticated = await finalizeTelegramAuth(widgetAuthData);
        if (authenticated) {
          return;
        }
        clearToken();
        startExternalAuth({resetStatus: false});
        return;
      }

      if (tg && tg.initData) {
        try {
          const authenticated = await finalizeTelegramAuth(tg.initData, 'init_data');
          if (authenticated) {
            return;
          }
        } catch (e) { }
      }

      if (state.token) {
        try {
          await loadData();
          return;
        } catch (e) {
          clearToken();
        }
      }

      await startExternalAuth();
    }

    function readTelegramLoginWidgetAuthData() {
      const query = new URLSearchParams(window.location.search);
      const keys = ['id', 'first_name', 'last_name', 'username', 'photo_url', 'auth_date', 'hash'];
      const authData = {};
      let hasAuthValue = false;

      keys.forEach(key => {
        if (!query.has(key)) return;
        authData[key] = query.get(key) || '';
        hasAuthValue = true;
      });

      if (!hasAuthValue || !authData.id || !authData.auth_date || !authData.hash) {
        return null;
      }

      return authData;
    }

    function readReferralParam() {
      const query = new URLSearchParams(window.location.search);
      const fromQuery = query.get('ref') || query.get('start') || query.get('start_param') || '';
      const fromTelegram = tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param
        ? tg.initDataUnsafe.start_param
        : '';
      const value = String(fromTelegram || fromQuery || '').trim();
      if (value) {
        localStorage.setItem('rw_webapp_referral', value);
        return value;
      }
      return localStorage.getItem('rw_webapp_referral') || '';
    }

    function clearTelegramLoginWidgetQuery() {
      const url = new URL(window.location.href);
      const keys = ['id', 'first_name', 'last_name', 'username', 'photo_url', 'auth_date', 'hash'];
      keys.forEach(key => url.searchParams.delete(key));
      if (window.history && window.history.replaceState) {
        window.history.replaceState({}, document.title, url.pathname + url.search + url.hash);
      }
    }

    async function finalizeTelegramAuth(authData, source = 'auth_data') {
      if (state.authInProgress) return false;
      state.authInProgress = true;
      setAuthStatus(t('telegram_auth_verifying'));
      try {
        const payload = source === 'init_data'
          ? {init_data: authData}
          : {auth_data: authData};
        if (state.referralParam) payload.referral_code = state.referralParam;
        const response = await fetch(CFG.apiBase + '/auth/token', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (response.ok && data.ok && data.token) {
          setToken(data.token);
          clearTelegramLoginWidgetQuery();
          try {
            setAuthStatus('');
            await loadData();
            return true;
          } catch (e) {
            clearToken();
            setAuthStatus(t('telegram_auth_failed'), true);
            return false;
          }
        }

        const errorKey = data.error === 'banned' || data.error === 'access_denied'
          ? 'telegram_auth_access_denied'
          : 'telegram_auth_failed';
        setAuthStatus(t(errorKey), true);
      } catch (e) {
        setAuthStatus(t('telegram_auth_failed'), true);
      } finally {
        state.authInProgress = false;
      }

      clearTelegramLoginWidgetQuery();
      return false;
    }

    async function handleTelegramLoginWidgetAuth(user) {
      if (!user) {
        setAuthStatus(t('telegram_auth_failed'), true);
        return;
      }

      await finalizeTelegramAuth(user, 'auth_data');
    }

    function setAuthMode(mode) {
      state.authMode = mode === 'telegram' ? 'telegram' : 'email';
      renderAuthMode();
    }

    function renderAuthMode() {
      const emailTab = document.getElementById('email-auth-tab');
      const telegramTab = document.getElementById('telegram-auth-tab');
      const emailPane = document.getElementById('email-login-pane');
      const telegramPane = document.getElementById('telegram-login-pane');
      const emailEnabled = CFG.emailAuthEnabled !== false;
      if (!emailEnabled && state.authMode === 'email') {
        state.authMode = 'telegram';
      }

      emailTab.classList.toggle('active', state.authMode === 'email');
      telegramTab.classList.toggle('active', state.authMode === 'telegram');
      emailPane.classList.toggle('hidden', state.authMode !== 'email');
      telegramPane.classList.toggle('hidden', state.authMode !== 'telegram');

      emailTab.disabled = !emailEnabled;
      if (state.authMode === 'telegram') {
        renderTelegramLoginWidget();
      } else if (!emailEnabled) {
        setAuthStatus(t('email_auth_disabled'), true);
      }
    }

    function renderTelegramLoginWidget() {
      const container = document.getElementById('telegram-login-widget');
      if (!container) return;

      container.innerHTML = '';
      const botUsername = String(CFG.telegramLoginBotUsername || '').trim();
      if (!botUsername) {
        setAuthStatus(t('telegram_auth_unavailable'), true);
        return;
      }

      if (typeof window.onTelegramAuth !== 'function') {
        window.onTelegramAuth = async function(user) {
          await handleTelegramLoginWidgetAuth(user);
        };
      }

      const script = document.createElement('script');
      script.async = true;
      script.src = TELEGRAM_LOGIN_WIDGET_URL;
      script.setAttribute('data-telegram-login', botUsername);
      script.setAttribute('data-size', 'large');
      script.setAttribute('data-userpic', 'false');
      script.setAttribute('data-request-access', 'write');
      script.setAttribute('data-onauth', 'onTelegramAuth(user)');
      script.onerror = () => setAuthStatus(t('telegram_auth_unavailable'), true);
      container.appendChild(script);
    }

    function bindEmailLoginInput() {
      const input = document.getElementById('email-login-input');
      if (!input) return;

      input.addEventListener('keydown', event => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        requestEmailLoginCode();
      });
      input.addEventListener('input', () => {
        if (input.getAttribute('aria-invalid') !== 'true') return;
        input.removeAttribute('aria-invalid');
        setAuthStatus('');
      });
    }

    function bindEmailCodeInput() {
      const input = document.getElementById('email-login-code-input');
      if (!input) return;

      input.addEventListener('input', () => {
        input.value = sanitizeCode(input.value);
        updateEmailLoginCodeSlots();
      });
      input.addEventListener('focus', updateEmailLoginCodeSlots);
      input.addEventListener('blur', updateEmailLoginCodeSlots);
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') {
          event.preventDefault();
          if (sanitizeCode(input.value).length === 6 && !state.emailLoginVerifying) {
            verifyEmailLoginCode();
          }
        }
      });

      const field = input.closest('.otp-field');
      if (field) {
        field.addEventListener('click', () => input.focus());
      }
    }

    function sanitizeCode(value) {
      return String(value || '').replace(/\D/g, '').slice(0, 6);
    }

    function isValidEmail(value) {
      const email = normalizeEmail(value);
      return Boolean(email && email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email));
    }

    function readValidEmailLoginInput() {
      const input = document.getElementById('email-login-input');
      const email = normalizeEmail(input && input.value);
      if (!email || !isValidEmail(email)) {
        if (input) {
          input.setAttribute('aria-invalid', 'true');
          input.focus();
        }
        setAuthStatus(t(email ? 'email_invalid' : 'email_required'), true);
        return '';
      }

      if (input) {
        input.value = email;
        input.removeAttribute('aria-invalid');
      }
      return email;
    }

    function openEmailLoginCodeModal(email, message, isError = false) {
      state.emailLoginEmail = email;
      state.emailLoginCodeModalOpen = true;
      const input = document.getElementById('email-login-code-input');
      if (input) input.value = '';
      renderEmailLoginCodeModal();
      setEmailCodeStatus(message || t('email_code_sent'), isError);
      window.setTimeout(() => {
        const codeInput = document.getElementById('email-login-code-input');
        if (state.emailLoginCodeModalOpen && codeInput) codeInput.focus();
      }, 80);
    }

    function closeEmailLoginCodeModal() {
      state.emailLoginCodeModalOpen = false;
      const input = document.getElementById('email-login-code-input');
      if (input) input.value = '';
      setEmailCodeStatus('');
      renderEmailLoginCodeModal();
    }

    function renderEmailLoginCodeModal() {
      const modal = document.getElementById('email-code-modal');
      if (!modal) return;

      if (!state.emailLoginCodeModalOpen) {
        modal.classList.remove('show');
        syncModalLock();
        window.setTimeout(() => {
          if (!state.emailLoginCodeModalOpen) modal.classList.add('hidden');
        }, 180);
        return;
      }

      const address = document.getElementById('email-code-address');
      if (address) address.textContent = state.emailLoginEmail || '...';
      modal.classList.remove('hidden');
      syncModalLock();
      applyI18n(modal);
      updateEmailLoginCodeSlots();
      window.requestAnimationFrame(() => modal.classList.add('show'));
    }

    function updateEmailLoginCodeSlots() {
      const input = document.getElementById('email-login-code-input');
      const value = sanitizeCode(input && input.value);
      if (input && input.value !== value) input.value = value;

      for (let index = 0; index < 6; index += 1) {
        const slot = document.getElementById('email-code-slot-' + index);
        if (!slot) continue;
        const character = value[index] || '';
        slot.textContent = character;
        slot.classList.toggle('filled', Boolean(character));
        slot.classList.toggle(
          'active',
          state.emailLoginCodeModalOpen
            && document.activeElement === input
            && index === Math.min(value.length, 5)
        );
      }

      const verifyButton = document.getElementById('email-login-verify-btn');
      if (verifyButton) {
        verifyButton.disabled = value.length !== 6 || state.emailLoginVerifying || state.emailLoginPending;
      }

      const resendButton = document.getElementById('email-login-resend-btn');
      if (resendButton) {
        resendButton.disabled = state.emailLoginPending || state.emailLoginResending;
      }
    }

    async function requestEmailLoginCode() {
      if (state.emailLoginPending) return;
      if (CFG.emailAuthEnabled === false) {
        setAuthStatus(t('email_auth_disabled'), true);
        return;
      }
      const email = readValidEmailLoginInput();
      if (!email) {
        return;
      }
      state.emailLoginPending = true;
      setButtonBusy('email-login-send-btn', true);
      openEmailLoginCodeModal(email, t('email_code_sending'));
      setAuthStatus('');
      try {
        const data = await publicApi('/auth/email/request', {
          email,
          language: getLanguage()
        });
        if (!data.ok) throw data;
        setEmailCodeStatus(t('email_code_sent'));
      } catch (e) {
        const message = emailErrorMessage(e, 'email_code_send_failed');
        if (e && e.error === 'invalid_email') {
          closeEmailLoginCodeModal();
          const input = document.getElementById('email-login-input');
          if (input) input.setAttribute('aria-invalid', 'true');
          setAuthStatus(message, true);
        } else {
          setEmailCodeStatus(message, true);
        }
      } finally {
        state.emailLoginPending = false;
        setButtonBusy('email-login-send-btn', false);
        updateEmailLoginCodeSlots();
      }
    }

    async function resendEmailLoginCode() {
      if (state.emailLoginPending || state.emailLoginResending) return;
      const email = state.emailLoginEmail || normalizeEmail(document.getElementById('email-login-input').value);
      if (!email || !isValidEmail(email)) {
        setEmailCodeStatus(t(email ? 'email_invalid' : 'email_required'), true);
        return;
      }

      state.emailLoginResending = true;
      updateEmailLoginCodeSlots();
      setEmailCodeStatus(t('email_code_sending'));
      try {
        const data = await publicApi('/auth/email/request', {
          email,
          language: getLanguage()
        });
        if (!data.ok) throw data;
        state.emailLoginEmail = email;
        const input = document.getElementById('email-login-code-input');
        if (input) input.value = '';
        setEmailCodeStatus(t('email_code_sent'));
      } catch (e) {
        setEmailCodeStatus(emailErrorMessage(e, 'email_code_send_failed'), true);
      } finally {
        state.emailLoginResending = false;
        updateEmailLoginCodeSlots();
      }
    }

    async function verifyEmailLoginCode() {
      const email = state.emailLoginEmail || normalizeEmail(document.getElementById('email-login-input').value);
      const input = document.getElementById('email-login-code-input');
      const code = sanitizeCode(input && input.value);
      if (!email || code.length !== 6) {
        setEmailCodeStatus(t('email_code_invalid'), true);
        updateEmailLoginCodeSlots();
        return;
      }

      state.emailLoginVerifying = true;
      updateEmailLoginCodeSlots();
      setEmailCodeStatus(t('telegram_auth_verifying'));
      try {
        const data = await publicApi('/auth/email/verify', {
          email,
          code,
          referral_code: state.referralParam || ''
        });
        if (!data.ok || !data.token) throw data;
        setToken(data.token);
        closeEmailLoginCodeModal();
        await loadData();
      } catch (e) {
        clearToken();
        setEmailCodeStatus(emailErrorMessage(e, 'email_code_invalid'), true);
      } finally {
        state.emailLoginVerifying = false;
        updateEmailLoginCodeSlots();
      }
    }

    function startExternalAuth(options = {}) {
      const resetStatus = options.resetStatus !== false;
      showLogin();
      if (resetStatus) {
        setAuthStatus('');
      }
      renderAuthMode();
    }

    async function loadData() {
      const previousMonths = state.selectedPlan && state.selectedPlan.months;
      const data = await api('/me');
      if (!data.ok) throw new Error(data.error || 'load failed');
      state.data = data;
      setBrand();
      applyI18n();
      applyLegalLinks();
      const plans = data.plans || [];
      state.selectedPlan = plans.find(plan => plan.months === previousMonths) || plans[0] || null;
      state.selectedMethod = null;
      state.payment = null;
      state.paymentStep = 'plan';
      state.telegramLinkRendered = false;
      render();
      showApp();
    }

    async function reloadData() {
      showToast(t('updating'));
      await loadData();
    }

    function render() {
      renderSubscription(state.data.subscription);
      renderAccount(state.data.user || {});
      renderReferral(state.data.referral || {});
      renderPaymentFlow();
    }

    function renderSubscription(sub) {
      const badge = document.getElementById('status-badge');
      badge.textContent = sub.active ? t('active') : t('inactive');
      badge.classList.toggle('off', !sub.active);
      document.getElementById('remaining').textContent = sub.remaining_text || t('no_active_subscription');
      document.getElementById('end-date').textContent = sub.end_date_text || t('not_available');
      document.getElementById('traffic').textContent = (sub.traffic_used || t('not_available')) + ' / ' + (sub.traffic_limit || t('not_available'));
      document.getElementById('connect-actions').classList.toggle('hidden', !sub.connect_url && !sub.config_link);
    }

    function renderAccount(user) {
      const emailLinked = Boolean(user.email && user.email_verified);
      const telegramLinked = Boolean(user.telegram_linked);
      document.getElementById('account-email').textContent = emailLinked ? user.email : t('not_linked');
      document.getElementById('account-telegram').textContent = telegramLinked
        ? (user.telegram_id ? String(user.telegram_id) : t('linked'))
        : t('not_linked');

      const emailBox = document.getElementById('email-link-box');
      const telegramBox = document.getElementById('telegram-link-box');
      emailBox.classList.toggle('hidden', emailLinked || !state.data.settings.email_auth_enabled);
      telegramBox.classList.toggle('hidden', telegramLinked);

      if (!telegramLinked) {
        renderTelegramLinkWidget();
      } else {
        state.telegramLinkRendered = false;
      }
    }

    function openPromoModal() {
      state.promoModalOpen = true;
      clearPromoStatus();
      renderPromoModal();
      window.setTimeout(() => {
        const input = document.getElementById('promo-code-input');
        if (input) input.focus();
      }, 80);
    }

    function closePromoModal() {
      state.promoModalOpen = false;
      clearPromoStatus();
      renderPromoModal();
    }

    function renderPromoModal() {
      const panel = document.querySelector('.promo-panel');
      if (!panel) return;
      panel.classList.toggle('hidden', !state.promoModalOpen);
      panel.classList.toggle('modal-panel', state.promoModalOpen);
      renderToolsBackdrop();
      syncModalLock();
      renderPromoStatus();
      if (state.promoModalOpen && !panel.querySelector('[data-modal-close="promo"]')) {
        const head = panel.querySelector('.panel-head');
        if (head) {
          head.insertAdjacentHTML(
            'beforeend',
            '<button class="icon-btn" type="button" data-modal-close="promo" data-title-i18n="close" onclick="closePromoModal()">×</button>'
          );
          applyI18n(panel);
        }
      }
    }

    function bindPromoInput() {
      const input = document.getElementById('promo-code-input');
      if (!input) return;

      input.addEventListener('input', () => {
        if (input.getAttribute('aria-invalid') === 'true') {
          input.removeAttribute('aria-invalid');
        }
        if (state.promoStatusText) {
          clearPromoStatus();
        }
      });

      input.addEventListener('keydown', event => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        applyPromoCode();
      });
    }

    function setPromoStatus(message, type = 'error') {
      state.promoStatusType = type === 'success' ? 'success' : 'error';
      state.promoStatusText = normalizeStatusText(message || '');
      renderPromoStatus();
    }

    function clearPromoStatus() {
      state.promoStatusType = '';
      state.promoStatusText = '';
      renderPromoStatus();
    }

    function renderPromoStatus() {
      const status = document.getElementById('promo-status');
      if (!status) return;

      if (!state.promoStatusText) {
        status.textContent = '';
        status.classList.add('hidden');
        status.classList.remove('error', 'success');
        return;
      }

      status.textContent = state.promoStatusText;
      status.classList.remove('hidden');
      status.classList.toggle('error', state.promoStatusType === 'error');
      status.classList.toggle('success', state.promoStatusType === 'success');
    }

    function normalizeStatusText(value) {
      const text = String(value || '');
      const wrapper = document.createElement('div');
      wrapper.innerHTML = text;
      return (wrapper.textContent || wrapper.innerText || '').trim();
    }

    function openReferralModal() {
      state.referralModalOpen = true;
      renderReferral(state.data && state.data.referral || {});
    }

    function closeReferralModal() {
      state.referralModalOpen = false;
      renderReferral(state.data && state.data.referral || {});
    }

    function closeToolModals() {
      state.promoModalOpen = false;
      state.referralModalOpen = false;
      clearPromoStatus();
      renderPromoModal();
      renderReferral(state.data && state.data.referral || {});
    }

    function renderToolsBackdrop() {
      const backdrop = document.getElementById('tools-modal-backdrop');
      if (!backdrop) return;
      backdrop.classList.toggle('hidden', !(state.promoModalOpen || state.referralModalOpen));
    }

    function renderReferral(referral) {
      const panel = document.querySelector('.referral-panel');
      if (!panel) return;
      panel.classList.toggle('hidden', !state.referralModalOpen);
      panel.classList.toggle('modal-panel', state.referralModalOpen);
      renderToolsBackdrop();
      syncModalLock();
      if (!state.referralModalOpen) return;

      const bonusRows = (referral.bonus_details || []).map(item => `
        <div class="bonus-row">
          <span>${escapeHtml(item.title || '')}</span>
          <strong>${escapeHtml(t('referral_bonus_pair', {
            inviter: item.inviter_days || 0,
            friend: item.friend_days || 0
          }))}</strong>
        </div>
      `).join('');

      panel.innerHTML = `
        <div class="panel-head">
          <div>
            <div class="section-title">${escapeHtml(t('referral_title'))}</div>
            <div class="flow-caption">${escapeHtml(t('referral_caption'))}</div>
          </div>
          <button class="icon-btn" type="button" data-title-i18n="close" onclick="closeReferralModal()">×</button>
        </div>
        <div class="referral-link-list">
          ${renderReferralLinkRow('webapp', t('referral_site_label'), referral.webapp_link)}
          ${renderReferralLinkRow('bot', t('referral_telegram_label'), referral.bot_link)}
        </div>
        <div class="referral-bonus-card">
          <div class="section-label">${escapeHtml(t('referral_bonus_title'))}</div>
          <div class="bonus-list">${bonusRows || '<div class="empty">' + escapeHtml(t('referral_no_bonuses')) + '</div>'}</div>
        </div>
      `;
      applyI18n(panel);
    }

    function renderReferralLinkRow(kind, label, link) {
      return `
        <div class="referral-link-row">
          <div>
            <div class="metric-label">${escapeHtml(label)}</div>
            <div class="referral-link-value">${escapeHtml(link || t('not_available'))}</div>
          </div>
          <button class="btn icon-only copy-icon-btn" type="button" onclick="copyReferralLink('${escapeAttr(kind)}')" ${link ? '' : 'disabled'} data-title-i18n="copy_link">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" aria-hidden="true"><path d="M451.5 160C434.9 160 418.8 164.5 404.7 172.7C388.9 156.7 370.5 143.3 350.2 133.2C378.4 109.2 414.3 96 451.5 96C537.9 96 608 166 608 252.5C608 294 591.5 333.8 562.2 363.1L491.1 434.2C461.8 463.5 422 480 380.5 480C294.1 480 224 410 224 323.5C224 322 224 320.5 224.1 319C224.6 301.3 239.3 287.4 257 287.9C274.7 288.4 288.6 303.1 288.1 320.8C288.1 321.7 288.1 322.6 288.1 323.4C288.1 374.5 329.5 415.9 380.6 415.9C405.1 415.9 428.6 406.2 446 388.8L517.1 317.7C534.4 300.4 544.2 276.8 544.2 252.3C544.2 201.2 502.8 159.8 451.7 159.8zM307.2 237.3C305.3 236.5 303.4 235.4 301.7 234.2C289.1 227.7 274.7 224 259.6 224C235.1 224 211.6 233.7 194.2 251.1L123.1 322.2C105.8 339.5 96 363.1 96 387.6C96 438.7 137.4 480.1 188.5 480.1C205 480.1 221.1 475.7 235.2 467.5C251 483.5 269.4 496.9 289.8 507C261.6 530.9 225.8 544.2 188.5 544.2C102.1 544.2 32 474.2 32 387.7C32 346.2 48.5 306.4 77.8 277.1L148.9 206C178.2 176.7 218 160.2 259.5 160.2C346.1 160.2 416 230.8 416 317.1C416 318.4 416 319.7 416 321C415.6 338.7 400.9 352.6 383.2 352.2C365.5 351.8 351.6 337.1 352 319.4C352 318.6 352 317.9 352 317.1C352 283.4 334 253.8 307.2 237.5z"/></svg>
          </button>
        </div>
      `;
    }

    async function applyPromoCode() {
      if (state.promoApplying) return;
      const input = document.getElementById('promo-code-input');
      const code = String(input && input.value || '').trim();
      if (!code) {
        setPromoStatus(t('promo_empty'), 'error');
        if (input) input.setAttribute('aria-invalid', 'true');
        if (input) input.focus();
        return;
      }

      state.promoApplying = true;
      setButtonBusy('promo-apply-btn', true);
      clearPromoStatus();
      if (input) input.removeAttribute('aria-invalid');
      try {
        const data = await api('/promo/apply', {
          method: 'POST',
          body: JSON.stringify({code})
        });
        if (!data.ok) throw data;
        if (input) input.value = '';
        setPromoStatus(t('promo_applied_ok'), 'success');
        await loadData();
      } catch (e) {
        const errorCode = e && e.error;
        const serverMessage = e && (e.message || e.detail);
        if (input) input.setAttribute('aria-invalid', 'true');
        if (errorCode === 'empty_code') {
          setPromoStatus(t('promo_empty'), 'error');
        } else if (serverMessage) {
          setPromoStatus(serverMessage, 'error');
        } else if (errorCode === 'promo_apply_failed') {
          setPromoStatus(t('promo_invalid'), 'error');
        } else {
          setPromoStatus(t('payment_error'), 'error');
        }
      } finally {
        state.promoApplying = false;
        setButtonBusy('promo-apply-btn', false);
      }
    }

    async function copyReferralLink(kind) {
      const referral = state.data && state.data.referral;
      const link = referral && (kind === 'bot' ? referral.bot_link : referral.webapp_link);
      if (!link) {
        showToast(t('no_link'));
        return;
      }
      await copyText(link);
      showToast(t('referral_copied'));
    }

    async function requestEmailLinkCode() {
      const input = document.getElementById('email-link-input');
      const email = normalizeEmail(input.value);
      if (!email) {
        showToast(t('email_code_send_failed'));
        return;
      }
      state.emailLinkPending = true;
      setButtonBusy('email-link-send-btn', true);
      try {
        const data = await api('/account/email/request', {
          method: 'POST',
          body: JSON.stringify({email})
        });
        if (!data.ok) throw data;
        if (data.already_linked) {
          showToast(t('email_linked'));
          await loadData();
          return;
        }
        state.emailLinkEmail = email;
        document.getElementById('email-link-code-row').classList.remove('hidden');
        showToast(t('email_code_sent'));
      } catch (e) {
        showToast(emailErrorMessage(e, 'email_code_send_failed'));
      } finally {
        state.emailLinkPending = false;
        setButtonBusy('email-link-send-btn', false);
      }
    }

    async function verifyEmailLinkCode() {
      const email = state.emailLinkEmail || normalizeEmail(document.getElementById('email-link-input').value);
      const code = document.getElementById('email-link-code-input').value;
      setButtonBusy('email-link-verify-btn', true);
      try {
        const data = await api('/account/email/verify', {
          method: 'POST',
          body: JSON.stringify({email, code})
        });
        if (!data.ok) throw data;
        if (data.token) setToken(data.token);
        showToast(t('email_linked'));
        state.emailLinkEmail = '';
        await loadData();
      } catch (e) {
        showToast(emailErrorMessage(e, 'email_code_invalid'));
      } finally {
        setButtonBusy('email-link-verify-btn', false);
      }
    }

    function renderTelegramLinkWidget() {
      const container = document.getElementById('telegram-link-widget');
      if (!container || state.telegramLinkRendered) return;
      container.innerHTML = '';
      const botUsername = String(CFG.telegramLoginBotUsername || '').trim();
      if (!botUsername) {
        setTelegramLinkStatus(t('telegram_auth_unavailable'), true);
        return;
      }

      window.onTelegramLinkAuth = async function(user) {
        await linkTelegramAccount(user);
      };

      const script = document.createElement('script');
      script.async = true;
      script.src = TELEGRAM_LOGIN_WIDGET_URL;
      script.setAttribute('data-telegram-login', botUsername);
      script.setAttribute('data-size', 'large');
      script.setAttribute('data-userpic', 'false');
      script.setAttribute('data-request-access', 'write');
      script.setAttribute('data-onauth', 'onTelegramLinkAuth(user)');
      script.onerror = () => setTelegramLinkStatus(t('telegram_auth_unavailable'), true);
      container.appendChild(script);
      state.telegramLinkRendered = true;
    }

    async function linkTelegramAccount(user) {
      if (!user || state.telegramLinkInProgress) return;
      state.telegramLinkInProgress = true;
      setTelegramLinkStatus(t('telegram_auth_verifying'));
      try {
        const data = await api('/account/telegram/link', {
          method: 'POST',
          body: JSON.stringify({auth_data: user})
        });
        if (!data.ok) throw data;
        await finishTelegramLink(data, user.id);
      } catch (e) {
        if (await refreshLinkedTelegramAfterError()) {
          setTelegramLinkStatus('');
          try {
            showToast(t('telegram_linked'));
          } catch (toastError) {
            console.warn('Telegram link success toast failed', toastError);
          }
          return;
        }
        setTelegramLinkStatus(emailErrorMessage(e, 'telegram_auth_failed'), true);
      } finally {
        state.telegramLinkInProgress = false;
      }
    }

    async function finishTelegramLink(data, fallbackTelegramId) {
      if (data.token) setToken(data.token);
      markTelegramLinked(data.telegram_id || fallbackTelegramId);
      setTelegramLinkStatus('');
      state.telegramLinkRendered = false;
      try {
        showToast(t('telegram_linked'));
      } catch (toastError) {
        console.warn('Telegram link success toast failed', toastError);
      }
      try {
        await loadData();
      } catch (refreshError) {
        console.warn('Telegram account linked, but data refresh failed', refreshError);
      }
    }

    function markTelegramLinked(telegramId) {
      if (!state.data || !state.data.user) return;
      state.data.user.telegram_linked = true;
      if (telegramId) {
        state.data.user.telegram_id = Number(telegramId);
      }
      renderAccount(state.data.user);
    }

    async function refreshLinkedTelegramAfterError() {
      try {
        await loadData();
        return Boolean(state.data && state.data.user && state.data.user.telegram_linked);
      } catch (refreshError) {
        console.warn('Telegram link status refresh failed', refreshError);
        return false;
      }
    }

    function togglePaymentFlow() {
      if (state.paymentFlowOpen) {
        closePaymentFlow();
        return;
      }
      state.paymentFlowOpen = true;
      state.paymentStep = 'plan';
      state.payment = null;
      state.selectedMethod = null;
      renderPaymentFlow();
    }

    function closePaymentFlow() {
      state.paymentFlowOpen = false;
      state.paymentStep = 'plan';
      state.payment = null;
      state.selectedMethod = null;
      renderPaymentFlow();
    }

    function renderPaymentFlow() {
      const modal = document.getElementById('payment-modal');
      if (!state.paymentFlowOpen) {
        modal.classList.remove('show');
        syncModalLock();
        window.setTimeout(() => {
          if (!state.paymentFlowOpen) modal.classList.add('hidden');
        }, 180);
        return;
      }

      modal.classList.remove('hidden');
      syncModalLock();
      window.requestAnimationFrame(() => modal.classList.add('show'));
      applyI18n(modal);
      renderStepState();
      renderPlans(state.data.plans || []);
      renderMethods();
      renderPaymentResult();
    }

    function syncModalLock() {
      document.body.classList.toggle(
        'modal-open',
        Boolean(
          state.paymentFlowOpen
          || state.emailLoginCodeModalOpen
          || state.promoModalOpen
          || state.referralModalOpen
        )
      );
    }

    function renderStepState() {
      const order = ['plan', 'method', 'result'];
      order.forEach((step, index) => {
        const node = document.getElementById('step-' + step);
        const currentIndex = order.indexOf(state.paymentStep);
        node.classList.toggle('active', state.paymentStep === step);
        node.classList.toggle('done', currentIndex > index);
      });

      document.getElementById('plan-step').classList.toggle('hidden', state.paymentStep !== 'plan');
      document.getElementById('method-step').classList.toggle('hidden', state.paymentStep !== 'method');
      document.getElementById('result-step').classList.toggle('hidden', state.paymentStep !== 'result');
    }

    function renderPlans(plans) {
      const wrap = document.getElementById('plans');
      const nextBtn = document.getElementById('to-methods-btn');
      if (!plans.length) {
        wrap.innerHTML = '<div class="empty">' + escapeHtml(t('no_plans')) + '</div>';
        nextBtn.disabled = true;
        return;
      }

      nextBtn.disabled = !state.selectedPlan;
      wrap.innerHTML = plans.map(plan => {
        const isActive = state.selectedPlan && state.selectedPlan.months === plan.months;
        const stars = plan.stars_price ? ' / ' + plan.stars_price + ' Stars' : '';
        return `
          <button class="plan ${isActive ? 'active' : ''}" type="button" onclick="selectPlan(${plan.months})">
            <span>
              <span class="plan-name">${escapeHtml(plan.title)}</span>
              <span class="plan-meta">${escapeHtml(t('access_period'))}</span>
            </span>
            <span class="plan-price">${escapeHtml(formatMoney(plan.price, plan.currency) + stars)}</span>
          </button>
        `;
      }).join('');
    }

    function renderMethods() {
      const methods = document.getElementById('methods');
      const createBtn = document.getElementById('create-payment-btn');
      if (!state.selectedPlan) {
        methods.innerHTML = '<div class="empty">' + escapeHtml(t('choose_plan_first')) + '</div>';
        createBtn.disabled = true;
        return;
      }

      const available = getAvailableMethods();
      if (state.selectedMethod && !available.some(method => method.id === state.selectedMethod)) {
        state.selectedMethod = null;
      }

      createBtn.disabled = !state.selectedMethod || state.creatingPayment;
      if (!available.length) {
        methods.innerHTML = '<div class="empty">' + escapeHtml(t('no_methods')) + '</div>';
        createBtn.disabled = true;
        return;
      }

      methods.innerHTML = available.map(method => {
        const isActive = state.selectedMethod === method.id;
        const amount = method.id === 'stars'
          ? state.selectedPlan.stars_price + ' Stars'
          : formatMoney(state.selectedPlan.price, state.selectedPlan.currency);
        return `
          <button class="method ${isActive ? 'active' : ''}" type="button" onclick="selectMethod('${escapeAttr(method.id)}')">
            <span>
              <span class="method-name">${escapeHtml(method.name)}</span>
              <span class="method-meta">${escapeHtml(state.selectedPlan.title)}</span>
            </span>
            <span class="plan-price">${escapeHtml(amount)}</span>
          </button>
        `;
      }).join('');
    }

    function renderPaymentResult() {
      const payment = state.payment;
      const msg = document.getElementById('payment-message');
      const openBtn = document.getElementById('payment-open-btn');
      const checkBtn = document.getElementById('payment-check-btn');
      if (!payment) {
        msg.textContent = t('payment_not_created');
        openBtn.classList.add('hidden');
        checkBtn.classList.add('hidden');
        return;
      }

      if (payment.action === 'invoice_sent') {
        msg.textContent = t('invoice_sent');
        openBtn.classList.add('hidden');
      } else {
        msg.textContent = t('payment_created');
        openBtn.classList.toggle('hidden', !payment.payment_url);
      }
      checkBtn.classList.toggle('hidden', !payment.payment_id);
    }

    function selectPlan(months) {
      state.selectedPlan = (state.data.plans || []).find(plan => plan.months === months) || null;
      state.selectedMethod = null;
      state.payment = null;
      renderPaymentFlow();
    }

    function selectMethod(method) {
      state.selectedMethod = method;
      state.payment = null;
      renderMethods();
      renderPaymentResult();
    }

    function goToPaymentStep(step) {
      if (step === 'method' && !state.selectedPlan) {
        showToast(t('choose_plan_toast'));
        return;
      }
      if (step === 'result' && !state.payment) {
        showToast(t('create_payment_toast'));
        return;
      }
      state.paymentStep = step;
      renderPaymentFlow();
    }

    async function createPaymentFromSelection() {
      if (!state.selectedPlan) {
        showToast(t('choose_plan_toast'));
        return;
      }
      if (!state.selectedMethod) {
        showToast(t('choose_method_toast'));
        return;
      }

      state.creatingPayment = true;
      renderMethods();
      try {
        const data = await api('/payments', {
          method: 'POST',
          body: JSON.stringify({months: state.selectedPlan.months, method: state.selectedMethod})
        });
        if (!data.ok) throw new Error(data.message || t('payment_error'));
        state.payment = data;
        state.paymentStep = 'result';
        renderPaymentFlow();
      } catch (e) {
        showToast(e.message || t('payment_error'));
      } finally {
        state.creatingPayment = false;
        renderPaymentFlow();
      }
    }

    function getAvailableMethods() {
      if (!state.data || !state.selectedPlan) return [];
      return (state.data.payment_methods || []).filter(method => {
        if (method.id === 'stars') return Number(state.selectedPlan.stars_price || 0) > 0;
        return true;
      });
    }

    function openPaymentUrl() {
      const payment = state.payment;
      if (!payment || !payment.payment_url) return;
      if (payment.action === 'open_invoice' && tg && tg.openInvoice) {
        tg.openInvoice(payment.payment_url, function(status) {
          if (status === 'paid') loadData();
        });
        return;
      }
      if (tg && tg.openLink) {
        tg.openLink(payment.payment_url);
      } else {
        window.open(payment.payment_url, '_blank', 'noopener');
      }
    }

    async function checkPayment() {
      if (!state.payment || !state.payment.payment_id) return;
      const data = await api('/payments/' + state.payment.payment_id);
      if (data.paid) {
        showToast(t('payment_confirmed'));
        state.paymentFlowOpen = false;
        await loadData();
      } else {
        showToast(t('payment_pending'));
      }
    }

    function openConnectLink() {
      const sub = state.data && state.data.subscription;
      const url = sub && (sub.connect_url || sub.config_link);
      if (!url) {
        showToast(t('no_link'));
        return;
      }
      if (tg && tg.openLink) tg.openLink(url);
      else window.open(url, '_blank', 'noopener');
    }

    async function copyConfigLink() {
      const sub = state.data && state.data.subscription;
      const link = sub && sub.config_link;
      if (!link) {
        showToast(t('no_link'));
        return;
      }
      await copyText(link);
      showToast(t('link_copied'));
    }

    async function copyText(value) {
      try {
        await navigator.clipboard.writeText(value);
      } catch (e) {
        const area = document.createElement('textarea');
        area.value = value;
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        area.remove();
      }
    }

    async function api(path, options = {}) {
      if (MOCK) {
        return mockApi(path, options);
      }

      const headers = Object.assign({'Authorization': 'Bearer ' + state.token}, options.headers || {});
      if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
      const response = await fetch(CFG.apiBase + path, Object.assign({}, options, {headers}));
      if (response.status === 401) {
        clearToken();
        await startExternalAuth();
        throw new Error('Unauthorized');
      }
      return response.json();
    }

    async function publicApi(path, payload = {}) {
      if (MOCK) {
        return mockApi(path, {
          method: 'POST',
          body: JSON.stringify(payload)
        });
      }
      const response = await fetch(CFG.apiBase + path, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      return response.json();
    }

    async function mockApi(path, options = {}) {
      await new Promise(resolve => window.setTimeout(resolve, 120));
      if (path === '/me') {
        return JSON.parse(JSON.stringify(MOCK.data));
      }
      if (path === '/auth/email/request' || path === '/account/email/request') {
        return {ok: true};
      }
      if (path === '/auth/email/verify') {
        return {ok: true, token: 'local-preview'};
      }
      if (path === '/account/email/verify') {
        MOCK.data.user.email = 'preview@example.com';
        MOCK.data.user.email_verified = true;
        return {ok: true, token: 'local-preview'};
      }
      if (path === '/account/telegram/link') {
        MOCK.data.user.telegram_linked = true;
        MOCK.data.user.telegram_id = 100200300;
        return {ok: true, token: 'local-preview'};
      }
      if (path === '/promo/apply') {
        return {ok: true, end_date_text: '20.05.2026 12:00'};
      }
      if (path === '/payments' && String(options.method || '').toUpperCase() === 'POST') {
        return {
          ok: true,
          action: 'open_link',
          payment_url: 'https://example.com/payment-preview',
          payment_id: 10001
        };
      }
      if (path.startsWith('/payments/')) {
        return {
          ok: true,
          payment_id: 10001,
          status: 'pending',
          paid: false
        };
      }
      return {ok: false, error: 'not_found'};
    }

    function setToken(token) {
      state.token = token;
      localStorage.setItem('rw_webapp_token', token);
    }

    function clearToken() {
      state.token = '';
      localStorage.removeItem('rw_webapp_token');
    }

    function normalizeEmail(value) {
      return String(value || '').trim().toLowerCase();
    }

    function emailErrorMessage(error, fallbackKey) {
      const code = error && error.error;
      if (code === 'rate_limited') {
        return t('email_rate_limited', {seconds: error.retry_after || 60});
      }
      if (code === 'invalid_email') return t('email_invalid');
      if (code === 'expired_code') return t('email_code_expired');
      if (code === 'invalid_code' || code === 'too_many_attempts') return t('email_code_invalid');
      if (code === 'email_auth_not_configured') return t('email_auth_disabled');
      if (code === 'account_merge_conflict') return t('account_merge_conflict');
      if (code === 'invalid_auth') return t('telegram_auth_failed');
      return t(fallbackKey);
    }

    function setButtonBusy(id, busy) {
      const button = document.getElementById(id);
      if (button) button.disabled = Boolean(busy);
    }

    function logout() {
      clearToken();
      closePaymentFlow();
      closeEmailLoginCodeModal();
      startExternalAuth();
    }

    function showLoader() {
      document.getElementById('loader').classList.remove('hidden');
      document.getElementById('app').classList.add('hidden');
      document.getElementById('login').classList.remove('show');
    }

    function showApp() {
      document.getElementById('loader').classList.add('hidden');
      document.getElementById('login').classList.remove('show');
      document.getElementById('app').classList.remove('hidden');
    }

    function showLogin() {
      document.getElementById('loader').classList.add('hidden');
      document.getElementById('app').classList.add('hidden');
      document.getElementById('login').classList.add('show');
    }

    function setAuthStatus(message, isError = false) {
      const status = document.getElementById('auth-status');
      if (!status) return;
      if (!message) {
        status.textContent = '';
        status.classList.add('hidden');
        status.classList.remove('error');
        return;
      }

      status.textContent = message;
      status.classList.remove('hidden');
      status.classList.toggle('error', Boolean(isError));
    }

    function setEmailCodeStatus(message, isError = false) {
      const status = document.getElementById('email-code-status');
      if (!status) return;
      if (!message) {
        status.textContent = '';
        status.classList.add('hidden');
        status.classList.remove('error');
        return;
      }

      status.textContent = message;
      status.classList.remove('hidden');
      status.classList.toggle('error', Boolean(isError));
    }

    function setTelegramLinkStatus(message, isError = false) {
      const status = document.getElementById('telegram-link-status');
      if (!status) return;
      if (!message) {
        status.textContent = '';
        status.classList.add('hidden');
        status.classList.remove('error');
        return;
      }
      status.textContent = message;
      status.classList.remove('hidden');
      status.classList.toggle('error', Boolean(isError));
    }

    function showToast(message) {
      if (tg && tg.showAlert) {
        tg.showAlert(message);
        return;
      }
      const toast = document.getElementById('toast');
      toast.textContent = message;
      toast.classList.remove('hidden');
      window.requestAnimationFrame(() => toast.classList.add('show'));
      if (state.toastTimer) window.clearTimeout(state.toastTimer);
      state.toastTimer = window.setTimeout(() => {
        toast.classList.remove('show');
        window.setTimeout(() => toast.classList.add('hidden'), 180);
      }, 1800);
    }

    function setBrand() {
      const title = CFG.title || t('page_title');
      const logoUrl = CFG.logoUrl || '';
      document.title = title;
      document.querySelectorAll('[data-brand-title]').forEach(node => {
        node.textContent = title;
      });
      document.querySelectorAll('[data-brand-logo]').forEach(logo => {
        if (!logoUrl) {
          logo.removeAttribute('src');
          logo.classList.add('hidden');
          return;
        }

        logo.onload = () => {
          logo.classList.remove('hidden');
        };
        logo.onerror = () => {
          logo.removeAttribute('src');
          logo.classList.add('hidden');
        };
        logo.src = logoUrl;
        if (logo.complete && logo.naturalWidth > 0) {
          logo.classList.remove('hidden');
        } else {
          logo.classList.add('hidden');
        }
      });
    }

    function applyI18n(root = document) {
      document.documentElement.lang = getLanguage();
      root.querySelectorAll('[data-i18n]').forEach(node => {
        node.textContent = t(node.dataset.i18n);
      });
      root.querySelectorAll('[data-title-i18n]').forEach(node => {
        const value = t(node.dataset.titleI18n);
        node.setAttribute('title', value);
        node.setAttribute('aria-label', value);
      });
      root.querySelectorAll('[data-aria-i18n]').forEach(node => {
        node.setAttribute('aria-label', t(node.dataset.ariaI18n));
      });
      root.querySelectorAll('[data-placeholder-i18n]').forEach(node => {
        node.setAttribute('placeholder', t(node.dataset.placeholderI18n));
      });
    }

    function applyLegalLinks(root = document) {
      const urls = {
        privacyPolicyUrl: CFG.privacyPolicyUrl || '',
        userAgreementUrl: CFG.userAgreementUrl || ''
      };

      root.querySelectorAll('[data-legal-key]').forEach(node => {
        const key = node.dataset.legalKey;
        const url = urls[key] || '';
        node.href = url || '#';
        node.classList.toggle('hidden', !url);
        node.setAttribute('aria-hidden', url ? 'false' : 'true');
      });

      root.querySelectorAll('.legal-links').forEach(container => {
        const visible = Array.from(container.querySelectorAll('[data-legal-key]'))
          .some(node => !node.classList.contains('hidden'));
        container.classList.toggle('hidden', !visible);
      });
    }

    function getLanguage() {
      const raw = (
        state.data && state.data.user && state.data.user.language_code
          ? state.data.user.language_code
          : (CFG.language || document.documentElement.lang || 'ru')
      ).toLowerCase();
      const short = raw.split('-')[0];
      return I18N[short] ? short : 'ru';
    }

    function t(key, params = {}) {
      const table = I18N[getLanguage()] || I18N.ru;
      const fallback = I18N.ru[key] || key;
      const template = table[key] || fallback;
      return template.replace(/\{(\w+)\}/g, (_, name) => (
        Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : ''
      ));
    }

    function formatMoney(value, currency) {
      const numeric = Number(value || 0);
      const formatted = Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2);
      return formatted + ' ' + (currency || CFG.currency || 'RUB');
    }

    function escapeHtml(value) {
      return String(value == null ? '' : value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }

    function escapeAttr(value) {
      return escapeHtml(value).replaceAll('`', '&#096;');
    }
