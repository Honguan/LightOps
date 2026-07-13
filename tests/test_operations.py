import sys

from lightops.operations import run_command


def test_command_runner_decodes_utf8_independent_of_system_locale() -> None:
    command = "import sys; sys.stdout.buffer.write(bytes([0xe2, 0x9c, 0x93]) + b' LightOps\\n')"
    code, output, error = run_command([sys.executable, "-c", command])

    assert code == 0
    assert output == "✓ LightOps"
    assert error == ""
