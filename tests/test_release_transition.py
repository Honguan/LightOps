import subprocess
from pathlib import Path


def run_bash(script: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["bash"], input=script.encode(), capture_output=True, check=False)


def run_transition_bash(script: str) -> subprocess.CompletedProcess[bytes]:
    setup = r"""
source installer/common.sh
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
LIGHTOPS_ROOT="$root/lightops"
DATA_DIR="$root/data"
BACKUP_DIR="$root/backups"
export DATA_DIR
"""
    return run_bash(setup + script)


def test_update_health_failure_restores_database_release_and_service() -> None:
    script = r"""
mkdir -p "$LIGHTOPS_ROOT/releases/1.0.0" "$LIGHTOPS_ROOT/releases/2.0.0/venv/bin" "$DATA_DIR"
ln -s "$LIGHTOPS_ROOT/releases/1.0.0" "$LIGHTOPS_ROOT/current"
python3 - "$DATA_DIR/lightops.db" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as database:
    database.execute("CREATE TABLE state (value TEXT)")
    database.execute("INSERT INTO state VALUES ('before')")
PY
cat > "$LIGHTOPS_ROOT/releases/2.0.0/venv/bin/lightops-migrate" <<'SCRIPT'
#!/usr/bin/env bash
if [[ $1 == plan ]]; then
  printf '[]'
else
  python3 - "$DATA_DIR/lightops.db" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as database:
    database.execute("UPDATE state SET value = 'after'")
PY
  printf stale > "$DATA_DIR/lightops.db-wal"
fi
SCRIPT
chmod +x "$LIGHTOPS_ROOT/releases/2.0.0/venv/bin/lightops-migrate"
systemctl() { printf '%s\n' "$*" >> "$root/systemctl.log"; }
chown() { :; }
health_check() { return 1; }
if transition_release update 2.0.0; then exit 1; fi
[[ "$(readlink -f "$LIGHTOPS_ROOT/current")" == "$LIGHTOPS_ROOT/releases/1.0.0" ]]
[[ "$(python3 -c 'import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute("SELECT value FROM state").fetchone()[0])' "$DATA_DIR/lightops.db")" == before ]]
[[ ! -e "$DATA_DIR/lightops.db-wal" ]]
grep -Fxq 'restart lightops' "$root/systemctl.log"
"""

    completed = run_transition_bash(script)

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


def test_install_allows_external_database_migrations() -> None:
    script = r"""
LIGHTOPS_DATABASE_URL="postgresql://example/lightops"
mkdir -p "$LIGHTOPS_ROOT/releases/1.0.0/venv/bin" "$DATA_DIR"
cat > "$LIGHTOPS_ROOT/releases/1.0.0/venv/bin/lightops-migrate" <<'SCRIPT'
#!/usr/bin/env bash
if [[ $1 == plan ]]; then printf '[{"version":"0001","reversible":false}]'; fi
exit 0
SCRIPT
chmod +x "$LIGHTOPS_ROOT/releases/1.0.0/venv/bin/lightops-migrate"
systemctl() { :; }
chown() { :; }
health_check() { return 0; }
prune_releases() { :; }
transition_release install 1.0.0
[[ "$(readlink -f "$LIGHTOPS_ROOT/current")" == "$LIGHTOPS_ROOT/releases/1.0.0" ]]
"""

    completed = run_transition_bash(script)

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


def test_update_acquires_lock_before_remote_version_lookup() -> None:
    source = Path("installer/update.sh").read_text(encoding="utf-8")

    assert source.index("acquire_transition_lock") < source.index("target_version=")


def test_update_rejects_external_database_migrations_before_stopping_service() -> None:
    script = r"""
LIGHTOPS_DATABASE_URL="postgresql://example/lightops"
mkdir -p "$LIGHTOPS_ROOT/releases/1.0.0" "$LIGHTOPS_ROOT/releases/2.0.0/venv/bin" "$DATA_DIR"
ln -s "$LIGHTOPS_ROOT/releases/1.0.0" "$LIGHTOPS_ROOT/current"
cat > "$LIGHTOPS_ROOT/releases/2.0.0/venv/bin/lightops-migrate" <<'SCRIPT'
#!/usr/bin/env bash
if [[ $1 == plan ]]; then printf '[{"version":"0002","reversible":true}]'; fi
SCRIPT
chmod +x "$LIGHTOPS_ROOT/releases/2.0.0/venv/bin/lightops-migrate"
systemctl() { printf called > "$root/systemctl-called"; }
if transition_release update 2.0.0; then exit 1; fi
[[ ! -e "$root/systemctl-called" ]]
[[ "$(readlink -f "$LIGHTOPS_ROOT/current")" == "$LIGHTOPS_ROOT/releases/1.0.0" ]]
"""

    completed = run_transition_bash(script)

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


