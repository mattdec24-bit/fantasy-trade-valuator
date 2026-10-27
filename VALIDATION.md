# Workflow completion validation

> Historical validation before lifecycle changes. Current checks and artifacts
> are recorded in [LIFECYCLE_VALIDATION.md](LIFECYCLE_VALIDATION.md). The old
> external `legacy-build/` and `legacy-dist/` snapshots were deleted on
> 2026-10-21; the hashes below are historical, not current artifact hashes.

The subsequent self-contained macOS app/DMG build and actual mounted native
WebKit/OCR/clean-stop checks are recorded in [MACOS_VALIDATION.md](MACOS_VALIDATION.md).
The older source/Docker results below retain their original scope.

Validated on 2026-10-20 in this sanitized repository with Python 3.14.7, Pillow 12.3.0, Node v22.22.3 and Tesseract 5.5.2. Pillow is pinned to this tested version in requirements.txt. All league data, settings and screenshots were synthetic. No live ESPN/provider calls were made. Existing staged starter files were preserved; this work did not stage, commit, push or publish anything.

## Latest local-only launcher verification

The macOS/Linux `start.sh` and Windows `start.cmd` use the shared standard-library
launcher. Default demo, LLM-off policy, private config/token generation, guided
hidden ESPN input, authenticated browser opening, explicit ESPN selection and
stop/reset are implemented. Full operator instructions are in
[SELF_HOSTING.md](SELF_HOSTING.md), with manual Python/Docker fallback in README.

| Check | Latest result |
| --- | --- |
| `python3 scripts/offline_tests.py` | **60 tests passed**, including 15 launcher regressions and guarded-bootstrap HTTP tests |
| `node tests/test_ui.cjs` | Passed Compose nonce bootstrap, manual password form/fallback, existing UI workflow and response-race checks |
| `python3 scripts/smoke.py` | Passed existing synthetic HTTP, evaluation, mocked-AI and real Tesseract smoke |
| Python compileall, Node syntax, `sh -n start.sh` | Passed |
| Compose structure / build context | Full JSON-form YAML parsed; loopback-only publish, read-only config mount/root filesystem, non-root UID/GID, LLM-off settings and fixed command checked; bind-free shutdown manifest and `.git`/test/CI exclusions checked |
| Fake Docker | Executable harness passed default launch, explicit source configuration, hostile inherited settings, redacted failures, open/no-open, stop and reset, including missing config/directory with required-bind checks |

Secret-safe regressions cover random first-run tokens and reuse; `0700`/`0600`
permissions and mocked Windows SID ACL commands; private atomic replacement and
failed-write preservation; config/link rejection; hidden-input failure instead
of echoed fallback; invalid/public/private ESPN setup; literal cookie characters;
no ESPN/provider call during setup; and no credentials in Docker environment
metadata or command arguments. Browser-opening checks assert that macOS `open`,
Linux `xdg-open` and Windows `os.startfile` receive only the plain local URL,
never the token, even in a fragment. The container bootstrap reads the private bind
mount into app memory, applies ESPN settings only for explicit ESPN mode, and
forces LLM off. Bootstrap tests replace app startup, never selecting live ESPN.

The fake-Docker harness runs actual child commands and validates the supplied
Compose project/files and rendered settings. A real ephemeral loopback app
stands in for the container; its LLM state is stubbed to the fixed container
policy because the parent deliberately contains hostile provider environment
settings. Separate bootstrap/readiness tests validate those boundaries. Docker
failure output deliberately contains synthetic secrets and remains suppressed.
Reset preserves valid or corrupt config unchanged if stop fails, recovers corrupt
config, removes only the managed config after success, preserves unrelated local
files, and rotates the token on next launch. Missing config/directory succeeds
without creating replacement config: down uses the same project/service through
a bind-free manifest. The fake rejects required binds with absent sources.
The shell wrapper is executed from a different directory with spaces in its
path, propagates the child's exit status, and skips an old first-on-PATH Python
to find a supported versioned executable, later `python3`, or `python`.
Windows version probes and candidate selection receive static checks only.

The actual UI controller bootstraps only when the page supplies a nonce, sends
it in a custom header with same-origin/no-store/no-referrer/no-redirect options,
then uses bearer headers. Manual deployments retain the password form and clear
the password field after submission; bootstrap rejection, network failure or an
invalid response falls back to that form. Legacy authentication fragments are
removed before fetch and ignored; workbench anchors remain. No token is persisted.
Reloading the Compose page repeats bootstrap; manual reloads require token entry.

