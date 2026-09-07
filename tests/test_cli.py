import json

import pytest

from mcp_drone_os.cli import main
import mcp_drone_os.cli as cli


def test_write_requires_explicit_confirmation(tmp_path, capsys):
    image = tmp_path / "runner.iso"
    image.write_bytes(b"not an actual image")
    with pytest.raises(SystemExit, match="refusing USB write"):
        main(["write", "--image", str(image), "--device", "/dev/sdb", "--confirm-device", "/dev/sdb"])


def test_events_cli(tmp_path, capsys):
    store = tmp_path / "events.jsonl"
    assert main(["events", "--store", str(store), "--append", "alpha", "user", "dashboard.open"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output[0]["action"] == "dashboard.open"


def test_devices_accepts_lsblk_boolean_removable_and_usb_transport(monkeypatch):
    requested = []
    class Result:
        stdout = json.dumps({"blockdevices": [
            {"path": "/dev/sdb", "type": "disk", "rm": True, "tran": "usb"},
            {"path": "/dev/nvme1n1", "type": "disk", "rm": False, "tran": "nvme"},
            {"path": "/dev/sdc", "type": "disk", "rm": False, "tran": "usb"},
        ]})
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/bin/lsblk")
    def fake_run(*args, **kwargs):
        requested.append(args[0])
        return Result()
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert [row["path"] for row in cli._devices()] == ["/dev/sdb", "/dev/sdc"]
    assert "TRAN" in requested[0][-1]


def test_write_runs_only_after_usb_gate_and_sync(monkeypatch, tmp_path, capsys):
    image = tmp_path / "runner.iso"
    image.write_bytes(b"image")
    calls = []
    monkeypatch.setattr(cli.os.path, "exists", lambda path: True)
    monkeypatch.setattr(cli, "_devices", lambda: [{"path": "/dev/sdb", "type": "disk", "rm": True}])
    monkeypatch.setattr(cli, "_partitions", lambda device: ["/dev/sdb1", "/dev/sdb2"])
    monkeypatch.setattr(cli.subprocess, "run", lambda command, **kwargs: calls.append(command))
    assert cli.main(["write", "--image", str(image), "--device", "/dev/sdb",
                     "--confirm-device", "/dev/sdb", "--yes"]) == 0
    assert calls == [["umount", "/dev/sdb2"], ["umount", "/dev/sdb1"],
                     ["dd", f"if={image}", "of=/dev/sdb", "bs=4M", "status=progress", "conv=fsync"], ["sync"]]
