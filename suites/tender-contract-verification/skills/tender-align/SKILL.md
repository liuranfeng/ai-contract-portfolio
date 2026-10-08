---
name: tender-align
description: Use when 已有多文档事实，需要挂接同一核验事项或核对响应与补充关系。
metadata:
  dumate:
    displayName: "跨文档事项关联"
    summary: "跨文档事项关联，使用项目文档索引和解析器原始 layoutId 保留可回溯证据，按共享契约输出结构化结果。"
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

# 跨文档事项关联

跨分片、跨阅读窗口关联时，按父业务文档和原始页码找上下文，证据引用仍保留子 documentIndex 与原生 layoutId；详见 [../tender-evidence/references/long-documents.md](../tender-evidence/references/long-documents.md)。重复读取不是新事实，相似标题不是同一义务。重新归并主题使用 priorCheckIds 桥接旧事项，不能覆盖历史判断或仅凭顺序连线。

先读 ../tender-evidence/references/data-contract.md 的 checks/relations。
输入 facts；输出 checks 的 factIds 和 relations，不提前生成确定结论。

按 ../tender-evidence/references/expectation-review.md，以适用的要求和投标承诺建立核验事项，再向合同正文及附件追踪。投标增量必须独立可追溯；没有找到合同对应事实的承诺也保留事项，不能因为无法配对而丢失。合同反查用于发现新增限制及对预期的影响，不取代承诺向合同的主线。

用条款引用、事项名、型号参数、关键词和语义找候选，再核对主体、对象、行为、范围、阶段、条件。每条关系填写 basis，不能以“相似度高”代替关联依据。
支持一对多、多对多：合同正文、技术协议和附件可能共同落实一项要求。投标增量承诺、合同新增条款也建立事项，所有事实都要归属，包括不适用事项。
分地域/阶段建立比较分支：市区一小时与其他地区两小时不合并。电话响应、安排人员、到达现场分开。只有局部重叠时明确重叠范围。
补遗、澄清、变更关系必须有明确对应事实；不按时间自动覆盖。不确定的关系保留 candidate，送复核；最终报告前必须确认或拆开，不丢掉难匹配事实。
运行 evidence.py validate，检查事实外键和关系端点。
