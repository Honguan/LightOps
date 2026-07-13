from __future__ import annotations

import argparse
import getpass
import json
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .config import load_settings
from .store import Store


API_URL = "http://127.0.0.1:9080/api"


def api_request(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{API_URL}/{path.lstrip('/')}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lightops", description="LightOps management tool")
    commands = parser.add_subparsers(dest="command")
    for command in ("install", "start", "stop", "restart", "status", "logs", "doctor", "version", "reset-password"):
        commands.add_parser(command)
    uninstall = commands.add_parser("uninstall")
    uninstall.add_argument("--purge", action="store_true")
    uninstall.add_argument("--yes", action="store_true")

    update = commands.add_parser("update")
    update.add_argument("--channel", choices=("stable", "beta"), default="stable")
    update.add_argument("--version")
    update.add_argument("--check", action="store_true")
    rollback = commands.add_parser("rollback")
    rollback.add_argument("--version")

    backup = commands.add_parser("backup")
    backup.add_argument("name")
    backup.add_argument("sources", nargs="+")
    restore = commands.add_parser("restore")
    restore.add_argument("filename")
    restore.add_argument("target")

    config = commands.add_parser("config")
    config_commands = config.add_subparsers(dest="config_action", required=True)
    config_set = config_commands.add_parser("set")
    config_set.add_argument("key", choices=("auto_update", "update_channel"))
    config_set.add_argument("value")

    app = commands.add_parser("app")
    app_commands = app.add_subparsers(dest="app_action", required=True)
    app_commands.add_parser("list")
    search = app_commands.add_parser("search")
    search.add_argument("query")
    for action in ("install", "update", "remove", "start", "stop", "restart"):
        action_parser = app_commands.add_parser(action)
        action_parser.add_argument("names", nargs="+")
    for action in ("status", "logs"):
        action_parser = app_commands.add_parser(action)
        action_parser.add_argument("name")

    stack = commands.add_parser("stack")
    stack_commands = stack.add_subparsers(dest="stack_action", required=True)
    stack_install = stack_commands.add_parser("install")
    stack_install.add_argument("name", choices=("lamp", "lemp", "docker", "node", "python"))

    project = commands.add_parser("project")
    project_commands = project.add_subparsers(dest="project_action", required=True)
    project_commands.add_parser("list")
    create = project_commands.add_parser("create")
    create.add_argument("name")
    create.add_argument("code")
    create.add_argument("project_type")
    create.add_argument("repository")
    create.add_argument("deploy_path")
    create.add_argument("--branch", default="main")
    for action in ("deploy", "rollback", "status", "logs"):
        action_parser = project_commands.add_parser(action)
        action_parser.add_argument("name")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        if argv is None and sys.stdin.isatty():
            return _interactive_menu()
        parser.print_help()
        return 0
    try:
        return _dispatch(args)
    except (OSError, RuntimeError, urllib.error.URLError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "version":
        print(f"LightOps {__version__}")
    elif args.command == "status":
        health = api_request("health")
        print(f"LightOps is running ({health['version']})")
    elif args.command in {"start", "stop", "restart"}:
        _local_command(["systemctl", args.command, "lightops"])
        print(f"LightOps {args.command}: ok")
    elif args.command == "logs":
        _local_command(["journalctl", "-u", "lightops", "-n", "200", "--no-pager"])
    elif args.command in {"install", "update", "rollback", "uninstall"}:
        _lifecycle(args)
    elif args.command == "doctor":
        _doctor()
    elif args.command == "backup":
        _print(api_request("backups", "POST", {"name": args.name, "sources": args.sources}))
    elif args.command == "restore":
        _print(api_request(f"backups/{args.filename}/restore", "POST", {"target": args.target}))
    elif args.command == "app":
        _app(args)
    elif args.command == "stack":
        _print(api_request(f"stacks/{args.name}/install", "POST"))
    elif args.command == "project":
        _project(args)
    elif args.command == "config":
        _config(args.key, args.value)
    elif args.command == "reset-password":
        _reset_password()
    return 0


def _interactive_menu() -> int:
    menu = """LightOps 管理工具

1. 查看服務狀態
2. 啟動 LightOps
3. 停止 LightOps
4. 重新啟動 LightOps
5. 查看日誌
6. 更新 LightOps
7. 回滾上一版本
8. 建立備份
9. 還原備份
10. 系統環境檢查
11. 修改設定
12. 重設管理員密碼
13. 移除 LightOps
0. 離開"""
    simple = {
        "1": ["status"], "2": ["start"], "3": ["stop"], "4": ["restart"], "5": ["logs"],
        "6": ["update"], "7": ["rollback"], "10": ["doctor"], "12": ["reset-password"], "13": ["uninstall"],
    }
    while True:
        print(menu)
        choice = input("請選擇操作：").strip()
        if choice == "0":
            return 0
        arguments = simple.get(choice)
        if choice == "8":
            arguments = ["backup", input("備份名稱：").strip(), input("來源絕對路徑：").strip()]
        elif choice == "9":
            arguments = ["restore", input("備份檔名：").strip(), input("還原目標絕對路徑：").strip()]
        elif choice == "11":
            arguments = ["config", "set", input("設定名稱：").strip(), input("設定值：").strip()]
        if arguments is None:
            print("無效選項。", file=sys.stderr)
            continue
        result = main(arguments)
        if result:
            return result


def _app(args: argparse.Namespace) -> None:
    if args.app_action in {"list", "search", "status"}:
        apps = api_request("apps")
        query = getattr(args, "query", getattr(args, "name", ""))
        selected = [item for item in apps if not query or query.lower() in item["name"].lower() or query.lower() in item.get("display_name", "").lower()]
        _print(selected)
        return
    if args.app_action == "logs":
        _print(api_request(f"apps/{args.name}/logs"))
        return
    for name in args.names:
        _print(api_request(f"apps/{name}/{args.app_action}", "POST"))


def _project(args: argparse.Namespace) -> None:
    if args.project_action == "list":
        _print(api_request("projects"))
    elif args.project_action == "create":
        payload = {
            "name": args.name,
            "code": args.code,
            "project_type": args.project_type,
            "repository": args.repository,
            "branch": args.branch,
            "deploy_path": args.deploy_path,
        }
        _print(api_request("projects", "POST", payload))
    elif args.project_action == "deploy":
        _print(api_request(f"projects/{args.name}/deploy", "POST"))
    elif args.project_action == "rollback":
        _print(api_request(f"projects/{args.name}/rollback", "POST"))
    else:
        _print(api_request(f"projects/{args.name}/deployments"))


def _lifecycle(args: argparse.Namespace) -> None:
    root = Path("/opt/lightops/current/installer")
    script = root / f"{args.command}.sh"
    if args.command == "install":
        script = Path(__file__).resolve().parents[2] / "installer" / "install.sh"
    command = ["bash", str(script)]
    for flag in ("channel", "version"):
        value = getattr(args, flag, None)
        if value:
            command.extend((f"--{flag}", value))
    if getattr(args, "check", False):
        command.append("--check")
    if getattr(args, "purge", False):
        command.append("--purge")
    if getattr(args, "yes", False):
        command.append("--yes")
    _local_command(command)


def _config(key: str, value: str) -> None:
    if key == "auto_update" and value not in {"true", "false"}:
        raise ValueError("auto_update must be true or false")
    if key == "update_channel" and value not in {"stable", "beta"}:
        raise ValueError("update_channel must be stable or beta")
    config_path = Path("/etc/lightops/lightops.env")
    entries: dict[str, str] = {}
    if config_path.exists():
        for line in config_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                current_key, current_value = line.split("=", 1)
                entries[current_key] = current_value
    entries[key.upper()] = value
    config_path.write_text("".join(f"{item}={entries[item]}\n" for item in sorted(entries)), encoding="utf-8")
    print(f"{key}={value}")


def _doctor() -> None:
    checks = {
        "operating_system": platform.platform(),
        "architecture": platform.machine(),
        "disk_free_gb": round(shutil.disk_usage("/").free / 1024**3, 2),
        "systemctl": shutil.which("systemctl") is not None,
        "curl_or_wget": shutil.which("curl") is not None or shutil.which("wget") is not None,
    }
    _print(checks)


def _reset_password() -> None:
    password = getpass.getpass("New administrator password: ")
    confirmation = getpass.getpass("Confirm administrator password: ")
    if password != confirmation:
        raise ValueError("passwords do not match")
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    key = settings.secret_key_file.read_bytes().strip() if settings.secret_key_file.is_file() else None
    Store(settings.database_url, key).set_password("admin", password)
    print("Administrator password updated; existing sessions were revoked.")


def _local_command(command: Sequence[str]) -> None:
    completed = subprocess.run(command, text=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"command failed with exit code {completed.returncode}: {command[0]}")


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
