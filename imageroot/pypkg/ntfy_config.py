#
# Copyright (C) 2026 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Shared helpers for the ntfy module actions and scripts."""

import json
import os
import re
import tempfile


CONFIG_DIRECTORY = "config"
CONFIG_PATH = os.path.join(CONFIG_DIRECTORY, "server.yml")
DATA_MOUNT = "/var/lib/ntfy"


def yaml_string(value):
    """Return a YAML-compatible, safely quoted string."""
    return json.dumps(str(value), ensure_ascii=False)


def default_config(host):
    """Return the server.yml used for new installations."""
    return "\n".join((
        f"base-url: {yaml_string('https://' + host)}",
        f'cache-file: "{DATA_MOUNT}/cache.db"',
        f'attachment-cache-dir: "{DATA_MOUNT}/attachments"',
        f'auth-file: "{DATA_MOUNT}/auth.db"',
        'auth-default-access: "deny-all"',
        "enable-login: true",
        "enable-signup: false",
        "",
    ))


def write_server_config(content):
    """Atomically persist server.yml with permissions suitable for secrets."""
    os.makedirs(CONFIG_DIRECTORY, mode=0o700, exist_ok=True)
    os.chmod(CONFIG_DIRECTORY, 0o700)
    fd, temporary_path = tempfile.mkstemp(
        dir=CONFIG_DIRECTORY,
        prefix=".server.yml.",
        text=True,
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            if content and not content.endswith("\n"):
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, CONFIG_PATH)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def secure_server_config():
    """Restrict permissions of an existing server.yml."""
    os.chmod(CONFIG_DIRECTORY, 0o700)
    os.chmod(CONFIG_PATH, 0o600)


def read_server_config():
    """Return the server.yml text, or an empty string if it is missing."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as stream:
            return stream.read()
    except FileNotFoundError:
        return ""


def validate_server_config(content):
    """Return an error message if content is not a YAML mapping, else None.

    PyYAML is part of the NS8 agent Python environment.
    """
    import yaml

    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as error:
        return str(error)
    if parsed is not None and not isinstance(parsed, dict):
        return "the top level of server.yml must be a mapping"
    return None


def _root_key_pattern(key):
    return re.compile(
        r"^[\"']?" + re.escape(key) + r"[\"']?[ \t]*:(?P<value>.*)$"
    )


def root_scalar(content, key):
    """Return the unquoted scalar value of a top-level (unindented) key.

    Return None if the key is missing or its value is empty.
    """
    pattern = _root_key_pattern(key)
    for line in content.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        value = match.group("value").strip()
        if value[:1] in ("'", '"'):
            quote = value[0]
            end = value.find(quote, 1)
            return value[1:end] or None if end > 0 else None
        return value.split(" #", 1)[0].strip() or None
    return None
