.DEFAULT_GOAL := help

SHELL := /bin/sh

MODE ?= local
SERVICE ?= streamlit
SERVICES ?= streamlit
ASSUME_YES ?= 0
NO_CHECK ?= 0
TEST_PATH ?= tests
PYTEST_ARGS ?=

# Optional closed-stand hostname→IP mapping. Included only when both values
# are set in .env; otherwise containers get no extra_hosts at all.
CSP_HOSTS_COMPOSE := $(shell \
	if [ -f .env ]; then \
		hostname=$$(awk -F= '$$1 == "APP_SDWAN_CSP_HOSTNAME" { \
			value = substr($$0, index($$0, "=") + 1); \
			sub(/\r$$/, "", value); \
			print value; \
			exit; \
		}' .env); \
		host_ip=$$(awk -F= '$$1 == "APP_SDWAN_CSP_HOST_IP" { \
			value = substr($$0, index($$0, "=") + 1); \
			sub(/\r$$/, "", value); \
			print value; \
			exit; \
		}' .env); \
		if [ -n "$$hostname" ] && [ -n "$$host_ip" ]; then \
			printf '%s' '-f docker-compose.csp-hosts.yml'; \
		fi; \
	fi)

ifeq ($(MODE),local)
COMPOSE_FILES := -f docker-compose.yml -f docker-compose.local.yml $(CSP_HOSTS_COMPOSE)
else ifeq ($(MODE),prod)
COMPOSE_FILES := -f docker-compose.yml $(CSP_HOSTS_COMPOSE)
else
$(error Unsupported MODE='$(MODE)'. Use local or prod)
endif

# current shell may not yet see new docker-group membership, so fall back to a
# cached, non-interactive sudo session for this invocation.
DOCKER = $(shell \
	if docker info >/dev/null 2>&1; then \
		printf '%s' docker; \
	elif command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then \
		printf '%s' 'sudo docker'; \
	else \
		printf '%s' docker; \
	fi)

DC = $(DOCKER) compose $(COMPOSE_FILES)
TOOLS_DC = $(DOCKER) compose -f docker-compose.tools.yml
# Final images expose tools via /.venv/bin on PATH (no Poetry in runtime stages).
TOOLS_RUN = $(TOOLS_DC) run --rm --user "$(shell id -u):$(shell id -g)" tools

.PHONY: help doctor setup env-init ensure-docker tools-build \
	up down prod-up prod-down api-up api-down ps logs shell open \
	build restart rebuild config image-size smoke \
	format format-check lint typecheck test check \
	migrate migrate-down migrate-current migrate-history \
	migrate-create migrate-autogenerate migrate-stamp db-reset

##@ Getting started

help: ## Show commands, modes, and commonly used variables
	@printf '%s\n' "Policy Migrator developer commands"
	@printf '%s\n\n' "Usage: make <target> [VARIABLE=value]"
	@awk 'BEGIN {FS = ":.*## ";} \
		/^##@ / {printf "\n\033[1m%s\033[0m\n", substr($$0, 5); next} \
		/^[a-zA-Z0-9_.-]+:.*## / {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}' \
		$(MAKEFILE_LIST)
	@printf '%s\n' ""
	@printf '%s\n' "Common variables:"
	@printf '%s\n' "  SERVICE=streamlit|app    Service used by logs/shell (default: streamlit)"
	@printf '%s\n' "  SERVICES='streamlit app' Services used by build/restart/rebuild"
	@printf '%s\n' "  TEST_PATH=tests/...      Pytest path (default: tests)"
	@printf '%s\n' "  PYTEST_ARGS='-k name'    Additional pytest arguments"
	@printf '%s\n' "  ASSUME_YES=1             Allow non-interactive Docker installation"
	@printf '%s\n' "  NO_CHECK=1               Skip ensure-docker and doctor (advanced Docker setups)"
	@printf '%s\n' "  STREAMLIT_HOST_PORT      Streamlit host port from .env (default: 8501)"
	@printf '%s\n' "  API_HOST_PORT            FastAPI host port from .env (default: 8000)"

doctor: ## Diagnose Docker, database/CSP environment, and the PEM bundle
	@ENV_FILE=.env CERT_FILE=client_cert.pem ./scripts/doctor.sh

