#!/bin/sh

set -u

ENV_FILE="${ENV_FILE:-.env}"
CERT_FILE="${CERT_FILE:-client_cert.pem}"
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

    require_env \
        "APP_SDWAN_CSP_API_URL" \
        "Set the CSP base URL, for example https://your-csp-host.example.com."
    require_env \
        "APP_SDWAN_CSP_CERT" \
        "Use /app/client_cert.pem for the Compose-mounted certificate."
    require_env \
        "APP_SDWAN_CSP_USERNAME" \
        "Set the CSP administrator username."
    require_env \
        "APP_SDWAN_CSP_PASSWORD" \
        "Set the CSP administrator password."

    if [ -z "$(env_value "APP_SDWAN_VPC_ID")" ]; then
        warn "APP_SDWAN_VPC_ID is empty. Configure it before mapping or executing rules."
    else
        ok "APP_SDWAN_VPC_ID is configured."
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

if [ -f "$CERT_FILE" ]; then
    ok "$CERT_FILE exists."
    if grep -q -- "BEGIN CERTIFICATE" "$CERT_FILE"; then
        ok "$CERT_FILE contains a certificate."
    else
        error "$CERT_FILE does not contain a PEM certificate block."
    fi
    if grep -Eq -- "BEGIN (RSA |EC |ENCRYPTED )?PRIVATE KEY" "$CERT_FILE"; then
        ok "$CERT_FILE contains a private key."
    else
        error "$CERT_FILE must contain the matching private key in the same PEM bundle."
    fi
else
    error "$CERT_FILE is missing. Put the combined client certificate/private-key PEM at ./$CERT_FILE."
fi

printf '%s\n' "[doctor] Result: $errors error(s), $warnings warning(s)."
[ "$errors" -eq 0 ]
