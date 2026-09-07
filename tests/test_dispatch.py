from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.state import State


class FakeTransport:
    def __init__(self):
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return {"ok": True, "result": {"status": "running"}}


def test_dispatch_uses_worker_stream_and_marks_task_running():
    coordinator = Coordinator(State())
    coordinator.register_drone(drone_id="d1", hostname="d1", address="10.0.0.2", capabilities=[], slots=1)
    task = coordinator.run_jobs("alpha", [{"command": ["echo", "hello"]}], drone_id="d1", dispatch=False)[0]
    transport = FakeTransport()
    result = coordinator.dispatch_task(task["task_id"], transport)
    assert result["status"] == "running"
    assert transport.requests[0]["spec"]["command"] == ["echo", "hello"]
