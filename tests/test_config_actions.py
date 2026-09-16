import contextlib
import io
import json
import os
import runpy
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIGURE_ACTION = (
    REPOSITORY_ROOT
    / "imageroot/actions/configure-module/10configure_environment_vars"
)
GET_CONFIGURATION_ACTION = (
    REPOSITORY_ROOT / "imageroot/actions/get-configuration/20read"
)
MIGRATION_ACTION = (
    REPOSITORY_ROOT / "imageroot/update-module.d/10migrate_server_config"
)
DISCOVER_SMARTHOST = REPOSITORY_ROOT / "imageroot/bin/discover-smarthost"


class FakeAgent(types.ModuleType):
    def __init__(self, smarthost=None):
        super().__init__("agent")
        self.unset_variables = []
        self.smarthost = smarthost

    def unset_env(self, variable):
        self.unset_variables.append(variable)
        os.environ.pop(variable, None)

    def redis_connect(self, **kwargs):
        return kwargs

    def get_smarthost_settings(self, _connection):
        return self.smarthost


@contextlib.contextmanager
def action_environment(directory, environment=None, stdin="", smarthost=None):
    previous_directory = os.getcwd()
    previous_stdin = sys.stdin
    previous_stdout = sys.stdout
    fake_agent = FakeAgent(smarthost)
    output = io.StringIO()

    with patch.dict(os.environ, environment or {}, clear=True):
        with patch.dict(sys.modules, {"agent": fake_agent}):
            os.chdir(directory)
            sys.stdin = io.StringIO(stdin)
            sys.stdout = output
            try:
                yield fake_agent, output
            finally:
                sys.stdin = previous_stdin
                sys.stdout = previous_stdout
                os.chdir(previous_directory)


class ConfigureActionTests(unittest.TestCase):
    def test_writes_explicit_config_atomically_with_private_permissions(self):
        payload = json.dumps({
            "host": "ntfy.example.org",
            "server_config": "base-url: https://ntfy.example.org",
        })

        with tempfile.TemporaryDirectory() as directory:
            with action_environment(directory, stdin=payload) as (agent, _):
                runpy.run_path(str(CONFIGURE_ACTION), run_name="__main__")

            config_path = Path(directory) / "config/server.yml"
            self.assertEqual(
                config_path.read_text(encoding="utf-8"),
                "base-url: https://ntfy.example.org\n",
            )
            self.assertEqual(stat.S_IMODE(config_path.stat().st_mode), 0o600)
            self.assertEqual(
                stat.S_IMODE(config_path.parent.stat().st_mode),
                0o700,
            )
            self.assertIn("NTFY_BASE_URL", agent.unset_variables)
            self.assertIn("NTFY_UPSTREAM_BASE_URE", agent.unset_variables)

    def test_migrates_legacy_environment_values(self):
        payload = json.dumps({"host": "ntfy.example.org"})
        environment = {
            "NTFY_BASE_URL": "https://old.example.org",
            "NTFY_BEHIND_PROXY": "True",
            "NTFY_ENABLE_LOGIN": "False",
            "NTFY_UPSTREAM_BASE_URE": "https://ntfy.sh",
            "NTFY_UPSTREAM_ACCESS_TOKEN": 'token:with"quotes',
        }

        with tempfile.TemporaryDirectory() as directory:
            with action_environment(directory, environment, payload):
                runpy.run_path(str(CONFIGURE_ACTION), run_name="__main__")

            config = (Path(directory) / "config/server.yml").read_text(
                encoding="utf-8"
            )
            self.assertIn('base-url: "https://old.example.org"', config)
            self.assertNotIn("behind-proxy:", config)
            self.assertIn("enable-login: false", config)
            self.assertIn('upstream-base-url: "https://ntfy.sh"', config)
            self.assertIn(
                'upstream-access-token: "token:with\\\"quotes"',
                config,
            )

    def test_empty_config_is_supported(self):
        payload = json.dumps({
            "host": "ntfy.example.org",
            "server_config": "",
        })

        with tempfile.TemporaryDirectory() as directory:
            with action_environment(directory, stdin=payload):
                runpy.run_path(str(CONFIGURE_ACTION), run_name="__main__")

            self.assertEqual(
                (Path(directory) / "config/server.yml").read_text(
                    encoding="utf-8"
                ),
                "",
            )


class GetConfigurationActionTests(unittest.TestCase):
    def test_returns_server_yml_without_modifying_it(self):
        environment = {
            "TRAEFIK_HOST": "ntfy.example.org",
            "TRAEFIK_HTTP2HTTPS": "True",
            "TRAEFIK_LETS_ENCRYPT": "False",
        }

        with tempfile.TemporaryDirectory() as directory:
            config_directory = Path(directory) / "config"
            config_directory.mkdir()
            expected = "base-url: https://ntfy.example.org\n# keep spacing\n"
            (config_directory / "server.yml").write_text(
                expected,
                encoding="utf-8",
            )
            with action_environment(directory, environment) as (_, output):
                runpy.run_path(
                    str(GET_CONFIGURATION_ACTION),
                    run_name="__main__",
                )
                result = json.loads(output.getvalue())

            self.assertEqual(result["server_config"], expected)
            self.assertTrue(result["http2https"])
            self.assertFalse(result["lets_encrypt"])


