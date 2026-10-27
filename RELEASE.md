# Releasing the unsigned Mac app

The current version is 1.0.0. No remote, commit or release exists yet. This guide
prepares a future owner-authorized release; none of its Git/publish steps has been
performed. Generated apps and DMGs stay outside the source repository.

## One-time owner setup (before any release)

1. Review the source, license, privacy docs and staged/unstaged changes. Establish
   a GitHub repository and first commit only when explicitly authorized.
2. Set `release.json` to `{"repository":"OWNER/REPOSITORY"}` using the verified
   public repository. Rebuild to embed this identifier. Keep it null until then;
   private/token-authenticated feeds are not supported. No token belongs here.
3. Enable Actions, Dependabot, dependency/security alerts, secret scanning and
   push protection where available, and private vulnerability reporting. Protect
   main and release tags. Require source/workflow checks and reviews.
4. Create the `release` environment with required reviewers. Environment names
   alone do not enforce approval; configure the actual protection in GitHub.
   If your plan does not offer it, enforce owner review before running the manual
   workflow. Draft creation still never publishes automatically.

## Each release

1. Change only VERSION for the app number when an increment is authorized. Use
   `major.minor.patch` with no leading zeros or prerelease suffix. The first
   release stays 1.0.0. Info.plist, HTTP version, About box, metadata, update
   comparisons and DMG filename derive from it. Versions must increase after a
   published release; never replace a released tag/asset with different bytes.
2. Run `python3 scripts/preflight.py --workflows`. On an arm64 Mac run
   `python3 scripts/build_macos.py`, then
   `python3 scripts/verify_release.py ../fantasy-trade-valuator-artifacts/1.0.0 --ui`
   (substitute the new version). Save the synthetic verification result. Verify
   the local first-open instructions without altering quarantine/Gatekeeper.
3. Review changes, complete .github/RELEASE_NOTES.md with behavior, exact checks
   and remaining limits, then create the reviewed commit and matching `v<VERSION>`
   tag through the owner's authorized Git process. Push only when authorized.
4. Run **Prepare unsigned macOS release** manually from **main**, supplying the
   existing tag. Its source gate requires a clean tree, matching checked-out
   commit/tag and repository. It builds on macos-15 arm64, runs offline preflight,
   verifies checksums and the read-only mounted native app, and retains artifacts
   for 14 days. Full rendered WebKit QA remains step 2's manual gate; hosted
   graphical sessions are not assumed equivalent to a logged-in Mac desktop.
5. Review/approve the `release` environment. The next job verifies downloaded
   checksums and creates a **draft** with DMG, BUILD.json and SHA256SUMS. Review
   the draft and evidence; publish in GitHub only on explicit owner authorization.
   A failed/retried run does not overwrite an existing draft/release; inspect
   it before deciding how to proceed.

Local equivalents for the source gate and release verification:

```sh
python3 scripts/release_preflight.py --tag v1.0.0 --repository OWNER/REPOSITORY
python3 scripts/verify_release.py ../fantasy-trade-valuator-artifacts/1.0.0 --ui
cd ../fantasy-trade-valuator-artifacts/1.0.0
shasum -a 256 -c SHA256SUMS
```

The gate intentionally fails in today's uncommitted/unconfigured checkout.
Local development builds are permitted and marked dirty/revision null. Build
inputs are pinned, but Swift tools, OS, timestamps and DMG compression are not:
this is a repeatable process, **not** a claim of byte-identical reproducibility.
Release assets are snapshots; never edit generated app internals or DMG contents.

## Member updates and trust

Repo source, external scheduling wrappers and installed apps update separately;
see MAINTAINING.md. No source edit, scheduled job or Git fetch updates an installed
app. Quit, download from the verified release page, verify SHA256SUMS, mount and
replace the app in Applications. Local settings are outside the app bundle.

**Updates → Check now** is disabled until a repository is embedded. Opening the
app/panel and reading local status make no external request. Once configured,
Check now makes one credential-free HTTPS GitHub latest-stable-release metadata
request (8-second timeout, size cap, no proxy or redirects). GitHub sees the
request IP and app version; no league data is sent. Failure, missing release,
rate limits and private repositories give a retry message. Versions compare
numerically; draft/prerelease/malformed tags are rejected. A separate button opens
the validated release page in the browser. The app never requests binary assets,
downloads them, installs them or runs release content. SHA-256 is corruption
detection, not an independent publisher signature or proof of repository ownership.

## Future option: Sparkle and EdDSA

Sparkle can manage appcasts, version checks and installation, adding a framework,
helper processes, feed hosting and maintenance. Its documented trust design uses
HTTPS and Ed25519 archive signatures with `SUPublicEDKey` embedded in the app;
it also recommends Developer ID signing/notarization. An EdDSA signature does
not make an unsigned app notarized or remove Apple's first-open restrictions.
See the [official setup and signing guide](https://sparkle-project.org/documentation/).

For this unsigned app, manual replacement is currently simpler and keeps the
trust boundary explicit. Before considering Sparkle, establish an owned stable
release/feed URL, verify/pin the public key in a trusted initial distribution,
keep the private key outside source and ordinary CI artifacts, plan backup and
rotation/recovery, and test tampering, downgrade and read-only/translocated app
behavior. Evaluate signed feeds and archive validation before extraction. Loss
of an unsigned app's sole signing key is a serious recovery problem. Owner
approval would also need to define download/install consent and signing policy.
No Sparkle code, generated keys, feed or auto-install is wired in this project.
