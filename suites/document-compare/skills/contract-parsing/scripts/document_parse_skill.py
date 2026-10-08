#!/usr/bin/env python3
"""Baidu PaddleOCR-VL asynchronous API, Bearer API Key only; never local OCR."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

PARSER = 'baidu-document-parser/paddle-vl'
API_KEY_URL = 'https://console.bce.baidu.com/qianfan/ais/console/apiKey'
TASK_URL = 'https://aip.baidubce.com/rest/2.0/brain/online/v2/paddle-vl-parser/task'
RUNTIME_FILE = Path(__file__).resolve().parents[1] / 'references/baidu-document-parser-runtime.json'


class ParseError(Exception):
    def __init__(self, code, message, exit_code=2):
        super().__init__(message)
        self.code, self.message, self.exit_code = code, message, exit_code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def resolve_route():
    key = os.environ.get('QIANFAN_API_KEY', '').strip()
    filename = os.environ.get('QIANFAN_API_KEY_FILE', '').strip()
    if not key and filename:
        try:
            with Path(filename).open('r', encoding='utf-8-sig') as stream:
                key = stream.read(8193).strip()
        except (OSError, UnicodeError):
            raise ParseError('api_key_file_invalid', '无法读取指定凭证文件；请检查路径和权限') from None
    if not key:
        raise ParseError('api_key_required', '请在 ' + API_KEY_URL + ' 创建具有 AI开放能力/OCR 权限的 API Key，并通过安全环境变量或凭证文件配置；禁止本地解析')
    if len(key) > 8192 or any(c.isspace() or ord(c) < 32 for c in key):
        raise ParseError('api_key_invalid', 'API Key 格式错误，请填写原始 Key，不要添加 Bearer 前缀')
    return {'mode': 'baidu-api-key', 'parser': PARSER, 'auth_source': 'qianfan_api_key',
            'url': TASK_URL, 'headers': {'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Bearer ' + key}}


def safe_route(route):
    return {'ok': True, 'status': 'runtime_configured', 'remote_verified': False,
            'mode': route['mode'], 'parser': PARSER, 'api_key_url': API_KEY_URL,
            'auth_source': 'qianfan_api_key', 'header_names': sorted(route['headers'])}


def _reject_errors(payload):
    if not isinstance(payload, dict):
        raise ParseError('invalid_parse_response', '文档解析服务返回的数据类型无效', 1)
    if payload.get('isError') is True or payload.get('success') is False or payload.get('ok') is False or payload.get('error') or payload.get('error_code') not in (None, 0):
        raise ParseError('document_parse_failed', '百度文档解析服务报告失败，请核对 Key 权限、额度及服务状态；禁止转本地解析', 1)


def _request_bytes(request, limit=64 * 1024 * 1024):
    try:
        with build_opener(NoRedirect()).open(request, timeout=120) as response:
            body = response.read(limit + 1)
            if len(body) > limit:
                raise ParseError('result_too_large', '远端返回内容超过大小限制', 1)
            return body
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise ParseError('api_key_rejected', '解析授权或结果下载权限被拒绝，请核对 API Key 权限与结果有效期') from None
        raise ParseError('backend_http_error', '百度文档解析请求返回 HTTP %s；未自动重提任务' % exc.code, 1) from None
    except (URLError, OSError, ValueError):
        raise ParseError('backend_request_failed', '请求未完成；已有任务请续查，提交状态不明时先核对用量，避免重复计费', 1) from None


def _post(route, url, form):
    request = Request(url, data=urlencode(form).encode('ascii'), method='POST', headers=route['headers'])
    try:
        value = json.loads(_request_bytes(request).decode('utf-8'))
    except (ValueError, UnicodeError):
        raise ParseError('invalid_parse_response', '服务返回非 JSON 数据', 1) from None
    _reject_errors(value)
    if not isinstance(value.get('result'), dict):
        raise ParseError('invalid_parse_response', '服务未返回有效 result', 1)
    return value['result']


def _download_url(value):
    if not isinstance(value, str):
        raise ParseError('invalid_result_url', '服务未返回有效结果下载地址', 1)
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.bcebos.com')
            or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None, 443)
            or any(ord(c) < 32 for c in value) or '\\' in value):
        raise ParseError('invalid_result_url', '只允许下载百度 BOS HTTPS 解析结果', 1)
    return value


def _parse_remote(route, source, output, digest, run_id, max_polls, resume_job):
    if not 1 <= max_polls <= 120:
        raise ParseError('invalid_poll_limit', '轮询次数必须介于 1 和 120')
    if resume_job:
        try:
            job = json.loads(Path(resume_job).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise ParseError('resume_job_invalid', '续查任务文件无效') from None
        if job.get('source_sha256') != digest or job.get('parser') != PARSER:
            raise ParseError('resume_source_mismatch', '续查任务与原始合同或解析器不匹配')
        task_id = job.get('task_id')
    else:
        task = _post(route, TASK_URL, {'file_name': source.name,
                     'file_data': base64.b64encode(source.read_bytes()).decode('ascii')})
        task_id = task.get('task_id')
    if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 512:
        raise ParseError('invalid_task_id', '服务未返回有效任务 ID', 1)
    output.mkdir(parents=True, exist_ok=True)
    job_path = output / (source.stem + '-' + run_id + '_job.json')
    with job_path.open('x', encoding='utf-8') as stream:
        json.dump({'task_id': task_id, 'parser': PARSER, 'source_sha256': digest,
                   'source_file': source.name, 'parse_run_id': run_id}, stream, ensure_ascii=False, indent=2)
    for _ in range(max_polls):
        time.sleep(5)
        result = _post(route, TASK_URL + '/query', {'task_id': task_id})
        if result.get('task_id') != task_id:
            raise ParseError('task_id_mismatch', '服务结果不属于当前任务', 1)
        status = result.get('status')
        if status in ('pending', 'processing'):
            continue
        if status == 'failed':
            raise ParseError('document_parse_failed', '远端解析失败，请核对权限、额度或文件；禁止本地解析', 1)
        if status != 'success':
            raise ParseError('invalid_task_status', '服务返回未知任务状态', 1)
        md_url = _download_url(result.get('markdown_url'))
        json_url = _download_url(result.get('parse_result_url'))
        # Never forward the service API Key to signed result URLs.
        try:
            markdown = _request_bytes(Request(md_url)).decode('utf-8-sig')
            raw = json.loads(_request_bytes(Request(json_url)).decode('utf-8-sig'))
        except (ValueError, UnicodeError):
            raise ParseError('invalid_parse_response', '结果编码或 JSON 格式不正确', 1) from None
        _reject_errors(raw)
        if not markdown.strip() or not isinstance(raw.get('pages'), list) or not raw['pages']:
            raise ParseError('incomplete_parse_result', '远端 Markdown 或页面结构缺失，不能进入审查', 1)
        return raw, task_id, markdown
    raise ParseError('parse_pending', '任务仍在排队或处理中；用 --resume-job ' + str(job_path) + ' 续查，不要重新上传', 3)


def _find_structured(value):
    _reject_errors(value)
    if any(k in value for k in ('markdown', 'pages', 'sections')):
        return value
    for key in ('data', 'result', 'output'):
        if isinstance(value.get(key), dict):
            return _find_structured(value[key])
    content = value.get('content')
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                try:
                    parsed = json.loads(item.get('text', ''))
                except (ValueError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    return _find_structured(parsed)
    raise ParseError('invalid_parse_response', '平台需返回 markdown、pages 或 sections 的结构化解析结果', 1)


def _normalize(raw):
    result = _find_structured(raw)
    pages = result.get('pages') or []
    sections = result.get('sections') or []
    markdown = result.get('markdown') or ''
    if not isinstance(pages, list) or not isinstance(sections, list) or not isinstance(markdown, str):
        raise ParseError('invalid_parse_response', '解析字段类型不符合输出契约', 1)
    normalized_pages = []
    seen_layout_ids = set()
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ParseError('invalid_parse_response', 'pages 必须包含页面对象', 1)
        page = dict(page)
        page_num = page.get('page_num', index)
        if type(page_num) is not int or page_num < 0:
            raise ParseError('invalid_parse_response', '页面编号必须是非负整数', 1)
        layouts = page.get('layouts') or []
        if not isinstance(layouts, list) or any(not isinstance(x, dict) for x in layouts):
            raise ParseError('invalid_parse_response', '页面布局格式错误', 1)
        page['page_num'] = page_num
        page['layouts'] = []
        for i, layout in enumerate(layouts):
            item = dict(layout)
            layout_id = item.get('layout_id')
            if type(layout_id) not in (str, int) or (isinstance(layout_id, str) and not layout_id.strip()):
                raise ParseError('native_layout_id_required', '缺少有效原生 layout_id；不能正式逐布局比对，禁止补造 ID', 1)
            identity = (type(layout_id), layout_id)
            if identity in seen_layout_ids:
                raise ParseError('duplicate_layout_id', '同一文档的原生 layout_id 重复，不能唯一定位布局', 1)
            seen_layout_ids.add(identity)
            original_text = item.get('text', '')
            if not isinstance(original_text, str):
                raise ParseError('invalid_parse_response', '布局文本必须是字符串', 1)
            item.setdefault('text_raw', original_text)
            if item.get('type') == 'table':
                tables = page.get('tables') or []
                if not isinstance(tables, list):
                    raise ParseError('invalid_parse_response', '页面表格格式错误', 1)
                table = next((t for t in tables if isinstance(t, dict) and t.get('layout_id') == item['layout_id']), None)
                if table:
                    item['text'] = table.get('markdown') or table.get('table_html') or item.get('text', '')
            text = item.get('text', '')
            if not isinstance(text, str):
                raise ParseError('invalid_parse_response', '布局文本必须是字符串', 1)
            item.setdefault('type', 'text')
            page['layouts'].append(item)
        normalized_pages.append(page)
    if not markdown.strip():
        chunks = [layout.get('text', '') for page in normalized_pages for layout in page['layouts']]
        if not any(chunks):
            chunks = [p.get('text', '') for p in pages]
        if not any(chunks):
            chunks = [s.get('text', '') for s in sections if isinstance(s, dict)]
        markdown = '\n\n'.join(c for c in chunks if isinstance(c, str) and c.strip())
    if not markdown.strip():
        raise ParseError('empty_parse_result', '解析服务没有返回合同正文', 1)
    # One exact text section preserves offsets without inventing OCR geometry.
    text_sections = [{'id': 'document', 'title': '合同正文', 'start_char': 0,
                      'end_char': len(markdown), 'char_count': len(markdown), 'text': markdown}]
    layout_available = any(l.get('text', '').strip() for p in normalized_pages for l in p['layouts'])
    return markdown, normalized_pages, text_sections, layout_available


def _safe_archive(value, secret='', path='$', redacted=None):
    """Copy service JSON, preserving structure except credentials and signed URLs."""
    if redacted is None:
        redacted = []
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            field = re.sub(r'[^a-z0-9]', '', key.lower())
            child = path + '.' + key
            if field in {'authorization', 'apikey', 'accesskey', 'secretkey', 'accesstoken',
                         'refreshtoken', 'idtoken', 'password', 'credential', 'credentials',
                         'cookie', 'setcookie', 'signature', 'securitytoken'}:
                result[key] = '[REDACTED]'
                redacted.append(child)
            else:
                result[key], _ = _safe_archive(item, secret, child, redacted)
        return result, redacted
    if isinstance(value, list):
        return [_safe_archive(item, secret, path + '[' + str(i) + ']', redacted)[0]
                for i, item in enumerate(value)], redacted
    if isinstance(value, str):
        clean = value.replace(secret, '[REDACTED]') if secret else value
        def redact_url(match):
            url = match.group(0)
            try:
                parsed = urlsplit(url)
                if parsed.query or parsed.username or parsed.password:
                    return '[REDACTED_URL]'
            except ValueError:
                return '[REDACTED_URL]'
            return url
        clean = re.sub(r'https?://[^\s<>"\']+', redact_url, clean)
        if clean != value:
            redacted.append(path)
        return clean, redacted
    return value, redacted


def parse_file(source_path, workspace_path, engine='base', max_polls=120, resume_job=None):
    source = Path(source_path).resolve()
    if not source.is_file():
        raise ParseError('source_missing', '待解析的原始附件不存在')
    if engine != 'base':
        raise ParseError('pipeline_not_configured', '极速 pipeline 接口尚未确认，不能自动换用其他服务；请选择 base 或补充接口约定')
    if source.suffix.lower() not in ('.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.ofd', '.doc', '.docx', '.txt', '.wps', '.ppt', '.pptx'):
        raise ParseError('unsupported_file_type', '该文件格式不在官方接口支持范围，请提供受支持的原始合同；禁止本地提取')
    limit = 10 if source.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff') else 50
    if source.stat().st_size == 0 or source.stat().st_size > limit * 1024 * 1024:
        raise ParseError('file_size_invalid', '文件为空或超出直接上传大小限制，请提供符合官方限制的文件')
    route = resolve_route()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    output = Path(workspace_path).resolve()
    run_id = uuid.uuid4().hex
    raw, task_id, remote_markdown = _parse_remote(route, source, output, digest, run_id, max_polls, resume_job)
    secret = route.get('headers', {}).get('Authorization', '').removeprefix('Bearer ')
    raw, redacted = _safe_archive(raw, secret)
    remote_markdown, markdown_redacted = _safe_archive(remote_markdown, secret, '$downloaded_markdown')
    stem = source.stem + '-' + run_id
    raw_path = output / (stem + '_raw_parse.json')
    raw_bytes = (json.dumps(raw, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with raw_path.open('xb') as stream:
        stream.write(raw_bytes)
    # Archive precedes validation: an invalid native layout response remains inspectable.
    markdown, pages, sections, has_layout = _normalize(dict(raw, markdown=remote_markdown))
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise ParseError('source_changed', '原始附件在解析期间发生变化，请重新解析')
    md_path, json_path = output / (stem + '_parsed.md'), output / (stem + '_parsed.json')
    md_bytes = markdown.encode('utf-8')
    metadata = {'schema_version': '2.0', 'source_file': source.name, 'source_kind': 'file_attachment',
                'source_sha256': digest, 'parse_run_id': run_id, 'parser': PARSER,
                'raw_parse_file': raw_path.name, 'raw_parse_sha256': hashlib.sha256(raw_bytes).hexdigest(),
                'archive_redacted_paths': redacted + markdown_redacted,
                'auth_source': 'qianfan_api_key', 'parse_status': 'success', 'task_id': task_id, 'engine': engine,
                'markdown_file': md_path.name, 'markdown_sha256': hashlib.sha256(md_bytes).hexdigest(),
                'pages': pages, 'sections': sections, 'layout_available': has_layout}
    # Exclusive files prevent overwriting other batch members; JSON is the completion marker.
    with md_path.open('xb') as stream:
        stream.write(md_bytes)
    try:
        with json_path.open('x', encoding='utf-8') as stream:
            json.dump(metadata, stream, ensure_ascii=False, indent=2)
    except Exception:
        md_path.unlink(missing_ok=True)
        raise
    return {'ok': True, 'mode': 'baidu-api-key', 'markdown': str(md_path),
            'metadata': str(json_path), 'raw_parse': str(raw_path), 'layout_available': has_layout}


def main():
    parser = argparse.ArgumentParser(description='API Key 鉴权调用百度 PaddleOCR-VL 异步解析')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    sub.add_parser('route')
    command = sub.add_parser('parse')
    command.add_argument('--file', required=True)
    command.add_argument('--workspace', required=True)
    command.add_argument('--engine', choices=['base', 'pipeline'], default='base')
    command.add_argument('--max-polls', type=int, default=120)
    command.add_argument('--resume-job')
    args = parser.parse_args()
    try:
        result = parse_file(args.file, args.workspace, args.engine, args.max_polls, args.resume_job) if args.command == 'parse' else safe_route(resolve_route())
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ParseError as exc:
        print(json.dumps({'ok': False, 'error': exc.code, 'message': exc.message}, ensure_ascii=False))
        return exc.exit_code
    except Exception:
        print(json.dumps({'ok': False, 'error': 'unexpected_error', 'message': '解析失败，请检查运行环境'}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
