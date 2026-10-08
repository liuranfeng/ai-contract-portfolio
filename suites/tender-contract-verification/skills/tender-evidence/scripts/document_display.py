"""Safe structural display of parser text. Raw evidence is never modified in storage."""
import difflib
import html
import re
from html.parser import HTMLParser

ALLOWED={'p','div','span','br','table','thead','tbody','tfoot','tr','th','td','caption','strong','b','em','i','u','s','del','sub','sup','ul','ol','li','blockquote','h1','h2','h3','h4','h5','h6','pre','code','hr','mark'}
FORBIDDEN={'script','style','iframe','object','embed','svg','math','form','input','button','textarea','select','link','meta','base'}
VOID={'br','hr','img','input','embed','link','meta','base'}

class Node:
    def __init__(self,tag='',attrs=''):
        self.tag=tag;self.attrs=attrs;self.children=[]

class SafeTree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.root=Node();self.stack=[self.root];self.blocked=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if self.blocked:
            if tag not in VOID:self.blocked.append(tag)
            return
        if tag in FORBIDDEN:
            if tag not in VOID:self.blocked.append(tag)
            return
        if tag=='img':
            node=Node('span',' class="doc-image"');node.children=['〔原文图像：'+(attrs.get('alt') or '见原件')+'〕'];self.stack[-1].children.append(node);return
        if tag=='a':tag='span'
        if tag not in ALLOWED:
            self.stack[-1].children.append(self.get_starttag_text());return
        safe=[]
        if tag in {'th','td'}:
            for key in ('colspan','rowspan'):
                value=attrs.get(key,'')
                if value.isdigit() and 1<=int(value)<=100:safe.append(key+'="'+str(int(value))+'"')
        if tag=='ol' and attrs.get('start','').isdigit():safe.append('start="'+str(int(attrs['start']))+'"')
        if attrs.get('class') in {'doc-image','doc-code'}:safe.append('class="'+attrs['class']+'"')
        align=re.search(r'(?:^|;)\s*text-align\s*:\s*(left|center|right)\s*(?:;|$)',attrs.get('style',''),re.I)
        if align:safe.append('style="text-align:'+align.group(1).lower()+'"')
        node=Node(tag,(' '+' '.join(safe)) if safe else '');self.stack[-1].children.append(node)
        if tag not in VOID:self.stack.append(node)
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)
    def handle_endtag(self,tag):
        if self.blocked:
            if tag in self.blocked:
                self.blocked=self.blocked[:len(self.blocked)-1-self.blocked[::-1].index(tag)]
            return
        if tag=='a':tag='span'
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];return
        if tag not in ALLOWED and tag not in FORBIDDEN:self.stack[-1].children.append('</'+tag+'>')
    def handle_data(self,data):
        if not self.blocked:self.stack[-1].children.append(data)

def inline(text):
    # These constructs encode typography, not new facts. Unsupported formulae stay literal.
    text=text.replace('\\n','<br>')
    text=re.sub(r'!\[([^\]]*)\]\([^\n)]*\)',lambda m:'<span class="doc-image">〔原文图像：'+html.escape(m[1] or '见原件')+'〕</span>',text)
    text=re.sub(r'\[([^\]]+)\]\([^\n)]*\)',r'<span>\1</span>',text)
    text=re.sub(r'\*\*([^*\n]+)\*\*',r'<strong>\1</strong>',text)
    text=re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)',r'<em>\1</em>',text)
    text=re.sub(r'`([^`\n]+)`',lambda m:'<code>'+html.escape(m[1])+'</code>',text)
    text=re.sub(r'\$\s*\\underline\{([^{}]+)\}\s*\$',r'<u>\1</u>',text)
    text=re.sub(r'\$\s*([^$]+?)\s*\$',lambda m:m[1].replace(r'\circ','°').replace(r'\leq','≤').replace(r'\geq','≥') if re.fullmatch(r'[\d\s.,%+\-°C℃\\a-z{}]+',m[1]) else m[0],text)
    text=text.replace(r'\(', '').replace(r'\)', '') if r'\circ' in text else text
    return text

def cells(line):
    return [c.strip().replace(r'\|','|') for c in re.split(r'(?<!\\)\|',line.strip().strip('|'))]

