import json

import pytest

from mcp_drone_os.manifest import load_manifest


def key():
    return "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK1PZlI/P9Uxt54/1imrBksnWHiwVVi4Mg2n236FocCD"


def test_valid_manifest(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"version": 1, "hostname": "drone", "agents": [{"id": "alpha", "public_keys": [key()]}]}))
    assert load_manifest(path).agents[0].id == "alpha"


def test_duplicate_and_missing_keys_are_rejected(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"version": 1, "agents": [{"id": "alpha", "public_keys": []}, {"id": "alpha", "public_keys": []}]}))
    with pytest.raises(ValueError, match="duplicate agent id"):
        load_manifest(path)
