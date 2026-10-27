# macOS refinement validation — 2026-10-20

> Historical validation before lifecycle changes. Current checks and artifacts
> are recorded in [LIFECYCLE_VALIDATION.md](LIFECYCLE_VALIDATION.md). The old
> external `legacy-build/` and `legacy-dist/` snapshots were deleted on
> 2026-10-21; the hashes below are historical, not current artifact hashes.

Verified the rebuilt unsigned Apple Silicon app on macOS 26.5.1 (25F80), arm64.
This run uses only synthetic leagues, screenshots, credentials and private
verification homes. The login Keychain, real providers and private legacy
projects were not accessed.

## Changes

The original `dist/verification` WebKit snapshots showed an ESPN form extending
the first-run welcome and an OCR roster pushing its confirmation footer off
screen. The revised welcome contains a focused **Explore synthetic demo** primary
action and **Set up ESPN · optional**, which opens a separate setup dialog.
**Local setup** remains available afterward. The existing colors, typography,
buttons, trade cards, engine and ESPN valuation behavior are preserved.

OCR review now uses a constrained flex layout. Only the player region scrolls;
the full player count, acknowledgement and confirmation/discard controls remain
visible. Recognized text is an expandable editable reference. Team selection,
full snapshot roster validation and explicit acknowledgement still gate scans.
Discard clears transient OCR data without replacing the previous results.

`desktop.Settings` now commits working file/metadata before retiring old Keychain
credentials. Keychain saves use fresh app-owned account slots under the same
fixed service, rather than overwriting the active credential. A private metadata
journal records staged/retired slot identifiers before creation/deletion. Failed
commit/rollback cleanup preserves the previous active settings and leaves a
retryable journal. Cleanup after a successful commit retains the new working
configuration. **Local setup · cleanup pending** reports incomplete removal;
**Forget** retries it, including after restart. Legacy account `league` remains
readable and migrates on an explicit save/forget. No startup Keychain access or
silent file fallback was introduced.

## Final deliverables

- `dist/Trade Room.app` — rebuilt unsigned native AppKit/WebKit app, macOS 13+
  Apple Silicon target, about 79 MiB.
- `dist/Trade-Room-1.0.0-macOS-arm64.dmg` — compressed read-only image, about
  42 MiB, containing only app, Applications shortcut, instructions and license.
- `dist/SHA256SUMS` — verified against the final image.
- `dist/verification/` — current native snapshots, test results, mount checks,
  full bundle/dependency hashes, signature assessment and shutdown evidence.

Final DMG SHA-256:

```text
7dd77b6d7c453661e9aabe610e5c105b0ba22cda19c9df6a1831d9456c8cc474
```

## Results

| Check | Observed result |
| --- | --- |
| All Python tests | **76 passed**, using the final mounted app's bundled Python under sanitized PATH with external networking blocked |
| Settings failure injection | Nine new tests with transition subcases cover new/existing/legacy Keychain slots, file↔Keychain and same-storage saves, failed helper saves/timeouts, metadata replace/fsync failure, Forget failure, commit/rollback cleanup failure, failed journal writes, retry after restart, missing-item deletion, private modes and temporary-file cleanup |
| Keychain isolation | Helper subprocess boundary replaced by an in-memory synthetic slot store in failure tests; no real login Keychain calls |
| JS controller suite | Authentication/bootstrap, full-roster count/confirmation/discard, cards/workbench, opt-out and stale-response tests passed |
| Native first run | Concise welcome, primary demo autofocus, separate optional setup, six synthetic teams, Keychain default, AI disabled |
| Minimum window | Actual native frame **800×600**, WebKit viewport **800×568**; welcome fits without scrolling; roster count and controls visible/unobscured |
| Larger windows | Native frames **1024×768** and **1200×850**, viewports **1024×736** and **1200×818**; same layout assertions passed |
| Roster overflow | Scroll-to-last-player checks, fixed action position, 60-row DOM stress at all three sizes, expanded recognized-text reference at minimum size passed |
| Valuation regression | **2,205** valid packages checked, **38** qualified, **12** cards; manual evaluation matches computed candidate |
| Actual native OCR | Synthetic PNG passed through Pillow sanitization and bundled Apple Vision; recognized Bennett Vale / Cameron Vale; full 12-player roster shown; acknowledgement starts unchecked |
| OCR confirmation/discard | Unconfirmed HTTP scan rejected; confirmed scan returns all-opponent cards; rendered Discard clears OCR state; reupload requires fresh acknowledgement |
| Setup | Actual synthetic form save uses explicitly chosen file storage, clears secrets and never selects ESPN; Forget removes configuration |
| Normal shutdown | Native window-close delegate terminates backend with exit status **0**, backend_alive=false, listener gone |
| LaunchServices/crash | Mounted unsigned app opened via `open -n -a` with a fresh home and sanitized PATH; synthetic health passed; SIGKILL of this test parent caused its backend to exit within five seconds |
| Real OCR smoke | Full HTTP smoke passed with host Tesseract and final mounted runtime/Apple Vision, including unchanged valuations and mocked provider fallback |
| Bundle audit | **1,834 files, 9 internal links, 38 Mach-O binaries**; all include arm64; external dependencies limited to Apple system libraries; mounted file hashes/links match build |
| Packaging | No `.env`, settings, Git metadata, private state or host runtime paths bundled; runtime and Pillow checksum pins checked during rebuild |
| Image verification | `hdiutil verify` valid; mount confirmed nonwritable; exact root contents checked; SHA-256 manifest verification passed |
| Unsigned | Read-only `codesign -dv` says code object is not signed at all; `spctl --assess` rejects as expected |
| Syntax | Python compile, JS syntax, shell syntax and Git whitespace checks passed |
| Existing index | Staged diff SHA-256 unchanged: `bcd07b3741bb4864f6cace26973b271c0b1b2eaac5732912cf69de8ef5aa9d5a` |