env-init: ## Create .env from .env.example without overwriting an existing file
	@if [ -e .env ]; then \
		printf '%s\n' "[setup] .env already exists; leaving it unchanged."; \
	else \
		cp .env.example .env; \
		printf '%s\n' "[setup] Created .env from .env.example."; \
		printf '%s\n' "[setup] Review CSP URL, username, password, VPC ID, and optional HOSTNAME/HOST_IP in .env."; \
	fi

ensure-docker: ## Install/start Docker on supported macOS or Linux hosts
	@ASSUME_YES="$(ASSUME_YES)" ./scripts/ensure_docker.sh

setup: ## Prepare .env; unless NO_CHECK=1, also ensure Docker and run doctor
	@$(MAKE) --no-print-directory env-init
	@if [ "$(NO_CHECK)" = "1" ]; then \
		printf '%s\n' "[setup] NO_CHECK=1: skipping ensure-docker and doctor."; \
	else \
		$(MAKE) --no-print-directory ensure-docker ASSUME_YES="$(ASSUME_YES)"; \
		$(MAKE) --no-print-directory doctor; \
	fi

##@ Local stack

up: setup ## Build and start PostgreSQL + Streamlit, migrate DB, and print the URL
	@$(DC) build streamlit
	@$(DC) up -d --wait --remove-orphans postgres
	@$(MAKE) --no-print-directory migrate MODE="$(MODE)"
	@$(DC) up -d --wait --remove-orphans streamlit
	@host_port="$$( \
		$(DC) port streamlit 8501 | head -n 1 | awk -F: '{print $$NF}' \
	)"; \
	printf '\n%s\n' "Streamlit is ready: http://localhost:$$host_port"

down: ## Stop the local stack and keep database data
	@$(DC) down

ps: ## Show service and health status
	@$(DC) ps

logs: ## Follow logs (default: SERVICE=streamlit)
	@$(DC) logs --tail=200 -f "$(SERVICE)"

shell: ## Open a shell in a running service (default: SERVICE=streamlit)
	@$(DC) exec "$(SERVICE)" sh

open: ## Open Streamlit in the default browser when supported
	@host_port="$$( \
		$(DC) port streamlit 8501 | head -n 1 | awk -F: '{print $$NF}' \
	)"; \
	test -n "$$host_port" || { \
		printf '%s\n' "Streamlit is not running. Run 'make up' first."; \
		exit 1; \
	}; \
	url="http://localhost:$$host_port"; \
	printf '%s\n' "$$url"; \
	if command -v open >/dev/null 2>&1; then \
		open "$$url"; \
	elif command -v xdg-open >/dev/null 2>&1; then \
		xdg-open "$$url"; \
	else \
		printf '%s\n' "Open the URL above in a browser."; \
	fi

api-up: setup ## Start postgres, migrate, then the optional FastAPI service
	@$(DC) --profile api build app
	@$(DC) up -d --wait --remove-orphans postgres
	@$(MAKE) --no-print-directory migrate MODE="$(MODE)"
	@$(DC) --profile api up -d --wait --remove-orphans app
	@host_port="$$( \
		$(DC) --profile api port app 8000 | head -n 1 | awk -F: '{print $$NF}' \
	)"; \
	printf '%s\n' "FastAPI is ready: http://localhost:$$host_port"

api-down: ## Stop the optional FastAPI service
	@$(DC) --profile api stop app

##@ Prod-like stack

prod-up: ## Start the immutable prod-like PostgreSQL + Streamlit stack
	@$(MAKE) --no-print-directory up MODE=prod ASSUME_YES="$(ASSUME_YES)" NO_CHECK="$(NO_CHECK)"

prod-down: ## Stop the prod-like stack and keep database data
	@$(MAKE) --no-print-directory down MODE=prod

##@ Images and runtime

build: ## Build images (default: SERVICES=streamlit)
	@$(DC) build $(SERVICES)

restart: ## Restart services without rebuilding
	@$(DC) restart $(SERVICES)

rebuild: ## Rebuild and force-recreate services
	@$(DC) build $(SERVICES)
	@$(DC) up -d --force-recreate $(SERVICES)