def prepare(raw):
    if re.search(r'&lt;/?(?:table|tr|td|th|p|div|br|img|strong|span)\b',raw,re.I):raw=html.unescape(raw)
    lines=raw.splitlines();out=[];i=0
    while i<len(lines):
        line=lines[i];trim=line.strip()
        if not trim:i+=1;continue
        if '|' in trim and i+1<len(lines) and all(re.fullmatch(r':?-{2,}:?',x) for x in cells(lines[i+1])):
            headers=cells(trim);out.append('<table><thead><tr>'+''.join('<th>'+inline(x)+'</th>' for x in headers)+'</tr></thead><tbody>');i+=2
            while i<len(lines) and '|' in lines[i] and lines[i].strip():
                row=cells(lines[i]);out.append('<tr>'+''.join('<td>'+inline(x)+'</td>' for x in row)+'</tr>');i+=1
            out.append('</tbody></table>');continue
        heading=re.match(r'^(#{1,6})\s+(.+)',trim)
        if heading:out.append('<h'+str(len(heading[1]))+'>'+inline(heading[2])+'</h'+str(len(heading[1]))+'>')
        elif re.match(r'^[-*+]\s+',trim):out.append('<ul><li>'+inline(trim[2:])+'</li></ul>')
        elif re.match(r'^\d+\.\s+',trim):
            m=re.match(r'^(\d+)\.\s+(.+)',trim);out.append('<ol start="'+m[1]+'"><li>'+inline(m[2])+'</li></ol>')
        elif trim.startswith('> '):out.append('<blockquote>'+inline(trim[2:])+'</blockquote>')
        elif re.match(r'^</?(?:table|tr|td|th|thead|tbody|tfoot|caption|p|div|ul|ol|li|h[1-6]|blockquote|pre)\b',trim,re.I):out.append(inline(line))
        else:out.append('<p>'+inline(line)+'</p>')
        i+=1
    return ''.join(out)

def tree(raw):
    p=SafeTree();p.feed(prepare(raw));p.close();return p.root

def plain(node):
    return ''.join(c if isinstance(c,str) else plain(c) for c in node.children)

def serialize(node,ranges=(),position=None):
    position=[0] if position is None else position;body=[]
    for child in node.children:
        if isinstance(child,Node):body.append(serialize(child,ranges,position));continue
        start=position[0];end=start+len(child);position[0]=end;cursor=start
        for lo,hi in ranges:
            lo=max(lo,start);hi=min(hi,end)
            if lo>=hi:continue
            body.append(html.escape(child[cursor-start:lo-start]));body.append('<mark>'+html.escape(child[lo-start:hi-start])+'</mark>');cursor=hi
        body.append(html.escape(child[cursor-start:]))
    if not node.tag:return ''.join(body)
    return '<'+node.tag+node.attrs+'>'+''.join(body)+('' if node.tag in VOID else '</'+node.tag+'>')

def render_document(raw):
    return serialize(tree(raw))

def document_diff(a,b):
    left,right=tree(a),tree(b);x,y=plain(left),plain(right);lr=[];rr=[]
    if max(len(x),len(y))>12000:
        # Bound expensive comparison for long OCR evidence; complete text remains visible.
        xx=x.splitlines(keepends=True);yy=y.splitlines(keepends=True)
        if len(xx)<2 or len(yy)<2:xx=[x[i:i+400] for i in range(0,len(x),400)];yy=[y[i:i+400] for i in range(0,len(y),400)]
        xa=[0];ya=[0]
        for s in xx:xa.append(xa[-1]+len(s))
        for s in yy:ya.append(ya[-1]+len(s))
        for tag,i,j,k,l in difflib.SequenceMatcher(None,xx,yy,autojunk=True).get_opcodes():
            if tag!='equal':lr.append((xa[i],xa[j]));rr.append((ya[k],ya[l]))
    else:
        for tag,i,j,k,l in difflib.SequenceMatcher(None,x,y,autojunk=False).get_opcodes():
            if tag!='equal':lr.append((i,j));rr.append((k,l))
    return serialize(left,lr),serialize(right,rr)
