"""Layout-backed evidence tools. No API calls, model inference or invented IDs."""
import argparse
import hashlib
import html
import json
from pathlib import Path


def key(ref):
    index, lid = ref.get('documentIndex'), ref.get('layoutId')
    if type(index) is not int or index < 0:
        raise ValueError('documentIndex must be a nonnegative integer')
    if type(lid) not in (str, int) or (isinstance(lid, str) and not lid.strip()):
        raise ValueError('layoutId must be an original nonempty string or integer')
    return index, type(lid).__name__, lid


def import_layouts(raw):
    pages = raw.get('pages')
    if not isinstance(pages, list) or not pages:
        raise ValueError('Expected raw pages[].layouts[]; adapter required for other formats')
    result, seen = [], set()
    for page in pages:
        blocks = page.get('layouts')
        if not isinstance(blocks, list) or not blocks:
            raise ValueError('Empty or missing layouts: review page before import')
        for block in blocks:
            if 'layoutId' in block and 'layout_id' in block:
                if type(block['layoutId']) != type(block['layout_id']) or block['layoutId'] != block['layout_id']:
                    raise ValueError('Conflicting layout ID fields')
            lid = block.get('layoutId', block.get('layout_id'))
            identity = key({'documentIndex': 0, 'layoutId': lid})
            if identity in seen:
                raise ValueError('Duplicate layoutId within document; do not renumber')
            seen.add(identity)
            text = block.get('text')
            if not isinstance(text, str):
                raise ValueError('Layout text missing; explicit parser adapter required')
            layout_text = text
            text_source = 'layouts.text'
            if block.get('type') == 'table':
                tables = [t for t in page.get('tables', [])
                          if type(t.get('layoutId', t.get('layout_id'))) == type(lid)
                          and t.get('layoutId', t.get('layout_id')) == lid]
                if len(tables) != 1 or not isinstance(tables[0].get('markdown'), str) or not tables[0]['markdown'].strip():
                    raise ValueError('Table layout needs matching native tables.markdown')
                text = tables[0]['markdown']
                text_source = 'tables.markdown'
            result.append({'layoutId': lid, 'text': text, 'layoutText': layout_text, 'textSource': text_source,
                           'page': page.get('page', page.get('page_num')),
                           'bbox': block.get('bbox', block.get('position')),
                           'bboxFormat': 'xywh' if 'position' in block else 'parser_native',
                           'type': block.get('type', 'unknown')})
    return result


def index_layouts(data):
    result, docs = {}, set()
    for doc in data['documents']:
        di = doc['documentIndex']
        if type(di) is not int or di < 0 or di in docs:
            raise ValueError('Invalid or duplicate documentIndex')
        docs.add(di)
        for block in doc['layouts']:
            k = key({'documentIndex': di, 'layoutId': block['layoutId']})
            if k in result:
                raise ValueError('Duplicate layoutId within document')
            if not isinstance(block['text'], str):
                raise ValueError('Layout text must be string')
            result[k] = block
    return result


def resolve(data, ref):
    try:
        return index_layouts(data)[key(ref)]
    except KeyError as exc:
        raise ValueError('Source does not resolve in this snapshot') from exc


STATUSES = {'pending', 'implemented', 'incorporated', 'partial', 'weakened',
            'conflict', 'not_found', 'insufficient_materials', 'not_applicable'}


