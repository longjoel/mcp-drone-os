"""Durable coordinator state for drones, tasks, artifacts, and user events."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS drones (
  drone_id TEXT PRIMARY KEY, hostname TEXT NOT NULL, address TEXT NOT NULL,
  capabilities TEXT NOT NULL, slots INTEGER NOT NULL DEFAULT 1,
  used_slots INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ready',
  last_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, drone_id TEXT,
  mode TEXT NOT NULL, spec TEXT NOT NULL, status TEXT NOT NULL,
  created_at REAL NOT NULL, started_at REAL, finished_at REAL, exit_code INTEGER,
  FOREIGN KEY(drone_id) REFERENCES drones(drone_id)
);
CREATE TABLE IF NOT EXISTS events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
  agent_id TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  payload TEXT NOT NULL, timestamp REAL NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, relative_path TEXT NOT NULL,
  size INTEGER NOT NULL, sha256 TEXT NOT NULL, fetched_path TEXT,
  UNIQUE(task_id, relative_path), FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
"""


class State:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # The dashboard serves requests on worker threads. SQLite remains the
        # durable source of truth; WAL mode in SCHEMA permits concurrent reads.
        self.db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self.lock = threading.RLock()
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def register_drone(self, drone_id: str, hostname: str, address: str,
                       capabilities: list[str], slots: int = 1) -> dict[str, Any]:
        with self.lock:
            if slots < 1:
                raise ValueError("slots must be positive")
            now = time.time()
            self.db.execute("""INSERT INTO drones(drone_id,hostname,address,capabilities,slots,last_seen)
          VALUES(?,?,?,?,?,?) ON CONFLICT(drone_id) DO UPDATE SET hostname=excluded.hostname,
          address=excluded.address, capabilities=excluded.capabilities, slots=excluded.slots,
          status='ready', last_seen=excluded.last_seen""",
              (drone_id, hostname, address, json.dumps(sorted(set(capabilities))), slots, now))
            return self.drone(drone_id)

    def drone(self, drone_id: str) -> dict[str, Any]:
        with self.lock:
            row = self.db.execute("SELECT * FROM drones WHERE drone_id=?", (drone_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown drone: {drone_id}")
            return self._drone(row)

    def _drone(self, row: sqlite3.Row) -> dict[str, Any]:
        return {**dict(row), "capabilities": json.loads(row["capabilities"]),
                "available_slots": row["slots"] - row["used_slots"]}

    def snapshot(self) -> list[dict[str, Any]]:
        with self.lock:
            return [self._drone(row) for row in self.db.execute("SELECT * FROM drones ORDER BY drone_id")]

    def choose_drone(self, required: list[str] | None = None, available_only: bool = True) -> str:
        with self.lock:
            required_set = set(required or [])
            availability = " AND used_slots < slots" if available_only else ""
            rows = self.db.execute(f"""SELECT d.* FROM drones d
                WHERE d.status='ready'{availability}
                ORDER BY d.used_slots + (SELECT COUNT(*) FROM tasks t
                  WHERE t.drone_id=d.drone_id AND t.status='queued'), d.drone_id""").fetchall()
            for row in rows:
                if required_set <= set(json.loads(row["capabilities"])):
                    return row["drone_id"]
            raise RuntimeError("no ready drone has a matching slot")

    def create_task(self, agent_id: str, mode: str, spec: dict[str, Any],
                    drone_id: str | None = None) -> dict[str, Any]:
        with self.lock:
            if mode not in {"once", "service"}:
                raise ValueError("mode must be once or service")
            # Queueing is durable and must not fail merely because the fleet
            # is temporarily full. Prefer an available runner, then choose a
            # matching ready runner so the task has a stable target.
            target = drone_id
            if target is None:
                try:
                    target = self.choose_drone(spec.get("requires"), available_only=True)
                except RuntimeError:
                    target = self.choose_drone(spec.get("requires"), available_only=False)
            self.drone(target)
            task_id = str(uuid.uuid4())
            now = time.time()
            self.db.execute("INSERT INTO tasks(task_id,agent_id,drone_id,mode,spec,status,created_at) VALUES(?,?,?,?,?,?,?)",
                             (task_id, agent_id, target, mode, json.dumps(spec), "queued", now))
            self.event(agent_id, "agent", "task.created", {"task_id": task_id, "drone_id": target})
            return self.task(task_id)

    def task(self, task_id: str) -> dict[str, Any]:
        with self.lock:
            row = self.db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown task: {task_id}")
            result = dict(row)
            result["spec"] = json.loads(result["spec"])
            return result

    def tasks(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        with self.lock:
            query = "SELECT task_id FROM tasks"
            args: tuple[str, ...] = ()
            if agent_id:
                query += " WHERE agent_id=?"
                args = (agent_id,)
            return [self.task(row["task_id"]) for row in self.db.execute(query + " ORDER BY created_at", args)]

    def update_task(self, task_id: str, status: str, exit_code: int | None = None) -> dict[str, Any]:
        with self.lock:
            task = self.task(task_id)
            allowed = {"queued": {"running", "cancelled"}, "running": {"completed", "failed", "cancelled"},
                   "completed": set(), "failed": set(), "cancelled": set()}
            if status not in allowed.get(task["status"], set()):
                raise ValueError(f"invalid task transition {task['status']} -> {status}")
            now = time.time()
            if status == "running":
                cursor = self.db.execute("UPDATE drones SET used_slots=used_slots+1 WHERE drone_id=? AND status='ready' AND used_slots < slots", (task["drone_id"],))
                if cursor.rowcount == 0:
                    raise RuntimeError("drone has no available slot")
            started = now if status == "running" else task["started_at"]
            finished = now if status in {"completed", "failed", "cancelled"} else None
            self.db.execute("UPDATE tasks SET status=?,started_at=?,finished_at=?,exit_code=? WHERE task_id=?",
                        (status, started, finished, exit_code, task_id))
            if finished:
                self.db.execute("UPDATE drones SET used_slots=MAX(used_slots-1,0) WHERE drone_id=?", (task["drone_id"],))
            self.event(task["agent_id"], "drone", f"task.{status}", {"task_id": task_id, "exit_code": exit_code})
            return self.task(task_id)

    def event(self, agent_id: str, actor: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            event = {"version": 1, "event_id": str(uuid.uuid4()), "agent_id": agent_id,
                 "actor": actor, "action": action, "payload": payload, "timestamp": time.time(),
                 "acknowledged": False}
            self.db.execute("INSERT INTO events(event_id,agent_id,actor,action,payload,timestamp) VALUES(?,?,?,?,?,?)",
                        (event["event_id"], agent_id, actor, action, json.dumps(payload), event["timestamp"]))
            return event

    def record_artifacts(self, task_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self.lock:
            self.task(task_id)
            for item in items:
                self.db.execute("""INSERT INTO artifacts(artifact_id,task_id,relative_path,size,sha256,fetched_path)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(task_id,relative_path) DO UPDATE SET size=excluded.size,
                    sha256=excluded.sha256""", (str(uuid.uuid4()), task_id, item["path"], int(item["size"]), item["sha256"], item.get("fetched_path")))
            return self.artifacts(task_id)

    def artifacts(self, task_id: str) -> list[dict[str, Any]]:
        with self.lock:
            self.task(task_id)
            return [dict(row) for row in self.db.execute("SELECT * FROM artifacts WHERE task_id=? ORDER BY relative_path", (task_id,))]

    def mark_artifact_fetched(self, task_id: str, relative_path: str, fetched_path: str) -> dict[str, Any]:
        with self.lock:
            self.db.execute("UPDATE artifacts SET fetched_path=? WHERE task_id=? AND relative_path=?", (fetched_path, task_id, relative_path))
            row = self.db.execute("SELECT * FROM artifacts WHERE task_id=? AND relative_path=?", (task_id, relative_path)).fetchone()
            if row is None:
                raise KeyError(f"unknown artifact: {relative_path}")
            return dict(row)

    def events(self, agent_id: str | None = None, after: int = 0) -> list[dict[str, Any]]:
        with self.lock:
            query = "SELECT * FROM events WHERE sequence>?"
            args: list[Any] = [after]
            if agent_id:
                query += " AND agent_id=?"
                args.append(agent_id)
            result = []
            for row in self.db.execute(query + " ORDER BY sequence", args):
                item = dict(row)
                item["payload"] = json.loads(item["payload"])
                item["acknowledged"] = bool(item["acknowledged"])
                result.append(item)
            return result
