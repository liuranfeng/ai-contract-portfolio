"""Render schema 1.0 comparisons as an offline, safe three-pane document view.

document_display is a local copy from tender-evidence/scripts/document_display.py.
Only presentation is performed here: semantic decisions always come from the input.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("_compare_document_display", _HERE / "document_display.py")
_display = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_display)

OPERATIONS = {"equal": "字面一致", "insert": "右侧新增", "replace": "右侧修改", "delete": "右侧删除"}
SEMANTICS = {"equal": "语义一致 · 字面相同", "equivalent": "改写一致", "changed": "含义变化", "uncertain": "语义不确定", "pending": "语义待判定", "not_requested": "未请求语义判断"}


def _e(value):
    return html.escape(str(value), quote=True)


def _validate(result):
    if result.get("schemaVersion") != "1.0":
        raise ValueError("HTML renderer requires schemaVersion 1.0")
    if result.get("mode") not in {"character", "semantic"} or result.get("surface") not in {"reading", "raw"}:
        raise ValueError("Invalid mode or surface")
    docs = result.get("documents", [])
    if len(docs) != 2 or any(d.get("documentIndex") != i for i, d in enumerate(docs)):
        raise ValueError("Exactly two ordered documents are required")
    seen = [[], []]
    ids = set()
    for alignment in result.get("alignments", []):
        if not isinstance(alignment.get("id"), str) or alignment["id"] in ids:
            raise ValueError("Alignment IDs must be unique strings")
        ids.add(alignment["id"])
        if alignment.get("operation") not in OPERATIONS:
            raise ValueError("Invalid operation")
        if not alignment.get("left") and not alignment.get("right"):
            raise ValueError("An alignment must have at least one side")
        for side, key in enumerate(("left", "right")):
            indices = alignment.get(key, [])
            layouts = docs[side].get("layouts", [])
            if any(type(i) is not int or not 0 <= i < len(layouts) for i in indices):
                raise ValueError("Alignment layout index out of bounds")
            seen[side].extend(indices)
            text = alignment.get(key + "Text")
            field = "readingText" if result["surface"] == "reading" else "text"
            expected = "\n".join(layouts[i].get(field, layouts[i].get("text", "")) for i in indices)
            if not isinstance(text, str) or text != expected:
                raise ValueError("Alignment text must match its selected surface")
        left_end = right_end = 0
        for op in alignment.get("charOps", []):
            values = [op.get(k) for k in ("leftStart", "leftEnd", "rightStart", "rightEnd")]
            if op.get("op") not in OPERATIONS or any(type(v) is not int for v in values):
                raise ValueError("Invalid character opcode")
            a, b, c, d = values
            if a != left_end or c != right_end or not a <= b <= len(alignment["leftText"]) or not c <= d <= len(alignment["rightText"]):
                raise ValueError("Character opcodes must cover ordered Unicode code-point ranges")
            if op["op"] == "equal" and alignment["leftText"][a:b] != alignment["rightText"][c:d]:
                raise ValueError("Equal opcode contains different text")
            if op["op"] == "insert" and (a != b or c == d):
                raise ValueError("Insert opcode must have an empty left range")
            if op["op"] == "delete" and (c != d or a == b):
                raise ValueError("Delete opcode must have an empty right range")
            if op["op"] == "replace" and (a == b or c == d):
                raise ValueError("Replace opcode must contain text on both sides")
            left_end, right_end = b, d
        if left_end != len(alignment["leftText"]) or right_end != len(alignment["rightText"]):
            raise ValueError("Incomplete character opcodes")
    for side in (0, 1):
        if seen[side] != list(range(len(docs[side].get("layouts", [])))):
            raise ValueError("Alignments must cover every layout in reading order exactly once")


def _semantic(alignment, mode):
    if mode != "semantic":
        return "not_requested", ""
    semantic = alignment.get("semantic") or {}
    status = semantic.get("status", "pending")
    reason = semantic.get("reason") or ""
    if alignment["operation"] == "equal":
        status = "equal"
    elif status not in {"equivalent", "changed", "uncertain"} or not reason.strip():
        status = "pending"
    return status, reason


def _mapped_render(raw, source, changed):
    """Map only proven equal characters between source and safe visible text.

    If any changed character is absent/ambiguous, mark nothing in the structure.
    The exact unmodified source is always available in the separate char view.
    """
    node = _display.tree(raw)
    visible = _display.plain(node)
    if not changed:
        return _display.serialize(node), True
    if source == visible:
        return _display.serialize(node, changed), True
    # Repeated strings can create several possible anchors. Only accept a unique
    # complete visible string after ignoring structural whitespace. This maps
    # HTML block separators and table tabs without inventing content positions.
    source_chars = [(c, i) for i, c in enumerate(source) if not c.isspace()]
    visible_chars = [(c, i) for i, c in enumerate(visible) if not c.isspace()]
    if [c for c, _ in source_chars] != [c for c, _ in visible_chars]:
        return _display.serialize(node), False
    mapping = {a[1]: b[1] for a, b in zip(source_chars, visible_chars)}
    targets = []
    for lo, hi in changed:
        if any(source[i].isspace() for i in range(lo, hi)):
            return _display.serialize(node), False
        targets.extend(mapping[i] for i in range(lo, hi) if i in mapping)
    if not targets:
        return _display.serialize(node), False
    ranges = []
    for position in sorted(set(targets)):
        if ranges and ranges[-1][1] == position:
            ranges[-1] = (ranges[-1][0], position + 1)
        else:
            ranges.append((position, position + 1))
    return _display.serialize(node, ranges), True


def _char_view(alignment, side):
    key = ("left", "right")[side]
    source = alignment[key + "Text"]
    rendered = []
    for op in alignment["charOps"]:
        content = _e(source[op[key + "Start"]:op[key + "End"]])
        rendered.append(content if op["op"] == "equal" else '<mark class="change-' + op["op"] + '">' + content + '</mark>')
    return "".join(rendered) or '<span class="empty-text">此侧无文字</span>'


def _block(result, alignment, side, number):
    key = ("left", "right")[side]
    operation = alignment["operation"]
    indices = alignment[key]
    classes = "alignment operation-" + operation
    title = _e(alignment["id"])
    if not indices:
        phrase = "此处新增 · 原件无对应内容" if side == 0 else "此处删除 · 比对件无对应内容"
        return f'<section class="{classes} placeholder" id="a{number}-{key}" data-alignment="{number}" aria-label="{title}，{phrase}"><span class="placeholder-rule"></span><p>{phrase}</p><small>{title} · 阅读序列占位</small></section>'
    blocks, offset, all_mapped = [], 0, True
    for index in indices:
        layout = result["documents"][side]["layouts"][index]
        raw = layout.get("text", "")
        source = layout.get("readingText", raw) if result["surface"] == "reading" else raw
        changes = []
        for op in alignment["charOps"]:
            if op["op"] != "equal":
                lo, hi = max(offset, op[key + "Start"]), min(offset + len(source), op[key + "End"])
                if lo < hi:
                    changes.append((lo - offset, hi - offset))
        if operation in {"insert", "delete"} and changes:
            node = _display.tree(raw)
            rendered, mapped = _display.serialize(node, [(0, len(_display.plain(node)))]), True
        else:
            rendered, mapped = _mapped_render(raw, source, changes)
        all_mapped = all_mapped and mapped
        ref = 'layoutId ' + _e(json.dumps(layout.get("layoutId"), ensure_ascii=False))
        page = "页码未提供" if layout.get("page") is None else "解析页码 " + _e(layout["page"])
        blocks.append(f'<div class="layout" data-layout-index="{index}"><div class="layout-meta"><span>{page}</span><span>{ref}</span></div><div class="document-content">{rendered or "<p class=empty-text>此布局无可显示文字</p>"}</div><details class="raw-source"><summary>原始解析文本</summary><pre>{_e(raw)}</pre></details></div>')
        offset += len(source) + 1
    notice = '' if all_mapped else '<p class="mapping-note">正文字符位置无法精确映射；请展开完整字符对照查看本项差异。</p>'
    char_panel = '' if operation == "equal" else f'<details class="char-panel"><summary>完整字符对照 <span>按输入字符范围</span></summary><pre>{_char_view(alignment, side)}</pre></details>'
    unresolved = '<span class="status-label uncertain">对齐待复核</span>' if alignment.get("alignmentStatus") == "unresolved" else ''
    return f'<section class="{classes}" id="a{number}-{key}" data-alignment="{number}" aria-label="{title}"><div class="alignment-label"><span>{title}</span>{unresolved}</div>{"".join(blocks)}{notice}{char_panel}</section>'


def render_html(result, output_path):
    """Write a complete standalone HTML comparison and return its Path."""
    _validate(result)
    mode = result["mode"]
    alignments = result["alignments"]
    differences = {i for i, a in enumerate(alignments) if a["operation"] != "equal" or a.get("alignmentStatus") == "unresolved"}
    counts = {op: sum(a["operation"] == op for a in alignments) for op in OPERATIONS}
    pending = sum(_semantic(a, mode)[0] in {"pending", "uncertain"} or a.get("alignmentStatus") == "unresolved" for a in alignments)
    list_items = []
    payload = []
    for i, alignment in enumerate(alignments):
        semantic, reason = _semantic(alignment, mode)
        payload.append({"id": alignment["id"], "operation": alignment["operation"], "semantic": semantic, "leftText": alignment["leftText"], "rightText": alignment["rightText"], "charOps": alignment["charOps"], "unresolved": alignment.get("alignmentStatus") == "unresolved"})
        if i not in differences:
            continue
        badge = f'<span class="status-label {semantic}">{SEMANTICS[semantic]}</span>' if mode == "semantic" else ''
        reason_html = '<p class="semantic-reason">' + _e(reason or ("等待宿主模型结合两侧内容与上下文判定。" if semantic == "pending" else "")) + '</p>' if mode == "semantic" else ''
        unresolved = '<p class="alignment-warning">对齐待复核，位置仅表示当前候选关系。</p>' if alignment.get("alignmentStatus") == "unresolved" else ''
        list_items.append(f'<li class="diff-entry" data-index="{i}"><button type="button" class="diff-select" data-select="{i}" aria-controls="a{i}-left a{i}-right" aria-label="定位差异 {_e(alignment["id"])}"><span class="diff-top"><span class="change-label {alignment["operation"]}">{OPERATIONS[alignment["operation"]]}</span><span class="diff-id">{_e(alignment["id"])}</span></span><span class="diff-preview" data-preview="{i}">{_e((alignment["rightText"] or alignment["leftText"])[:100])}</span><span class="select-hint">定位两侧正文 <span aria-hidden="true">↗</span></span></button>{badge}{reason_html}{unresolved}<details class="diff-full"><summary>展开完整差异文字</summary><div class="full-label">原件</div><pre>{_char_view(alignment, 0)}</pre><div class="full-label">比对件</div><pre>{_char_view(alignment, 1)}</pre></details></li>')
    columns = []
    for side in (0, 1):
        document = result["documents"][side]
        name = document.get("name", ("原件", "比对件")[side])
        content = ''.join(_block(result, alignment, side, i) for i, alignment in enumerate(alignments))
        content = content or '<div class="document-empty"><h2>文档没有文本布局</h2><p>当前解析结果为空，请核对原件与解析范围。</p></div>'
        columns.append(f'<section class="document-pane pane-{side}" aria-label="{("原件", "比对件")[side]}"><header class="pane-heading"><span class="eyebrow">{("01 / 原件", "02 / 比对件")[side]}</span><h2 title="{_e(name)}">{_e(name)}</h2><span class="layout-count">{len(document.get("layouts", []))} 个原文块</span></header><div class="document-scroll" id="scroll-{side}" tabindex="0" aria-label="{("原件", "比对件")[side]}独立滚动区域"><div class="document-paper">{content}</div></div></section>')
    warnings = result.get("warnings", [])
    warning_html = '<details class="warnings"><summary>' + str(len(warnings)) + ' 项解析／比对提示</summary><ul>' + ''.join('<li>' + _e(w if isinstance(w, str) else json.dumps(w, ensure_ascii=False)) + '</li>' for w in warnings) + '</ul></details>' if warnings else ''
    needs_review = pending or result.get("status") == "needs_review"
    mode_label = "语义比对" if mode == "semantic" else "字符比对"
    status_label = "含待复核内容" if needs_review else "比对完成"
    surface_label = "可阅读文本" if result["surface"] == "reading" else "原始解析文本"
    empty_list = '<li class="empty-state"><h3>未发现字面差异</h3><p>两侧文字一致。图像、签章等非文字内容仍需查看原件。</p></li>' if not differences else ''
    asset_dir = _HERE.parent / "assets"
    css = (asset_dir / "compare.css").read_text(encoding="utf-8")
    js = (asset_dir / "compare.js").read_text(encoding="utf-8")
    # A hash-based CSP permits only this renderer's script. Embedded evidence is
    # serialized as inert JSON and '<' is escaped to prevent closing script tags.
    import base64
    digest = base64.b64encode(hashlib.sha256(js.encode("utf-8")).digest()).decode("ascii")
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    document_html = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-{digest}'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"><title>文档比对 · {_e(result["documents"][0].get("name", "原件"))}</title><style>{css}</style></head>
<body><header class="app-header"><div class="brand"><span class="brand-mark" aria-hidden="true">＝</span><div><h1>文档比对</h1><p>原件 → 比对件</p></div></div><div class="run-info"><span class="mode-pill">{mode_label}</span><span class="run-status {"review" if needs_review else "complete"}">{status_label}</span><span class="surface-note">按{surface_label}比较</span></div></header>
<div class="summary-bar"><p><strong>{len(differences)}</strong> 项待浏览差异 <span class="summary-divider">/</span> <span class="legend insert">新增 {counts["insert"]}</span><span class="legend replace">修改 {counts["replace"]}</span><span class="legend delete">删除 {counts["delete"]}</span>{f'<span class="pending-count">待复核 {pending}</span>' if pending else ''}</p><span class="keyboard-note">Alt + ↑ / ↓ 切换差异</span></div>{warning_html}
<noscript><p class="noscript-note">脚本未启用；全文与差异可展开阅读，双侧定位和连线不可用。</p></noscript>
<main class="comparison" id="comparison">{columns[0]}<div class="connector-gutter" aria-hidden="true"></div>{columns[1]}<aside class="diff-pane" aria-label="差异清单"><header class="diff-heading"><div><span class="eyebrow">03 / 差异清单</span><h2>逐项查看<span id="visible-count">{len(differences)}</span></h2></div><div class="navigation"><button id="previous" type="button" aria-label="上一项差异">↑</button><button id="next" type="button" aria-label="下一项差异">↓</button></div></header><div class="filter-row"><label for="diff-filter">显示</label><select id="diff-filter"><option value="all">全部差异</option><option value="insert">右侧新增</option><option value="replace">右侧修改</option><option value="delete">右侧删除</option>{'<option value="pending">语义待判定／不确定</option><option value="equivalent">改写一致</option>' if mode == 'semantic' else ''}<option value="unresolved">对齐待复核</option></select></div><div class="diff-scroll" tabindex="0" aria-label="差异清单独立滚动区域"><ol id="diff-list">{''.join(list_items)}{empty_list}</ol><p class="filter-empty" id="filter-empty" hidden>当前筛选没有差异。</p></div><footer class="diff-footer"><span id="position-label">点击一项，同时定位两侧</span><span>虚线表示当前对齐关系</span></footer></aside><svg class="connectors" id="connectors" aria-hidden="true"></svg></main>
<div id="announcement" class="sr-only" aria-live="polite"></div><script id="comparison-data" type="application/json">{data}</script><script>{js}</script></body></html>'''
    output = Path(output_path)
    if output.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("Output must have an .html or .htm suffix")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document_html, encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="schema 1.0 comparison JSON")
    parser.add_argument("output", type=Path, help="new standalone HTML path")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output paths must differ")
    result = json.loads(args.input.read_text(encoding="utf-8-sig"))
    print(render_html(result, args.output))


if __name__ == "__main__":
    main()
