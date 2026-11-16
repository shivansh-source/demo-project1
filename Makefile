PY ?= python

.PHONY: up down db migrate api worker frontend test lint typecheck fmt

up:            ## start db, api, worker
	docker compose up -d --build --wait db
	docker compose up -d --build api worker

down:
	docker compose down

db:            ## start only Postgres and wait until healthy
	docker compose up -d --wait db

migrate:
	$(PY) -m alembic upgrade head

api:
	$(PY) -m uvicorn app.main:app --reload

worker:
	$(PY) -m app.worker

frontend:      ## React dev server on :5173 (proxies /api to :8000)
	cd frontend && npm install && npm run dev

lint:
	$(PY) -m ruff check .

typecheck:
	$(PY) -m mypy

fmt:
	$(PY) -m ruff format .

# Starts Postgres, then runs everything (unit + integration) with coverage on app/services.
# Set SKIP_DB=1 if you already have Postgres reachable at TEST_DATABASE_URL.
test:
ifndef SKIP_DB
	docker compose up -d --wait db
endif
	$(PY) -m pytest --cov=app --cov-report=term-missing
