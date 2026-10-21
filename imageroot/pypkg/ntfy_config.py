#
# Copyright (C) 2026 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Shared helpers for the ntfy module actions and scripts."""

import contextlib
import fcntl
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


# These values are maintained outside the editor. Keep existing installations'
# values in the same private, backed-up server.yml; never send them to the UI.
with open(os.path.join(os.path.dirname(__file__), "ntfy_config_policy.json"), encoding="utf-8") as policy_file:
    CONFIG_POLICY = json.load(policy_file)
MANAGED_KEYS = frozenset(CONFIG_POLICY["managed_keys"])


def managed_key(key):
    key = key.replace("_", "-").lower()
    return (key in MANAGED_KEYS or key.startswith(tuple(CONFIG_POLICY["managed_prefixes"]))
            or bool(re.search(CONFIG_POLICY["secret_pattern"], key)))


def parse_config(content):
    """Load unambiguous YAML. Reject duplicates, aliases and merge overrides."""
    import yaml

    class UniqueLoader(yaml.SafeLoader):
        def compose_node(self, parent, index):
            if self.check_event(yaml.AliasEvent):
                raise ValueError("YAML aliases are not supported")
            return super().compose_node(parent, index)

        def construct_mapping(self, node, deep=False):
            result = {}
            for key_node, value_node in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    raise ValueError("YAML merge keys are not supported")
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str):
                    raise ValueError("YAML keys must be strings")
                if key in result:
                    raise ValueError("Duplicate YAML key")
                result[key] = self.construct_object(value_node, deep=deep)
            return result

    try:
        parsed = yaml.load(content, Loader=UniqueLoader)
    except yaml.YAMLError:
        # PyYAML exceptions include source lines, possibly containing secrets.
        raise ValueError("Invalid YAML syntax") from None
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError("The top level must be a mapping")
    return parsed


def dump_config(config):
    import yaml
    return yaml.safe_dump(config, sort_keys=False, allow_unicode=True) if config else ""


def validate_server_config(content):
    try:
        parsed = parse_config(content)
        if any(not re.fullmatch(CONFIG_POLICY["option_pattern"], key) for key in parsed):
            return "Use canonical lowercase YAML option names with hyphens"
        if any(managed_key(key) for key in parsed):
            return "The YAML contains settings managed outside the editor"
    except ValueError as error:
        return str(error)
    return None


def editable_config(content):
    # Re-serialize to avoid leaking secrets in comments, aliases or inline text.
    return dump_config({key: value for key, value in parse_config(content).items()
                        if not managed_key(key)})


def merge_configuration(content, previous, ios_push=None):
    error = validate_server_config(content)
    if error:
        raise ValueError(error)
    hidden = {key: value for key, value in parse_config(previous).items()
              if managed_key(key)}
    # Preserve the target in private module metadata when disabled. Otherwise
    # re-enabling a custom upstream could send its token to the default host.
    saved_upstream = "x-ns8-disabled-upstream-base-url"
    if ios_push is True:
        hidden["upstream-base-url"] = (hidden.get("upstream-base-url")
                                       or hidden.get(saved_upstream)
                                       or "https://ntfy.sh")
        hidden.pop(saved_upstream, None)
    elif ios_push is False and hidden.get("upstream-base-url"):
        hidden[saved_upstream] = hidden.pop("upstream-base-url")
    if not hidden:
        return content
    return dump_config({**parse_config(content), **hidden})


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


@contextlib.contextmanager
def state_lock(directory=None):
    """Coordinate account writes with stopped-database backup snapshots."""
    directory = directory or os.environ.get("AGENT_STATE_DIR", ".")
    descriptor = os.open(os.path.join(directory, ".ntfy-admin.lock"),
                         os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield
