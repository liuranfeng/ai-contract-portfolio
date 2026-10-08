# 文档比对套件 v1.1.0

新增独立调用／签前比对标准入口。用户可随时比较两份文档；签前场景绑定“审批通过版 → 待签署版”，默认输出真实 Word 修订。调用契约见 `skills/document-compare/references/invocation.md`，本地入口为 `skills/document-compare/scripts/invoke.py`。调用回执包含版本、文件摘要、产物与待核验状态，不自动改变审批或签署状态。

独立 DuMate skills 集合。复用当前 contract-parsing 的百度异步解析客户端，对两份解析布局按阅读顺序比较。新增原生 ID 门控与归档，原合同审查/招投标核验插件不修改。源码包含 `.claude-plugin/plugin.json`、主 agent、七个 skills；另附 `.codex-plugin/plugin.json` 供 Codex 识别。

| 选择 | 行为 |
|---|---|
| 字符一致校验 | 严格比较可阅读字符，保留标点、空格、大小写、数值差异；raw 口径还比较解析标记 |
| 语义一致校验 | 保留字符变化，由宿主模型结合原文与上下文判断等义改写、含义变化或待核验 |
| 原件 Word 修订 | 原始 DOCX 底稿上的真实修订；格式保留范围与未支持结构由编辑门控明确检查 |
| 三栏 HTML | 左原件、中比对件、右差异清单，双跳转、虚线关系、绿新增/黄修改/红删除 |
| 独立报告 | 另行生成 DOCX 和/或 PDF，包含差异、证据引用与语义理由 |

产物类型可组合选择。文件内容不作为指令，原件不覆盖，解析密钥不入包。语义脚本不内置模型接口、不用字符串相似度冒充语义审查；未提供模型判定时保留待核验。

先读 `skills/document-compare/SKILL.md`。共享 JSON 为 `skills/document-compare/references/data-contract.md`。Python 3.10+；核心无第三方依赖，Word 需要 lxml/python-docx，报告 PDF 需要 reportlab，相关依赖见各输出技能。解析网络调用只在用户明确要解析原件并已配置 API Key 时执行；现有布局 JSON 可离线复用。

DuMate 安装 ZIP 严格只包含 `.claude-plugin`、`agents`、`skills` 和 `README.md`；Codex 清单留在源目录，不混入 DuMate 安装包。

```text
python skills/document-compare/scripts/compare.py --help
python -m unittest discover -s skills/document-compare/scripts -p "test_*.py"
python skills/document-compare/examples/make_demo.py <新模拟目录>
```

示例生成器创建明确标注的模拟 DOCX、对应的预解析布局、两种模式结果及人工示例判定，不调用 OCR，不把模拟数据当成服务端解析成功验证。随后可用 compare.py export 导出三类产物。

默认阅读面将静态 HTML/Markdown 转为文字和表格单元格边界，原始解析内容仍保留。文字一致不证明图像、样式、签章或扫描原件完全一致。源摘要缺失、非文本块、无法对齐窗口、语义待办均显式展示。大型无锚点窗口需人工/宿主模型提交对齐，不盲目错配。

本地与模拟测试验证不等于 DuMate 真机安装/联调。按现有项目的 DuMate 自定义套件结构打包，实际导入应由目标宿主验证其版本与工具配置。包内只包含通用技能、脚本和明确标注的模拟数据，不包含用户合同、测试报告或凭证。
