#
# Copyright (C) 2026 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Move ntfy data of releases before the ntfy-data volume into the volume.

Earlier releases bind-mounted the whole state directory at /var/lib/ntfy,
so ntfy databases and attachments were stored next to the agent files and
were never included in backups. Functions work relative to the state
directory, which is the working directory of actions and of the service.

While the data is still in the state directory, ntfy can already have been
started once on the volume: the upstream module crash-loops during the
update, and systemd may finish such a restart with the new unit. That run
creates empty databases and directories. The data in the state directory is
the original, so it takes precedence; replaced files are kept aside.
"""

import os
import subprocess
import sys
import time

import ntfy_backup
import ntfy_config

# Agent and module files that always stay in the state directory.
STATE_FILES = {"environment", "agent.env", "config", "smarthost.env"}
SQLITE_SUFFIXES = ("", "-wal", "-shm", "-journal")


def legacy_names(environ=None):
    """Return ntfy data names that still have files in the state directory."""
    # Before update-module.d/10migrate_server_config runs, custom data paths
    # are only known from the legacy NTFY_* variables.
    names = set(ntfy_config.data_names(ntfy_config.read_server_config()))
    names.update(ntfy_config.data_names(ntfy_config.legacy_config(environ) or ""))
    return [
        name for name in sorted(names)
        if name and not name.startswith(".") and name not in STATE_FILES
        and any(os.path.lexists(name + suffix) for suffix in SQLITE_SUFFIXES)
    ]


def _move(source, target):
    # Volume and state directory are both in the module home, so this is
    # normally an atomic rename.
    subprocess.run(("mv", "--no-target-directory", source, target), check=True)


def _is_directory(path):
    return os.path.isdir(path) and not os.path.islink(path)


def _merge_directory(source, target):
    """Move the entries of source into target without replacing any."""
    for entry in sorted(os.listdir(source)):
        source_entry = os.path.join(source, entry)
        target_entry = os.path.join(target, entry)
        if not os.path.lexists(target_entry):
            _move(source_entry, target_entry)
        elif _is_directory(source_entry) and _is_directory(target_entry):
            _merge_directory(source_entry, target_entry)
        else:
            print(f"Keeping existing {target_entry}; legacy {source_entry} left in the state directory", file=sys.stderr)
    try:
        os.rmdir(source)
    except OSError:
        pass


def move_legacy_data(names):
    """Move data names into the ntfy-data volume; ntfy must not be running."""
    mountpoint = ntfy_backup.volume_mountpoint()
    replaced = time.strftime(".replaced-%Y%m%dT%H%M%SZ", time.gmtime())
    for name in names:
        target = os.path.join(mountpoint, name)
        if _is_directory(name):
            if not os.path.lexists(target):
                _move(name, target)
            elif _is_directory(target):
                _merge_directory(name, target)
            else:
                print(f"Keeping existing {target}; legacy {name} left in the state directory", file=sys.stderr)
                continue
            print(f"Moved {name} to volume {ntfy_config.DATA_VOLUME}", file=sys.stderr)
            continue

        if _is_directory(target):
            print(f"Keeping existing {target}; legacy {name} left in the state directory", file=sys.stderr)
            continue
        # A database and its -wal/-shm/-journal files belong together: a
        # stray WAL file of another database would corrupt it.
        for suffix in SQLITE_SUFFIXES:
            if os.path.lexists(target + suffix):
                _move(target + suffix, target + suffix + replaced)
                print(f"<4>Replaced {target + suffix} with the data from the state directory; kept it as {target + suffix + replaced}", file=sys.stderr)
        for suffix in SQLITE_SUFFIXES:
            if os.path.lexists(name + suffix):
                _move(name + suffix, target + suffix)
                print(f"Moved {name + suffix} to volume {ntfy_config.DATA_VOLUME}", file=sys.stderr)
