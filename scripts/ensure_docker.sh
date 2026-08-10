#!/bin/sh

set -eu

ASSUME_YES="${ASSUME_YES:-0}"
WAIT_SECONDS="${DOCKER_WAIT_SECONDS:-180}"

info() {
    printf '%s\n' "[setup] $*"
}

fail() {
    printf '%s\n' "[setup] ERROR: $*" >&2
    exit 1
}

run_as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        fail "Root privileges are required, but sudo is unavailable."
    fi
}

confirm() {
    if [ "$ASSUME_YES" = "1" ]; then
        return 0
    fi
    if [ ! -t 0 ]; then
        fail "Docker installation needs confirmation. Re-run interactively or use ASSUME_YES=1."
    fi
    printf '%s' "$1 [y/N] "
    read -r answer
    case "$answer" in
        y|Y|yes|YES) return 0 ;;
        *) fail "Docker installation cancelled." ;;
    esac
}

docker_daemon_ready() {
    docker info >/dev/null 2>&1 \
        || { command -v sudo >/dev/null 2>&1 \
            && sudo -n docker info >/dev/null 2>&1; }
}

wait_for_docker() {
    elapsed=0
    info "Waiting for the Docker daemon (up to ${WAIT_SECONDS}s)..."
    while [ "$elapsed" -lt "$WAIT_SECONDS" ]; do
        if docker_daemon_ready; then
            info "Docker daemon is ready."
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    fail "Docker daemon did not become ready. Start Docker and run 'make doctor'."
}

install_macos() {
    if ! command -v brew >/dev/null 2>&1; then
        fail "Homebrew is required for automatic setup. Install it from https://brew.sh, or install Docker Desktop from https://docs.docker.com/desktop/setup/install/mac-install/."
    fi

    confirm "Docker Desktop is not installed. Install it with Homebrew?"
    brew install --cask docker
}

start_macos() {
    if docker_daemon_ready; then
        return 0
    fi

    info "Starting Docker Desktop..."
    if docker desktop start >/dev/null 2>&1; then
        :
    elif command -v open >/dev/null 2>&1; then
        open -a Docker
    else
        fail "Docker Desktop is installed but could not be started."
    fi
    info "The first launch may require accepting Docker Desktop terms in the GUI."
}

install_linux_compose_plugin() {
    if docker compose version >/dev/null 2>&1; then
        return 0
    fi

    info "Installing the Docker Compose plugin..."
    if command -v apt-get >/dev/null 2>&1; then
        run_as_root apt-get update
        run_as_root apt-get install -y docker-compose-plugin
    elif command -v dnf >/dev/null 2>&1; then
        run_as_root dnf install -y docker-compose-plugin
    elif command -v yum >/dev/null 2>&1; then
        run_as_root yum install -y docker-compose-plugin
    else
        fail "Docker is installed, but the Compose plugin is missing. See https://docs.docker.com/compose/install/linux/."
    fi
}

install_linux() {
    command -v curl >/dev/null 2>&1 \
        || fail "curl is required to download Docker's official installer."
    if [ "$(id -u)" -ne 0 ] && ! command -v sudo >/dev/null 2>&1; then
        fail "sudo is required to install Docker Engine as a non-root user."
    fi

    confirm "Docker Engine is not installed. Run Docker's official development installer?"

    installer="$(mktemp "${TMPDIR:-/tmp}/policy-migrator-docker.XXXXXX")"
    trap 'rm -f "$installer"' EXIT HUP INT TERM
    curl -fsSL https://get.docker.com -o "$installer"
    run_as_root sh "$installer"
    rm -f "$installer"
    trap - EXIT HUP INT TERM

    if command -v systemctl >/dev/null 2>&1; then
        run_as_root systemctl enable --now docker
    fi

    if [ "$(id -u)" -ne 0 ] && command -v usermod >/dev/null 2>&1; then
        run_as_root usermod -aG docker "$(id -un)"
        info "Added $(id -un) to the docker group. A new login session will use Docker without sudo."
    fi
}

start_linux() {
    if docker_daemon_ready; then
        return 0
    fi
    if command -v systemctl >/dev/null 2>&1; then
        info "Starting Docker Engine..."
        run_as_root systemctl start docker
    fi
}

os="$(uname -s)"

case "$os" in
    Darwin)
        if ! command -v docker >/dev/null 2>&1; then
            install_macos
        fi
        start_macos
        ;;
    Linux)
        if ! command -v docker >/dev/null 2>&1; then
            install_linux
        fi
        install_linux_compose_plugin
        start_linux
        ;;
    *)
        fail "Automatic Docker setup supports macOS and Linux only (detected: $os)."
        ;;
esac

command -v docker >/dev/null 2>&1 \
    || fail "Docker CLI is still unavailable."
docker compose version >/dev/null 2>&1 \
    || fail "Docker Compose plugin is still unavailable."
wait_for_docker
