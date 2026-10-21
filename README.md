# ntfy for NethServer 8

This repository packages [ntfy](https://ntfy.sh/) for NethServer 8. The module
provides a Traefik route, user/token/topic administration, an editor for public
ntfy settings, backup and restore,
and optional outgoing mail through the NS8 smarthost. It runs the
`docker.io/binwiederhier/ntfy:v2.28.0` image.

## Install

Add the [Platypuschan NS8 module catalog](https://github.com/Platypuschan/ns8-modules#add-the-repository)
as a software repository and install **ntfy Reworked** from the NS8 Software
Center.

To install from the command line, use a released version number from
[`CATALOG_VERSION`](CATALOG_VERSION) or the catalog, for example:

```bash
add-module ghcr.io/platypuschan/ntfy-reworked:0.3.4 1
```

The command returns an instance ID such as `ntfy-reworked1`. Use the returned
ID in the commands below.

Do not install production instances from `:latest` or a branch tag. NS8 takes
the displayed module version from the image tag and offers updates only to
instances with a SemVer version such as `0.3.0`; an instance installed from
`:latest` never receives update notifications.

## Update

Create and verify an NS8 application backup before every update. Then update
the instance from the NS8 Software Center or from the command line with the new
version number:

```bash
api-cli run update-module --data '{
  "module_url": "ghcr.io/platypuschan/ntfy-reworked:0.3.4",
  "instances": ["ntfy-reworked1"]
}'
```

An instance that shows the version `latest` was installed or updated from the
moving `:latest` tag. Update it once with the command above to a released
version; afterwards the Software Center offers new catalog versions again.
`force` is only needed for moving development tags such as `:latest`, because
it makes NS8 pull the image again even if the tag is already present locally.

Updates and restores are supported from the base version **0.2.2** onward.
Older releases of this module and the original NS8 ntfy module
(`geniusdynamics/ntfy`) cannot be updated to it, and their backups cannot be
restored. Install a new instance instead.

## Configure

Assume the instance ID is `ntfy-reworked1`. Configuration accepts:
- `host`: a fully qualified domain name for the application
- `http2https`: enable or disable HTTP to HTTPS redirection (true/false)
- `lets_encrypt`: enable or disable Let's Encrypt certificate (true/false)
- `server_config`: editable YAML options, excluding secrets and module-managed
  settings (optional; omitted settings preserve the existing configuration)
- `ios_push`: enable iOS wake-up forwarding (optional; omission preserves its state)

The web interface exposes `server_config` as a multiline editor under
**Advanced**. This is a filtered view of the private `config/server.yml`, not
the entire file. SMTP sender settings, upstream options, declarative auth
entries, private keys and other secret options are not returned to the UI.
Existing hidden values remain in the private file when saving the editor.
NS8 reverse-proxy options are reserved and cannot be overwritten in the editor.
Only canonical lowercase option names with hyphens are accepted.

The editor rejects duplicate keys at every nesting level, YAML aliases, merge
keys and protected options. Errors never echo YAML source lines. Comments and
formatting are not preserved in the filtered view, since comments can also
contain credentials. Ambiguous existing files must be corrected on the NS8
node before configuration can proceed. See [administration details](docs/administration.md).

Example `server.yml` for a private installation (replace the hostname):

```yaml
base-url: "https://ntfy.example.test"
cache-file: "/var/lib/ntfy/cache.db"
attachment-cache-dir: "/var/lib/ntfy/attachments"
auth-file: "/var/lib/ntfy/auth.db"
auth-default-access: "deny-all"
enable-login: true
enable-signup: false
```

Configure the module from the command line with a local `server.yml`:

```bash
server_config=$(<server.yml)
jq -n \
  --arg host "ntfy.example.test" \
  --arg server_config "$server_config" \
  '{host: $host, http2https: true, lets_encrypt: false, server_config: $server_config}' |
api-cli run module/ntfy-reworked1/configure-module --data -
```

The command starts ntfy, creates its Traefik route and saves `server.yml` in
`state/config/server.yml` with mode `0600`.

The config directory is mounted read-only at `/etc/ntfy` inside the ntfy
container. `configure-module` rejects a `server_config` that is ambiguous or invalid YAML, contains protected options,
or whose top level is not a mapping, with the `invalid_server_config`
validation error. Invalid ntfy option values are only detected by ntfy itself;
inspect the module service log after changing advanced settings.

## Data and backup

ntfy data (message cache, user and ACL database, web push database and
attachments) is stored in the `ntfy-data` Podman volume, mounted at
`/var/lib/ntfy`. Keep the `cache-file`, `auth-file`, `web-push-file` and
`attachment-cache-dir` paths below `/var/lib/ntfy`, otherwise the data is
neither persistent nor backed up.

Before a module backup, ntfy is stopped and its closed SQLite databases,
attachments and `server.yml` are copied into a temporary snapshot within the
`ntfy-data` volume. ntfy is started again before Restic uploads that snapshot.
After a successful backup, the temporary copy is removed. A failed upload can
leave the copy in the volume until the next backup, but does not leave ntfy
stopped. Allow enough free space in the volume for a second copy of the
databases. Attachments in a top-level `attachment-cache-dir` below
`/var/lib/ntfy` are hard-linked into the snapshot instead of copied, because
ntfy never modifies an attachment file after writing it.
A restore fails if the backup contains no such snapshot.

## Reverse proxy

The module is reachable only through the node's Traefik route. It therefore
always injects these runtime settings:

```text
NTFY_BEHIND_PROXY=true
NTFY_PROXY_FORWARDED_HEADER=X-Forwarded-For
```

They override the corresponding keys in `server.yml`. Traefik adds
`X-Forwarded-For` automatically. Do not add the NS8 Traefik or the loopback
address to `proxy-trusted-hosts`: ntfy uses that option only to strip
additional upstream proxy addresses from a multi-proxy forwarded chain. Leave
it unset for a normal NS8 installation. If another reverse proxy or CDN is in
front of NS8, configure its known IP addresses or CIDRs manually in
`proxy-trusted-hosts`.

## Get the configuration

Retrieve the current module settings with:

```bash
api-cli run module/ntfy-reworked1/get-configuration
```

## Users, tokens and topic access

Open **Users and tokens** in the NS8 module UI after configuring ntfy. It lists
users and roles, tokens (label and expiry only), and topic ACLs. Create users
with generated passwords, generate replacement passwords, create tokens with
an expiry, revoke tokens, and grant or remove topic permissions. Passwords and
tokens are masked by default; only newly generated values can be shown/copied.
The last administrator cannot be deleted through this page.

A new installation uses `deny-all`; regular users need explicit topic rights.
An ntfy administrator can access all topics. Tokens inherit their user's
permissions, so use separate integration users for different privileges.
Changing a password does **not** revoke existing tokens; revoke them separately.
Account changes briefly restart ntfy to refresh any configured access cache.

Existing declaratively provisioned accounts/tokens/ACLs remain intact and are
marked as configured on the server. Their protected properties are read-only
in the UI. They can still be maintained in the private `config/server.yml` on
the NS8 node. No implicit conversion or deletion of provisioned users occurs.

Creation results contain the new credential so the administrator can copy it.
List/configuration actions never return existing passwords or raw tokens.
The UI forgets the displayed credential on navigation/dismissal. **NS8 can
retain task results**, so this is a one-time display in the page, not a
cryptographic single-use retrieval guarantee. Do not share creation task results.
ntfy itself stores tokens in its authentication database; this module does not
change the upstream token storage format.

## iOS notifications

Enable **iOS instant notifications** in Settings to send wake-up requests via
`https://ntfy.sh`. An existing custom upstream URL is preserved. Disabling the
switch removes only the upstream URL, preserving an existing private upstream
token. The switch does not expose that token. A token is normally unnecessary
unless the upstream requires authentication or higher limits are needed.

The official iOS app needs the external push infrastructure for timely
notifications. The upstream receives `poll_request` messages, not the actual
notification contents. The app retrieves those contents from your server.

## Web Push

Generate a unique key pair inside your instance:

```bash
runagent -m ntfy-reworked1 podman exec ntfy-app ntfy webpush keys
```

Set `web-push-private-key` directly in the instance's private
`config/server.yml` on the NS8 node. Private keys are rejected by the UI
editor. Public options can be set in the editor:

```yaml
web-push-public-key: "<generated-public-key>"
web-push-file: "/var/lib/ntfy/webpush.db"
web-push-email-address: "admin@example.test"
```

Use your real contact address. Restart ntfy after direct file changes.

## Uninstall

To uninstall the instance:

    remove-module --no-preserve ntfy-reworked1

## SMTP

When the cluster smarthost is enabled, the module reads its current host, port,
username and password from the local NS8 Redis replica before every start. It
injects them as `NTFY_SMTP_SENDER_ADDR`, `NTFY_SMTP_SENDER_USER` and
`NTFY_SMTP_SENDER_PASS`. A `smarthost-changed` event restarts ntfy so changes
are applied without editing `server.yml`. The generated credential file has
mode `0600` and is not included in module backups.

If `server.yml` defines a top-level `smtp-sender-addr`, the NS8 smarthost is
ignored and all `smtp-sender-*` settings come from `server.yml`.

NS8 does not define a sender email address. If `smtp-sender-from` exists in
`server.yml`, the module preserves it. Otherwise it uses an email-shaped SMTP
username, or finally `no-reply@<ntfy-host>`.

ntfy's SMTP client supports plain SMTP and opportunistic STARTTLS, with normal
certificate verification. It does not support implicit SMTPS/TLS, commonly
used on port 465, nor disabling certificate verification. An NS8 smarthost
configured for implicit TLS is therefore not injected and a warning is written
to the service journal. If the NS8 smarthost is disabled, all manual
`smtp-sender-*` settings in `server.yml` remain effective.

SMTP sender options are hidden from the editor and preserved when saving.
Manual changes to these options must be made in the private `config/server.yml`
on the NS8 node. Existing explicit relay settings continue to take precedence.

Incoming email publishing is unrelated to the NS8 smarthost. ntfy supports
`smtp-server-*`, but this module currently publishes only HTTP; setting those
options alone does not make SMTP reachable. A separate module integration is
needed. [The implementation assessment](docs/administration.md#mail-to-push-on-ns8)
describes a recipient relay through the NS8 Mail application, avoiding a second
public port 25 listener.

## Debug

Inspect the running containers and ntfy logs on the NS8 node:

```bash
runagent -m ntfy-reworked1 podman ps
runagent -m ntfy-reworked1 podman logs ntfy-app
```

The module stores `server.yml` in the instance's `config/` directory. Avoid
sharing full environment dumps or configuration files without removing
passwords, tokens and private keys.

## Testing

The test scripts accept an NS8 leader node address and a module image URL:

```bash
./test-module-install.sh <NODE_ADDR> ghcr.io/platypuschan/ntfy-reworked:latest
./test-module-update.sh <NODE_ADDR> ghcr.io/platypuschan/ntfy-reworked:latest
```

The update test starts with the last published release of this module and
updates it without a forced pull, like the Software Center. It checks that a
cached message and a file in the `ntfy-data` volume survive.
`.github/scripts/previous-release` looks the release up in GHCR: the newest
stable tag that is not newer than `CATALOG_VERSION`.

Every change to `imageroot/`, `ui/` or `build-images.sh` needs a higher
`CATALOG_VERSION`. Validate fails otherwise
(`.github/scripts/check-catalog-version`), and so does the catalog promotion,
because an existing version tag is never overwritten.

Unit tests for actions and helpers need PyYAML, which the NS8 agent provides:

```bash
python3 -m pip install PyYAML==6.0.3
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Minimum NS8 core version

This module requires NS8 core **3.22.0** or newer. This conservative minimum
matches the core version recorded by the existing successful QEMU installation
[tests](https://github.com/Platypuschan/ns8-ntfy-reworked/actions/runs/37214325103);
compatibility with older cores has not been verified. The module image
declares this requirement in `org.nethserver.min-core`.

For a local CLI/HTTP/SMTP integration check against the packaged upstream version:

```bash
NTFY_TEST_BINARY=/path/to/ntfy-v2.28.0 \
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

This substitutes only Podman/systemd; it does not replace NS8 lifecycle/UI tests.
