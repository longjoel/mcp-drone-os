# mcp-drone-os

An Arch-based, LAN-only disposable agent runner. The project builds a bootable
USB image with hardened SSH, per-agent Unix identities, isolated SMB shares,
an MCP bridge, and a local control-plane dashboard.

## Architecture

Run one coordinator on the laptop where the host agent lives. Booted machines
are drones. The host agent connects to one local MCP server; the coordinator
keeps fleet state and later maintains one persistent SSH control connection per
drone. Drones run one-shot jobs or durable services.

```text
host agent -> local mcp-drone-mcp -> coordinator state -> SSH -> drones
```

Job submission is batched. A twelve-variant experiment is one MCP call, not
twelve independent shell conversations. A drone advertises available slots
and capabilities; placement can be explicit or capability-aware.

## Features

This repository contains the contracts and safe host-side tooling needed for
the first image profile:

- `mcp-drone-os validate` validates an agent manifest without network access.
- `mcp-drone-os devices` lists removable block devices.
- `mcp-drone-os write` requires `--yes`, an exact device confirmation, and a
  removable-disk check before writing.
- `mcp-drone-os events` appends and reads the legacy JSONL event format.
- `mcp-drone-mcp` provides a local JSON-RPC stdio MCP gateway.
- `mcp-drone-agent` provides a persistent JSON-lines worker protocol for
  launching, inspecting, and reading logs from transient systemd tasks.
- `mcp_drone_os.ssh_transport.SSHDrone` keeps one SSH worker stream alive and
  uses OpenSSH connection multiplexing for repeated operations.
- The coordinator stores drones, tasks, artifacts, and audit events in SQLite.
- The MCP gateway exposes registration, batch submission, status, bounded logs,
  artifact listing/fetching, cancellation, reconciliation, persistence
  promotion, and user-event recording.
- `run_jobs` accepts many variants in one call. Each job can select a drone;
  otherwise placement uses available slots. Jobs support one-shot work,
  durable services, and long-lived provisioning work.
- Each drone uses a persistent JSON-lines SSH worker stream plus OpenSSH
  connection multiplexing. The host agent sends coarse batch operations rather
  than starting a new SSH process for every command.
- Drones use per-agent Unix accounts, transient systemd units with CPU,
  memory, and process limits, and rootless Podman/Quadlet for durable services.
- Enrollment supports agent keys, a separate controller key, and an OpenSSH
  host certificate signed by a coordinator-held CA. Password and root SSH are
  disabled.
- A preconfigured image boots without a framebuffer login: it creates declared
  agent accounts, installs the controller key, derives a unique
  `mcp-drone-<NIC>` hostname, records IP/CPU/memory in
  `/run/mcp-drone/identity`, and advertises `_ssh._tcp` over mDNS.
- `runner/profile/` is an ArchISO profile with the minimal runtime package set,
  SSH hardening, first-boot enrollment hook, and systemd target.
- `tools/test-image.sh` boots a built image in QEMU with SSH forwarded to port
  6022.

## Install and use

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
mcp-drone-os validate examples/manifest.json
mcp-drone-os devices

# Start the local MCP gateway for an MCP client
mcp-drone-mcp

# The coordinator can also be inspected directly
mcp-drone-os fleet --state /var/lib/mcp-drone/coordinator.db
```

Launch `mcp-drone-mcp` as a local stdio MCP server for the host agent. The
dashboard is optional and defaults to localhost; view it remotely through SSH
port forwarding. Use TLS and a network boundary before exposing it on a LAN.

### USB-only operation

After the ISO is built, the runtime does not need this repository, Python
packages, or an internet connection. Boot the USB and use the bundled
commands:

```sh
/usr/local/bin/mcp-drone-os fleet --state /var/lib/mcp-drone/coordinator.db
/usr/local/libexec/mcp-drone-mcp
```

An MCP client on another computer can use the USB-hosted coordinator over SSH
by launching `/usr/local/libexec/mcp-drone-mcp` as its SSH stdio command. The
dashboard is available through `ssh -L 8787:127.0.0.1:8787 ...`; it is not
exposed on the LAN by default. Enrollment and remote multi-drone jobs still
need LAN connectivity to the other machines, but the USB itself is the
complete control-plane/runtime artifact.

Build an image after installing Arch’s `archiso` package:

```sh
tools/build-image.sh out
tools/test-image.sh out/mcp-drone-os-0.1.0-x86_64.iso
```

For a dedicated machine, boot the ISO and run the guarded persistent
installer from the live shell. It repartitions the selected whole disk,
creates a LUKS2-encrypted root, installs the runner filesystem, and configures
BIOS and UEFI GRUB boot paths:

```sh
/usr/local/bin/mcp-drone-install \
  --device /dev/sda --confirm-device /dev/sda --yes
