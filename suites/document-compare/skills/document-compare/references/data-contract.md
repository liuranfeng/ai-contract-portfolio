# 文档比对交换契约

schemaVersion 为 1.0。比较方向固定 left 原件 → right 比对件，绿色 insert，黄色 replace，红色 delete。交付选项独立：tracked DOCX、三栏 HTML、report DOCX/PDF，可多选。

JSON 结构：
```
{
  "schemaVersion":"1.0", "mode":"character|semantic", "surface":"reading|raw",
  "comparisonId":"sha256...", "status":"complete|needs_review",
  "documents":[
    {"documentIndex":0,"name":"原件","parseRunId":"...","sourceSha256":"...或null",
     "rawParseSha256":"...","layouts":[
       {"layoutId":"原生ID（string或int）","ordinal":0,"page":1,"type":"text",
        "text":"解析原文（不改）","readingText":"可阅读纯文本","bbox":null}
     ]},
    {"documentIndex":1,"name":"比对件", "layouts":[...]}
  ],
  "alignments":[
    {"id":"D0001","left":[0],"right":[0],"operation":"replace",
     "alignmentStatus":"aligned|unresolved","leftText":"三年","rightText":"五年",
     "leftRefs":[{"documentIndex":0,"layoutId":"..."}],"rightRefs":[...],
     "charOps":[{"op":"replace","leftStart":0,"leftEnd":1,"rightStart":0,"rightEnd":1},...],
     "semantic":{"status":"not_requested|pending|equal|equivalent|changed|uncertain","reason":"..."}
    }
  ],
  "summary":{"equal":0,"insert":0,"delete":0,"replace":1,"pending":0},
  "warnings":[], "coverage":{"left":1,"right":1}
}
```

left/right 为 documents[0/1].layouts 的零基索引，单调递增、全覆盖、不重复。一对多/多对一允许。空侧为纯新增/删除，用该空侧在阅读序列中的相邻项作 UI 插入占位，不捏造 layoutId。leftText/rightText 是按 surface 取各 layout 内容，使用换行拼接；charOps 包含 equal 在内的完整 difflib Unicode code-point 范围，不是 JS UTF-16 范围。原件含图片时不能由文字相等推断图像相同。

semantic 模式仍保留全部字符差异。字符相同可记录 equal；其余必须有宿主模型对两侧及上下文给出的证据理由，否则 pending，绝不按字符串相似度宣布语义一致。字符模式语义为 not_requested。模型提交 decisions.json：{comparisonId, decisions:[{id,status:equivalent|changed|uncertain,reason,leftQuote,rightQuote}]}。quote 是对应 text 的非空原文子串，空侧 quote 为空。缺少判定保持 pending。

Word 原件修订与比对报告区分：前者保留原 DOCX 的段落、表格、样式并生成 OOXML w:ins/w:del，后者是独立报告。现有修订、不能明确定位、图形等无法可靠编辑的内容必须列出或拒绝，不能悄悄重建原文冒充原件修订。只在明确选择 reconstructed 时从解析文本重建；对所有生成修订验证拒绝修订=基准、接受修订=目标，原文件不覆盖。

核心 CLI 在 skills/document-compare/scripts/compare.py。renderer 函数 render_html(result, output_path) 位于 skills/document-diff-html/scripts/render_html.py。Word/报告导出脚本归属于 skills/document-word-edit 与 skills/document-diff-report；直接读取此 JSON，不重新判定。SDK 不自动连接模型、解析或外部资源。
