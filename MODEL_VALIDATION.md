# Season replacement provenance and sensitivity validation

Codex's implementation validation used Python 3.14.7, Node v22.22.3 and
Tesseract 5.5.2; an independent local re-run on 2026-10-21 used Python 3.12.13.
Only synthetic repository fixtures and synthetic mocked ESPN/provider responses
were used. No live source was queried.

## Changes and preserved behavior

- `evaluator/model.py`: reject lineup horizons other than `week`/`season`;
  expose deterministic per-position primary/Doubtful/Out/IR-filtered replacement provenance;
  calculate the Doubtful/Out/IR-filtered free-agent sensitivity through the same exact
  slot-mask DP; serialize explicit ROS unavailable/null metadata.
- `evaluator/sources.py`: accept agreeing duplicate projections, reject
  conflicting matching records before display rounding, and disclose the lack
  of a verified ROS field in the ESPN source label.
- `static/app.js`, `static/index.html`: display provenance, pool/projection
  counts, selected player/status, relevance, fallback, excluded-status counts,
  sensitivity totals, deltas, coverage and legal lineups in cards/workbench; retain provenance and
  sensitivity warnings for empty scans; clarify methodology.
- `tests/test_engine.py`, `tests/test_privacy.py`, `tests/test_ui.cjs`: focused
  synthetic regressions, including preserved demo candidate IDs/scores,
  input-order independence, defensive output copies, duplicate conflicts in
  roster/free-agent responses and empty-scan UI disclosure.
- `scripts/smoke.py`: assert provenance and sensitivity on actual local HTTP
  results, with ROS unavailable/null and unchanged demo primary lineups.
- `README.md`, `MODEL_VALIDATION.md`: behavior, output contract and evidence.

The primary formula remains `max(season / 17 - positional replacement / 17, 0)`.
Primary replacement still uses every projected free agent at its native
position, including unavailable players. Baseline ties select the smallest
player ID for provenance; this does not change the baseline amount. Negative
baselines remain valid, known zero is distinct from missing, and relevant
missing baselines still use zero with the original primary warning. Coverage,
score, verdict, candidate qualification and deterministic ranking retain their
original semantics. The demo still checks 2,205 packages, qualifies 38 and
returns the same 12 candidate IDs and scores captured before implementation.

The season-baseline sensitivity excludes only explicit `DOUBTFUL`, `OUT`/`O`,
`IR`, and injury-reserve aliases. `QUESTIONABLE`, `SUSPENDED`, and unrecognized
statuses remain in this full-season baseline sensitivity; the separate weekly
lineup filter still treats `SUSPENDED` as unavailable. Status matching trims and
uppercases text and normalizes spaces/hyphens to underscores. Per-position
provenance reports excluded projected-player counts by normalized status;
unprojected players are reported separately by pool/projection counts. Rostered
full-season projections stay unchanged. Bye/started flags do not filter either
season baseline. The sensitivity never changes primary qualification, verdict
or score.

## Test-first evidence

Tests were added and run before the corresponding implementation:

| Exact command | Before implementation | After implementation |
| --- | --- | --- |
| `python3 -m unittest discover -s tests -p test_engine.py -v` | Exit 1: 6 unsupported-horizon failures and 2 missing-output errors; existing primary ranking regression passed | Exit 0: 17 tests passed in 27.919s |
| `python3 -m unittest discover -s tests -p test_privacy.py -k espn -v` | Exit 1: 24 duplicate-conflict subtest failures and missing ROS source disclosure | Exit 0: 3 tests passed in 0.010s |
| `node tests/test_ui.cjs` | Exit 1: sensitivity disclosure assertion failed | Exit 0: provenance/sensitivity, empty scans, auth, OCR workflow and response-race checks passed |

A user correction established that `QUESTIONABLE` must remain in the alternate
pool while `DOUBTFUL`, `OUT`, and injury-reserve statuses are filtered. The
synthetic regression makes a QUESTIONABLE free agent the highest eligible
candidate, checks the exclusion counts for Doubtful/Out/IR (including normalized
injury-reserve spelling), and confirms SUSPENDED and an unmapped status remain
eligible. The first run failed because the new `doubtful_out_ir_filtered` policy
was absent; after implementation, all 17 engine tests passed. The UI test also
failed before the rendered labels and policy name were updated, then passed
with the corrected provenance disclosure.

## Final checks

All commands below exited 0:

