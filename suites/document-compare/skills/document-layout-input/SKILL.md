---
name: document-layout-input
description: Use when 需要导入带原生 layout_id 或 layoutId 的文档解析 JSON，准备左右文档比对，或复用已有与模拟预解析数据。
metadata:
  dumate:
    displayName: "布局导入"
    summary: "按原生布局 ID 和阅读顺序导入两份文档。"
    publisher: "文档比对套件"
    icon: "assets/icon.png"
    publishedAt: 1789430400000
    version: "1.1.0"
    level: L3
    category: 行业服务
    tags: ["文档比对", "布局", "JSON"]
    sensitive: false
    allow_implicit_invocation: true
    review:
      status: pending
---

## 输入与身份

使用 contract-parsing 同一脚本产生的 `*_parsed.json`，也接受用户已有的含布局解析 JSON。非空预解析结果可以直接复用，无需重新上传；用户允许的模拟 fixture 必须保留模拟来源说明。原始附件需要解析时才运行 contract-parsing，不创建第二套 OCR 或 adapter。

导入器位于 `../document-compare/scripts/compare.py`。原件是 documentIndex=0，比对件是 documentIndex=1。`documentIndex + layoutId` 是引用身份；layoutId 必须原样保留服务字符串/整数及类型。缺失、空白或重复 ID 不能正式逐 layout 比对，禁止以数组索引、文本哈希、UUID 或 AI 补号。

## 导入

在插件目录执行，使用上一步实际返回的 metadata 路径。真实批次沿用输入；`--parse-run-id` 仅填已知真实批次，不编造云端任务号。

```bash
python skills/document-compare/scripts/compare.py import --input "<左侧parsed.json>" --document-index 0 --name "原件" --output "<left.json>" --source "<原始附件>"
python skills/document-compare/scripts/compare.py import --input "<右侧parsed.json>" --document-index 1 --name "比对件" --output "<right.json>" --source "<比对附件>"
python skills/document-compare/scripts/compare.py compare --left "<left.json>" --right "<right.json>" --mode character --output "<result.json>"
```

已有解析 JSON 或模拟 fixture 未提供原件时可以省略 `--source`，如实保留来源限制，不能声称已核对原件 SHA-256。提供原件时由核心计算并核对摘要。使用原始服务 raw JSON 时保留其实际解析批次；有配套 parsed 元数据则优先导入元数据以保留原件摘要与归档关联。

## 阅读顺序与显示

页面保持服务数组顺序。页内有完整、唯一的服务 reading_order/readingOrder 时核心采用该明确顺序，否则保持 layouts 数组顺序；导入后的 ordinal 是规范阅读序列的零基索引。页码仅用于显示，不能按页码、ID 字典顺序或坐标自行重排。原始归档不重排。一对多或多对一对齐由 document-compare 决定，不在导入时拼接或删掉布局。

表格 text 使用解析脚本按原生 ID 关联的 Markdown/HTML，readingText 是核心生成的可阅读纯文本；raw surface 保留原始 text 表达，禁止把 HTML 标签误报为文字内容。原始结构、表格、text_raw、坐标、解析批次和原件摘要保留为证据。缺少坐标时不补造。

## Fallback Behavior

ID、结构、批次或摘要异常时使用核心的实际报错，修复来源或重新取得合格解析结果。保留原 JSON；不手写“成功”的规范化结果掩盖缺项。

## Examples

“已有两份带 layout_id 的 JSON，只做字符比对”：直接分别导入为 0 和 1 后执行 compare。“JSON 的 page_num 是 3、1、2”：保持其原数组顺序，页码照实显示。
