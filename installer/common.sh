#!/usr/bin/env bash
set -Eeuo pipefail

LIGHTOPS_ROOT="${LIGHTOPS_ROOT:-/opt/lightops}"
CONFIG_DIR="${LIGHTOPS_CONFIG_DIR:-/etc/lightops}"
DATA_DIR="${LIGHTOPS_DATA_DIR:-/var/lib/lightops}"
LOG_DIR="${LIGHTOPS_LOG_DIR:-/var/log/lightops}"
BACKUP_DIR="${LIGHTOPS_BACKUP_DIR:-/var/backups/lightops}"
SERVICE_NAME="lightops"

load_config() {
  local line
  [[ -r "$CONFIG_DIR/lightops.env" ]] || return 0
  while IFS= read -r line; do
    [[ "$line" =~ ^(LIGHTOPS_[A-Z0-9_]+|AUTO_UPDATE|UPDATE_CHANNEL)= ]] && export "$line"
  done < "$CONFIG_DIR/lightops.env"
  DATA_DIR="${LIGHTOPS_DATA_DIR:-$DATA_DIR}"
  LOG_DIR="${LIGHTOPS_LOG_DIR:-$LOG_DIR}"
  BACKUP_DIR="${LIGHTOPS_BACKUP_DIR:-$BACKUP_DIR}"
}

require_root() {
  if [[ ${EUID} -ne 0 ]]; then
    echo "This command must run as root (use sudo)." >&2
    exit 1
  fi
}

load_os() {
  [[ -r /etc/os-release ]] || { echo "Cannot detect the operating system." >&2; exit 1; }
  # shellcheck disable=SC1091
  source /etc/os-release
  case "${ID:-}" in
    ubuntu|debian) PACKAGE_MANAGER="apt-get" ;;
    *) echo "Unsupported operating system: ${ID:-unknown}. MVP supports Ubuntu and Debian." >&2; exit 1 ;;
  esac
  case "$(uname -m)" in
    x86_64|amd64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "Unsupported CPU architecture: $(uname -m)." >&2; exit 1 ;;
  esac
}

atomic_link() {
  local target="$1" link="$2" temporary="${2}.new"
  ln -sfn "$target" "$temporary"
  mv -Tf "$temporary" "$link"
}

health_check() {
  curl -fsS --max-time 10 http://127.0.0.1:9080/api/health >/dev/null
}

install_release() {
  local source_dir="$1"
  local version="$2"
  local release_dir="$LIGHTOPS_ROOT/releases/$version"
  if [[ ! -d "$release_dir" ]]; then
    mkdir -p "$release_dir"
    tar -C "$source_dir" --exclude=.git --exclude=node_modules --exclude=__pycache__ --exclude=.pytest_cache -cf - . | tar -C "$release_dir" -xf -
  fi
  if [[ ! -x "$release_dir/venv/bin/python" ]]; then
    python3 -m venv "$release_dir/venv"
  fi
  "$release_dir/venv/bin/pip" install --disable-pip-version-check --no-cache-dir "$release_dir"
  chown -R root:root "$release_dir"
}

prune_releases() {
  mapfile -t releases < <(find "$LIGHTOPS_ROOT/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -Vr)
  for release in "${releases[@]:3}"; do
    [[ "$LIGHTOPS_ROOT/releases/$release" == "$(readlink -f "$LIGHTOPS_ROOT/current")" ]] || rm -rf "$LIGHTOPS_ROOT/releases/$release"
  done
}
