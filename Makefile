.PHONY: install dev-backend dev-frontend dev test lint

install:
	cd backend && uv sync --extra dev
	cd frontend && npm install

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

dev:
	$(MAKE) dev-backend & $(MAKE) dev-frontend &

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .