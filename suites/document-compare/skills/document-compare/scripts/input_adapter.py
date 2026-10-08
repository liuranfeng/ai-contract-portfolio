"""Read parser layouts without renumbering source identifiers or changing raw text."""
import hashlib
import html
import json
import math
import re
from html.parser import HTMLParser
from pathlib import Path

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()

def id_key(value):
    if isinstance(value,bool) or not isinstance(value,(str,int)) or isinstance(value,str) and not value.strip():
        raise ValueError('layoutId 必须为非空原生字符串或整数，不能补号')
    return type(value).__name__,value

class ReadingHTML(HTMLParser):
    """A textual reading surface: preserve cell boundaries; never execute markup."""
    def __init__(self):
        super().__init__(convert_charrefs=True);self.out=[];self.blocked=[];self.in_row=False;self.cell=0
    def newline(self):
        if self.out and not self.out[-1].endswith('\n'):self.out.append('\n')
    def handle_starttag(self,tag,attrs):
        if self.blocked:
            if tag not in {'br','hr','img','input','link','meta'}:self.blocked.append(tag)
            return
        if tag in {'script','style','iframe','object','svg','math'}:self.blocked.append(tag);return
        if tag=='tr':self.newline();self.in_row=True;self.cell=0
        elif tag in {'td','th'}:
            if self.cell:self.out.append('\t')
            self.cell+=1
        elif tag=='br':self.out.append('\n')
        elif tag in {'p','div','h1','h2','h3','h4','h5','h6','li'}:self.newline()
        elif tag=='img':self.out.append('〔图像：'+(dict(attrs).get('alt') or '需核对原件')+'〕')
    def handle_endtag(self,tag):
        if self.blocked:
            if tag==self.blocked[-1]:self.blocked.pop()
            return
        if tag=='tr':self.in_row=False;self.newline()
        elif tag in {'p','div','h1','h2','h3','h4','h5','h6','li'}:self.newline()
    def handle_data(self,data):
        if not self.blocked:self.out.append(data)

def _inline(s):
    s=re.sub(r'!\[([^\]]*)\]\([^)]*\)',r'〔图像：\1〕',s)
    s=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',s)
    s=re.sub(r'\*\*([^*]+)\*\*',r'\1',s)
    s=re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)',r'\1',s)
    s=re.sub(r'`([^`\n]+)`',r'\1',s)
    if re.search(r'<[A-Za-z][^>]*>',s):
        p=ReadingHTML();p.feed(s);p.close();s=''.join(p.out)
        if s.endswith('\n'):s=s[:-1]
    return s

def reading_text(raw):
    if not isinstance(raw,str):raise ValueError('解析 text 必须是字符串')
    source=raw
    if re.search(r'&lt;/?(?:table|tr|td|th|p|div|br)\b',source,re.I):source=html.unescape(source)
    if re.search(r'</?(?:table|thead|tbody|tr|td|th|p|div|br|strong|span|h[1-6]|script|img)\b',source,re.I):
        p=ReadingHTML();p.feed(source);p.close();value=''.join(p.out)
        return value[:-1] if value.endswith('\n') else value
    if not re.search(r'(?m)^#{1,6}\s|\*\*|`[^`]+`|!\[|\]\(|^\s*\|',source):return raw
    lines=source.split('\n');out=[];i=0
    while i<len(lines):
        line=lines[i]
        if '|' in line and i+1<len(lines) and re.fullmatch(r'\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*',lines[i+1]):
            rows=[line];i+=2
            while i<len(lines) and '|' in lines[i] and lines[i].strip():rows.append(lines[i]);i+=1
            for row in rows:out.append('\t'.join(_inline(x.strip().replace('\\|','|').replace('\\n','\n')) for x in re.split(r'(?<!\\)\|',row.strip().strip('|'))))
            continue
        out.append(_inline(re.sub(r'^#{1,6}\s+','',line)));i+=1
    return '\n'.join(out)

