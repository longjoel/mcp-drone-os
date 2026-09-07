"""Manifest loading and validation with no third-party runtime dependency."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
KEY_TYPES = {"ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521"}


@dataclass(frozen=True)
class Agent:
    id: str
    display_name: str
    public_keys: tuple[str, ...]
    quota_cpu: int | None = None
    quota_memory_mb: int | None = None


@dataclass(frozen=True)
class Manifest:
    version: int
    hostname: str
    agents: tuple[Agent, ...]
    lan_cidr: str = "192.168.0.0/16"
    persistence: str = "disposable"


def _load_data(path: Path) -> dict[str, Any]:
    if path.suffix != ".json":
        raise ValueError("manifest must use .json (the canonical machine format)")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest root must be an object")
    return data


def _validate_key(key: str) -> bool:
    parts = key.split()
    if len(parts) < 2 or parts[0] not in KEY_TYPES:
        return False
    try:
        encoded = parts[1] + ("=" * (-len(parts[1]) % 4))
        base64.b64decode(encoded, validate=True)
    except Exception:
        return False
    return True


def load_manifest(path: str | Path) -> Manifest:
    data = _load_data(Path(path))
    errors: list[str] = []
    if data.get("version") != 1:
        errors.append("version must be 1")
    hostname = data.get("hostname", "mcp-drone")
    if not isinstance(hostname, str) or not NAME.fullmatch(hostname):
        errors.append("hostname must match ^[a-z][a-z0-9_-]{0,31}$")
    agents_data = data.get("agents")
    agents: list[Agent] = []
    seen: set[str] = set()
    if not isinstance(agents_data, list) or not agents_data:
        errors.append("agents must be a non-empty array")
        agents_data = []
    for index, item in enumerate(agents_data):
        if not isinstance(item, dict):
            errors.append(f"agents[{index}] must be an object")
            continue
        agent_id = item.get("id")
        if not isinstance(agent_id, str) or not NAME.fullmatch(agent_id):
            errors.append(f"agents[{index}].id is invalid")
            continue
        if agent_id in seen:
            errors.append(f"duplicate agent id: {agent_id}")
        seen.add(agent_id)
        name = item.get("display_name", agent_id)
        keys = item.get("public_keys", [])
        if not isinstance(keys, list) or not keys or any(not isinstance(k, str) or not _validate_key(k) for k in keys):
            errors.append(f"agents[{index}].public_keys must contain valid SSH public keys")
            keys = []
        quota = item.get("quota", {})
        if not isinstance(quota, dict):
            errors.append(f"agents[{index}].quota must be an object")
            quota = {}
        cpu = quota.get("cpu")
        memory = quota.get("memory_mb")
        if cpu is not None and (not isinstance(cpu, int) or cpu < 1):
            errors.append(f"agents[{index}].quota.cpu must be a positive integer")
        if memory is not None and (not isinstance(memory, int) or memory < 128):
            errors.append(f"agents[{index}].quota.memory_mb must be >= 128")
        agents.append(Agent(agent_id, str(name), tuple(keys), cpu, memory))
    persistence = data.get("persistence", "disposable")
    if persistence not in {"disposable", "persistent-capable"}:
        errors.append("persistence must be disposable or persistent-capable")
    if errors:
        raise ValueError("; ".join(errors))
    return Manifest(1, hostname, tuple(agents), str(data.get("lan_cidr", "192.168.0.0/16")), persistence)
