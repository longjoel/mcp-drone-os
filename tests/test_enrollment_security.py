import json

import pytest

from mcp_drone_os.enroll import enroll


def test_insecure_coordinator_is_rejected_by_default(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": 1, "agents": [{"id": "alpha", "public_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK1PZlI/P9Uxt54/1imrBksnWHiwVVi4Mg2n236FocCD"]}]}))
    config = tmp_path / "enrollment.json"
    config.write_text(json.dumps({"drone_id": "d1", "manifest": str(manifest), "coordinator_url": "http://127.0.0.1:8787"}))
    with pytest.raises(ValueError, match="https"):
        enroll(config)
