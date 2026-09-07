import pytest

from mcp_drone_os.drone_agent import launch


def test_task_workspace_cannot_escape_task_root(monkeypatch):
    with pytest.raises(ValueError, match="workspace"):
        launch("task-1", {"command": ["true"], "workspace": "/tmp/outside"})
