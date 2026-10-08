"""Offline renderer contract, evidence preservation, and injection tests."""
import copy
import difflib
import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_html.py"
spec = importlib.util.spec_from_file_location("render_compare_html", SCRIPT)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class Inspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.ids = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if "id" in attrs:
            self.ids.append(attrs["id"])

    def handle_data(self, data):
        self.text.append(data)


def fixture():
    result = {"schemaVersion": "1.0", "mode": "semantic", "surface": "reading", "comparisonId": "simulated-html-fixture", "status": "needs_review", "documents": [{"documentIndex": 0, "name": "原件 · 模拟服务协议.docx", "parseRunId": "simulated-left", "layouts": []}, {"documentIndex": 1, "name": "比对件 · 模拟服务协议.docx", "parseRunId": "simulated-right", "layouts": []}], "alignments": [], "summary": {}, "warnings": ["模拟数据，仅验证展示；未连接 DuMate 或真实解析器。", "图片与签章须查看原件，文字一致不代表图像一致。"], "coverage": {"left": 1, "right": 1}}

    def add(left, right, status="pending", reason="", ids=None, unresolved=False):
        num = len(result["alignments"])
        ids = ids or ("z-" + str(90 - num), "a-" + str(99 - num))
        indices = [[], []]
        texts = []
        for side, blocks in enumerate((left, right)):
            blocks = [] if blocks is None else blocks
            for raw, reading in blocks:
                layouts = result["documents"][side]["layouts"]
                indices[side].append(len(layouts))
                layouts.append({"layoutId": ids[side] if len(blocks) == 1 else str(ids[side]) + "-" + str(len(indices[side])), "ordinal": len(layouts), "page": num + 1, "type": "text", "text": raw, "readingText": reading, "bbox": None})
            texts.append("\n".join(reading for _, reading in blocks))
        operation = "insert" if not left else "delete" if not right else "equal" if texts[0] == texts[1] else "replace"
        ops = [{"op": tag, "leftStart": a, "leftEnd": b, "rightStart": c, "rightEnd": d} for tag, a, b, c, d in difflib.SequenceMatcher(None, *texts, autojunk=False).get_opcodes()]
        refs = [[{"documentIndex": side, "layoutId": result["documents"][side]["layouts"][i]["layoutId"]} for i in indices[side]] for side in (0, 1)]
        result["alignments"].append({"id": "D" + str(num + 1).zfill(4), "left": indices[0], "right": indices[1], "operation": operation, "alignmentStatus": "unresolved" if unresolved else "aligned", "leftText": texts[0], "rightText": texts[1], "charOps": ops, "leftRefs": refs[0], "rightRefs": refs[1], "semantic": {"status": "equal" if operation == "equal" else status, "reason": reason}})

    add([("# 技术服务协议\n本示例为离线验证用模拟材料。", "技术服务协议\n本示例为离线验证用模拟材料。")], [("# 技术服务协议\n本示例为离线验证用模拟材料。", "技术服务协议\n本示例为离线验证用模拟材料。")])
    add([("## 一、服务期限\n服务期限为三年，自验收通过之日起计算。", "一、服务期限\n服务期限为三年，自验收通过之日起计算。")], [("## 一、服务期限\n服务期限为五年，自验收通过之日起计算。", "一、服务期限\n服务期限为五年，自验收通过之日起计算。")], "changed", "服务期限从三年改为五年，双方履行义务的持续时间发生变化。")
    add([("<h2>二、付款安排</h2><table><tr><th>阶段</th><th>支付比例</th></tr><tr><td>验收完成</td><td>30%</td></tr></table>", "二、付款安排\n阶段\t支付比例\n验收完成\t30%")], [("<h2>二、付款安排</h2><table><tr><th>阶段</th><th>支付比例</th></tr><tr><td>验收完成</td><td>50%</td></tr></table>", "二、付款安排\n阶段\t支付比例\n验收完成\t50%")], "pending")
    add(None, [("## 三、资料交付\n乙方应在验收后五个工作日内移交全部技术资料。", "三、资料交付\n乙方应在验收后五个工作日内移交全部技术资料。")], "changed", "比对件增加了资料移交义务及五个工作日的期限。")
    add([("## 四、专属许可\n甲方享有成果的排他使用权。", "四、专属许可\n甲方享有成果的排他使用权。")], None, "uncertain", "比对件删除专属使用约定，需结合其他知识产权条款确认影响。")
    add([("## 五、通知方式\n通知应以书面形式送达。", "五、通知方式\n通知应以书面形式送达。")], [("## 五、通知方式\n应通过书面方式送达通知。", "五、通知方式\n应通过书面方式送达通知。")], "equivalent", "双方均要求通知以书面形式送达；该句的义务主体、方式与动作一致。")
    add([("服务标识 🧪 𠀀 甲", "服务标识 🧪 𠀀 甲")], [("服务标识 🧪 𠀀 乙", "服务标识 🧪 𠀀 乙")], unresolved=True)
    add([("分段内容第一部分。", "分段内容第一部分。"), ("分段内容第二部分。", "分段内容第二部分。")], [("分段内容第一部分。\n分段内容第二部分。增加说明。", "分段内容第一部分。\n分段内容第二部分。增加说明。")])
    return result


