import os

import pytest

from mcp_drone_os.persistence import promote


def test_promotion_requires_a_real_mount(monkeypatch, tmp_path):
    monkeypatch.setattr(os.path, "ismount", lambda path: False)
    with pytest.raises(RuntimeError, match="not a mounted data volume"):
        promote(str(tmp_path / "source"), str(tmp_path / "data"), str(tmp_path / "config"))


def test_promotion_copies_and_records_data_root(monkeypatch, tmp_path):
    source, mount = tmp_path / "source", tmp_path / "data"
    source.mkdir(); mount.mkdir()
    monkeypatch.setattr(os.path, "ismount", lambda path: path == mount.resolve())
    calls = []
    result = promote(str(source), str(mount), str(tmp_path / "config"), lambda command, **kwargs: calls.append(command))
    assert calls[0][0] == "rsync"
    assert result["status"] == "persistent"
    assert "MCP_DRONE_DATA_ROOT" in (tmp_path / "config").read_text()
