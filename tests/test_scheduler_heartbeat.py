from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.state import State


class Worker:
    def __init__(self):
        self.requests = []

    def request(self, payload):
        self.requests.append(payload)
        if payload["operation"] == "status":
            return {"ok": True, "result": {"active": "inactive", "exit_code": "0"}}
        return {"ok": True, "result": {}}


def test_reconcile_dispatches_next_queued_task_when_slot_opens():
    worker = Worker()
    coordinator = Coordinator(State())
    coordinator.register_drone(drone_id="d", hostname="d", address="10.0.0.2", capabilities=[], slots=1)
    coordinator.attach_transport("d", worker)
    tasks = coordinator.run_jobs("a", [{"command": ["true"]}, {"command": ["true"]}], drone_id="d", dispatch=False)
    coordinator.dispatch_pending()
    assert [item["operation"] for item in worker.requests] == ["launch"]
    coordinator.reconcile_running()
    assert [item["operation"] for item in worker.requests] == ["launch", "status", "launch"]
    assert coordinator.state.task(tasks[1]["task_id"])["status"] == "running"
