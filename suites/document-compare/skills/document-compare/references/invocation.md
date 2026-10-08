# 标准调用与签前比对

插件独立于合同生命周期，可由 DuMate 对话随时调用，也可由业务系统编排调用同一 CLI。没有依赖 V7、某个合同项目的页面或某个合同项目的固定路径。此接口为本地请求文件契约，不宣称已部署远程 HTTP API。

## 使用场景

- `standalone`：任意阶段比较两份材料，不要求审批记录，不改变业务流程状态。
- `pre_sign`：原件固定为审批通过文件，比对件为待签署文件。必须绑定审批、版本与文件摘要，默认输出真实 Word 修订；不能把“最新清稿”当作“审批通过版”。

两个场景均区分 `character` 和 `semantic`。签前通常先完整保留字符差异，再按需要进行语义判断；语义相同不删除字符修订。原件非 DOCX 时明确说明不能保留原件 Word 版式，按 Word 编辑技能由用户选择重建，禁止静默降级。

## 请求

`parsedPath` 是复用解析技能得到的 `pages[].layouts[]` 原始解析文件。路径相对请求 JSON；提供源文件时解析结果必须包含匹配的 `source_sha256`。已有解析结果不重复上传。解析摘要缺失时回到解析归档核对，不允许当前包装器自造解析成功状态。

```json
{
  "schemaVersion": "1.0",
  "useCase": "pre_sign",
  "mode": "character",
  "surface": "reading",
  "original": {"name": "审批通过版", "parsedPath": "approved-parsed.json", "sourcePath": "approved.docx"},
  "candidate": {"name": "待签署版", "parsedPath": "candidate-parsed.json", "sourcePath": "candidate.docx"},
  "context": {
    "contractId": "调用方的合同ID",
    "approvalId": "调用方的审批记录ID",
    "approvedVersionId": "调用方固定的审批通过版本",
    "approvedSourceSha256": "审批通过文件的实际SHA256"
  },
  "outputs": ["tracked", "html"]
}
```

独立调用改为 `useCase=standalone` 并省略 context；输出可以选择 `tracked`、`html`、`report-docx`、`report-pdf`。可选 `alignmentPath`（全量单调对齐）、`mappingPath`（Word 原生位置映射）、`semanticDecisionsPath`（绑定 comparisonId 的宿主语义结论）。格式参见既有交换契约。

```text
python skills/document-compare/scripts/invoke.py --request request.json --out fresh-output-directory
```

产出包括 comparison.json、选定文件、export-manifest.json、invocation-receipt.json。接入方读取 receipt 中的 comparisonStatus、exportStatus、outputs、binding；出现 partial 或 needs_review 时保留原因，不展示为全部完成。

## 与业务流的边界

插件输出差异及原文证据，`businessDecision=not_made_by_plugin`。签署放行、差异接受、回审和重新审批由合同系统的用户决策与制度控制，不能由插件依据差异数量自动决定。receipt 中的 approvalId 是调用方传入的关联信息；生产审批真实性需调用方认证，摘要校验本身不是身份或授权证明。

Word 按审批通过的 DOCX 作底稿生成 w:ins/w:del；拒绝全部修订对应审批基准，接受全部修订对应待签署文本。原件不覆盖，签署文件不用带审阅修订的交付稿替代。非文本、图片、签章、复杂格式及不支持结构遵守 Word 编辑技能的门控与披露。

用户随时调用同一个插件不会触发签署，不会让当前合同审批自动失效；仅在用户明确选择关联某一流程后，由业务系统把回执挂到对应版本。
