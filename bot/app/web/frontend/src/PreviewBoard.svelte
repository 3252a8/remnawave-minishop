<script>
  import {
    ArrowRight,
    CheckCircle2,
    Circle,
    Copy,
    Crown,
    Database,
    Download,
    Gift,
    Globe2,
    LockKeyhole,
    Mail,
    RefreshCw,
    Repeat2,
    Send,
    Ticket,
    UserRound,
    Zap,
  } from "lucide-svelte";

  import Button from "./lib/components/ui/button.svelte";
  import Card from "./lib/components/ui/card.svelte";
  import BackTitle from "./preview/BackTitle.svelte";
  import PhoneFrame from "./preview/PhoneFrame.svelte";
  import PreviewMethods from "./preview/PreviewMethods.svelte";
  import PreviewNav from "./preview/PreviewNav.svelte";

  export let config = {};
  export let mockData = {};

  const title = config.title || "/minishop";
  const logoEmoji = config.logoEmoji || "🫥";
  const plans = mockData.plans || [];
  const sub = mockData.subscription || {};
  const methods = mockData.payment_methods || [];
  const user = mockData.user || {};
  const tariffs = [
    ["subscription", "Подписка", "Безлимитный трафик", "Идеально для постоянного использования", Zap],
    ["traffic", "Трафик", "Пакеты гигабайт", "Платите только за нужный объем", Database],
    ["premium", "Премиум", "Максимальная скорость", "Приоритетные серверы и поддержка", Crown],
  ];
  const traffic = [
    [20, 290],
    [50, 590],
    [100, 990],
    [300, 2190],
  ];
  const settingsRows = [
    [Globe2, "Язык интерфейса", "Русский"],
    [Send, "Привязка Telegram", user.telegram_linked ? `@${user.username || "username"}` : "Не привязан"],
    [Mail, "Привязка почты", user.email || "Не привязана"],
    [UserRound, "Выйти", "Завершить сессию"],
  ];
  const previewTelegramName = user.first_name || (user.username ? `@${user.username}` : "Telegram не привязан");
  const previewEmail = user.email || "Почта не привязана";
  const previewTelegramId = user.telegram_id ? `TG ID ${user.telegram_id}` : "TG ID не привязан";
  const previewAvatar = user.telegram_photo_url || "";

  function money(value) {
    return `${value} ₽`;
  }
</script>

