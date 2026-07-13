#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY="${LIGHTOPS_REPOSITORY:-https://github.com/<owner>/lightops}"
VERSION="${LIGHTOPS_VERSION:-latest}"

if [[ -f "$(dirname "${BASH_SOURCE[0]}")/installer/install.sh" ]]; then
  exec bash "$(dirname "${BASH_SOURCE[0]}")/installer/install.sh" "$@"
fi

if [[ "${1:-}" == "--help" ]]; then
  echo "Usage: curl -fsSL <lightops-install-url> | sudo bash"
  echo "Environment: LIGHTOPS_REPOSITORY, LIGHTOPS_VERSION"
  exit 0
fi

if [[ ${EUID} -ne 0 ]]; then
  echo "LightOps installation must run as root (use sudo)." >&2
  exit 1
fi

command -v curl >/dev/null || { echo "curl is required to bootstrap LightOps." >&2; exit 1; }
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
if [[ "$VERSION" == "latest" ]]; then
  VERSION="$(curl -fsSL "$REPOSITORY/releases/latest/download/VERSION")"
fi
archive="$tmp_dir/lightops-$VERSION.tar.gz"
curl -fsSL "$REPOSITORY/releases/download/v$VERSION/lightops-$VERSION.tar.gz" -o "$archive"
curl -fsSL "$REPOSITORY/releases/download/v$VERSION/lightops-$VERSION.tar.gz.sha256" -o "$archive.sha256"
(cd "$tmp_dir" && sha256sum -c "$(basename "$archive").sha256")
mkdir "$tmp_dir/source"
tar -xzf "$archive" -C "$tmp_dir/source" --strip-components=1
bash "$tmp_dir/source/installer/install.sh" --source "$tmp_dir/source"
