# Gadziriro AI Workspace — dev tasks. Use `uv`/`py`; never bare `python`.
.PHONY: install test lint fmt serve ui-install ui-build ui-dev clean

install:
	cd backend && uv venv --python 3.11 && uv pip install -r requirements-dev.txt

test:
	cd backend && .venv/Scripts/python -m pytest -q || cd backend && .venv/bin/python -m pytest -q

lint:
	cd backend && .venv/Scripts/python -m ruff check gadziriro tests || cd backend && .venv/bin/python -m ruff check gadziriro tests

fmt:
	cd backend && .venv/Scripts/python -m black gadziriro tests && .venv/Scripts/python -m isort gadziriro tests

serve:
	cd backend && .venv/Scripts/python -m uvicorn gadziriro.gateway.app:app --host 127.0.0.1 --port 8080

ui-install:
	cd frontend && npm ci

ui-build:
	cd frontend && npm run build

ui-dev:
	cd frontend && npm run dev

clean:
	rm -rf backend/.venv backend/.pytest_cache frontend/node_modules frontend/dist
