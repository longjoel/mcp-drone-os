"""Agent-directed coordinator façade; transport-independent by design."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .state import State
from .ssh_transport import SSHDrone


class Coordinator:
    def __init__(self, state: State | None = None) -> None:
        self.state = state or State()
        self.transports: dict[str, Any] = {}
        # Dashboard and MCP gateway can be separate processes. Rebuild lazy
        # SSH transports from durable registrations on startup.
        for drone in self.state.snapshot():
            if drone["address"]:
                self.transports[drone["drone_id"]] = SSHDrone(drone["address"], user=drone["ssh_user"])

    def attach_transport(self, drone_id: str, transport: Any) -> None:
        self.state.drone(drone_id)
        self.transports[drone_id] = transport

    def fleet_snapshot(self) -> dict[str, Any]:
        return {"drones": self.state.snapshot(), "tasks": self.state.tasks()}

    def register_drone(self, **kwargs: Any) -> dict[str, Any]:
        drone = self.state.register_drone(**kwargs)
        if drone["address"] and drone["drone_id"] not in self.transports:
            self.transports[drone["drone_id"]] = SSHDrone(drone["address"], user=drone["ssh_user"])
        return drone

    def run_jobs(self, agent_id: str, jobs: list[dict[str, Any]], mode: str = "once",
                 drone_id: str | None = None, defaults: dict[str, Any] | None = None,
                 dispatch: bool = True) -> list[dict[str, Any]]:
        defaults = defaults or {}
        tasks = []
        for job in jobs:
            spec = {**defaults, **job}
            spec["mode"] = mode
            spec.setdefault("run_as", f"drone-{agent_id}")
            task_target = spec.pop("drone_id", drone_id)
            tasks.append(self.state.create_task(agent_id, mode, spec, task_target))
        if dispatch:
            self.dispatch_pending()
        return [self.state.task(task["task_id"]) for task in tasks]

    def task_status(self, task_id: str) -> dict[str, Any]:
        return self.state.task(task_id)

    def dispatch_task(self, task_id: str, transport: Any) -> dict[str, Any]:
        task = self.state.task(task_id)
        if task["status"] != "queued":
            raise ValueError("only queued tasks can be dispatched")
        # Reserve the slot before sending the remote launch. This prevents a
        # single heartbeat from oversubscribing a drone when several queued
        # tasks share the same target.
        started = self.state.update_task(task_id, "running")
        try:
            response = transport.request({"operation": "launch", "task_id": task_id, "spec": task["spec"]})
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "drone rejected task"))
        except Exception:
            self.state.update_task(task_id, "failed", 1)
            raise
        return started

    def dispatch_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        dispatched = []
        for task in self.state.tasks():
            if len(dispatched) >= limit or task["status"] != "queued":
                continue
            transport = self.transports.get(task["drone_id"])
            if transport is not None:
                try:
                    dispatched.append(self.dispatch_task(task["task_id"], transport))
                except Exception as error:
                    self.state.event(task["agent_id"], "coordinator", "task.dispatch_failed", {"task_id": task["task_id"], "error": str(error)})
        return dispatched

    def reconcile_task(self, task_id: str, transport: Any | None = None) -> dict[str, Any]:
        task = self.state.task(task_id)
        if task["status"] != "running":
            return task
        response = self._transport_for(task_id, transport).request({"operation": "status", "task_id": task_id})
        if not response.get("ok"):
            self.state.event(task["agent_id"], "coordinator", "task.status_failed", {"task_id": task_id, "error": response.get("error", "unknown")})
            return task
        worker = response.get("result", {})
        if worker.get("active") == "inactive":
            try:
                exit_code = int(worker.get("exit_code", "1"))
            except (TypeError, ValueError):
                exit_code = 1
            return self.state.update_task(task_id, "completed" if exit_code == 0 else "failed", exit_code)
        return task

    def reconcile_running(self) -> list[dict[str, Any]]:
        result = []
        for task in self.state.tasks():
            if task["status"] == "running" and task["drone_id"] in self.transports:
                result.append(self.reconcile_task(task["task_id"]))
        # Reconciliation is also the lightweight scheduler heartbeat: any
        # slots released by completed tasks are immediately offered to the
        # oldest queued work.
        self.dispatch_pending()
        return result

    def _transport_for(self, task_id: str, transport: Any | None) -> Any:
        if transport is not None:
            return transport
        task = self.state.task(task_id)
        try:
            return self.transports[task["drone_id"]]
        except KeyError as error:
            raise RuntimeError(f"no connected transport for drone {task['drone_id']}") from error

    def cancel_task(self, task_id: str, transport: Any | None = None) -> dict[str, Any]:
        task = self.state.task(task_id)
        if task["status"] not in {"queued", "running"}:
            raise ValueError("only queued or running tasks can be cancelled")
        if task["status"] == "running":
            response = self._transport_for(task_id, transport).request({"operation": "cancel", "task_id": task_id})
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "drone rejected cancellation"))
        return self.state.update_task(task_id, "cancelled")

    def task_logs(self, task_id: str, transport: Any | None = None, lines: int = 200) -> dict[str, Any]:
        response = self._transport_for(task_id, transport).request({"operation": "logs", "task_id": task_id, "lines": lines})
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "drone rejected log request"))
        return response["result"]

    def task_artifacts(self, task_id: str, transport: Any | None = None) -> dict[str, Any]:
        response = self._transport_for(task_id, transport).request({"operation": "artifacts", "task_id": task_id})
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "drone rejected artifact request"))
        result = response["result"]
        result["artifacts"] = self.state.record_artifacts(task_id, result.get("artifacts", []))
        return result

    def promote_persistent(self, drone_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        transport = self.transports.get(drone_id)
        if transport is None:
            raise RuntimeError(f"no connected transport for drone {drone_id}")
        response = transport.request({"operation": "promote_persistent", "options": options or {}})
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "drone rejected persistence promotion"))
        self.state.event("system", "user", "user.promoted_persistence", {"drone_id": drone_id})
        return response["result"]

    def fetch_artifact(self, task_id: str, relative_path: str, destination: str,
                       transport: Any | None = None) -> dict[str, Any]:
        if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise ValueError("artifact path must be relative and traversal-free")
        artifact = next((item for item in self.state.artifacts(task_id) if item["relative_path"] == relative_path), None)
        if artifact is None:
            raise KeyError(f"unknown artifact: {relative_path}")
        task = self.state.task(task_id)
        remote = str(Path(task["spec"].get("workspace", f"/var/lib/mcp-drone/tasks/{task_id}")) / relative_path)
        target = Path(destination).resolve()
        self._transport_for(task_id, transport).fetch(remote, str(target))
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != artifact["sha256"]:
            target.unlink(missing_ok=True)
            raise ValueError("artifact checksum mismatch")
        return self.state.mark_artifact_fetched(task_id, relative_path, str(target))

    def user_event(self, agent_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.state.event(agent_id, "user", action, payload or {})

    def stage_bundle(self, agent_id: str, drone_id: str, source: str, bundle_id: str) -> dict[str, Any]:
        if not bundle_id or not bundle_id.replace("-", "").replace("_", "").isalnum() or not bundle_id[0].isalpha():
            raise ValueError("bundle_id must be a simple identifier")
        transport = self.transports.get(drone_id)
        if transport is None:
            raise RuntimeError(f"no connected transport for drone {drone_id}")
        remote = f"/var/lib/mcp-drone/staging/{bundle_id}"
        transport.push(source, remote)
        result = {"drone_id": drone_id, "bundle_id": bundle_id, "source": str(Path(source).resolve()), "remote_path": remote}
        self.state.event(agent_id, "coordinator", "bundle.staged", result)
        return result
