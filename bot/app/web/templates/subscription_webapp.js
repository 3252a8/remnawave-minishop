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
        language: 'ru'
      },
      data: {
        ok: true,
        user: {
          id: 100200300,
          username: 'preview',
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
        settings: {
          support_url: 'https://t.me/support',
          traffic_mode: false
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
      payment: null,
      paymentFlowOpen: false,
      paymentStep: 'plan',
      creatingPayment: false,
      authInProgress: false,
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
        extend_subscription: 'Продлить подписку/Добавить дни',
        payment_title: 'Оплата подписки',
        payment_caption: 'Выберите срок, способ оплаты и создайте платеж.',
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
        user_agreement: 'Пользовательское соглашение'
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
        user_agreement: 'User agreement'
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

    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && state.paymentFlowOpen) {
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

    function startExternalAuth(options = {}) {
      const resetStatus = options.resetStatus !== false;
      showLogin();
      if (resetStatus) {
        setAuthStatus('');
      }
      renderTelegramLoginWidget();
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
      render();
      showApp();
    }

    async function reloadData() {
      showToast(t('updating'));
      await loadData();
    }

    function render() {
      renderSubscription(state.data.subscription);
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
        document.body.classList.remove('modal-open');
        window.setTimeout(() => {
          if (!state.paymentFlowOpen) modal.classList.add('hidden');
        }, 180);
        return;
      }

      modal.classList.remove('hidden');
      document.body.classList.add('modal-open');
      window.requestAnimationFrame(() => modal.classList.add('show'));
      applyI18n(modal);
      renderStepState();
      renderPlans(state.data.plans || []);
      renderMethods();
      renderPaymentResult();
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
      try {
        await navigator.clipboard.writeText(link);
        showToast(t('link_copied'));
      } catch (e) {
        const area = document.createElement('textarea');
        area.value = link;
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        area.remove();
        showToast(t('link_copied'));
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

    async function mockApi(path, options = {}) {
      await new Promise(resolve => window.setTimeout(resolve, 120));
      if (path === '/me') {
        return JSON.parse(JSON.stringify(MOCK.data));
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

    function logout() {
      clearToken();
      closePaymentFlow();
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
