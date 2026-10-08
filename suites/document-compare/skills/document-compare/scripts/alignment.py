"""Monotonic layout alignment. Similarity is used for alignment, never semantic truth."""
import bisect
import copy
import difflib
import re
import unicodedata
from collections import Counter
from input_adapter import digest, validate_document

def normalized(s):return re.sub(r'\s+','',unicodedata.normalize('NFKC',s).casefold())

def character_ops(a,b):
    if a==b:return [{'op':'equal','leftStart':0,'leftEnd':len(a),'rightStart':0,'rightEnd':len(b)}]
    # First isolate the unchanged prefix/suffix. Huge changed regions are refined by lines,
    # never silently labelled identical and never truncate source strings.
    if max(len(a),len(b))<=20000:
        return [{'op':tag,'leftStart':i,'leftEnd':j,'rightStart':k,'rightEnd':l} for tag,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes()]
    left=a.splitlines(keepends=True);right=b.splitlines(keepends=True)
    if len(left)<2:left=[a[i:i+4000] for i in range(0,len(a),4000)]
    if len(right)<2:right=[b[i:i+4000] for i in range(0,len(b),4000)]
    la=[0];rb=[0]
    for s in left:la.append(la[-1]+len(s))
    for s in right:rb.append(rb[-1]+len(s))
    result=[]
    for tag,i,j,k,l in difflib.SequenceMatcher(None,left,right,autojunk=False).get_opcodes():
        x,y=''.join(left[i:j]),''.join(right[k:l]);lo,ro=la[i],rb[k]
        if tag=='equal' or max(len(x),len(y))>20000:
            result.append({'op':tag,'leftStart':lo,'leftEnd':la[j],'rightStart':ro,'rightEnd':rb[l]})
        else:
            for op in character_ops(x,y):
                result.append({'op':op['op'],'leftStart':op['leftStart']+lo,'leftEnd':op['leftEnd']+lo,'rightStart':op['rightStart']+ro,'rightEnd':op['rightEnd']+ro})
    return result

def _similarity(a,b):
    if a==b:return 1.0
    if not a or not b:return 0.0
    if max(len(a),len(b))>1600:
        a=a[:800]+a[-800:];b=b[:800]+b[-800:]
    return difflib.SequenceMatcher(None,a,b,autojunk=False).ratio()

def _anchors(left,right):
    lc,rc=Counter(left),Counter(right);positions={v:i for i,v in enumerate(right) if v and rc[v]==1}
    pairs=[(i,positions[v]) for i,v in enumerate(left) if v and lc[v]==1 and v in positions]
    tails=[];indices=[];parents=[]
    for k,(_,j) in enumerate(pairs):
        p=bisect.bisect_left(tails,j);parents.append(indices[p-1] if p else -1)
        if p==len(tails):tails.append(j);indices.append(k)
        else:tails[p]=j;indices[p]=k
    out=[];k=indices[-1] if indices else -1
    while k!=-1:out.append(pairs[k]);k=parents[k]
    return out[::-1]

def _gap(left,right,lo,ro,max_cells):
    n,m=len(left),len(right)
    if not n:return [([],list(range(ro,ro+m)),True)] if m else []
    if not m:return [(list(range(lo,lo+n)),[],True)]
    if n*m>max_cells:
        # Preserve the unresolved window explicitly, rather than invent cross-window matches.
        return [(list(range(lo,lo+n)),list(range(ro,ro+m)),False)]
    costs=[[float('inf')]*(m+1) for _ in range(n+1)];costs[0][0]=0;prev={}
    for i in range(n+1):
        for j in range(m+1):
            score=costs[i][j]
            options=[]
            if i<n:options.append((1,0,1.0,True))
            if j<m:options.append((0,1,1.0,True))
            for di,dj in ((1,1),(1,2),(2,1),(1,3),(3,1)):
                if i+di>n or j+dj>m:continue
                r=_similarity(''.join(left[i:i+di]),''.join(right[j:j+dj]))
                if di+dj>2 and r<.8:continue
                options.append((di,dj,(1-r)*1.8+.2*(di+dj-2),r>=.32))
            for di,dj,delta,certain in options:
                value=score+delta
                if value<costs[i+di][j+dj]:
                    costs[i+di][j+dj]=value;prev[i+di,j+dj]=(i,j,certain)
    result=[];i,j=n,m
    while i or j:
        pi,pj,certain=prev[i,j];result.append((list(range(lo+pi,lo+i)),list(range(ro+pj,ro+j)),certain));i,j=pi,pj
    return result[::-1]

