---
name: tender-report
description: Use when 需要生成文档式详细核验报告，展示事实差异、原文 Diff、关系连线与证据定位，或导出待复核过程报告。
metadata:
  dumate:
    displayName: "核验报告交付"
    summary: "核验报告交付，使用项目文档索引和解析器原始 layoutId 保留可回溯证据，按共享契约输出结构化结果。"
    publisher: "自定义安装"
    icon: "assets/icon.png"
    publishedAt: 1788998400000
    version: "1.2.1"
    level: L3
    category: 行业服务
    tags: ["合同核验", "招投标", "证据定位"]
    sensitive: true
    allow_implicit_invocation: true
    review:
      status: pending
---

# 核验报告交付

先读 ../tender-evidence/references/data-contract.md 和 parser-integration.md（同 references 目录）。
按同目录 expectation-review.md，以“合同不及预期”及“预期落实待确认”为主要发现。上部结论应能看出预期来源（尤其投标承诺）、合同落实、差距影响及不确定性。一般文字差异保留但不宣称预期损失；不可只在展示层将历史 partial/conflict 批量改为已证实缩水。若快照缺这些实质判断，返回 tender-verify/audit 补核另存快照，不能由报告脚本猜测。
输入通过 final 校验的 JSON 快照。使用 ../tender-evidence/scripts/evidence.py report <快照> <新输出目录>，自动重新执行交付门控。

交付项目 JSON、report.md、report.html，保留原件和原始解析归档位置。报告按核验事项展示状态、比较理由、逐字段事实、关系依据、主证据/上下文、缺件、复核与独立建议。正常、未找到、无法判断都保留。
HTML 默认采用文档式长报告（assets/report.css）：上半部列出已登记的事实差异、冲突与待确认事项；下半部逐事项展示核验结论、逐字段事实、并排原文 Diff、关系连线和关联上下文。不要改回侧栏工作台。正常事项完整保留；条款与背景记录放入可展开附录，不全部当作独立冲突计数。

连线只渲染 checks.relations 中记录的关系，保留 basis；未配对事实独立展示，不凭排序自动连线。候选关系用虚线且不能进入正式报告。上下文虚线仅表示事实引用，不自动等于承诺纳入合同。字面 Diff 与核验判断分开，长文本采用按行 Diff；两侧文件角色按实际来源显示。

证据链接由复合定位点派生，点击展开并高亮完整原文块，保留文档名、documentIndex、原类型 layoutId、解析批次及已有原始页码。不要宣称实现 PDF 原件坐标高亮；原件查看器需宿主接入。默认打印正文与正文上下文，历史与完整原文附录保持折叠；用户指定完整打印时才展开全部。
打开报告检查中文、证据链接、长表格和窄屏阅读；无浏览器时可验证 HTML 链接完整性并明确未做视觉验证。证据展示使用 document_display.py 将 Markdown 表格、标题、列表与允许的静态 HTML 排为可读文档，不执行脚本、事件或远程资源。布局原文和逐字摘录不变，来源索引同时保留折叠的原始解析文本。无法恢复的图像显示明确占位，不把签名地址或 HTML 标签铺在正文中。保留模拟样例标识。
需要本轮主题报告、渲染图、PDF、超长打印或重试时，读 [references/render-and-print.md](references/render-and-print.md)。使用 scripts/export_report.cjs 和 scripts/verify_pdf.py；保留来源与输出哈希，逐项说明机械校验和视觉检查结果。主题与历史选择由 reportView 明示，比较由 expectationComparison 明示；不得靠修改标签代替复核。只截图不等于导出 PDF 成功，正文打印不等于全部附录已打印。
缺件报告说明实际核验范围；不宣布项目全量完成。有 OCR 疑点或 needs_review 时，使用 `evidence.py report <快照> <新输出目录> --process` 导出标注“过程报告”的 Markdown/HTML、原快照副本和 manifest，保留待复核块及正式门控失败原因。该模式仍须通过基础结构及证据引用校验，不修改源快照、不绕过正式门控。修复后不加 --process 重新出正式报告。外发、签署或直接修改合同不属于本技能动作。
