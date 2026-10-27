// Synthetic-only WebKit integration test. Runs only with all three verification flags.
(async () => {
  const passed = [];
  const assert = (condition, message) => { if (!condition) throw Error(message); };
  const wait = async (condition, label) => {
    const end = Date.now() + 20000;
    while (!condition()) { if (Date.now() > end) throw Error('Timed out: ' + label); await new Promise(r => setTimeout(r, 50)); }
  };
  let sequence = 0;
  const layouts = [];
  const report = (stage, extra = {}) => new Promise((resolve, reject) => {
    const capture = ++sequence;
    const timer = setTimeout(() => reject(Error('Native capture timed out: ' + stage)), 10000);
    window.__verificationComplete = id => { if (id === capture) { clearTimeout(timer); resolve(); } };
    window.webkit.messageHandlers.verification.postMessage({stage, capture, passed:[...passed], ...extra});
  });
  const resize = async (width, height) => {
    await report('resize', {width, height});
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    assert(innerWidth === width && innerHeight >= height - 40 && innerHeight < height, 'Actual native frame/viewport size');
    layouts.push({window:[width,height], viewport:[innerWidth,innerHeight]});
  };
  const visible = selector => {
    const node = document.querySelector(selector), r = node.getBoundingClientRect();
    assert(r.width > 0 && r.height > 0 && r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth, selector + ' fully visible');
    const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    assert(hit === node || node.contains(hit), selector + ' unobscured');
  };
  const frameAt = selector => window.scrollTo({top:document.querySelector(selector).getBoundingClientRect().top + scrollY - 8, behavior:'instant'});
  const checkWelcome = () => {
    const welcome = document.querySelector('#desktop-welcome');
    assert(welcome.open && !document.querySelector('#desktop-dialog').open, 'Separate welcome');
    assert(welcome.scrollHeight <= welcome.clientHeight + 1, 'Welcome fits without scrolling');
    assert(welcome.querySelectorAll('input, select').length === 0, 'No setup form in welcome');
    visible('#desktop-demo'); visible('#desktop-optional');
  };
  const checkRoster = () => {
    const dialog = document.querySelector('#ocr-dialog'), list = document.querySelector('#ocr-matches');
    assert(dialog.scrollHeight <= dialog.clientHeight + 1, 'OCR dialog does not scroll');
    assert(list.scrollHeight > list.clientHeight, 'Roster has its own overflow');
    for (const selector of ['#ocr-count', '#ocr-ack', '#ocr-clear', '#ocr-confirm']) visible(selector);
    assert(document.querySelector('#ocr-count').textContent === '12 players', 'Visible full player count');
    const top = document.querySelector('#ocr-confirm').getBoundingClientRect().top;
    list.scrollTop = list.scrollHeight;
    assert(list.scrollTop > 0, 'Roster scrolls to last player');
    assert(list.lastElementChild.getBoundingClientRect().bottom <= list.getBoundingClientRect().bottom + 1, 'Last player reachable');
    assert(document.querySelector('#ocr-confirm').getBoundingClientRect().top === top, 'Actions stay fixed while roster scrolls');
  };
  try {
    await wait(() => document.querySelector('#desktop-welcome')?.open && !document.querySelector('#app').hidden, 'first-run welcome and authenticated UI');
    assert(league.teams.length === 6 && league.teams[0].id === 'harbor' && league.source.includes('Synthetic'), 'Synthetic fixture required');
    assert(document.querySelector('#desktop-storage').value === 'keychain', 'Keychain default');
    assert(document.querySelector('#llm-rank').disabled && !document.querySelector('#llm-rank').checked, 'AI off');
    assert(!document.querySelector('#desktop-load').disabled === false, 'ESPN load unavailable without settings');
    for (const [width, height] of [[800,600], [1024,768], [1200,850]]) {
      await resize(width, height); checkWelcome();
      await report(`welcome-${width}x${height}`);
    }
    assert(document.activeElement.id === 'desktop-demo', 'Primary demo action focused');
    passed.push('concise separate welcome fits 800x600, 1024x768, 1200x850; focused demo; AI disabled');
    await report('welcome');
    document.querySelector('#desktop-optional').click();
    assert(document.querySelector('#desktop-dialog').open && !document.querySelector('#desktop-welcome').open, 'Optional setup is a separate step');
    for (const [width, height] of [[800,600], [1200,850]]) {
      await resize(width, height);
      document.querySelector('#desktop-dialog').scrollTop = 0;
      await report(`setup-${width}x${height}`);
      document.querySelector('#desktop-load').scrollIntoView({block:'end', behavior:'instant'});
      visible('#desktop-load'); visible('#desktop-forget');
      await report(`setup-actions-${width}x${height}`);
    }
    await report('setup');
    document.querySelector('#desktop-dialog').close();
    document.querySelector('#desktop-welcome').showModal();
    document.querySelector('#desktop-demo').click();
    await wait(() => !document.querySelector('#desktop-welcome').open, 'welcome dismissal');
    await resize(800, 600);
    visible('#desktop-update-menu');
    document.querySelector('#desktop-update-menu').click();
    assert(document.querySelector('#desktop-updates').open, 'Update panel opens explicitly');
    assert(document.querySelector('#desktop-check-updates').disabled === !desktopState.updates.enabled, 'Update check availability matches local configuration');
    assert(document.querySelector('#desktop-open-release').hidden, 'No release link without configuration/check');
    assert(document.querySelector('#desktop-update-status').textContent.includes(desktopState.updates.current_version), 'Current version displayed');
    visible('#desktop-check-updates');
    if (!desktopState.updates.enabled) {
      assert(document.querySelector('#desktop-update-status').textContent.includes('Updates disabled — no release repository'), 'Disabled update reason is explicit');
      assert(document.querySelector('#desktop-check-updates').textContent.includes('unavailable'), 'Disabled update button is unambiguous');
    }
    await report('setup-updates-800x600');
    document.querySelector('#desktop-updates').close();
    await resize(1200, 850);
    passed.push('update panel: current version; check availability matches configuration; no release link or external request');
    document.querySelector('#scan').click();
    await wait(() => document.querySelectorAll('#cards > .card').length === 12, 'trade cards');
    assert(document.querySelector('#checked-count').textContent.replaceAll(',', '') === '2205', '2205 packages');
    assert(document.querySelector('#qualified-count').textContent === '38', '38 qualified');
    document.querySelector('#cards > .card').open = true;
    assert(document.querySelector('.metric-table').textContent.includes('Known coverage'), 'trade details');
    passed.push('league scan: 2205 checked, 38 qualified, 12 rendered cards; expanded details');
    for (const [width, height] of [[800,600], [1024,768], [1200,850]]) {
      await resize(width, height);
      window.scrollTo({top:0, behavior:'instant'});
      assert(document.documentElement.scrollWidth <= document.documentElement.clientWidth, 'Main view has no horizontal clipping');
      await report(`final-main-${width}x${height}`);
      frameAt('#cards');
      await report(`final-expanded-${width}x${height}`);
      frameAt('.details-content');
      const table = document.querySelector('.metric-table').getBoundingClientRect();
      assert(table.left >= 0 && table.right <= innerWidth, 'Analytics table fits viewport');
      await report(`final-details-${width}x${height}`);
    }
    document.querySelector('.lineup-block').open = true;
    frameAt('.lineup-block');
    await report('final-lineups-1200x850');
    document.querySelector('.lineup-block').open = false;
    document.querySelector('#method-open').click();
    await report('setup-model-1200x850');
    document.querySelector('#method-dialog').close();
    const c = candidates[0];
    document.querySelector('#other-team').value = c.other_id;
    document.querySelector('#other-team').dispatchEvent(new Event('change'));
    for (const [name, ids] of [['give',c.give], ['receive',c.receive]]) {
      for (const input of document.querySelectorAll(`input[name="${name}"]`)) {
        input.checked = ids.includes(input.value); input.dispatchEvent(new Event('change'));
      }
    }
    document.querySelector('#evaluate').click();
    await wait(() => document.querySelector('#manual-result .card'), 'manual result');
    passed.push('rendered workbench selections and manual evaluation');
    for (const [width, height] of [[800,600], [1024,768], [1200,850]]) {
      await resize(width, height);
      frameAt('#workbench');
      for (const selector of ['#give-options', '#receive-options']) {
        const list = document.querySelector(selector);
        list.scrollTop = list.scrollHeight;
        assert(list.lastElementChild.getBoundingClientRect().bottom <= list.getBoundingClientRect().bottom + 1, 'Full manual roster is reachable');
        list.scrollTop = 0;
      }
      visible('#evaluate');
      assert(document.documentElement.scrollWidth <= document.documentElement.clientWidth, 'Roster workbench has no horizontal clipping');
      await report(`final-workbench-${width}x${height}`);
    }
    // Check the actual rendered palette and core text contrast, not just CSS source.
    const rgb = value => value.match(/[\d.]+/g).slice(0,3).map(Number);
    const luminance = value => rgb(value).map(c => { c /= 255; return c <= .04045 ? c/12.92 : ((c+.055)/1.055)**2.4; }).reduce((a,c,i) => a+c*[.2126,.7152,.0722][i],0);
    const contrast = (a,b) => (Math.max(luminance(a),luminance(b))+.05)/(Math.min(luminance(a),luminance(b))+.05);
    const root = getComputedStyle(document.documentElement);
    const probe = document.createElement('span'); document.body.append(probe);
    const resolved = name => { probe.style.color = root.getPropertyValue(name); return getComputedStyle(probe).color; };
    for (const foreground of ['--ink','--muted','--ochre']) assert(contrast(resolved(foreground), resolved('--surface')) >= 4.5, foreground + ' legible against white surface');
        assert(root.getPropertyValue('--paper').trim() === '#f6f4ec' && root.getPropertyValue('--green').trim() === '#244c3c', 'Warm paper and forest-green palette is rendered');
        probe.remove();
        passed.push('editorial paper/forest-green palette rendered; ink, muted and ochre text pass 4.5:1 on white; no horizontal clipping');
    const bytes = Uint8Array.from(atob('__SYNTHETIC_PNG__'), c => c.charCodeAt(0));
    await upload(new File([bytes], 'synthetic-roster.png', {type:'image/png'}));
    assert(document.querySelector('#ocr-dialog').open, 'OCR review open');
    assert(document.querySelector('#ocr-text').value.includes('Bennett Vale'), 'Real Vision text');
    assert(document.querySelector('#ocr-team').value === 'harbor', 'Detected synthetic team');
    assert(!document.querySelector('#ocr-ack').checked, 'Explicit roster confirmation');
    assert(document.querySelectorAll('#ocr-matches > div').length === 12, 'Full roster review');
    for (const [width, height] of [[800,600], [1024,768], [1200,850]]) {
      await resize(width, height);
      // Also stress rosters longer than the synthetic fixture without altering engine data.
      const list = document.querySelector('#ocr-matches');
      const rows = [...list.children];
      for (let i = 0; i < 4; i++) rows.forEach(row => list.append(row.cloneNode(true)));
      checkRoster();
      reviewRoster();
      if (height === 600) {
        checkRoster(); await report('ocr-bottom-800x600');
        list.scrollTop = 0; await report('ocr-800x600');
        document.querySelector('#ocr-reference').open = true;
        checkRoster(); await report('ocr-reference-800x600');
        document.querySelector('#ocr-reference').open = false;
      } else {
        // At larger sizes the ordinary roster may fit; stressed overflow was checked above.
        for (const selector of ['#ocr-count', '#ocr-ack', '#ocr-clear', '#ocr-confirm']) visible(selector);
        await report(`ocr-${width}x${height}`);
      }
    }
    passed.push('real Vision OCR; roster scroll, count and actions visible at 800x600/1024x768/1200x850; expanded reference; 60-row stress');
    await report('ocr');
    const previousCandidates = candidates;
    document.querySelector('#ocr-clear').click();
    await wait(() => !document.querySelector('#ocr-dialog').open && document.querySelector('#ocr-text').value === '' && document.querySelector('#ocr-count').textContent === '', 'discard close event clears OCR state');
    assert(candidates === previousCandidates, 'Discard preserves previous scan');
    await upload(new File([bytes], 'synthetic-roster.png', {type:'image/png'}));
    assert(!document.querySelector('#ocr-ack').checked, 'New upload requires fresh acknowledgement');
    passed.push('discard clears OCR without rescanning; reupload requires fresh confirmation');
    document.querySelector('#ocr-ack').checked = true;
    document.querySelector('#ocr-confirm').click();
    await wait(() => !document.querySelector('#ocr-dialog').open, 'confirmed OCR scan');
    assert(document.querySelectorAll('#cards > .card').length === 12, 'OCR scan cards');
    passed.push('confirmed screenshot roster scans league and renders cards');
    document.querySelector('#desktop-setup').click();
    document.querySelector('#desktop-private').checked = false;
    document.querySelector('#desktop-private').dispatchEvent(new Event('change'));
    document.querySelector('#desktop-year').value = '2026';
    document.querySelector('#desktop-league').value = '123456';
    document.querySelector('#desktop-storage').value = 'file';
    document.querySelector('#desktop-settings').requestSubmit();
    await wait(() => document.querySelector('#desktop-message').textContent.startsWith('Saved locally.'), 'local settings save');
    assert(document.querySelector('#desktop-league').value === '', 'Saved league field cleared');
    assert((await api('/health')).source === 'synthetic', 'Save never selects ESPN');
    await api('/api/desktop', {action:'forget'});
    renderDesktop(await api('/api/desktop'));
    assert(!desktopState.configured, 'Forgot settings');
    document.querySelector('#desktop-dialog').close();
    passed.push('setup form saves without ESPN, clears fields; forget removes saved configuration');
    document.querySelector('#cards > .card').open = true;
    document.querySelector('#cards').scrollIntoView({block:'start'});
    await report('final', {ok:true, layouts, cards:12, ocr:'Bennett Vale / Cameron Vale', llm:false});
  } catch (error) { await report('final', {ok:false, error:String(error)}); }
})();
