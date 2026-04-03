.PHONY: help up down ps logs build restart smoke verify-release

help:
	@echo "Targets:"
	@echo "  make up        - build + start stack (uses env.example)"
	@echo "  make down      - stop stack"
	@echo "  make ps        - list containers"
	@echo "  make logs      - tail logs"
	@echo "  make build     - build images"
	@echo "  make restart   - restart stack"
	@echo "  make migrate   - run alembic migrations in api container"
	@echo "  make seed      - seed dev data in api container"
	@echo "  make test-api  - run api tests in api container"
	@echo "  make smoke     - run basic health smoke checks"
	@echo "  make verify-release - build and run prod-profile smoke checks"

up:
	docker compose --env-file env.example up --build -d

down:
	docker compose --env-file env.example down

ps:
	docker compose --env-file env.example ps

logs:
	docker compose --env-file env.example logs -f --tail=200

build:
	docker compose --env-file env.example build

restart:
	docker compose --env-file env.example down
	docker compose --env-file env.example up --build -d

migrate:
	docker compose --env-file env.example exec api alembic -c alembic.ini upgrade head

seed:
	docker compose --env-file env.example exec api python -m app.cli.seed

test-api:
	docker compose --env-file env.example exec -e PYTHONPATH=/app api pytest -q

smoke:
	@echo "Checking container status..."
	docker compose --env-file env.example ps
	@echo "Checking API health..."
	curl -fsS http://localhost:8000/health

verify-release:
	@echo "Starting production-profile stack..."
	APP_RUNTIME_PROFILE=prod docker compose --env-file env.example up --build -d
	@echo "Running migrations..."
	APP_RUNTIME_PROFILE=prod docker compose --env-file env.example exec -T api alembic -c alembic.ini upgrade head
	@echo "Checking API health..."
	curl -fsS http://localhost:8000/health
	@echo "Checking web root..."
	curl -fsS http://localhost:3000 > /dev/null
	@echo "Stopping production-profile stack..."
	APP_RUNTIME_PROFILE=prod docker compose --env-file env.example down -v
	@echo "Release-profile verification complete."

