"""Safe promotion of disposable state onto an already-mounted data volume."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


def promote(source: str = "/var/lib/mcp-drone", data_mount: str = "/srv/mcp-drone-data",
            config_path: str = "/etc/mcp-drone/persistence.conf", runner: Any = subprocess.run) -> dict[str, str]:
    mount = Path(data_mount).resolve()
    source_path = Path(source).resolve()
    if not os.path.ismount(mount):
        raise RuntimeError(f"refusing persistence promotion: {mount} is not a mounted data volume")
    if source_path == mount or mount.is_relative_to(source_path):
        raise ValueError("data mount must not be inside the disposable source")
    target = mount / "mcp-drone"
    target.mkdir(parents=True, exist_ok=True)
    runner(["rsync", "-a", "--numeric-ids", f"{source_path}/", f"{target}/"], check=True)
    config = Path(config_path)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(f"MCP_DRONE_DATA_ROOT={target}\n", encoding="utf-8")
    return {"data_root": str(target), "config": str(config), "status": "persistent"}
