#!/bin/sh

set -u

ENV_FILE="${ENV_FILE:-.env}"
errors=0
warnings=0

ok() {
    printf '%s\n' "[doctor] OK: $*"
}

warn() {
    warnings=$((warnings + 1))
    printf '%s\n' "[doctor] WARN: $*"
}

error() {
    errors=$((errors + 1))
    printf '%s\n' "[doctor] ERROR: $*" >&2
}

env_value() {
    key="$1"
    awk -F= -v key="$key" '
        $1 == key {
            value = substr($0, index($0, "=") + 1)
            sub(/\r$/, "", value)
            print value
            exit
        }
    ' "$ENV_FILE"
}

require_env() {
    key="$1"
    hint="$2"
    value="$(env_value "$key")"
    if [ -z "$value" ]; then
        error "$key is missing or empty. $hint"
    else
        ok "$key is configured."
    fi
}

if command -v docker >/dev/null 2>&1; then
    ok "Docker CLI is installed."
else
    error "Docker CLI is missing. Run 'make setup'."
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    ok "Docker Compose plugin is installed."
else
    error "Docker Compose plugin is missing. Run 'make setup'."
fi

if command -v docker >/dev/null 2>&1 \
    && { docker info >/dev/null 2>&1 || sudo -n docker info >/dev/null 2>&1; }; then
    ok "Docker daemon is reachable."
else
    error "Docker daemon is not reachable. Start Docker Desktop/Engine, then retry."
fi

if [ -f "$ENV_FILE" ]; then
    ok "$ENV_FILE exists."

    require_env \
        "PYTHON_IMAGE" \
        "Docker image for python service should be set."
    require_env \
        "POSTGRES_IMAGE" \
        "Docker image for postgres service should be set."

    require_env \
        "APP_DB_HOST" \
        "Use postgres for the bundled Compose database."
    require_env \
        "APP_DB_PORT" \
        "Use 5432 for the bundled Compose database."
    require_env \
        "APP_DB_USER" \
        "Set the PostgreSQL user."
    require_env \
        "APP_DB_PASSWORD" \
        "Set the PostgreSQL password."
    require_env \
        "APP_DB_NAME" \
        "Set the PostgreSQL database name."

    if [ -n "$(env_value "APP_DATABASE_URL")" ]; then
        warn "APP_DATABASE_URL is not used by the legacy release settings. Configure APP_DB_HOST, APP_DB_PORT, APP_DB_USER, APP_DB_PASSWORD, and APP_DB_NAME instead."
    fi

    hostname="$(env_value "APP_SDWAN_CSP_HOSTNAME")"
    host_ip="$(env_value "APP_SDWAN_CSP_HOST_IP")"
    if [ -n "$hostname" ] && [ -n "$host_ip" ]; then
        ok "APP_SDWAN_CSP_HOSTNAME/APP_SDWAN_CSP_HOST_IP set; Make will include docker-compose.csp-hosts.yml (${hostname} -> ${host_ip})."
    elif [ -n "$hostname" ] || [ -n "$host_ip" ]; then
        error "Set both APP_SDWAN_CSP_HOSTNAME and APP_SDWAN_CSP_HOST_IP together, or leave both empty for normal DNS."
    else
        ok "APP_SDWAN_CSP_HOSTNAME/APP_SDWAN_CSP_HOST_IP are empty; no Compose extra_hosts overlay."
    fi
else
    error "$ENV_FILE is missing. Run 'make env-init' or 'make setup'."
fi

printf '%s\n' "[doctor] Result: $errors error(s), $warnings warning(s)."
[ "$errors" -eq 0 ]
