"""Offline orchestration for parser-result comparison and independently selectable outputs."""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from alignment import align_documents, recalculate, character_ops
from input_adapter import import_document, validate_document, digest
from semantics import semantic_requests, apply_decisions

PLUGIN=Path(__file__).resolve().parents[3]

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)

def validate_result(result):
    if result.get('schemaVersion')!='1.0':raise ValueError('不支持的比对 schemaVersion')
    docs=result.get('documents',[])
    if len(docs)!=2:raise ValueError('比对必须恰好包含两份文档')
    for i,d in enumerate(docs):validate_document(d,i)
    if result.get('mode') not in {'character','semantic'} or result.get('surface') not in {'reading','raw'}:raise ValueError('校验模式/文本口径无效')
    field='readingText' if result['surface']=='reading' else 'text';rows=result.get('alignments',[])
    if not rows:raise ValueError('无对齐事项')
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('重复的差异ID')
    for side,i in (('left',0),('right',1)):
        if [j for r in rows for j in r[side]]!=list(range(len(docs[i]['layouts']))):raise ValueError('对齐阅读顺序或覆盖率不完整')
    semantic_decisions=[]
    for r in rows:
        if not r['left'] and not r['right']:raise ValueError('空对齐事项')
        for side,i in (('left',0),('right',1)):
            if any(isinstance(j,bool) or not isinstance(j,int) for j in r[side]):raise ValueError('布局索引类型无效')
            text='\n'.join(docs[i]['layouts'][j][field] for j in r[side])
            refs=[{'documentIndex':i,'layoutId':docs[i]['layouts'][j]['layoutId']} for j in r[side]]
            if r[side+'Text']!=text or r[side+'Refs']!=refs:raise ValueError('差异文本或原文引用与布局不匹配')
        expected='insert' if not r['left'] else 'delete' if not r['right'] else 'equal' if r['leftText']==r['rightText'] else 'replace'
        if r['operation']!=expected:raise ValueError('字符差异类别不匹配')
        if r['charOps']!=character_ops(r['leftText'],r['rightText']):raise ValueError('字符差异范围不匹配')
        if r['alignmentStatus'] not in {'aligned','unresolved'}:raise ValueError('对齐状态无效')
        s=r['semantic']['status']
        if result['mode']=='character' and s!='not_requested':raise ValueError('字符模式混入语义结论')
        if result['mode']=='semantic':
            if expected=='equal' and s!='equal':raise ValueError('字符相同的语义状态被替换')
            if expected!='equal' and s not in {'pending','equivalent','changed','uncertain'}:raise ValueError('语义状态无效')
            if s in {'equivalent','changed','uncertain'}:
                semantic_decisions.append({'id':r['id'],**r['semantic']})
    if semantic_decisions:apply_decisions(result,{'comparisonId':result['comparisonId'],'decisions':semantic_decisions})
    identity={'documents':docs,'mode':result['mode'],'surface':result['surface'],'pairs':[(r['left'],r['right'],r['alignmentStatus']=='aligned') for r in rows]}
    if digest(identity)!=result['comparisonId']:raise ValueError('比对快照摘要与内容不匹配')
    check=recalculate(json.loads(json.dumps(result)))
    if any(check[k]!=result[k] for k in ('summary','status','coverage')):raise ValueError('统计/完成状态与事项不匹配')
    return {'valid':True,'status':result['status'],'coverage':result['coverage'],'summary':result['summary']}

def _module(skill,name):
    script=PLUGIN/'skills'/skill/'scripts'/(name+'.py')
    if not script.is_file():raise ValueError('缺少输出 skill 脚本：'+str(script))
    sys.path.insert(0,str(script.parent));spec=importlib.util.spec_from_file_location(name,script);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module

