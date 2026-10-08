# 项目快照数据契约 v1.0.0

这是七个 skills 的共享约定。示例见 [demo.json](../examples/demo.json)，机械校验以 [evidence.py](../scripts/evidence.py) 为准。脚本只检查结构与部分约束，不证明模型完成了语义核验。

## 根对象

- schemaVersion: 固定 1.0.0。
- projectId: 项目标识；不同标段单独项目或明确分组，禁止混配。
- snapshotId: 不可变快照标识。重新解析或人工修改另存新快照，记录变更原因和旧快照；不要覆盖旧产物。
- synthetic: 仅模拟样例为 true，生产数据不可假标模拟或反之。
- documents: 文档清单；documentIndex 是稳定索引，与数组位置/UI 排序无关，删除保留登记记录不复用索引。
- missingMaterials: 缺失的文件、附件、已知更正或待确认版本名称数组。
- facts: 事实数组；checks: 事项数组；coverage: 每个解析块的处理记录。

## documents[]

documentIndex 为非负整数。name、parseRunId 为非空字符串。role 为 tender/bid/contract/clarification/amendment/attachment。sourceSha256 为原件实际字节 SHA256；rawParseSha256 为原始解析 JSON 字节 SHA256。status 为 complete/incomplete。可追加 sourcePath、rawParsePath、version、parentDocumentIndex、pageNumbering、parser 等溯源字段。

layouts[] 保存 layoutId（原类型 string 或 integer）、text（解析原文）、page、bbox、type。不得把归纳结果写回 text。原始响应独立留存，必须先核对原始 ID 再导入；旧套件生成的 lay-p… 编号不能作为本套件解析器原生 ID 的证明。

脚本 import-layouts 目前支持原始 pages[].layouts[]；layoutId 与 layout_id 只做字段名映射，值和类型不变。其他接口需依据真实响应补适配器，不猜字段。页码保留返回值，明确 0/1 起算；不默默加一。空页/无文本图块需人工或适配器明确处理后再导入，默认阻断。

## SourceRef

每个引用固定为 {documentIndex, layoutId}，解析批次由当前快照 documents 中唯一绑定。
允许多个引用，禁止仅 layoutId。数值 12 与字符串 "12" 不相等。不存在或同文档重复 ID 都阻断；文档内跨页重置 ID 时不能改造 ID 绕过，需解析服务给出文档级唯一 ID 或另行确认契约。
只有整表 ID 时使用整表 ID，行列/摘录可作辅助提示，不发明 row ID 或坐标。

## facts[]

- factId: 业务事实标识，不替代原文定位。
- fields: 推荐 subject/action/object/scope/trigger/operator/value/unit/duration/startEvent/exceptions/role。未知为 null。一个事实只表达一个可比较义务，完整保留范围、起算条件和例外。
- primarySources、contextSources: SourceRef 数组，主证据非空；标题、表头、定义和例外作为上下文。
- fieldSources: 每个非 null 字段对应的 SourceRef 数组，必须在该事实已声明证据中。
- quotes: [{source: SourceRef, text: 原文逐字摘录}]。每条摘录必须是对应块 text 的非空子串；跨块拆开记录。
- 可选 review: 人工修正记录，保留原值、新值、原因、来源与时间，不修改原件。

“完全响应”事实只记录响应本身，并关联其明确指向的要求；不要把推导的两小时当成投标原文。“市区一小时”不能省掉 scope；安排人员不等于到达现场。

## checks[]

checkId、title、factIds 非空。facts 不区分来源数组存储，按 document role 与事实业务角色展示。
relations: [{fromFactId,toFactId,type,basis}]。type: responds/supplements/implements/conflicts/amends/candidate。basis 说明为什么是同一主体、对象、行为、范围的事项，或说明差异；候选不能进入最终报告。明确变更关系还需事实证据支撑，不按日期自动覆盖。

