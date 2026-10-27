// Synthetic DOM/API harness: exercises the actual app controller without network or dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'static/index.html'), 'utf8');
const source = fs.readFileSync(path.join(root, 'static/app.js'), 'utf8')
  .replace('bootstrapLocal().then(initialize).catch(e=>status(e.message));', 'globalThis.ready = bootstrapLocal().then(initialize).catch(e=>status(e.message));');
const league = JSON.parse(fs.readFileSync(path.join(root, 'fixtures/demo.json'), 'utf8'));
class Node {
  constructor(tag = '') { this.tag = tag; this.children = []; this.listeners = {}; this.dataset = {}; this.value = ''; this.checked = false; this.disabled = false; this.textContent = ''; this.classList = {toggle() {}}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; if (this.tag === 'select') this.value = nodes[0]?.value || ''; }
  addEventListener(event, fn) { this.listeners[event] = fn; }
  showModal() { this.open = true; }
  close() { this.open = false; this.listeners.close?.(); }
  scrollIntoView() { this.scrolled = true; }
}
const textOf = node => node.textContent + node.children.map(textOf).join(' ');
async function harness(available, enabled = available, fragment = '', auth = {}) {
  const nodes = Object.fromEntries([...html.matchAll(/<([\w]+)[^>]*\bid="([^"]+)"/g)].map(m=>[m[2], new Node(m[1])]));
  nodes['.avatar'] = new Node();
  nodes['auth-form button'] = new Node('button');
  const filters = ['all', 'one', 'package'].map(value=>{const n=new Node();n.dataset.filter=value;return n;});
  const walk = node => [node, ...node.children.flatMap(walk)];
  const document = {
    createElement: tag=>new Node(tag), createTextNode: text=>Object.assign(new Node(), {textContent:text}),
    querySelector: selector=>selector === 'meta[name="trade-room-bootstrap"]' ? (auth.nonce ? {content:auth.nonce} : null)
      : nodes[selector.startsWith('#') ? selector.slice(1) : selector],
    querySelectorAll: selector=>{
      if (selector === '[data-filter]') return filters;
      const name = selector.match(/^input\[name="(\w+)"\]:checked$/)?.[1];
      if (name) return Object.values(nodes).flatMap(walk).filter(n=>n.name === name && n.checked);
      throw Error('Unhandled selector: ' + selector);
    }
  };
  const calls = [];
  const replacements = [];
  const location = {hash:fragment, pathname:'/', search:''};
  const manualReplies = [];
  let ocr = {text:'Bennett Vale', suggestions:[{matches:[{player_id:'harbor-2', confidence:1}]}]};
  const lineup = {total:10,coverage:1,slots:1,filled:1,benched_slots:0,lineup:[]};
  const side = {season:{delta:2,before:lineup,after:lineup},week:{delta:-1,before:lineup,after:lineup},depth:[],roster_before:12,roster_after:12};
  const baseline = {position:'RB',relevant:true,pool_count:2,projected_count:2,eligible_count:2,excluded_status_counts:{},zero_fallback:false,
    selected:{id:'synthetic-fa',name:'Synthetic FA <unsafe>',status:'OUT',bye:false,started:false},season_projection:170,weekly_equivalent:10};
  const model = {horizon:'full_season',divisor:17,primary_policy:'all_projected_free_agents',sensitivity_policy:'exclude_doubtful_out_ir_free_agents',
    replacement:{primary:[baseline],doubtful_out_ir_filtered:[{...baseline,eligible_count:0,excluded_status_counts:{DOUBTFUL:1,OUT:1,IR:1},zero_fallback:true,selected:null,season_projection:null,weekly_equivalent:0}]},
    ros:{available:false,value:null,reason:'The current ESPN source has no verified ROS field; no ROS number is produced.'}};
  const candidate = {team_id:'harbor',other_id:'orbit',give:['harbor-2'],receive:['orbit-5'],yours:side,theirs:side,verdict:'Mutual upside',explanation:'Computed explanation',warnings:[],llm_summary:'Season gains come with a current-week cost.',season_model:model,
    sensitivity:{affects_ranking:false,policy:'exclude_doubtful_out_ir_free_agents',yours:{delta:4,before:lineup,after:{...lineup,total:14}},theirs:{delta:4,before:lineup,after:{...lineup,total:14}},warnings:['Doubtful/Out/IR-filtered sensitivity: no free-agent baseline for: RB; zero baseline disclosed']}};
  let scanCandidates = [candidate];
  const context = vm.createContext({document, location, history:{replaceState:(state,title,url)=>{
    replacements.push(url); location.hash='';
  }}, setTimeout:()=>1,clearTimeout:()=>{},fetch:async(url,options)=>{
    const data = options.body && options.headers['Content-Type'] === 'application/json' ? JSON.parse(options.body) : options.body;
    calls.push({url,data,headers:{...options.headers},hash:location.hash,options});
    if (url === '/api/local-bootstrap') {
      if (auth.networkError) throw Error('Synthetic bootstrap failure');
      return {ok:!auth.fail,status:auth.fail ? 403 : 200,json:async()=>({token:auth.invalidToken ? 'short' : 'a'.repeat(43)})};
    }
    if (auth.required && url.startsWith('/api/') && options.headers.Authorization !== 'Bearer ' + 'a'.repeat(43)) {
      return {ok:false,status:401,json:async()=>({error:'Enter the deployment access token'})};
    }
    if (url === '/api/evaluate' && manualReplies.length) return await manualReplies.shift();
    const body = url === '/api/league' ? league : url === '/health' ? {source:'synthetic',llm_enabled:enabled,llm_available:available,ocr_available:true}
      : url === '/api/ocr' ? ocr : url === '/api/candidates' ? {candidates:scanCandidates,checked:2205,qualified:38,opponents:5,warnings:['Synthetic coverage gap'],search:'All opposing teams.',llm_status:'mocked',season_model:model,sensitivity_warnings:candidate.sensitivity.warnings} : candidate;
    return {ok:true,status:200,json:async()=>body};
  }});
  vm.runInContext(source, context);
  await context.ready;
  return {nodes,calls,replacements,run:code=>vm.runInContext(code,context),setOcr:value=>{ocr=value;},emptyScan:()=>{scanCandidates=[];},holdManual:()=>{
    let resolve, reject;
    manualReplies.push(new Promise((yes,no)=>{resolve=yes;reject=no;}));
    return {resolve:(changes={})=>resolve({ok:true,status:200,json:async()=>({...candidate,...changes})}),reject};
  }};
}
function selectManual(nodes) {
  nodes['give-options'].children[1].children[0].checked=true;
  nodes['receive-options'].children[4].children[0].checked=true;
}
async function testManualRaces() {
  const changes = {
    'own team':async n=>{n['my-team'].value='orbit';await n['my-team'].listeners.change();},
    'partner':async n=>{n['other-team'].value=n['other-team'].children[1].value;await n['other-team'].listeners.change();},
    'give player':async n=>{const p=n['give-options'].children[1].children[0];p.checked=false;await p.listeners.change();},
    'receive player':async n=>{const p=n['receive-options'].children[4].children[0];p.checked=false;await p.listeners.change();},
    'AI preference':async n=>{n['llm-summary'].checked=false;await n['llm-summary'].listeners.change();},
    'selection changed back':async n=>{const p=n['give-options'].children[1].children[0];p.checked=false;await p.listeners.change();p.checked=true;await p.listeners.change();},
  };
  for (const [label, change] of Object.entries(changes)) for (const failure of [false,true]) {
    const h=await harness(true), n=h.nodes;
    selectManual(n);
    await n['evaluate'].listeners.click(); // Previously rendered cards clear immediately on change.
    const reply=h.holdManual(), pending=n['evaluate'].listeners.click();
    assert.equal(n['manual-result'].children.length,0);
    await change(n);
    if (failure) reply.reject(Error('Obsolete evaluation failed')); else reply.resolve({llm_status:'stale annotation'});
    await pending;
    assert.equal(n['manual-result'].children.length,0,label);
    assert.doesNotMatch(n['status'].textContent,/Obsolete evaluation failed/,label);
    assert.equal(n['evaluate'].disabled,false);
  }
  const h=await harness(true), n=h.nodes;
  selectManual(n);
  const older=h.holdManual(), first=h.run('evaluate()');
  const newer=h.holdManual(), second=h.run('evaluate()');
  newer.resolve({explanation:'Current evaluation',llm_status:'current annotation'});await second;
  const current=n['manual-result'].children[0];
  older.resolve({explanation:'Obsolete evaluation',llm_status:'stale annotation'});await first;
  assert.equal(n['manual-result'].children[0],current);
  assert.match(textOf(n['manual-result']),/Current evaluation/);
  assert.doesNotMatch(textOf(n['manual-result']),/Obsolete|stale annotation/);
  // Screenshot confirmation changes the perspective without a select change event.
  const reply=h.holdManual(), pending=n['evaluate'].listeners.click();
  await h.run("upload({type:'image/png',size:100})");
  n['ocr-ack'].checked=true;await n['ocr-confirm'].listeners.click();
  reply.resolve();await pending;
  assert.equal(n['manual-result'].children.length,0);
}
(async()=>{
  const provenance = await harness(false), pn = provenance.nodes;
  await pn.scan.listeners.click();
  assert.match(textOf(pn.cards), /Doubtful\/Out\/IR-filtered free-agent sensitivity/);
  assert.match(textOf(pn.cards), /\+4\.00/);
  assert.match(textOf(pn.cards), /Synthetic FA <unsafe>.*OUT/);
  assert.match(textOf(pn.cards), /zero baseline disclosed/);
  assert.match(textOf(pn.cards), /DOUBTFUL=1, OUT=1, IR=1/);
  assert.match(textOf(pn.cards), /no verified ROS field/);
  selectManual(pn); await pn.evaluate.listeners.click();
  assert.match(textOf(pn['manual-result']), /Doubtful\/Out\/IR-filtered free-agent sensitivity/);
  assert.match(textOf(pn['manual-result']), /Synthetic FA <unsafe>.*OUT/);
  provenance.emptyScan(); await pn.scan.listeners.click();
  assert.match(textOf(pn['season-provenance']), /Synthetic FA <unsafe>.*OUT/);
  assert.match(textOf(pn['season-provenance']), /zero baseline disclosed/);
  assert.match(textOf(pn['season-provenance']), /no verified ROS field/);
  console.log('PASS season provenance: selected FA/status, counts, zero fallback, separate Doubtful/Out/IR-filtered sensitivity, ROS disclosure, manual and empty scans');
  await testManualRaces();
  for (const [available, enabled] of [[false,false],[false,true],[true,true]]) {
    const h = await harness(available, enabled), n=h.nodes;
    for (const id of ['llm-rank','llm-summary']) { assert.equal(n[id].checked,available);assert.equal(n[id].disabled,!available); }
    assert.deepEqual(h.calls.map(c=>c.url),['/api/league','/health']);
    await h.run("upload({type:'image/png',size:100})");
    assert.equal(n['ocr-team'].value,'harbor');
    assert.equal(n['ocr-ack'].checked,false);
    assert.equal(n['ocr-matches'].children.length,league.teams[0].players.length);
    assert.equal(n['ocr-count'].textContent, '12 players');
    assert.match(textOf(n['ocr-matches']),/not detected/);
    await assert.rejects(h.run('confirmRoster()'),/explicitly confirm/);
    assert.equal(h.calls.filter(c=>c.url === '/api/candidates').length,0);
    n['llm-rank'].checked=false; // Per-scan opt-out survives roster confirmation.
    await n['llm-rank'].listeners.change();
    assert.equal(h.calls.filter(c=>c.url === '/api/candidates').length,0);
    n['ocr-ack'].checked=true;
    await n['ocr-confirm'].listeners.click();
    const scan = h.calls.find(c=>c.url === '/api/candidates');
    assert.equal(scan.data.team_id,'harbor');assert.equal(scan.data.source,'ocr');assert.equal(scan.data.confirmed,true);
    assert.deepEqual(scan.data.roster_ids,league.teams[0].players.map(p=>p.id));assert.equal(scan.data.use_llm,false);
    assert.equal(h.calls.filter(c=>c.url === '/api/evaluate').length,0);
    assert.equal(n['cards'].children[0].className,'card');
    assert.match(textOf(n['cards'].children[0].children[0]),/AI summary: Season gains/);
    assert.match(n['search-note'].textContent,/5 opposing teams/);
    assert.match(n['search-note'].textContent,/Data gaps: Synthetic coverage gap/);
    assert.equal(n['ocr-dialog'].open,false);assert.equal(n['ocr-text'].value,'');assert.equal(n['ocr-ack'].checked,false);
    assert.equal(n['cards'].scrolled,true);
    // Manual trade selection stays independent of screenshot confirmation.
    n['give-options'].children[1].children[0].checked=true;
    n['receive-options'].children[4].children[0].checked=true;
    n['llm-summary'].checked=available;
    await n['evaluate'].listeners.click();
    const manual = h.calls.find(c=>c.url === '/api/evaluate');
    assert.equal(manual.data.source,'manual');assert.equal(manual.data.use_llm,available);
    assert.equal(n['manual-result'].children[0].className,'card');
  }
  const h = await harness(true), n=h.nodes;
  h.setOcr({text:'Mixed screenshot',suggestions:[{matches:[{player_id:'harbor-2',confidence:1}]},{matches:[{player_id:'orbit-5',confidence:1}]}]});
  await h.run("upload({type:'image/png',size:100})");
  assert.equal(n['ocr-team'].value,'');
  n['ocr-team'].value='orbit';await n['ocr-team'].listeners.change();
  assert.equal(n['ocr-ack'].checked,false);
  n['ocr-ack'].checked=true;
  n['ocr-team'].value='harbor';await n['ocr-team'].listeners.change();
  assert.equal(n['ocr-ack'].checked,false); // Changing a guess revokes acknowledgement.
  n['ocr-ack'].checked=true;
  await n['ocr-confirm'].listeners.click();
  assert.equal(h.calls.find(c=>c.url === '/api/candidates').data.use_llm,true);
  h.setOcr({text:'',suggestions:[]});
  await h.run("upload({type:'image/png',size:100})");
  assert.equal(n['ocr-team'].value,'');
  await n['ocr-clear'].listeners.click();
  assert.equal(n['ocr-text'].value,'');assert.equal(n['ocr-matches'].children.length,0);
  assert.equal(n['ocr-count'].textContent,'');assert.equal(n['ocr-reference'].open,false);
  assert.equal(h.calls.filter(c=>c.url === '/api/candidates').length,1);
  const accessToken = 'a'.repeat(43);
  const authenticated = await harness(false, false, '', {nonce:'synthetic-page-nonce',required:true});
  assert.deepEqual(authenticated.replacements, []);
  const bootstrap = authenticated.calls[0];
  assert.equal(bootstrap.url,'/api/local-bootstrap');
  assert.deepEqual(bootstrap.headers, {'X-Trade-Room-Bootstrap':'synthetic-page-nonce'});
  for (const [name,value] of Object.entries({mode:'same-origin',credentials:'omit',cache:'no-store',referrerPolicy:'no-referrer',redirect:'error'})) {
    assert.equal(bootstrap.options[name],value);
  }
  for (const call of authenticated.calls.slice(1)) {
    assert.equal(call.headers.Authorization, 'Bearer ' + accessToken);
    assert.equal(call.hash, '');
    assert.ok(!call.url.includes(accessToken));
    assert.ok(!JSON.stringify(call.data || {}).includes(accessToken));
  }
  assert.equal(authenticated.nodes.auth.hidden,true);
  const reloaded = await harness(false, false, '', {required:true});
  assert.ok(reloaded.calls.every(c=>!c.headers.Authorization)); // No persistent browser storage.
  assert.equal(reloaded.nodes.auth.hidden,false);
  assert.equal(reloaded.nodes.app.hidden,true);
  assert.ok(reloaded.calls.every(c=>c.url !== '/api/local-bootstrap'));
  reloaded.nodes.token.value=accessToken;
  await reloaded.nodes['auth-form'].listeners.submit({preventDefault(){}});
  assert.equal(reloaded.nodes.token.value,'');
  assert.equal(reloaded.nodes.auth.hidden,true);
  assert.equal(reloaded.nodes.app.hidden,false);
  assert.equal(reloaded.calls.findLast(c=>c.url === '/api/league').headers.Authorization,'Bearer ' + accessToken);
  for (const failure of [{fail:true},{networkError:true},{invalidToken:true}]) {
    const fallback=await harness(false,false,'',{nonce:'synthetic-page-nonce',required:true,...failure});
    assert.equal(fallback.nodes.auth.hidden,false);
    assert.equal(fallback.nodes.app.hidden,true);
    assert.ok(fallback.calls.every(c=>!c.headers.Authorization));
  }
  for (const fragment of ['#access_token=' + accessToken, '#access_token=short', '#access_token=' + accessToken + '&extra=1', '#access_token']) {
    const invalid = await harness(false, false, fragment, {required:true});
    assert.deepEqual(invalid.replacements, ['/']);
    assert.ok(invalid.calls.every(c=>!c.headers.Authorization && c.hash === ''));
  }
  const anchored = await harness(false, false, '#workbench');
  assert.deepEqual(anchored.replacements, []);
  assert.ok(anchored.calls.every(c=>!c.headers.Authorization));
  console.log('PASS browser authentication: Compose same-origin nonce bootstrap; manual password form; bootstrap failure fallback; bearer header only; no persistence; legacy auth fragments cleared and ignored');
  console.log('PASS UI workflow: own-roster confirmation → full-league cards; manual evaluation separate; detection correction/discard; provider-gated defaults and opt-out');
  console.log('PASS manual response races: team/player/AI changes and reversal, late errors, newest request wins, OCR perspective reset');
})().catch(error=>{console.error(error);process.exitCode=1;});
