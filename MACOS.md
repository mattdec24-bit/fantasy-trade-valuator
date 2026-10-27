# Trade Room for Mac

Trade Room is a local, read-only fantasy football trade workbench. The desktop
app includes Python 3.13.16, Pillow 12.3.0, and a native Apple Vision OCR helper.
English OCR uses the on-device macOS Vision revision 2 model. There is no
Tesseract download, language-pack installation, Docker, Homebrew, system Python,
browser installation, or first-launch dependency download.

## Install and first open

Requires **Apple Silicon (M1 or newer), macOS 13 Ventura or newer**, about 250 MB
of free disk space, and a graphical desktop session. This is an arm64 build,
not a universal or Intel build. The minimum OS is the compilation target;
end-to-end verification was performed on macOS 26.5.1 arm64, not every older OS.

1. Double-click `Trade-Room-<VERSION>-macOS-arm64.dmg` (currently 1.0.0) in Finder.
2. Drag **Trade Room.app** onto the **Applications** shortcut. Wait for the copy
   to finish. Eject the disk image and open **Applications → Trade Room**.
3. This app is **unsigned by an identified developer and not notarized**. If
   macOS blocks it with “Apple could not verify…” / “developer cannot be
   verified”, dismiss the alert with **Done** or **Cancel** (not Move to Trash).
4. Immediately open **System Settings → Privacy & Security**. Scroll to the
   Security section and click **Open Anyway** next to Trade Room. Authenticate
   with your Mac password or Touch ID if asked, then click **Open** in the
   confirmation. The exception applies to this app; later double-clicks work.
   On older macOS versions, Control-click the app in Finder → Open → Open may
   also be available. On newer macOS use Privacy & Security as above.
5. The concise welcome appears over the existing workbench. Choose
   **Explore synthetic demo**. Six invented teams are ready without an account.
   **Set up ESPN · optional** opens a separate setup step, also available later
   from **Local setup**.

These are Apple's per-app first-open steps: [Safely open apps on your Mac](https://support.apple.com/en-us/102445).
Do not disable Gatekeeper or remove quarantine attributes. A managed Mac may
prohibit exceptions; its administrator must allow the app. If macOS reports
actual damage or malware, do not override that warning; obtain a verified copy.
A locally built DMG may have no download quarantine, so it may open directly.
That does not demonstrate the downloaded-file Gatekeeper exception flow.

The build does not invoke a signing tool or notarization service. Apple Silicon
Mach-O files carry compiler/linker-generated ad-hoc execution hashes, and
upstream runtime binaries retain their original hashes. These do not establish
a developer identity or notarization. The application bundle has no Developer
ID signature. No certificate or signing key is used.

## Use and stop

Choose your team under **Your perspective**, then **Scan the league**. Expand a
trade card for gains, lineups, depth, and warnings. **Trade workbench** evaluates
one or two players per side. Existing valuation and shortlist rules are preserved.

**Upload lineup screenshot** opens a native PNG/JPEG picker. OCR runs locally;
review/correct the detected team and explicitly confirm its full snapshot roster
before scanning. The player list scrolls independently; the player count,
acknowledgement, Discard and Confirm controls remain visible at 800×600 and larger.
Recognized text is available in an expandable reference. Screenshots, recognized text and roster snapshots are transient,
not saved or sent to a model. OS memory/swap is outside this guarantee.

**Local setup** in the top navigation or **Trade Room → Local Setup… (⌘,)**
reopens setup. **Quit**, **⌘Q**, or the red window-close button terminates the
local server and closes the window. No login item, daemon, container, or startup
service is installed. A crashed parent also closes the server through its stdin
lifetime pipe. A new launch always starts synthetic demo. Launches use a free
ephemeral IPv4 loopback port, so port 8000 need not be free. Finder reopens the
existing app instance; manually running several executables is not supported.

## Optional local ESPN setup

Use **Local setup** on your own Mac. Enter a four-digit season and numeric league
ID. For a private league, enter your own `espn_s2` and `SWID` values from your
signed-in browser's developer tools → Storage/Application → Cookies. Copy only
the value, not a whole cookie header; retain SWID braces. Public leagues can
uncheck **Private league**. No browser/account/credential discovery occurs.
Clear your clipboard after entry.

**Save locally · no connection** validates and saves settings without contacting
ESPN. Password fields are cleared after save, errors, or dialog closure; saved
values are never returned to the UI. **Load ESPN snapshot** is a separate explicit
action. Only this action reads saved secrets and invokes the existing adapter's
fixed-host read-only HTTPS GETs to `lm-api-reads.fantasy.espn.com`. Use it again to
refresh. A failed read keeps the previous snapshot and gives a controlled error.
An unsupported league, occupied IR slots, missing projections or an expired
cookie can prevent loading. No live private ESPN league was used in validation.

