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
DATA_VOLUME = "ntfy-data"
DATA_MOUNT = "/var/lib/ntfy"

# Environment variables written by module releases before server.yml existed.
LEGACY_VARIABLES = (
    "NTFY_BASE_URL",
    "NTFY_AUTH_DEFAULT_ACCESS",
    "NTFY_BEHIND_PROXY",
    "NTFY_ENABLE_LOGIN",
    "NTFY_ENABLE_SIGNUP",
    "NTFY_UPSTREAM_BASE_URE",
    "NTFY_UPSTREAM_BASE_URL",
    "NTFY_UPSTREAM_ACCESS_TOKEN",
    "NTFY_WEB_PUSH_EMAIL_ADDRESS",
    "NTFY_CACHE_FILE",
    "NTFY_ATTACHMENT_CACHE_DIR",
    "NTFY_AUTH_FILE",
    "NTFY_WEB_PUSH_FILE",
    "NTFY_WEB_PUSH_PUBLIC_KEY",
    "NTFY_WEB_PUSH_PRIVATE_KEY",
)

LEGACY_STRING_OPTIONS = (
    ("base-url", "NTFY_BASE_URL"),
    ("auth-default-access", "NTFY_AUTH_DEFAULT_ACCESS"),
    ("upstream-base-url", "NTFY_UPSTREAM_BASE_URL"),
    ("upstream-access-token", "NTFY_UPSTREAM_ACCESS_TOKEN"),
    ("web-push-email-address", "NTFY_WEB_PUSH_EMAIL_ADDRESS"),
    ("cache-file", "NTFY_CACHE_FILE"),
    ("attachment-cache-dir", "NTFY_ATTACHMENT_CACHE_DIR"),
    ("auth-file", "NTFY_AUTH_FILE"),
    ("web-push-file", "NTFY_WEB_PUSH_FILE"),
    ("web-push-public-key", "NTFY_WEB_PUSH_PUBLIC_KEY"),
    ("web-push-private-key", "NTFY_WEB_PUSH_PRIVATE_KEY"),
)

LEGACY_BOOLEAN_OPTIONS = (
    ("enable-login", "NTFY_ENABLE_LOGIN"),
    ("enable-signup", "NTFY_ENABLE_SIGNUP"),
)

# server.yml options whose values are paths of ntfy runtime data.
DATA_PATH_OPTIONS = (
    "cache-file",
    "auth-file",
    "attachment-cache-dir",
    "web-push-file",
)

# Data files created by the defaults of this module and by ntfy itself.
DEFAULT_DATA_NAMES = (
    "cache.db",
    "auth.db",
    "user.db",
    "webpush.db",
    "attachments",
)


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


def legacy_config(environ=None):
    """Convert legacy NTFY_* variables to server.yml, or return None."""
    environ = os.environ if environ is None else environ
    values = []

    for option, variable in LEGACY_STRING_OPTIONS:
        value = environ.get(variable, "").strip()
        if value and value.lower() != "none":
            values.append(f"{option}: {yaml_string(value)}")

    for option, variable in LEGACY_BOOLEAN_OPTIONS:
        value = environ.get(variable, "").strip().lower()
        if value in ("true", "false"):
            values.append(f"{option}: {value}")

    # Older releases wrote this misspelled variable.
    if not environ.get("NTFY_UPSTREAM_BASE_URL"):
        value = environ.get("NTFY_UPSTREAM_BASE_URE", "").strip()
        if value and value.lower() != "none":
            values.append(f"upstream-base-url: {yaml_string(value)}")

    if values:
        return "\n".join(values) + "\n"
    return None


def initial_config(host, environ=None):
    """Return migrated legacy settings, or the defaults for a new install."""
    return legacy_config(environ) or default_config(host)


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


def data_names(content):
    """Return top-level names inside DATA_MOUNT used by ntfy data."""
    names = set(DEFAULT_DATA_NAMES)
    for option in DATA_PATH_OPTIONS:
        value = root_scalar(content, option)
        if not value:
            continue
        path = os.path.normpath(value)
        prefix = DATA_MOUNT + "/"
        if path.startswith(prefix):
            names.add(path[len(prefix):].split("/", 1)[0])
    return sorted(names)
