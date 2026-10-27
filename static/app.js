'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
let league, players, teams, candidates = [], filter = 'all', token = '', scanVersion = 0, manualVersion = 0, ocrSuggested = new Set();
// Scrub legacy auth fragments, but never authenticate from URLs.
if (location.hash.startsWith('#access_token')) {
  history.replaceState(null, '', location.pathname + location.search);
}
async function bootstrapLocal() {
  const nonce = $('meta[name="trade-room-bootstrap"]')?.content;
  if (!nonce) return; // Manual deployments use the password form.
  try {
    const response = await fetch('/api/local-bootstrap', {
      headers: {'X-Trade-Room-Bootstrap': nonce}, mode: 'same-origin',
      credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer', redirect: 'error'
    });
    if (response.ok) {
      const body = await response.json();
      if (/^[A-Za-z0-9_-]{43}$/.test(body.token)) token = body.token;
    }
  } catch { /* Fall back to the password form on the normal API 401. */ }
}
let toastTimer;
const el = (tag, className, text) => { const n = document.createElement(tag); if (className) n.className = className; if (text !== undefined) n.textContent = text; return n; };
// A local blob icon avoids the browser's implicit /favicon.ico request.
if (document.head) {
  const icon = el('link'); icon.rel = 'icon';
  icon.href = URL.createObjectURL(new Blob(['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="4" fill="#244c3c"/><path d="M6 11h20l-5-5M26 21H6l5 5" fill="none" stroke="#f6f4ec" stroke-width="2"/></svg>'], {type: 'image/svg+xml'}));
  document.head.append(icon);
}
const signed = n => `${n >= 0 ? '+' : ''}${n.toFixed(2)}`;
function status(message) { $('#status').textContent = message; clearTimeout(toastTimer); if (message) toastTimer = setTimeout(() => $('#status').textContent = '', 8000); }
async function api(path, data, raw = false) {
  const headers = token ? {Authorization: `Bearer ${token}`} : {};
  const options = {headers};
  if (data !== undefined) { options.method = 'POST'; headers['Content-Type'] = raw ? data.type : 'application/json'; options.body = raw ? data : JSON.stringify(data); }
  const response = await fetch(path, options);
  const body = await response.json();
  if (response.status === 401) { $('#auth').hidden = false; $('#app').hidden = true; throw new Error('Enter your deployment access token.'); }
  if (!response.ok) throw new Error(body.error || 'Request failed');
  return body;
}
async function busy(button, task) { button.disabled = true; try { await task(); } catch (e) { status(e.message); } finally { button.disabled = false; } }
function playerNode(id) { const p = players.get(id); const n = el('div', 'player-name'); n.append(el('span', 'position', p.position), document.createTextNode(p.name)); return n; }
function seasonProvenance(model, warnings = []) {
  const details = el('details', 'lineup-block');
  details.append(el('summary', '', 'Season replacement provenance · primary & Doubtful/Out/IR-filtered sensitivity'));
  details.append(el('p', '', 'Primary season fit uses all projected free agents in the supplied snapshot pool at each position, including unavailable players. Baselines use native position; ties use player ID. The pool may be incomplete. The Doubtful/Out/IR-filtered sensitivity excludes `DOUBTFUL`, `OUT/O`, and IR/injury-reserve aliases. It retains `QUESTIONABLE`, `SUSPENDED`, and other statuses outside that explicit filter; weekly lineup logic still treats SUSPENDED as unavailable. Rostered season projections stay unchanged in both. Bye and started-game flags do not filter either full-season baseline. Only primary season fit determines scores, verdicts and qualification.'));
  details.append(el('p', '', model.ros.reason));
  for (const [policy, label] of [['primary', 'Primary'], ['doubtful_out_ir_filtered', 'Doubtful/Out/IR-filtered sensitivity']]) {
    const list = el('ul');
    for (const r of model.replacement[policy]) {
      const excluded = Object.entries(r.excluded_status_counts || {}).map(([status, count]) => `${status}=${count}`).join(', ') || 'none';
      const source = r.selected ? `${r.selected.name} [${r.selected.id}] · ${r.selected.status}${r.selected.bye ? ' · bye' : ''}${r.selected.started ? ' · game started' : ''}; season ${r.season_projection.toFixed(2)}` : 'No projected baseline; zero baseline disclosed';
      list.append(el('li', '', `${r.position} · ${label} · ${r.relevant ? 'relevant' : 'no startable rostered player'}: ${source}; excluded statuses ${excluded}; ÷${model.divisor} = ${r.weekly_equivalent.toFixed(2)}/wk. Pool ${r.pool_count}, projected ${r.projected_count}, policy-eligible ${r.eligible_count}.`));
    }
    details.append(list);
  }
  warnings.forEach(w => details.append(el('p', 'warning', w)));
  return details;
}
function metricTable(trade) {
  const table = el('table', 'metric-table');
  const head = el('tr'); ['', 'Before', 'After', 'Change', 'Known coverage'].forEach(t => head.append(el('th', '', t))); table.append(head);
  for (const [side, label] of [['yours','You'], ['theirs','Them']]) for (const [mode, unit] of [['season','Season fit'], ['week','Week']]) {
    const m = trade[side][mode]; const row = el('tr');
    [`${label} · ${unit}`, m.before.total.toFixed(2), m.after.total.toFixed(2), signed(m.delta), `${m.before.coverage}/${m.before.slots} → ${m.after.coverage}/${m.after.slots}`].forEach(t => row.append(el('td', '', t))); table.append(row);
  }
  for (const [side, label] of [['yours', 'You'], ['theirs', 'Them']]) {
    const m = trade.sensitivity[side], row = el('tr');
    [`${label} · Doubtful/Out/IR-filtered free-agent sensitivity`, m.before.total.toFixed(2), m.after.total.toFixed(2), signed(m.delta), `${m.before.coverage}/${m.before.slots} → ${m.after.coverage}/${m.after.slots}`].forEach(t => row.append(el('td', '', t))); table.append(row);
  }
  return table;
}
function card(trade, index, open = false) {
  const details = el('details', 'card'); details.open = open;
  const summary = el('summary'); const top = el('div', 'card-top');
  top.append(el('span', 'candidate-number', index ? `OPPORTUNITY ${String(index).padStart(2,'0')}` : 'YOUR PROPOSED TRADE'), el('span', 'fit-tag', trade.verdict.toUpperCase()));
  summary.append(top, el('h3', '', `${trade.give.length}-for-${trade.receive.length} · ${teams.get(trade.other_id).name}`), el('div', 'partner', 'A potential fit for your two rosters'));
  const row = el('div', 'trade-row');
  for (const [ids, label] of [[trade.give, 'YOU SEND'], [trade.receive, 'YOU RECEIVE']]) { if (row.children.length) row.append(el('span', 'arrow', '⇄')); const side = el('div'); side.append(el('div', 'side-title', label)); ids.forEach(id => side.append(playerNode(id))); row.append(side); }
  summary.append(row);
  const bottom = el('div', 'card-bottom'), gains = el('div', 'gains');
  for (const [side, label] of [['yours', 'YOUR SEASON FIT / WK'], ['theirs', 'THEIR SEASON FIT / WK']]) { const gain = el('div', 'gain'); gain.append(el('strong', '', signed(trade[side].season.delta)), el('span', '', label)); gains.append(gain); }
  bottom.append(gains, el('span', 'expand-label', 'The breakdown')); summary.append(bottom); details.append(summary);
  const content = el('div', 'details-content'); content.append(el('p', '', trade.explanation), metricTable(trade));
  content.append(seasonProvenance(trade.season_model, trade.sensitivity.warnings));
  if (trade.llm_summary) summary.append(el('p', 'search-note', `AI summary: ${trade.llm_summary}`));
  if (index && trade.llm_reason) content.append(el('p', '', `AI ranking note: ${trade.llm_reason}`));
  trade.warnings.forEach(w => content.append(el('p', 'warning', w)));
  for (const [side, label] of [['yours', 'Your'], ['theirs', 'Their']]) for (const mode of ['week', 'season']) for (const phase of ['before', 'after']) {
    const lineup = trade[side][mode][phase];
    if (lineup.benched_slots) content.append(el('p', '', `${label} ${mode} lineup ${phase}: ${lineup.benched_slots} slot(s) intentionally empty to maximize points. Known projections can cover ${lineup.coverage}/${lineup.slots} slots; ${lineup.filled} starters selected.`));
  }
  for (const [side, label] of [['yours','Your'], ['theirs','Their']]) {
    for (const [impact, name] of [[trade[side].season, 'primary'], [trade.sensitivity[side], 'Doubtful/Out/IR-filtered free-agent sensitivity']]) {
      const lineups = el('details', 'lineup-block'); lineups.append(el('summary', '', `${label} ${name} legal starting lineup · before & after`)); const grid = el('div', 'lineup-grid');
      for (const phase of ['before','after']) { const col = el('div'); col.append(el('strong', '', phase.toUpperCase())); const list = el('ul'); impact[phase].lineup.forEach(p => list.append(el('li', '', `${p.slot} · ${players.get(p.player_id).name}`))); col.append(list); grid.append(col); } lineups.append(grid); content.append(lineups);
    }
    const depth = trade[side].depth.filter(d => d.before !== d.after).map(d => `${d.position} ${d.before} → ${d.after}`).join(' · ');
    content.append(el('p', '', `${label} roster: ${trade[side].roster_before} → ${trade[side].roster_after} / ${league.roster_limit}. ${depth || 'Position counts unchanged.'}`));
  }
  content.append(el('p', '', 'Season fit: full-season projected points per week above positional replacement, using season projection ÷ 17. This is not a rest-of-season forecast. Weekly totals are separate. Bench players contribute no value to this model.'));
  details.append(content); return details;
}
function showCards() {
  const shown = candidates.filter(c => filter === 'all' || (filter === 'one' ? c.give.length === 1 && c.receive.length === 1 : c.give.length + c.receive.length > 2));
  $('#cards').replaceChildren(...shown.map((c,i) => card(c, i+1)));
  if (!shown.length) { const empty = el('div','empty'); empty.append(el('strong','', 'No matching mutual-upside trades.'), el('span','', 'Try another perspective or evaluate a deal on the workbench. We never invent a trade to fill this space.')); $('#cards').append(empty); }
}
async function scan(confirmation = {}) {
  const version = ++scanVersion; const teamId = $('#my-team').value;
  $('#cards').replaceChildren(el('div', 'empty', 'Checking legal trade packages across the league…'));
  const result = await api('/api/candidates', {team_id: teamId, use_llm: $('#llm-rank').checked, ...confirmation});
  if (version !== scanVersion || teamId !== $('#my-team').value) return;
  candidates = result.candidates; $('#checked-count').textContent = result.checked.toLocaleString(); $('#qualified-count').textContent = result.qualified;
  $('#search-note').textContent = `${result.opponents} opposing teams · ${result.search} Showing up to 12. AI: ${result.llm_status}. ${result.warnings?.length ? 'Data gaps: ' + result.warnings.join(' ') : ''}`;
  $('#season-provenance').replaceChildren(seasonProvenance(result.season_model, result.sensitivity_warnings));
  showCards();
}
function options(target, teamId, side) {
  $(target).replaceChildren(...teams.get(teamId).players.map(p => { const label = el('label','player-option'); const input = el('input'); input.type = 'checkbox'; input.value = p.id; input.name = side;
    input.addEventListener('change', () => { if ($$(`input[name="${side}"]:checked`).length > 2) { input.checked = false; status('Choose at most two players on each side.'); } clearManual(); });
    label.append(input, document.createTextNode(p.name), el('span','position',p.position)); return label; }));
}
function clearManual() { ++manualVersion; $('#manual-result').replaceChildren(); }
function updatePartner() { options('#receive-options', $('#other-team').value, 'receive'); clearManual(); }
function updatePerspective() {
  const my = $('#my-team').value; $('.avatar').textContent = teams.get(my).name.split(' ').map(x=>x[0]).slice(0,2).join('');
  $('#your-roster-label').textContent = teams.get(my).name; options('#give-options', my, 'give');
  $('#other-team').replaceChildren(...league.teams.filter(t => t.id !== my).map(t => { const n = el('option','',t.name); n.value=t.id; return n; })); updatePartner();
}
async function evaluate() {
  clearManual();
  const version = manualVersion;
  const give = $$('input[name="give"]:checked').map(n=>n.value), receive = $$('input[name="receive"]:checked').map(n=>n.value);
  if (!give.length || !receive.length) throw new Error('Choose one or two players on both sides.');
  let trade;
  try {
    trade = await api('/api/evaluate', {team_id: $('#my-team').value, other_id: $('#other-team').value, give, receive, source: 'manual', use_llm: $('#llm-summary').checked});
  } catch (error) {
    if (version !== manualVersion) return;
    throw error;
  }
  if (version !== manualVersion) return;
  $('#manual-result').replaceChildren(card(trade, 0, true));
  if (trade.llm_status) $('#manual-result').append(el('p', 'search-note', `AI: ${trade.llm_status}.`));
}
function clearOcr() { ocrSuggested.clear(); $('#ocr-team').replaceChildren(); $('#ocr-ack').checked = false; $('#ocr-text').value = ''; $('#ocr-matches').replaceChildren(); $('#ocr-note').textContent = ''; $('#ocr-count').textContent = ''; $('#ocr-reference').open = false; $('#upload').value = ''; }
async function upload(file) {
  if (!file) return;
  if (!['image/png','image/jpeg'].includes(file.type) || file.size > 5*1024*1024) throw new Error('Choose a PNG/JPEG up to 5 MiB.');
  status('Reading screenshot locally…');
  const result = await api('/api/ocr', file, true); $('#ocr-text').value = result.text; $('#ocr-matches').replaceChildren();
  ocrSuggested = new Set(result.suggestions.flatMap(s=>s.matches.map(m=>m.player_id)));
  // Count only unambiguous strong matches; mixed/tied screenshots require a team choice.
  const detected = new Set(result.suggestions.flatMap(row => {
    const [first, second] = row.matches;
    return first && first.confidence >= .85 && (!second || first.confidence > second.confidence)
      ? [first.player_id] : [];
  }));
  const counts = league.teams.map(t => ({id:t.id, count:t.players.filter(p=>detected.has(p.id)).length}));
  const owners = counts.filter(t=>t.count > 0);
  const placeholder = el('option', '', 'Choose your team'); placeholder.value = '';
  $('#ocr-team').replaceChildren(placeholder, ...league.teams.map(t=>{const n=el('option','',t.name);n.value=t.id;return n;}));
  $('#ocr-team').value = owners.length === 1 ? owners[0].id : '';
  reviewRoster();
  $('#ocr-note').textContent = result.text.trim()
    ? 'Review all players below. OCR matches are suggestions.'
    : 'No text recognized. Choose your team, or discard and try a clearer image.';
  $('#ocr-dialog').showModal(); status(''); $('#upload').value='';
}
function reviewRoster() {
  $('#ocr-ack').checked = false;
  const team = teams.get($('#ocr-team').value);
  $('#ocr-count').textContent = team ? `${team.players.length} players` : 'Choose a team';
  $('#ocr-matches').scrollTop = 0;
  $('#ocr-matches').replaceChildren(...(team ? team.players.map(p=>{
    const row = el('div','player-option');
    row.append(playerNode(p.id), el('span', 'muted', ocrSuggested.has(p.id) ? 'Possible screenshot match' : 'Snapshot roster · not detected'));
    return row;
  }) : []));
}
async function confirmRoster() {
  const team = teams.get($('#ocr-team').value);
  if (!team || !$('#ocr-ack').checked) throw new Error('Choose your team and explicitly confirm the displayed full roster.');
  $('#my-team').value = team.id; updatePerspective();
  filter = 'all'; $$('[data-filter]').forEach(n=>n.classList.toggle('selected',n.dataset.filter === 'all'));
  await scan({source:'ocr', confirmed:true, roster_ids:team.players.map(p=>p.id)});
  $('#ocr-dialog').close(); $('#cards').scrollIntoView({behavior:'smooth',block:'start'});
}