<div class="preview-board" style={`--accent: ${config.primaryColor || "#00fe7a"};`}>
  <PhoneFrame number="1" label="Главный экран">
    <main class="home-layout">
      <div class="login-brand home-brand">
        <div class="brand-mark brand-mark-xl"><span>{logoEmoji}</span></div>
        <h1>{title}</h1>
      </div>
      <div class="home-bottom">
        <Card class="status-card">
          <div class="sub-status">
            <CheckCircle2 size={23} />
            <div><h2>Подписка активна</h2><p>до {sub.end_date_text}</p></div>
          </div>
        </Card>
        <Card>
          <div class="traffic-top"><span>Использовано трафика</span><strong>{sub.traffic_used} из {sub.traffic_limit}</strong></div>
          <div class="progress"><span style="width: 18%"></span></div>
          <div class="traffic-percent">18%</div>
        </Card>
        <div class="action-stack">
          <Button class="wide"><Download size={17} />Установить и настроить</Button>
          <Button variant="secondary" class="wide"><RefreshCw size={17} />Продлить</Button>
          <Button variant="secondary" class="wide"><Repeat2 size={17} />Сменить тариф</Button>
        </div>
      </div>
      <PreviewNav active="home" />
    </main>
  </PhoneFrame>

  <PhoneFrame number="2" label="Выбор тарифа">
    <div class="preview-header"><div class="brand-row"><div class="brand-mark"><span>{logoEmoji}</span></div><strong>{title}</strong></div></div>
    <div class="tariff-list">
      {#each tariffs as tariff, index}
        <div class:active={index === 0} class="select-card">
          <span class="select-icon"><svelte:component this={tariff[4]} size={24} /></span>
          <span><strong>{tariff[1]}</strong><small>{tariff[2]}</small><em>{tariff[3]}</em></span>
          {#if index === 0}<CheckCircle2 size={21} />{:else}<Circle size={21} />{/if}
        </div>
      {/each}
    </div>
    <Button class="wide bottom-action">Далее <ArrowRight size={17} /></Button>
  </PhoneFrame>

  <PhoneFrame number="3" label="Оплата тарифа — подписка" wide>
    <BackTitle title="Подписка" subtitle="Выберите срок подписки" />
    <div class="period-grid">
      {#each plans as plan, index}
        <div class:active={index === 1} class="period-card">
          <strong>{plan.title}</strong><span>{money(plan.price)}</span><small>{money(Math.round(plan.price / plan.months))}/мес</small>
          {#if index === 1}<CheckCircle2 size={18} />{/if}
        </div>
      {/each}
    </div>
    <Card class="total-card"><span>Итого<br /><small>К оплате</small></span><strong>790 ₽</strong></Card>
    <PreviewMethods {methods} />
    <Button class="wide bottom-action">Оплатить 790 ₽ <LockKeyhole size={16} /></Button>
  </PhoneFrame>

  <PhoneFrame number="4" label="Оплата тарифа — трафик" wide>
    <BackTitle title="Трафик" subtitle="Выберите пакет трафика" />
    <div class="period-grid">
      {#each traffic as pack, index}
        <div class:active={index === 2} class="period-card">
          <strong>{pack[0]} ГБ</strong><span>{money(pack[1])}</span><small>{money(Math.round(pack[1] / pack[0]))}/ГБ</small>
          {#if index === 2}<CheckCircle2 size={18} />{/if}
        </div>
      {/each}
    </div>
    <Card class="total-card"><span>Итого<br /><small>К оплате</small></span><strong>990 ₽</strong></Card>
    <PreviewMethods {methods} />
    <Button class="wide bottom-action">Оплатить 990 ₽ <LockKeyhole size={16} /></Button>
  </PhoneFrame>

  <PhoneFrame number="5" label="Смена тарифа">
    <BackTitle title="Смена тарифа" subtitle="Остаток 12 дней будет пересчитан" />
    <div class="tariff-list compact">
      <div class="select-card"><span><strong>Подписка</strong><small>Безлимитный трафик</small></span><em>Доплата 190 ₽</em><Circle size={20} /></div>
      <div class="select-card active"><span><strong>Трафик</strong><small>Пакеты гигабайт</small></span><em>Доплата не требуется</em><CheckCircle2 size={20} /></div>
      <div class="select-card"><span><strong>Премиум</strong><small>Максимальная скорость</small></span><em>Доплата 390 ₽</em><Circle size={20} /></div>
    </div>
    <Button class="wide bottom-action">Далее <ArrowRight size={17} /></Button>
    <div class="preview-modal">
      <Repeat2 size={30} />
      <strong>Сменить тариф без доплаты?</strong>
      <p>Остаток 12 дней будет пересчитан по новому тарифу.</p>
      <Button>Да, сменить</Button>
      <Button variant="secondary">Отмена</Button>
    </div>
  </PhoneFrame>

  <PhoneFrame number="6" label="Пригласить друга">
    <div class="preview-header"><div class="brand-row"><div class="brand-mark"><span>{logoEmoji}</span></div><strong>{title}</strong></div></div>
    <Card>
      <div class="card-label">Ваша реферальная ссылка</div>
      <div class="copy-row"><code>https://minishop.app/ref/ABCD1234</code><Button>Копировать <Copy size={16} /></Button></div>
    </Card>
    <Card class="bonus-card">
      <Gift size={42} /><div><span>Ваш бонус</span><strong>+7 дней за каждого друга</strong><p>Друг получит +3 дня к подписке.</p></div>
    </Card>
    <Button variant="outline" class="wide"><Ticket size={18} />Активировать промокод</Button>
  </PhoneFrame>

  <PhoneFrame number="7" label="Настройки">
    <div class="preview-header"><div class="brand-row"><div class="brand-mark"><span>{logoEmoji}</span></div><strong>{title}</strong></div></div>
    <Card class="settings-profile">
      <div class="settings-avatar">
        {#if previewAvatar}
          <img src={previewAvatar} alt="Аватар пользователя" />
        {:else}
          <UserRound size={27} />
        {/if}
      </div>
      <div class="settings-profile-meta">
        <strong>{previewTelegramName}</strong>
        <small>{previewEmail}</small>
        <small>{previewTelegramId}</small>
      </div>
    </Card>    <div class="settings-list">
      {#each settingsRows as row}
        <div class="settings-row">
          <svelte:component this={row[0]} size={20} />
          <span><strong>{row[1]}</strong><small>{row[2]}</small></span>
          <ArrowRight size={16} />
        </div>
      {/each}
    </div>
  </PhoneFrame>

  <PhoneFrame number="8" label="Логин" wide>
    <div class="login-brand small">
      <div class="brand-mark brand-mark-xl"><span>{logoEmoji}</span></div>
      <h1>{title}</h1><p>Войдите в свой аккаунт</p>
    </div>
    <Card class="auth-card">
      <div class="field-label">Вход по email</div>
      <div class="auth-email-stack"><div class="input muted">Email</div><Button class="wide"><Mail size={17} />Войти по почте</Button></div>
      <div class="or-line"><span></span>или<span></span></div>
      <Button variant="telegram" class="wide telegram-login-button">
        <span class="telegram-login-text"><Send size={17} />Войти через телеграм</span>
      </Button>
    </Card>
  </PhoneFrame>

  <PhoneFrame number="9" label="Подтверждение по коду" wide>
    <BackTitle title="Подтверждение по email" subtitle="Мы отправили код на user@example.com" />
    <div class="otp-slots static">{#each [1, 2, 3, 4, 5, 6] as digit}<span>{digit}</span>{/each}</div>
    <Button class="wide bottom-action">Подтвердить</Button>
    <button class="link-button"><RefreshCw size={15} />Отправить код повторно (00:45)</button>
  </PhoneFrame>
</div>



