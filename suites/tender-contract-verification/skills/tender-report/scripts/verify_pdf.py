"""Reopen every PDF page and render representative pages; visual review stays explicit."""
import argparse
import hashlib
import json
from pathlib import Path

def inspect_pdf(source):
    from pypdf import PdfReader
    reader=PdfReader(source)
    if reader.is_encrypted:raise ValueError('Cannot inspect encrypted PDF without authorized decryption')
    pages=[]
    for i,page in enumerate(reader.pages,1):
        text=page.extract_text() or ''
        pages.append({'page':i,'characters':len(text),'width':float(page.mediabox.width),'height':float(page.mediabox.height),
                      'hasEvidenceHeading':'原文关系' in text or '原文证据' in text})
    if not pages:raise ValueError('No PDF pages')
    samples={1,len(pages),max(pages,key=lambda x:x['characters'])['page']}
    evidence=next((x['page'] for x in pages if x['hasEvidenceHeading']),None)
    if evidence:samples.add(evidence)
    return {'source':Path(source).name,'sourceSha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        'pageCount':len(pages),'pages':pages,'lowTextPages':[x['page'] for x in pages if x['characters']<15],
        'samplePages':sorted(samples),'visualReview':'pending',
        'note':'Low text can be blank or graphical. Rendered samples require visual inspection; counts do not prove no clipping.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pdf');p.add_argument('output_directory');p.add_argument('--pages',help='Additional one-based page numbers, comma separated');a=p.parse_args()
    result=inspect_pdf(a.pdf)
    if a.pages:result['samplePages']=sorted(set(result['samplePages'])|{int(x) for x in a.pages.split(',')})
    if any(x<1 or x>result['pageCount'] for x in result['samplePages']):raise ValueError('Sample page outside PDF')
    import pypdfium2
    document=pypdfium2.PdfDocument(a.pdf);out=Path(a.output_directory);out.mkdir(parents=True,exist_ok=False)
    for i in result['samplePages']:
        page=document[i-1];bitmap=page.render(scale=1.3);bitmap.to_pil().save(out/('page-%04d.png'%i));bitmap.close();page.close()
    document.close()
    (out/'pdf-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pageCount':result['pageCount'],'lowTextPages':result['lowTextPages'],'samplePages':result['samplePages'],'visualReview':'pending'},ensure_ascii=False))

if __name__=='__main__':main()
