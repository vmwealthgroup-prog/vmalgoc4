.PHONY: env up down logs test test-pg migrate revision fe-check backup
env:          ## generate .env with fresh secrets
	python scripts/init_env.py
up:           ## build and start everything (Postgres, Redis, API, worker, web, Caddy)
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs -f --tail=100 backend worker
test:         ## backend tests on SQLite
	cd backend && python -m pytest -q tests
migrate:      ## apply database migrations (the Docker image also does this on start)
	cd backend && alembic upgrade head
revision:     ## make a new migration after changing models:  make revision m="add column x"
	cd backend && alembic revision --autogenerate -m "$(m)"
fe-check:
	cd frontend && npx tsc --noEmit && npm run build
backup:       ## dump the database to backups/
	sh scripts/backup.sh
