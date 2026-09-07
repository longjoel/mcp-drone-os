from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.state import State


class Transport:
    def __init__(self):
        self.calls = []

    def push(self, source, remote):
        self.calls.append((source, remote))


def test_stage_bundle_is_one_coarse_transfer(tmp_path):
    source = tmp_path / "runner"
    source.mkdir()
    (source / "run.sh").write_text("#!/bin/sh\n")
    coordinator = Coordinator(State())
    coordinator.register_drone(drone_id="d", hostname="d", address="10.0.0.2", capabilities=[], slots=1)
    transport = Transport()
    coordinator.attach_transport("d", transport)
    result = coordinator.stage_bundle("agent", "d", str(source), "suite-1")
    assert result["remote_path"] == "/var/lib/mcp-drone/staging/suite-1"
    assert transport.calls[0][1] == result["remote_path"]
