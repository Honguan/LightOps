#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
VERSION=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --help) echo "Usage: sudo lightops rollback [--version X.Y.Z]"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
require_root
load_config
acquire_transition_lock
current="$(basename "$(readlink -f "$LIGHTOPS_ROOT/current")")"
if [[ -z "$VERSION" ]]; then
  VERSION="$(find "$LIGHTOPS_ROOT/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -Vr | grep -Fxv "$current" | head -n1)"
fi
[[ -n "$VERSION" && -d "$LIGHTOPS_ROOT/releases/$VERSION" ]] || { echo "Requested rollback version is unavailable." >&2; exit 1; }
transition_release rollback "$VERSION"
echo "Rolled back LightOps from $current to $VERSION."