Real loopback HTTP checks verify a random page nonce distinct from the token;
matching Origin or same-origin fetch metadata succeeds. Missing/wrong nonce,
missing same-origin evidence, cross-origin/malformed Origin, cross-site/same-site
metadata, duplicate headers, nonloopback Host and proxy forwarding headers fail.
Preflight grants no CORS permission. Bootstrap/page responses are no-store and
no-referrer, and stdout/stderr remain empty. Other API resources still require
bearer authentication. Disabled mode refuses bootstrap even with valid bearer
authentication, emits no nonce, and public-origin/nonloopback-host configuration
with bootstrap enabled fails before source loading.
Readiness bypasses HTTP proxies, rejects redirects, checks source/LLM state and
uses the authenticated `/api/session` endpoint without reading league data.
Missing/wrong tokens fail; a query-string token does not authenticate.

**Docker and Podman were unavailable: no real image build, Docker Compose parser run,
container startup, bind-mount enforcement or Docker port mapping was tested.**
Windows batch/ACL/browser branches received static or mocked checks, not native
Windows execution. Graphical browser opening/rendering was not exercised.
Rootless/user-remapped Docker file ownership and native Docker Desktop file
sharing remain deployment checks. No live integration or public service was
started. Tests used private temporary directories; the repository's existing
`.local/` remains empty.

## Behavior verified

- Manual evaluation results are invalidated when either team, selected players, or the manual AI preference changes, including screenshot-driven perspective updates. Delayed successes and failures cannot restore obsolete results; changing a selection back still invalidates its old request, and only the newest evaluation can render.
- PNG and JPEG inputs containing ICC profiles, EXIF, DPI, and text/comments are decoded and copied into a fresh RGB image. Tests inspect the actual Tesseract stdin bytes: pixel values are preserved and the output contains only PNG IHDR/IDAT/IEND chunks, with no image info or EXIF.
- IPv6 loopback binds with AF_INET6 and serves real local HTTP requests at `[::1]`. Matching HTTP origins pass and HTTPS on the same authority fails. The unavailable-IPv6 branch explicitly rejects startup; non-loopback IPv6 still requires a deployment token.
- Direct HTTP requires matching origin scheme, hostname and effective port. A single explicit `APP_PUBLIC_ORIGIN` / `--public-origin` permits HTTPS reverse-proxy origins while rejecting HTTP downgrade, wrong hosts/ports and malformed origins. The request's `Host` hostname must match the public origin hostname even if both hostnames are allowed, with or without an `Origin` header. The flag overrides the environment setting; host checks and origin-less health requests with the public hostname remain supported. Forwarding headers cannot establish trust. Invalid public origins fail before source loading.
- Uploading an own-team lineup screenshot opens full-roster review. Unambiguous strong matches suggest a team; mixed/empty recognition requires team selection. Users can correct detection, see snapshot players missed by OCR, explicitly acknowledge the full roster, and automatically scan every opposing team. No partner or outgoing/incoming selection is required. Manual trade evaluation remains independent.
- OCR-origin candidate requests require literal confirmation and the exact full snapshot roster. Missing, duplicate, foreign and stale roster identities are rejected before search or AI. Closing/discarding review clears OCR state; changing the selected team revokes acknowledgement.
- Optional summaries contain provider-written text, returned from the response rather than selected from local sentence templates. Only four numeric deltas and request-local labels enter model input. Payload tests poison private fields and verify exclusion of names, team/player/league IDs, trade hashes, rosters, screenshots, OCR, warnings, arbitrary text and credentials. The provider key appears only in the authorization header.
- Response validation enforces the exact schema, candidate membership, unique JSON keys/labels, supported ranking reasons, delta-consistent direction codes, bounded nonempty plain text, and complete provider responses. Invalid/refused/oversized/truncated responses or provider errors fall back atomically to deterministic results. Scores, verdicts, explanations, warnings and cache contents remain intact. Prose is commentary; its semantics are not independently proven by schema validation.
- AI stays disabled by default. UI controls start checked/enabled only after complete explicit local provider opt-in; both allow per-operation opt-out. Initial page loading/OCR and changing the AI checkbox do not request a scan/model. API requests require literal `use_llm: true`. The CLI mirrors configured defaults and supports mutually exclusive `--llm` / `--no-llm`; explicit requests cannot bypass the operator gate.
- Baseline warnings apply only to positions represented by rostered players eligible for a starting slot, including cross-position eligibility. Free agents alone and unrepresented theoretical slot positions do not trigger baseline warnings. Relevant baseline and incomplete-coverage gaps remain disclosed, including in empty recommendation results.
- Existing optimizer, negative/zero/missing projection handling, independent exhaustive lineup oracle, ownership/capacity validation, all-opponent search, cache copies and HTTP protections pass. Default demo results remain 2,205 valid packages, 38 qualified, 12 returned.
- README setup uses an explicitly versioned Python executable, checks Python 3.11+, creates its venv from that executable, and uses the venv interpreter thereafter. System `python3` is not assumed compatible.

