import subprocess
from pathlib import Path


def test_bootstrap_accepts_script_from_standard_input(tmp_path: Path) -> None:
    script = Path("install.sh").read_bytes()

    completed = subprocess.run(
        ["bash", "-s", "--", "--help"],
        cwd=tmp_path,
        input=script,
        capture_output=True,
        check=False,
    )
    stderr = completed.stderr.decode("utf-8", errors="replace")
    stdout = completed.stdout.decode("utf-8", errors="replace")

    assert completed.returncode == 0
    assert "BASH_SOURCE" not in stderr
    assert "Usage: curl" in stdout


def test_health_check_retries_while_service_starts() -> None:
    script = b"""
source installer/common.sh
calls=0
curl() { calls=$((calls + 1)); [[ $calls -ge 3 ]]; }
sleep() { :; }
health_check
[[ $calls -eq 3 ]]
"""

    completed = subprocess.run(["bash"], input=script, capture_output=True, check=False)

    assert completed.returncode == 0


def test_health_check_stops_at_thirty_second_deadline() -> None:
    script = b"""
source installer/common.sh
calls=0
first_timeout=
last_timeout=
curl() {
  calls=$((calls + 1))
  [[ -n $first_timeout ]] || first_timeout=$3
  last_timeout=$3
  return 1
}
sleep() { SECONDS=$((SECONDS + 1)); }
SECONDS=0
if health_check; then exit 1; fi
[[ $calls -eq 30 && $first_timeout -eq 30 && $last_timeout -eq 1 ]]
"""

    completed = subprocess.run(["bash"], input=script, capture_output=True, check=False)

    assert completed.returncode == 0
