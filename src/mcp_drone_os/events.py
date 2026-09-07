"""Append-only, replayable event contract for dashboard/MCP interactions."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


def make_event(agent_id: str, actor: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"version": 1, "event_id": str(uuid.uuid4()), "agent_id": agent_id,
            "timestamp": time.time(), "actor": actor, "action": action,
            "payload": payload or {}, "acknowledged": False}


def append_event(path: str | Path, event: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")


def read_events(path: str | Path, agent_id: str | None = None) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    events = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [event for event in events if agent_id is None or event.get("agent_id") == agent_id]