class RendererTests(unittest.TestCase):
    def render(self, result):
        with tempfile.TemporaryDirectory() as directory:
            path = renderer.render_html(result, Path(directory) / "comparison.html")
            return path.read_text(encoding="utf-8")

    def test_complete_standalone_safe_document_structure_and_all_anchors(self):
        result = fixture()
        output = self.render(result)
        parsed = Inspector()
        parsed.feed(output)
        self.assertEqual(len(parsed.ids), len(set(parsed.ids)))
        self.assertEqual(2, sum(tag == "table" for tag, _ in parsed.tags))
        for i in range(len(result["alignments"])):
            for side in ("left", "right"):
                self.assertIn(f"a{i}-{side}", parsed.ids)
        self.assertIn("此处新增 · 原件无对应内容", output)
        self.assertIn("此处删除 · 比对件无对应内容", output)
        self.assertIn("解析页码 1", output)
        self.assertIn('connect-src \'none\'', output)
        self.assertTrue(all("src" not in attrs and "href" not in attrs for _, attrs in parsed.tags))
        self.assertIn("Array.from(alignment[key + 'Text'])", output)
        self.assertNotIn("scrollIntoView", output)

    def test_semantic_status_not_inferred_from_character_similarity(self):
        result = fixture()
        output = self.render(result)
        self.assertIn("改写一致", output)
        self.assertIn("语义待判定", output)
        self.assertIn("含义变化", output)
        self.assertIn("语义不确定", output)
        self.assertIn("完整字符对照", output)
        self.assertEqual(("pending", ""), renderer._semantic({"operation": "replace", "semantic": {"status": "equivalent"}}, "semantic"))
        self.assertEqual(("pending", "未经判定"), renderer._semantic({"operation": "replace", "semantic": {"status": "equal", "reason": "未经判定"}}, "semantic"))

    def test_character_mode_does_not_claim_semantic_findings(self):
        result = fixture()
        result["mode"] = "character"
        output = self.render(result)
        self.assertNotIn("改写一致", output)
        self.assertNotIn("语义待判定", output)
        self.assertIn("字符比对", output)

    def test_injections_are_inert_in_document_json_and_names(self):
        result = fixture()
        attack = '<h2 onclick="evil()">标题</h2><script>window.injected=1</script><img src="https://bad.invalid/x" onerror="evil()" alt="图像"><a href="javascript:evil()">链接</a><iframe src="https://bad.invalid">坏内容</iframe><svg onload="evil()">svg</svg>'
        layout = result["documents"][0]["layouts"][0]
        layout["text"] = attack
        result["documents"][0]["name"] = '</title><script>alert(1)</script>'
        result["alignments"][1]["semantic"]["reason"] = '</script><script>alert(2)</script>'
        output = self.render(result)
        parsed = Inspector()
        parsed.feed(output)
        scripts = [attrs for tag, attrs in parsed.tags if tag == "script"]
        self.assertEqual(2, len(scripts))
        self.assertFalse(any(tag in {"img", "iframe", "object", "embed", "a"} for tag, _ in parsed.tags))
        self.assertFalse(any(any(k.startswith("on") for k in attrs) for _, attrs in parsed.tags))
        self.assertIn("原文图像", output)
        self.assertIn("&lt;script&gt;window.injected=1&lt;/script&gt;", output)

    def test_astral_characters_use_python_codepoints(self):
        alignment = fixture()["alignments"][6]
        right = renderer._char_view(alignment, 1)
        self.assertIn('🧪 𠀀 <mark class="change-replace">乙</mark>', right)
        rendered, exact = renderer._mapped_render("🧪甲𠀀", "🧪甲𠀀", [(1, 2)])
        self.assertTrue(exact)
        self.assertIn("🧪<mark>甲</mark>𠀀", rendered)

    def test_structural_mapping_is_conservative(self):
        rendered, exact = renderer._mapped_render("<p>甲</p><p>乙</p>", "甲\n乙", [(2, 3)])
        self.assertTrue(exact)
        self.assertIn("<mark>乙</mark>", rendered)
        rendered, exact = renderer._mapped_render("<p>甲</p><p>乙</p>", "甲\n乙", [(1, 2)])
        self.assertFalse(exact)
        self.assertNotIn("<mark>", rendered)
        rendered, exact = renderer._mapped_render("<p>完全不同</p>", "甲乙", [(0, 1)])
        self.assertFalse(exact)

    def test_long_layout_keeps_complete_text_and_raw(self):
        result = fixture()
        long_text = "超长正文" * 20000 + "终点验证𠀀"
        layout = result["documents"][0]["layouts"][0]
        layout["text"] = layout["readingText"] = long_text
        layout = result["documents"][1]["layouts"][0]
        layout["text"] = layout["readingText"] = long_text
        alignment = result["alignments"][0]
        alignment["leftText"] = alignment["rightText"] = long_text
        alignment["charOps"] = [{"op": "equal", "leftStart": 0, "leftEnd": len(long_text), "rightStart": 0, "rightEnd": len(long_text)}]
        output = self.render(result)
        self.assertGreaterEqual(output.count(long_text), 4)

    def test_no_input_mutation(self):
        result = fixture()
        before = copy.deepcopy(result)
        self.render(result)
        self.assertEqual(before, result)

    def test_coverage_and_opcode_errors_rejected(self):
        result = fixture()
        result["alignments"][1]["left"] = [0]
        with self.assertRaises(ValueError):
            self.render(result)
        result = fixture()
        result["alignments"][6]["charOps"][-1]["rightEnd"] += 1
        with self.assertRaises(ValueError):
            self.render(result)

    def test_native_layout_ids_do_not_reorder_content(self):
        result = fixture()
        output = self.render(result)
        self.assertLess(output.index('id="a1-left"'), output.index('id="a2-left"'))
        self.assertIn('data-layout-index="', output)

    def test_entire_insert_and_delete_keep_structural_color(self):
        result = fixture()
        inserted = renderer._block(result, result["alignments"][3], 1, 3)
        deleted = renderer._block(result, result["alignments"][4], 0, 4)
        self.assertIn("<mark>三、资料交付</mark>", inserted)
        self.assertIn("<mark>四、专属许可</mark>", deleted)
        self.assertNotIn("无法精确映射", inserted + deleted)

    def test_empty_documents_render_clear_state(self):
        result = fixture()
        result["alignments"] = []
        for doc in result["documents"]:
            doc["layouts"] = []
        output = self.render(result)
        self.assertIn("文档没有文本布局", output)
        self.assertIn("未发现字面差异", output)


if __name__ == "__main__":
    unittest.main()
