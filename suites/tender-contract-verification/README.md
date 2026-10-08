# 招投标合同核验套件 v1.2.1

独立 DuMate Skill 组合包，含七个 skills：tender-review 总入口、tender-evidence 原文证据、tender-facts 事实提取、tender-align 事项关联、tender-verify 落实核验、tender-audit 复核、tender-report 报告。

主审查目标：合同是否低于有依据的预期。预期包含招标要求及投标中的具体承诺、增量承诺，不能仅以满足招标最低要求结束核验。v1.2.0 将真实测试中验证的长文档、版本、主题复核、文档式报告和打印策略回流到七个 skills 及可复用脚本；不会自动重分类既有快照。

通过 .claude-plugin/plugin.json 声明主入口及 skills；按 DuMate 自定义套件导入流程导入本目录或 ZIP。当前未执行 DuMate 真机安装/联调。

核心数据：项目快照 → 核验事项 → 事实 → {documentIndex, layoutId} → 解析原文块。文档索引稳定，layoutId 保留解析器原值，缺失或同文档重复时拒绝。核心校验/报告/阅读规划使用 Python 标准库（3.10+）；PDF 拆分需要 pypdf，PDF 检查还需要 pypdfium2；截图与 PDF 导出需要 Node.js 22+ 和本地 Chromium/Chrome/Edge。

先读 skills/tender-review/SKILL.md。共享数据契约、解析接入方法、运行命令和模拟 JSON 均在 skills/tender-evidence 下。工具提供布局导入、引用校验、原文查询和 Markdown/HTML 报告。语义提取与核验由 skills 指导宿主模型完成，脚本不会自动调用模型。

模拟验证：运行 evidence.py validate examples/demo.json --final，再运行 evidence.py report examples/demo.json <新目录>，路径均相对于 skills/tender-evidence。新增 examples/expectation-demo.json 演示显式主题选择与预期比较字段。测试：python -m unittest discover -s skills/tender-evidence/scripts -p "test_*.py"。

报告采用文档式长报告：上部展示主要预期差距与待确认事项，下部逐事项展示预期/合同/影响、并排原文 Diff、真实关系连线和上下文；完整原文及历史记录保留在附录。reportView 和 expectationComparison 显式描述本轮范围与比较，生成器不猜结论。默认打印正文及必要上下文，完整附录打印需显式选择。

有 OCR 疑点时显式运行 `evidence.py report project.json <新目录> --process`，生成标注过程状态的报告，保留未解决块及正式门控失败原因。不加该参数仍执行原有 final 门控。每次输出 report.html、report.md、project.json 和 report-manifest.json，后者记录源快照和报告摘要。展示与打印不改变事实、历史判断或门控。

解析边界：需要宿主提供原始解析响应和原件；此包不自带生产 API 客户端或密钥。当前导入格式为 pages[].layouts[]，其他真实格式需添加适配。旧合同套件可能补造 layout_id，不能直接当作原生证据。HTML 提供解析块回看与高亮，PDF 原件坐标高亮需要宿主查看器集成。

安装包不含客户材料、密钥或个人工作区。示例为模拟，不代表法律意见、解析服务测试或模型准确率评测。JSON 是权威交换数据；第一版未引入 SQLite，避免两套数据状态不一致。

## 策略与工具入口

| 情形 | 插件内入口 |
|---|---|
| 文件超限、按实际字节自适应分片、原始页码映射、无漏页重页、跨页表格 | skills/tender-evidence/references/long-documents.md；scripts/document_chunks.py 的 split/verify/map-layouts |
| 模型输入过长、唯一主责、上下文复用与延后补读 | 同一工具 chunk-plan；不截断超长原文块 |
| DOCX 修订混排、原始/接受修订/最终版本不明 | skills/tender-evidence/references/docx-revisions.md |
| OCR 缓存、异步任务恢复、提交结果不明、秘密不入产物 | long-documents.md；由宿主现有解析能力执行，不自带生产客户端 |
| 投标具体/增量承诺，条件、纳入和反证核查 | skills/tender-evidence/references/expectation-review.md |
| 主题重审、不可变历史、新旧桥接、范围说明 | skills/tender-evidence/references/review-runs.md；scripts/review_run.py |
| 文档式报告、Diff、线与原文、正文/完整打印、失败处理 | skills/tender-report/references/render-and-print.md |
| 渲染图与 PDF，输出哈希及交互检查 | skills/tender-report/scripts/export_report.cjs |
| PDF 重开、逐页机械检查、抽查图 | skills/tender-report/scripts/verify_pdf.py |

上述 scripts 路径相对于其所属 skill。各命令均支持 --help，输出使用新目录/文件，避免覆盖旧证据。

## 离线验证

```text
python -m unittest discover -s skills/tender-evidence/scripts -p "test_*.py"
python -m unittest discover -s skills/tender-report/scripts -p "test_*.py"
node --test skills/tender-report/scripts/test_export_report.cjs
node skills/tender-report/scripts/export_report.cjs --html <报告>/report.html --out <新导出目录> --screenshots --pdf
```

测试包含模拟数据，不打包客户报告。边界：不宣称 DuMate 真机已联调、OCR 语义百分百准确或全部附录已默认打印。分卷打印提供策略，当前 CLI 不自动分卷；原件坐标高亮仍需宿主查看器。

1.2.1：阅读层将 Markdown/静态 HTML 转换为文档排版，保留原始解析文本折叠回溯；突出预期差距和合同对照。缺少归档图像时显示原件提示，禁止加载签名链接；不声称像素级还原。
