from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.dashboard import (cancel_dashboard_task, dashboard_dispatch,
                                    dashboard_reconcile, fleet_payload, record_user_event)
from mcp_drone_os.state import State


def test_dashboard_payload_reads_state_and_records_user_events():
    state = State()
    coordinator = Coordinator(state)
    coordinator.register_drone(drone_id="d1", hostname="d1", address="10.0.0.2", capabilities=[], slots=1)
    assert len(fleet_payload(state)["drones"]) == 1
    event = record_user_event(state, {"agent_id": "alpha", "action": "dashboard.open"})
    assert event["action"] == "dashboard.open"
    assert state.events("alpha")[0]["action"] == "dashboard.open"


class CancelCoordinator:
    def __init__(self, state):
        self.state = state

    def cancel_task(self, task_id):
        return self.state.update_task(task_id, "cancelled")


def test_dashboard_cancel_records_user_action_for_running_task():
    state = State()
    state.register_drone("d1", "d1", "10.0.0.2", [], 1)
    task = state.create_task("alpha", "once", {"command": ["sleep", "10"]}, "d1")
    state.update_task(task["task_id"], "running")
    result = cancel_dashboard_task(state, CancelCoordinator(state), task["task_id"])
    assert result["status"] == "cancelled"
    assert state.events("alpha")[-1]["action"] == "user.cancelled_task"


class DispatchCoordinator:
    def __init__(self, state):
        self.state = state

    def dispatch_pending(self):
        return [{"task_id": "t1", "agent_id": "alpha"}]

    def reconcile_running(self):
        return [{"task_id": "t1", "agent_id": "alpha", "status": "completed"}]


def test_dashboard_fleet_actions_emit_originating_agent_events():
    state = State()
    coordinator = DispatchCoordinator(state)
    assert dashboard_dispatch(state, coordinator)[0]["task_id"] == "t1"
    assert dashboard_reconcile(state, coordinator)[0]["status"] == "completed"
    assert [event["action"] for event in state.events("alpha")] == [
        "user.dispatched_task", "user.reconciled_task"]
