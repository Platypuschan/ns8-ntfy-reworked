"""Backup snapshot and restore checks without requiring Podman or systemd."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "imageroot/pypkg"))
import ntfy_backup  # noqa: E402


class SnapshotTests(unittest.TestCase):
    def test_snapshot_and_restore_preserve_databases_attachments_and_config(self):
        with tempfile.TemporaryDirectory() as directory:
            volume = Path(directory) / "volume"
            config = Path(directory) / "state/config/server.yml"
            volume.mkdir()
            config.parent.mkdir(parents=True)
            config.write_text('auth-file: "/var/lib/ntfy/auth.db"\n')
            config.chmod(0o600)
            (volume / "cache.db").write_bytes(b"messages")
            (volume / "auth.db").write_bytes(b"users and ACLs")
            (volume / "auth.db-wal").write_bytes(b"pending transaction")
            (volume / "attachments").mkdir()
            (volume / "attachments/file").write_bytes(b"attachment")

            ntfy_backup.run_in_user_namespace(
                ntfy_backup.SNAPSHOT_SCRIPT, volume, config, prefix=()
            )
            snapshot = volume / ntfy_backup.SNAPSHOT
            self.assertEqual((snapshot / "data/auth.db").read_bytes(), b"users and ACLs")
            self.assertEqual((snapshot / "data/auth.db-wal").read_bytes(), b"pending transaction")
            self.assertEqual((snapshot / "data/attachments/file").read_bytes(), b"attachment")
            self.assertEqual((snapshot / "server.yml").read_text(), config.read_text())

            (volume / "auth.db").unlink()
            (volume / "auth.db-wal").unlink()
            (volume / "cache.db").unlink()
            (volume / "attachments/file").unlink()
            config.unlink()
            ntfy_backup.run_in_user_namespace(
                ntfy_backup.RESTORE_SCRIPT, volume, config, prefix=()
            )
            self.assertEqual((volume / "auth.db").read_bytes(), b"users and ACLs")
            self.assertEqual((volume / "auth.db-wal").read_bytes(), b"pending transaction")
            self.assertEqual((volume / "cache.db").read_bytes(), b"messages")
            self.assertEqual((volume / "attachments/file").read_bytes(), b"attachment")
            self.assertIn("auth-file:", config.read_text())
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            self.assertFalse(snapshot.exists())

    def test_new_snapshot_replaces_old_copy_without_nesting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            volume = Path(directory)
            config = volume / "missing.yml"
            (volume / "cache.db").write_text("before")
            for content in ("before", "after"):
                (volume / "cache.db").write_text(content)
                ntfy_backup.run_in_user_namespace(
                    ntfy_backup.SNAPSHOT_SCRIPT, volume, config, prefix=()
                )
            snapshot = volume / ntfy_backup.SNAPSHOT
            self.assertEqual((snapshot / "data/cache.db").read_text(), "after")
            self.assertFalse((snapshot / "data" / ntfy_backup.SNAPSHOT).exists())
            ntfy_backup.run_in_user_namespace(
                ntfy_backup.CLEANUP_SCRIPT, volume, prefix=()
            )
            self.assertFalse(snapshot.exists())

    def test_ntfy_restarts_if_the_snapshot_copy_fails(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(tuple(command))
            if command[:2] == ("podman", "unshare"):
                raise subprocess.CalledProcessError(1, command)
            if command[:3] == ("podman", "ps", "--filter"):
                return subprocess.CompletedProcess(command, 0, "")
            return subprocess.CompletedProcess(command, 0, "")

        with patch.object(ntfy_backup, "volume_mountpoint", return_value="/test/volume"):
            with patch.object(ntfy_backup.subprocess, "run", side_effect=fake_run):
                with self.assertRaises(subprocess.CalledProcessError):
                    ntfy_backup.make_snapshot("/test/state")

        self.assertIn(("systemctl", "--user", "stop", "ntfy.service"), calls)
        self.assertIn(("systemctl", "--user", "start", "ntfy.service"), calls)
        self.assertLess(
            calls.index(("systemctl", "--user", "stop", "ntfy.service")),
            calls.index(("systemctl", "--user", "start", "ntfy.service")),
        )

    def test_ntfy_stays_off_if_it_was_off_before_the_backup(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(tuple(command))
            result = 3 if "is-active" in command else 0
            return subprocess.CompletedProcess(command, result, "")

        with patch.object(ntfy_backup.subprocess, "run", side_effect=fake_run):
            ntfy_backup.with_ntfy_stopped(lambda: None)
        self.assertNotIn(("systemctl", "--user", "start", "ntfy.service"), calls)

    def test_no_snapshot_keeps_legacy_restores_unchanged(self):
        with patch.object(ntfy_backup, "volume_mountpoint", return_value="/test/volume"):
            with patch.object(ntfy_backup.subprocess, "run") as run:
                run.return_value = subprocess.CompletedProcess([], 1, "")
                ntfy_backup.restore_snapshot("/test/state")
        run.assert_called_once()
