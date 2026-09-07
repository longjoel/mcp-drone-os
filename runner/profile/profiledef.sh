#!/usr/bin/env bash

iso_name="mcp-drone-os"
iso_label="MCP_DRONE"
iso_publisher="mcp-drone-os"
iso_application="Disposable MCP drone runner"
iso_version="0.1.0"
install_dir="drone"
buildmodes=("iso")
bootmodes=("bios.syslinux" "uefi.grub")
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
file_permissions=(
  ["/usr/local/libexec/mcp-drone-enroll"]="0:0:0755"
  ["/usr/local/libexec/mcp-drone-agent"]="0:0:0755"
  ["/usr/local/libexec/mcp-drone-mcp"]="0:0:0755"
  ["/usr/local/libexec/mcp-drone-dashboard"]="0:0:0755"
  ["/usr/local/bin/mcp-drone-os"]="0:0:0755"
  ["/usr/local/bin/mcp-drone-info"]="0:0:0755"
)