| Exact command | Result |
| --- | --- |
| `python3 scripts/offline_tests.py` | 95 tests passed in 59.112s; external Python DNS/connections denied by the runner |
| `node tests/test_ui.cjs` | All synthetic DOM/controller checks passed |
| `python3 -m compileall -q app.py trade_valuator.py fantasy_lib.py evaluator tests scripts` | Passed, no output |
| `node --check static/app.js && node --check tests/test_ui.cjs` | Passed, no output |
| `python3 scripts/smoke.py` | Passed health/static/league, 2,205 checked / 38 qualified / 12 returned, evaluation parity, coverage, season metadata/sensitivity, mocked AI opt-in/fallback, real local OCR and clean local-server shutdown |
| `git diff --check` | Passed, no output |
| `git diff --cached --binary \| shasum -a 256` | Same initial and final digest below |

Independent Hermes re-run using Python 3.12.13 on 2026-10-21:

- `$HOME/Quant/.venv-test/bin/python scripts/preflight.py` — passed; 95 offline
  tests in 57.510s plus UI harness, compile/syntax checks, smoke and diff checks.
- Browser visual pass after the policy correction: source demo at 1280×633 and
  390×844, plus the built native WebKit app at 800×600, 1024×768 and 1200×850.
  New sensitivity labels wrapped without clipping or horizontal overflow; the
  detailed provenance stays collapsed by default.
- `$HOME/Quant/.venv-test/bin/python scripts/build_macos.py --offline` — rebuilt
  `../fantasy-trade-valuator-artifacts/1.0.0/Trade Room.app` and
  `../fantasy-trade-valuator-artifacts/1.0.0/Trade-Room-1.0.0-macOS-arm64.dmg`
  from the verified local dependency cache; version remains 1.0.0.
- `$HOME/Quant/.venv-test/bin/python scripts/verify_release.py ../fantasy-trade-valuator-artifacts/1.0.0 --ui` — passed DMG checksum, read-only mount, identical mounted/built arm64 bundles, synthetic native workflow, Vision OCR, rendered WebKit UI and clean shutdown. Synthetic demo: 2,205 checked / 38 qualified / 12 cards; no private ESPN or LLM data.
- `shasum -a 256 -c SHA256SUMS` — both entries OK. DMG SHA-256: `c5accbb4c9147e2ef5a3b80cd5d23e62485c2315f8421c21a666175df740befd`; BUILD.json SHA-256: `f07310955175ecb6db515f582b4dcf0aa612c04cda3adae20a2472708ffe7cb3`.
- Source/bundle hashes match for `evaluator/model.py`, `evaluator/sources.py`, `static/app.js` and `static/index.html`. BUILD metadata: `source_revision=null`, `source_dirty=true`, unsigned and not notarized. The installed copy was not replaced; no publishing occurred.

Staged-index SHA-256 before and after:

```text
bcd07b3741bb4864f6cace26973b271c0b1b2eaac5732912cf69de8ef5aa9d5a
```

No staging, commits, remote changes, tags, pushes or publication occurred. VERSION
remains 1.0.0; launch behavior was not changed. The local `.app` and DMG were
rebuilt and verified as dirty, unsigned, unnotarized development artifacts. The
installed copy was not replaced.

## Data horizons and remaining limits

- ESPN split 0 projections remain the existing assumed full-season proxy,
  divided by a fixed 17. Split 1 must match the current week; weekly totals are
  full-week, with ESPN bye/game-lock state unavailable. Actuals, other seasons,
  other weeks and unverified split types do not fill either projection field.
- The current ESPN source has **no verified ROS field**. Output explicitly uses
  `season_model.ros.available = false` and `value = null`. Unsupported lineup
  horizons raise `ValueError`; no remaining-schedule estimate is invented.
- The supplied ESPN free-agent pool is limited and may be incomplete. The
  Doubtful/Out/IR-filtered sensitivity is not a player recovery,
  remaining-games or bench-value model. No live private league compatibility was verified.
- Browser visual checks covered the local synthetic demo at 1280×633 and
  390×844. The expanded provenance list is vertically long but scrollable and
  collapsed by default. The packaged/installed app was not rebuilt or checked.
- P3 test hygiene: the passing full suite emitted two cleanup ResourceWarnings
  for mocked HTTPError 302/404 objects. These were non-failing test-resource
  cleanup messages; unrelated mock cleanup was left outside this change.
