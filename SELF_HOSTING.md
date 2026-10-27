# Run Trade Room on your own computer

Apple Silicon Mac users can use the self-contained [desktop app and DMG](MACOS.md)
without the source/Docker prerequisites below. This guide describes the separate
source-based Compose launcher.

The recommended launcher starts a **synthetic demo**, with **LLM disabled**. It
uses Docker on this computer and publishes only `127.0.0.1`. It does not create a
shared league service, discover accounts, upload configuration, or contact ESPN.
Each member can run their own copy. This is for a trusted local desktop session;
anyone with access to your OS account or Docker engine can inspect its settings.

## First launch

Install **Python 3.11 or newer** and **Docker Desktop with Docker Compose v2**
on macOS/Windows. On Linux, use Docker Engine plus the Compose v2 plugin and a
graphical browser (`xdg-open`). Start Docker before continuing. Windows users
should run Docker Desktop in Linux-container mode. You do not need Node,
Tesseract, pip, or a Python virtual environment on the host for the launcher;
the app and OCR dependencies are installed inside the image.

Extract/copy this repository to a directory you own, outside a shared or synced
folder. Open a terminal in that directory:

| macOS / Linux | Windows PowerShell or Command Prompt |
| --- | --- |
| `./start.sh` | `.\start.cmd` |

If executable permissions were lost when extracting, run `sh start.sh`. The
wrappers probe interpreter versions and skip Python older than 3.11, including
when an older `python3` appears first on PATH. They check versioned executables
3.11–3.15 and `python3`/`python` across PATH; Windows first checks `py` selectors.
You can also use your installed newer interpreter directly:
`python3.11 scripts/local.py` (substitute its installed version).

The first run creates `.local/config.json`, generates a random 256-bit deployment
token, builds the image, starts the demo, waits for readiness and authentication,
then opens your default graphical browser. The first build may take several
minutes and needs internet access for the base image and dependency downloads.
The running synthetic demo needs no ESPN or provider access. Docker build and
error output is captured rather than displayed because it can contain settings.

You should see **SYNTHETIC DEMO**, **AI DISABLED**, and six synthetic teams. Choose
your team and scan, or use the manual workbench. No account/cookie is needed for
the demo. Closing the browser does not stop the container.

The local configuration is not encrypted. On macOS/Linux the directory is mode
`0700` and the file `0600`; on Windows the launcher uses the current user's SID
and `icacls` to remove inherited/other grants. Failure to secure the file stops
setup. Config writes use a private temporary file and atomic replacement.
Symlinks and Windows reparse points are rejected. `.local/` is excluded from Git
and Docker's build context; no config file is copied into the image. The config
is mounted read-only at runtime. The container reads it into app memory; secrets
are never supplied as Docker environment settings or command arguments, so they
are not duplicated in Docker's saved environment metadata. On macOS/Linux the
container runs with your non-root user/group IDs so it can read your `0600`
file; run the launcher without sudo. Windows uses container UID/GID 10001 and
Docker Desktop's host-file sharing. Docker/OS administrators can still read the
mounted config and process memory. Rootless/user-remapped Docker file ownership
may require manual setup instead; native bind-mount behavior was not tested.

Do not share the config file. Browser launch URLs contain no token. Manual deployments may also put
secrets in Docker inspection or `docker compose config` output. Avoid shell tracing
(`set -x`) and process-monitor captures while launching. Other files in `.local/`
are not managed by this launcher. Keep private backups only if you need them.

## Everyday controls

All commands run in the repository directory; the wrappers also work when called
by their full path from another directory.

| Task | macOS / Linux | Windows |
| --- | --- | --- |
| Start demo | `./start.sh demo` | `.\start.cmd demo` |
| Reopen already running app with authentication | `./start.sh open` | `.\start.cmd open` |
| Start without opening browser | `./start.sh demo --no-open` | `.\start.cmd demo --no-open` |
| Use a different port | `./start.sh demo --port 8001` | `.\start.cmd demo --port 8001` |
| Stop; keep local settings | `./start.sh stop` | `.\start.cmd stop` |
| Stop and delete local settings/token | `./start.sh reset` | `.\start.cmd reset` |

Stop before switching sources or changing ports. Starting on an occupied port
fails with guidance to use `open`, `stop`, or another port. One launcher-managed
instance is supported per Docker engine, using project name `trade-room-local`.
Always use the same repository copy to manage that instance. The saved port is
used by `open`; the port always binds to IPv4 loopback. No LAN or public listening
option is provided. The container listens on its own `0.0.0.0:8000`, which Docker
maps to host `127.0.0.1` only. Containers are not configured to restart on boot.

