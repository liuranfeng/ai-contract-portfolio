---
name: tender-facts
description: Use when 原始布局已登记，需要提取招标要求、投标承诺、合同约定及逐字段证据。
metadata:
  dumate:
    displayName: "要求与承诺提取"
    summary: "要求与承诺提取，使用项目文档索引和解析器原始 layoutId 保留可回溯证据，按共享契约输出结构化结果。"
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

# 要求与承诺提取

超长输入先按 [../tender-evidence/references/long-documents.md](../tender-evidence/references/long-documents.md) 生成阅读窗口。主责引用恰好一次，上下文可复用但不重复计数；补读切分边界的表头、定义、前置范围和例外。遇到合并单元格先看原版面，不重复累加同一个数值。带修订 DOCX 按同目录 docx-revisions.md 分视图提取，不把删除/插入混排当单一承诺。

先读 ../tender-evidence/references/data-contract.md 的 facts 和 coverage 约定。
同时按 ../tender-evidence/references/expectation-review.md 建立预期事实。优先识别投标中本项目适用的具体承诺与增量承诺，不限于含“承诺”字样的段落；把历史案例、产品能力介绍、其他包件及不确定版本分清。保留所有范围和费用条件，不自动选择最严格数值作为预期。
输入 documents；输出 facts、coverage，保存提取阶段快照。

逐章节和表格处理所有布局，带上标题、定义、表头与例外上下文。每个可独立比较的行为拆为事实：质保期限、免费上门、到场时限不能揉成“售后已响应”。
fields 完整记录主体、行为、对象、范围、触发条件、数值/单位、起算事件、例外。未知为 null，不从常识填充。每个非空字段的 fieldSources 都绑定真实 SourceRef；quotes 按块逐字截取。
“市区一小时到场”保留市区与到场，“安排人员”不能改为到场。“完全响应”记录为响应事实，待关联其指向的招标要求，不能伪装为投标原文写出了两小时。
同时提取投标增量承诺、合同新增收费/限制以及冲突条款；不能只找招标已有关键词。程序性投标要求也入账，在核验时判断是否属于合同落实范围。
每个布局登记 extracted/no_relevant_fact/needs_review 和实际理由；不得自动把所有剩余块标记无关。表格只有整表 ID 时，字段证据引用整表，表头上下文保留。
运行 evidence.py validate。原文摘录无法对应、条件不明或 OCR 疑点进入待复核，不硬凑字段。
