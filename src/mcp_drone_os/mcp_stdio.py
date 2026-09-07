"""Minimal stdio MCP gateway for the local coordinator.

The gateway intentionally exposes coarse operations so a host agent can submit
an experiment matrix in one call and poll a compact task result later.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from .coordinator import Coordinator


TOOLS = [
    {"name": "fleet_snapshot", "description": "Get drones, capacity, and task state.", "inputSchema": {"type": "object"}},
    {"name": "register_drone", "description": "Register or heartbeat a drone.", "inputSchema": {"type": "object", "required": ["drone_id", "hostname", "address"]}},
    {"name": "run_jobs", "description": "Submit and, by default, dispatch one-shot or long-lived jobs as a batch.", "inputSchema": {"type": "object", "required": ["agent_id", "jobs"]}},
    {"name": "stage_bundle", "description": "Copy a local script or directory to one drone once for reuse by many jobs.", "inputSchema": {"type": "object", "required": ["agent_id", "drone_id", "source", "bundle_id"]}},
    {"name": "task_status", "description": "Read one task.", "inputSchema": {"type": "object", "required": ["task_id"]}},
    {"name": "task_logs", "description": "Read bounded task logs.", "inputSchema": {"type": "object", "required": ["task_id"]}},
    {"name": "task_artifacts", "description": "List task artifact metadata.", "inputSchema": {"type": "object", "required": ["task_id"]}},
    {"name": "fetch_artifact", "description": "Fetch one verified artifact to the coordinator host.", "inputSchema": {"type": "object", "required": ["task_id", "relative_path", "destination"]}},
    {"name": "cancel_task", "description": "Cancel a queued or running task.", "inputSchema": {"type": "object", "required": ["task_id"]}},
    {"name": "dispatch_pending", "description": "Dispatch queued tasks to connected drones.", "inputSchema": {"type": "object"}},
    {"name": "reconcile_running", "description": "Reconcile running task state with connected drones.", "inputSchema": {"type": "object"}},
    {"name": "promote_persistent", "description": "Move a drone onto an already-mounted persistent data volume.", "inputSchema": {"type": "object", "required": ["drone_id"]}},
    {"name": "user_event", "description": "Record a dashboard/user action for an agent.", "inputSchema": {"type": "object", "required": ["agent_id", "action"]}},
]


def _result(value: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}], "structuredContent": value}


def dispatch(coordinator: Coordinator, request: dict[str, Any]) -> dict[str, Any]:
    method, params, request_id = request.get("method"), request.get("params", {}), request.get("id")
    if method == "initialize":
        result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {"listChanged": False}, "tasks": {}}, "serverInfo": {"name": "mcp-drone-coordinator", "version": "0.1.0"}}
    elif method == "notifications/initialized":
        return {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        if name == "fleet_snapshot": result = _result(coordinator.fleet_snapshot())
        elif name == "register_drone": result = _result(coordinator.register_drone(**args))
        elif name == "run_jobs": result = _result(coordinator.run_jobs(**args))
        elif name == "stage_bundle": result = _result(coordinator.stage_bundle(**args))
        elif name == "task_status": result = _result(coordinator.task_status(**args))
        elif name == "task_logs": result = _result(coordinator.task_logs(**args))
        elif name == "task_artifacts": result = _result(coordinator.task_artifacts(**args))
        elif name == "fetch_artifact": result = _result(coordinator.fetch_artifact(**args))
        elif name == "cancel_task": result = _result(coordinator.cancel_task(**args))
        elif name == "dispatch_pending": result = _result(coordinator.dispatch_pending(**args))
        elif name == "reconcile_running": result = _result(coordinator.reconcile_running())
        elif name == "promote_persistent": result = _result(coordinator.promote_persistent(**args))
        elif name == "user_event": result = _result(coordinator.user_event(**args))
        else: raise ValueError(f"unknown tool: {name}")
    else:
        raise ValueError(f"unsupported method: {method}")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve(coordinator: Coordinator | None = None) -> None:
    if coordinator is None:
        from .state import State
        coordinator = Coordinator(State(os.environ.get("MCP_DRONE_STATE", "/var/lib/mcp-drone/coordinator.db")))
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        try:
            response = dispatch(coordinator, request)
        except Exception as error:
            response = {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32000, "message": str(error)}}
        if response:
            print(json.dumps(response), flush=True)


def main() -> int:
    serve()
    return 0
