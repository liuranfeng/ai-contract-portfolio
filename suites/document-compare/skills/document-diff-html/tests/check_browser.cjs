/* Isolated offline Chromium smoke test; no packages, user-profile access or uploads. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {pathToFileURL} = require('node:url');
const assert = require('node:assert/strict');

async function main() {
  const [sourceArg, outArg, configuredBrowser, captureOnly] = process.argv.slice(2);
  if (!sourceArg || !outArg) throw Error('Usage: node check_browser.cjs comparison.html OUTPUT_DIRECTORY [CHROME_EXECUTABLE]');
  const source = path.resolve(sourceArg), out = path.resolve(outArg);
  const chrome = [configuredBrowser, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(p => p && fs.existsSync(p));
  if (!chrome) throw Error('Supply a Chromium executable');
  fs.mkdirSync(out, {recursive: true});
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'document-compare-test-'));
  const child = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'], {windowsHide: true, stdio: 'ignore'});
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const checks = {source, browser: null, status: 'running', checks: {}, runtimeErrors: [], consoleWarnings: []};
  const stage = name => {checks.stage = name; fs.writeFileSync(path.join(out, 'browser-checks.json'), JSON.stringify(checks, null, 2));};
  stage('browser-start');
  let socket, sequence = 0, timeout;
  const pending = new Map();
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    pending.set(++sequence, {resolve, reject});
    socket.send(JSON.stringify({id: sequence, method, params}));
  });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
    if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  try {
    await Promise.race([(async () => {
      let port;
      for (let i = 0; i < 100; i++) {
        try { port = Number(fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]); } catch {}
        if (port) break;
        await pause(150);
      }
      if (!port) throw Error('Browser startup timed out');
      stage('connect-debugger');
      const tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
      socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
      await new Promise((resolve, reject) => {socket.onopen = resolve; socket.onerror = reject;});
      socket.onmessage = event => {
        const message = JSON.parse(event.data);
        if (message.id && pending.has(message.id)) {
          const task = pending.get(message.id);
          pending.delete(message.id);
          message.error ? task.reject(Error(JSON.stringify(message.error))) : task.resolve(message.result);
        }
        if (message.method === 'Runtime.exceptionThrown') checks.runtimeErrors.push(message.params);
        if (message.method === 'Log.entryAdded' && ['warning', 'error'].includes(message.params.entry.level)) checks.consoleWarnings.push(message.params.entry);
      };
      checks.browser = (await send('Browser.getVersion')).product;
      stage('enable-page');
      await send('Page.enable');
      stage('enable-runtime');
      await send('Runtime.enable');
      stage('enable-log');
      await send('Log.enable');
      stage('enable-network');
      await send('Network.enable');
      await send('Network.setBlockedURLs', {urls: ['http://*', 'https://*']});
      await send('Emulation.setDeviceMetricsOverride', {width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false});
      await send('Page.navigate', {url: pathToFileURL(source).href});
      stage('load-comparison');
      for (let i = 0; i < 100; i++) {
        if (await evaluate("document.readyState === 'complete' && !!document.querySelector('.diff-entry')")) break;
        await pause(100);
      }
      await pause(100);
      stage('check-interactions');
      checks.checks.desktop = await evaluate("(() => {const ids = Array.from(document.querySelectorAll('[id]')).map(e=>e.id);return {duplicateIds: ids.length-new Set(ids).size, documentOverflow: document.documentElement.scrollWidth>innerWidth, tables: document.querySelectorAll('.document-content table').length, panes: document.querySelectorAll('.document-scroll').length, entries: document.querySelectorAll('.diff-entry').length};})()");
      assert.equal(checks.checks.desktop.duplicateIds, 0);
      assert.equal(checks.checks.desktop.documentOverflow, false);
      assert.equal(checks.checks.desktop.panes, 2);
      assert.ok(checks.checks.desktop.tables > 0);
      if (captureOnly === 'capture') {
        checks.checks.pairedJumps = await evaluate("(() => {const rows=JSON.parse(document.getElementById('comparison-data').textContent);return ['insert','delete'].map(operation=>{const index=rows.findIndex(row=>row.operation===operation);if(index<0)return {operation,present:false};document.querySelector('[data-select=\"'+index+'\"]').click();const left=document.getElementById('a'+index+'-left'),right=document.getElementById('a'+index+'-right');return {operation,present:true,bothActive:left.classList.contains('active')&&right.classList.contains('active'),placeholder:document.getElementById('a'+index+'-'+(operation==='insert'?'left':'right')).classList.contains('placeholder')};});})()");
        assert.ok(checks.checks.pairedJumps.every(check=>!check.present || check.bothActive && check.placeholder));
        await evaluate("(() => {const block=Array.from(document.querySelectorAll('.pane-0 .alignment')).find(e=>e.querySelector('table')&&e.classList.contains('operation-replace'));const button=block&&document.querySelector('[data-select=\"'+block.dataset.alignment+'\"]');if(button)button.click();else document.querySelector('.diff-select')?.click();})()");
        await pause(100);
        const preview = await send('Page.captureScreenshot', {format: 'png'});
        fs.writeFileSync(path.join(out, 'preview.png'), Buffer.from(preview.data, 'base64'));
        assert.equal(checks.runtimeErrors.length, 0);
        assert.equal(checks.consoleWarnings.length, 0);
        checks.status = 'complete';
        return;
      }
      await evaluate("document.querySelector('[data-select=\"2\"]').click()");
      await pause(80);
      checks.checks.locate = await evaluate("(() => {const blocks=['left','right'].map(s=>document.getElementById('a2-'+s));return {active: blocks.every(b=>b.classList.contains('active')), scroll: [0,1].map(i=>document.getElementById('scroll-'+i).scrollTop), connections: document.querySelectorAll('.connection.active').length, current: document.querySelectorAll('[aria-current=true]').length};})()");
      assert.equal(checks.checks.locate.active, true);
      assert.ok(checks.checks.locate.scroll.every(top => top > 0));
      assert.equal(checks.checks.locate.connections, 1);
      assert.equal(checks.checks.locate.current, 1);
      let screenshot = await send('Page.captureScreenshot', {format: 'png'});
      fs.writeFileSync(path.join(out, 'comparison-desktop.png'), Buffer.from(screenshot.data, 'base64'));
      const before = await evaluate("document.querySelector('.connection.active').getAttribute('d')");
      const rightScrollBefore = await evaluate("document.getElementById('scroll-1').scrollTop");
      await evaluate("document.getElementById('scroll-0').scrollTop += 41");
      await pause(80);
      checks.checks.independentScroll = (await evaluate("document.getElementById('scroll-1').scrollTop")) === rightScrollBefore;
      checks.checks.lineUpdated = before !== await evaluate("document.querySelector('.connection.active').getAttribute('d')");
      assert.equal(checks.checks.independentScroll, true);
      assert.equal(checks.checks.lineUpdated, true);
      await evaluate("document.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',altKey:true,bubbles:true}))");
      checks.checks.keyboardNext = await evaluate("document.querySelector('[aria-current=true]').dataset.select === '3'");
      assert.equal(checks.checks.keyboardNext, true);
      checks.checks.placeholder = await evaluate("document.getElementById('a3-left').classList.contains('placeholder') && document.getElementById('a3-right').classList.contains('active')");
      assert.equal(checks.checks.placeholder, true);
      await evaluate("document.querySelector('[data-select=\"4\"]').click()");
      checks.checks.deletePlaceholder = await evaluate("document.getElementById('a4-right').classList.contains('placeholder') && document.getElementById('a4-left').classList.contains('active') && document.getElementById('a4-right').classList.contains('active')");
      assert.equal(checks.checks.deletePlaceholder, true);
      await evaluate("document.getElementById('diff-filter').value='equivalent';document.getElementById('diff-filter').dispatchEvent(new Event('change'))");
      checks.checks.semanticFilter = await evaluate("Array.from(document.querySelectorAll('.diff-entry')).filter(e=>!e.hidden).length===1 && document.querySelector('[aria-current=true]').dataset.select==='5' && document.querySelectorAll('.alignment').length===16");
      assert.equal(checks.checks.semanticFilter, true);
      await evaluate("document.getElementById('diff-filter').value='all';document.getElementById('diff-filter').dispatchEvent(new Event('change'));document.querySelector('[data-select=\"6\"]').click();document.getElementById('a6-right').querySelector('.char-panel').open=true");
      checks.checks.unicode = await evaluate("document.getElementById('a6-right').querySelector('.char-panel mark').textContent==='乙' && document.querySelector('[data-preview=\"6\"]').textContent.includes('🧪 𠀀')");
      assert.equal(checks.checks.unicode, true);
      await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
      await pause(100);
      checks.checks.narrowScreenFullColumns = await evaluate("document.querySelector('.comparison').scrollWidth >= 1040 && document.querySelector('.diff-pane').getBoundingClientRect().width >= 280");
      assert.equal(checks.checks.narrowScreenFullColumns, true);
      screenshot = await send('Page.captureScreenshot', {format: 'png'});
      fs.writeFileSync(path.join(out, 'comparison-narrow.png'), Buffer.from(screenshot.data, 'base64'));
      assert.equal(checks.runtimeErrors.length, 0);
      assert.equal(checks.consoleWarnings.length, 0);
      checks.status = 'complete';
    })(), new Promise((_, reject) => {timeout = setTimeout(() => reject(Error('Browser checks timed out')), 120000);})]);
  } catch (error) {
    checks.status = 'failed'; checks.error = error.message;
    throw error;
  } finally {
    clearTimeout(timeout);
    fs.writeFileSync(path.join(out, 'browser-checks.json'), JSON.stringify(checks, null, 2));
    if (socket) socket.close();
    child.kill();
  }
  console.log(JSON.stringify(checks, null, 2));
}
main().catch(error => {console.error(error.message); process.exitCode = 1;});
