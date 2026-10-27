# Trade Room

A self-hostable, read-only ESPN fantasy football trade evaluator. The default app runs entirely offline on synthetic players and projections. No ESPN writes, account discovery, analytics, remote fonts, or persistent upload storage. Licensed under the MIT License; see [LICENSE](LICENSE).

The interface uses blue-black surfaces, cyan analytics and amber accents, with
original local SVG geometry and system fonts. See [native UI verification](UI_VALIDATION.md)
for screenshots, rendering checks and the current unsigned build evidence.

## macOS desktop app

For Apple Silicon league members, use the self-contained **Trade Room.app** in
`Trade-Room-<VERSION>-macOS-arm64.dmg` from a verified future GitHub Release
(or an owner-provided verified local build). No Docker, Homebrew, Python or Tesseract
installation is needed. It starts synthetic demo with AI disabled and includes
on-device English OCR. See [Mac install, first-open and local ESPN setup](MACOS.md)
and [current lifecycle validation](LIFECYCLE_VALIDATION.md). No release is
published yet; build assets live outside this source folder.

For source edits and adding files, start with [MAINTAINING.md](MAINTAINING.md).
For versions, checksums, GitHub draft releases and update trust, see
[RELEASE.md](RELEASE.md). Repo source, external scheduler wrappers and installed
apps are separate update surfaces.

## Run locally (source / Docker alternative)

For league members, install **Python 3.11+** and **Docker Desktop with Compose
v2**, start Docker, then open a terminal in this folder:

```sh
# macOS / Linux
./start.sh
```

```powershell
# Windows PowerShell (also works in Command Prompt)
.\start.cmd
```

The launcher creates private ignored local config and a random token, starts the
synthetic demo with LLM off, and opens your browser already authenticated. Only
loopback is published. Use `open` to reopen, `stop` to stop, or `reset` to stop and
delete the saved token/settings (`./start.sh stop` / `.\start.cmd stop`, etc.).
Use `setup-espn` for guided hidden local credential entry, then the separate
explicit `espn` command only when ready to read your own league. Saving settings
never contacts ESPN; the default launch always selects demo.

See **[the complete self-hosting guide](SELF_HOSTING.md)** for prerequisites,
Windows/Linux details, authentication, privacy, ESPN setup, troubleshooting,
ports, stop/reset and manual fallback. Docker was not installed during
implementation: Compose and launchers were checked statically and with an
offline fake-Docker harness; **no real Docker image/build/run was tested**.

## Manual Python setup (fallback)

Python 3.11+ is required. Install a compatible interpreter first and check its version; the OS-provided `python3` (especially `/usr/bin/python3` on macOS) may be older. The examples below use `python3.11`; substitute the explicit executable for your installed Python 3.12+ if appropriate. The web server, CLI, and valuation engine use the standard library. Screenshot OCR additionally needs Pillow and the local Tesseract executable with English language data.

```sh
python3.11 --version
python3.11 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
python3.11 -m venv .venv
.venv/bin/python --version
.venv/bin/python -m pip install -r requirements.txt
# macOS: brew install tesseract
# Debian/Ubuntu: apt-get install tesseract-ocr tesseract-ocr-eng
.venv/bin/python app.py --source demo --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. `/health` reports readiness, source, read-only mode, OCR availability, and whether AI is enabled. IPv6 loopback is also supported: run with `--host ::1` and open `http://[::1]:8000`; the OS must provide IPv6 loopback. Demo data is fixed, synthetic, and reproducible with `.venv/bin/python scripts/make_fixture.py`. If OCR is unavailable, the workbench still supports manual roster selection. `requirements.txt` pins the tested Pillow version to 12.3.0.

```sh
.venv/bin/python trade_valuator.py --demo
.venv/bin/python trade_valuator.py --team harbor --other orbit --give harbor-2 --get orbit-5
```

With the default deployment config, the CLI prints deterministic candidate JSON with no network access or snapshot files. The same explicit operator AI opt-in and per-run opt-out as the UI apply; see below. The sanitized starter CLI and helper have been replaced with the shared engine; the old league/Keychain CLI interface is no longer used.

## Use the app

Select your team, scan the entire league, filter one-for-one trades or packages, and expand any card to inspect both teams' deltas, coverage, legal lineups, position depth, and roster counts. The workbench accepts one or two players per side and validates exact ownership and capacity. Changing either team, any selected player, or the manual AI preference clears the manual result and invalidates pending evaluations. Late results and errors cannot restore an obsolete proposal, even if you change a selection back.