```

The installer asks for the device path a second time and prompts for the disk
passphrase. Verify the target carefully: this operation destroys all existing
partitions on that disk. The live image remains the recommended disposable
mode when a machine should be reset by rebooting.

The image configures wired Ethernet and USB Ethernet for DHCP through
systemd-networkd. Wi-Fi credentials are intentionally not baked into the
generic image; configure the appropriate network profile on machines that
need wireless operation.

To bake a runner enrollment bundle into the image, set both
`MCP_DRONE_MANIFEST` and `MCP_DRONE_ENROLLMENT`. The enrollment JSON must
reference `/etc/mcp-drone/manifest.json`; the builder copies the selected
manifest to that path. Enrollment tokens are secrets and should not be
committed to the repository.

To make a USB immediately accept work from one controller, also provide its
public key at build time. It is copied into the image but is not committed:

```sh
MCP_DRONE_MANIFEST=manifest.json \
MCP_DRONE_ENROLLMENT=enrollment.json \
MCP_DRONE_CONTROLLER_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub" \
tools/build-image.sh out-ready
```

The enrollment manifest declares the agent IDs that become
`drone-<id>` Unix accounts. Discover a runner with
`avahi-browse -rt _ssh._tcp`, then register its advertised hostname and SSH
account with the coordinator. `register_drone` accepts `ssh_user` for hosts
whose SSH username differs from the default `mcp-control`.

For an offline/preconfigured runner, start with
`examples/enrollment.json`; add `coordinator_url` and a one-time `token` when
the coordinator is available on the LAN.

Enrollment URLs must use HTTPS by default. For a temporary isolated lab only,
`allow_insecure: true` can be set in the enrollment bundle. The dashboard
supports `--tls-cert` and `--tls-key` when it must be reachable from a LAN;
otherwise keep its localhost default and use SSH forwarding.

For authenticated host enrollment, configure the coordinator with
`MCP_DRONE_ENROLL_TOKEN` and `MCP_DRONE_SSH_CA_KEY`. The drone generates its
own host key on first boot and receives an OpenSSH host certificate; the CA
private key never goes into the image.

SMB is intentionally optional. Install `samba` in a custom profile, generate
`/etc/samba/mcp-drone-shares.conf` with `mcp_drone_os.shares.render_shares`,
then enable `mcp-drone-smb.service`. Agent homes remain accessible over SFTP
without enabling Samba.

### Parallel example: 12 experiments on 3 machines

Register three runners with four slots each. Submit one batch through MCP:

```json
{
  "agent_id": "research-agent",
  "mode": "once",
  "defaults": {"limits": {"cpu_quota": "200%", "memory_max": "2G", "tasks_max": 256}},
  "jobs": [
    {"command": ["./run-test", "--variant", "0"]},
    {"command": ["./run-test", "--variant", "1"]},
    {"command": ["./run-test", "--variant", "2"]}
  ]
}
```

Continue the array through variant 11. The coordinator persists all tasks,
dispatches up to the available slots, and fills slots as work finishes. Use
`fleet_snapshot` or `reconcile_running` for progress, then `task_artifacts`
and `fetch_artifact` to collect results. The laptop handles coordination and
metadata; the three drones perform the CPU and I/O work.

For scripts or repositories, call `stage_bundle` once per destination drone,
then have the batch commands reference
`/var/lib/mcp-drone/staging/<bundle-id>`. Jobs submitted for `agent_id=alpha`
run as the provisioned `drone-alpha` Unix account, so the manifest must declare
that agent on each target runner.

### Current boundaries

This is a small v1 runner, not a general cluster scheduler. It does not flash
media automatically, provide browser login, or implement remote HTTP MCP.
Persistence promotion still expects an already-mounted data volume; the
separate persistent installer handles whole-disk installation and LUKS2 root
encryption. SMB, Kubernetes, and remote MCP transport remain optional future
work.

USB writes are destructive and are never part of the build step. The image
enrollment hook is intentionally explicit: it only registers when given a
coordinator URL and one-time token.

## Security defaults

The image profile disables root/password SSH, accepts only declared public
keys, binds services to the private interface, and creates one Unix identity
and share root per agent. The host builder never guesses a target disk.

## Repository layout

```text
schemas/manifest.schema.json   manifest contract
src/mcp_drone_os/              coordinator, MCP gateway, and state
runner/profile/                bootable ArchISO profile
runner/systemd/                service templates
tools/                         image build and QEMU test entrypoints
tests/                         unit and contract tests
```
