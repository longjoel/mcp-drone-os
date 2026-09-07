from mcp_drone_os import drone_agent


def test_service_writes_quadlet_and_starts_user_unit(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(drone_agent.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(drone_agent.subprocess, "run", lambda command, **kwargs: calls.append(command))
    result = drone_agent.apply_service("web", {"image": "example/web:1", "command": ["python", "-m", "http.server"]})
    quadlet = tmp_path / ".config/containers/systemd/mcp-drone-web.container"
    assert quadlet.exists()
    assert "Image=example/web:1" in quadlet.read_text()
    assert result["unit"] == "mcp-drone-web.service"
    assert calls[-1][-1] == "mcp-drone-web.service"