def validate(data, final=False):
    errors = []
    def require(condition, message):
        if not condition:
            errors.append(message)
    try:
        require(data['schemaVersion'] == '1.0.0', 'Unsupported schemaVersion')
        require(bool(data['projectId']) and bool(data['snapshotId']), 'Missing project/snapshot')
        require(bool(data['documents']), 'No documents')
        layouts = index_layouts(data)
        for doc in data['documents']:
            require(bool(doc['parseRunId']) and bool(doc['name']), 'Missing document metadata')
            for field in ('sourceSha256', 'rawParseSha256'):
                value = doc[field]
                require(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'Invalid ' + field)
            require(doc['role'] in {'tender', 'bid', 'contract', 'clarification', 'amendment', 'attachment'}, 'Unknown document role')
            require(doc['status'] in {'complete', 'incomplete'}, 'Unknown parse status')

        def sources(refs):
            require(isinstance(refs, list), 'Sources must be arrays')
            for ref in refs:
                require(key(ref) in layouts, 'Dangling source: ' + str(ref))

        facts = {}
        for fact in data['facts']:
            fid = fact['factId']
            require(isinstance(fid, str) and bool(fid) and fid not in facts, 'Invalid/duplicate factId')
            facts[fid] = fact
            require(bool(fact['primarySources']), 'Fact needs primary evidence')
            sources(fact['primarySources']); sources(fact['contextSources'])
            available = {key(r) for r in fact['primarySources'] + fact['contextSources']}
            require(bool(fact['fields']), 'Empty fact fields')
            for name, value in fact['fields'].items():
                if value is not None:
                    refs = fact['fieldSources'].get(name, [])
                    require(bool(refs), 'Field has no evidence: ' + name)
                    sources(refs)
                    require(all(key(r) in available for r in refs), 'Field evidence not declared on fact')
            require(bool(fact['quotes']), 'Fact needs verbatim quote')
            for quote in fact['quotes']:
                sources([quote['source']])
                require(key(quote['source']) in available, 'Quote evidence not declared on fact')
                block = layouts.get(key(quote['source']), {})
                require(bool(quote['text']) and quote['text'] in block.get('text', ''), 'Quote differs from layout text')
        covered = set()
        for entry in data['coverage']:
            sources([entry['source']])
            k = key(entry['source'])
            require(k not in covered, 'Duplicate coverage')
            covered.add(k)
            require(entry['status'] in {'extracted', 'no_relevant_fact', 'needs_review'}, 'Invalid coverage status')
            require(bool(entry['reason']), 'Coverage needs reason')
            if entry['status'] == 'extracted':
                require(any(k in {key(r) for r in f['primarySources']} for f in facts.values()), 'Extracted block has no fact')
            if final:
                require(entry['status'] != 'needs_review', 'Unresolved coverage')
        checks = set(); used_facts = set()
        for check in data['checks']:
            cid = check['checkId']
            require(isinstance(cid, str) and bool(cid) and cid not in checks, 'Invalid/duplicate checkId')
            checks.add(cid)
            require(bool(check['title']) and bool(check['factIds']), 'Check needs title and facts')
            require(all(fid in facts for fid in check['factIds']), 'Dangling fact reference')
            used_facts.update(check['factIds'])
            for relation in check['relations']:
                require(relation['fromFactId'] in check['factIds'] and relation['toFactId'] in check['factIds'], 'Relation outside check')
                require(relation['type'] in {'responds', 'supplements', 'implements', 'conflicts', 'amends', 'candidate'}, 'Invalid relation type')
                require(bool(relation['basis']), 'Relation needs basis')
                if final:
                    require(relation['type'] != 'candidate', 'Unconfirmed candidate relation')
            v = check['verification']; status = v['status']
            require(status in STATUSES, 'Unknown verification status')
            require(bool(v['reason']), 'Verification needs reason')
            sources(v['reviewedSources'])
            require(isinstance(v['missingMaterials'], list), 'Missing materials must be list')
            if status == 'not_found':
                require(not data['missingMaterials'] and not v['missingMaterials'], 'Missing materials prohibit not_found')
                require(all(d['status'] == 'complete' for d in data['documents']), 'Incomplete parse prohibits not_found')
                contract_sources = {key({'documentIndex': d['documentIndex'], 'layoutId': b['layoutId']})
                                    for d in data['documents'] if d['role'] in {'contract', 'attachment'} for b in d['layouts']}
                require(bool(contract_sources) and contract_sources <= {key(r) for r in v['reviewedSources']}, 'not_found requires full contract/attachment review')
            if status == 'insufficient_materials':
                require(bool(v['missingMaterials']) or any(d['status'] != 'complete' for d in data['documents']), 'Specify missing/incomplete material')
            if final:
                require(status != 'pending', 'Pending verification')
                require(bool(v['reviewNote']), 'Final result needs contextual reviewNote')
                if status not in {'insufficient_materials', 'not_applicable'}:
                    require(bool(v['comparedFields']) and bool(v['reviewedSources']), 'Comparison evidence required')
        if final:
            require(bool(checks), 'No checks to deliver')
            require(covered == set(layouts), 'Every layout needs coverage disposition')
            require(used_facts == set(facts), 'Unassigned facts')
            if data['missingMaterials'] or any(d['status'] != 'complete' for d in data['documents']):
                require(any(c['verification']['status'] == 'insufficient_materials' for c in data['checks']), 'Material gaps must appear in report')
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        errors.append('Invalid structure: ' + str(exc))
    if not errors:
        from report_renderer import validate_report_options
        errors.extend(validate_report_options(data))
    return errors


