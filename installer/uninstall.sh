#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
PURGE=false
CONFIRMED=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge) PURGE=true; shift ;;
    --yes) CONFIRMED=true; shift ;;
    --help) echo "Usage: sudo lightops uninstall [--purge] [--yes]"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
require_root
if ! $CONFIRMED; then
  [[ -t 0 ]] || { echo "Use --yes for non-interactive removal." >&2; exit 2; }
  read -r -p "Type REMOVE to uninstall LightOps: " answer
  [[ "$answer" == "REMOVE" ]] || { echo "Removal cancelled."; exit 1; }
fi
systemctl disable --now lightops 2>/dev/null || true
rm -f /etc/systemd/system/lightops.service /etc/sudoers.d/lightops /usr/local/bin/lightops
systemctl daemon-reload
rm -rf "$LIGHTOPS_ROOT"
if $PURGE; then
  rm -rf "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR" "$BACKUP_DIR"
  userdel lightops 2>/dev/null || true
  echo "LightOps and all data were removed."
else
  echo "LightOps was removed; configuration, data, logs, and backups were preserved."
fi
