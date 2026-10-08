"""Document-style reports. Render recorded findings/relations, never infer new ones."""
import difflib
import hashlib
import html
import json
from collections import Counter
from pathlib import Path
from document_display import render_document, document_diff

LABELS = {'implemented': '已对应', 'incorporated': '已纳入', 'partial': '部分对应 / 待明确',
          'weakened': '承诺弱化', 'conflict': '事实冲突', 'not_found': '已核查范围内未找到',
          'insufficient_materials': '材料不足', 'not_applicable': '背景 / 不适用', 'pending': '待核验'}
RELATIONS = {'implements': '落实关联', 'responds': '响应关联', 'supplements': '补充关联',
             'conflicts': '冲突关联', 'amends': '变更关联', 'candidate': '候选关联 · 未确认'}
FIELDS = {'subject': '主体', 'action': '行为', 'object': '对象', 'scope': '范围', 'trigger': '触发条件',
          'value': '数值 / 内容', 'unit': '单位', 'operator': '比较符', 'duration': '期限',
          'startEvent': '起算事件', 'exceptions': '例外', 'role': '角色', 'clauseText': '条款文本'}
ROLES = {'tender': '招标文件', 'bid': '投标文件', 'contract': '合同文件', 'attachment': '附件',
         'clarification': '澄清文件', 'amendment': '补遗文件'}
ATTENTION = {'partial', 'weakened', 'conflict', 'not_found', 'insufficient_materials', 'pending'}
EXPECTATION_RESULTS = {'weakened':'已证实低于预期', 'uncertain':'预期落实待确认', 'baseline':'预期基准待澄清',
                       'incorporated':'已纳入', 'met':'已满足', 'other':'其他差异'}
RESULT_STATUSES = {'weakened':{'weakened'}, 'uncertain':{'partial','conflict','not_found','insufficient_materials','pending'},
                   'baseline':{'partial','conflict','insufficient_materials'}, 'incorporated':{'incorporated'},
                   'met':{'implemented'}, 'other':{'not_applicable','partial','conflict','implemented','pending'}}

def validate_report_options(data):
    """Validate optional presentation data; never derive a legal result from text/status."""
    errors=[]; checks=data.get('checks',[])
    known={c.get('checkId') for c in checks if isinstance(c,dict)}
    if 'reportView' in data:
        view=data['reportView']
        if not isinstance(view,dict):errors.append('reportView must be an object')
        else:
            ids=view.get('mainCheckIds')
            if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids):
                errors.append('reportView.mainCheckIds must be a list of check IDs')
            elif len(ids)!=len(set(ids)) or any(x not in known for x in ids):
                errors.append('reportView.mainCheckIds contains duplicates or unknown check IDs')
            for key in ('title','summary','scope'):
                if key in view and (not isinstance(view[key],str) or not view[key].strip()):errors.append('reportView.'+key+' must be nonempty text')
    for c in checks:
        if not isinstance(c,dict) or 'expectationComparison' not in c:continue
        e=c['expectationComparison']; prefix=str(c.get('checkId'))+': expectationComparison'
        if not isinstance(e,dict):errors.append(prefix+' must be an object');continue
        for key in ('expectation','contract','impact','result'):
            if not isinstance(e.get(key),str) or not e[key].strip():errors.append(prefix+'.'+key+' must be nonempty text')
        result=e.get('result')
        if not isinstance(result,str) or result not in EXPECTATION_RESULTS:errors.append(prefix+' has unknown result')
        elif c.get('verification',{}).get('status') not in RESULT_STATUSES[result]:errors.append(prefix+' result contradicts verification.status')
    return errors

def result_label(check):
    e=check.get('expectationComparison')
    return EXPECTATION_RESULTS[e['result']] if e else LABELS[check['verification']['status']]

def esc(value):
    return html.escape(str(value), quote=True)

def refkey(ref):
    return (ref['documentIndex'], type(ref['layoutId']).__name__, ref['layoutId'])

def ident(prefix, value):
    return prefix + hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()

def source_id(ref):
    return ident('src-', refkey(ref))

