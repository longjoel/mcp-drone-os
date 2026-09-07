from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.ssh_transport import SSHDrone
from mcp_drone_os.state import State


def test_registration_installs_lazy_ssh_transport(monkeypatch):
    coordinator = Coordinator(State())
    coordinator.register_drone(drone_id="d1", hostname="d1", address="10.0.0.2", capabilities=[], slots=1)
    assert isinstance(coordinator.transports["d1"], SSHDrone)
