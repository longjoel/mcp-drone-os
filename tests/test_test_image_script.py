from pathlib import Path


def test_qemu_smoke_script_has_software_fallback():
    script = (Path(__file__).parents[1] / "tools/test-image.sh").read_text()
    assert "-enable-kvm" in script
    assert "/dev/kvm" in script
    assert "software emulation" in script
