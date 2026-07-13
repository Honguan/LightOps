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
