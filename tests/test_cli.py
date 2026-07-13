from lightops import __version__
from lightops.cli import main


def test_version_command(capsys) -> None:
    result = main(["version"])

    assert result == 0
    assert capsys.readouterr().out.strip() == f"LightOps {__version__}"


def test_status_command_reports_api_health(monkeypatch, capsys) -> None:
    monkeypatch.setattr("lightops.cli.api_request", lambda *_args, **_kwargs: {"status": "ok", "version": "0.1.0"})

    result = main(["status"])

    assert result == 0
    assert "LightOps is running (0.1.0)" in capsys.readouterr().out


def test_app_install_calls_allowlisted_api_action(monkeypatch, capsys) -> None:
    calls = []

    def request(path, method="GET", payload=None):
        calls.append((path, method, payload))
        return {"name": "nginx", "status": "ok"}

    monkeypatch.setattr("lightops.cli.api_request", request)

    result = main(["app", "install", "nginx"])

    assert result == 0
    assert calls == [("apps/nginx/install", "POST", None)]
    assert "nginx" in capsys.readouterr().out


def test_project_deploy_uses_named_project(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("lightops.cli.api_request", lambda path, method="GET", payload=None: calls.append((path, method)) or {"status": "ok"})

    assert main(["project", "deploy", "my-site"]) == 0
    assert calls == [("projects/my-site/deploy", "POST")]
