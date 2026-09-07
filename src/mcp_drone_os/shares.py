"""Opt-in Samba share configuration with strict per-agent path validation."""

from __future__ import annotations

import re
from pathlib import Path


ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def share_block(agent_id: str, root: str = "/srv/mcp-drone/agents") -> str:
    if not ID_RE.fullmatch(agent_id):
        raise ValueError("invalid agent id")
    base = Path(root).resolve()
    path = (base / agent_id).resolve()
    if not path.is_relative_to(base):
        raise ValueError("share path escapes agent root")
    return f"[{agent_id}]\n   path = {path}\n   valid users = drone-{agent_id}\n   read only = no\n   browseable = yes\n   inherit permissions = yes\n"


def render_shares(agent_ids: list[str], root: str = "/srv/mcp-drone/agents") -> str:
    if len(set(agent_ids)) != len(agent_ids):
        raise ValueError("duplicate agent id")
    return "\n".join(share_block(agent_id, root) for agent_id in agent_ids)
