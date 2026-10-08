"""Standard local invocation for standalone and pre-signature comparison. No approval actions."""
import argparse
import hashlib
import json
from pathlib import Path
from compare import align_documents, apply_decisions, export, import_document, read, validate_result, write


def invoke(request, directory, request_home=None):
    if request.get('schemaVersion') != '1.0':
        raise ValueError('调用契约 schemaVersion 必须为 1.0')
    use_case = request.get('useCase', 'standalone')
    if use_case not in ('standalone', 'pre_sign'):
        raise ValueError('useCase 仅支持 standalone / pre_sign')
    mode = request.get('mode')
    if mode not in ('character', 'semantic'):
        raise ValueError('必须明确 character 或 semantic 模式')
    surface = request.get('surface', 'reading')
    if surface not in ('reading', 'raw'):
        raise ValueError('surface 必须为 reading 或 raw')
    home = Path(request_home or '.').resolve()
    def local(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('缺少文件路径')
        path = Path(value)
        return (home / path).resolve() if not path.is_absolute() else path.resolve()
    documents, paths = [], []
    for index, key in enumerate(('original', 'candidate')):
        source = request.get(key, {})
        parsed_path = local(source.get('parsedPath'))
        source_path = local(source['sourcePath']) if source.get('sourcePath') else None
        raw = parsed_path.read_bytes()
        parsed = json.loads(raw.decode('utf-8-sig'))
        # At this entry point a supplied source must be bound to its parse output.
        # import_document also validates the same value against the actual bytes.
        container = parsed
        while isinstance(container, dict) and 'pages' not in container and any(k in container for k in ('result', 'data', 'structuredContent')):
            container = next(container[k] for k in ('result', 'data', 'structuredContent') if k in container)
        if source_path and not container.get('source_sha256'):
            raise ValueError('标准调用要求解析结果带 source_sha256，不能把无来源摘要的解析结果绑定到文件')
        documents.append(import_document(parsed, index, source.get('name') or ('原件' if index == 0 else '比对件'), source=source_path, raw_bytes=raw))
        paths.append(source_path)
    context = request.get('context', {})
    if not isinstance(context, dict):
        raise ValueError('context 必须为对象')
    binding = None
    if use_case == 'pre_sign':
        required = ('contractId', 'approvalId', 'approvedVersionId', 'approvedSourceSha256')
        if any(not isinstance(context.get(k), str) or not context[k].strip() for k in required):
            raise ValueError('签前比对必须提供合同、审批、通过版本和通过文件摘要')
        if not all(paths):
            raise ValueError('签前比对必须绑定审批通过文件和待签署文件')
        approved_hash = hashlib.sha256(paths[0].read_bytes()).hexdigest()
        if context['approvedSourceSha256'].lower() != approved_hash:
            raise ValueError('审批通过版摘要不匹配，不能改用最新清稿或其他文件作基准')
        binding = {k:context[k] for k in required}
        binding['candidateSourceSha256'] = hashlib.sha256(paths[1].read_bytes()).hexdigest()
    formats = request.get('outputs', ['tracked'] if use_case == 'pre_sign' else ['html'])
    if not isinstance(formats, list) or not formats or any(x not in ('tracked', 'html', 'report-docx', 'report-pdf') for x in formats):
        raise ValueError('outputs 必须为有效产物数组')
    if use_case == 'pre_sign' and 'tracked' not in formats:
        raise ValueError('签前场景必须包含 Word 修订 tracked 输出')
    if 'tracked' in formats and (not paths[0] or paths[0].suffix.lower() != '.docx'):
        raise ValueError('原件修订需要审批基准的 DOCX；非 DOCX 请显式选择重建路径，不静默替代原件')
    alignment = read(local(request['alignmentPath'])) if request.get('alignmentPath') else None
    result = align_documents(*documents, mode=mode, surface=surface, alignment_override=alignment)
    if request.get('semanticDecisionsPath'):
        if mode != 'semantic':
            raise ValueError('字符模式不能传入语义判定')
        result = apply_decisions(result, read(local(request['semanticDecisionsPath'])))
    validate_result(result)
    mapping = read(local(request['mappingPath'])) if request.get('mappingPath') else None
    manifest = export(result, directory, formats, source_docx=paths[0], mapping=mapping)
    changed = sum(result['summary'].get(k, 0) for k in ('insert', 'delete', 'replace'))
    receipt = {
        'schemaVersion':'1.0', 'plugin':'document-compare-plugin', 'pluginVersion':'1.1.0',
        'useCase':use_case, 'mode':mode, 'surface':surface,
        'comparisonId':result['comparisonId'], 'comparisonStatus':result['status'],
        'exportStatus':manifest['status'], 'changedItems':changed,
        'sourceHashes':{'original':documents[0].get('sourceSha256'), 'candidate':documents[1].get('sourceSha256')},
        'binding':binding, 'outputs':manifest['outputs'], 'errors':manifest['errors'],
        'businessDecision':'not_made_by_plugin',
        'notice':'比对插件只产出差异与证据，不执行审批、签署或修改业务状态。文字一致不证明图像、签章、版式一致。'
    }
    write(Path(directory) / 'invocation-receipt.json', receipt)
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    try:
        request_path = Path(args.request).resolve()
        result = invoke(read(request_path), args.out, request_path.parent)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['exportStatus'] == 'complete' else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'ok':False, 'error':str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
