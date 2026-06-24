PYTHON ?= python
NPM ?= npm

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
	backend/bot/app/web

.PHONY: test lint types front check cov

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

types:
	$(PYTHON) -m mypy $(MYPY_PATHS)

front:
	$(NPM) --prefix frontend run check
	$(NPM) --prefix frontend run test
	$(NPM) --prefix frontend run build

check: test lint types front

cov:
	$(PYTHON) -m pytest --cov=backend --cov-report=term-missing
