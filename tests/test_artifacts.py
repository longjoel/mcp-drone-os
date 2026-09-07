from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.state import State


def test_artifact_metadata_survives_state_reads():
    state = State()
    coordinator = Coordinator(state)
    coordinator.register_drone(drone_id="d1", hostname="d1", address="10.0.0.2", capabilities=[], slots=1)
    task = coordinator.run_jobs("alpha", [{"command": ["true"]}], drone_id="d1", dispatch=False)[0]
    state.record_artifacts(task["task_id"], [{"path": "result.json", "size": 12, "sha256": "abc"}])
    assert state.artifacts(task["task_id"])[0]["sha256"] == "abc"