**Login Keychain** is the default. Settings are stored in this Mac's login
Keychain, with synchronizable=false and WhenUnlockedThisDeviceOnly access;
the helper uses only the app’s fixed service and app-owned credential slots. macOS may ask for
Keychain permission, especially after replacing this unsigned app. Allow only
if expected. Cancellation produces an error, with no silent file fallback.
The metadata file records the storage choice, slot identifiers, cleanup journal
and welcome state, not cookies. Saving creates a new Keychain slot before
committing metadata; the previous working slot is retired only after commit.
A failed save or metadata write preserves the previous working settings.
Migration to a file commits the file before deleting the old Keychain slot.

If Keychain is unavailable, explicitly choose **Private local file**. This stores
settings unencrypted in `~/Library/Application Support/Trade Room/settings.json`:
the app directory is `0700`, files are `0600`, owned by your account, and writes
use private temporary files plus atomic replacement. Linked paths are rejected.
Use a local home directory; cloud backups/snapshots can retain local files.
The app does not sync settings. Credentials are absent from URLs, command-line
arguments, bundled files, logs, analytics, and provider requests. Users/admins
controlling the OS account can inspect local files and process memory.

**Forget saved ESPN settings** first commits an empty configuration, then removes
app-owned Keychain slots and returns to demo. If metadata cannot be written,
the working configuration and credential are retained. If Keychain removal is
cancelled or unavailable after commit, **Local setup · cleanup pending** reports
it; use **Forget** to retry removal. Pending slot identifiers remain journaled
across restarts, including failed rollback cleanup. A completed save still uses
the new working credentials when cleanup is pending. Quit first if manually removing `settings.json` to recover corrupt config;
if Keychain storage was in use, use **Keychain Access** to delete the app-owned
“Trade Room — local ESPN settings” items too. File deletion does not securely
erase SSDs, backups, or snapshots. To uninstall, forget settings, quit, then
move the app and its Trade Room Application Support directory to Trash.

## Network and model boundaries

The desktop app always disables LLM functionality and collects no provider key.
Inherited ESPN/LLM/proxy/Python loader settings cannot opt it in. The native
WebKit view uses a nonpersistent data store and permits navigation only to its
own loopback origin. All UI assets are bundled. The server uses a fresh random
memory-only access token and the existing guarded same-origin nonce bootstrap;
no token appears in the URL. It listens only on `127.0.0.1`, not LAN interfaces.
No local browser profile or saved browser credentials are read.

Saving settings, demo, OCR and startup make no ESPN/provider request. The desktop
profile adds local setup operations; it adds no ESPN write endpoint. No trade
submission, roster modification, lineup edit or waiver action exists. The
standard-library HTTP server is for a trusted local desktop, not public hosting.

The adapter is unofficial and has only synthetic-response coverage. ESPN weekly
projections are full-week, with game-lock/bye status unavailable. The pool and
valuation limitations in README still apply. OCR can misread small/cropped text;
English is the supported recognition language. This is not investment or trade
acceptance advice.

## Build and verify (maintainers only)

Build on Apple Silicon macOS with Python 3.11+ and Apple command-line compiler
tools (`swiftc`, `iconutil`, `hdiutil`, `ditto`). Node is required only for the
existing JavaScript tests. End users need none of these build tools.

```sh
python3 scripts/build_macos.py
```

Output: `../fantasy-trade-valuator-artifacts/<VERSION>/` (outside the source
folder). For the current version: `cd ../fantasy-trade-valuator-artifacts/1.0.0`
then `shasum -a 256 -c SHA256SUMS`.
The builder pins the public standalone Python archive and Pillow wheel by hash,
copies an explicit runtime allowlist, preserves bundled licenses, compiles the
two native helpers and icon, and writes `Contents/Resources/BUILD.json`. It
creates the actual compressed DMG, an Applications shortcut, this guide, and
`SHA256SUMS` in that external output directory. Build setup needs internet; the installed demo and OCR do not.
The `.app` is a directory bundle and should be distributed inside the DMG so
executable bits and relative links survive. No whole-repository or credentials
copy is performed. The builder never signs, commits, pushes or publishes. A separate manual GitHub
workflow can prepare a draft after repository/tag setup; see RELEASE.md.

Run `python3 scripts/verify_release.py ../fantasy-trade-valuator-artifacts/1.0.0 --ui`.
See `LIFECYCLE_VALIDATION.md` in the repository for current mounted-DMG checks,
synthetic UI/OCR results, dependency audit, hashes, and remaining test limits.


## Checking for updates

Open **Updates** to see the installed version. Until the maintainer configures
a verified release repository, Check now is disabled. Once configured, only
clicking **Check now** contacts GitHub for public release metadata. A separate
button opens the release page in your browser. No league data or credentials
are sent; the app never downloads or installs updates. Download and verify
release assets yourself, quit Trade Room, and replace the app in Applications.
Keep following Apple's first-open steps; unsigned updates do not change them.
See RELEASE.md for checksum limits and the deferred Sparkle trust design.