verification:
- status: pending/implemented/incorporated/partial/weakened/conflict/not_found/insufficient_materials/not_applicable。
- reason: 有范围限定的结论。
- comparedFields: 本次比较维度的字符串数组；按地域、阶段等分支分别建事项，不把不同条件合成单值。
- reviewedSources: 已实质核查的 SourceRef 数组，不允许只检索未阅读就登记。
- missingMaterials: 该事项所缺资料。
- reviewNote: 复核人员/代理实际检查的条件、附件、例外及结论说明。
- suggestion: 独立建议，不执行原合同修改；不得扩大原承诺范围。

not_found 只表示“在已核查材料中未找到落实依据”，绝不自动等于法律上未生效。第一版采用保守门控：项目存在缺件或解析不完整时禁止此状态；该状态要求核查全部合同和附件块。insufficient_materials 要列缺失/解析不完整信息。incorporated 须检查附件已提供、版本明确、纳入条款及冲突；无法证明则保持不确定。

## coverage[]

{source: SourceRef,status: extracted/no_relevant_fact/needs_review,reason: 实际处理说明}。
每个布局块单独登记，不能批量默认 no_relevant_fact。最终报告要求全部布局都有处理结果、无 needs_review、每个事实归属事项。过程快照可未完成；report 命令自动执行 final 校验。

有限范围报告的边界：缺附件且已提供材料均已可靠核验时，可以用 insufficient_materials 报告缺口；已提供材料仍有 OCR 疑点或 needs_review 时，阻断正式报告；可通过显式 --process 导出标注过程状态的文档式 HTML/Markdown、过程 JSON 和待复核清单，保留正式门控失败原因。不能将疑点改成无关来过门控。

## 向后兼容扩展（插件 1.2.0）

schemaVersion 继续为 1.0.0；以下均为可选字段，旧快照不自动推导新结论。

- documents：拆分解析的 sourceSha256 对应实际上传子 PDF，parentSourceSha256 对应未改变的业务原件；保留 parentDocumentIndex、chunkSha256、splitManifestSha256、originalPageStart/End 和显式 pageNumbering。解析返回 page 原值不改，layout.originalPage 由已校验 manifest 与明确页码基准计算。父文件可作为 sourceDocuments 归档记录；不要为了给未解析父文件凑 coverage 造空 layouts。项目内所有业务/解析索引统一预留，避免后续冲突。
- check.priorCheckIds：新主题关联的历史 checkId 数组。关联不代表每个历史结论均已重新核验，旧 check 原样保留。
- check.expectationComparison：`{expectation, contract, impact, result}`，前三项是非空分析文字，不是原文；result 显式使用 weakened/uncertain/baseline/incorporated/met/other。分别表示已证实低于预期、预期落实待确认、预期基准待澄清、已纳入、已满足、其他差异。mechanical validator 检查结构和与 verification.status 的兼容性，不能证明判断正确。weakened 只能配 weakened；met 只能配 implemented；incorporated 只能配 incorporated。未知或矛盾组合拒绝。
- reportView：`{mainCheckIds, title?, summary?, scope?}`。mainCheckIds 显式选择并排列主要事项，其他事项进入完整历史附录；空数组表示全部为历史。结果统计仅计主要主题，不推导全项目达标率。summary/scope 由实质复核者提供；选择视图不改变 coverage 或正式门控。
- reviewRun：记录 previousSnapshotId、inputSha256、methodVersion、scope、新主题/历史数量、declaredRereadUniqueBlocks。后一数字是所声明 reviewedSources 的去重数，不是机器证明已完成回读。生成工具见 review-runs.md。

比较摘要、真实原文和历史桥接均保留在同一 JSON 与 Markdown/HTML 输出，不再靠另一个脱离快照的模板替换判断。

## 原件定位集成

报告已提供解析原文块锚点跳转。宿主原件查看器应接收 projectId + snapshotId + SourceRef，用文档索引读取解析批次和 layout。普通文档使用 sourcePath 与明确基准的 page/bbox；派生 PDF 则沿 parentDocumentIndex/parentSourcePath 找未改动原件，使用经校验的 originalPage 及原坐标系 bbox。查看上传分片时才用子 sourcePath/page。禁止二次语义搜索替代定位。没有 bbox 时仅块/页定位；坐标系和旋转无法确认时不得宣称精确高亮。HTML DOM 锚点的哈希只用于页面链接，不是新增证据 ID。
