# =============================================================================
# NHS Elective Flow Intelligence
# =============================================================================
# Quick start:
#   make setup    install backend and frontend dependencies
#   make data     ingest official NHS England data and build the warehouse
#   make dev      run backend and frontend together
# =============================================================================

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-frontend data data-offline demo \
        validate dev dev-backend dev-frontend build test test-backend lint \
        lint-backend lint-frontend typecheck check clean clean-data \
        docker-up docker-down

# Cross-platform virtualenv paths (Windows uses Scripts/, POSIX uses bin/).
ifeq ($(OS),Windows_NT)
	VENV_BIN := .venv/Scripts
	PY       := python
else
	VENV_BIN := .venv/bin
	PY       := python3
endif

PYTHON := $(VENV_BIN)/python

help: ## Show this help
	@echo ""
	@echo "  NHS Elective Flow Intelligence"
	@echo "  ------------------------------------------------------------"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""

# --- Setup -------------------------------------------------------------------
setup: setup-backend setup-frontend ## Install all dependencies
	@echo ""
	@echo "Setup complete. Next: make data (official) or make demo (synthetic)."

setup-backend: ## Create the Python venv and install backend dependencies
	$(PY) -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r backend/requirements.txt

setup-frontend: ## Install frontend dependencies
	cd frontend && npm install

# --- Data --------------------------------------------------------------------
data: ## Ingest official NHS England RTT data and build the warehouse
	$(PYTHON) scripts/build_warehouse.py --months 18

data-offline: ## Rebuild the warehouse from workbooks already in data/raw
	$(PYTHON) scripts/build_warehouse.py --offline --months 18

download: ## Download source files only (no warehouse build)
	$(PYTHON) scripts/download_data.py --months 18

discover: ## List the source files discovery finds, without downloading
	$(PYTHON) scripts/download_data.py --dry-run

demo: ## Build the warehouse from the labelled synthetic demo dataset
	$(PYTHON) scripts/build_warehouse.py --demo

validate: ## Validate the built warehouse
	$(PYTHON) scripts/validate_data.py

# --- Development -------------------------------------------------------------
dev: ## Run backend and frontend together
	@echo "Backend  -> http://localhost:8000  (docs at /docs)"
	@echo "Frontend -> http://localhost:3000"
	@$(MAKE) -j2 dev-backend dev-frontend

dev-backend: ## Run the FastAPI backend with reload
	cd backend && ../$(PYTHON) -m uvicorn app.main:app --reload --port 8000

dev-frontend: ## Run the Next.js dev server
	cd frontend && npm run dev

build: ## Build the frontend for production
	cd frontend && npm run build

start: ## Serve the production frontend build
	cd frontend && npm run start

# --- Quality -----------------------------------------------------------------
test: test-backend ## Run all tests

test-backend: ## Run the backend test suite
	cd backend && ../$(PYTHON) -m pytest

lint: lint-backend lint-frontend ## Lint everything

lint-backend: ## Lint Python with ruff
	cd backend && ../$(PYTHON) -m ruff check .

lint-fix: ## Auto-fix Python lint findings
	cd backend && ../$(PYTHON) -m ruff check . --fix

lint-frontend: ## Lint the frontend with ESLint
	cd frontend && npm run lint

typecheck: ## Type-check the frontend
	cd frontend && npm run typecheck

check: lint typecheck test ## Run every quality gate

# --- Docker ------------------------------------------------------------------
docker-up: ## Build and start the full stack in Docker
	docker compose up --build

docker-down: ## Stop the Docker stack
	docker compose down

# --- Housekeeping ------------------------------------------------------------
clean: ## Remove build artefacts and caches
	-rm -rf backend/.pytest_cache backend/.ruff_cache
	-rm -rf frontend/.next frontend/out
	-find . -type d -name __pycache__ -prune -exec rm -rf {} +

clean-data: ## Remove downloaded and processed data (forces a full re-ingest)
	-rm -rf data/raw/* data/processed/*
