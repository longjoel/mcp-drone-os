"""Persistent SSH JSON-lines transport for one drone."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class SSHDrone:
    def __init__(self, host: str, user: str = "mcp-control", control_dir: str = "~/.cache/mcp-drone/ssh") -> None:
        self.host = host
        self.user = user
        self.control_dir = Path(control_dir).expanduser()
        self.process: subprocess.Popen[str] | None = None

    def connect(self) -> None:
        self.control_dir.mkdir(parents=True, exist_ok=True)
        control_path = self.control_dir / "%C"
        self.process = subprocess.Popen(
            ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "ControlMaster=auto", "-o", "ControlPersist=10m",
             "-o", f"ControlPath={control_path}", f"{self.user}@{self.host}",
             "/usr/local/libexec/mcp-drone-agent", "--stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            self.connect()
        assert self.process is not None and self.process.stdin is not None and self.process.stdout is not None
        try:
            self.process.stdin.write(json.dumps(payload) + "\n")
            self.process.stdin.flush()
            response = self.process.stdout.readline()
            if not response:
                raise ConnectionError(f"drone SSH stream closed: {self.host}")
            return json.loads(response)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process = None

    def fetch(self, remote_path: str, local_path: str) -> None:
        if not remote_path or ".." in Path(remote_path).parts or not remote_path.startswith("/var/lib/mcp-drone/tasks/"):
            raise ValueError("remote artifact path must stay under the drone task root")
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        control_path = self.control_dir / "%C"
        subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", f"ControlPath={control_path}",
                        f"{self.user}@{self.host}:{remote_path}", str(destination)], check=True)

    def push(self, local_path: str, remote_path: str) -> None:
        """Stage a file or directory under the drone's non-task staging root."""
        source = Path(local_path).resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        remote = Path(remote_path)
        if (not remote.is_absolute() or ".." in remote.parts or
                not remote_path.startswith("/var/lib/mcp-drone/staging/")):
            raise ValueError("remote staging path must stay under /var/lib/mcp-drone/staging")
        if self.process is None:
            self.connect()
        control_path = self.control_dir / "%C"
        parent = str(remote if source.is_dir() else remote.parent)
        subprocess.run(["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                        "-o", f"ControlPath={control_path}", f"{self.user}@{self.host}",
                        "mkdir", "-p", parent], check=True)
        source_arg = str(source) + ("/" if source.is_dir() else "")
        target = f"{self.user}@{self.host}:{remote}"
        subprocess.run(["rsync", "-a", "-e",
                        f"ssh -o BatchMode=yes -o ConnectTimeout=5 -o ControlPath={control_path}",
                        source_arg, target], check=True)
