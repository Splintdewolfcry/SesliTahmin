.PHONY: install dev-backend test lint

install:
	cd backend && uv sync --extra dev

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .
