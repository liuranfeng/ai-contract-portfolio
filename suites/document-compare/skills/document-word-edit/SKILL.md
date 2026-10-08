---
name: document-word-edit
description: Use when the user requests a Word document with accepted or rejected tracked changes, 保留原件版式的修订 Word, or explicitly labelled reconstruction from parsed text.
metadata:
  dumate:
    displayName: "文档比对 Word 修订"
    summary: "在原始 DOCX 中保留样式与表格并生成真实修订；无法定位时明确报告，解析文本重建须显式选择。"
    publisher: "自定义安装"
    icon: "assets/icon.png"
    publishedAt: 1789444800000
    version: "1.1.0"
    level: L0
    category: 行业服务
    tags: ["文档比对", "Word", "修订"]
    sensitive: true
    allow_implicit_invocation: true
    review:
      status: pending
---

# 原件 Word 修订

输入为 [统一比对结果](../document-compare/references/data-contract.md)。此交付物是带真实 `w:ins` 和 `w:del` 的 DOCX。独立说明报告使用 `document-diff-report`；三栏网页使用 `document-diff-html`。三个输出独立选择。

先用 `document-compare` 校验结果 JSON。读取原 DOCX，只向新路径输出；运行时需要 `lxml`，重建还需要 `python-docx`。宿主提供 bundled Python 时优先使用该解释器。本脚本不接云 OCR、不调用模型。

```python
write_redline(result, source_docx, output_path, mapping=None, reconstructed=False)
```

函数在 [write_redline.py](scripts/write_redline.py)，返回 manifest，同时保存 `输出.docx.manifest.json`。

```text
python scripts/write_redline.py result.json --source-docx original.docx --output tracked.docx
python scripts/write_redline.py --inspect original.docx
python scripts/write_redline.py result.json --source-docx original.docx --mapping mapping.json --output tracked.docx
```

自动定位要求全文唯一且精确匹配；重复文本不能凭相似度或顺序猜测。检查 `--inspect` 输出后，以原生 `layoutId` 写显式映射，所有序号均从零开始：

```json
{"layoutMap":[
  {"layoutId":"native-paragraph","part":"word/document.xml","paragraphIndex":0},
  {"layoutId":"native-table","tableIndex":0}
]}
```

整表 readingText 用制表符分列、换行分行，支持结构不变的逐单元格修订。单元格原生布局可用 `tableIndex,rowIndex,cellIndex,cellParagraphIndex`；段落组可用 `paragraphIndices`，以换行连接后须逐字匹配该原生布局。不要为定位方便伪造或拆分 layoutId。插入边界跨表格／正文时，以 `insertions:{"D0002":{"part":"word/document.xml","beforeParagraphIndex":2}}` 明确位置；也可用 `afterParagraphIndex`。

既有修订须先由用户明确基准版本并另存，不能自动接受后继续。文字未覆盖、定位错误、域／超链接／图片所在复杂段落修改、整表新增删除、合并单元格及表结构变化等不支持情况会失败；保留但未比对的页眉页脚等部件列入 manifest。图片原样保留不代表图像一致。

只有用户明确选择解析文本重建时使用 `--reconstructed`，可不传原 DOCX。文件永久标题含“由解析文本重建”，manifest 标注 `mode=reconstructed`。重建不能宣称保留原 PDF 或 Word 版式。

完成时检查 manifest 中拒绝修订等于基准、接受修订等于目标、目标布局独立校验均通过。原件模式保留源 ZIP 的未修改部件字节。对代表性样例运行 [测试](tests/test_redline.py)。使用宿主文档渲染器渲染并逐页检查；无法渲染时查看日志并明确写“已做结构与文本验证，未完成 Word 视觉验收”，不得把 XML 检查称作视觉验收。
