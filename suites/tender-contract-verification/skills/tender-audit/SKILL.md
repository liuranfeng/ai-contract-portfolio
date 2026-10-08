---
name: tender-audit
description: Use when 初步交叉核验已完成，需要复核条件丢失、证据遗漏和报告交付资格。
metadata:
  dumate:
    displayName: "证据与结论复核"
    summary: "证据与结论复核，使用项目文档索引和解析器原始 layoutId 保留可回溯证据，按共享契约输出结构化结果。"
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

# 证据与结论复核

超长资料复核同时核对拆分 manifest、逐页映射、批次原生 ID、窗口唯一主责及 deferredContextRefs 是否补读；见 [../tender-evidence/references/long-documents.md](../tender-evidence/references/long-documents.md)。主题复核按同目录 review-runs.md 核对新旧桥接、回读范围与历史保留。DOCX 原始/接受修订视图及最终版本确认各自留证。报告与 PDF 的截图检查不能替代此处语义复核；未完成项保持 needs_review/过程门控。

先读 ../tender-evidence/references/data-contract.md。输入完整项目快照；输出修正后的新快照、实际 reviewNote 和剩余缺件。

按 ../tender-evidence/references/expectation-review.md 复核预期方向：是否遗漏投标增量、以招标下限替代投标承诺、拿历史能力当本项目承诺、把低下限当作取消高承诺、把文字冲突当成已证实损失。逐项检查“低于预期”是否有同条件证据以及对纳入和例外的实质复核；不确定时保留待确认，不批量改标签。

逐事项沿 Check → Fact → {documentIndex,layoutId} 回读主证据和上下文，检查：是否串文档；解析批次是否对应；事实字段是否有据；地域、触发、起算、免费范围、例外是否完整；关系是否同一义务。
特别复核四类压力：不同文件同 ID；市区条件变成全域；缺附件误判未落实；整表 ID 伪造行 ID。复核建议条款同样不得扩大承诺。
逐块检查 coverage 是否真实，不只看计数。not_found 必须全查合同/附件且无缺件；材料不足保留不确定。报告要保留正常事项，不能只展示风险导致覆盖不可核。
将实质复核过程填写 reviewNote，随后运行 evidence.py validate <快照> --final。失败返回对应技能修复；不能通过改状态、空泛复核说明或伪造覆盖记录绕过。
机器校验只证明引用与字段的部分一致性，不证明结论语义正确。人工纠正保存旧值与证据，另存快照。
