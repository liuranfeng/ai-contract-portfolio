#!/usr/bin/env python3
"""Validate a parsing result against its original attachment and Markdown."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def probe(verbose=True):
    spec = importlib.util.spec_from_file_location('document_parser', Path(__file__).with_name('document_parse_skill.py'))
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    try:
        detail = parser.safe_route(parser.resolve_route())
        code = 0
    except parser.ParseError as exc:
        code, detail = 2, {'ok': False, 'error': exc.code, 'message': exc.message}
    if verbose:
        print(json.dumps(detail, ensure_ascii=False))
    return code, detail


def verify(parsed_json_path, source_path=None, require_layout=False):
    try:
        path = Path(parsed_json_path)
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('invalid object')
    except (OSError, ValueError):
        return 2, {'ok': False, 'error': 'parsed_json_invalid'}
    fails = []
    if data.get('source_kind') != 'file_attachment':
        fails.append('附件门控不接受产物自行声明为粘贴文本')
    if data.get('parser') != 'baidu-document-parser/paddle-vl' or data.get('auth_source') != 'qianfan_api_key':
        fails.append('必须为 API Key 鉴权的百度 PaddleOCR-VL 解析产物')
    if not isinstance(data.get('task_id'), str) or not data['task_id'].strip():
        fails.append('缺少远端异步解析任务 ID')
    if data.get('parse_status') != 'success':
        fails.append('解析服务未成功')
    if not isinstance(data.get('parse_run_id'), str) or not data['parse_run_id'].strip():
        fails.append('缺少解析批次')
    raw_name = data.get('raw_parse_file')
    if not isinstance(raw_name, str) or not raw_name or '/' in raw_name or '\\' in raw_name or ':' in raw_name:
        fails.append('原始解析归档路径无效')
    else:
        raw_path = path.parent / raw_name
        if not raw_path.is_file() or data.get('raw_parse_sha256') != hashlib.sha256(raw_path.read_bytes()).hexdigest():
            fails.append('原始解析归档缺失或摘要不匹配')
    source = Path(source_path) if source_path else None
    if source is None or not source.is_file():
        fails.append('必须提供原始附件以核对来源')
    elif data.get('source_sha256') != hashlib.sha256(source.read_bytes()).hexdigest():
        fails.append('解析结果与原始附件摘要不匹配')
    name = data.get('markdown_file')
    if not isinstance(name, str) or not name or '/' in name or '\\' in name or ':' in name:
        fails.append('Markdown 关联路径无效')
    else:
        markdown = path.parent / name
        if not markdown.is_file():
            fails.append('Markdown 双输出缺失')
        else:
            content = markdown.read_bytes()
            if not content.strip() or data.get('markdown_sha256') != hashlib.sha256(content).hexdigest():
                fails.append('Markdown 正文为空或摘要不匹配')
            try:
                text = content.decode('utf-8')
                sections = data.get('sections')
                if not isinstance(sections, list) or not sections or not all(isinstance(s, dict) for s in sections):
                    fails.append('章节数据缺失')
                elif ''.join(s.get('text', '') for s in sections) != text:
                    fails.append('章节文本与 Markdown 不一致')
            except (UnicodeDecodeError, TypeError):
                fails.append('正文或章节编码格式错误')
    if require_layout:
        pages = data.get('pages')
        valid_pages = isinstance(pages, list) and all(isinstance(p, dict) and isinstance(p.get('layouts'), list) for p in pages)
        layouts = [l for p in pages for l in p['layouts']] if valid_pages else []
        valid_layouts = all(isinstance(l, dict) for l in layouts)
        ids = [l.get('layout_id') for l in layouts] if valid_layouts else []
        valid_ids = all(type(i) in (str, int) and (not isinstance(i, str) or i.strip()) for i in ids)
        unique = valid_ids and len(ids) == len({(type(i), i) for i in ids})
        if not ids or not unique or data.get('layout_available') is not True:
            fails.append('逐布局比对所需原生唯一 ID 不足，不能补造 ID')
    return (1, {'ok': False, 'fails': fails}) if fails else (0, {'ok': True, 'source_verified': True, 'layout_required': require_layout})


def main():
    parser = argparse.ArgumentParser(description='解析附件一致性门控')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('probe')
    p.add_argument('--quiet', action='store_true')
    p = sub.add_parser('verify')
    p.add_argument('parsed_json')
    p.add_argument('--source', required=True)
    p.add_argument('--require-layout', action='store_true')
    args = parser.parse_args()
    if args.command == 'probe':
        code, _ = probe(not args.quiet)
    else:
        code, detail = verify(args.parsed_json, args.source, args.require_layout)
        print(json.dumps(detail, ensure_ascii=False))
    return code


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