Upload your own-team lineup screenshot from Discover, review the detected team, and correct the team selector if needed. The dialog displays that team's **full loaded snapshot roster**, marks possible screenshot matches, and identifies players OCR missed (including bench players). It does not edit the source roster. Mixed-team, ambiguous, or empty OCR requires an explicit team choice. Check the separate roster-confirmation box and click **Confirm roster & scan league**: the app automatically checks every opposing team and displays recommendation cards. No incoming players or trade partner need to be selected. Confirmation resets whenever you change the detected team. If the loaded roster is wrong, discard and refresh the source snapshot before scanning. The manual workbench remains a separate option for evaluating a specific 1–2-player-per-side proposal.

Screenshot import accepts PNG/JPEG up to 5 MiB and 16 million pixels. Pillow decodes the image, copies only RGB pixels into a fresh image, and re-encodes it in memory. All source metadata, including ICC profiles, EXIF, text/comments and DPI, is stripped before Tesseract receives the PNG through stdin/stdout with a 15-second timeout. No upload or OCR record is written to disk, database, journal, or log. Suggestions reference only rostered players. Recognized text can be edited for reference; text edits never change roster identities. `/api/candidates` requests marked `source: ocr` require `confirmed: true` and `roster_ids` containing the exact full roster for `team_id`; missing, duplicate, foreign, or stale identities are rejected before search or AI. The legacy manual-evaluation API also rejects `source: ocr` without confirmation. These are interaction safeguards, not authenticity proofs of a client request.

Images and recognized text exist transiently in process/browser memory; closing the review clears the UI state. Browser and OS memory/swap are outside the app's deletion guarantees. Responses use `Cache-Control: no-store`; no screenshot, OCR, or ESPN credential ever reaches the optional LLM adapter.

## Valuation and search

