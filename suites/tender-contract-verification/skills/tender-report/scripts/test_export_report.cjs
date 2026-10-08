const test = require('node:test');
const assert = require('node:assert/strict');
const {parseArgs, validateDestination, sha256} = require('./export_report.cjs');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
test('explicit full mode; default report mode; invalid modes and missing paths rejected',()=>{
  assert.equal(parseArgs(['--html','a.html','--out','b','--pdf']).mode,'report');
  assert.equal(parseArgs(['--html','a.html','--out','b','--mode','full','--pdf']).mode,'full');
  assert.throws(()=>parseArgs(['--html','a','--out','b','--mode','everything','--pdf']));
  assert.throws(()=>parseArgs(['--html','a','--pdf']));
  assert.throws(()=>parseArgs(['--html','a','--out','b']));
});
test('cannot overwrite existing output or treat URL as local source',()=>{
  assert.throws(()=>validateDestination('https://example.invalid/report.html','new'));
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'tender-export-test-'));
  const source=path.join(dir,'report.html');fs.writeFileSync(source,'test');
  assert.throws(()=>validateDestination(source,dir));
  assert.equal(validateDestination(source,path.join(dir,'new')).source,source);
});
test('manifest digest is of exact bytes',()=>{
  assert.equal(sha256(Buffer.from('abc')),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
});
