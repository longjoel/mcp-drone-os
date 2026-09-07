from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.state import State


def test_agent_directed_batch_uses_capacity_and_releases_slots():
    state = State()
    coordinator = Coordinator(state)
    coordinator.register_drone(drone_id="a", hostname="drone-a", address="192.168.1.10", capabilities=["gpu"], slots=2)
    coordinator.register_drone(drone_id="b", hostname="drone-b", address="192.168.1.11", capabilities=[], slots=1)
    tasks = coordinator.run_jobs("alpha", [{"id": "one"}, {"id": "two"}], drone_id="a", dispatch=False)
    assert [task["drone_id"] for task in tasks] == ["a", "a"]
    assert state.drone("a")["available_slots"] == 2
    assert state.update_task(tasks[0]["task_id"], "running")["status"] == "running"
    assert state.update_task(tasks[0]["task_id"], "completed", 0)["status"] == "completed"
    assert state.drone("a")["available_slots"] == 2


def test_batch_can_queue_beyond_current_capacity_and_dispatch_after_completion():
    state = State()
    coordinator = Coordinator(state)
    coordinator.register_drone(drone_id="a", hostname="drone-a", address="192.168.1.10", capabilities=[], slots=1)
    tasks = coordinator.run_jobs("alpha", [{"command": ["true"]}, {"command": ["true"]}], drone_id="a", dispatch=False)
    assert [task["status"] for task in tasks] == ["queued", "queued"]
    assert state.drone("a")["available_slots"] == 1
    state.update_task(tasks[0]["task_id"], "running")
    assert state.drone("a")["available_slots"] == 0
    state.update_task(tasks[0]["task_id"], "completed", 0)
    assert state.drone("a")["available_slots"] == 1


def test_capability_matching():
    state = State()
    coordinator = Coordinator(state)
    coordinator.register_drone(drone_id="cpu", hostname="cpu", address="192.168.1.20", capabilities=["cpu"], slots=1)
    coordinator.register_drone(drone_id="gpu", hostname="gpu", address="192.168.1.21", capabilities=["cpu", "gpu"], slots=1)
    task = coordinator.run_jobs("alpha", [{"requires": ["gpu"]}], dispatch=False)[0]
    assert task["drone_id"] == "gpu"
