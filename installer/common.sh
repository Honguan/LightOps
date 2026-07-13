#!/usr/bin/env bash
set -Eeuo pipefail

LIGHTOPS_ROOT="${LIGHTOPS_ROOT:-/opt/lightops}"
CONFIG_DIR="${LIGHTOPS_CONFIG_DIR:-/etc/lightops}"
DATA_DIR="${LIGHTOPS_DATA_DIR:-/var/lib/lightops}"
LOG_DIR="${LIGHTOPS_LOG_DIR:-/var/log/lightops}"
BACKUP_DIR="${LIGHTOPS_BACKUP_DIR:-/var/backups/lightops}"
SERVICE_NAME="lightops"
TRANSITION_LOCK_FILE="${LIGHTOPS_TRANSITION_LOCK:-/run/lock/lightops-transition.lock}"

load_config() {
  local line
  [[ -r "$CONFIG_DIR/lightops.env" ]] || return 0
  while IFS= read -r line; do
    [[ "$line" =~ ^(LIGHTOPS_[A-Z0-9_]+|AUTO_UPDATE|UPDATE_CHANNEL)= ]] && export "$line"
  done < "$CONFIG_DIR/lightops.env"
  DATA_DIR="${LIGHTOPS_DATA_DIR:-$DATA_DIR}"
  LOG_DIR="${LIGHTOPS_LOG_DIR:-$LOG_DIR}"
  BACKUP_DIR="${LIGHTOPS_BACKUP_DIR:-$BACKUP_DIR}"
  TRANSITION_LOCK_FILE="${LIGHTOPS_TRANSITION_LOCK:-$TRANSITION_LOCK_FILE}"
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

acquire_transition_lock() {
  mkdir -p "$(dirname "$TRANSITION_LOCK_FILE")"
  exec {TRANSITION_LOCK_FD}>"$TRANSITION_LOCK_FILE"
  if ! flock -n "$TRANSITION_LOCK_FD"; then
    echo "Another LightOps release transition is already in progress." >&2
    return 1
  fi
}

health_check() {
  local deadline=$((SECONDS + 30))
  local remaining
  while ((SECONDS < deadline)); do
    remaining=$((deadline - SECONDS))
    if curl -fsS --max-time "$remaining" http://127.0.0.1:9080/api/health >/dev/null; then
      return 0
    fi
    ((SECONDS >= deadline)) || sleep 1
  done
  return 1
}

restore_transition() {
  local previous_release="$1"
  local database_backup="$2"
  local failed=false
  systemctl stop "$SERVICE_NAME" || true
  if [[ -n "$database_backup" ]]; then
    rm -f "$DATA_DIR/lightops.db-wal" "$DATA_DIR/lightops.db-shm"
    if ! cp -p "$database_backup" "$DATA_DIR/lightops.db" || ! chown lightops:lightops "$DATA_DIR/lightops.db"; then
      echo "LightOps database restoration failed." >&2
      failed=true
    fi
  fi
  if [[ -n "$previous_release" ]]; then
    if ! atomic_link "$previous_release" "$LIGHTOPS_ROOT/current" || ! systemctl restart "$SERVICE_NAME" || ! health_check; then
      echo "Previous LightOps release could not be verified after restoration." >&2
      failed=true
    fi
  else
    rm -f "$LIGHTOPS_ROOT/current"
  fi
  [[ "$failed" == false ]]
}

transition_release() {
  local mode="$1"
  local target_version="$2"
  local target_release="$LIGHTOPS_ROOT/releases/$target_version"
  local previous_release=""
  local current_version="none"
  local database_backup=""
  local migration_plan="[]"
  local migrator="$target_release/venv/bin/lightops-migrate"
  local configure_service=false
  local enforce_update_policy=false
  local run_migrations=true

  case "$mode" in
    install) configure_service=true ;;
    update) enforce_update_policy=true ;;
    rollback) run_migrations=false ;;
    *) echo "Invalid release transition mode: $mode" >&2; return 2 ;;
  esac
  [[ -d "$target_release" ]] || { echo "Release $target_version is unavailable." >&2; return 1; }
  if [[ -L "$LIGHTOPS_ROOT/current" ]]; then
    previous_release="$(readlink -f "$LIGHTOPS_ROOT/current" || true)"
    [[ -n "$previous_release" ]] && current_version="$(basename "$previous_release")"
  fi

  if [[ "$run_migrations" == true ]]; then
    [[ -x "$migrator" ]] || { echo "Release $target_version has no migration command." >&2; return 1; }
    if ! migration_plan="$($migrator plan)"; then
      echo "Database migration plan failed; the current version was not changed." >&2
      return 1
    fi
    if [[ "$enforce_update_policy" == true ]] && grep -q '"reversible": false' <<<"$migration_plan"; then
      echo "Release contains an irreversible migration and requires a manual procedure." >&2
      return 1
    fi
    if [[ "$enforce_update_policy" == true && -n "${LIGHTOPS_DATABASE_URL:-}" && "$migration_plan" != "[]" ]]; then
      echo "External database migrations require a manual backup and release procedure." >&2
      return 1
    fi
  fi

  if [[ "$configure_service" == true ]]; then
    if ! systemctl daemon-reload || ! systemctl enable "$SERVICE_NAME"; then
      echo "Could not configure the LightOps service." >&2
      return 1
    fi
  fi
  if ! systemctl stop "$SERVICE_NAME"; then
    echo "Could not stop LightOps before the release transition." >&2
    return 1
  fi
  if [[ "$run_migrations" == true ]]; then
    if [[ -f "$DATA_DIR/lightops.db" ]]; then
      mkdir -p "$BACKUP_DIR"
      database_backup="$BACKUP_DIR/pre-$mode-$current_version-$(date -u +%Y%m%dT%H%M%SZ).db"
      if ! python3 - "$DATA_DIR/lightops.db" "$database_backup" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as source, sqlite3.connect(sys.argv[2]) as target:
    source.backup(target)
PY
      then
        echo "Database backup failed; restoring the previous release." >&2
        restore_transition "$previous_release" "" || true
        return 1
      fi
    fi
    if ! "$migrator" up; then
      echo "Database migration failed; restoring the previous release." >&2
      restore_transition "$previous_release" "$database_backup" || true
      return 1
    fi
    if ! chown -R lightops:lightops "$DATA_DIR"; then
      echo "Could not set data ownership; restoring the previous release." >&2
      restore_transition "$previous_release" "$database_backup" || true
      return 1
    fi
  fi

  if ! atomic_link "$target_release" "$LIGHTOPS_ROOT/current"; then
    echo "Could not activate release $target_version; restoring the previous release." >&2
    restore_transition "$previous_release" "$database_backup" || true
    return 1
  fi
  if systemctl start "$SERVICE_NAME" && health_check; then
    prune_releases || echo "LightOps release pruning failed." >&2
    return 0
  fi

  echo "Release $target_version failed its health check; restoring the previous release." >&2
  restore_transition "$previous_release" "$database_backup" || true
  return 1
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