def import_document(raw,document_index,name,source=None,parse_run_id=None,raw_bytes=None):
    if type(document_index) is not int or document_index not in (0,1):raise ValueError('两文件比对的文档索引固定为 0 原件、1 比对件')
    container=raw
    while isinstance(container,dict) and 'pages' not in container and any(k in container for k in ('result','data','structuredContent')):
        container=next(container[k] for k in ('result','data','structuredContent') if k in container)
    if not isinstance(container,dict) or not isinstance(container.get('pages'),list):raise ValueError('需要解析返回的 pages[].layouts[]')
    if container.get('parse_status') not in (None,'success'):raise ValueError('解析尚未成功，不能导入')
    original_hash=container.get('source_sha256')
    if source:
        actual=hashlib.sha256(Path(source).read_bytes()).hexdigest()
        if original_hash and actual!=original_hash:raise ValueError('解析原件摘要不匹配')
        original_hash=actual
    layouts=[];seen=set();warnings=[];ordering=[]
    for pi,page in enumerate(container['pages']):
        if not isinstance(page,dict) or not isinstance(page.get('layouts'),list):raise ValueError('页面缺少 layouts，不能假定该页没有文字')
        items=list(page['layouts'])
        if any(not isinstance(x,dict) for x in items):raise ValueError('layout 必须是对象')
        orders=[x.get('reading_order',x.get('readingOrder')) for x in items]
        if any(x is not None for x in orders):
            if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in orders) or len(set(orders))!=len(orders):raise ValueError('reading_order 缺失、非法或重复，需核对阅读顺序')
            items=[x for _,x in sorted(zip(orders,items),key=lambda x:x[0])];ordering.append('explicit')
        else:ordering.append('parser-array')
        for item in items:
            lid=item.get('layoutId',item.get('layout_id'));key=id_key(lid)
            if container.get('parser')=='baidu-document-parser/paddle-vl' and isinstance(lid,str) and re.fullmatch(r'lay-p\d+-i\d+',lid) and not container.get('raw_parse_sha256'):
                raise ValueError('旧解析适配器可能补造了 layoutId；请提供未补号的原始服务布局及归档来源')
            if key in seen:raise ValueError('同一文档的原生 layoutId 重复；分片应先提供文档索引映射')
            if item.get('layout_id_source') in {'generated','synthetic'}:raise ValueError('不能用补造的 layoutId 定位')
            seen.add(key)
            text=item.get('text','');kind=item.get('type',item.get('block_type','text'))
            if not isinstance(text,str):raise ValueError('layout.text 必须为字符串')
            if kind=='table' and not text.strip():
                table=next((t for t in page.get('tables',[]) if isinstance(t,dict) and id_key(t.get('layout_id',t.get('layoutId')))==key),None)
                if table:text=table.get('markdown') or table.get('table_html') or ''
            value={'layoutId':lid,'ordinal':len(layouts),'page':page.get('page',page.get('page_num',pi)),
                   'type':kind,'text':text,'readingText':reading_text(text),'bbox':item.get('bbox',item.get('bounding_box',item.get('position')))}
            if 'text_raw' in item:value['parserLayoutText']=item['text_raw']
            if kind in {'image','figure','picture'} or re.search(r'<img\b|!\[',text,re.I):
                value['nonTextReview']=True;warnings.append('图像/图形需核对原件，文字一致不能证明图像一致')
            if kind=='table' and not text.strip():value['nonTextReview']=True;warnings.append('表格布局缺少可比文字，需复核原件')
            layouts.append(value)
    if not layouts:raise ValueError('解析未提供任何原生布局')
    return {'documentIndex':document_index,'name':name,'parseRunId':parse_run_id or container.get('parse_run_id') or container.get('parseRunId'),
            'sourceSha256':original_hash,'rawParseSha256':hashlib.sha256(raw_bytes).hexdigest() if raw_bytes is not None else digest(raw),
            'layouts':layouts,'readingOrder':ordering,'warnings':list(dict.fromkeys(warnings)),
            'provenance':{'sourceVerified':bool(source),'parseStatus':container.get('parse_status','provided_result'),'pageNumberBasis':'parser-native',
                          'rawParseFile':container.get('raw_parse_file'),'rawArchiveSha256':container.get('raw_parse_sha256'),
                          'archiveRedactedPaths':container.get('archive_redacted_paths',[])}}

def validate_document(doc,index):
    if type(doc.get('documentIndex')) is not int or doc['documentIndex']!=index:raise ValueError('原件文档索引须为0，比对件须为1')
    if not isinstance(doc.get('layouts'),list) or not doc['layouts']:raise ValueError('文档没有 layouts')
    seen=set()
    for i,b in enumerate(doc['layouts']):
        if b.get('ordinal')!=i:raise ValueError('阅读序号与布局数组不一致')
        key=id_key(b.get('layoutId'))
        if key in seen:raise ValueError('原生 layoutId 重复')
        seen.add(key)
        if not isinstance(b.get('text'),str) or not isinstance(b.get('readingText'),str):raise ValueError('缺少原文或阅读文字')
        if b['readingText']!=reading_text(b['text']):raise ValueError('readingText 与解析原文不匹配')
