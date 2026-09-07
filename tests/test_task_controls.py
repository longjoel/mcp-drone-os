from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.state import State


class FakeTransport:
    def __init__(self):
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        return {"ok": True, "result": {"lines": ["hello"], "artifacts": []}}


def test_pending_dispatch_and_artifact_controls_share_one_transport():
    coordinator = Coordinator(State())
    coordinator.register_drone(drone_id="d1", hostname="d1", address="10.0.0.2", capabilities=[], slots=2)
    transport = FakeTransport()
    coordinator.attach_transport("d1", transport)
    task = coordinator.run_jobs("alpha", [{"command": ["echo", "hello"]}], drone_id="d1", dispatch=False)[0]
    assert coordinator.dispatch_pending()[0]["status"] == "running"
    assert coordinator.task_logs(task["task_id"])["lines"] == ["hello"]
    assert coordinator.task_artifacts(task["task_id"])["artifacts"] == []
    assert [request["operation"] for request in transport.requests] == ["launch", "logs", "artifacts"]