def export(result,directory,formats,source_docx=None,mapping=None,reconstructed=False):
    validate_result(result);out=Path(directory)
    if out.exists():raise ValueError('输出目录已存在，请使用新目录以保留旧产物')
    if not formats or any(f not in {'html','tracked','report-docx','report-pdf'} for f in formats):raise ValueError('输出项为 html/tracked/report-docx/report-pdf，可多选')
    if 'tracked' in formats and not source_docx and not reconstructed:raise ValueError('原件修订需要 source-docx；从解析文本重建须显式 reconstructed')
    out.mkdir(parents=True);write(out/'comparison.json',result)
    manifest={'comparisonId':result['comparisonId'],'comparisonStatus':result['status'],'outputs':[],'status':'running','errors':[]}
    for f in dict.fromkeys(formats):
        try:
            if f=='html':
                path=out/'comparison.html';_module('document-diff-html','render_html').render_html(result,path)
            elif f=='tracked':
                path=out/'tracked.docx';_module('document-word-edit','write_redline').write_redline(result,source_docx,path,mapping=mapping,reconstructed=reconstructed)
            else:
                ext=f.split('-')[1];path=out/('comparison-report.'+ext);_module('document-diff-report','write_report').write_report(result,path,format=ext)
            manifest['outputs'].append({'format':f,'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
        except Exception as exc:
            manifest['errors'].append({'format':f,'message':str(exc)})
    manifest['status']='partial' if manifest['errors'] else 'complete'
    write(out/'export-manifest.json',manifest)
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('import');q.add_argument('--input',required=True);q.add_argument('--document-index',type=int,choices=[0,1],required=True);q.add_argument('--name',required=True);q.add_argument('--output',required=True);q.add_argument('--source');q.add_argument('--parse-run-id')
    q=sub.add_parser('compare');q.add_argument('--left',required=True);q.add_argument('--right',required=True);q.add_argument('--mode',choices=['character','semantic'],required=True);q.add_argument('--surface',choices=['reading','raw'],default='reading');q.add_argument('--output',required=True);q.add_argument('--alignment',help='显式对齐数组 JSON，须完整覆盖且按阅读顺序');q.add_argument('--max-cells',type=int,default=16000)
    q=sub.add_parser('validate');q.add_argument('--input',required=True)
    q=sub.add_parser('semantic-requests');q.add_argument('--input',required=True);q.add_argument('--output',required=True)
    q=sub.add_parser('apply-semantic');q.add_argument('--input',required=True);q.add_argument('--decisions',required=True);q.add_argument('--output',required=True)
    q=sub.add_parser('read-window');q.add_argument('--input',required=True);q.add_argument('--id',required=True);q.add_argument('--side',choices=['left','right'],required=True);q.add_argument('--start',type=int,default=0);q.add_argument('--length',type=int,default=6000)
    q=sub.add_parser('export');q.add_argument('--input',required=True);q.add_argument('--out',required=True);q.add_argument('--formats',required=True,help='逗号分隔 html,tracked,report-docx,report-pdf');q.add_argument('--source-docx');q.add_argument('--mapping');q.add_argument('--reconstructed',action='store_true')
    args=p.parse_args()
    try:
        if args.command=='import':
            raw_bytes=Path(args.input).read_bytes();result=import_document(json.loads(raw_bytes.decode('utf-8-sig')),args.document_index,args.name,source=args.source,parse_run_id=args.parse_run_id,raw_bytes=raw_bytes);write(args.output,result)
        elif args.command=='compare':
            if args.max_cells<1:raise ValueError('max-cells 必须为正整数')
            result=align_documents(read(args.left),read(args.right),args.mode,args.surface,args.max_cells,read(args.alignment) if args.alignment else None);validate_result(result);write(args.output,result)
        elif args.command=='validate':print(json.dumps(validate_result(read(args.input)),ensure_ascii=False));return 0
        elif args.command=='semantic-requests':
            result=read(args.input);validate_result(result);write(args.output,semantic_requests(result))
        elif args.command=='apply-semantic':
            result=read(args.input);validate_result(result);result=apply_decisions(result,read(args.decisions));validate_result(result);write(args.output,result)
        elif args.command=='read-window':
            result=read(args.input);validate_result(result);row=next(x for x in result['alignments'] if x['id']==args.id);text=row[args.side+'Text']
            if args.start<0 or not 0<args.length<=20000 or args.start>len(text):raise ValueError('窗口范围无效；单次最多20000字符')
            end=min(len(text),args.start+args.length);print(json.dumps({'id':args.id,'side':args.side,'start':args.start,'end':end,'total':len(text),'text':text[args.start:end],'nextStart':end if end<len(text) else None},ensure_ascii=False));return 0
        elif args.command=='export':
            result=export(read(args.input),args.out,args.formats.split(','),args.source_docx,read(args.mapping) if args.mapping else None,args.reconstructed);print(json.dumps(result,ensure_ascii=False));return 1 if result['errors'] else 0
        print(json.dumps({'ok':True,'output':str(Path(args.output).resolve())},ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError,StopIteration) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),file=sys.stderr);return 2

if __name__=='__main__':sys.exit(main())
