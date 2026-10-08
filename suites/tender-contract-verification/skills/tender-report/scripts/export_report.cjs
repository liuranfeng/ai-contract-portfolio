/* Local Chrome/Chromium/Edge export; no package dependencies, no uploads. Node 22+. */
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawn}=require('node:child_process'),{pathToFileURL}=require('node:url');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const sha256=b=>crypto.createHash('sha256').update(b).digest('hex');
function parseArgs(argv){
  const a={mode:'report',timeout:600000,pdf:false,screenshots:false};
  for(let i=0;i<argv.length;i++){
    const k=argv[i];if(k==='--pdf'||k==='--screenshots'){a[k.slice(2)]=true;continue}
    if(k==='--help'){a.help=true;return a}
    if(!['--html','--out','--chrome','--mode','--timeout'].includes(k)||!argv[i+1]||argv[i+1].startsWith('--'))throw Error('Unknown option or missing value: '+k);
    a[k.slice(2)]=argv[++i];
  }
  a.timeout=Number(a.timeout);
  if(!a.html||!a.out||(!a.pdf&&!a.screenshots))throw Error('Require --html FILE --out NEW_DIRECTORY and --pdf and/or --screenshots');
  if(!['report','full'].includes(a.mode))throw Error('--mode must be report or full');
  if(!Number.isFinite(a.timeout)||a.timeout<1000||a.timeout>1800000)throw Error('--timeout must be 1000..1800000 milliseconds');
  return a;
}
function validateDestination(source,out){
  if(/^https?:|^file:/i.test(source))throw Error('--html must be a local filesystem path');
  source=path.resolve(source);out=path.resolve(out);
  if(!fs.statSync(source).isFile())throw Error('HTML source is not a file');
  if(fs.existsSync(out))throw Error('Output directory already exists; choose a new destination');
  return {source,out};
}
function browserPath(configured){
  const candidates=[configured,process.env.CHROME_PATH,
    process.env.PROGRAMFILES&&path.join(process.env.PROGRAMFILES,'Google/Chrome/Application/chrome.exe'),
    process.env['PROGRAMFILES(X86)']&&path.join(process.env['PROGRAMFILES(X86)'],'Microsoft/Edge/Application/msedge.exe'),
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/usr/bin/chromium','/usr/bin/chromium-browser','/usr/bin/google-chrome'];
  const found=candidates.find(p=>p&&fs.existsSync(p));if(!found)throw Error('No Chromium browser found; supply --chrome ABSOLUTE_EXECUTABLE');return found;
}
async function exportReport(a){
  const {source,out}=validateDestination(a.html,a.out),chrome=browserPath(a.chrome),input=fs.readFileSync(source);
  if(typeof WebSocket==='undefined')throw Error('Node 22+ with built-in WebSocket is required');
  fs.mkdirSync(out,{recursive:true});const profile=fs.mkdtempSync(path.join(os.tmpdir(),'tender-report-browser-'));
  const manifest={source:path.basename(source),sourceSha256:sha256(input),mode:a.mode,outputs:[],status:'running',checks:{},browserVersion:null};
  const stage=name=>{manifest.stage=name;fs.writeFileSync(path.join(out,'export-manifest.json'),JSON.stringify(manifest,null,2));};
  stage('browser-start');
  const child=spawn(chrome,['--headless=new','--disable-gpu','--no-first-run','--no-proxy-server','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
  let ws,stop,spawnError;child.on('error',e=>spawnError=e);
  const deadline=Date.now()+a.timeout;const pending=new Map();let seq=0;
  const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++seq,{resolve,reject});ws.send(JSON.stringify({id:seq,method,params}))});
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error('Browser evaluation failed: '+JSON.stringify(r.exceptionDetails));return r.result.value};
  const save=(name,bytes)=>{fs.writeFileSync(path.join(out,name),bytes,{flag:'wx'});manifest.outputs.push({file:name,bytes:bytes.length,sha256:sha256(bytes)})};
  try{
    await Promise.race([(async()=>{
      let port;while(Date.now()<deadline){if(spawnError)throw spawnError;try{port=Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0]);if(port)break}catch{}await sleep(200)}
      if(!port)throw Error('Browser startup timed out');
      const version=await(await fetch(`http://127.0.0.1:${port}/json/version`)).json();manifest.browserVersion=version.Browser;
      const tabs=await(await fetch(`http://127.0.0.1:${port}/json`)).json();ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
      await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
      const runtimeErrors=[];ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}if(m.method==='Runtime.exceptionThrown')runtimeErrors.push(m.params)};
      await send('Page.enable');await send('Runtime.enable');
      // Report content is escaped by the suite. Disable network loads, including accidental external resources.
      await send('Network.enable');await send('Network.setBlockedURLs',{urls:['http://*','https://*']});
      // Legacy reports expand every appendix on beforeprint; control the scope explicitly.
      await send('Page.addScriptToEvaluateOnNewDocument',{source:"window.addEventListener('beforeprint',e=>e.stopImmediatePropagation(),true)"});
      await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1450,deviceScaleFactor:1,mobile:false});
      await send('Page.navigate',{url:pathToFileURL(source).href});
      stage('load-report');
      while(Date.now()<deadline){if(await evaluate("document.readyState==='complete'&&!!document.querySelector('.report')"))break;await sleep(150)}
      await evaluate('document.fonts.ready.then(()=>true)');
      manifest.checks=await evaluate("(()=>{const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);const links=[...document.querySelectorAll('a[href^=\"#\"]')].map(a=>a.getAttribute('href').slice(1));return {mainChecks:document.querySelectorAll('.case').length,duplicateIds:ids.length-new Set(ids).size,brokenAnchors:links.filter(x=>x&&!document.getElementById(x)).length,desktopOverflow:document.documentElement.scrollWidth>innerWidth}})()");
      if(manifest.checks.duplicateIds||manifest.checks.brokenAnchors||manifest.checks.desktopOverflow)throw Error('HTML validation failed: '+JSON.stringify(manifest.checks));
      manifest.checks.diffToggle=await evaluate("(()=>{const b=document.getElementById('highlight');if(!b)return null;const before=document.body.classList.contains('no-diff');b.click();const ok=before!==document.body.classList.contains('no-diff');b.click();return ok})()");
      manifest.checks.sourceJump=await evaluate("(()=>{const a=document.querySelector('.case a[href^=\"#src-\"]');if(!a)return null;const id=a.getAttribute('href').slice(1);a.click();return id})()");
      if(manifest.checks.sourceJump){await sleep(100);manifest.checks.sourceJump=await evaluate("(()=>{let e=document.getElementById(location.hash.slice(1));if(!e)return false;while(e){if(e.tagName==='DETAILS'&&!e.open)return false;e=e.parentElement}return true})()");}
      await evaluate("document.querySelectorAll('details').forEach(d=>d.open=false);history.replaceState(null,'',location.pathname);document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,0)");
      if(a.screenshots){
        let shot=await send('Page.captureScreenshot',{format:'png'});save('report-desktop.png',Buffer.from(shot.data,'base64'));
        await evaluate("document.querySelector('.case')?.scrollIntoView()");await sleep(100);shot=await send('Page.captureScreenshot',{format:'png'});save('report-evidence.png',Buffer.from(shot.data,'base64'));
        await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await evaluate('window.scrollTo(0,0)');await sleep(100);
        manifest.checks.mobileOverflow=await evaluate('document.documentElement.scrollWidth>innerWidth');
        if(manifest.checks.mobileOverflow)throw Error('Mobile horizontal overflow');
        shot=await send('Page.captureScreenshot',{format:'png'});save('report-mobile.png',Buffer.from(shot.data,'base64'));
      }
      if(manifest.checks.diffToggle===false||manifest.checks.sourceJump===false||runtimeErrors.length)throw Error('Browser interaction check failed');
      if(a.pdf){
        stage('prepare-print');
        await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1450,deviceScaleFactor:1,mobile:false});
        manifest.printScope=await evaluate(`(()=>{if(typeof window.tenderPreparePrint==='function')return window.tenderPreparePrint(${JSON.stringify(a.mode)});document.querySelectorAll(${JSON.stringify(a.mode==='full'?'details':'.case details, details.contents')}).forEach(d=>d.open=true);return {mode:${JSON.stringify(a.mode)},legacy:true}})()`);
        // Drop only invisible descendants from the in-memory print DOM; original HTML remains unchanged.
        await evaluate("document.querySelectorAll('details:not([open])').forEach(d=>[...d.children].filter(c=>c.tagName!=='SUMMARY').forEach(c=>c.remove()))");
        await evaluate("(()=>{const s=document.createElement('style');s.textContent='@media print{.quote,.context-evidence blockquote{max-height:none!important;overflow:visible!important}.top,.back{display:none!important}.document-flow,.extra-documents{break-inside:auto}.document,.context-evidence{break-inside:auto}.document header,.evidence-title{break-after:avoid}.case .facts th:first-child{width:18%}.case .facts th:nth-child(2){width:auto}}';document.head.append(s)})()");
        stage('print-pdf');
        const pdf=await send('Page.printToPDF',{generateTaggedPDF:false,generateDocumentOutline:false,landscape:true,paperWidth:8.2677,paperHeight:11.6929,marginTop:0.45,marginBottom:0.5,marginLeft:0.45,marginRight:0.45,printBackground:true,displayHeaderFooter:true,headerTemplate:'<span></span>',footerTemplate:'<div style="width:100%;text-align:center;font-size:8px;color:#697c88"><span class="pageNumber"></span> / <span class="totalPages"></span></div>'});
        const bytes=Buffer.from(pdf.data,'base64');if(bytes.subarray(0,5).toString()!=='%PDF-')throw Error('Invalid PDF response');save('report.pdf',bytes);
      }
      manifest.checks.runtimeErrors=runtimeErrors.length;manifest.checks.sourceUnchanged=sha256(fs.readFileSync(source))===manifest.sourceSha256;
      if(!manifest.checks.sourceUnchanged)throw Error('Source changed during export');manifest.status='complete';manifest.stage='complete';
    })(),new Promise((_,reject)=>{stop=setTimeout(()=>reject(Error('Export timeout; partial outputs are not a completed delivery')),a.timeout)})]);
  }catch(e){manifest.status='failed';manifest.error=e.message;throw e}
  finally{clearTimeout(stop);for(const p of pending.values())p.reject(Error('Browser session closed'));pending.clear();if(ws)ws.close();child.kill();fs.writeFileSync(path.join(out,'export-manifest.json'),JSON.stringify(manifest,null,2));}
  return manifest;
}
module.exports={parseArgs,validateDestination,sha256,exportReport};
if(require.main===module){let a;try{a=parseArgs(process.argv.slice(2))}catch(e){console.error(e.message);process.exit(2)}
if(a.help)console.log('node export_report.cjs --html FILE --out NEW_DIRECTORY [--chrome EXECUTABLE] [--pdf] [--screenshots] [--mode report|full] [--timeout MILLISECONDS]');
else exportReport(a).then(r=>console.log(JSON.stringify(r,null,2))).catch(e=>{console.error(e.message);process.exitCode=1});}
