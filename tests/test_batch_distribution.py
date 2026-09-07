from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.state import State


def test_batch_is_distributed_across_available_fleet_slots():
    coordinator = Coordinator(State())
    for name in ("a", "b", "c"):
        coordinator.register_drone(drone_id=name, hostname=f"drone-{name}",
                                   address=f"192.168.1.{10 + ord(name) - ord('a')}",
                                   capabilities=[], slots=4)
    tasks = coordinator.run_jobs("agent", [{"command": ["true"]} for _ in range(12)], dispatch=False)
    counts = {name: sum(task["drone_id"] == name for task in tasks) for name in ("a", "b", "c")}
    assert counts == {"a": 4, "b": 4, "c": 4}