## Prior baseline commands and results

The installed `python3` was checked to be Python 3.14.7 before running these commands. For a fresh setup, follow the versioned-interpreter/venv instructions in README.

```sh
python3 scripts/offline_tests.py
```

Exit 0:

```text
Ran 43 tests in 28.682s

OK
```

The runner installs a Python audit hook rejecting non-loopback DNS/connections. HTTP tests use ephemeral loopback servers. Remote transports are mocked. CLI configuration/flag combinations cover manual evaluations and recommendation scans.

The added Host/public-origin regression failed before the guard change (HTTP 200 instead of 403) and passed afterward. It checks environment and explicit public-origin configuration, two allowed but mismatched hostnames, matching and absent Origin headers, and health/API routes. Existing HTTPS proxy tests still pass with explicit ports 8443 and 443 and a case-insensitive matching Host. Scoring and deployment configuration were otherwise unchanged.

```sh
node tests/test_ui.cjs
```

Exit 0:

```text
PASS UI workflow: own-roster confirmation → full-league cards; manual evaluation separate; detection correction/discard; provider-gated defaults and opt-out
PASS manual response races: team/player/AI changes and reversal, late errors, newest request wins, OCR perspective reset
```

This dependency-free harness executes the actual UI controller against a synthetic DOM and API. It verifies no pre-confirmation scan, exact confirmed-roster submission, full-league card rendering, provider text visible on cards, data-gap disclosure, independent manual evaluation, configuration defaults, opt-out, mixed-team correction, confirmation reset and discard. Deferred manual responses exercise changes to both team selectors, both player selectors, the AI preference, selection reversal, stale errors, out-of-order evaluations, and OCR-driven perspective reset.

```sh
python3 scripts/smoke.py
```

Exit 0:

```text
PASS OCR own-roster confirmation: unconfirmed HTTP 400; confirmed scan HTTP 200, all 5 opponents, 12 cards
PASS health: HTTP 200, synthetic source, read_only=true, llm_enabled=false
PASS UI and league: HTTP 200, 6 synthetic teams
PASS candidate generation: 2205 checked, 38 qualified, 12 returned
PASS manual evaluation: identical computed candidate
PASS coverage: filled and intentionally benched slots disclosed separately
PASS opt-in AI: disabled by default; mocked model-written manual/card summaries; deltas-only payload; timeout retains exact deterministic results
PASS real local OCR: synthetic own-team PNG → Bennett Vale / Cameron Vale; confirmation required; retained=false
PASS smoke: local server closed cleanly; no private ESPN data or LLM used
```

The smoke blocks non-loopback Python networking, starts/shuts down its own demo server, and generates the PNG in memory for real local Tesseract processing. Provider success and timeout are mocked.

```sh
python3 -m compileall -q app.py trade_valuator.py fantasy_lib.py evaluator tests scripts
node --check static/app.js
node --check tests/test_ui.cjs
```

All exit 0 with no output. Whitespace checks include untracked changed files via `git diff --no-index --check /dev/null <file>`. The installed Pillow version was also checked against the exact requirements pin.

## Limits

UI verification uses a synthetic DOM/controller harness, not an interactive browser or visual-layout review. HTTPS proxy policy was tested over local HTTP with a configured public origin; no external proxy/TLS deployment was created. Docker, live ESPN compatibility and live provider behavior were not exercised. The Docker base tag remains unchanged; no registry digest was guessed or verified, and OS packages remain unpinned. The smoke's ephemeral server was closed; no persistent service or remote artifact was created.
