---
name: document-diff-report
description: Use when the user requests a separate document comparison report in Word or PDF, 独立比对报告, 全部差异清单, or a report with semantic reasons and source layout references.
metadata:
  dumate:
    displayName: "文档比对独立报告"
    summary: "独立输出 DOCX 或 PDF 比对报告，完整呈现差异、语义理由、待确认事项和原生来源索引。"
    publisher: "自定义安装"
    icon: "assets/icon.png"
    publishedAt: 1789444800000
    version: "1.1.0"
    level: L0
    category: 行业服务
    tags: ["文档比对", "报告", "PDF", "Word"]
    sensitive: true
    allow_implicit_invocation: true
    review:
      status: pending
---

# 独立比对报告

输入是经 `document-compare` 校验的 [统一比对结果](../document-compare/references/data-contract.md)。这是用户可单独选择的第三类交付物：DOCX 或 PDF 说明报告。原件真实修订使用 `document-word-edit`；三栏网页使用 `document-diff-html`。不要把独立报告称作原文件修订。

报告包括校验概况、全部对齐条目（含一致项）、两侧全文、原生 documentIndex 和 layoutId、语义状态与理由、pending／uncertain 待确认事项、来源文档与解析批次索引。正文用中文业务标签；字符区间位于末尾追溯部分。equal 无需语义解释，not_requested 表示此次未请求语义判断；任何 pending 不能改写为等义或完成。

```python
write_report(result, output_path, format="docx")
```

函数在 [write_report.py](scripts/write_report.py)，不添加语义判断，返回 manifest 并保存 `输出文件.manifest.json`。

```text
python scripts/write_report.py result.json --output report.docx --format docx
python scripts/write_report.py result.json --output report.pdf --format pdf
```

DOCX 需要 `python-docx`；PDF 需要 `reportlab`，可直接生成，不依赖 Word 转换。宿主有 bundled Python 时使用该运行时；脚本不调用模型、OCR 或外部网络。

交付前核对每个对齐 ID、两侧全文、来源索引及待确认数量均保留，运行 [报告测试](tests/test_report.py)。DOCX 用宿主文档渲染器、PDF 用 PDF 渲染器逐页检查排版、中文字符、表格和分页。查看失败日志再诊断；渲染不可用时如实区分结构／文本验证与视觉验收。生成器 manifest 的 `visualQA=not_performed_by_writer` 不能自行宣称视觉检查通过。
