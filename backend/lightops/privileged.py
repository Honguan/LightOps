from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .operations import Operations


def main(argv: list[str] | None = None) -> int:
    if os.geteuid() != 0:
        print("lightops-privileged must run as root", file=sys.stderr)
        return 1
    arguments = argv if argv is not None else sys.argv[1:]
    manifests = Path(os.getenv("LIGHTOPS_MANIFESTS_DIR", "/opt/lightops/current/manifests"))
    additional_services = tuple(item for item in os.getenv("LIGHTOPS_CUSTOM_SERVICES", "").split(",") if item)
    operations = Operations(manifests, additional_services=additional_services)
    try:
        result = _dispatch(operations, arguments)
    except (KeyError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


def _dispatch(operations: Operations, arguments: list[str]) -> object:
    if len(arguments) == 3 and arguments[:2] == ["app", "logs"]:
        return operations.app_logs(arguments[2])
    if len(arguments) == 3 and arguments[0] == "app":
        return operations.app_action(arguments[2], arguments[1])
    if len(arguments) == 3 and arguments[0] == "service":
        return operations.service_action(arguments[2], arguments[1])
    if len(arguments) == 2 and arguments == ["docker", "list"]:
        return operations.containers()
    if len(arguments) == 3 and arguments[0] == "docker":
        return operations.container_action(arguments[2], arguments[1])
    raise ValueError("unsupported privileged operation")


if __name__ == "__main__":
    raise SystemExit(main())
