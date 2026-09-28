#
# Copyright (C) 2026 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Prepare a consistent ntfy data snapshot for the NS8 module backup."""

import os
import subprocess


DATA_VOLUME = "ntfy-data"
SNAPSHOT = ".ntfy-backup-snapshot"

# Run file operations in Podman's user namespace: ntfy may own files as a
# subordinate UID that the module agent cannot read directly.
SNAPSHOT_SCRIPT = r"""
volume=$1
config=$2
snapshot="$volume/.ntfy-backup-snapshot"
staging="$volume/.ntfy-backup-snapshot.tmp"
rm -rf -- "$staging"
mkdir -p -- "$staging/data"
find "$volume" -mindepth 1 -maxdepth 1 \
  ! -name '.ntfy-backup-snapshot' \
  ! -name '.ntfy-backup-snapshot.tmp' \
  -exec cp -a -- {} "$staging/data/" \;
if [ -f "$config" ]; then
  cp -a -- "$config" "$staging/server.yml"
fi
rm -rf -- "$snapshot"
mv -- "$staging" "$snapshot"
"""

RESTORE_SCRIPT = r"""
volume=$1
config=$2
snapshot="$volume/.ntfy-backup-snapshot"
[ -d "$snapshot" ] || exit 0
[ -d "$snapshot/data" ] || { echo "Incomplete ntfy backup snapshot" >&2; exit 1; }
cp -a -- "$snapshot/data/." "$volume/"
if [ -f "$snapshot/server.yml" ]; then
  mkdir -p -- "${config%/*}"
  chmod 700 "${config%/*}"
  cp -a -- "$snapshot/server.yml" "$config"
  chmod 600 "$config"
fi
rm -rf -- "$snapshot"
"""

CLEANUP_SCRIPT = r"""
volume=$1
rm -rf -- "$volume/.ntfy-backup-snapshot" "$volume/.ntfy-backup-snapshot.tmp"
"""


def volume_mountpoint():
    # The service may not have created the volume yet, or an old backup may
    # predate it. An empty volume is enough for those cases.
    subprocess.run(
        ("podman", "volume", "create", "--ignore", DATA_VOLUME),
        check=True, stdout=subprocess.DEVNULL,
    )
    output = subprocess.run(
        ("podman", "volume", "inspect", "--format", "{{.Mountpoint}}", DATA_VOLUME),
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if not output or not os.path.isabs(output):
        raise RuntimeError("Podman returned an invalid ntfy-data mountpoint")
    return output


def run_in_user_namespace(script, *arguments, prefix=("podman", "unshare")):
    subprocess.run(
        (*prefix, "sh", "-ec", script, "ntfy-backup", *map(str, arguments)),
        check=True,
    )


def service_is_active():
    return subprocess.run(
        ("systemctl", "--user", "is-active", "--quiet", "ntfy.service"),
        check=False,
    ).returncode == 0


def stop_and_verify():
    subprocess.run(
        ("systemctl", "--user", "stop", "ntfy.service"),
        check=True,
    )
    running = subprocess.run(
        ("podman", "ps", "--filter", "name=ntfy-app", "--format", "{{.Names}}"),
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    if "ntfy-app" in running:
        raise RuntimeError("ntfy-app is still running; refusing to copy SQLite files")


def with_ntfy_stopped(operation):
    was_active = service_is_active()
    try:
        stop_and_verify()
        operation()
    finally:
        if was_active:
            # Restart independently of Restic: NS8 does not call
            # module-cleanup-state if its backup command fails.
            subprocess.run(
                ("systemctl", "--user", "start", "ntfy.service"),
                check=True,
            )


def make_snapshot(state_dir):
    mountpoint = volume_mountpoint()
    config_path = os.path.join(state_dir, "config", "server.yml")
    with_ntfy_stopped(
        lambda: run_in_user_namespace(SNAPSHOT_SCRIPT, mountpoint, config_path)
    )


def restore_snapshot(state_dir):
    mountpoint = volume_mountpoint()
    config_path = os.path.join(state_dir, "config", "server.yml")
    # Old backups have data directly in ntfy-data and need no conversion.
    # Probe inside the user namespace because the agent may not be able to
    # traverse the volume directory itself.
    probe = subprocess.run(
        ("podman", "unshare", "test", "-d", os.path.join(mountpoint, SNAPSHOT)),
        check=False,
    )
    if probe.returncode == 1:
        return
    probe.check_returncode()
    with_ntfy_stopped(
        lambda: run_in_user_namespace(RESTORE_SCRIPT, mountpoint, config_path)
    )


def cleanup_snapshot():
    run_in_user_namespace(CLEANUP_SCRIPT, volume_mountpoint())
