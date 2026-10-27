'use strict';
// Loaded only by the native desktop profile; all assets and setup requests are local.
const setupButton = el('button', 'nav-button', 'Local setup');
setupButton.id = 'desktop-setup';
$('nav').append(setupButton);
const quitButton = el('button', 'nav-button', 'Quit');
quitButton.id = 'desktop-quit';
$('nav').append(quitButton);
quitButton.addEventListener('click', () => window.webkit?.messageHandlers.lifecycle.postMessage('quit'));
const updateDialog = document.createElement('dialog');
updateDialog.id = 'desktop-updates';
updateDialog.setAttribute('aria-labelledby', 'desktop-updates-title');
updateDialog.innerHTML = `<form method="dialog"><button class="close" aria-label="Close updates">×</button></form>
<div class="eyebrow">SYSTEM / UPDATES</div>
<h2 id="desktop-updates-title">App updates</h2>
<p class="update-state" id="desktop-update-status" role="status" aria-live="polite"></p>
<p>When configured, Check now requests release metadata from GitHub. No league data or credentials are sent. Downloads and installation are always manual.</p>
<div class="dialog-actions"><button id="desktop-check-updates" class="secondary" disabled>Check now</button><button id="desktop-open-release" class="primary" hidden>Open release page in browser</button></div>`;
document.body.append(updateDialog);
const updateButton = el('button', 'nav-button', 'Updates');
updateButton.id = 'desktop-update-menu';
// Keep the compact navigation usable at the minimum window width.
quitButton.before(updateButton);
updateButton.addEventListener('click', () => updateDialog.showModal());
let releaseAddress;
$('#desktop-check-updates').addEventListener('click', async () => {
  $('#desktop-check-updates').disabled = true;
  $('#desktop-open-release').hidden = true;
  releaseAddress = undefined;
  $('#desktop-update-status').textContent = 'Checking published releases…';
  try {
    const result = await api('/api/desktop', {action:'check-updates'});
    $('#desktop-update-status').textContent = result.state === 'available'
      ? `Version ${result.latest_version} is available. You have ${result.current_version}.`
      : result.state === 'current' ? `You have ${result.current_version}. No newer stable release is available.`
      : 'Update checks are unavailable until the maintainer configures a release repository.';
    if (result.state === 'available') {
      releaseAddress = result.release_url;
      $('#desktop-open-release').hidden = false;
    }
  } catch (error) { $('#desktop-update-status').textContent = error.message; }
  finally { $('#desktop-check-updates').disabled = !desktopState?.updates.enabled; }
});
$('#desktop-open-release').addEventListener('click', () => {
  if (releaseAddress) window.webkit?.messageHandlers.lifecycle.postMessage({action:'open-release', url:releaseAddress});
});
const welcome = document.createElement('dialog');
welcome.id = 'desktop-welcome';
welcome.setAttribute('aria-labelledby', 'desktop-welcome-title');
welcome.innerHTML = `
<div class="arrival-art" aria-hidden="true"><span class="arrival-code">TRADE ROOM / LOCAL TERMINAL<br>01 — LINEUP INTELLIGENCE</span><svg class="city-signal" viewBox="0 0 400 130" xmlns="http://www.w3.org/2000/svg"><path d="M0 120H60V65H85V90H123V27H139V10H150V27H176V120H211V72H247V105H286V42H305V24H317V42H344V102H400V130H0Z" fill="#0a1825"/><path d="M139 35V112M305 50V120M0 125H400" stroke="#77dce2" stroke-opacity=".5"/><path d="M58 95H210V56H268" fill="none" stroke="#ffb06c" stroke-opacity=".6"/></svg></div>
<div class="eyebrow">YOUR MAC. YOUR LEAGUE. YOUR NEXT MOVE.</div>
<h2 id="desktop-welcome-title">Enter the trade room.</h2>
<p>Find the edge in two better lineups. Explore six synthetic teams and inspect the numbers behind every opportunity.</p>
<div class="desktop-facts"><span>On-device screenshot OCR · AI off</span><span>Closing this window or ⌘Q stops the local server.</span></div>
<div class="dialog-actions welcome-actions"><button id="desktop-demo" class="primary" autofocus>Explore synthetic demo</button><button id="desktop-optional" class="nav-button">Set up ESPN · optional</button></div>
<p id="desktop-welcome-message" role="status" aria-live="polite">No account or connection needed. ESPN setup is always in Local setup.</p>`;
document.body.append(welcome);
const setup = document.createElement('dialog');
setup.id = 'desktop-dialog';
setup.setAttribute('aria-labelledby', 'desktop-setup-title');
setup.innerHTML = `
<form method="dialog"><button class="close" aria-label="Close local setup">×</button></form>
<div class="eyebrow">OPTIONAL · LOCAL SETUP</div>
<h2 id="desktop-setup-title">Your ESPN snapshot.</h2>
<p id="desktop-state" role="status"></p>
<p>Saving stays local. <strong>Load ESPN snapshot</strong> separately makes read-only requests. Each launch starts in the synthetic demo.</p>
<details class="desktop-help"><summary>Where to find your league details</summary><p>Use your own authorized league. Find leagueId in its page address. For private leagues, copy espn_s2 and SWID from your signed-in browser’s developer tools → Storage/Application → Cookies. Keep SWID braces and clear your clipboard after entry. Unsupported rosters or occupied IR slots may be rejected.</p></details>
<form id="desktop-settings" autocomplete="off">
<div class="desktop-grid"><label>Season year<input id="desktop-year" inputmode="numeric" required pattern="20[0-9]{2}" maxlength="4"></label><label>League ID<input id="desktop-league" type="password" inputmode="numeric" required pattern="[0-9]{1,20}" maxlength="20" autocomplete="off"></label></div>
<label class="player-option"><input id="desktop-private" type="checkbox" checked> Private league (both cookies required)</label>
<div id="desktop-cookies" class="desktop-grid"><label>espn_s2<input id="desktop-s2" type="password" maxlength="8192" autocomplete="off" spellcheck="false" required></label><label>SWID<input id="desktop-swid" type="password" maxlength="8192" autocomplete="off" spellcheck="false" required></label></div>
<label>Store settings<select id="desktop-storage"><option value="keychain">Login Keychain — this Mac only (recommended)</option><option value="file">Private local file — not encrypted</option></select></label>
<p class="muted">Keychain may ask for local permission. File storage uses a 0700 directory and 0600 file in ~/Library/Application Support/Trade Room. Nothing is synced by this app. Anyone controlling your OS account can access local data. Saved credentials are never displayed.</p>
<button id="desktop-save" class="secondary" type="submit">Save locally · no connection</button>
</form>
<p id="desktop-message" role="status" aria-live="polite"></p>
<div class="dialog-actions"><button id="desktop-forget" class="secondary">Forget saved ESPN settings</button><button id="desktop-load" class="primary">Load ESPN snapshot</button></div>`;
document.body.append(setup);
let desktopState;
function clearDesktopSecrets() {
  for (const id of ['#desktop-league', '#desktop-s2', '#desktop-swid']) $(id).value = '';
}
function renderDesktop(state) {
  desktopState = state;
  $('#desktop-check-updates').disabled = !state.updates.enabled;
  $('#desktop-check-updates').textContent = state.updates.enabled ? 'Check now' : 'Check now · unavailable';
  $('#desktop-update-status').dataset.enabled = String(state.updates.enabled);
  if (!releaseAddress) $('#desktop-update-status').textContent = state.updates.enabled
    ? `Version ${state.updates.current_version}. Check now to contact GitHub for release metadata.`
    : `Version ${state.updates.current_version}. Updates disabled — no release repository is configured. The maintainer must configure one in a future build.`;
  $('#desktop-state').textContent = state.configured
    ? `ESPN settings saved in ${state.storage === 'keychain' ? 'login Keychain' : 'a private local file'}. Current source is shown in the league bar. Loading is always explicit.`
    : 'Synthetic demo is ready. No ESPN settings saved; no ESPN connection made.';
  $('#desktop-load').disabled = !state.configured;
  $('#desktop-forget').disabled = !state.configured && !state.cleanup_pending;
  setupButton.textContent = state.cleanup_pending ? 'Local setup · cleanup pending' : 'Local setup';
  if (state.cleanup_pending) $('#desktop-state').textContent += ' Previous Keychain removal is pending. Use Forget to retry; it also clears the current ESPN settings.';
}
async function desktopAction(data, reload = false) {
  const controls = [...setup.querySelectorAll('button, input, select'), ...welcome.querySelectorAll('button')];
  controls.forEach(n => n.disabled = true);
  $('#desktop-message').textContent = data.action === 'espn' ? 'Reading your ESPN snapshot… No trades will be submitted.' : 'Applying local settings…';
  try {
    const state = await api('/api/desktop', data);
    clearDesktopSecrets();
    if (reload) { location.reload(); return true; }
    renderDesktop(state);
    $('#desktop-message').textContent = data.action === 'save' ? 'Saved locally. No ESPN connection made. Use Load ESPN snapshot when ready.' : '';
    return true;
  } catch (error) {
    clearDesktopSecrets();
    $('#desktop-message').textContent = error.message;
    $('#desktop-welcome-message').textContent = error.message;
    try { renderDesktop(await api('/api/desktop')); } catch (_) { /* Preserve the actionable error. */ }
    return false;
  } finally {
    controls.forEach(n => n.disabled = false);
    if (desktopState) renderDesktop(desktopState);
    $('#desktop-s2').disabled = $('#desktop-swid').disabled = !$('#desktop-private').checked;
  }
}
function openDesktopSetup() {
  welcome.close(); clearDesktopSecrets(); $('#desktop-message').textContent = ''; setup.showModal();
}
setupButton.addEventListener('click', openDesktopSetup);
$('#desktop-optional').addEventListener('click', openDesktopSetup);
setup.addEventListener('close', clearDesktopSecrets);
welcome.addEventListener('cancel', event => { event.preventDefault(); if (!$('#desktop-demo').disabled) $('#desktop-demo').click(); });
setup.addEventListener('cancel', event => { if ($('#desktop-save').disabled) event.preventDefault(); });
$('#desktop-private').addEventListener('change', () => {
  const isPrivate = $('#desktop-private').checked;
  $('#desktop-cookies').hidden = !isPrivate;
  for (const id of ['#desktop-s2', '#desktop-swid']) { $(id).disabled = !isPrivate; $(id).required = isPrivate; $(id).value = ''; }
});
$('#desktop-settings').addEventListener('submit', event => {
  event.preventDefault();
  return desktopAction({action:'save', storage:$('#desktop-storage').value, espn:{
    year:$('#desktop-year').value.trim(), league_id:$('#desktop-league').value.trim(),
    s2:$('#desktop-private').checked ? $('#desktop-s2').value : '',
    swid:$('#desktop-private').checked ? $('#desktop-swid').value : ''}});
});
$('#desktop-load').addEventListener('click', () => desktopAction({action:'espn'}, true));
$('#desktop-forget').addEventListener('click', () => desktopAction({action:'forget'}, true));
$('#desktop-demo').addEventListener('click', async () => {
  if (!await desktopAction({action:'welcome'})) return;
  if ($('#source-badge').textContent.includes('ESPN')) await desktopAction({action:'demo'}, true);
  else welcome.close();
});
bootstrapLocal().then(async () => {
  renderDesktop(await api('/api/desktop'));
  $('#desktop-year').value = desktopState.year;
  if (!desktopState.welcomed) welcome.showModal();
}).catch(() => status('Local setup unavailable. Quit and reopen Trade Room.'));
