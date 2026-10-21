# ntfy administration and NS8 integration

Assessment and implementation: 2026-10-21, ntfy v2.28.0.

## Configuration ownership

`config/server.yml` stays the private source of truth and remains part of the
existing consistent backup snapshot. No new secret file needs separate restore
or update migration. Existing private values are filtered from get-configuration
and merged back server-side on configure-module. No masked placeholder is sent
back as a real credential. Invalid existing YAML fails closed; error text omits
source lines. YAML comments are excluded from the editable representation.
The browser uses the same reserved-option policy and rejects invalid YAML before
creating a task; the backend validates independently for direct API clients.

Reserved settings include `smtp-sender-*`, `upstream-*`, `auth-users`,
`auth-tokens`, `auth-access`, `database-url`, private credential keys and the
reverse-proxy options injected by NS8. Protected keys cannot be inserted again
in the editor. Unknown spelling variants are not a second configuration path:
new YAML must use lowercase option names with hyphens.

Users created from the module page use ntfy's native authentication database.
No password is saved by the module, and credentials are never returned by list
or configuration actions. Existing declaratively provisioned objects remain
read-only where ntfy disallows CLI changes. The page is part of the existing
NS8 administrative interface; ntfy application accounts do not authorize NS8
module actions.

## Account administration

Actions invoke the CLI shipped with the pinned ntfy image, using argument arrays
rather than shell interpolation. Passwords are generated server-side and
forwarded through an inherited environment variable whose value is absent from
argv. Raw CLI errors and token-list output are captured and never forwarded to
NS8 logs. Token list responses use SHA-256 opaque identifiers; revocation resolves
the identifier internally, checks the owner and rejects provisioned tokens.

Account mutations, backup snapshot creation and restore are serialized by a
shared module-local file lock, so account-related service restarts cannot reopen
the databases during a stopped-database snapshot. The last admin
cannot be deleted and exceeding ntfy's 60-token limit is rejected rather than
silently pruning an older token. Native CLI writes avoid maintaining a second
user database or editing ntfy's SQLite schema directly. The service is restarted
after mutation because the configured server may cache access rules. New
credentials are still returned if only that restart fails, with a warning flag.

The creation response necessarily contains the new credential. NS8's normal
task interface can retain that response, so one-time display is an interface
behavior, not a guarantee that no administrator can retrieve the task output.
The page does not save credentials to localStorage or re-fetch them in lists.
ntfy's own token storage is unchanged. Password replacement does not revoke
existing tokens.

## iOS instant delivery

The upstream implementation is already present. The change is limited to a
boolean setting, a UI switch and server-side handling of `upstream-base-url`.
Enabling uses an existing upstream or defaults to `https://ntfy.sh`. Disabling
removes the URL without deleting its optional token. No additional container,
port or push service is needed. The optional token stays out of UI responses.

Actual iOS/APNS delivery was not tested on a device. External upstream
availability, Internet access and the app's connectivity still matter.

## Mail-to-push on NS8

**Feasible for authenticated internal senders with moderate module work; not
enabled by this change. Public incoming mail needs additional domain handling.**

ntfy v2.28.0 has a lightweight incoming SMTP server. It turns mail into a normal
publish request and uses normal topic authorization. The source supports both
SMTP AUTH PLAIN and `topic+token@domain` addresses. A local runtime check confirms
that deny-all rejects anonymous mail and that an authorized topic token permits
publishing. There is no reason to grant global anonymous write access.

The current NS8 module only publishes HTTP on localhost and cannot receive
external SMTP by adding YAML settings alone. The preferred integration when NS8
Mail is present is:

1. Keep public mail reception, filtering and port 25 with the Mail application.
2. Expose ntfy's SMTP listener on an allocated non-conflicting internal port.
3. Add a recipient/domain relay rule in Mail targeting that endpoint. NS8 Mail
   supports a target hostname/port and optional SMTP authentication.
4. Use a dedicated ntfy integration user with write-only rights to selected
   topics. Avoid a full ntfy administrator token.

This relay path is established for authenticated or IP-authorized senders.
A recipient relay rule changes the next hop; it does **not** itself grant public
relay authorization for a new external domain. For arbitrary Internet senders,
the Mail application must also accept that domain and its recipients and route
them to ntfy instead of a local mailbox. Current Mail domain actions expose
local-domain options, not a general remote-transport setting. That additional
public-reception integration is therefore not established by the relay UI alone
and needs a separate implementation/test. Merely adding a local domain can
cause local mailbox delivery or unknown-recipient rejection instead of forwarding.

For Mail and ntfy on the same node, localhost can be considered only after
checking the Mail container network context; another container's localhost is
not automatically the host. For different nodes, a private reachable address
and firewall rule are needed. The SMTP hop must not send credentials over an
untrusted network. ntfy's lightweight SMTP server must not be assumed to provide
an Internet-facing authenticated TLS submission service.

A production module integration must allocate and persist the listener port,
validate the domain, bind only intended interfaces, handle firewall lifecycle,
backup/restore/clone conflicts, and remove relay/firewall resources cleanly.
Multiple module instances and an existing Mail service must coexist. Changes to
the Mail application's relay rules should be a separate explicitly scoped step.
Without Mail, an external MTA relay or a dedicated receiving configuration is
needed; it is not supplied by NS8's outgoing smarthost setting.

Tokens in recipient addresses can appear in mail headers and relay logs. Where
possible, use authenticated internal forwarding instead, and verify the precise
TLS/network path during the NS8 integration test.

## Verification and sources

- Unit tests cover duplicate/merge/alias rejection, protected key preservation,
  iOS toggling, redacted lists, credential generation, owner-bound revocation,
  provisioned accounts, token limits and last-admin protection.
- Optional `NTFY_TEST_BINARY` integration runs native CLI, SQLite, HTTP and SMTP
  against v2.28.0, substituting only the Podman/systemd process boundary.
- Browser-side YAML validation has three additional Node test groups.
- UI lint and production build are separate checks. No deployed NS8 UI test,
  NS8 update/restore VM test or iOS device test was performed for this change.

Sources:

- [Pinned ntfy configuration](https://github.com/binwiederhier/ntfy/blob/v2.28.0/server/server.yml)
- [Pinned user CLI](https://github.com/binwiederhier/ntfy/blob/v2.28.0/cmd/user.go)
- [Pinned token CLI](https://github.com/binwiederhier/ntfy/blob/v2.28.0/cmd/token.go)
- [Pinned ACL CLI](https://github.com/binwiederhier/ntfy/blob/v2.28.0/cmd/access.go)
- [Pinned SMTP implementation](https://github.com/binwiederhier/ntfy/blob/v2.28.0/server/smtp_server.go)
- [Mail relay-domain generation](https://github.com/NethServer/ns8-mail/blob/main/postfix/usr/local/bin/reload-config)
- [Mail domain schema](https://github.com/NethServer/ns8-mail/blob/main/imageroot/validator-definitions.json)
- [NS8 Mail relay rules](https://docs.nethserver.org/docs/administrator-manual/applications/mail)
- [NS8 firewall](https://docs.nethserver.org/docs/administrator-manual/configuration/firewall)
- UI reference: [Termine2 settings at 29838a3](https://github.com/Platypuschan/ns8-termine2/blob/29838a38c53e5ac3e313ebd94e07a0b774508709/ui/src/views/Settings.vue)
