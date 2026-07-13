import sys
from pathlib import Path

from lightops.operations import Operations, run_command


def test_command_runner_decodes_utf8_independent_of_system_locale() -> None:
    command = "import sys; sys.stdout.buffer.write(bytes([0xe2, 0x9c, 0x93]) + b' LightOps\\n')"
    code, output, error = run_command([sys.executable, "-c", command])

    assert code == 0
    assert output == "✓ LightOps"
    assert error == ""


def test_container_logs_use_bounded_tail() -> None:
    commands: list[list[str]] = []

    def runner(command):
        commands.append(list(command))
        return 0, "recent log", ""

    result = Operations(Path("manifests"), runner=runner).container_logs("abc-123")

    assert commands == [["docker", "logs", "--tail", "200", "abc-123"]]
    assert result == {"id": "abc-123", "logs": "recent log"}
