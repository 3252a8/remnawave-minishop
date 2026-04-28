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
          traffic_used_bytes: 19778468741,
          traffic_limit_bytes: 536870912000,
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
          {id: 'platega_sbp', name: 'Platega · СБП'},
          {id: 'platega_crypto', name: 'Platega · Crypto'},
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
    function readJsonScript(id) {
      const node = document.getElementById(id);
      if (!node || !node.textContent) return null;
      try {
        return JSON.parse(node.textContent);
      } catch (error) {
        console.warn('Failed to parse JSON config from #' + id, error);
        return null;
      }
    }

    const CFG = readJsonScript('webapp-config') || (MOCK && MOCK.config) || {};
    const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
    const TELEGRAM_LOGIN_WIDGET_URL = './telegram-widget.js';
    const MANUAL_LOGOUT_FLAG_KEY = 'rw_webapp_manual_logout';
    const state = {
      token: MOCK ? 'local-preview' : (localStorage.getItem('rw_webapp_token') || ''),
      csrfToken: MOCK ? '' : (readCookie('rw_webapp_csrf') || ''),
      data: null,
      selectedPlan: null,
      referralParam: readReferralParam(),
      promoApplying: false,
      payment: null,
      paymentFlowOpen: false,
      promoModalOpen: false,
      referralModalOpen: false,
      accountMergeModalOpen: false,
      accountMergeNotice: null,
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
      toastTimer: null,
      userMenuOpen: false,
      userMenuCloseTimer: null,
      langOverride: (function() {
        try { return localStorage.getItem('rw_webapp_lang') || ''; } catch (e) { return ''; }
      })(),
      langMenuOpen: false,
      langMenuCloseTimer: null
    };

    const LANG_OPTIONS = [
      { code: 'ru', label: 'Русский', short: 'RU', flag: '🇷🇺' },
      { code: 'en', label: 'English', short: 'EN', flag: '🇬🇧' }
    ];

    const TW = {
      iconBtn: 'icon-btn',
      btnBase: 'btn',
      btnIconOnly: 'w-12 min-w-12 p-0',
      panelHead: 'panel-head',
      flowCaption: 'section-caption',
      sectionTitle: 'section-title',
      metricLabel: 'metric-label',
      metricValue: 'metric-value',
      referralLinkRow: 'referral-link-row',
      referralLinkValue: 'referral-link-value',
      bonusRow: 'bonus-row',
      empty: 'empty-state',
      planCard: 'plan-card',
      planCardActive: 'plan-card-active',
      planName: 'plan-name',
      planMeta: 'plan-meta',
      planPrice: 'plan-price',
      paymentMethodCard: 'payment-method-card',
      paymentMethodCardPlatega: 'payment-method-card--platega',
      paymentMethodCardPlategaSbp: 'payment-method-card--platega payment-method-card--platega-sbp',
      paymentMethodCardPlategaCrypto: 'payment-method-card--platega payment-method-card--platega-crypto',
      paymentMethodCardCryptopay: 'payment-method-card--cryptopay',
      notice: 'notice',
      stepNum: 'step-num',
      stepName: 'step-name'
    };

    const FALLBACK_I18N = {
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
        payment_caption: 'Выберите период и нажмите способ оплаты. Сервис оплаты откроется сразу.',
        close: 'Закрыть',
        close_payment: 'Закрыть оплату',
        payment_steps: 'Шаги оплаты',
        step_plan: 'Срок',
        step_method: 'Метод',
        step_result: 'Платеж',
        select_period: 'Выберите период',
        select_method: 'Выберите способ оплаты',
        payment_status: 'Статус платежа',
        payment_amount_label: 'Стоимость выбранного периода',
        choose_payment_method: 'Способ оплаты',
        back: 'Назад',
        create_payment: 'Создать платеж',
        open_payment: 'Открыть оплату',
        check_payment: 'Проверить оплату',
        choose_other_method: 'Выбрать другой способ',
        pay_with_platega_button: 'Оплатить картой (СБП)',
        pay_with_platega_sbp_button: 'Оплата через СБП',
        pay_with_platega_crypto_button: 'Оплата криптой',
        pay_with_cryptopay_button: 'Оплатить криптой',
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
        login_title: 'Войдите или зарегистрируйтесь',
        login_continue: 'Продолжить',
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
        account_merge_toast: 'Аккаунты объединены',
        account_merge_title: 'Аккаунты объединены',
        account_merge_caption: 'Оплаченные периоды сложились, и теперь у вас один аккаунт.',
        account_merge_body: 'Мы объединили ваш Telegram и email в один профиль. Оплаченные периоды сложились, ссылка на подписку осталась прежней, а более поздний аккаунт был удалён автоматически.',
        account_merge_primary_account_label: 'Оставлен аккаунт',
        account_merge_removed_account_label: 'Удалён аккаунт',
        account_merge_end_date_label: 'Новая дата окончания',
        account_merge_conflict: 'Этот аккаунт уже связан с другими данными.',
        telegram_auth: 'Telegram auth',
        telegram_auth_verifying: 'Проверяю вход...',
        telegram_auth_failed: 'Не удалось подтвердить Telegram-вход. Попробуйте еще раз.',
        telegram_auth_unavailable: 'Telegram Login Widget недоступен. Проверьте username бота и доступ к telegram.org.',
        telegram_auth_access_denied: 'Доступ запрещен.',
        active: 'Активна',
        inactive: 'Не активна',
        subscription_active: 'Подписка активна',
        subscription_inactive: 'Подписка не активна',
        sub_remaining_template: 'Действует еще {value}',
        sub_ends_template: 'Закончится {date}',
        sub_ended_template: 'Закончилась {date}',
        sub_no_expiry: 'Бессрочно',
        traffic_unlimited: '∞ бесконечный трафик',
        traffic_unavailable: 'Сервис недоступен',
        link_panel_title: 'Привяжите способ входа',
        link_panel_caption: 'Чтобы не потерять доступ к кабинету',
        link_email_title: 'Привяжите email',
        link_email_caption: 'Получайте код для входа на почту',
        link_telegram_title: 'Привяжите Telegram',
        link_telegram_caption: 'Входите одним нажатием через Telegram',
        guest_user: 'Гость',
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
        referral_caption: 'Поделитесь ссылкой и получайте бонусы.',
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
        referral_no_bonuses: 'Бонусы пока не настроены.',
        referral_bonus_explanation: 'Бонусы начисляются один раз за каждого приглашенного пользователя, когда приглашенный пользователь покупает подписку.'
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
        payment_caption: 'Choose a period and tap a payment method. The payment service will open right away.',
        close: 'Close',
        close_payment: 'Close payment',
        payment_steps: 'Payment steps',
        step_plan: 'Period',
        step_method: 'Method',
        step_result: 'Payment',
        select_period: 'Select period',
        select_method: 'Select payment method',
        payment_status: 'Payment status',
        payment_amount_label: 'Selected period cost',
        choose_payment_method: 'Payment method',
        back: 'Back',
        create_payment: 'Create payment',
        open_payment: 'Open payment',
        check_payment: 'Check payment',
        choose_other_method: 'Choose another method',
        pay_with_platega_button: 'Pay by card (SBP)',
        pay_with_platega_sbp_button: 'Pay via SBP',
        pay_with_platega_crypto_button: 'Pay with crypto',
        pay_with_cryptopay_button: 'Pay with crypto',
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
        login_title: 'Log in or sign up',
        login_continue: 'Continue',
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
        account_merge_toast: 'Accounts merged',
        account_merge_title: 'Accounts merged',
        account_merge_caption: 'Your paid periods were combined and you now have one account.',
        account_merge_body: 'We merged your Telegram and email accounts into one profile. Your paid periods were combined, your subscription link stayed the same, and the later account was removed automatically.',
        account_merge_primary_account_label: 'Kept account',
        account_merge_removed_account_label: 'Removed account',
        account_merge_end_date_label: 'New end date',
        account_merge_conflict: 'This account is already linked to different data.',
        telegram_auth: 'Telegram auth',
        telegram_auth_verifying: 'Verifying login...',
        telegram_auth_failed: 'Could not verify Telegram login. Try again.',
        telegram_auth_unavailable: 'Telegram Login Widget is unavailable. Check the bot username and access to telegram.org.',
        telegram_auth_access_denied: 'Access denied.',
        active: 'Active',
        inactive: 'Inactive',
        subscription_active: 'Subscription is active',
        subscription_inactive: 'Subscription is inactive',
        sub_remaining_template: 'Valid for {value} more',
        sub_ends_template: 'Expires {date}',
        sub_ended_template: 'Expired {date}',
        sub_no_expiry: 'No expiration',
        traffic_unlimited: '∞ unlimited traffic',
        traffic_unavailable: 'Service unavailable',
        link_panel_title: 'Link a sign-in method',
        link_panel_caption: 'So you never lose access',
        link_email_title: 'Link email',
        link_email_caption: 'Receive sign-in codes by email',
        link_telegram_title: 'Link Telegram',
        link_telegram_caption: 'Sign in with one tap via Telegram',
        guest_user: 'Guest',
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
        referral_caption: 'Share your link and receive bonuses.',
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
        referral_no_bonuses: 'Bonuses are not configured yet.',
        referral_bonus_explanation: 'Bonuses are awarded once for each invited user when they purchase a subscription.'
      }
    };
    const I18N = (function () {
      const server = readJsonScript('i18n') || (MOCK && MOCK.i18n) || {};
      const merged = {};
      const langs = new Set(Object.keys(FALLBACK_I18N).concat(Object.keys(server)));
      langs.forEach(function (lang) {
        merged[lang] = Object.assign({}, FALLBACK_I18N[lang] || {}, server[lang] || {});
      });
      return merged;
    })();

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
      handleDocumentKeyForUserMenu(event);
      if (event.key !== 'Escape') return;
      if (state.emailLoginCodeModalOpen) {
        closeEmailLoginCodeModal();
      } else if (state.accountMergeModalOpen) {
        closeAccountMergeModal();
      } else if (state.promoModalOpen) {
        closePromoModal();
      } else if (state.referralModalOpen) {
        closeReferralModal();
      } else if (state.paymentFlowOpen) {
        closePaymentFlow();
      }
    });

    document.addEventListener('click', handleDocumentActionClick);
    document.addEventListener('click', handleDocumentClickForUserMenu);
    document.addEventListener('click', handleDocumentClickForLangMenu);
    renderLangMenu();

    boot();

    async function boot() {
      showLoader();
      if (MOCK) {
        await loadData();
        return;
      }

      const magicToken = readMagicLoginToken();
      if (magicToken) {
        const authenticated = await finalizeMagicLogin(magicToken);
        if (authenticated) {
          return;
        }
      }

      // Explicit logout should survive refresh, even if the old cookie session is still valid.
      if (isManuallyLoggedOut()) {
        await startExternalAuth();
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

      if (state.token || readCookie('rw_webapp_csrf')) {
        try {
          await loadData();
          return;
        } catch (e) {
          clearToken();
        }
      }

      await startExternalAuth();
    }

    function readMagicLoginToken() {
      const query = new URLSearchParams(window.location.search);
      const token = (query.get('login_token') || '').trim();
      return token || null;
    }

    function clearMagicLoginQuery() {
      const url = new URL(window.location.href);
      ['login_token', 'login_purpose'].forEach(key => url.searchParams.delete(key));
      if (window.history && window.history.replaceState) {
        window.history.replaceState({}, document.title, url.pathname + url.search + url.hash);
      }
    }

    async function finalizeMagicLogin(token) {
      if (state.authInProgress) return false;
      state.authInProgress = true;
      setAuthStatus(t('telegram_auth_verifying'));
      try {
        const payload = {token};
        if (state.referralParam) payload.referral_code = state.referralParam;
        const data = await publicApi('/auth/email/magic', payload);
        if (data && data.ok && data.token) {
          setToken(data.token, data.csrf_token);
          clearManualLogoutFlag();
          clearMagicLoginQuery();
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
        clearMagicLoginQuery();
        setAuthStatus(emailErrorMessage(data, 'email_code_invalid'), true);
        return false;
      } catch (e) {
        clearMagicLoginQuery();
        setAuthStatus(t('telegram_auth_failed'), true);
        return false;
      } finally {
        state.authInProgress = false;
      }
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
          setToken(data.token, data.csrf_token);
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
      const authBody = document.querySelector('.login-auth-body');
      const emailEnabled = CFG.emailAuthEnabled !== false;
      if (!emailEnabled && state.authMode === 'email') {
        state.authMode = 'telegram';
      }

      emailTab.classList.toggle('active', state.authMode === 'email');
      telegramTab.classList.toggle('active', state.authMode === 'telegram');
      emailPane.classList.toggle('hidden', state.authMode !== 'email');
      telegramPane.classList.toggle('hidden', state.authMode !== 'telegram');
      if (authBody) {
        authBody.classList.toggle('login-auth-body--telegram', state.authMode === 'telegram');
      }

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
      script.setAttribute('data-userpic', 'true');
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
        setToken(data.token, data.csrf_token);
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
      const data = await api('/me');
      if (!data.ok) throw new Error(data.error || 'load failed');
      state.data = data;
      setBrand();
      applyI18n();
      applyLegalLinks();
      const plans = data.plans || [];
      state.selectedPlan = getDefaultPaymentPlan(plans);
      state.payment = null;
      state.creatingPayment = false;
      state.telegramLinkRendered = false;
      render();
      showApp();
    }

    function render() {
      renderSubscription(state.data.subscription);
      renderUserMenu(state.data.user || {});
      renderAccount(state.data.user || {});
      renderReferral(state.data.referral || {});
      renderAccountMergeModal();
      renderPaymentFlow();
    }

    function renderSubscription(sub) {
      const wrap = document.getElementById('sub-status');
      const text = document.getElementById('sub-status-text');
      const remaining = document.getElementById('remaining');
      const endCaption = document.getElementById('end-date-caption');

      wrap.classList.toggle('active', Boolean(sub.active));
      text.textContent = sub.active ? t('subscription_active') : t('subscription_inactive');

      if (sub.active) {
        const compact = formatCompactRemaining(sub.days_left, getLanguage()) || sub.remaining_text || '';
        remaining.textContent = compact;
      } else {
        remaining.textContent = t('no_active_subscription');
      }

      if (sub.end_date_text) {
        const template = sub.active ? 'sub_ends_template' : 'sub_ended_template';
        endCaption.textContent = t(template, {date: sub.end_date_text});
        endCaption.classList.remove('hidden');
      } else if (sub.active) {
        endCaption.textContent = t('sub_no_expiry');
        endCaption.classList.remove('hidden');
      } else {
        endCaption.textContent = '';
        endCaption.classList.add('hidden');
      }

      renderTraffic(sub);
      document.getElementById('connect-actions').classList.toggle('hidden', !sub.connect_url && !sub.config_link);
    }

    function renderTraffic(sub) {
      const bar = document.getElementById('traffic-bar');
      const fill = document.getElementById('traffic-bar-fill');
      const value = document.getElementById('traffic');
      if (!bar || !fill || !value) return;

      const limitBytes = Number(sub.traffic_limit_bytes);
      const usedBytes = Number(sub.traffic_used_bytes);
      const hasLimit = Number.isFinite(limitBytes) && limitBytes > 0;
      const hasUsed = Number.isFinite(usedBytes) && usedBytes >= 0;
      const usedText = sub.traffic_used || t('not_available');
      const limitText = sub.traffic_limit || t('not_available');

      bar.classList.remove('over', 'unlimited', 'inactive');

      if (!sub.active) {
        bar.classList.add('inactive');
        fill.style.width = '100%';
        value.textContent = t('traffic_unavailable');
        bar.setAttribute('aria-valuenow', '0');
        return;
      }

      if (!hasLimit) {
        bar.classList.add('unlimited');
        fill.style.width = '100%';
        value.textContent = t('traffic_unlimited');
        bar.setAttribute('aria-valuenow', '0');
        return;
      }

      const ratio = hasUsed ? usedBytes / limitBytes : 0;
      const pct = Math.max(0, Math.min(100, Math.round(ratio * 100)));
      fill.style.width = pct + '%';
      value.textContent = usedText + ' / ' + limitText;
      bar.setAttribute('aria-valuenow', String(pct));
      if (hasUsed && usedBytes >= limitBytes) {
        bar.classList.add('over');
      }
    }

    function formatCompactRemaining(daysRaw, lang) {
      const days = Math.max(0, Math.floor(Number(daysRaw) || 0));
      if (days <= 0) return null;
      if (days >= 365) {
        const years = Math.round((days / 365) * 2) / 2;
        return formatDecimal(years, lang) + ' ' + pluralizeUnit(years, 'year', lang);
      }
      if (days >= 30) {
        const months = Math.round((days / 30) * 2) / 2;
        return formatDecimal(months, lang) + ' ' + pluralizeUnit(months, 'month', lang);
      }
      return formatDecimal(days, lang) + ' ' + pluralizeUnit(days, 'day', lang);
    }

    function formatDecimal(value, lang) {
      if (Number.isInteger(value)) return String(value);
      const str = value.toFixed(1);
      return lang === 'ru' ? str.replace('.', ',') : str;
    }

    function pluralizeUnit(value, kind, lang) {
      const enMap = {year: ['year', 'years'], month: ['month', 'months'], day: ['day', 'days']};
      const ruMap = {
        year: ['год', 'года', 'лет'],
        month: ['месяц', 'месяца', 'месяцев'],
        day: ['день', 'дня', 'дней']
      };
      if (lang === 'en') {
        return value === 1 ? enMap[kind][0] : enMap[kind][1];
      }
      const forms = ruMap[kind];
      if (!Number.isInteger(value)) return forms[1];
      const n = Math.abs(value);
      const mod10 = n % 10;
      const mod100 = n % 100;
      if (mod10 === 1 && mod100 !== 11) return forms[0];
      if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
      return forms[2];
    }

    function renderUserMenu(user) {
      const emailLinked = Boolean(user.email && user.email_verified);
      const telegramLinked = Boolean(user.telegram_linked);
      const displayName = getUserDisplayName(user);
      const secondary = getUserSecondaryText(user, emailLinked, telegramLinked);
      const avatarSrc = getUserAvatarSrc(user);
      const avatarFallback = buildIdenticon(getUserAvatarSeed(user, emailLinked));

      const chipName = document.getElementById('user-chip-name');
      const chipAvatar = document.getElementById('user-chip-avatar');
      const dropAvatar = document.getElementById('user-dropdown-avatar');
      const dropName = document.getElementById('user-dropdown-name');
      const dropSub = document.getElementById('user-dropdown-sub');
      const emailStatus = document.getElementById('user-dropdown-email-status');
      const telegramStatus = document.getElementById('user-dropdown-telegram-status');

      chipName.textContent = displayName;
      setAvatarWithFallback(chipAvatar, avatarSrc, avatarFallback, displayName);
      setAvatarWithFallback(dropAvatar, avatarSrc, avatarFallback, displayName);
      dropName.textContent = displayName;
      dropSub.textContent = secondary;
      dropSub.classList.toggle('hidden', !secondary);

      emailStatus.textContent = emailLinked ? user.email : t('not_linked');
      emailStatus.classList.toggle('linked', emailLinked);
      emailStatus.classList.toggle('unlinked', !emailLinked);

      telegramStatus.textContent = telegramLinked
        ? (user.telegram_id ? String(user.telegram_id) : t('linked'))
        : t('not_linked');
      telegramStatus.classList.toggle('linked', telegramLinked);
      telegramStatus.classList.toggle('unlinked', !telegramLinked);
    }

    function renderAccount(user) {
      const emailLinked = Boolean(user.email && user.email_verified);
      const telegramLinked = Boolean(user.telegram_linked);
      const emailAuthEnabled = Boolean(state.data.settings && state.data.settings.email_auth_enabled);
      const emailCtaVisible = !emailLinked && emailAuthEnabled;
      const telegramCtaVisible = !telegramLinked;

      const emailBox = document.getElementById('email-link-box');
      const telegramBox = document.getElementById('telegram-link-box');
      const linkPanel = document.getElementById('link-panel');
      emailBox.classList.toggle('hidden', !emailCtaVisible);
      telegramBox.classList.toggle('hidden', !telegramCtaVisible);
      linkPanel.classList.toggle('hidden', !emailCtaVisible && !telegramCtaVisible);

      if (!telegramLinked) {
        renderTelegramLinkWidget();
      } else {
        state.telegramLinkRendered = false;
      }
    }

    function getTelegramInitUser() {
      if (!tg || !tg.initDataUnsafe || !tg.initDataUnsafe.user) return null;
      return tg.initDataUnsafe.user;
    }

    function getUserAvatarSeed(user, emailLinked) {
      const tgUser = getTelegramInitUser();
      if (emailLinked && user && user.email) return user.email.trim().toLowerCase();
      return String((user && user.id) || (user && user.telegram_id) || (tgUser && tgUser.id) || 'guest');
    }

    function getUserAvatarSrc(user) {
      const tgUser = getTelegramInitUser();
      if (tgUser && tgUser.photo_url) return tgUser.photo_url;
      if (user && user.telegram_photo_url) return user.telegram_photo_url;
      return '';
    }

    function getUserDisplayName(user) {
      const tgUser = getTelegramInitUser();
      if (tgUser && tgUser.first_name) return tgUser.first_name;
      if (user && user.first_name) return user.first_name;
      if (user && user.username) return '@' + user.username;
      if (tgUser && tgUser.username) return '@' + tgUser.username;
      if (user && user.email) return user.email;
      return t('guest_user');
    }

    function getUserSecondaryText(user, emailLinked, telegramLinked) {
      if (emailLinked && user.email) return user.email;
      if (telegramLinked && user.telegram_id) return '#' + user.telegram_id;
      return '';
    }

    function setAvatarWithFallback(img, avatarSrc, avatarFallback, altText) {
      if (!img) return;

      img.alt = altText || '';
      if (!avatarSrc) {
        img.onerror = null;
        img.src = avatarFallback;
        return;
      }

      img.onerror = () => {
        img.onerror = null;
        img.src = avatarFallback;
      };
      img.src = avatarSrc;
    }

    function buildIdenticon(seed) {
      const raw = String(seed || 'guest');
      let hash = 2166136261 >>> 0;
      for (let i = 0; i < raw.length; i++) {
        hash ^= raw.charCodeAt(i);
        hash = Math.imul(hash, 16777619) >>> 0;
      }
      const hue = hash % 360;
      const bg = 'hsl(' + hue + ', 60%, 18%)';
      const fg = 'hsl(' + ((hue + 180) % 360) + ', 78%, 62%)';
      let rects = '';
      let bits = hash;
      for (let y = 0; y < 5; y++) {
        for (let x = 0; x < 3; x++) {
          const on = bits & 1;
          bits = (bits >>> 1) ^ ((bits & 1) ? 0xB400 : 0);
          if (!on) continue;
          rects += '<rect x="' + x + '" y="' + y + '" width="1" height="1"/>';
          if (x !== 2) {
            rects += '<rect x="' + (4 - x) + '" y="' + y + '" width="1" height="1"/>';
          }
        }
      }
      const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 5 5" shape-rendering="crispEdges">' +
        '<rect width="5" height="5" fill="' + bg + '"/>' +
        '<g fill="' + fg + '">' + rects + '</g>' +
        '</svg>';
      return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
    }

    function toggleUserMenu(force) {
      const open = typeof force === 'boolean' ? force : !state.userMenuOpen;
      state.userMenuOpen = open;
      const chip = document.getElementById('user-chip');
      const dropdown = document.getElementById('user-dropdown');
      if (!chip || !dropdown) return;

      if (state.userMenuCloseTimer) {
        window.clearTimeout(state.userMenuCloseTimer);
        state.userMenuCloseTimer = null;
      }

      chip.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) {
        dropdown.classList.remove('hidden');
        dropdown.classList.remove('show');
        window.requestAnimationFrame(() => {
          if (state.userMenuOpen) {
            dropdown.classList.add('show');
          }
        });
        return;
      }

      dropdown.classList.remove('show');
      state.userMenuCloseTimer = window.setTimeout(() => {
        if (!state.userMenuOpen) {
          dropdown.classList.add('hidden');
        }
        state.userMenuCloseTimer = null;
      }, 180);
    }

    function handleDocumentClickForUserMenu(event) {
      if (!state.userMenuOpen) return;
      const menu = document.querySelector('.user-menu');
      if (menu && menu.contains(event.target)) return;
      toggleUserMenu(false);
    }

    function handleDocumentKeyForUserMenu(event) {
      if (event.key === 'Escape' && state.userMenuOpen) {
        toggleUserMenu(false);
      }
      if (event.key === 'Escape' && state.langMenuOpen) {
        toggleLangMenu(false);
      }
    }

    function renderLangMenu() {
      const current = getLanguage();
      const chipLabel = document.getElementById('lang-chip-label');
      const chipFlag = document.getElementById('lang-chip-flag');
      const opt = LANG_OPTIONS.find(o => o.code === current) || LANG_OPTIONS[0];
      if (chipLabel) chipLabel.textContent = opt.short;
      if (chipFlag) chipFlag.textContent = opt.flag;
      const list = document.getElementById('lang-dropdown');
      if (!list) return;
      list.innerHTML = LANG_OPTIONS.map(o => (
        '<button type="button" role="menuitem" class="lang-dropdown-item' +
        (o.code === current ? ' is-active' : '') +
        '" data-lang="' + o.code + '">' +
        '<span class="lang-dropdown-flag" aria-hidden="true">' + o.flag + '</span>' +
        '<span class="lang-dropdown-label">' + escapeHtml(o.label) + '</span>' +
        '</button>'
      )).join('');
      list.querySelectorAll('[data-lang]').forEach(btn => {
        btn.addEventListener('click', () => setLanguage(btn.dataset.lang));
      });
    }

    function toggleLangMenu(force) {
      const open = typeof force === 'boolean' ? force : !state.langMenuOpen;
      state.langMenuOpen = open;
      const chip = document.getElementById('lang-chip');
      const dropdown = document.getElementById('lang-dropdown');
      if (!chip || !dropdown) return;
      if (state.langMenuCloseTimer) {
        window.clearTimeout(state.langMenuCloseTimer);
        state.langMenuCloseTimer = null;
      }
      chip.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) {
        dropdown.classList.remove('hidden');
        dropdown.classList.remove('show');
        window.requestAnimationFrame(() => {
          if (state.langMenuOpen) dropdown.classList.add('show');
        });
        return;
      }
      dropdown.classList.remove('show');
      state.langMenuCloseTimer = window.setTimeout(() => {
        if (!state.langMenuOpen) dropdown.classList.add('hidden');
        state.langMenuCloseTimer = null;
      }, 180);
    }

    function handleDocumentClickForLangMenu(event) {
      if (!state.langMenuOpen) return;
      const menu = document.querySelector('.lang-menu');
      if (menu && menu.contains(event.target)) return;
      toggleLangMenu(false);
    }

    function handleDocumentActionClick(event) {
      const target = event.target instanceof Element ? event.target.closest('[data-action]') : null;
      if (!target || !document.contains(target) || target.disabled) return;

      const action = String(target.dataset.action || '');
      if (!action) return;

      switch (action) {
        case 'toggle-user-menu':
          toggleUserMenu();
          break;
        case 'toggle-lang-menu':
          toggleLangMenu();
          break;
        case 'logout':
          logout();
          break;
        case 'open-connect-link':
          openConnectLink();
          break;
        case 'toggle-payment-flow':
          togglePaymentFlow();
          break;
        case 'open-referral-modal':
          openReferralModal();
          break;
        case 'open-promo-modal':
          openPromoModal();
          break;
        case 'close-payment-flow':
          closePaymentFlow();
          break;
        case 'close-promo-modal':
          closePromoModal();
          break;
        case 'close-referral-modal':
          closeReferralModal();
          break;
        case 'close-account-merge-modal':
          closeAccountMergeModal();
          break;
        case 'close-email-login-code-modal':
          closeEmailLoginCodeModal();
          break;
        case 'request-email-link-code':
          requestEmailLinkCode();
          break;
        case 'verify-email-link-code':
          verifyEmailLinkCode();
          break;
        case 'request-email-login-code':
          requestEmailLoginCode();
          break;
        case 'verify-email-login-code':
          verifyEmailLoginCode();
          break;
        case 'resend-email-login-code':
          resendEmailLoginCode();
          break;
        case 'set-auth-mode':
          setAuthMode(target.dataset.mode || 'email');
          break;
        case 'apply-promo-code':
          applyPromoCode();
          break;
        case 'select-plan':
          selectPlan(target.dataset.months || '');
          break;
        case 'create-payment':
          createAndOpenPayment(target.dataset.method || '');
          break;
        case 'copy-referral-link':
          copyReferralLink(target.dataset.kind || 'webapp');
          break;
        case 'copy-config-link':
          copyConfigLink();
          break;
        case 'check-payment':
          checkPayment();
          break;
        default:
          return;
      }

      event.preventDefault();
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
      const modal = document.getElementById('promo-modal');
      if (!modal) return;

      if (!state.promoModalOpen) {
        modal.classList.remove('show');
        syncModalLock();
        window.setTimeout(() => {
          if (!state.promoModalOpen) modal.classList.add('hidden');
        }, 180);
        return;
      }

      modal.classList.remove('hidden');
      syncModalLock();
      renderPromoStatus();
      applyI18n(modal);
      window.requestAnimationFrame(() => modal.classList.add('show'));
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
      state.accountMergeModalOpen = false;
      clearPromoStatus();
      renderPromoModal();
      renderReferral(state.data && state.data.referral || {});
      renderAccountMergeModal();
    }



    function openAccountMergeModal(notice = null) {
      if (notice) {
        state.accountMergeNotice = notice;
      }
      state.accountMergeModalOpen = true;
      renderAccountMergeModal();
    }

    function closeAccountMergeModal() {
      state.accountMergeModalOpen = false;
      renderAccountMergeModal();
    }

    function renderAccountMergeModal() {
      const modal = document.getElementById('account-merge-modal');
      const panel = document.getElementById('account-merge-panel');
      if (!modal || !panel) return;

      if (!state.accountMergeModalOpen) {
        modal.classList.remove('show');
        syncModalLock();
        window.setTimeout(() => {
          if (!state.accountMergeModalOpen) modal.classList.add('hidden');
        }, 180);
        return;
      }

      modal.classList.remove('hidden');
      syncModalLock();

      const notice = state.accountMergeNotice || {};
      const primaryUserId = notice.primary_user_id != null ? String(notice.primary_user_id) : t('not_available');
      const removedUserId = notice.removed_user_id != null ? String(notice.removed_user_id) : t('not_available');
      const finalEndDateText = notice.final_end_date_text || t('not_available');

      panel.innerHTML = `
        <div class="${TW.panelHead}">
          <div>
            <div id="account-merge-title" class="${TW.sectionTitle} text-[var(--accent)]">${escapeHtml(t('account_merge_title'))}</div>
            <div id="account-merge-caption" class="${TW.flowCaption}">${escapeHtml(t('account_merge_caption'))}</div>
          </div>
          <button class="${TW.iconBtn}" type="button" data-title-i18n="close" data-action="close-account-merge-modal">×</button>
        </div>

        <div class="notice grid gap-2">
          <div class="text-[13px] leading-[1.5] text-[var(--text-secondary)]">${escapeHtml(t('account_merge_body'))}</div>
        </div>

        <div class="grid gap-2">
          <div class="metric rounded-[var(--radius-md)] grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
            <div class="metric-label">${escapeHtml(t('account_merge_primary_account_label'))}</div>
            <div class="metric-value">#${escapeHtml(primaryUserId)}</div>
          </div>
          <div class="metric rounded-[var(--radius-md)] grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
            <div class="metric-label">${escapeHtml(t('account_merge_removed_account_label'))}</div>
            <div class="metric-value">#${escapeHtml(removedUserId)}</div>
          </div>
          <div class="metric rounded-[var(--radius-md)] grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
            <div class="metric-label">${escapeHtml(t('account_merge_end_date_label'))}</div>
            <div class="metric-value">${escapeHtml(finalEndDateText)}</div>
          </div>
        </div>
      `;
      applyI18n(modal);
      window.requestAnimationFrame(() => modal.classList.add('show'));
    }

    function renderReferral(referral) {
      const modal = document.getElementById('referral-modal');
      const panel = document.getElementById('referral-panel');
      if (!modal || !panel) return;

      if (!state.referralModalOpen) {
        modal.classList.remove('show');
        syncModalLock();
        window.setTimeout(() => {
          if (!state.referralModalOpen) modal.classList.add('hidden');
        }, 180);
        return;
      }

      modal.classList.remove('hidden');
      syncModalLock();
      if (!state.referralModalOpen) return;

      const bonusRows = (referral.bonus_details || []).map(item => `
        <div class="${TW.bonusRow}">
          <span>${escapeHtml(item.title || '')}</span>
          <strong>${escapeHtml(t('referral_bonus_pair', {
            inviter: item.inviter_days || 0,
            friend: item.friend_days || 0
          }))}</strong>
        </div>
      `).join('');

      panel.innerHTML = `
        <div class="${TW.panelHead}">
          <div>
            <div class="${TW.sectionTitle} text-[var(--accent)]">${escapeHtml(t('referral_title'))}</div>
            <div class="${TW.flowCaption}">${escapeHtml(t('referral_caption'))}</div>
          </div>
          <button class="${TW.iconBtn}" type="button" data-title-i18n="close" data-action="close-referral-modal">×</button>
        </div>
        
        <div class="grid gap-4 mt-1">
          <div class="grid gap-2.5">
            <div class="section-label font-[family-name:var(--font-mono)] text-[12px] font-extrabold text-[var(--accent)] uppercase">ВАШИ ССЫЛКИ</div>
            <div class="referral-link-list grid gap-2">
              ${renderReferralLinkRow('webapp', t('referral_site_label'), referral.webapp_link)}
              ${renderReferralLinkRow('bot', t('referral_telegram_label'), referral.bot_link)}
            </div>
          </div>

          <div class="referral-bonus-card grid gap-3 rounded-[var(--radius-md)] border border-[var(--border)] bg-[rgba(255,255,255,0.015)] p-3.5">
            <div class="grid gap-1">
              <div class="section-label font-[family-name:var(--font-mono)] text-[12px] font-extrabold text-[var(--accent)] uppercase">${escapeHtml(t('referral_bonus_title'))}</div>
              <div class="text-[13px] leading-[1.45] text-[var(--text-secondary)]">${escapeHtml(t('referral_bonus_explanation'))}</div>
            </div>
            <div class="bonus-list grid gap-2">${bonusRows || '<div class="' + TW.empty + ' border-none bg-[rgba(255,255,255,0.03)]">' + escapeHtml(t('referral_no_bonuses')) + '</div>'}</div>
          </div>
        </div>
      `;
      applyI18n(modal);
      window.requestAnimationFrame(() => modal.classList.add('show'));
    }

    function renderReferralLinkRow(kind, label, link) {
      return `
        <div class="${TW.referralLinkRow}">
          <div>
            <div class="${TW.metricLabel}">${escapeHtml(label)}</div>
            <div class="${TW.referralLinkValue}">${escapeHtml(link || t('not_available'))}</div>
          </div>
          <button class="${TW.btnBase} w-12 px-0" type="button" data-action="copy-referral-link" data-kind="${escapeAttr(kind)}" ${link ? '' : 'disabled'} data-title-i18n="copy_link">
            <svg class="h-5 w-5 fill-current" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" aria-hidden="true">
              <path d="M352 512L128 512L128 288L176 288L176 224L128 224C92.7 224 64 252.7 64 288L64 512C64 547.3 92.7 576 128 576L352 576C387.3 576 416 547.3 416 512L416 464L352 464L352 512zM288 416L512 416C547.3 416 576 387.3 576 352L576 128C576 92.7 547.3 64 512 64L288 64C252.7 64 224 92.7 224 128L224 352C224 387.3 252.7 416 288 416z"/>
            </svg>
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

    async function copyReferralCode() {
      const referral = state.data && state.data.referral;
      const code = referral && referral.code;
      if (!code) {
        showToast(t('no_link'));
        return;
      }
      await copyText(code);
      showToast(t('code_copied'));
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
      let mergeNotice = null;
      try {
        const data = await api('/account/email/verify', {
          method: 'POST',
          body: JSON.stringify({email, code})
        });
        if (!data.ok) throw data;
        if (data.token) setToken(data.token, data.csrf_token);
        mergeNotice = data.account_merge && data.account_merge.merged ? data.account_merge : null;
        state.accountMergeNotice = mergeNotice;
        showToast(mergeNotice ? t('account_merge_toast') : t('email_linked'));
        state.emailLinkEmail = '';
        try {
          await loadData();
          if (mergeNotice) {
            openAccountMergeModal(mergeNotice);
          }
        } catch (refreshError) {
          console.warn('Email account linked, but data refresh failed', refreshError);
          if (mergeNotice) {
            openAccountMergeModal(mergeNotice);
          }
        }
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
      script.setAttribute('data-userpic', 'true');
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
      if (data.token) setToken(data.token, data.csrf_token);
      markTelegramLinked(data.telegram_id || fallbackTelegramId);
      setTelegramLinkStatus('');
      state.telegramLinkRendered = false;
      const mergeNotice = data.account_merge && data.account_merge.merged ? data.account_merge : null;
      state.accountMergeNotice = mergeNotice;
      try {
        showToast(mergeNotice ? t('account_merge_toast') : t('telegram_linked'));
      } catch (toastError) {
        console.warn('Telegram link success toast failed', toastError);
      }
      try {
        await loadData();
        if (mergeNotice) {
          openAccountMergeModal(mergeNotice);
        }
      } catch (refreshError) {
        console.warn('Telegram account linked, but data refresh failed', refreshError);
        if (mergeNotice) {
          openAccountMergeModal(mergeNotice);
        }
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
      state.creatingPayment = false;
      state.payment = null;
      state.selectedPlan = getDefaultPaymentPlan((state.data && state.data.plans) || []);
      renderPaymentFlow();
    }

    function closePaymentFlow() {
      state.paymentFlowOpen = false;
      state.creatingPayment = false;
      state.payment = null;
      renderPaymentFlow();
    }

    function renderPaymentFlow() {
      const modal = document.getElementById('payment-modal');
      if (!modal) return;
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
      renderPlans((state.data && state.data.plans) || []);
      renderPaymentSummary();
      renderMethods();
      applyI18n(modal);
    }

    function syncModalLock() {
      document.body.classList.toggle(
        'modal-open',
        Boolean(
          state.paymentFlowOpen
          || state.emailLoginCodeModalOpen
          || state.promoModalOpen
          || state.referralModalOpen
          || state.accountMergeModalOpen
        )
      );
    }

    function getDefaultPaymentPlan(plans = []) {
      if (!plans.length) return null;
      return plans.find(plan => Number(plan.months) === 3) || plans[0] || null;
    }

    function renderPlans(plans) {
      const wrap = document.getElementById('plans');
      if (!wrap) return;
      if (!plans.length) {
        wrap.innerHTML = '<div class="' + TW.empty + '">' + escapeHtml(t('no_plans')) + '</div>';
        return;
      }

      if (!state.selectedPlan || !plans.some(plan => Number(plan.months) === Number(state.selectedPlan.months))) {
        state.selectedPlan = getDefaultPaymentPlan(plans);
      }

      wrap.innerHTML = plans.map(plan => {
        const planMonths = Number(plan.months);
        const isActive = state.selectedPlan && Number(state.selectedPlan.months) === planMonths;
        return `
          <button class="${TW.planCard} ${isActive ? TW.planCardActive : ''}" type="button" data-action="select-plan" data-months="${planMonths}" ${state.creatingPayment ? 'disabled' : ''}>
            ${escapeHtml(plan.title)}
          </button>
        `;
      }).join('');
    }

    function renderPaymentSummary() {
      const price = document.getElementById('selected-plan-price');
      if (!price) return;
      if (!state.selectedPlan) {
        price.textContent = t('no_plans');
        return;
      }
      price.textContent = formatMoney(state.selectedPlan.price, state.selectedPlan.currency);
    }

    function renderMethods() {
      const methods = document.getElementById('payment-methods');
      if (!methods) return;
      if (!state.selectedPlan) {
        methods.innerHTML = '<div class="' + TW.empty + '">' + escapeHtml(t('choose_plan_first')) + '</div>';
        return;
      }

      const available = getAvailableMethods();
      if (!available.length) {
        methods.innerHTML = '<div class="' + TW.empty + '">' + escapeHtml(t('no_methods')) + '</div>';
        return;
      }

      methods.innerHTML = available.map(method => {
        let labelKey;
        let variantClass;
        if (method.id === 'platega_sbp') {
          labelKey = 'pay_with_platega_sbp_button';
          variantClass = TW.paymentMethodCardPlategaSbp;
        } else if (method.id === 'platega_crypto') {
          labelKey = 'pay_with_platega_crypto_button';
          variantClass = TW.paymentMethodCardPlategaCrypto;
        } else if (method.id === 'platega') {
          labelKey = 'pay_with_platega_button';
          variantClass = TW.paymentMethodCardPlatega;
        } else {
          labelKey = 'pay_with_cryptopay_button';
          variantClass = TW.paymentMethodCardCryptopay;
        }
        return `
          <button class="${TW.paymentMethodCard} ${variantClass}" type="button" data-action="create-payment" data-method="${escapeAttr(method.id)}" data-i18n="${labelKey}" ${state.creatingPayment ? 'disabled' : ''}>
            ${escapeHtml(t(labelKey))}
          </button>
        `;
      }).join('');
    }

    function selectPlan(months) {
      if (state.creatingPayment) return;
      state.selectedPlan = ((state.data && state.data.plans) || []).find(plan => Number(plan.months) === Number(months)) || null;
      state.payment = null;
      renderPaymentFlow();
    }

    async function createAndOpenPayment(method) {
      if (state.creatingPayment) return;
      if (!state.selectedPlan) {
        showToast(t('choose_plan_toast'));
        return;
      }
      const available = getAvailableMethods();
      if (!available.some(item => item.id === method)) {
        showToast(t('no_methods'));
        return;
      }

      state.creatingPayment = true;
      state.payment = null;
      renderPaymentFlow();
      try {
        const data = await api('/payments', {
          method: 'POST',
          body: JSON.stringify({months: state.selectedPlan.months, method})
        });
        if (!data.ok || !data.payment_url) throw new Error(data.message || t('payment_error'));
        state.payment = data;
        const opened = openPaymentUrl(data.payment_url);
        if (opened) {
          closePaymentFlow();
        }
      } catch (e) {
        showToast(e.message || t('payment_error'));
      } finally {
        state.creatingPayment = false;
        if (state.paymentFlowOpen) {
          renderPaymentFlow();
        }
      }
    }

    function getAvailableMethods() {
      if (!state.data || !state.selectedPlan) return [];
      const methodsById = new Map(
        (state.data.payment_methods || []).map(method => [String(method.id || '').toLowerCase(), method])
      );
      return ['platega_sbp', 'platega_crypto', 'platega', 'cryptopay']
        .map(methodId => methodsById.get(methodId))
        .filter(Boolean);
    }

    function openPaymentUrl(url) {
      const paymentUrl = String(url || (state.payment && state.payment.payment_url) || '').trim();
      if (!paymentUrl) return false;
      if (tg && tg.openLink) {
        tg.openLink(paymentUrl);
        return true;
      }
      const opened = window.open(paymentUrl, '_blank', 'noopener');
      if (!opened) {
        window.location.assign(paymentUrl);
      }
      return true;
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

      const method = String(options.method || 'GET').toUpperCase();
      const headers = Object.assign({}, options.headers || {});
      if (state.token) {
        headers.Authorization = 'Bearer ' + state.token;
      }
      const csrfToken = state.csrfToken || readCookie('rw_webapp_csrf') || '';
      if (csrfToken && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
        headers['X-CSRF-Token'] = csrfToken;
      }
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
        return {ok: true, token: 'local-preview', csrf_token: 'local-preview-csrf'};
      }
      if (path === '/auth/email/magic') {
        return {ok: true, token: 'local-preview', csrf_token: 'local-preview-csrf'};
      }
      if (path === '/account/email/verify') {
        MOCK.data.user.email = 'preview@example.com';
        MOCK.data.user.email_verified = true;
        return {ok: true, token: 'local-preview', csrf_token: 'local-preview-csrf'};
      }
      if (path === '/account/telegram/link') {
        MOCK.data.user.telegram_linked = true;
        MOCK.data.user.telegram_id = 100200300;
        return {ok: true, token: 'local-preview', csrf_token: 'local-preview-csrf'};
      }
      if (path === '/auth/logout') {
        return {ok: true};
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

    function setToken(token, csrfToken = '') {
      clearManualLogoutFlag();
      state.token = token;
      state.csrfToken = csrfToken || readCookie('rw_webapp_csrf') || state.csrfToken || '';
    }

    function clearToken() {
      state.token = '';
      state.csrfToken = '';
      localStorage.removeItem('rw_webapp_token');
    }

    function clearReadableAuthCookie() {
      document.cookie = 'rw_webapp_csrf=; Max-Age=0; path=/; SameSite=None; Secure';
    }

    function isManuallyLoggedOut() {
      try {
        return localStorage.getItem(MANUAL_LOGOUT_FLAG_KEY) === '1';
      } catch (e) {
        return false;
      }
    }

    function markManualLogout() {
      try {
        localStorage.setItem(MANUAL_LOGOUT_FLAG_KEY, '1');
      } catch (e) { }
    }

    function clearManualLogoutFlag() {
      try {
        localStorage.removeItem(MANUAL_LOGOUT_FLAG_KEY);
      } catch (e) { }
    }

    function readCookie(name) {
      const prefix = name + '=';
      const cookie = document.cookie.split('; ').find(part => part.startsWith(prefix));
      return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : '';
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

    async function logout() {
      toggleUserMenu(false);
      markManualLogout();
      clearReadableAuthCookie();
      clearToken();
      closePaymentFlow();
      closeEmailLoginCodeModal();
      startExternalAuth();
      try {
        await publicApi('/auth/logout', {keepalive: true});
      } catch (e) { }
    }

    function showLoader() {
      document.getElementById('loader').classList.remove('hidden');
      document.getElementById('app').classList.add('hidden');
      document.getElementById('login').classList.remove('show');
    }

    function showApp() {
      document.getElementById('loader').classList.add('hidden');
      document.getElementById('login').classList.remove('show');
      document.getElementById('login').classList.add('hidden');
      document.getElementById('app').classList.remove('hidden');
    }

    function showLogin() {
      document.getElementById('loader').classList.add('hidden');
      document.getElementById('app').classList.add('hidden');
      document.getElementById('login').classList.remove('hidden');
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
      const toast = document.getElementById('toast');
      if (!toast) return;

      toast.textContent = message;
      toast.classList.remove('hidden');
      
      // Force reflow
      void toast.offsetWidth;
      
      toast.classList.add('show');

      // Telegram Haptic Feedback
      if (tg && tg.HapticFeedback) {
        try {
          tg.HapticFeedback.notificationOccurred('success');
        } catch (e) {
          console.warn('Haptic feedback failed', e);
        }
      }

      if (state.toastTimer) window.clearTimeout(state.toastTimer);
      state.toastTimer = window.setTimeout(() => {
        toast.classList.remove('show');
        window.setTimeout(() => {
          if (!toast.classList.contains('show')) {
            toast.classList.add('hidden');
          }
        }, 250);
      }, 2200);
    }

    function setFavicon(href) {
      let favicon = document.getElementById('app-favicon');
      if (!favicon) {
        favicon = document.createElement('link');
        favicon.id = 'app-favicon';
        favicon.rel = 'icon';
        favicon.setAttribute('sizes', 'any');
        document.head.appendChild(favicon);
      }
      favicon.href = href || 'data:,';
    }

    function setBrandLogo(shell, logoUrl) {
      if (!shell) return;

      const logo = shell.querySelector('[data-brand-logo]');
      const spinner = shell.querySelector('[data-brand-logo-spinner]');
      if (!logo) return;

      logo.onload = null;
      logo.onerror = null;
      logo.removeAttribute('data-brand-logo-url');

      if (!logoUrl) {
        logo.removeAttribute('src');
        logo.classList.add('hidden');
        if (spinner) spinner.classList.add('hidden');
        shell.classList.add('hidden');
        return;
      }

      const expectedUrl = logoUrl;
      shell.classList.remove('hidden');
      if (spinner) spinner.classList.remove('hidden');
      logo.classList.add('hidden');
      logo.dataset.brandLogoUrl = expectedUrl;

      logo.onload = () => {
        if (logo.dataset.brandLogoUrl !== expectedUrl) return;
        logo.classList.remove('hidden');
        if (spinner) spinner.classList.add('hidden');
      };

      logo.onerror = () => {
        if (logo.dataset.brandLogoUrl !== expectedUrl) return;
        logo.removeAttribute('src');
        logo.classList.add('hidden');
        if (spinner) spinner.classList.add('hidden');
        shell.classList.add('hidden');
      };

      logo.src = logoUrl;
      if (logo.complete && logo.naturalWidth > 0) {
        logo.classList.remove('hidden');
        if (spinner) spinner.classList.add('hidden');
      }
    }

    function setBrand() {
      const title = CFG.title || document.title || t('page_title');
      const logoUrl = CFG.logoUrl || '';
      document.title = title;
      setFavicon(logoUrl);
      document.querySelectorAll('[data-brand-title]').forEach(node => {
        node.textContent = title;
      });
      document.querySelectorAll('[data-brand-logo-shell]').forEach(shell => {
        setBrandLogo(shell, logoUrl);
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

      root.querySelectorAll('[data-legal-links]').forEach(container => {
        const visible = Array.from(container.querySelectorAll('[data-legal-key]'))
          .some(node => !node.classList.contains('hidden'));
        container.classList.toggle('hidden', !visible);
      });
    }

    function getLanguage() {
      const candidates = [];
      if (state.langOverride) candidates.push(state.langOverride);
      if (state.data && state.data.user && state.data.user.language_code) {
        candidates.push(state.data.user.language_code);
      }
      const tgUser = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
      if (tgUser && tgUser.language_code) candidates.push(tgUser.language_code);
      if (typeof navigator !== 'undefined') {
        if (Array.isArray(navigator.languages)) {
          navigator.languages.forEach(l => l && candidates.push(l));
        }
        if (navigator.language) candidates.push(navigator.language);
      }
      if (CFG.language) candidates.push(CFG.language);
      if (document.documentElement.lang) candidates.push(document.documentElement.lang);
      for (const raw of candidates) {
        const short = String(raw).toLowerCase().split('-')[0];
        if (I18N && I18N[short]) return short;
      }
      return 'ru';
    }

    function setLanguage(lang) {
      const short = String(lang || '').toLowerCase().split('-')[0];
      if (I18N && Object.keys(I18N).length && !I18N[short]) return;
      state.langOverride = short;
      try { localStorage.setItem('rw_webapp_lang', short); } catch (e) { }
      applyI18n();
      if (state.data) {
        try { render(); } catch (e) { }
      }
      renderLangMenu();
      toggleLangMenu(false);
    }

    function t(key, params = {}) {
      const table = (I18N && I18N[getLanguage()]) || (I18N && I18N.ru) || {};
      const fallback = (I18N && I18N.ru && I18N.ru[key]) || key;
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