async function initialize() {
  league = await api('/api/league'); const health = await api('/health');
  teams = new Map(league.teams.map(t=>[t.id,t])); players = new Map(league.teams.flatMap(t=>t.players).map(p=>[p.id,p]));
  $('#auth').hidden=true; $('#app').hidden=false;
  $('#league-name').textContent=league.name; $('#league-info').textContent=`${league.season} · Week ${league.week}`; $('#team-count').textContent=league.teams.length;
  $('#source-badge').textContent=health.source === 'synthetic' ? 'SYNTHETIC DEMO' : 'ESPN · READ-ONLY';
  $('#provenance').textContent=`Source: ${league.source}. Snapshot: ${league.fetched_at}. Scoring: ${league.scoring}. Demo data is fixed and synthetic. ESPN access requires operator configuration and explicit server startup mode.`;
  for (const selector of ['#llm-rank', '#llm-summary']) { $(selector).disabled=!health.llm_available; $(selector).checked=health.llm_available; }
  $('#llm-badge').textContent=health.llm_available ? 'ON' : 'DISABLED';
  $('#upload-button').disabled=!health.ocr_available; $('#upload-button').title=health.ocr_available ? 'Recognize screenshot text locally on this computer' : 'Local OCR is unavailable; use manual player selection';
  $('#my-team').replaceChildren(...league.teams.map(t=>{const o=el('option','',t.name);o.value=t.id;return o;})); updatePerspective();
  $('#cards').replaceChildren(el('div', 'empty', 'Upload a lineup screenshot and confirm your roster, or choose your team and scan the league.'));
}
$('#auth-form').addEventListener('submit', event=>{event.preventDefault();token=$('#token').value;$('#token').value='';return busy($('#auth-form button'),initialize);});
$('#scan').addEventListener('click',()=>busy($('#scan'),scan));
$('#my-team').addEventListener('change',()=>{updatePerspective();busy($('#scan'),scan);});
$('#other-team').addEventListener('change',updatePartner);
$('#evaluate').addEventListener('click',()=>busy($('#evaluate'),()=>evaluate()));
$$('[data-filter]').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;$$('[data-filter]').forEach(n=>n.classList.toggle('selected',n===b));showCards();}));
$('#llm-rank').addEventListener('change',()=>{$('#llm-badge').textContent=$('#llm-rank').checked?'ON':'OFF';});
$('#llm-summary').addEventListener('change',clearManual);
$('#method-open').addEventListener('click',()=>$('#method-dialog').showModal());
$('#upload-button').addEventListener('click',()=>$('#upload').click());
$('#upload').addEventListener('change',()=>busy($('#upload-button'),()=>upload($('#upload').files[0])));
$('#ocr-clear').addEventListener('click',()=>$('#ocr-dialog').close());
$('#ocr-dialog').addEventListener('close',clearOcr);
$('#ocr-team').addEventListener('change',reviewRoster);
$('#ocr-confirm').addEventListener('click',()=>busy($('#ocr-confirm'),confirmRoster));
bootstrapLocal().then(initialize).catch(e=>status(e.message));
