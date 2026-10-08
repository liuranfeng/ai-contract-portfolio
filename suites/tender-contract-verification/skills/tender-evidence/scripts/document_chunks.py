"""Offline PDF chunk lineage and model-reading windows; never uploads or rewrites layout IDs.

PDF commands require pypdf. The chunk-plan command uses the standard library only.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def pdf_types():
    try:
        from pypdf import PdfReader, PdfWriter
        return PdfReader, PdfWriter
    except ImportError as exc:
        raise RuntimeError('PDF splitting/verification requires pypdf; install in the selected runtime') from exc


def positive(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(name + ' must be a positive integer')


def doc_index(value):
    if type(value) is not int or value < 0:
        raise ValueError('documentIndex must be a nonnegative integer')


def page_signature(page):
    content = page.get_contents()
    return {
        'mediaBox': [float(v) for v in page.mediabox],
        'cropBox': [float(v) for v in page.cropbox],
        'rotation': page.rotation,
        'contentSha256': hashlib.sha256(content.get_data() if content else b'').hexdigest(),
    }


def split_pdf(source, output, parent_document_index, child_index_start, max_pages=60,
              max_bytes=35_000_000):
    """Write new derived PDFs with explicit one-based lineage. Never overwrite output.

    Limits are caller supplied service constraints, not a claim about any API's current limit.
    On failure, a partially written directory may remain, but no complete manifest is issued.
    """
    positive(max_pages, 'max_pages')
    positive(max_bytes, 'max_bytes')
    doc_index(parent_document_index)
    doc_index(child_index_start)
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Output already exists; choose a new run directory')
    PdfReader, PdfWriter = pdf_types()
    reader = PdfReader(source)
    if reader.is_encrypted:
        raise ValueError('Encrypted PDF needs an explicitly decrypted input copy')
    count = len(reader.pages)
    if not count:
        raise ValueError('PDF has no pages')
    # Worst-case one page per child: reserve this entire range before any writes.
    if child_index_start <= parent_document_index < child_index_start + count:
        raise ValueError('Child documentIndex range aliases parent; reserve a disjoint range')
    source_hash = sha256(source)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'schemaVersion': '1.0', 'kind': 'physical-pdf-split', 'status': 'pending',
                'sourcePath': str(source), 'sourceSha256': source_hash,
                'parentDocumentIndex': parent_document_index, 'originalPageCount': count,
                'maxPages': max_pages, 'maxBytes': max_bytes, 'chunks': []}

    def write_range(start, end):
        writer = PdfWriter()
        for page in reader.pages[start:end]:
            writer.add_page(page)  # retain vector/text objects; no rasterization
        buffer = io.BytesIO()
        writer.write(buffer)
        body = buffer.getvalue()
        if len(body) > max_bytes:
            if end - start == 1:
                raise ValueError('single page exceeds max_bytes at originalPage ' + str(start + 1))
            middle = start + (end - start) // 2
            write_range(start, middle)
            write_range(middle, end)
            return
        index = child_index_start + len(manifest['chunks'])
        name = 'document-%s-pages-%s-%s.pdf' % (index, start + 1, end)
        with (output / name).open('xb') as stream:
            stream.write(body)
        manifest['chunks'].append({
            'documentIndex': index, 'parentDocumentIndex': parent_document_index,
            'file': name, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
            'originalPageStart': start + 1, 'originalPageEnd': end,
            'pages': [{'chunkPage': i - start + 1, 'originalPage': i + 1,
                       'signature': page_signature(reader.pages[i])} for i in range(start, end)]})

    for start in range(0, count, max_pages):
        write_range(start, min(start + max_pages, count))
    if sha256(source) != source_hash:
        raise ValueError('Source changed during split; discard incomplete output and use a new run')
    manifest_path = output / 'manifest.json'
    with manifest_path.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    try:
        result = verify_manifest(manifest_path, _allow_pending=True)
        if not result['valid']:
            raise ValueError('Split failed verification: ' + '; '.join(result['errors']))
    except Exception:
        # A failed run is never represented as complete, even after a verifier exception.
        manifest['status'] = 'failed'
        temporary = output / 'manifest.failed.tmp'
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
        temporary.replace(manifest_path)
        raise
    manifest['status'] = 'complete'
    temporary = output / 'manifest.complete.tmp'
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    temporary.replace(manifest_path)  # Atomic publication after successful verification.
    return manifest


def verify_manifest(path, *, _allow_pending=False):
    """Check source/chunk bytes, contiguous exact-once page coverage and page preservation."""
    path = Path(path).resolve()
    errors = []
    try:
        manifest = json.loads(path.read_text(encoding='utf-8-sig'))
        PdfReader, _ = pdf_types()
        source = Path(manifest['sourcePath'])
        if sha256(source) != manifest['sourceSha256']:
            errors.append('Source hash mismatch')
        reader = PdfReader(source)
        allowed_statuses = ('complete', 'pending') if _allow_pending else ('complete',)
        if manifest.get('status') not in allowed_statuses:
            errors.append('Manifest is not complete')
        count = manifest['originalPageCount']
        positive(count, 'originalPageCount')
        positive(manifest['maxPages'], 'maxPages')
        positive(manifest['maxBytes'], 'maxBytes')
        doc_index(manifest['parentDocumentIndex'])
        if len(reader.pages) != count:
            errors.append('Original page count mismatch')
        indexes, files, seen = set(), set(), []
        for chunk in manifest['chunks']:
            try:
                di = chunk['documentIndex']
                doc_index(di)
                if di in indexes or di == manifest['parentDocumentIndex']:
                    errors.append('Duplicate or aliased child documentIndex')
                indexes.add(di)
                if chunk['parentDocumentIndex'] != manifest['parentDocumentIndex']:
                    errors.append('Parent documentIndex mismatch')
                target = (path.parent / chunk['file']).resolve()
                if not target.is_relative_to(path.parent) or target == path:
                    raise ValueError('Chunk path escapes manifest directory')
                if target in files:
                    errors.append('Duplicate chunk file')
                files.add(target)
                if not target.is_file():
                    raise ValueError('Missing chunk file: ' + chunk['file'])
                if target.stat().st_size != chunk['bytes'] or sha256(target) != chunk['sha256']:
                    raise ValueError('Chunk bytes/hash mismatch: ' + chunk['file'])
                if chunk['bytes'] > manifest['maxBytes']:
                    errors.append('Chunk exceeds maxBytes')
                child = PdfReader(target)
                mappings = chunk['pages']
                if len(child.pages) != len(mappings) or not mappings or len(mappings) > manifest['maxPages']:
                    errors.append('Chunk page count/limit mismatch')
                if [m['chunkPage'] for m in mappings] != list(range(1, len(mappings) + 1)):
                    errors.append('Local chunk pages must be contiguous and one-based')
                originals = [m['originalPage'] for m in mappings]
                if originals != list(range(chunk['originalPageStart'], chunk['originalPageEnd'] + 1)):
                    errors.append('Original page range mismatch')
                for m in mappings:
                    positive(m['originalPage'], 'originalPage')
                    positive(m['chunkPage'], 'chunkPage')
                    seen.append(m['originalPage'])
                    a = page_signature(reader.pages[m['originalPage'] - 1])
                    b = page_signature(child.pages[m['chunkPage'] - 1])
                    if a != b or a != m['signature']:
                        errors.append('Page content/geometry mismatch: ' + str(m['originalPage']))
            except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
                errors.append(str(exc))
        if seen != list(range(1, count + 1)):
            errors.append('Page mapping has gap, overlap, duplicate or wrong order')
    except Exception as exc:
        errors.append(type(exc).__name__ + ': ' + str(exc))
    return {'valid': not errors, 'errors': errors}


def ref_key(ref):
    doc_index(ref['documentIndex'])
    lid = ref['layoutId']
    if type(lid) not in (str, int) or (type(lid) is str and not lid.strip()):
        raise ValueError('layoutId must retain its native nonempty string/integer type')
    return ref['documentIndex'], type(lid).__name__, lid


def map_layouts(manifest_path, child_document_index, imported, *, page_base):
    """Attach original pages using a verified physical manifest and explicit parser base.

    Native parser page/layoutId/text fields are preserved, never normalized or renamed.
    The returned metadata is intended for the host document registry, which still supplies
    role, display name and actual parseRunId. No parsing or API call happens here.
    """
    if type(page_base) is not int or page_base not in (0, 1):
        raise ValueError('page_base must explicitly be 0 or 1')
    doc_index(child_document_index)
    verified = verify_manifest(manifest_path)
    if not verified['valid']:
        raise ValueError('Invalid manifest: ' + '; '.join(verified['errors']))
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    chunks = [c for c in manifest['chunks'] if c['documentIndex'] == child_document_index]
    if len(chunks) != 1:
        raise ValueError('Child documentIndex must identify exactly one verified chunk')
    chunk = chunks[0]
    if not isinstance(imported, dict) or not isinstance(imported.get('layouts'), list):
        raise ValueError('Expected import-layouts JSON with layouts and rawParseSha256')
    digest = imported.get('rawParseSha256')
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdefABCDEF' for c in digest):
        raise ValueError('rawParseSha256 must be a SHA-256 hex digest')
    if not imported['layouts']:
        raise ValueError('Imported layouts are empty; review parsing before mapping')
    result = copy.deepcopy(imported)
    lineage = {
        'documentIndex': child_document_index,
        'parentDocumentIndex': manifest['parentDocumentIndex'],
        'sourcePath': str((manifest_path.parent / chunk['file']).resolve()),
        'sourceSha256': chunk['sha256'],
        'parentSourcePath': manifest['sourcePath'],
        'parentSourceSha256': manifest['sourceSha256'],
        'chunkSha256': chunk['sha256'],
        'splitManifestSha256': sha256(manifest_path),
        'originalPageStart': chunk['originalPageStart'],
        'originalPageEnd': chunk['originalPageEnd'],
        'originalPageCount': manifest['originalPageCount'],
        'parserPageBase': page_base,
    }
    for field, value in lineage.items():
        if field in result and (type(result[field]) is not type(value) or result[field] != value):
            raise ValueError('Contradictory imported lineage field: ' + field)
    mapping = {m['chunkPage']: m['originalPage'] for m in chunk['pages']}
    seen = set()
    for block in result['layouts']:
        identity = ref_key({'documentIndex': child_document_index, 'layoutId': block['layoutId']})
        if identity in seen:
            raise ValueError('Duplicate layoutId within parser document; do not renumber or auto-partition')
        seen.add(identity)
        native_page = block.get('page')
        if type(native_page) is not int:
            raise ValueError('Native parser page must be an integer, not bool/string/float')
        chunk_page = native_page + 1 - page_base
        if chunk_page not in mapping:
            raise ValueError('Unmapped parser page: ' + str(native_page))
        original_page = mapping[chunk_page]
        if 'originalPage' in block and (type(block['originalPage']) is not int or block['originalPage'] != original_page):
            raise ValueError('Contradictory originalPage for layoutId ' + str(block['layoutId']))
        block['originalPage'] = original_page
    result.update(lineage)
    return result


def chunk_plan(snapshot, max_chars=24000, context_blocks=2):
    """Plan exact-once primary ownership, opportunistic context under a character budget.

    Oversize blocks remain intact and are flagged. Deferred context must be explicitly
    retrieved before deciding any fact depending on it. A character budget is not tokens.
    """
    positive(max_chars, 'max_chars')
    if type(context_blocks) is not int or context_blocks < 0:
        raise ValueError('context_blocks must be nonnegative')
    windows, seen, docs = [], set(), set()
    for doc in snapshot['documents']:
        di = doc['documentIndex']
        doc_index(di)
        if di in docs:
            raise ValueError('Duplicate documentIndex')
        docs.add(di)
        blocks = doc['layouts']
        refs = []
        for block in blocks:
            ref = {'documentIndex': di, 'layoutId': block['layoutId']}
            k = ref_key(ref)
            if k in seen:
                raise ValueError('Duplicate layoutId within document; do not renumber')
            seen.add(k)
            if not isinstance(block['text'], str):
                raise ValueError('Layout text must be a string')
            refs.append(ref)
        start = 0
        while start < len(blocks):
            end, primary_chars = start, 0
            while end < len(blocks):
                size = len(blocks[end]['text'])
                if end > start and primary_chars + size > max_chars:
                    break
                primary_chars += size
                end += 1
                if primary_chars >= max_chars:
                    break
            context, deferred, total = [], [], primary_chars
            # Nearest neighbors first, then output in source order.
            candidates = sorted(list(range(max(0, start - context_blocks), start)) +
                                list(range(end, min(len(blocks), end + context_blocks))),
                                key=lambda i: min(abs(i - start), abs(i - (end - 1))))
            for i in candidates:
                size = len(blocks[i]['text'])
                if total + size <= max_chars:
                    context.append(i)
                    total += size
                else:
                    deferred.append(i)
            windows.append({'windowIndex': len(windows), 'documentIndex': di,
                            'primaryRefs': refs[start:end],
                            'contextRefs': [refs[i] for i in sorted(context)],
                            'deferredContextRefs': [refs[i] for i in sorted(deferred)],
                            'primaryChars': primary_chars, 'totalChars': total,
                            'oversizeBlock': primary_chars > max_chars,
                            'needsContextFollowup': bool(deferred),
                            'parseRunId': doc.get('parseRunId')})
            start = end
    return {'schemaVersion': '1.0', 'kind': 'analysis-window-plan', 'maxChars': max_chars,
            'contextBlocks': context_blocks, 'primaryBlockCount': len(seen),
            'sourceSnapshotSha256': hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest(),
            'windows': windows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    split = sub.add_parser('split', help='Copy PDF pages into new bounded chunks; never rasterize')
    split.add_argument('source')
    split.add_argument('output')
    split.add_argument('--parent-document-index', required=True, type=int)
    split.add_argument('--child-index-start', required=True, type=int,
                       help='Reserve a project-wide unused contiguous child index range')
    split.add_argument('--max-pages', type=int, default=60)
    split.add_argument('--max-bytes', type=int, default=35_000_000)
    verify = sub.add_parser('verify', help='Check manifest, hashes, page coverage and geometry')
    verify.add_argument('manifest')
    mapped = sub.add_parser('map-layouts', help='Map native parser pages to original pages through a verified manifest')
    mapped.add_argument('manifest')
    mapped.add_argument('child_document_index', type=int)
    mapped.add_argument('imported_layouts_json')
    mapped.add_argument('output_json')
    mapped.add_argument('--page-base', required=True, type=int, choices=(0, 1),
                        help='Explicit native parser page base; never guessed')
    plan = sub.add_parser('chunk-plan', help='Plan bounded reading windows without truncating source blocks')
    plan.add_argument('snapshot')
    plan.add_argument('output')
    plan.add_argument('--max-chars', type=int, default=24000)
    plan.add_argument('--context-blocks', type=int, default=2)
    args = parser.parse_args()
    if args.command == 'split':
        result = split_pdf(args.source, args.output, args.parent_document_index,
                           args.child_index_start, args.max_pages, args.max_bytes)
        print(json.dumps({'manifest': str(Path(args.output).resolve() / 'manifest.json'),
                          'chunks': len(result['chunks'])}, ensure_ascii=False))
    elif args.command == 'verify':
        result = verify_manifest(args.manifest)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result['valid']:
            raise SystemExit(1)
    elif args.command == 'map-layouts':
        imported_path = Path(args.imported_layouts_json)
        imported = json.loads(imported_path.read_text(encoding='utf-8-sig'))
        result = map_layouts(args.manifest, args.child_document_index, imported, page_base=args.page_base)
        result['importedLayoutsFileSha256'] = sha256(imported_path)
        with Path(args.output_json).open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({'output': str(Path(args.output_json).resolve()),
                          'documentIndex': args.child_document_index, 'layouts': len(result['layouts'])}))
    else:
        source = Path(args.snapshot)
        snapshot = json.loads(source.read_text(encoding='utf-8-sig'))
        result = chunk_plan(snapshot, args.max_chars, args.context_blocks)
        result['sourceFileSha256'] = sha256(source)
        with Path(args.output).open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({'output': str(Path(args.output).resolve()),
                          'windows': len(result['windows']), 'blocks': result['primaryBlockCount']}))


if __name__ == '__main__':
    main()