The final native integration snapshots were captured by the actual WKWebView
from the mounted DMG and inspected visually. Capture acknowledgement now waits
for the native snapshot before advancing the UI; Discard verification waits for
WebKit's asynchronous dialog close event. The 60-row stress duplicates DOM rows
only and does not modify the loaded roster, player count or valuation engine.

Minimum-size evidence: `ui-welcome-800x600.png`, `ui-ocr-800x600.png`,
`ui-ocr-bottom-800x600.png`, `ui-ocr-reference-800x600.png`. The corresponding
1024×768 and 1200×850 images, separate setup, final expanded cards, UI results
and `stop-result.json` are alongside them.

## Reproduce

```sh
python3 scripts/build_macos.py
hdiutil verify dist/Trade-Room-1.0.0-macOS-arm64.dmg
hdiutil attach -readonly -nobrowse -mountpoint '/Volumes/Trade Room Refinement Verification' \
  dist/Trade-Room-1.0.0-macOS-arm64.dmg

env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin HOME=/private/tmp \
  '/Volumes/Trade Room Refinement Verification/Trade Room.app/Contents/Resources/python/bin/python3' \
  -I -B scripts/verify_macos.py \
  '/Volumes/Trade Room Refinement Verification/Trade Room.app' --ui

env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin HOME=/private/tmp \
  '/Volumes/Trade Room Refinement Verification/Trade Room.app/Contents/Resources/python/bin/python3' \
  -B scripts/offline_tests.py
node tests/test_ui.cjs
python3 scripts/audit_macos.py 'dist/Trade Room.app' \
  --compare '/Volumes/Trade Room Refinement Verification/Trade Room.app'
(cd dist && shasum -a 256 -c SHA256SUMS)
hdiutil detach '/Volumes/Trade Room Refinement Verification'
```

Native UI verification requires all three flags: `--verify-ui`,
`--verification-home`, and `--offline-verification`. Ordinary launches do not
capture screenshots. Verification denies backend external DNS/connections and
runs the real DOM handlers, engine, HTTP endpoints and native OCR.

## Limits and preserved constraints

Real Keychain permission dialogs and real ESPN/provider endpoints were not
exercised. Tests model the helper's save/read/delete outcomes, including timeout
after creation and repeated cleanup errors. File fallback was exercised end to
end. No private project was accessed, and no signing, notarization, Gatekeeper
change, quarantine removal, staging, commit, push or publication occurred.
Native arm64 executables retain compiler/upstream execution hashes; no Developer
ID bundle signature or signing operation was added.

The app targets macOS 13+ but this run used only macOS 26.5.1 on Apple Silicon.
No Intel or second physical Mac testing is claimed. Native UI verification uses
DOM automation and WKWebView snapshots; it does not claim accessibility-driven
file-picker or menu interaction, or a downloaded/quarantined first-open flow.

All verification app/backend processes were stopped and the DMG was ejected.
