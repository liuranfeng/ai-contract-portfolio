# 合同 AI 产品作品集 · 刘冉丰

> 企业 Agent · 合同工作台 · 招投标与合同交叉校验 · 文档比对
> 本仓库收录可运行的产物与套件源码；**演示数据全部为合成或脱敏内容**，不含客户名称与客户合同原文。

**🌐 在线浏览**：<https://liuranfeng.github.io/ai-contract-portfolio/> —— 首页与三张演示页可直接在浏览器打开，无需下载。

## 目录索引

| # | 内容 | 形态 | 入口 |
| --- | --- | --- | --- |
| 01 | 合同智能化工作台 V5 | 交互演示（合成数据） | [`demos/workbench-v5.html`](demos/workbench-v5.html) |
| 02 | 招投标文件 × 合同交叉校验 | 交互演示（合成文本） | [`demos/tender-cross-check.html`](demos/tender-cross-check.html) |
| 03 | 独立文档比对（签前核对） | 交互演示（合成文本） | [`demos/doc-compare.html`](demos/doc-compare.html) |
| 04 | 招投标与合同交叉校验套件 | 源码（5 个 Skill） | [`suites/tender-contract-verification/`](suites/tender-contract-verification/) |
| 05 | 文档比对套件 | 源码（7 个 Skill） | [`suites/document-compare/`](suites/document-compare/) |
| 06 | 索引说明与脱敏口径 | 文档 | [`docs/`](docs/) |

在线首页：<https://liuranfeng.github.io/ai-contract-portfolio/>（GitHub Pages，源为 `main` / `/ (root)`）

## 三条主线

1. **把业务规则变成可执行任务**：规则 DSL 原子化、清单审查、角色与生命周期分工，任务、版本与意见处置由业务侧管理，Agent 只做模型执行。
2. **让结论可回溯到原文**：以解析 layoutId + 文档索引建立原文证据层，每条结论都能指回招标文件、投标文件或合同的具体段落。
3. **明确什么必须被拒收**：候选稿与正式版分离、受控回传 + 哈希校验；比对结果以真实 Word 修订输出，可逐条接受或拒绝。

## 每个作品的说明

- [01 · 合同智能化工作台](docs/01-contract-workbench.md) — 产品结构、角色 × 生命周期四阶段、任务与版本分离、受控回传与拒收判据
- [02 · 招投标与合同交叉校验](docs/02-tender-cross-check.md) — 非置换式校验的判定口径、原文证据层、跨文档 layoutId 重排处理、长文档分段
- [03 · 独立文档比对](docs/03-document-compare.md) — 逐 layout 比对、字符/语义双模式的适用边界、Word 原生修订与三屏联动
- [04 · 数据与脱敏说明](docs/04-data-and-anonymization.md) — 哪些是本地验证、哪些只是方案原型；数据来源与脱敏处理

## 成果状态口径

本仓库严格区分三种状态，避免把设计目标写成成果：

| 状态 | 含义 |
| --- | --- |
| 本地验证 | 在本机环境跑通并留有产物（脚本、报告、测试），未接客户生产环境 |
| 方案 / 原型 | 完成设计与原型，等待实现或排期 |
| 客户验收 | 客户环境通过验收，**本仓库不包含任何此类结论** |

## 使用与授权

代码与文档归作者所有，仅用于作品展示与交流；如需引用或复用请先联系。演示页中的公司名、条款、金额与日期均为合成示意数据。
