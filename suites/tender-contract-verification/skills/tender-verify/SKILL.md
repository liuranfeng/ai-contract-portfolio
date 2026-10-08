---
name: tender-verify
description: Use when 需要判断合同是否低于招标要求和投标承诺形成的预期，识别承诺遗漏、削弱、条件变化及落实不确定性。
metadata:
  dumate:
    displayName: "承诺落实交叉核验"
    summary: "承诺落实交叉核验，使用项目文档索引和解析器原始 layoutId 保留可回溯证据，按共享契约输出结构化结果。"
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

# 承诺落实交叉核验

主题复核按 [../tender-evidence/references/review-runs.md](../tender-evidence/references/review-runs.md) 另存。记录 expectationComparison 的预期、合同、影响和明确结果；保留 verification 的实质证据及状态，两者矛盾由机械校验拒绝。修订版及最终签署版本按同目录 docx-revisions.md 分开，不能以“接受修订视图”证明最终确认。单块超长或缺跨页上下文时先补读，不用摘要替代核验。

先读 ../tender-evidence/references/data-contract.md 的 verification 状态与门控。
输入 checks/facts/documents；输出每事项 verification。

先按 ../tender-evidence/references/expectation-review.md 核对预期基准。主问题是“合同是否兑现本项目的具体承诺”，尤其是投标增量。verification.reason 写清预期及来源、合同约定、差距与交付影响、纳入/例外核查、结论与不确定性；不能只报文字不同。满足招标下限不能替代投标承诺落实。

分别比较招标到投标、投标到合同、招标到合同，并从合同反查新增收费/免责/型号替换。不要只检查是否达到招标最低要求，投标额外五年承诺落成三年也是差异候选。
先对齐范围、主体、行为、起算点、单位与例外，再比较数值；单位转换保留原值与转换过程，无法确定不换算。“及时”不能直接当作满足两小时。
记录 comparedFields、reviewedSources 与 reason。reviewedSources 只登记真正阅读过的块。
状态选择：implemented 明确落实；incorporated 附件引用落实且附件可核；partial 部分；weakened 缩水/条件模糊；conflict 冲突；not_found 已核查材料未找到；insufficient_materials 材料不足；not_applicable 非合同落实事项；pending 待核。
未检出时全查合同正文、附件、技术协议、引用条款和例外。缺附件或解析不完整用 insufficient_materials，列缺件；不得判确定未落实。incorporated 要有纳入条款和附件内容证据，不能仅凭“详见附件”。
建议单独写入 suggestion，保留原承诺的地域/条件/例外；不修改原合同，不机械选择最严格值。争议效力、法条适用另行核实，不把文本差异说成当然违法。
