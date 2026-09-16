# ns8-ntfy

This is a NethServer 8 app for [ntfy](https://github.com/binwiederhier/ntfy).
https://ntfy.sh/

ntfy (pronounced notify) is a simple HTTP-based pub-sub notification service. It allows you to send notifications to your phone or desktop via scripts from any computer, and/or using a REST API. It's infinitely flexible, and 100% free software.

## Install

Instantiate the module with:

    add-module ghcr.io/geniusdynamics/ntfy:latest 1

The output of the command will return the instance name.
Output example:

    {"module_id": "ntfy1", "image_name": "ntfy", "image_url": "ghcr.io/geniusdynamics/ntfy:latest"}

## Configure

Let's assume that the ntfy instance is named `ntfy1`.

Launch `configure-module`, by setting the following parameters:
- `host`: a fully qualified domain name for the application
- `http2https`: enable or disable HTTP to HTTPS redirection (true/false)
- `lets_encrypt`: enable or disable Let's Encrypt certificate (true/false)
- `server_config`: the complete contents of ntfy's `server.yml` (optional for
  backward-compatible API calls)

The web interface exposes `server_config` as a multiline editor under
**Advanced**. The YAML file is the source of truth for user-managed ntfy
settings. A small set of `NTFY_*` environment variables is reserved for the
NS8 reverse-proxy and smarthost integrations described below. See the
[ntfy configuration reference](https://docs.ntfy.sh/config/#config-options).

Example `server.yml` suitable as a private starting point:

```yaml
base-url: "https://ntfy.domain.com"
cache-file: "/var/lib/ntfy/cache.db"
attachment-cache-dir: "/var/lib/ntfy/attachments"
auth-file: "/var/lib/ntfy/auth.db"
auth-default-access: "deny-all"
enable-login: true
enable-signup: false
```

Configure the module from the command line with a local `server.yml`:

```
server_config=$(<server.yml)
jq -n \
  --arg host "ntfy.domain.com" \
  --arg server_config "$server_config" \
  '{host: $host, http2https: true, lets_encrypt: false, server_config: $server_config}' |
api-cli run configure-module --agent module/ntfy1 --data -
```

The above command will:
- start and configure the ntfy instance
- configure a virtual host for Traefik to access the instance
- save `server.yml` as `state/config/server.yml` with mode `0600`

The config directory is mounted read-only at `/etc/ntfy` inside the ntfy
container. The configuration file is included in module backups. Invalid YAML
will prevent ntfy from starting; inspect the module service log after changing
advanced settings.

When upgrading from an older release, the update action converts existing
`NTFY_*` values to `server.yml` once and then removes those legacy variables.

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
You can retrieve the configuration with

```
api-cli run get-configuration --agent module/ntfy1
```
## Web Push Private and Public key Pairs
- enter into the container

`ssh ntfy1@localhost`

- run the command inside the container 
 `podman exec ntfy-app  ntfy webpush keys`
 ```
Web Push keys generated. Add the following lines to the Advanced YAML editor:

web-push-public-key: BIoV3b7JhU0y-4CeP32PmFcVTQB5_rAfC99S8684FI72pC50GvICMwmTn1TLcqqbiREcYLmgQVMvTRDS75Bpg_E
web-push-private-key: BrOm7ZuMouXzV8lT8xoC2wCSa7wscaZ9_JN3oKQama8
web-push-file: /var/cache/ntfy/webpush.db # or similar
web-push-email-address: <email address>

```
## Uninstall

To uninstall the instance:

    remove-module --no-preserve ntfy1

## SMTP

When the cluster smarthost is enabled, the module reads its current host, port,
username and password from the local NS8 Redis replica before every start. It
injects them as `NTFY_SMTP_SENDER_ADDR`, `NTFY_SMTP_SENDER_USER` and
`NTFY_SMTP_SENDER_PASS`. A `smarthost-changed` event restarts ntfy so changes
are applied without editing `server.yml`. The generated credential file has
mode `0600` and is not included in module backups.

NS8 does not define a sender email address. If `smtp-sender-from` exists in
`server.yml`, the module preserves it. Otherwise it uses an email-shaped SMTP
username, or finally `no-reply@<ntfy-host>`.

ntfy's SMTP client supports plain SMTP and opportunistic STARTTLS, with normal
certificate verification. It does not support implicit SMTPS/TLS, commonly
used on port 465, nor disabling certificate verification. An NS8 smarthost
configured for implicit TLS is therefore not injected and a warning is written
to the service journal. If the NS8 smarthost is disabled, all manual
`smtp-sender-*` settings in `server.yml` remain effective.

Incoming email publishing is unrelated to the NS8 smarthost. Configure its
`smtp-server-*` options directly in the Advanced YAML editor.

## Debug

some CLI are needed to debug

- The module runs under an agent that initiate a lot of environment variables (in /home/ntfy1/.config/state), it could be nice to verify them
on the root terminal

    `runagent -m ntfy1 env`

- you can become runagent for testing scripts and initiate all environment variables
  
    `runagent -m ntfy1`

 the path become : 
```
    echo $PATH
    /home/ntfy1/.config/bin:/usr/local/agent/pyenv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/usr/
```

- if you want to debug a container or see environment inside
 `runagent -m ntfy1`
 ```
podman ps
CONTAINER ID  IMAGE                                      COMMAND               CREATED        STATUS        PORTS                    NAMES
d292c6ff28e9  localhost/podman-pause:4.6.1-1702418000                          9 minutes ago  Up 9 minutes  127.0.0.1:20015->80/tcp  80b8de25945f-infra
d8df02bf6f4a  docker.io/library/mariadb:10.11.5          --character-set-s...  9 minutes ago  Up 9 minutes  127.0.0.1:20015->80/tcp  mariadb-app
9e58e5bd676f  docker.io/library/nginx:stable-alpine3.17  nginx -g daemon o...  9 minutes ago  Up 9 minutes  127.0.0.1:20015->80/tcp  ntfy-app
```

you can see what environment variable is inside the container
```
podman exec  ntfy-app env
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
TERM=xterm
PKG_RELEASE=1
MARIADB_DB_HOST=127.0.0.1
MARIADB_DB_NAME=ntfy
MARIADB_IMAGE=docker.io/mariadb:10.11.5
MARIADB_DB_TYPE=mysql
container=podman
NGINX_VERSION=1.24.0
NJS_VERSION=0.7.12
MARIADB_DB_USER=ntfy
MARIADB_DB_PASSWORD=ntfy
MARIADB_DB_PORT=3306
HOME=/root
```

you can run a shell inside the container

```
podman exec -ti   ntfy-app sh
/ # 
```
## Testing

Test the module using the `test-module.sh` script:


    ./test-module.sh <NODE_ADDR> ghcr.io/geniusdynamics/ntfy:latest

The tests are made using [Robot Framework](https://robotframework.org/)

## UI translation

Translated with [Weblate](https://hosted.weblate.org/projects/ns8/).

To setup the translation process:

- add [GitHub Weblate app](https://docs.weblate.org/en/latest/admin/continuous.html#github-setup) to your repository
- add your repository to [hosted.weblate.org]((https://hosted.weblate.org) or ask a nethserver developer to add it to ns8 Weblate project
