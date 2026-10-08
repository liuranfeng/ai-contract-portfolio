---
name: document-diff-html
description: Use when 需要把独立文档比对结果生成离线三栏 HTML，展示原件、比对件、差异清单、双侧定位和差异连线。
metadata:
  dumate:
    displayName: "文档差异视图"
    summary: "左原件、中比对件、右差异清单，保留完整正文与证据定位，分开呈现字符变化和语义结论。"
    publisher: "自定义安装"
    icon: "assets/icon.png"
    publishedAt: 1789430400000
    version: "1.1.0"
    level: L3
    category: 行业服务
    tags: ["文档比对", "差异定位", "离线报告"]
    sensitive: true
    allow_implicit_invocation: true
    review:
      status: pending
---

# 文档差异视图

先读 [交换契约](../document-compare/references/data-contract.md)。读取 document-compare 产出的 schemaVersion 1.0 JSON；不重新调用解析器，不发起模型请求，不在展示层补判语义。

运行：

```shell
python scripts/render_html.py comparison.json comparison.html
```

或导入 `scripts/render_html.py`，调用 `render_html(result, output_path)`；返回输出文件的 Path。生成一个包含 CSS、JS、数据和全文的 HTML 文件，无 CDN、外部字体、远程图像或网络请求。使用新输出路径；不覆盖输入文档。

正文左原件、中比对件，右侧为差异清单。三栏独立滚动；点清单项同时定位两侧；空侧增删有阅读序列占位；虚线连接同一比对项。列表筛选只影响差异清单，不删除正文。Tab / Enter 可达所有操作，Alt+↑ / Alt+↓ 切换差异。窄屏保留可横向滚动的三栏。

绿色是右侧新增，黄色是右侧修改，红色是右侧删除。字符模式只表达字面变化。语义模式对改写一致、含义变化、不确定、待判定分别显示状态与既有理由；equivalent 不抹掉字面变化，pending 不称为一致。未判定及未解决对齐须保留明确提示。

正文按静态 HTML / Markdown 的安全子集显示，保留标题、列表、表格。脚本、事件、任意样式、链接和远程资源不会执行；图片显示“见原件”占位，不能据此宣布图像一致。原始解析文本完整保留在每块的折叠区。安全渲染无法精确映射字符位置时，正文不猜测高亮，并显示提示；“完整字符对照”仍按 charOps 精确展示。JS 字符处理用 Array.from 遵守 Unicode 码点契约。

正文不截断、不依据原生 layoutId 排序，按 alignments 与 layouts 数组的阅读顺序显示。超长原文仍完整可滚动阅读与展开。HTML 仅为比对视图，不加入案件、项目或工作台管理。

本地验证：`python -m unittest discover -s tests -v`。测试样例是模拟数据，不代表 DuMate 真机联调。浏览器视觉验证应使用隔离的 headless 实例，不占用用户现有浏览器。

`scripts/document_display.py` 复制自工作区 `tender-contract-verification-plugin/skills/tender-evidence/scripts/document_display.py`，用于允许列表结构渲染；原模块未修改。本技能在 renderer 中保守映射既有 charOps，不使用该模块的 document_diff 重新生成结论。