def anchor(ref):
    return 'src-' + hashlib.sha256(json.dumps(key(ref), ensure_ascii=False).encode()).hexdigest()


def render(data, process=False, gate_errors=()):
    from report_renderer import render_report
    return render_report(data, process=process, gate_errors=gate_errors)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('import-layouts'); p.add_argument('raw'); p.add_argument('output')
    p = subs.add_parser('validate'); p.add_argument('data'); p.add_argument('--final', action='store_true')
    p = subs.add_parser('locate'); p.add_argument('data'); p.add_argument('document_index', type=int); p.add_argument('layout_id_json', help='JSON literal: 12 or \"12\"')
    p = subs.add_parser('report'); p.add_argument('data'); p.add_argument('output_directory')
    p.add_argument('--process', action='store_true', help='Export an explicitly non-final process report')
    args = parser.parse_args()
    try:
        if args.command == 'import-layouts':
            write_new(args.output, json.dumps({'rawParseSha256': hashlib.sha256(Path(args.raw).read_bytes()).hexdigest(), 'layouts': import_layouts(read(args.raw))}, ensure_ascii=False, indent=2))
        else:
            data = read(args.data)
            process = args.command == 'report' and args.process
            errors = validate(data, final=(args.command == 'report' and not process) or getattr(args, 'final', False))
            if errors:
                raise ValueError('\n'.join(errors))
            if args.command == 'locate':
                print(json.dumps(resolve(data, {'documentIndex': args.document_index, 'layoutId': json.loads(args.layout_id_json)}), ensure_ascii=False))
            elif args.command == 'report':
                out = Path(args.output_directory)
                out.mkdir(parents=True, exist_ok=False)
                gate_errors = validate(data, final=True) if process else []
                md, report = render(data, process=process, gate_errors=gate_errors)
                write_new(out / 'report.md', md); write_new(out / 'report.html', report)
                write_new(out / 'project.json', json.dumps(data, ensure_ascii=False, indent=2))
                write_new(out / 'report-manifest.json', json.dumps({
                    'projectId': data['projectId'], 'snapshotId': data['snapshotId'],
                    'reportMode': 'process' if process else 'final', 'reportStyle': 'document-relations-v1',
                    'sourceSha256': hashlib.sha256(Path(args.data).read_bytes()).hexdigest(),
                    'checks': len(data['checks']), 'facts': len(data['facts']),
                    'unresolvedCoverage': sum(x['status'] == 'needs_review' for x in data['coverage']),
                    'finalGateErrors': gate_errors,
                    'reportSha256': hashlib.sha256(report.encode('utf-8')).hexdigest()
                }, ensure_ascii=False, indent=2))
            else:
                print('Validation passed')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
