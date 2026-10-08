# 分批核验、主题复核与历史追溯

超长文件先读 long-documents.md，按模型处理批次逐块登记 coverage。检索用于召回候选，不能把搜索命中等同于回读证据；数量齐全不证明语义核验完成。某批次失败保留未完成状态，只续跑失败批次，不将剩余内容默认标成无关。

## 本轮主题与历史判断

重新按“合同不及预期”复核时，逐主题实质回读原文、条件和纳入条款，形成新 checkId；用 priorCheckIds 记录对应的历史事项。可复用旧事实证据，但旧判断、原件、原始解析和 coverage 不覆盖。新主题数量不是独立风险数量，归并到主题不表示所有历史事项均被重新审查。

宿主模型提供完整的新增 facts/checks，包含真实 reviewedSources、reason、reviewNote 和独立 suggestion。机械工具不从标题或关键词生成判断：

```text
python <套件>/skills/tender-evidence/scripts/review_run.py old.json review-patch.json <新复核目录>
python <套件>/skills/tender-evidence/scripts/evidence.py report <新复核目录>/snapshot.json <新报告目录> --process
```

review-patch.json：snapshotId（新值）、scope（实际回读范围）、facts（新增事实或空数组）、checks（新增主题数组），可选 title、summary、methodVersion。新增事项可引用旧 factId；新增 factId/checkId 不得复用。每个新 check 可带 priorCheckIds（历史 checkId 数组）和 expectationComparison（见 data-contract.md）。

输出 snapshot.json、prior-review-bridge.json、review-manifest.json，后者记录输入和补丁摘要、正式门控失败项、历史保留数量和所声明的回读块数。append 工具不会清除旧 needs_review，也不授予正式交付资格。修复 OCR 或版本证据应先另存修正快照，保留修改原因，再启动本轮复核。

## 事实粒度与主题粒度

一个主题可以关联多个原子事实，但事实仍按行为、范围、触发、期限、免费范围、例外拆开。原文大块作为 sourceStatement 可用于复核证据展示，不能以此宣称已经完成逐义务结构化提取。条件不同须分支比较，不以最严格数值拼成原文不存在的承诺。

典型检查：送货与验收、答复处理结果与初次响应、平均年龄与逐人年龄上限、最低人数与授权裁员、备用比例与新增采购、历史能力与本项目专用投入。累计表格跨页出现同一个合并单元格时核对原版面再计数。DOCX 修订另读 docx-revisions.md。

## 交付范围

报告同时说明：收到哪些文件、缺什么材料、多少本轮主题、哪些原文实际回读、保留多少历史记录、剩余多少 OCR/版本疑点。缺独立招标文件仍可核对投标明确承诺，但不宣称覆盖全部招标要求。结构校验、语义复核、浏览器截图、PDF 外观检查分别留证，不互相替代。
