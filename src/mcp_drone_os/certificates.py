"""OpenSSH host-certificate issuance for authenticated drone enrollment."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def issue_host_certificate(public_key: str, drone_id: str, ca_key: str,
                           validity: str = "+52w") -> str:
    if not public_key.startswith(("ssh-ed25519 ", "ecdsa-sha2-", "ssh-rsa ")):
        raise ValueError("unsupported host public key")
    if not drone_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in drone_id):
        raise ValueError("invalid drone id")
    ca = Path(ca_key)
    if not ca.is_file():
        raise FileNotFoundError(ca)
    with tempfile.TemporaryDirectory(prefix="mcp-drone-cert-") as directory:
        base = Path(directory) / "host"
        (base.with_suffix(".pub")).write_text(public_key.strip() + "\n", encoding="utf-8")
        subprocess.run(["ssh-keygen", "-s", str(ca), "-I", drone_id, "-h", "-n", drone_id,
                        "-V", f"-1:{validity}", str(base.with_suffix(".pub"))], check=True,
                       capture_output=True, text=True)
        certificate = base.with_name(base.name + "-cert.pub")
        return certificate.read_text(encoding="utf-8")
