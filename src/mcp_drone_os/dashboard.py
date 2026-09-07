"""Small coordinator-local dashboard/API; bind remotely only behind an auth proxy."""

from __future__ import annotations

import json
import os
import ssl
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .state import State
from .certificates import issue_host_certificate


HTML = """<!doctype html><meta charset=utf-8><title>mcp-drone</title>
<style>body{font:15px system-ui;margin:2rem;max-width:1000px}pre{background:#111;color:#eee;padding:1rem;overflow:auto}button{margin:.2rem}.task{border:1px solid #ccc;padding:.5rem;margin:.4rem 0}</style>
<h1>mcp-drone coordinator</h1><p id=summary>Loading…</p><button onclick="action('/api/reconcile')">Reconcile and dispatch</button><button onclick="action('/api/dispatch')">Dispatch pending</button><section id=tasks></section><pre id=state></pre>
<script>async function cancelTask(id){await fetch('/api/tasks/'+encodeURIComponent(id)+'/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});refresh()}
async function action(path){await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});refresh()}
async function refresh(){let r=await fetch('/api/fleet');let x=await r.json();summary.textContent=`${x.drones.length} drones · ${x.tasks.length} tasks`;tasks.innerHTML=x.tasks.map(t=>`<div class=task><code>${t.task_id}</code> · ${t.agent_id} · ${t.status} · ${t.drone_id||'unassigned'} ${['queued','running'].includes(t.status)?`<button onclick="cancelTask('${t.task_id}')">Cancel</button>`:''}</div>`).join('');state.textContent=JSON.stringify(x,null,2)}refresh();setInterval(refresh,3000)</script>"""


def fleet_payload(state: State) -> dict[str, Any]:
    return {"drones": state.snapshot(), "tasks": state.tasks()}


def record_user_event(state: State, payload: dict[str, Any]) -> dict[str, Any]:
    return state.event(payload["agent_id"], "user", payload["action"], payload.get("payload", {}))


def task_payload(state: State, task_id: str) -> dict[str, Any]:
    task = state.task(task_id)
    task["artifacts"] = state.artifacts(task_id)
    return task


def cancel_dashboard_task(state: State, coordinator: Any | None, task_id: str) -> dict[str, Any]:
    task = state.task(task_id)
    if task["status"] == "running":
        if coordinator is None:
            raise RuntimeError("running task cancellation requires coordinator")
        result = coordinator.cancel_task(task_id)
    elif task["status"] == "queued":
        result = state.update_task(task_id, "cancelled")
    else:
        raise ValueError("only queued or running tasks can be cancelled")
    state.event(task["agent_id"], "user", "user.cancelled_task", {"task_id": task_id})
    return result


def dashboard_dispatch(state: State, coordinator: Any | None) -> list[dict[str, Any]]:
    if coordinator is None:
        raise RuntimeError("dispatch requires coordinator")
    result = coordinator.dispatch_pending()
    for task in result:
        state.event(task["agent_id"], "user", "user.dispatched_task", {"task_id": task["task_id"]})
    return result


def dashboard_reconcile(state: State, coordinator: Any | None) -> list[dict[str, Any]]:
    if coordinator is None:
        raise RuntimeError("reconcile requires coordinator")
    result = coordinator.reconcile_running()
    for task in result:
        state.event(task["agent_id"], "user", "user.reconciled_task", {"task_id": task["task_id"]})
    return result


class Handler(BaseHTTPRequestHandler):
    state: State
    coordinator: Any | None = None

    def _send(self, status: int, body: Any, content_type: str = "application/json") -> None:
        payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/":
            self._send(200, HTML, "text/html; charset=utf-8")
        elif path == "/api/fleet":
            self._send(200, fleet_payload(self.state))
        elif path == "/api/events":
            self._send(200, self.state.events())
        elif path.startswith("/api/tasks/"):
            try:
                self._send(200, task_payload(self.state, path.removeprefix("/api/tasks/")))
            except KeyError as error:
                self._send(404, {"error": str(error)})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path not in {"/api/events", "/api/drones/register", "/api/dispatch", "/api/reconcile"} and not path.startswith("/api/tasks/"):
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            if path == "/api/dispatch":
                self._send(200, dashboard_dispatch(self.state, self.coordinator))
                return
            if path == "/api/reconcile":
                self._send(200, dashboard_reconcile(self.state, self.coordinator))
                return
            if path == "/api/drones/register":
                expected = os.environ.get("MCP_DRONE_ENROLL_TOKEN", "")
                if not expected or self.headers.get("X-MCP-Drone-Token") != expected:
                    self._send(403, {"error": "invalid enrollment token"})
                    return
                result = self.state.register_drone(payload["drone_id"], payload["hostname"], payload["address"], payload.get("capabilities", []), payload.get("slots", 1), payload.get("ssh_user", "mcp-control"))
                self._send(201, result)
                return
            if path == "/api/drones/enroll":
                expected = os.environ.get("MCP_DRONE_ENROLL_TOKEN", "")
                if not expected or self.headers.get("X-MCP-Drone-Token") != expected:
                    self._send(403, {"error": "invalid enrollment token"})
                    return
                ca_key = os.environ.get("MCP_DRONE_SSH_CA_KEY", "")
                if not ca_key:
                    self._send(503, {"error": "SSH CA is not configured"})
                    return
                certificate = issue_host_certificate(payload["host_public_key"], payload["drone_id"], ca_key)
                self._send(201, {"drone_id": payload["drone_id"], "host_certificate": certificate})
                return
            if path.startswith("/api/tasks/") and path.endswith("/cancel"):
                task_id = path.removeprefix("/api/tasks/").removesuffix("/cancel").strip("/")
                result = cancel_dashboard_task(self.state, self.coordinator, task_id)
                self._send(200, result)
                return
            event = record_user_event(self.state, payload)
            self._send(201, event)
        except (KeyError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            self._send(400, {"error": str(error)})

    def log_message(self, *_: Any) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8787, state_path: str = "/var/lib/mcp-drone/coordinator.db",
          tls_cert: str | None = None, tls_key: str | None = None) -> None:
    state = State(state_path)
    from .coordinator import Coordinator
    coordinator = Coordinator(state)
    handler = type("DashboardHandler", (Handler,), {"state": state, "coordinator": coordinator})
    server = ThreadingHTTPServer((host, port), handler)
    if bool(tls_cert) != bool(tls_key):
        raise ValueError("tls_cert and tls_key must be provided together")
    if tls_cert and tls_key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(tls_cert, tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    try:
        server.serve_forever()
    finally:
        state.close()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="mcp-drone-dashboard")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--state", default="/var/lib/mcp-drone/coordinator.db")
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    args = parser.parse_args()
    serve(args.bind, args.port, args.state, args.tls_cert, args.tls_key)
    return 0
