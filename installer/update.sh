#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
REPOSITORY="${LIGHTOPS_REPOSITORY:-https://github.com/Honguan/LightOps}"
CHANNEL="stable"
REQUESTED_VERSION=""
CHECK_ONLY=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --channel) CHANNEL="$2"; shift 2 ;;
    --version) REQUESTED_VERSION="$2"; shift 2 ;;
    --check) CHECK_ONLY=true; shift ;;
    --help) echo "Usage: sudo lightops update [--channel stable|beta] [--version X.Y.Z] [--check]"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ "$CHANNEL" == "stable" || "$CHANNEL" == "beta" ]] || { echo "Invalid update channel." >&2; exit 2; }
require_root
load_config
mkdir -p "$LOG_DIR" "$BACKUP_DIR"
exec > >(tee -a "$LOG_DIR/update.log") 2>&1
$CHECK_ONLY || acquire_transition_lock
current_version="$(basename "$(readlink -f "$LIGHTOPS_ROOT/current")")"
version_url="$REPOSITORY/releases/latest/download/VERSION"
[[ "$CHANNEL" == "beta" ]] && version_url="$REPOSITORY/releases/download/beta/VERSION"
target_version="${REQUESTED_VERSION:-$(curl -fsSL "$version_url")}"; target_version="${target_version//[[:space:]]/}"
[[ "$target_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Remote version is invalid." >&2; exit 1; }
echo "Current: $current_version; available: $target_version"
$CHECK_ONLY && exit 0
[[ "$current_version" != "$target_version" ]] || { echo "LightOps is already up to date."; exit 0; }

tmp_dir="$(mktemp -d)"; trap 'rm -rf "$tmp_dir"' EXIT
archive="$tmp_dir/lightops-$target_version.tar.gz"
curl -fsSL "$REPOSITORY/releases/download/v$target_version/lightops-$target_version.tar.gz" -o "$archive"
curl -fsSL "$REPOSITORY/releases/download/v$target_version/lightops-$target_version.tar.gz.sha256" -o "$archive.sha256"
(cd "$tmp_dir" && sha256sum -c "$(basename "$archive").sha256")
mkdir "$tmp_dir/source"; tar -xzf "$archive" -C "$tmp_dir/source" --strip-components=1
tar -czf "$BACKUP_DIR/pre-update-$current_version-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" "$DATA_DIR" "$CONFIG_DIR"
install_release "$tmp_dir/source" "$target_version"
transition_release update "$target_version"
echo "Updated LightOps to $target_version."