def check_id(check):
    return ident('check-', check['checkId'])

def is_ledger(check):
    # Explicit existing classification, not an inference from status/count alone.
    return (check.get('checkClass') == 'clause_coverage_or_provenance'
            or check.get('comparisonKind') == 'background_or_procedure')

def text_diff(a, b):
    # Long blocks use line granularity to avoid quadratic character matching.
    long = max(len(a), len(b)) > 6000
    aa, bb = (a.splitlines(keepends=True), b.splitlines(keepends=True)) if long else (a, b)
    left, right = [], []
    for tag, i, j, k, l in difflib.SequenceMatcher(None, aa, bb, autojunk=long).get_opcodes():
        x, y = esc(''.join(aa[i:j])), esc(''.join(bb[k:l]))
        left.append(x if tag == 'equal' else '<mark>' + x + '</mark>')
        right.append(y if tag == 'equal' else '<mark>' + y + '</mark>')
    return ''.join(left), ''.join(right)

def render_report(data, process=False, gate_errors=()):
    option_errors=validate_report_options(data)
    if option_errors:raise ValueError('; '.join(option_errors))
    docs = {d['documentIndex']: d for d in data['documents']}
    blocks = {refkey({'documentIndex': d['documentIndex'], 'layoutId': b['layoutId']}): b
              for d in data['documents'] for b in d['layouts']}
    facts = {f['factId']: f for f in data['facts']}
    view=data.get('reportView',{})
    if 'mainCheckIds' in view:
        by_id={c['checkId']:c for c in data['checks']}
        main=[by_id[cid] for cid in view['mainCheckIds']]
        selected=set(view['mainCheckIds'])
        ledger=[c for c in data['checks'] if c['checkId'] not in selected]
    else:
        main = [c for c in data['checks'] if not is_ledger(c)]
        ledger = [c for c in data['checks'] if is_ledger(c)]
    findings = [c for c in main if (c['expectationComparison']['result'] in {'weakened','uncertain','baseline'} if c.get('expectationComparison') else c['verification']['status'] in ATTENTION)]
    counts = Counter(result_label(c) for c in main)
    unresolved = [x for x in data['coverage'] if x['status'] == 'needs_review']
    title = view.get('title') or '投标承诺与合同事实对照' + ('过程报告' if process else '报告')
    stamp = ('模拟样例 · ' if data.get('synthetic') else '') + ('核验过程报告 · 非正式交付' if process else '已通过交付门控')

    def link(ref):
        return '<a href="#' + source_id(ref) + '">文档 ' + esc(ref['documentIndex']) + ' · ' + esc(ref['layoutId']) + '</a>'

    def links(refs):
        return '；'.join(link(r) for r in refs) or '无'

    def source_meta(ref):
        d, b = docs[ref['documentIndex']], blocks[refkey(ref)]
        page = '来源 P' + str(b['originalPage']) if b.get('originalPage') is not None else '解析页标记 ' + str(b.get('page', '未知'))
        return '<span class="docname">' + esc(d['name']) + '</span>' + link(ref) + ' · ' + esc(page) + '<br>解析批次 ' + esc(d['parseRunId'])

    def fact_quote(f):
        return '\n\n'.join(q['text'] for q in f['quotes'])

    def doc_card(f, quote=None):
        refs = f['primarySources']
        roles = list(dict.fromkeys(ROLES.get(docs[r['documentIndex']]['role'], docs[r['documentIndex']]['role']) for r in refs))
        role_class = 'contract' if any(docs[r['documentIndex']]['role'] in {'contract','attachment'} for r in refs) else ''
        return ('<div class="document ' + role_class + '"><div class="document-head"><strong>' + esc(' / '.join(roles))
                + '</strong><span class="page">事实 ' + esc(f['factId']) + '</span></div><div class="quote">'
                + (quote if quote is not None else render_document(fact_quote(f))) + '</div><div class="source">'
                + '<br><br>'.join(source_meta(q['source']) for q in f['quotes']) + '</div></div>')

    def fields_table(check):
        if check.get('expectationComparison'):
            e=check['expectationComparison']
            return '<div class="table-wrap"><table class="facts expectation-facts"><thead><tr><th>比较维度</th><th>本轮结构化判断（下方可回看原文）</th></tr></thead><tbody>'+''.join('<tr><td>'+label+'</td><td>'+esc(e[key])+'</td></tr>' for key,label in [('expectation','预期依据'),('contract','合同落实'),('impact','差距影响')])+'</tbody></table></div>'
        rows = []
        for fid in check['factIds']:
            f = facts[fid]
            for name, value in f['fields'].items():
                if value is None:
                    continue
                value = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
                rows.append('<tr><td>' + esc(fid) + '</td><td>' + esc(FIELDS.get(name, name)) + '</td><td>' + (render_document(value) if name in {'sourceStatement','clauseText'} else esc(value))
                            + '</td><td>' + links(f['fieldSources'].get(name, [])) + '</td></tr>')
        return '<div class="table-wrap"><table class="facts"><thead><tr><th>事实</th><th>维度</th><th>结构化提取内容</th><th>字段依据</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'

    def detail(check, number, appendix=False):
        v = check['verification']
        content = ['<div class="case-number">' + esc(number) + ' / ' + esc(check['checkId']) + '</div>',
                   '<div class="case-heading"><h2>' + esc(check['title']) + '</h2><span class="tag '
                   + ('good' if v['status'] in {'implemented','incorporated'} else '') + '">' + result_label(check) + '</span></div>',
                   ('<div class="focus-impact"><span>本项重点 · '+result_label(check)+'</span><p>'+esc(check['expectationComparison']['impact'])+'</p></div><details class="reason-detail"><summary>判断依据与待确认原因</summary><p>'+esc(v['reason'])+'</p></details>' if check.get('expectationComparison') and not appendix else '<div class="verdict"><strong>核验发现</strong><p>' + esc(v['reason']) + '</p></div>'),
                   '<p class="detail-caption">本次比较维度：' + esc('、'.join(v['comparedFields']) or '未登记') + '</p>']
        if appendix:
            content.append('<details><summary>逐字段事实及来源（' + str(len(check['factIds'])) + ' 个事实记录）</summary>' + fields_table(check) + '</details>')
        else:
            content.append(fields_table(check))
        used = set()
        for rel in check['relations']:
            a, b = facts[rel['fromFactId']], facts[rel['toFactId']]
            used.update((a['factId'], b['factId']))
            left, right = document_diff(fact_quote(a), fact_quote(b))
            content.append('<div class="evidence-title"><strong>原文证据与事实关系</strong><span>左侧琥珀 / 右侧青绿：字面差异，不是义务增减结论</span></div>')
            content.append('<div class="document-flow">' + doc_card(a, left)
                           + '<div class="connector ' + ('candidate' if rel['type']=='candidate' else '') + '"><span>'
                           + RELATIONS[rel['type']] + '</span></div>' + doc_card(b, right) + '</div>')
            # The stored basis, not the edge type alone, determines what a relation means.
            content.append('<div class="relation-basis"><strong>关联依据：</strong>' + esc(rel['basis']) + '</div>')
        remaining = [facts[fid] for fid in check['factIds'] if fid not in used]
        if remaining:
            content.append('<div class="evidence-title"><strong>' + ('其他事项事实' if used else '本事项原文证据') + '</strong><span>未登记成对关系的事实不自动连线</span></div>')
            content.append('<div class="extra-documents">' + ''.join(doc_card(f) for f in remaining) + '</div>')
        contexts = {}
        for fid in check['factIds']:
            for ref in facts[fid]['contextSources']:
                contexts.setdefault(refkey(ref), {'ref':ref,'facts':[]})['facts'].append(fid)
        if contexts:
            content.append('<div class="context-branch"></div><div class="context-list"><div class="context-label">关联上下文 · 虚线表示事实所引用的上下文，不自动认定为合同纳入</div>')
            for item in contexts.values():
                ref = item['ref']
                content.append('<details class="context-evidence"><summary>' + esc('上下文 → '+', '.join(item['facts'])) + ' · ' + esc(ref['layoutId'])
                               + '</summary><blockquote>' + render_document(blocks[refkey(ref)]['text']) + '</blockquote><div class="small-source">'
                               + source_meta(ref) + '</div></details>')
            content.append('</div>')
        content.append('<div class="review-note"><strong>复核说明</strong><p>' + esc(v.get('reviewNote','') or '尚未登记')
                       + '</p><details><summary>已实质核查的来源</summary>' + links(v['reviewedSources']) + '</details></div>')
        if v['missingMaterials']:
            content.append('<div class="coverage">本事项缺件：' + esc('；'.join(v['missingMaterials'])) + '</div>')
        if v.get('suggestion'):
            content.append('<div class="verdict"><strong>独立建议</strong><p>' + esc(v['suggestion']) + '</p></div>')
        content.append('<a class="back" href="#findings">↑ 返回发现概览</a>')
        body = ''.join(content)
        if appendix:
            return '<details class="ledger-entry" id="' + check_id(check) + '"><summary>' + esc(check['checkId']+' · '+check['title']) + ' <span class="tag">' + result_label(check) + '</span></summary>' + body + '</details>'
        return '<section class="case" id="' + check_id(check) + '">' + body + '</section>'

    cards = ''.join('<a class="finding" href="#' + check_id(c) + '"><div class="finding-top"><span>' + esc(c['checkId'])
                    + '</span><span class="tag">' + result_label(c) + '</span></div><h3>' + esc(c['title'])
                    + '</h3>' + ('<p class="finding-impact">'+esc(c['expectationComparison']['impact'])+'</p><div class="finding-comparison"><div><span>投标 / 预期</span><p>'+esc(c['expectationComparison']['expectation'])+'</p></div><div><span>合同落实</span><p>'+esc(c['expectationComparison']['contract'])+'</p></div></div>' if c.get('expectationComparison') else '<p>'+esc(c['verification']['reason'])+'</p>') + '<div class="goto">核对差距与原文 →</div></a>' for c in findings)
    if not findings:
        cards = '<p>当前主要核验事项中没有登记差异或待确认状态；请结合材料范围阅读。</p>'
    status_summary = '；'.join(s + ' ' + str(n) for s,n in counts.items())
    cover = ('<div class="kicker">EVIDENCE-BASED COMPARISON REPORT</div><h1>' + esc(title) + '</h1><p class="intro">先看发现，再沿原文核对。以核验事项为单位呈现事实、字面差异、关联依据和完整来源。</p>'
             + '<div class="meta"><div><span>项目</span>' + esc(data['projectId']) + '</div><div><span>快照</span>' + esc(data['snapshotId'])
             + '</div><div>' + esc(stamp) + '</div></div><div class="coverage"><b>核验范围</b><br>主要事项 ' + str(len(main))
             + '；条款与背景记录 ' + str(len(ledger)) + '；合计 ' + str(len(data['checks'])) + ' 个登记事项（不等同于独立义务数量）。<br>'
             + esc(status_summary) + '<br>上述状态统计仅计主要事项；附录记录不重复计入发现数量。<br>缺失材料：'
             + esc('；'.join(data['missingMaterials']) or '无登记缺件') + '<br>待复核解析块：' + str(len(unresolved)) + '。</div>')
    if view.get('summary'):cover += '<p class="intro">'+esc(view['summary'])+'</p>'
    if view.get('scope'):cover += '<div class="coverage"><strong>本轮复核边界</strong><br>'+esc(view['scope'])+'</div>'
    if process:
        cover += '<div class="coverage"><strong>过程报告边界</strong><br>保留当前全部已登记事项与原文，不代表 OCR 疑点已解决或项目已全量核验。正式交付门控未被跳过。'
        if gate_errors:
            cover += '<details><summary>正式门控检查结果</summary><ul>' + ''.join('<li>'+esc(e)+'</li>' for e in dict.fromkeys(gate_errors)) + '</ul></details>'
        cover += '</div>'
    lead,metadata=cover.split('<div class="meta">',1)
    cover=lead+'<div class="focus-stats">'+''.join('<div><strong>'+str(count)+'</strong><span>'+esc(label)+'</span></div>' for label,count in counts.items())+'</div><p class="boundary-alert">主要关注 '+str(len(findings))+' 项 · 待复核原文 '+str(len(unresolved))+' 块 · 缺失材料：'+esc('；'.join(data['missingMaterials']) or '无登记缺件')+'</p><details class="report-metadata"><summary>材料范围、历史记录与复核边界</summary><div class="meta">'+metadata+'</details>'
    top = '<section class="section" id="findings"><div class="section-heading"><span class="section-number">01</span><h2>优先关注的合同预期差距</h2></div><p class="section-note">先看差距及影响，再核对承诺与合同。待确认事项不等同于已证实损失。</p><div class="findings">' + cards + '</div></section>'
    contents = '<details class="contents"><summary>全部主要事项目录（' + str(len(main)) + '）</summary><ol>' + ''.join('<li><a href="#'+check_id(c)+'">'+esc(c['checkId']+' '+c['title'])+'</a> · '+result_label(c)+'</li>' for c in main) + '</ol></details>'
    detail_html = '<section class="section"><div class="section-heading"><span class="section-number">02</span><h2>逐事项对照与原文证据链</h2></div><p class="section-note">实线表达已登记关系；候选关系用虚线标明。没有明确关系的数据不自动配对。连线不代表实际履约。</p>' + contents + ''.join(detail(c, '事项 '+str(i+1)) for i,c in enumerate(main)) + '</section>'
    appendix = '<section class="section"><div class="section-heading"><span class="section-number">03</span><h2>条款、背景与待复核附录</h2></div>'
    appendix += '<p class="section-note">保留历史与辅助登记事项；逐条内容可展开。默认打印正文及正文上下文，历史与完整原文附录保持折叠；可选择打印完整附录。</p>' + ''.join(detail(c,'附录 '+str(i+1),True) for i,c in enumerate(ledger))
    appendix += '<h3>待复核解析块</h3>' + (''.join('<div class="coverage">'+links([x['source']])+'<br>'+esc(x['reason'])+'</div>' for x in unresolved) or '<p>无登记待复核块。</p>') + '</section>'
    sources = ['<section class="section"><div class="section-heading"><span class="section-number">04</span><h2>完整解析原文索引</h2></div><p class="section-note">证据链接展开精确原文块；定位键保留类型，不重新编号。原文仅作为文本展示，不加载其中链接或脚本。</p>']
    for d in data['documents']:
        sources.append('<details class="source-document"><summary>文档 '+esc(d['documentIndex'])+' · '+esc(d['name'])+'（'+str(len(d['layouts']))+' 块）</summary>')
        for b in d['layouts']:
            ref={'documentIndex':d['documentIndex'],'layoutId':b['layoutId']}
            sources.append('<details class="source-block" id="'+source_id(ref)+'"><summary>'+esc(b['layoutId'])+'</summary><div class="small-source">'+source_meta(ref)+'</div><div class="source-reading">'+render_document(b['text'])+'</div><details class="raw-evidence"><summary>查看原始解析文本（未改动）</summary><pre>'+esc(b['text'])+'</pre></details></details>')
        sources.append('</details>')
    sources.append('</section>')
    css=(Path(__file__).resolve().parents[2]/'tender-report/assets/report.css').read_text(encoding='utf-8')
    js="""function openTarget(){const el=document.getElementById(location.hash.slice(1));if(!el)return;let p=el;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement}requestAnimationFrame(()=>window.scrollTo({top:el.getBoundingClientRect().top+window.scrollY-20,behavior:'auto'}))}window.addEventListener('hashchange',openTarget);openTarget();document.getElementById('highlight').onclick=function(){const off=document.body.classList.toggle('no-diff');this.textContent='差异高亮：'+(off?'关':'开');this.setAttribute('aria-pressed',String(!off))};let printState=[];
window.tenderPreparePrint=function(mode='report'){
 if(!printState.length)printState=[...document.querySelectorAll('details')].map(d=>[d,d.open]);
 document.querySelectorAll('.print-context-note').forEach(n=>n.remove());
 const full=mode==='full';let duplicateContexts=0;
 printState.forEach(([d])=>{
  d.open=full||Boolean(d.closest('.case'))||d.classList.contains('contents');
  if(d.classList.contains('raw-evidence'))d.open=false;
  if(!full&&d.classList.contains('context-evidence')){
   const section=d.closest('.case'),anchor=d.querySelector('.small-source a[href^="#src-"]');
   const text=d.querySelector('blockquote')?.textContent;
   const covered=section&&anchor&&text&&[...section.querySelectorAll('.document')].some(card=>
    [...card.querySelectorAll('.source a[href^="#src-"]')].some(a=>a.getAttribute('href')===anchor.getAttribute('href'))&&card.querySelector('.quote')?.textContent.includes(text));
   if(covered){d.open=false;duplicateContexts++;const note=document.createElement('span');note.className='print-context-note';note.textContent=' · 原文已在本事项证据卡展示';d.querySelector('summary').append(note)}
  }
 });
 document.body.classList.toggle('print-full',full);
 return {mode:full?'full':'report',duplicateContexts};
};
window.tenderRestorePrint=function(){printState.forEach(([d,open])=>d.open=open);printState=[];document.querySelectorAll('.print-context-note').forEach(n=>n.remove());document.body.classList.remove('print-full')};
window.addEventListener('beforeprint',()=>window.tenderPreparePrint(document.getElementById('print-full').checked?'full':'report'));
window.addEventListener('afterprint',window.tenderRestorePrint);
document.getElementById('print').onclick=()=>window.print();"""
    output='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+css+'</style></head><body><div class="top"><span>事实关系报告 / '+esc(stamp)+'</span><div><button id="highlight" aria-pressed="true">差异高亮：开</button> <label><input type="checkbox" id="print-full">包含完整附录</label> <button id="print">打印 / 存为 PDF</button></div></div><article class="report">'+cover+top+detail_html+appendix+''.join(sources)+'<div class="end">文档索引 + layoutId 定位原文；解析批次由快照绑定。字面 Diff 不替代核验判断。<br>解析文本回溯已提供；PDF 原件坐标高亮需宿主查看器接入。</div></article><script>'+js+'</script></body></html>'
    md=['# '+title,'',stamp,'项目：'+data['projectId'],'快照：'+data['snapshotId'],'缺件：'+'；'.join(data['missingMaterials']), '']
    if view:
        md+=['本轮主要事项：'+json.dumps(view['mainCheckIds'],ensure_ascii=False),
             '本轮摘要：'+view.get('summary',''), '本轮复核边界：'+view.get('scope',''), '主要事项状态：'+status_summary, '']
    for c in data['checks']:
        v=c['verification'];md+=['## '+c['checkId']+' '+c['title'], '状态：'+result_label(c), '结论：'+v['reason'], '复核：'+v.get('reviewNote',''), '缺件：'+'；'.join(v['missingMaterials']), '独立建议：'+v.get('suggestion','')]
        if c.get('expectationComparison'):md+=['预期对照：'+json.dumps(c['expectationComparison'],ensure_ascii=False)]
        for r in c['relations']:md+=['关联：'+json.dumps(r,ensure_ascii=False)]
        for fid in c['factIds']:
            f=facts[fid];md+=['事实 '+fid+'：'+json.dumps(f['fields'],ensure_ascii=False),'逐字段来源：'+json.dumps(f['fieldSources'],ensure_ascii=False),'上下文：'+json.dumps(f['contextSources'],ensure_ascii=False)]
            for q in f['quotes']:md+=['原文证据 '+json.dumps(q['source'],ensure_ascii=False)+'：'+q['text']]
        md+=['']
    md+=['## 待复核解析块',json.dumps(unresolved,ensure_ascii=False,indent=2),'## 完整解析原文']
    for d in data['documents']:
        md+=['### 文档 '+str(d['documentIndex'])+' '+d['name'],'解析批次：'+d['parseRunId']]
        for b in d['layouts']:md+=['layoutId '+str(b['layoutId']),b['text'],'']
    return '\n'.join(md),output
