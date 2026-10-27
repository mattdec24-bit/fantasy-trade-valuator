# Maintaining Trade Room

Start here for source updates. Use [RELEASE.md](RELEASE.md) when distributing an
app. This folder has no Git commit or remote yet; nothing has been published by
the lifecycle work. Keep VERSION at **1.0.0** until the first authorized release.

## What changes what

| Surface | Source of truth | How it changes |
| --- | --- | --- |
| Repo source | This folder's Python, JS, Swift, manifests and docs | Edit source and run preflight. A future GitHub checkout is another copy of this source. |
| External scheduled wrapper | Whatever separately configured scheduler/wrapper the owner uses | Owner reviews its path, arguments, environment and working directory separately. This repo neither installs nor synchronizes it. |
| Installed app / DMG | A snapshot made by scripts/build_macos.py | Rebuild, verify, distribute and manually replace the app. Editing source does not change an existing app. |

GitHub Release assets will be downloadable snapshots of a tagged source commit,
not the place to edit source. BUILD.json records the source revision (null before
the first commit), whether it was dirty, source hashes and pinned runtime inputs.
An existing external scheduler may call a repo script directly or a copied
wrapper. Its existence/configuration has **not** been inspected. Updating a
wrapper cannot update the embedded app, and replacing the app cannot update a
wrapper. Keep scheduler-specific adaptation thin; put reusable behavior here.

## Everyday edit → check → build

Use Python 3.11+ with Pillow from requirements.txt, Node 22, and local Tesseract
with English data. See README for virtual-environment setup. Substitute your
venv's Python for `python3` below. Setup can use the network; all source tests
use synthetic data and reject non-loopback Python connections.

```sh
python3 scripts/preflight.py
python3 scripts/preflight.py --workflows
```

The first command checks Python/JS/shell syntax, Git whitespace, the runtime
manifest, all Python offline tests, the UI controller and the real local OCR
smoke. The second also requires actionlint 1.7.7 and zizmor 1.31.1 on PATH.
It does not stage anything. Keep logs outside this folder if saving output.

Install workflow tooling in a separate venv with
`python3 -m pip install -r requirements-dev.txt`. Install actionlint from its
[official release](https://github.com/rhysd/actionlint/releases/tag/v1.7.7), verify
its published checksum, and add the binary to PATH. With Go installed, the
alternative is `go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.7`.
Both actionlint (explicit workflow filenames) and zizmor offline mode work before
the first commit. `pip-audit --strict -r requirements.txt` is a separate **online**
dependency check. Never run it as part of the app or offline checks.

On an Apple Silicon build Mac with Apple command-line compiler tools:

```sh
python3 scripts/build_macos.py
python3 scripts/verify_release.py ../fantasy-trade-valuator-artifacts/1.0.0 --ui
```

Default output is `../fantasy-trade-valuator-artifacts/<VERSION>/`; verified public
downloads are cached in its sibling `cache/`. Use `--offline` on the builder to
require an already populated cache. `--output` and `--cache-dir` accept separate
external directories and reject the source tree or its ancestors. Never put
artifacts in Git or Git LFS. Obsolete `legacy-build/` and `legacy-dist/` snapshots
were removed after updating and verifying the current local DMG. The build's
`work/` directory is generated staging and can be removed after verification; a
future build recreates it.

## Where to edit and add files

| Change | Edit here | Packaging follow-up |
| --- | --- | --- |
| Browser layout/behavior | static/ | Approved JS, CSS, HTML, PNG and SVG files are included automatically. Add a server asset route if the new file must be served. |
| Valuation / ESPN / OCR | evaluator/ | Python files are included automatically; add focused synthetic tests. |
| Desktop settings or update check | desktop.py, updates.py, static/desktop.js | Preserve explicit request/auth/privacy tests. |
| Native app | macos/Launcher.swift, NativeHelper.swift | Rebuild and run mounted WebKit/Vision/shutdown QA. |
| New top-level runtime module or data | New file + macos/bundle-files.json | Add the exact path to `files`; add it to Dockerfile COPY too if used by the server/container. |
| Tests / docs / maintenance helper | tests/, docs here, scripts/ | Never automatically bundled; no manifest edit unless the app needs it. |

Only fixtures/demo.json is bundled; keep it synthetic. Runtime directories reject
hidden files, links and unreviewed extensions. Preflight tells you which new file
type needs review. Avoid duplicate/generated copies of source files. Private
settings remain in ignored local storage, never in the manifest or fixtures.

## Routine maintenance

Dependabot proposes pip, action SHA and Docker updates after a future remote is
enabled. Review and run checks; do not auto-merge. Native Python archive hashes,
license archive, Pillow wheel/hash and their tested architecture are explicit in
scripts/build_macos.py and require a manual review together with requirements.txt.
Do not substitute a hash from an untrusted download. Keep bundled notices.

CI checks Python 3.11/3.13, UI/smoke and workflow security; weekly dependency audit
uses the network. Changes to these workflows do not edit any external scheduler.
Before enabling GitHub, review the entire working tree: many files predate this
task and the original staged index was deliberately left unchanged.