class MigrationActionTests(unittest.TestCase):
    def test_does_not_overwrite_an_existing_server_yml(self):
        environment = {
            "TRAEFIK_HOST": "ntfy.example.org",
            "NTFY_BASE_URL": "https://legacy.example.org",
        }

        with tempfile.TemporaryDirectory() as directory:
            config_directory = Path(directory) / "config"
            config_directory.mkdir()
            config_path = config_directory / "server.yml"
            config_path.write_text("keep: this\n", encoding="utf-8")

            with action_environment(directory, environment) as (agent, _):
                runpy.run_path(str(MIGRATION_ACTION), run_name="__main__")

            self.assertEqual(
                config_path.read_text(encoding="utf-8"),
                "keep: this\n",
            )
            self.assertIn("NTFY_BASE_URL", agent.unset_variables)


class DiscoverSmarthostTests(unittest.TestCase):
    def test_writes_compatible_smarthost_as_private_ntfy_environment(self):
        smarthost = {
            "enabled": True,
            "host": "smtp.example.org",
            "port": 587,
            "username": "ntfy@example.org",
            "password": "secret=value",
            "encrypt_smtp": "starttls",
            "tls_verify": True,
        }

        with tempfile.TemporaryDirectory() as directory:
            environment = {"TRAEFIK_HOST": "ntfy.example.org"}
            with action_environment(directory, environment, smarthost=smarthost):
                runpy.run_path(str(DISCOVER_SMARTHOST), run_name="__main__")

            env_path = Path(directory) / "smarthost.env"
            self.assertEqual(
                env_path.read_text(encoding="utf-8"),
                "NTFY_SMTP_SENDER_ADDR=smtp.example.org:587\n"
                "NTFY_SMTP_SENDER_FROM=ntfy@example.org\n"
                "NTFY_SMTP_SENDER_PASS=secret=value\n"
                "NTFY_SMTP_SENDER_USER=ntfy@example.org\n",
            )
            self.assertEqual(stat.S_IMODE(env_path.stat().st_mode), 0o600)

    def test_preserves_explicit_sender_from_in_server_yml(self):
        smarthost = {
            "enabled": True,
            "host": "smtp.example.org",
            "port": 25,
            "username": "relay-user",
            "password": "secret",
            "encrypt_smtp": "none",
            "tls_verify": True,
        }

        with tempfile.TemporaryDirectory() as directory:
            config_directory = Path(directory) / "config"
            config_directory.mkdir()
            (config_directory / "server.yml").write_text(
                'smtp-sender-from: "alerts@example.org"\n',
                encoding="utf-8",
            )
            with action_environment(directory, smarthost=smarthost):
                runpy.run_path(str(DISCOVER_SMARTHOST), run_name="__main__")

            environment_file = (Path(directory) / "smarthost.env").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("NTFY_SMTP_SENDER_FROM", environment_file)

    def test_uses_public_host_when_smtp_username_is_not_an_email(self):
        smarthost = {
            "enabled": True,
            "host": "smtp.example.org",
            "port": 25,
            "username": "relay-user",
            "password": "secret",
            "encrypt_smtp": "none",
            "tls_verify": True,
        }

        with tempfile.TemporaryDirectory() as directory:
            environment = {"TRAEFIK_HOST": "ntfy.example.org"}
            with action_environment(directory, environment, smarthost=smarthost):
                runpy.run_path(str(DISCOVER_SMARTHOST), run_name="__main__")

            environment_file = (Path(directory) / "smarthost.env").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "NTFY_SMTP_SENDER_FROM=no-reply@ntfy.example.org\n",
                environment_file,
            )

    def test_skips_disabled_or_implicit_tls_smarthost(self):
        variants = (
            {
                "enabled": False,
                "host": "smtp.example.org",
                "port": 587,
                "username": "",
                "password": "",
                "encrypt_smtp": "starttls",
                "tls_verify": True,
            },
            {
                "enabled": True,
                "host": "smtp.example.org",
                "port": 465,
                "username": "user",
                "password": "secret",
                "encrypt_smtp": "tls",
                "tls_verify": True,
            },
        )

        for smarthost in variants:
            with self.subTest(smarthost=smarthost):
                with tempfile.TemporaryDirectory() as directory:
                    with action_environment(directory, smarthost=smarthost):
                        with self.assertRaises(SystemExit) as raised:
                            runpy.run_path(
                                str(DISCOVER_SMARTHOST),
                                run_name="__main__",
                            )
                    self.assertEqual(raised.exception.code, 0)
                    self.assertEqual(
                        (Path(directory) / "smarthost.env").read_text(
                            encoding="utf-8"
                        ),
                        "",
                    )


if __name__ == "__main__":
    unittest.main()
