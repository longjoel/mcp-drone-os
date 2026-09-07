import json

from mcp_drone_os.enroll import registration_payload


def test_registration_payload_uses_manifest_and_capacity(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": 1, "hostname": "drone-a", "agents": [{"id": "alpha", "public_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK1PZlI/P9Uxt54/1imrBksnWHiwVVi4Mg2n236FocCD"]}]}))
    payload = registration_payload({"manifest": str(manifest), "drone_id": "a", "address": "10.0.0.2", "slots": 4})
    assert payload["hostname"] == "drone-a"
    assert payload["slots"] == 4
