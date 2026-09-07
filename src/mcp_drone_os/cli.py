"""Small, safe host-side CLI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .events import append_event, make_event, read_events
from .manifest import load_manifest
from .mcp_stdio import serve
from .state import State


def _devices() -> list[dict[str, str]]:
    if not shutil.which("lsblk"):
        return []
    result = subprocess.run(["lsblk", "-J", "-o", "NAME,PATH,TYPE,RM,SIZE,MODEL,TRAN"], check=True, text=True, capture_output=True)
    rows = json.loads(result.stdout).get("blockdevices", [])
    return [row for row in rows if row.get("type") == "disk" and
            (row.get("rm") in (True, 1, "1") or row.get("tran") == "usb")]


def _partitions(device: Path) -> list[str]:
    result = subprocess.run(["lsblk", "-ln", "-o", "PATH", str(device)], check=True, text=True, capture_output=True)
    return [line.strip() for line in result.stdout.splitlines()[1:] if line.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcp-drone-os")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("manifest")
    sub.add_parser("devices")
    write = sub.add_parser("write", help="write an image to a removable disk")
    write.add_argument("--image", required=True)
    write.add_argument("--device", required=True)
    write.add_argument("--yes", action="store_true")
    write.add_argument("--confirm-device", required=True)
    events = sub.add_parser("events")
    events.add_argument("--store", default="/var/lib/mcp-drone/events.jsonl")
    events.add_argument("--agent")
    events.add_argument("--append", nargs=3, metavar=("AGENT", "ACTOR", "ACTION"))
    sub.add_parser("mcp-stdio")
    fleet = sub.add_parser("fleet")
    fleet.add_argument("--state", default="/var/lib/mcp-drone/coordinator.db")
    fleet.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        manifest = load_manifest(args.manifest)
        print(json.dumps({"valid": True, "hostname": manifest.hostname,
                          "agents": [agent.id for agent in manifest.agents]}, indent=2))
        return 0
    if args.command == "devices":
        print(json.dumps(_devices(), indent=2))
        return 0
    if args.command == "write":
        image, device = Path(args.image), Path(args.device)
        if not image.is_file():
            raise SystemExit(f"image not found: {image}")
        if not os.path.exists(device) or args.confirm_device != str(device) or not args.yes:
            raise SystemExit("refusing USB write: pass --yes and --confirm-device with the exact device path")
        if not any(row.get("path") == str(device) for row in _devices()):
            raise SystemExit("refusing USB write: target is not reported as a removable disk")
        if not str(device).startswith("/dev/"):
            raise SystemExit("refusing USB write: unsupported target device")
        for partition in reversed(_partitions(device)):
            subprocess.run(["umount", partition], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["dd", f"if={image}", f"of={device}", "bs=4M", "status=progress", "conv=fsync"], check=True)
        subprocess.run(["sync"], check=True)
        print(f"image written and synced: {device}")
        return 0
    if args.command == "events":
        if args.append:
            agent, actor, action = args.append
            append_event(args.store, make_event(agent, actor, action))
        print(json.dumps(read_events(args.store, args.agent), indent=2))
        return 0
    if args.command == "mcp-stdio":
        serve()
        return 0
    if args.command == "fleet":
        state = State(args.state)
        print(json.dumps({"drones": state.snapshot(), "tasks": state.tasks()}, indent=2))
        state.close()
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
