"""Append explicitly supplied reviewed facts/checks to a new immutable snapshot. No inference."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import evidence

def append_review(original, patch):
    errors=evidence.validate(original)
    if errors:raise ValueError('; '.join(errors))
    if not isinstance(patch.get('snapshotId'),str) or not patch['snapshotId'].strip() or patch['snapshotId']==original['snapshotId']:
        raise ValueError('A distinct nonempty snapshotId is required')
    if not isinstance(patch.get('scope'),str) or not patch['scope'].strip():raise ValueError('Explicit fresh-review scope required')
    newchecks=copy.deepcopy(patch.get('checks'));newfacts=copy.deepcopy(patch.get('facts',[]))
    if not isinstance(newchecks,list) or not newchecks or not isinstance(newfacts,list):raise ValueError('Require checks and facts arrays')
    oldchecks={c['checkId'] for c in original['checks']};oldfacts={f['factId'] for f in original['facts']}
    ids=[c['checkId'] for c in newchecks]; fids=[f['factId'] for f in newfacts]
    if len(ids)!=len(set(ids)) or oldchecks.intersection(ids):raise ValueError('New check IDs must be unique and unused')
    if len(fids)!=len(set(fids)) or oldfacts.intersection(fids):raise ValueError('New fact IDs must be unique and unused')
    for check in newchecks:
        prior=check.get('priorCheckIds',[])
        if not isinstance(prior,list) or any(not isinstance(x,str) or x not in oldchecks for x in prior) or len(prior)!=len(set(prior)):
            raise ValueError('priorCheckIds must identify distinct existing historical checks')
    data=copy.deepcopy(original);data['snapshotId']=patch['snapshotId'];data['checks']=newchecks+data['checks'];data['facts'].extend(newfacts)
    data['reportView']={'mainCheckIds':ids,'scope':patch['scope']}
    for field in ('title','summary'):
        if field in patch:data['reportView'][field]=patch[field]
    refs={evidence.key(r) for c in newchecks for r in c['verification']['reviewedSources']}
    data['reviewRun']={'previousSnapshotId':original['snapshotId'],'methodVersion':patch.get('methodVersion','1.2.0'),
        'scope':patch['scope'],'newGroupedChecks':len(newchecks),'declaredRereadUniqueBlocks':len(refs),
        'preservedPriorChecks':len(oldchecks),'scopeCaution':'Counts reflect declared reread evidence; structural validation does not prove semantic review.'}
    bridge=[{'priorCheckId':c['checkId'],'reviewCheckIds':[n['checkId'] for n in newchecks if c['checkId'] in n.get('priorCheckIds',[])],
             'disposition':'Historical record preserved; linking a topic does not certify every old finding was freshly audited.'} for c in original['checks']]
    errors=evidence.validate(data)
    if errors:raise ValueError('; '.join(errors))
    return data,bridge

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('previous');p.add_argument('review_patch');p.add_argument('output_directory');a=p.parse_args()
    original=Path(a.previous).read_bytes();patch=Path(a.review_patch).read_bytes()
    data,bridge=append_review(json.loads(original.decode('utf-8-sig')),json.loads(patch.decode('utf-8-sig')))
    data['reviewRun']['inputSha256']=hashlib.sha256(original).hexdigest()
    out=Path(a.output_directory);out.mkdir(parents=True,exist_ok=False)
    for name,obj in [('snapshot.json',data),('prior-review-bridge.json',bridge),('review-manifest.json',{
        'inputSha256':hashlib.sha256(original).hexdigest(),'patchSha256':hashlib.sha256(patch).hexdigest(),
        'baseValidation':'passed','formalGateErrors':evidence.validate(data,final=True),
        'reviewRun':data['reviewRun']})]:
        with (out/name).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2)
    print(out.resolve())

if __name__=='__main__':main()
