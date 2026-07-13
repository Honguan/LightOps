#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE_DIR="$(cd "$2" && pwd)"; shift 2 ;;
    --help) echo "Usage: sudo bash installer/install.sh [--source DIR]"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

require_root
load_os
mkdir -p "$LOG_DIR"
touch "$LOG_DIR/install.log"
exec > >(tee -a "$LOG_DIR/install.log") 2>&1
trap 'echo "Installation failed at line $LINENO." >&2' ERR

available_kb="$(df -Pk /opt | awk 'NR==2 {print $4}')"
[[ "$available_kb" -ge 524288 ]] || { echo "At least 512 MB of free disk space is required." >&2; exit 1; }
echo "Installing LightOps on $ID ($ARCH)..."
$PACKAGE_MANAGER update
DEBIAN_FRONTEND=noninteractive $PACKAGE_MANAGER install -y python3 python3-venv python3-pip curl ca-certificates sudo tar

getent passwd lightops >/dev/null || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin lightops
install -d -o root -g root -m 0755 "$LIGHTOPS_ROOT" "$LIGHTOPS_ROOT/releases" "$CONFIG_DIR"
install -d -o lightops -g lightops -m 0750 "$DATA_DIR" "$LOG_DIR" "$BACKUP_DIR"

VERSION="$(tr -d '[:space:]' < "$SOURCE_DIR/VERSION")"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Invalid VERSION file." >&2; exit 1; }
install_release "$SOURCE_DIR" "$VERSION"
release_dir="$LIGHTOPS_ROOT/releases/$VERSION"
if [[ ! -f "$release_dir/frontend/dist/index.html" ]]; then
  DEBIAN_FRONTEND=noninteractive $PACKAGE_MANAGER install -y nodejs npm
  npm --prefix "$release_dir/frontend" install --no-audit --no-fund
  npm --prefix "$release_dir/frontend" run build
fi
"$release_dir/venv/bin/lightops-migrate" up

if [[ ! -f "$CONFIG_DIR/lightops.env" ]]; then
  install -m 0640 -o root -g lightops "$SOURCE_DIR/systemd/lightops.env" "$CONFIG_DIR/lightops.env"
fi
if [[ ! -f "$CONFIG_DIR/secret.key" ]]; then
  "$release_dir/venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' > "$CONFIG_DIR/secret.key"
  chown root:lightops "$CONFIG_DIR/secret.key"
  chmod 0640 "$CONFIG_DIR/secret.key"
fi
install -m 0644 "$SOURCE_DIR/systemd/lightops.service" /etc/systemd/system/lightops.service
install -m 0440 "$SOURCE_DIR/systemd/lightops.sudoers" /etc/sudoers.d/lightops
visudo -cf /etc/sudoers.d/lightops
atomic_link "$LIGHTOPS_ROOT/releases/$VERSION" "$LIGHTOPS_ROOT/current"
ln -sfn "$LIGHTOPS_ROOT/current/venv/bin/lightops" /usr/local/bin/lightops
systemctl daemon-reload
systemctl enable --now lightops
health_check || { journalctl -u lightops -n 50 --no-pager; exit 1; }
prune_releases

echo "LightOps $VERSION installed successfully."
echo "Management URL: http://$(hostname -I | awk '{print $1}'):9080"
echo "Administrator account: admin (set the password on first login)"
echo "Run: sudo lightops reset-password"