`stop` removes the container/network while retaining private config and the
built image/cache. `reset` first requires a successful stop, then deletes only
`.local/config.json`, including saved ESPN cookies and the token. It also works
with a missing/corrupt config or a missing `.local/` directory: shutdown uses
`scripts/compose-stop.yaml`, which identifies the same project/service without
requiring the config bind mount. It creates no replacement config. If stop
fails, existing config is retained. Other `.local/` files, Docker images/cache and
private backups are retained. The next launch generates a new token. Deleted
files are not securely erased from SSDs, snapshots or backups. To remove the
whole installation, stop/reset, then remove your repository copy and its private
backups. Docker Desktop can remove the unused image/build cache separately.

## Browser authentication

The launcher opens only `http://127.0.0.1:8000/` (or your saved port). The token
never enters `open`/`xdg-open` arguments or Windows `os.startfile`, and is absent
from the URL, query and fragment.

Only the Compose container entry point enables `--compose-local-bootstrap`.
In this mode the page contains a random 256-bit nonce, separate from the access
token. Its JavaScript sends that nonce in `X-Trade-Room-Bootstrap` to the
same-origin `/api/local-bootstrap` endpoint and receives the token in a JSON
response. The endpoint requires a loopback Host, a loopback-only Host allowlist,
no configured public origin, the exact nonce header, and `Sec-Fetch-Site:
same-origin` or an exact matching `Origin`. Conflicting origins, cross-site or
same-site fetch metadata, and proxy forwarding headers are rejected. There is
no CORS permission or preflight grant. Public-origin/nonloopback-host
configuration cannot enable this mode. The wildcard bind inside the isolated
Compose container is supported only with loopback Host restrictions; host
publishing remains `127.0.0.1`. Never expose or reverse-proxy this local profile.

Page and bootstrap responses carry `Cache-Control: no-store` and
`Referrer-Policy: no-referrer`; request logging is suppressed. The browser uses
same-origin fetch with no cache, referrer, cookies or redirects, retains the
token only in JavaScript memory, and sends subsequent API requests with
`Authorization: Bearer …`. It uses no local/session storage or token cookie.
Reload clears memory and repeats the guarded exchange. `open` reopens the same
plain URL. Legacy access-token fragments are scrubbed and ignored.

Manual deployments keep bootstrap disabled and use the password-token form
when an access token is configured. A failed local bootstrap also falls back
to that form. Readiness verifies `/api/session` using the bearer header; the
browser is not opened if source, LLM-off state or token checks fail. Launcher
HTTP checks bypass system proxies and reject redirects. Use a trusted browser
and OS account: local browser extensions and other processes with local access
can inspect credentials. This is local bearer-token access, not member accounts.

## Optional: operator-guided ESPN setup

Only an authorized league operator should do this, on their own computer. There
is no central settings service and no credential-collection web form. Start with
the demo to confirm the installation works, then run:

| macOS / Linux | Windows |
| --- | --- |
| `./start.sh setup-espn` | `.\start.cmd setup-espn` |

The guide asks for the season year, a hidden league ID, and whether the league
is private. For a private league it asks for `espn_s2` and `SWID` in hidden input
prompts. In your own signed-in ESPN browser, open developer tools, find the
Storage/Application section, then the Cookies section for ESPN. Copy only your
own `espn_s2` value and `SWID` value; retain braces in SWID if present. The league
ID is the numeric `leagueId` visible in your league page address. Do not copy the
whole cookie header. Cookie availability depends on your account/browser; the
app cannot recover or discover these values for you. Clear your clipboard after
entry. Public leagues can select `n` and save empty cookie values.

Secrets do not appear as you type and no existing value is displayed. If hidden
input is unavailable, the guide stops instead of reading echoed/piped secrets.
Use a normal interactive Terminal/PowerShell window. Never put cookies in command
arguments, paste them into chat/issues, or use a shell transcript. Ctrl+C cancels;
invalid/incomplete input preserves previous settings. Rerunning the guide
replaces all ESPN settings, allowing cookie rotation or a public-league switch.

Setup saves only the ignored private config. **It does not test credentials or
contact ESPN.** When ready for a real ESPN read, explicitly stop the demo and start:

| macOS / Linux | Windows |
| --- | --- |
| `./start.sh stop` | `.\start.cmd stop` |
| `./start.sh espn` | `.\start.cmd espn` |

