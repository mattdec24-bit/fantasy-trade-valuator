# Contributing

Small, focused issues and pull requests are welcome. Describe the problem, the
behavior change, and how you verified it. Report vulnerabilities privately as
described in [SECURITY.md](SECURITY.md).

See [MAINTAINING.md](MAINTAINING.md) for the file map, adding runtime files and
the separate source/scheduler/app update surfaces. [RELEASE.md](RELEASE.md) owns
versioning and release instructions; generated binaries stay outside this repo.

## Local checks

Follow [README.md](README.md#manual-python-setup-fallback) to create a Python 3.11+ virtual
environment and install the pinned requirements. Install Tesseract with English
language data and Node.js (CI uses Python 3.13 and Node 22), install workflow validators as described in MAINTAINING.md, then run:

```sh
.venv/bin/python scripts/preflight.py --workflows
```

Use synthetic fixtures and mocked remote transports for regression coverage.
The Python runner and smoke reject non-loopback networking; the smoke uses real
local Tesseract. The UI check uses a synthetic DOM, not browser rendering. CI
downloads tools and dependencies during setup, then runs only these offline
checks; it requires no configured secrets and performs no deployment.

The Python suite also parses the JSON-form YAML Compose file and exercises the
launcher against an executable offline fake Docker and real loopback HTTP app.
It covers config permissions/atomic writes, hidden-input failure, environment
isolation, readiness, token-free browser-launch arguments, guarded same-origin
bootstrap, manual password fallback, Python version selection, missing-config
stop/reset and secret-safe errors. Build-context checks exclude `.git`, tests
and CI-only content as well as private settings.
The fake harness does not prove a real image build or Docker networking works.
Windows ACL/browser branches are mocked; validate them on a Windows desktop
before claiming native end-to-end support. See [SELF_HOSTING.md](SELF_HOSTING.md).

## Data and license

Keep fixtures, screenshots, issue reports, logs, and PR attachments synthetic.
Never include real league snapshots, private rosters, OCR text, ESPN cookies
(`ESPN_S2` / `ESPN_SWID`), API keys, or deployment tokens. Keep local credentials
in the process environment, an ignored `.env` file, or the launcher's private
ignored `.local/config.json`; the app does not load either file automatically.
Keep `.local/` excluded from Git and Docker build contexts. Preserve the read-only ESPN behavior, local screenshot
processing, and explicit optional-AI opt-in described in the README.

Contributions are provided under the repository's [MIT License](LICENSE).
Include only material you have permission to contribute; the software license
does not grant rights to third-party data or screenshots.

## macOS package

`python3 scripts/build_macos.py` builds an unsigned Apple Silicon app and DMG
from pinned public runtime artifacts and an explicit source allowlist. It needs
Apple command-line compiler tools only on the build host. Use the mounted app's
Python with `scripts/verify_macos.py <bundle> --ui` to run the actual native
WebKit workflow, Vision OCR and window-close shutdown in a fresh synthetic home
with external Python networking blocked. `scripts/audit_macos.py <bundle>
--compare <mounted-bundle>` checks dependency paths, architecture, links and
content hashes. See MACOS.md, RELEASE.md and LIFECYCLE_VALIDATION.md for complete commands and
verification limits. No signing, commit or publication is part of the builder.
