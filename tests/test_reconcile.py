from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.state import State


class StatusTransport:
    def request(self, payload):
        assert payload["operation"] == "status"
        return {"ok": True, "result": {"active": "inactive", "exit_code": "0"}}


def test_reconcile_releases_slot_after_worker_exits():
    coordinator = Coordinator(State())
    coordinator.register_drone(drone_id="d1", hostname="d1", address="10.0.0.2", capabilities=[], slots=1)
    task = coordinator.run_jobs("alpha", [{"command": ["true"]}], drone_id="d1", dispatch=False)[0]
    coordinator.state.update_task(task["task_id"], "running")
    coordinator.attach_transport("d1", StatusTransport())
    assert coordinator.reconcile_task(task["task_id"])["status"] == "completed"
    assert coordinator.state.drone("d1")["available_slots"] == 1
