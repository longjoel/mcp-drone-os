from mcp_drone_os.ssh_transport import SSHDrone


def test_ssh_worker_uses_bundled_absolute_helper(monkeypatch, tmp_path):
    calls = []

    class Process:
        stdin = None
        stdout = None

    monkeypatch.setattr("mcp_drone_os.ssh_transport.subprocess.Popen",
                        lambda command, **kwargs: calls.append(command) or Process())
    drone = SSHDrone("10.0.0.2", control_dir=str(tmp_path))
    drone.connect()
    assert calls[0][-2:] == ["/usr/local/libexec/mcp-drone-agent", "--stdio"]
