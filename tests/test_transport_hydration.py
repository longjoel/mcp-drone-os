from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.state import State


def test_coordinator_rebuilds_transports_from_persisted_registrations(tmp_path):
    state_path = tmp_path / "state.db"
    first = State(state_path)
    first.register_drone("d1", "drone-1", "10.0.0.2", [], 1)
    first.close()

    second = Coordinator(State(state_path))
    assert "d1" in second.transports
    assert second.transports["d1"].host == "10.0.0.2"
