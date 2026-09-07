"""First-boot enrollment and local agent account provisioning."""

from __future__ import annotations

import json
import os
import pwd
import ssl
from urllib.parse import urlparse
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

from .manifest import NAME, load_manifest


def registration_payload(config: dict[str, Any]) -> dict[str, Any]:
    manifest_path = config.get("manifest")
    if not isinstance(manifest_path, str):
        raise ValueError("enrollment config requires a manifest path")
    manifest = load_manifest(manifest_path)
    return {"drone_id": config["drone_id"], "hostname": manifest.hostname,
            "address": config.get("address", ""), "capabilities": config.get("capabilities", []),
            "slots": config.get("slots", 1)}


def enroll_host_certificate(config: dict[str, Any], key_path: str = "/etc/ssh/ssh_host_mcp_drone") -> str | None:
    url = config.get("coordinator_url")
    if not url:
        return None
    key = Path(key_path)
    if not key.exists():
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    public_key = key.with_name(key.name + ".pub").read_text(encoding="utf-8").strip()
    request = urllib.request.Request(f"{url.rstrip('/')}/api/drones/enroll",
        data=json.dumps({"drone_id": config["drone_id"], "host_public_key": public_key}).encode(),
        headers={"Content-Type": "application/json", "X-MCP-Drone-Token": config.get("token", "")}, method="POST")
    context = ssl.create_default_context(cafile=config["coordinator_ca"] if config.get("coordinator_ca") else None)
    with urllib.request.urlopen(request, timeout=10, context=context) as response:
        certificate = json.load(response)["host_certificate"]
    certificate_path = key.with_name(key.name + "-cert.pub")
    certificate_path.write_text(certificate, encoding="utf-8")
    os.chmod(key, 0o600)
    os.chmod(certificate_path, 0o644)
    return str(certificate_path)


def provision_accounts(manifest_path: str | Path, root: str = "") -> list[str]:
    """Create declared agent users; intended to run as root during first boot."""
    manifest = load_manifest(manifest_path)
    created: list[str] = []
    for agent in manifest.agents:
        username = f"drone-{agent.id}"
        if not NAME.fullmatch(agent.id):
            raise ValueError(f"invalid agent id: {agent.id}")
        home = Path(root) / "srv" / "mcp-drone" / "agents" / agent.id
        home.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["useradd", "--system", "--home-dir", str(home), "--create-home", "--shell", "/bin/bash", "--groups", "mcp-agents", username], check=False)
        ssh_dir = home / ".ssh"
        ssh_dir.mkdir(parents=True, exist_ok=True)
        authorized_keys = ssh_dir / "authorized_keys"
        authorized_keys.write_text("\n".join(agent.public_keys) + "\n", encoding="utf-8")
        account = pwd.getpwnam(username)
        os.chown(home, account.pw_uid, account.pw_gid)
        os.chown(ssh_dir, account.pw_uid, account.pw_gid)
        os.chown(authorized_keys, account.pw_uid, account.pw_gid)
        os.chmod(ssh_dir, 0o700)
        os.chmod(authorized_keys, 0o600)
        created.append(username)
    return created


def provision_controller_access(config: dict[str, Any], root: str = "") -> bool:
    """Install explicitly supplied coordinator keys for the control account."""
    keys = config.get("controller_public_keys", [])
    if not keys:
        return False
    if not isinstance(keys, list) or any(not isinstance(key, str) or not key.startswith(("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-")) for key in keys):
        raise ValueError("controller_public_keys must contain SSH public key strings")
    home = Path(root) / "var" / "lib" / "mcp-drone"
    ssh_dir = home / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    authorized_keys = ssh_dir / "authorized_keys"
    authorized_keys.write_text("\n".join(keys) + "\n", encoding="utf-8")
    account = pwd.getpwnam("mcp-control")
    os.chown(home, account.pw_uid, account.pw_gid)
    os.chown(ssh_dir, account.pw_uid, account.pw_gid)
    os.chown(authorized_keys, account.pw_uid, account.pw_gid)
    os.chmod(ssh_dir, 0o700)
    os.chmod(authorized_keys, 0o600)
    return True


def enroll(config_path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    url = config.get("coordinator_url")
    if url:
        scheme = urlparse(url).scheme
        if scheme != "https" and not config.get("allow_insecure", False):
            raise ValueError("coordinator_url must use https (set allow_insecure only for isolated development)")
    created = provision_accounts(config["manifest"])
    controller_access = provision_controller_access(config)
    if url:
        host_certificate = enroll_host_certificate(config)
        request = urllib.request.Request(f"{url.rstrip('/')}/api/drones/register",
            data=json.dumps(registration_payload(config)).encode(), headers={
                "Content-Type": "application/json", "X-MCP-Drone-Token": config.get("token", "")}, method="POST")
        context = None
        if config.get("coordinator_ca"):
            context = ssl.create_default_context(cafile=config["coordinator_ca"])
        with urllib.request.urlopen(request, timeout=10, context=context) as response:
            registration = json.load(response)
    else:
        host_certificate = None
        registration = {"offline": True}
    return {"agents": created, "controller_access": controller_access,
            "host_certificate": host_certificate, "registration": registration}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("config", default="/etc/mcp-drone/enrollment.json", nargs="?")
    args = parser.parse_args()
    print(json.dumps(enroll(args.config), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