def test_update_success_switches_release_and_keeps_migrated_database() -> None:
    script = r"""
mkdir -p "$LIGHTOPS_ROOT/releases/1.0.0" "$LIGHTOPS_ROOT/releases/2.0.0/venv/bin" "$DATA_DIR"
ln -s "$LIGHTOPS_ROOT/releases/1.0.0" "$LIGHTOPS_ROOT/current"
python3 - "$DATA_DIR/lightops.db" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as database:
    database.execute("CREATE TABLE state (value TEXT)")
    database.execute("INSERT INTO state VALUES ('before')")
PY
cat > "$LIGHTOPS_ROOT/releases/2.0.0/venv/bin/lightops-migrate" <<'SCRIPT'
#!/usr/bin/env bash
if [[ $1 == plan ]]; then
  printf '[]'
else
  python3 - "$DATA_DIR/lightops.db" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as database:
    database.execute("UPDATE state SET value = 'migrated'")
PY
fi
SCRIPT
chmod +x "$LIGHTOPS_ROOT/releases/2.0.0/venv/bin/lightops-migrate"
systemctl() { printf '%s\n' "$*" >> "$root/systemctl.log"; }
chown() { :; }
health_check() { return 0; }
prune_releases() { printf pruned > "$root/pruned"; }
transition_release update 2.0.0
[[ "$(readlink -f "$LIGHTOPS_ROOT/current")" == "$LIGHTOPS_ROOT/releases/2.0.0" ]]
[[ "$(python3 -c 'import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute("SELECT value FROM state").fetchone()[0])' "$DATA_DIR/lightops.db")" == migrated ]]
compgen -G "$BACKUP_DIR/pre-update-1.0.0-*.db" >/dev/null
[[ -f "$root/pruned" ]]
"""

    completed = run_transition_bash(script)

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


def test_initial_install_failure_removes_active_link_and_stops_service() -> None:
    script = r"""
mkdir -p "$LIGHTOPS_ROOT/releases/1.0.0/venv/bin" "$DATA_DIR"
cat > "$LIGHTOPS_ROOT/releases/1.0.0/venv/bin/lightops-migrate" <<'SCRIPT'
#!/usr/bin/env bash
if [[ $1 == plan ]]; then printf '[]'; fi
exit 0
SCRIPT
chmod +x "$LIGHTOPS_ROOT/releases/1.0.0/venv/bin/lightops-migrate"
systemctl() { printf '%s\n' "$*" >> "$root/systemctl.log"; }
chown() { :; }
health_check() { return 1; }
if transition_release install 1.0.0; then exit 1; fi
[[ ! -e "$LIGHTOPS_ROOT/current" && ! -L "$LIGHTOPS_ROOT/current" ]]
grep -Fxq 'start lightops' "$root/systemctl.log"
grep -Fxq 'stop lightops' "$root/systemctl.log"
"""

    completed = run_transition_bash(script)

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


def test_rollback_health_failure_restores_original_release() -> None:
    script = r"""
mkdir -p "$LIGHTOPS_ROOT/releases/1.0.0" "$LIGHTOPS_ROOT/releases/2.0.0"
ln -s "$LIGHTOPS_ROOT/releases/2.0.0" "$LIGHTOPS_ROOT/current"
systemctl() { :; }
health_check() { return 1; }
if transition_release rollback 1.0.0; then exit 1; fi
[[ "$(readlink -f "$LIGHTOPS_ROOT/current")" == "$LIGHTOPS_ROOT/releases/2.0.0" ]]
"""

    completed = run_transition_bash(script)

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")


def test_transition_lock_rejects_concurrent_process() -> None:
    script = r"""
root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
LIGHTOPS_TRANSITION_LOCK="$root/transition.lock"
source installer/common.sh
exec 9>"$LIGHTOPS_TRANSITION_LOCK"
flock -n 9
if acquire_transition_lock; then exit 1; fi
"""

    completed = run_bash(script)

    assert completed.returncode == 0
    assert "already in progress" in completed.stderr.decode(errors="replace")