- Exact dynamic programming solves the best legal starting lineup, including repeated RB/WR slots, flex, and superflex. A player fills at most one slot. Supported slots: QB, RB, WR, TE, D/ST, K, RB/WR, WR/TE, RB/WR/TE, OP. IDP and occupied IR slots fail closed.
- Weekly lineup totals use available projections, excluding known bye, OUT/IR/suspended/doubtful, or started-game players. Missing values remain null; present zero and negative projections remain known values. Known coverage is the maximum number of slots that available players with projections could fill, independent of score. `filled` counts the chosen starters and `benched_slots` counts additional slots that could be filled but are intentionally empty to maximize points. Negative weekly projections may be benched without a missing-data warning. A true shortage of known, available, eligible projections still produces a coverage warning. Questionable players are flagged on evaluation.
- Season fit is `max(season projection / 17 − positional replacement / 17, 0)` summed across the exact best starting lineup. Replacement is the highest season projection in the supplied free-agent pool at that position. Missing baselines explicitly fall back to zero with a warning only for positions represented by at least one rostered player eligible for a starting slot, including explicit cross-position eligibility. Empty starting positions still produce coverage warnings; unavailable or missing projections remain disclosed. Free agents alone do not make a position relevant. Scan results also disclose relevant baseline and lineup-coverage gaps when no recommendation qualifies. No fabricated rankings, actual-points fallback, market values, acceptance probabilities, or rest-of-season claims.
- The season divisor is a fixed 17-game full-season weekly equivalent. This assumes projections are full-season totals; it does not adjust player-specific games, injury recovery, or remaining schedule. Bench value is zero, so consolidation can be overstated. Review both teams' depth and weekly deltas.
- Primary replacement uses **all projected players in the supplied free-agent pool**, including OUT/IR/questionable players; current status does not filter rostered full-season projections either. A separate **Doubtful/Out/IR-filtered free-agent sensitivity** excludes `DOUBTFUL`, `OUT`/`O`, `IR`, and injury-reserve aliases; it retains `QUESTIONABLE`, `SUSPENDED`, and other statuses outside that explicit set. Weekly lineup calculations still treat `SUSPENDED` as unavailable. This sensitivity leaves rostered season projections and the ÷17 formula unchanged. Bye/started flags do not filter either season baseline. Both use the same exact slot-mask DP. Sensitivity never affects primary scores, verdicts, qualification or ranking; its missing-baseline warnings are separate. This is a baseline sensitivity, not a player recovery model.
- Evaluation JSON exposes `season_model` (horizon, divisor, primary/sensitivity policies and positional replacement provenance) and `sensitivity` (both teams' before/after legal lineups, totals, coverage and deltas). Provenance includes the selected free agent's ID/name/status/bye/started flags, season points and weekly equivalent, pool/projected/policy-eligible counts, excluded-status counts, positional relevance and explicit zero fallback. Selection uses native position, highest season projection, then player ID for ties. Display quotients are rounded; the optimizer uses the unrounded quotient. Scan output includes the same `season_model` and separate `sensitivity_warnings` even with no candidates. Expand provenance in scan results or any trade card/workbench result; sensitivity metrics and legal lineups appear separately from primary season fit.
- Only `week` and `season` are supported lineup horizons; `ros` and all other values raise an error. The current ESPN source has **no verified ROS field**. `season_model.ros` explicitly reports `available: false` and `value: null`; no ROS number is computed, prorated or inferred from full-season totals.

See [model regression evidence and horizon limits](MODEL_VALIDATION.md) for the
test-first checks and preserved demo ranking.
- Deterministic search covers **every opposing team**, using each team's **six highest season-projected eligible available players**, all 1:1, 1:2, 2:1, and 2:2 combinations. Players with no eligible starting slot are removed before the six-player cap. It is a bounded shortlist, not an exhaustive search of all players. Ties use player/candidate IDs. Up to 12 results are returned; no automatic drops are assumed. Only complete-data candidates with strictly positive season lineup gains for both teams and no traded-player warnings qualify. Weekly changes are displayed, not included in the ranking score.
- Score = your season-fit gain + their gain + 2 × min(the two gains). Thresholds are local consistent rules, not a proven trade price. The UI may show several related packages; a zero-result state is valid.

## Optional ESPN snapshot

No live private ESPN requests were made in building or testing this repository. The adapter is tested with synthetic response shapes. ESPN's unofficial response format may change; unsupported slots, incomplete data, and errors fail closed or are disclosed. This integration has not been verified against a live private league.

Inject `ESPN_FANTASY_YEAR`, `ESPN_LEAGUE_ID`, and, for private leagues, your own `ESPN_S2` and `ESPN_SWID` through your local process environment. `.env.example` contains empty placeholders; `.env` is ignored and is **not automatically loaded**. Do not put credentials in command-line arguments, commits, screenshots, or shared logs.

The Docker launcher offers [guided local setup](SELF_HOSTING.md#optional-operator-guided-espn-setup)
as a simpler alternative. Its `.local/config.json` is separate from `.env` and
is read only by the launcher; direct Python/CLI commands do not load it.

```sh
# After configuring the process environment locally:
.venv/bin/python app.py --source espn --host 127.0.0.1 --port 8000
```

The server makes only fixed-host HTTPS **GET** requests to `lm-api-reads.fantasy.espn.com` for settings, teams, rosters and a limited free-agent pool. Redirects are rejected so credentials are never forwarded to another host. It loads once at startup; restart to refresh. ESPN account owner records and the league ID are not exposed by `/api/league`. Team/player IDs are runtime roster identifiers and remain necessary for selection; they are never sent to the LLM.

Only ESPN projection records (`statSourceId=1`) with matching season/week are accepted. Absent fields are null. Cumulative actual points are not season projections. Roster responses do not reliably provide bye/game-lock state: the ESPN source label explicitly describes weekly totals as **full-week**, with game-lock/bye status unavailable. Free agents are restricted to returned `FREEAGENT` records (up to 100); the pool is not claimed to be exhaustive. Unsupported IR handling must be resolved before loading a league. All figures reflect the startup snapshot, not live availability or lineup eligibility at submission time.

Matching duplicate projection records must agree on their numeric value (including null versus a known zero); conflicts reject the snapshot instead of selecting the last record. Comparison occurs before display rounding. Identical duplicates are allowed. Season and current-week projections are separate horizons; other seasons/weeks, actuals and unverified split types never supply or override them. No verified rest-of-season field is currently mapped, and unknown splits never become ROS estimates.

There are no endpoints to submit, accept, reject, edit trades, set lineups, or modify waivers. Local POST routes compute evaluations, search, and OCR; the desktop-only setup route also saves local settings and explicitly loads read-only snapshots.

## Optional AI (off by default)

The local Compose launcher always disables AI and does not collect provider
keys. The optional configuration below applies to manual deployments only.

`LLM_ENABLED=false` remains the deployment default. To opt in, set `LLM_ENABLED=true`, `LLM_PROVIDER=openai`, and a nonempty `LLM_API_KEY` locally; optionally set `LLM_MODEL` (default `gpt-4.1-mini`). Both UI run controls then start checked and enabled: **Optional AI ranking & summaries** for scans and **Optional AI summary** for manual evaluations. Uncheck either to opt out of that operation. Without complete local provider opt-in, both controls are unchecked and disabled. `/health` distinguishes the enable flag (`llm_enabled`) from complete provider configuration (`llm_available`); it does not probe the provider. Initial page loading and OCR extraction make no AI request. A screenshot scan starts only after roster confirmation. Selecting a perspective, scanning, or evaluating with the relevant control checked requests AI. API clients must send the literal JSON boolean `"use_llm": true`; absent, false, string, or numeric values never opt in.

The CLI uses the same local opt-in: configured/enabled providers default on, `--no-llm` opts out for a run, and `--llm` explicitly requests AI without bypassing the operator gate. Both candidate scans and manual evaluations support these switches. For example, after local configuration:

```sh
.venv/bin/python trade_valuator.py --demo --no-llm
.venv/bin/python trade_valuator.py --demo --llm
.venv/bin/python trade_valuator.py --other orbit --give harbor-2 --get orbit-5 --llm
```

No flag or default can enable provider calls while `LLM_ENABLED` is false.

The adapter uses the existing fixed HTTPS OpenAI endpoint and rejects redirects. Its only per-trade model input is a request-local label (`c0`, `c1`, …) plus four numeric computed deltas: your/their season and week changes. Stable trade hashes, computed scores, names, league/team/player IDs, warnings, raw rosters, images, OCR, ESPN credentials, deployment tokens, and arbitrary user text are excluded. The provider API key appears only in its authorization header, never in the prompt. Requests set `store: false`; provider processing of the anonymized payload follows the operator's provider account terms.

Output must include every request-local label exactly once, an allowed ranking reason, and exact season/week direction codes consistent with the supplied deltas, plus **actual model-written summary text**. The adapter returns this text rather than selecting a local sentence template. Summaries are limited to 280 characters of plain text and requested to describe only computed season/current-week tradeoffs without identities, numerical claims, external facts, advice, or new verdicts. Invalid types, empty/oversized text, control characters, digits, HTML/link delimiters or explicit URL prefixes, extra fields, duplicate JSON keys or labels, incorrect direction codes, malformed/oversized/truncated/refused responses, and provider failures reject the whole annotation batch. Fallback preserves the original deterministic results and explanation, with an AI status explaining unavailability. Structure and direction codes are validated; free-form prose is commentary, not independently proven facts.

Optional ranking may reorder validated cards; it cannot change scores, projections, warnings, verdicts, explanations, or candidate membership. Summaries appear on the recommendation cards and manual results as plain text. Annotations never enter the recommendation or lineup caches. The adapter retains the existing fixed-endpoint JSON response mode and independently validates its application schema.

## Self-hosting

Use [SELF_HOSTING.md](SELF_HOSTING.md) for the recommended local Compose launcher.
The following is the manual deployment fallback.

Loopback binding is the default. Binding to a network interface requires `APP_ACCESS_TOKEN` of at least 24 characters. API requests use `Authorization: Bearer …`; manual deployments accept the token in a password field and keep it only in JS memory. The local Compose entry point explicitly enables a guarded same-origin bootstrap: a random page nonce in a custom header, loopback Host restrictions, no public origin, same-origin checks, no forwarding headers and no CORS permission. Page/bootstrap responses are no-store/no-referrer and requests are never logged. Browser-launch arguments contain only the plain local URL; no token appears in a URL. Reload repeats bootstrap only in this local profile; manual deployments show the token form again. Legacy token fragments are scrubbed and ignored. See [browser authentication](SELF_HOSTING.md#browser-authentication) for the full contract. This token is separate from ESPN/LLM credentials. Keep `--compose-local-bootstrap` disabled for manual/public deployments; it rejects public origins and nonloopback allowed hosts. Configure `--allowed-host your-domain.example` for your deployed hostname. Cross-origin browser requests are rejected, hosts are checked, and the app has no CORS policy, external assets, or third-party scripts. Deploy behind HTTPS and an authenticated reverse proxy for multi-user use. Treat this as a trusted-operator tool; the standard-library server is not a hardened public service.

For direct HTTP, an `Origin` header must match the request's HTTP scheme, allowed hostname, and port. HTTPS on the same authority is a different origin and is rejected. Hostnames are case-insensitive and omitted ports use the scheme default (HTTP 80 / HTTPS 443). Requests without `Origin`, such as CLI clients and local health checks, remain supported; API token checks still apply.

When a reverse proxy terminates HTTPS, explicitly configure the single trusted browser-facing origin with `APP_PUBLIC_ORIGIN` or `--public-origin` (the flag takes precedence):

```sh
# After configuring APP_ACCESS_TOKEN and the proxy's authentication locally:
.venv/bin/python app.py --source demo --host 127.0.0.1 --port 8000 \
  --allowed-host trades.example.com --public-origin https://trades.example.com
```

The proxy should route `https://trades.example.com` to `http://127.0.0.1:8000`, preserve the browser-facing `Host`, and forward API authorization. Include the external port in the public origin when non-default, for example `https://trades.example.com:8443`. This setting replaces the direct-HTTP origin expectation; requests carrying an origin must match its scheme, hostname and port. The `Host` hostname must also match the configured public origin hostname, even for requests without `Origin` and when another hostname is allowed. The `Host` allowlist remains a separate check. Use only an HTTP(S) origin with no credentials, trailing slash, path, query or fragment; invalid settings fail startup. `Forwarded` and `X-Forwarded-*` headers never grant origin trust. Leave `APP_PUBLIC_ORIGIN` empty for direct HTTP.

```sh
docker build -t trade-room .
# Prepare ignored .env locally with a random APP_ACCESS_TOKEN of >=24 characters.
docker run --rm --read-only --tmpfs /tmp:rw,noexec,nosuid,size=32m \
  --env-file .env -p 127.0.0.1:8000:8000 trade-room
```

The container runs as a non-root user and includes Tesseract. Its default source is demo; pass `python app.py --source espn --host 0.0.0.0 --allowed-host your-domain.example` after the image name to explicitly use ESPN. Docker health is local and does not call ESPN or an LLM. Image builds need package-network access; runtime demo/tests do not. A Docker build is not required for local use.

For HTTPS proxy deployments, set `APP_PUBLIC_ORIGIN` in the process environment or Docker env file and include the proxy hostname with `--allowed-host` in the container command. The Docker base remains `python:3.13-slim`; no digest was guessed or verified here. Pillow is pinned, but the mutable base tag and OS package versions mean the full image is not reproducibly pinned. Resolve and verify a registry digest in your release environment before pinning it.

## Offline verification

With Python 3.11+, Pillow, Tesseract and Node.js installed (Node is used for the synthetic UI controller regression):

```sh
.venv/bin/python scripts/offline_tests.py
.venv/bin/python scripts/smoke.py
.venv/bin/python -m compileall -q app.py trade_valuator.py fantasy_lib.py evaluator tests scripts
node --check static/app.js
node tests/test_ui.cjs
sh -n start.sh
```

Launcher regressions parse the full JSON-form YAML Compose structure and run an
offline fake-Docker executable with a real loopback app. They check private and
atomic config writes, hidden-input failure, local contexts, fixed loopback
publishing, secret-free Docker metadata/arguments, runtime config loading,
demo/ESPN selection, redacted command failures, readiness, interpreter selection,
and stop/reset even with missing config/directory. HTTP checks cover nonce and
same-origin bootstrap success, missing/wrong headers, cross-origin rejection,
disabled/manual mode and unsafe configuration. The UI harness checks bootstrap,
password fallback, ignored legacy fragments, header-only bearer use, and no
persistent token storage. These checks do not replace a real image/build
or desktop/Windows integration test; see [SELF_HOSTING.md](SELF_HOSTING.md#validation-boundary).

The offline runner and smoke install a Python audit hook that rejects non-loopback DNS/connections. Tests use synthetic fixtures, mocked remote transports, local HTTP on ephemeral loopback ports, and no live ESPN/LLM data. You can also run the same suite directly with `.venv/bin/python -m unittest discover -s tests -v`. The smoke launches its own local demo server, checks health/UI/rosters, scans and re-evaluates a candidate, checks opt-in summaries with mocked provider success/failure, generates a synthetic screenshot in memory, exercises real Tesseract through the upload endpoint, then shuts down. The Node harness exercises the actual UI controller with a synthetic DOM and API responses: detection correction, explicit full-roster confirmation, automatic league scan/cards, separate manual evaluation, delayed manual responses/errors after selection changes, newest-request rendering, discard, provider-gated defaults and opt-out. It does not test browser rendering. Unit coverage includes exact flex assignment and duplicate slots; an independent exhaustive slot-assignment oracle for maximum points and coverage; missing, zero and negative projections; scoped replacement warnings; eligibility before shortlist truncation; defensive cache copies; determinism and all-team search; ownership/capacity; explicit OCR confirmation; upload bounds; metadata-free PNG/JPEG OCR re-encoding; IPv6 loopback; exact origin scheme/host/port and trusted HTTPS proxy configuration; auth/host checks; rejected ESPN writes; and opt-in summaries/ranking, payload privacy, strict output validation and failure fallback. No search optimization was added. No artifacts are published, pushed, or sent to a remote Git repository.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) for offline checks and contribution rules. For vulnerability reports, follow [SECURITY.md](SECURITY.md); do not post credentials or sensitive league data in public issues.
