"""Drone-side JSON-lines worker backed by transient systemd services."""

from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
import shlex
from pathlib import Path
from typing import Any

from .persistence import promote


UNIT_RE = re.compile(r"[^a-zA-Z0-9_.@:-]")
RUN_AS_RE = re.compile(r"drone-[a-z][a-z0-9_-]{0,31}$")
TASK_ROOT = Path("/var/lib/mcp-drone/tasks").resolve()


def unit_name(task_id: str) -> str:
    return "mcp-drone-task-" + UNIT_RE.sub("-", task_id)[:180]


def launch(task_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    command = spec.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(item, str) or not item for item in command):
        raise ValueError("task command must be a non-empty argv array of strings")
    workspace = Path(spec.get("workspace", f"/var/lib/mcp-drone/tasks/{task_id}"))
    workspace = workspace.resolve()
    if not workspace.is_relative_to(TASK_ROOT):
        raise ValueError("task workspace must stay under /var/lib/mcp-drone/tasks")
    workspace.mkdir(parents=True, exist_ok=True)
    properties = ["--property=NoNewPrivileges=yes", "--property=PrivateTmp=yes"]
    run_as = spec.get("run_as", "mcp-control")
    if not isinstance(run_as, str) or not RUN_AS_RE.fullmatch(run_as):
        raise ValueError("run_as must name a declared drone agent account")
    properties.extend([f"--property=User={run_as}", "--property=Group=mcp-agents"])
    limits = spec.get("limits", {})
    if isinstance(limits, dict):
        if isinstance(limits.get("cpu_quota"), str):
            properties.append(f"--property=CPUQuota={limits['cpu_quota']}")
        if isinstance(limits.get("memory_max"), str):
            properties.append(f"--property=MemoryMax={limits['memory_max']}")
        if isinstance(limits.get("tasks_max"), int):
            properties.append(f"--property=TasksMax={limits['tasks_max']}")
    # Keep the transient unit record after exit so reconciliation can read its
    # final status and exit code. A later maintenance job can prune old units.
    command_line = ["sudo", "-n", "systemd-run", "--quiet", "--unit", unit_name(task_id),
                    "--working-directory", str(workspace), *properties, "--", *command]
    subprocess.run(command_line, check=True, capture_output=True, text=True)
    return {"task_id": task_id, "unit": unit_name(task_id), "status": "running", "workspace": str(workspace)}


def apply_service(service_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    image = spec.get("image")
    if not isinstance(image, str) or not image or any(char.isspace() for char in image):
        raise ValueError("service image must be a non-empty image reference")
    safe_id = UNIT_RE.sub("-", service_id)[:120]
    quadlet_dir = Path.home() / ".config" / "containers" / "systemd"
    quadlet_dir.mkdir(parents=True, exist_ok=True)
    quadlet = quadlet_dir / f"mcp-drone-{safe_id}.container"
    lines = ["[Unit]", f"Description=mcp-drone service {safe_id}", "", "[Container]", f"Image={image}"]
    command = spec.get("command")
    if command:
        if not isinstance(command, list) or any(not isinstance(item, str) for item in command):
            raise ValueError("service command must be an argv array of strings")
        lines.append(f"Exec={shlex.join(command)}")
    for volume in spec.get("volumes", []):
        if not isinstance(volume, str) or ".." in Path(volume.split(":", 1)[0]).parts:
            raise ValueError("service volumes must not contain parent traversal")
        lines.append(f"Volume={volume}")
    lines.extend(["", "[Service]", "Restart=always", "", "[Install]", "WantedBy=default.target", ""])
    quadlet.write_text("\n".join(lines), encoding="utf-8")
    unit = f"mcp-drone-{safe_id}.service"
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "start", unit], check=True)
    return {"service_id": service_id, "unit": unit, "quadlet": str(quadlet), "status": "running"}


def status(task_id: str) -> dict[str, str]:
    unit = unit_name(task_id)
    result = subprocess.run(["sudo", "-n", "systemctl", "show", unit, "-p", "ActiveState", "-p", "SubState", "-p", "ExecMainStatus"], check=False, capture_output=True, text=True)
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    return {"task_id": task_id, "unit": unit, "active": values.get("ActiveState", "unknown"),
            "substate": values.get("SubState", "unknown"), "exit_code": values.get("ExecMainStatus", "")}


def logs(task_id: str, lines: int = 200) -> dict[str, Any]:
    if lines < 1 or lines > 10000:
        raise ValueError("lines must be between 1 and 10000")
    result = subprocess.run(["sudo", "-n", "journalctl", "-u", unit_name(task_id), "-n", str(lines), "--no-pager", "-o", "cat"], check=False, capture_output=True, text=True)
    return {"task_id": task_id, "lines": result.stdout.splitlines(), "returncode": result.returncode}


def cancel(task_id: str) -> dict[str, Any]:
    result = subprocess.run(["sudo", "-n", "systemctl", "stop", unit_name(task_id)], check=False, capture_output=True, text=True)
    return {"task_id": task_id, "unit": unit_name(task_id), "stopped": result.returncode == 0}


def artifacts(task_id: str, workspace: str | None = None) -> dict[str, Any]:
    root = Path(workspace or f"/var/lib/mcp-drone/tasks/{task_id}").resolve()
    if not root.exists():
        return {"task_id": task_id, "artifacts": []}
    found = []
    for path in root.rglob("*"):
        if path.is_file() and path.resolve().is_relative_to(root):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            found.append({"path": str(path.relative_to(root)), "size": path.stat().st_size, "sha256": digest})
    return {"task_id": task_id, "artifacts": sorted(found, key=lambda item: item["path"])}


def serve() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        try:
            operation = request.get("operation")
            if operation == "launch":
                if request["spec"].get("mode") == "service":
                    result = apply_service(request["task_id"], request["spec"])
                else:
                    result = launch(request["task_id"], request["spec"])
            elif operation == "apply_service":
                result = apply_service(request["service_id"], request["spec"])
            elif operation == "promote_persistent":
                result = promote(**request.get("options", {}))
            elif operation == "status":
                result = status(request["task_id"])
            elif operation == "logs":
                result = logs(request["task_id"], request.get("lines", 200))
            elif operation == "cancel":
                result = cancel(request["task_id"])
            elif operation == "artifacts":
                result = artifacts(request["task_id"], request.get("workspace"))
            else:
                raise ValueError("operation must be launch, apply_service, promote_persistent, status, logs, cancel, or artifacts")
            response = {"ok": True, "result": result}
        except Exception as error:
            response = {"ok": False, "error": str(error)}
        print(json.dumps(response), flush=True)


def main() -> int:
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
