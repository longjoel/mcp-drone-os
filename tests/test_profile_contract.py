from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_usb_image_contains_self_hosted_entrypoints_and_enrollment_write_access():
    profile = ROOT / "runner" / "profile" / "airootfs"
    packages = (ROOT / "runner" / "profile" / "packages.x86_64").read_text().split()
    assert "archiso" in packages
    assert "mkinitcpio-archiso" in packages
    initramfs = profile / "etc/mkinitcpio.conf.d/archiso.conf"
    assert initramfs.read_text().strip() == "HOOKS=(base udev modconf archiso block filesystems)"
    for relative in (
        "usr/local/bin/mcp-drone-os",
        "usr/local/libexec/mcp-drone-agent",
        "usr/local/libexec/mcp-drone-dashboard",
        "usr/local/libexec/mcp-drone-enroll",
        "usr/local/libexec/mcp-drone-mcp",
        "usr/local/bin/mcp-drone-info",
    ):
        assert (profile / relative).is_file(), relative
    assert (ROOT / "tools/install-persistent.sh").is_file()
    network = (profile / "etc/systemd/network/20-mcp-drone-wired.network").read_text()
    assert "DHCP=yes" in network and "Name=en* eth* usb*" in network
    installer = (ROOT / "tools/install-persistent.sh").read_text()
    assert "encrypt filesystems" in installer
    unit = (profile / "etc/systemd/system/mcp-drone-enroll.service").read_text()
    assert "ReadWritePaths=" in unit and "/etc/ssh" in unit
    customize = (profile / "root/customize_airootfs.sh").read_text()
    assert "systemd-firstboot.service" in customize
    assert "/usr/share/zoneinfo/UTC" in customize
    target = (profile / "etc/systemd/system/mcp-drone.target").read_text()
    assert "mcp-drone-info.service" in target
    avahi = (profile / "etc/avahi/services/mcp-drone-ssh.service").read_text()
    assert "_ssh._tcp" in avahi and "product=mcp-drone-os" in avahi
