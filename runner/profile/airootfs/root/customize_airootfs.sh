#!/usr/bin/env bash
set -euo pipefail

install -d -m 0750 /etc/mcp-drone /var/lib/mcp-drone
install -d -m 0755 /srv/mcp-drone /srv/mcp-drone/agents
# Live media must never stop for systemd-firstboot questions.  Seed the two
# values it prompts for and mask the prompt service as a belt-and-suspenders
# guard for future Arch/systemd defaults.
ln -sfn /usr/share/zoneinfo/UTC /etc/localtime
printf 'LANG=C.UTF-8\n' > /etc/locale.conf
ln -sfn /dev/null /etc/systemd/system/systemd-firstboot.service
if [ ! -f /etc/ssh/ssh_host_mcp_drone ]; then
  ssh-keygen -q -t ed25519 -N "" -f /etc/ssh/ssh_host_mcp_drone
  chmod 0600 /etc/ssh/ssh_host_mcp_drone
  chmod 0644 /etc/ssh/ssh_host_mcp_drone.pub
fi
groupadd --system mcp-agents || true
useradd --system --home-dir /var/lib/mcp-drone --shell /bin/bash --gid mcp-agents mcp-control || true
chown mcp-control:mcp-agents /var/lib/mcp-drone
if [ -s /etc/mcp-drone/controller_authorized_keys ]; then
  install -d -m 0700 -o mcp-control -g mcp-agents /var/lib/mcp-drone/.ssh
  install -m 0600 -o mcp-control -g mcp-agents /etc/mcp-drone/controller_authorized_keys /var/lib/mcp-drone/.ssh/authorized_keys
fi
install -d -m 0755 /etc/sudoers.d
cat > /etc/sudoers.d/mcp-drone-control <<'EOF'
mcp-control ALL=(root) NOPASSWD: /usr/bin/systemd-run, /usr/bin/systemctl, /usr/bin/journalctl
EOF
chmod 0440 /etc/sudoers.d/mcp-drone-control
systemctl enable sshd.service
systemctl enable systemd-networkd.service
systemctl enable systemd-resolved.service
systemctl enable avahi-daemon.service
systemctl enable mcp-drone-info.service
systemctl enable mcp-drone-dashboard.service
systemctl enable mcp-drone.target
