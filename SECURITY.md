# Security policy

## Private vulnerability reporting

Do not disclose vulnerabilities in public issues, pull requests, or attachments.
On the GitHub repository, use **Security → Report a vulnerability** if private
vulnerability reporting is enabled. Include the affected revision, impact, and
minimal reproduction using synthetic data, with expected and actual behavior.
Do not send credentials, real league snapshots, screenshots, or OCR text.

If that option is unavailable, no alternate private maintainer contact is
published here. You may open a public issue asking only that a private reporting
channel be enabled, without vulnerability details. Wait for a verified private
channel before sharing the report. This policy does not imply that private
reporting is already enabled or promise a response or fix deadline.

## Scope and safe use

Reports should target the latest default-branch revision; no separate maintained
release branches are currently documented. See [README.md](README.md) for the
deployment model and data-privacy boundaries. This is a trusted-operator tool:
loopback is the default, and network deployments require the documented token,
host/origin configuration, HTTPS, and authenticated reverse proxy for multi-user
use. The standard-library server is not a hardened public service.

ESPN access is read-only. Screenshots and OCR are transient in app/browser memory;
browser and OS memory/swap are outside the app's deletion guarantees. Optional AI
is off by default and uses the limited payload documented in the README. Keep
ESPN credentials, provider keys, and deployment tokens out of commits and shared
logs. If a credential is exposed, revoke or rotate it with its issuer.

The local launcher creates ignored private `.local/config.json`, publishes only
loopback, and uses a read-only runtime config mount rather than storing secrets
in Docker's environment metadata. Setup does not connect to ESPN; the explicit
`espn` command is required. LLM is always disabled in this launcher. Browser
authentication uses an explicitly enabled Compose-only same-origin bootstrap
with a random nonce header, loopback Host restrictions and no public origin,
CORS permission or proxy forwarding headers. Page/bootstrap responses are
no-store/no-referrer and never logged. Launch URLs and browser-launch arguments
contain no token. Manual deployments retain the password form; bootstrap must
remain disabled for public use and rejects public/nonlocal configuration.
API authorization uses bearer headers. Anyone controlling the OS account, Docker engine or browser can
still access local credentials. See [SELF_HOSTING.md](SELF_HOSTING.md) for file
permissions, token lifecycle, reset and the untested real-Docker boundary.

The software is provided under the [MIT License](LICENSE), including its warranty
disclaimer. The license does not authorize access to anyone else's data.

## macOS desktop profile

The self-contained arm64 desktop app always starts demo with AI disabled. Its
native launcher uses an explicit environment allowlist; the backend binds only
to an ephemeral IPv4 loopback port and uses a fresh in-memory token plus the
existing guarded same-origin bootstrap. WebKit uses a nonpersistent data store.
ESPN requires the separate explicit Load ESPN snapshot action. Local setup saves
to the app-owned, nonsynchronizing Keychain item by default, or an explicitly
selected private 0700/0600 local file. No secret is returned to the setup UI.
Apple Vision OCR receives only Pillow-sanitized pixels over pipes. Closing the
window or quitting stops the backend process group; parent EOF also stops it.
No user browser profile, legacy project or existing credentials are discovered.
See [MACOS.md](MACOS.md) for first-open, storage/reset details and limits, and
[MACOS_VALIDATION.md](MACOS_VALIDATION.md) for actual mounted-bundle verification.

Release checks are disabled until release.json embeds a verified public repository.
Only the explicit Check now action requests fixed-host HTTPS release metadata;
it sends no auth/league data, follows no redirects and downloads no assets. A
separate user action opens a validated release page. Never embed a GitHub token.
SHA256SUMS detects corruption but does not independently authenticate a publisher.
The app remains unsigned/not notarized. Sparkle and EdDSA installation trust are
deferred in [RELEASE.md](RELEASE.md); no updater key or auto-installer exists.
Current lifecycle results are in [LIFECYCLE_VALIDATION.md](LIFECYCLE_VALIDATION.md).