config: ## Render the fully merged Compose configuration
	@$(DC) config

image-size: ## Show Compose image names and sizes
	@printf '%-42s %-10s %s\n' "IMAGE" "SIZE" "IMAGE ID"
	@for image in \
		policy-migrator-streamlit:runtime \
		policy-migrator-streamlit:dev \
		policy-migrator-api:runtime \
		policy-migrator-api:dev; do \
		if $(DOCKER) image inspect "$$image" >/dev/null 2>&1; then \
			$(DOCKER) image ls --format \
				'{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.ID}}' "$$image"; \
		else \
			printf '%-42s %s\n' "$$image" "not built"; \
		fi; \
	done

smoke: ## Check PostgreSQL readiness and Streamlit health
	@$(DC) exec -T postgres sh -ec \
		'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' >/dev/null
	@host_port="$$( \
		$(DC) port streamlit 8501 | head -n 1 | awk -F: '{print $$NF}' \
	)"; \
	curl -fsS "http://localhost:$$host_port/_stcore/health" >/dev/null
	@printf '%s\n' "Smoke checks passed (postgres + streamlit)."

##@ Code quality (manual/CI; never run by make up)

tools-build:
	@$(TOOLS_DC) build tools

format: tools-build ## Format Python code with Ruff
	@$(TOOLS_RUN) ruff format src tests

format-check: tools-build ## Verify Ruff formatting without changing files
	@$(TOOLS_RUN) ruff format --check src tests

lint: tools-build ## Run Ruff lint checks
	@$(TOOLS_RUN) ruff check .

typecheck: tools-build ## Run mypy static type checks
	@$(TOOLS_RUN) mypy .

test: tools-build ## Run pytest (supports TEST_PATH and PYTEST_ARGS)
	@$(TOOLS_RUN) pytest $(PYTEST_ARGS) $(TEST_PATH)

check: lint format-check typecheck test ## Run the complete code-quality suite

##@ Database migrations

migrate: ## Upgrade the database to the latest Alembic revision
	@$(DC) run --rm streamlit alembic upgrade head

migrate-current: ## Show the current Alembic revision
	@$(DC) run --rm streamlit alembic current

migrate-history: ## Show Alembic migration history
	@$(DC) run --rm streamlit alembic history

DOWN ?= 1
migrate-down: ## Downgrade Alembic revisions (requires CONFIRM=1)
	@test "$(CONFIRM)" = "1" || { \
		printf '%s\n' "Refusing migration downgrade. Re-run with CONFIRM=1."; \
		exit 1; \
	}
	@$(DC) run --rm streamlit alembic downgrade "-$(DOWN)"

MSG ?=
migrate-create: ## Create an empty revision (requires MSG='description')
	@test -n "$(MSG)" || { \
		printf '%s\n' "MSG is required, e.g. make migrate-create MSG='add table foo'"; \
		exit 1; \
	}
	@$(DC) run --rm streamlit alembic revision -m "$(MSG)"

migrate-autogenerate: ## Autogenerate a revision (requires MSG='description')
	@test -n "$(MSG)" || { \
		printf '%s\n' "MSG is required, e.g. make migrate-autogenerate MSG='add table foo'"; \
		exit 1; \
	}
	@$(DC) run --rm streamlit alembic revision --autogenerate -m "$(MSG)"

REV ?= head
migrate-stamp: ## Stamp the database without running migrations (requires CONFIRM=1)
	@test "$(CONFIRM)" = "1" || { \
		printf '%s\n' "Refusing to stamp the database. Re-run with CONFIRM=1."; \
		exit 1; \
	}
	@$(DC) run --rm streamlit alembic stamp "$(REV)"

db-reset: ## Delete PostgreSQL data and recreate the stack (requires CONFIRM=1)
	@test "$(CONFIRM)" = "1" || { \
		printf '%s\n' "Refusing to delete database data. Re-run with CONFIRM=1."; \
		exit 1; \
	}
	@$(DC) down -v
	@$(MAKE) --no-print-directory up MODE="$(MODE)" ASSUME_YES="$(ASSUME_YES)" NO_CHECK="$(NO_CHECK)"