def recalculate(result):
    counts=Counter(a['operation'] for a in result['alignments'])
    pending=sum(a['semantic']['status'] in {'pending','uncertain'} for a in result['alignments'])
    unresolved=sum(a['alignmentStatus']=='unresolved' for a in result['alignments'])
    result['summary']={k:counts[k] for k in ('equal','insert','delete','replace')}
    result['summary'].update(pending=pending,unresolved=unresolved)
    result['status']='needs_review' if pending or unresolved or result.get('nonTextReview') else 'complete'
    result['coverage']={'left':sum(len(a['left']) for a in result['alignments']),'right':sum(len(a['right']) for a in result['alignments'])}
    return result

def align_documents(left,right,mode='character',surface='reading',max_cells=16000,alignment_override=None):
    validate_document(left,0);validate_document(right,1)
    if mode not in {'character','semantic'} or surface not in {'reading','raw'}:raise ValueError('未知校验模式或文本口径')
    documents=copy.deepcopy([left,right]);field='readingText' if surface=='reading' else 'text'
    texts=[[b[field] for b in d['layouts']] for d in documents];norms=[[normalized(s) for s in ss] for ss in texts]
    pairs=[];li=rj=0
    if alignment_override is not None:
        if not isinstance(alignment_override,list):raise ValueError('对齐覆盖必须是数组')
        pairs=[(a['left'],a['right'],True) for a in alignment_override]
    else:
        for i,j in _anchors(*norms)+[(len(norms[0]),len(norms[1]))]:
            pairs.extend(_gap(norms[0][li:i],norms[1][rj:j],li,rj,max_cells))
            if i<len(norms[0]):pairs.append(([i],[j],True))
            li,rj=i+1,j+1
    for side,total in ((0,len(texts[0])),(1,len(texts[1]))):
        flattened=[index for pair in pairs for index in pair[side]]
        if any(isinstance(i,bool) or not isinstance(i,int) for i in flattened) or flattened!=list(range(total)):raise ValueError('对齐必须按阅读顺序完整覆盖两份文档各一次')
    records=[]
    for i,(ls,rs,certain) in enumerate(pairs,1):
        if not ls and not rs:raise ValueError('对齐事项不能两侧均为空')
        a,b='\n'.join(texts[0][j] for j in ls),'\n'.join(texts[1][j] for j in rs)
        op='insert' if not ls else 'delete' if not rs else 'equal' if a==b else 'replace'
        records.append({'id':f'D{i:04}','left':ls,'right':rs,'operation':op,'alignmentStatus':'aligned' if certain else 'unresolved',
            'leftText':a,'rightText':b,'leftRefs':[{'documentIndex':0,'layoutId':left['layouts'][j]['layoutId']} for j in ls],
            'rightRefs':[{'documentIndex':1,'layoutId':right['layouts'][j]['layoutId']} for j in rs],
            'charOps':character_ops(a,b),'semantic':{'status':'not_requested' if mode=='character' else 'equal' if op=='equal' else 'pending','reason':''}})
    identity={'documents':documents,'mode':mode,'surface':surface,'pairs':[(x,y,c) for x,y,c in pairs]}
    warnings=list(dict.fromkeys(left.get('warnings',[])+right.get('warnings',[])))
    if any(not c for _,_,c in pairs):warnings.append('存在未确认对齐窗口，需复核或提交 alignment override；没有丢弃布局')
    if any(d.get('parseRunId') is None for d in documents):warnings.append('解析批次未提供，仅以归档结果摘要绑定当前输入')
    if any(d.get('sourceSha256') is None for d in documents):warnings.append('未提供原件摘要，当前仅校验所给解析结果')
    if any(max(len(r['leftText']),len(r['rightText']))>20000 for r in records):warnings.append('超长差异使用分层字符区间，保留完整文本；不保证编辑区间为最小集合')
    return recalculate({'schemaVersion':'1.0','comparisonId':digest(identity),'mode':mode,'surface':surface,'documents':documents,'alignments':records,
        'warnings':warnings,'nonTextReview':any(b.get('nonTextReview') for d in documents for b in d['layouts']),
        'algorithm':{'name':'reading-order-anchors-dynamic-programming','maxCells':max_cells,'similarityPurpose':'alignment_only'}})