Only that explicit `espn` action loads your league from ESPN, read-only, once at
server startup. LLM remains disabled. Repeat stop/espn to refresh the snapshot.
The default/no-argument launcher always selects **demo**, even after saving ESPN
settings, and does not apply ESPN credentials to the demo app environment. The
private config mount can contain saved ESPN settings in either mode; only the
explicit `espn` bootstrap selects them for the adapter. The launcher also strips
inherited `APP_*`, `ESPN_*`, `LLM_*` and `COMPOSE_*` settings; the explicit Compose
env file is empty, so a stray `.env`/Compose override cannot opt into live data
or AI. Saved secrets are read literally from JSON into runtime app memory, never
parsed as shell code, Compose interpolation or dotenv text. No provider key is
collected by this launcher.

ESPN cookies may expire; rerun setup locally if necessary. This unofficial ESPN
adapter has only synthetic-response validation, not live private-league testing.
See [README](README.md#optional-espn-snapshot) for supported projections, missing
data and roster limitations. Do not use real ESPN/provider credentials for
development or bug reproduction.

## Troubleshooting

- **Docker missing / not running:** start Docker Desktop or the local engine,
  verify `docker compose version`, and rerun. A failed launch retains config.
- **Remote Docker context:** this launcher accepts only a local Unix-socket or
  Windows named-pipe endpoint. Unset `DOCKER_HOST`, `DOCKER_TLS_VERIFY` and
  `DOCKER_CERT_PATH`, and select a local context in Docker Desktop. Do not point
  it at SSH, TCP, a cloud engine, or an exposed daemon.
- **Port in use:** `open` reopens your app; otherwise stop the conflicting app
  or use `demo --port 8001`. Stop the existing Trade Room before changing port.
- **Build/readiness failed:** check Docker Desktop engine status, disk space,
  internet access for build dependencies and container state. Use `stop`, then
  retry `demo`. The launcher intentionally suppresses raw Docker output; never
  share raw inspect/config/log output that contains private settings.
- **Browser not opening:** the container may already be ready. Run `open` from
  your graphical desktop terminal. On Linux ensure `xdg-open` is available.
  Ordinary visits and reloads authenticate automatically only in the local
  Compose profile; manual deployments use the token form.
- **ESPN mode not ready:** retry the demo first. Reenter your own settings if
  needed. No live integration was validated here. Startup errors do not echo
  provider responses or credentials.
- **Config corrupt or compromised token:** `reset` then relaunch; enter ESPN
  settings again if desired. If Docker is unavailable, retain the config until
  you can run reset; deleting it alone does not remove a running container or
  invalidate that container's token.

## Manual setup fallback

Docker is optional. The [manual Python instructions](README.md#manual-python-setup-fallback)
create a virtual environment and launch the synthetic app bound to loopback.
Install Pillow and Tesseract locally to enable OCR. That manual app invocation
does not load `.env` or `.local/config.json` automatically. The standalone CLI
also uses only its process environment. Manual process-manager/container setup
can inject settings from an ignored local `.env` using `.env.example` as the
placeholder template. Never `source` an untrusted env file or put secrets on a
command line. If you configure a manual deployment token, enter it in the app's
password field. The launcher `open` action checks its own saved token and is
intended for its Compose instance. Leave `--compose-local-bootstrap` off for
manual or public deployments.

The [manual Docker example](README.md#self-hosting) keeps host publishing on
loopback and offers no automatic browser/config setup. The Compose file uses
JSON-form YAML so the offline suite can parse its full structure without another
dependency. Use the wrappers rather than bare `docker compose up`: they validate
config, reject remote contexts, fix the project/files, and supply a token.
Advanced HTTPS reverse-proxy hosting remains documented in README and requires
separate operator configuration; these launchers do not publish a public site.

## Validation boundary

The offline suite parses the Compose structure, exercises the scripts through
an executable fake-Docker harness, and tests real local HTTP authentication plus
the synthetic UI controller. It does **not** validate Docker's own Compose parser,
daemon networking, image build, container startup, Windows ACL enforcement or
graphical browser behavior on every OS. **Docker was unavailable during this
implementation; no real image/build or container run was tested.**

Run the commands in [CONTRIBUTING](CONTRIBUTING.md#local-checks). The fake harness
is included in `scripts/offline_tests.py` discovery; do not run it with real
settings. On a Docker-equipped desktop, use demo mode only to check the build,
loopback port, browser authentication, reload/open, stop/reset and hidden-input
setup with dummy credentials before choosing any live source. See
[VALIDATION](VALIDATION.md) for recorded results and remaining limitations.
