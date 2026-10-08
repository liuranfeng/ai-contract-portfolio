# 离线验证

在插件目录运行：

```bash
python -B -X utf8 -m unittest discover -s skills/contract-parsing/tests
```

29 个互不重复的自动测试，无真实上传、无真实服务调用。网络传输由 Transport 模拟，使用假 Key 和假原件；不读取机器上已配置的 Key。

复用原客户端的 task/query、鉴权、超时续查、源摘要、拒绝本地降级、签名结果下载不带 API Key 的回归测试。新增测试覆盖缺失/重复原生 ID、整数 0、字符串/整数 ID 区分、表格 text_raw、保序、不修改输入、原始归档、归档摘要和敏感信息脱敏。

新增测试先在原副本上运行，观察到缺 ID 不拒绝、跨页重复不拒绝、表格覆盖 text_raw、归档字段缺失；门控测试复现了整数 0 被误拒、空布局重复被忽略和归档变更未被识别，随后修复并通过。此记录仅为模拟验证，不是百度接口联通验证。

技能应用场景见 cases.json：重点区分原件云端解析与已有 JSON 导入；缺 native ID 时拒绝补号；数组顺序不按页码重排。完整服务 reading_order 的导入排序由 document-compare 核心负责。
