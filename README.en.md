# Remnawave Minishop

![Remnawave Minishop](docs/remnawave-minishop.webp)

English contributor entry point. The Russian [README.md](README.md) and
[CONTRIBUTING.md](CONTRIBUTING.md) are canonical; this page is a compact map for setup,
verification, and the most important repository rules.

Remnawave Minishop is a Telegram bot and Web App (Mini App) for selling and managing
subscriptions in a [Remnawave](https://docs.rw/) panel. It covers registration, payments,
renewals, trials, promo codes, referrals, support tickets, install guides, device management,
traffic add-ons, and an admin panel backed by typed HTTP contracts.

## Features

For users:

- Telegram bot onboarding with Russian and English locales.
- Subscription status, connection link, expiry date, traffic usage, and device limits.
- Web App login through Telegram Mini Apps `initData`, Telegram OAuth / OpenID Connect, or a
  one-time email code.
- Trial periods, promo codes, referrals, traffic packages, extra devices, and install guides.
- Payment integrations including YooKassa, FreeKassa, Platega, SeverPay, Wata, CryptoPay,
  Heleket, PayKilla, LAVA, Pally, CloudPayments, Stripe, and Telegram Stars.
- Support tickets inside the Web App plus optional external support links.

For admins:

- Web App admin area for `ADMIN_IDS`.
- User, subscription, payment, sync, broadcast, promo, support, and action-log workflows.
- Tariff catalog editor with time-based, traffic-based, premium-traffic, Internal Squad, and
  HWID/device options.
- Manual Remnawave sync, panel webhook processing, backups, themes, translations, and runtime
  settings layered over `.env`.

## Quickstart

Requirements:

- Docker and Docker Compose.
- A Remnawave panel newer than `2.7.0`.
- A Telegram bot token.
- Public HTTPS domains for webhooks and the Mini App.

```bash
git clone https://github.com/3252a8/remnawave-minishop
cd remnawave-minishop
cp .env.example .env
# edit .env
docker compose up -d --build
docker compose logs -f backend worker frontend
```

Minimum `.env` values:

- `BOT_TOKEN` and `ADMIN_IDS`.
- `WEBHOOK_BASE_URL`, `WEBHOOK_SECRET_TOKEN`, and `SUBSCRIPTION_MINI_APP_URL`.
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`.
- `WEBAPP_ENABLED=True` and a stable `WEBAPP_SESSION_SECRET`.
- `PANEL_API_URL`, `PANEL_API_KEY`, and `PANEL_WEBHOOK_SECRET`.

After the first admin login, finish tariffs, payment providers, appearance, support, and
installation-guide settings in the UI. See [docs/index.md](docs/index.md) for the full docs map.

## Contributor Map

The local and CI toolchain is Python 3.12 plus Node.js 22.

Run the aggregate gate before pushing:

```bash
make check
```

Start the local development stand with one command:

```bash
make dev
```

Without GNU Make, use the equivalent root command:

```bash
npm run check
```

The canonical gates from [CONTRIBUTING.md](CONTRIBUTING.md) section 1 are:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy --explicit-package-bases backend/config backend/db backend/bot/infra \
  backend/bot/middlewares backend/bot/utils \
  backend/bot/plugins backend/bot/keyboards backend/bot/payment_providers backend/bot/services \
  backend/bot/handlers backend/bot/app/factories backend/bot/app/controllers backend/bot/app/web \
  backend/main_backend.py backend/main_worker.py backend/scripts scripts tests
npm --prefix frontend run check
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
python scripts/check_architecture.py
```

Golden rules from section 2, in short:

- Regenerate generated artifacts instead of hand-editing them.
- Treat database migrations as append-only.
- Keep mypy green without silencing first-party code.
- Preserve wire contracts: the `{"ok": ...}` envelope, flat event payloads, and plugin subscriber
  signature `(event_name, dict)`.
- Keep first-party Svelte code in `frontend/src` on runes-only syntax.
- Decompose large modules before broadening type scope.
- Preserve compatibility with imports from older bots; it is a supported feature, not dead code.

Commits use English Conventional Commit subjects and no `Co-Authored-By` trailer.
