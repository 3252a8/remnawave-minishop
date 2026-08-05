PYTHON ?= python
NPM ?= npm
DEV_PRESET ?= 2.8.1

MYPY_PATHS := \
	backend/config \
	backend/db \
	backend/bot/infra \
	backend/bot/middlewares \
	backend/bot/utils \
	backend/bot/plugins \
	backend/bot/keyboards \
	backend/bot/payment_providers \
	backend/bot/services \
	backend/bot/handlers \
	backend/bot/app/factories \
	backend/bot/app/controllers \
	backend/bot/app/web \
	backend/main_backend.py \
	backend/main_worker.py \
	backend/scripts \
	scripts \
	tests

.PHONY: test lint types architecture front check cov dev dev-config dev-down dev-ps dev-logs

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

types:
	$(PYTHON) -m mypy --explicit-package-bases $(MYPY_PATHS)

architecture:
	$(PYTHON) scripts/check_architecture.py

front:
	$(NPM) --prefix frontend run check
	$(NPM) --prefix frontend run test
	$(NPM) --prefix frontend run build

check: test lint types architecture front

cov:
	$(PYTHON) -m pytest --cov=backend --cov-report=term-missing

dev:
	$(NPM) run dev:stand:use -- $(DEV_PRESET)
	$(NPM) run dev:stand:config
	$(NPM) run dev:stand:up

dev-config:
	$(NPM) run dev:stand:config

dev-down:
	$(NPM) run dev:stand:down

dev-ps:
	$(NPM) run dev:stand:ps

dev-logs:
	$(NPM) run dev:stand:logs
