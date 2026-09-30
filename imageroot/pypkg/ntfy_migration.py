#
# Copyright (C) 2026 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Move ntfy data of releases before the ntfy-data volume into the volume.

Earlier releases bind-mounted the whole state directory at /var/lib/ntfy,
so ntfy databases and attachments were stored next to the agent files and
were never included in backups. Functions work relative to the state
directory, which is the working directory of actions and of the service.
"""

import os
import subprocess
import sys

import ntfy_backup
import ntfy_config

# Agent and module files that always stay in the state directory.
STATE_FILES = {"environment", "agent.env", "config", "smarthost.env"}
SQLITE_SUFFIXES = ("", "-wal", "-shm", "-journal")


def legacy_entries(environ=None):
    """Return ntfy data entries still present in the state directory."""
    # Before update-module.d/10migrate_server_config runs, custom data paths
    # are only known from the legacy NTFY_* variables.
    names = set(ntfy_config.data_names(ntfy_config.read_server_config()))
    names.update(ntfy_config.data_names(ntfy_config.legacy_config(environ) or ""))
    entries = []
    for name in sorted(names):
        if not name or name.startswith(".") or name in STATE_FILES:
            continue
        for suffix in SQLITE_SUFFIXES:
            path = name + suffix
            if os.path.lexists(path):
                entries.append(path)
    return entries


def move_legacy_data(entries):
    """Move entries into the ntfy-data volume; ntfy must not be running."""
    mountpoint = ntfy_backup.volume_mountpoint()
    for entry in entries:
        target = os.path.join(mountpoint, entry)
        if os.path.lexists(target):
            print(f"Keeping existing {target}; legacy {entry} left in the state directory", file=sys.stderr)
            continue
        # Volume and state directory are both in the module home, so this is
        # normally an atomic rename.
        subprocess.run(("mv", "--no-target-directory", entry, target), check=True)
        print(f"Moved {entry} to volume {ntfy_config.DATA_VOLUME}", file=sys.stderr)
