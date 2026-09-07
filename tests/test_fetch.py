import hashlib

from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.state import State


class FakeTransport:
    def fetch(self, remote, local):
        open(local, "wb").write(b"result")


def test_fetch_verifies_and_records_artifact(tmp_path):
    state = State()
    coordinator = Coordinator(state)
    coordinator.register_drone(drone_id="d1", hostname="d1", address="", capabilities=[], slots=1)
    task = coordinator.run_jobs("alpha", [{"command": ["true"]}], drone_id="d1", dispatch=False)[0]
    digest = hashlib.sha256(b"result").hexdigest()
    state.record_artifacts(task["task_id"], [{"path": "result.txt", "size": 6, "sha256": digest}])
    result = coordinator.fetch_artifact(task["task_id"], "result.txt", str(tmp_path / "result.txt"), FakeTransport())
    assert result["fetched_path"].endswith("result.txt")
