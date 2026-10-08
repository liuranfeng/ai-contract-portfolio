# 文档比对解析输出 1.0.0

解析元数据沿用 schema_version=2.0，增加原始服务归档字段。入口：百度 PaddleOCR-VL task → query → 下载 Markdown 与页面 JSON。客户端仅依赖 Python 标准库。

| 字段 | 约定 |
| --- | --- |
| parser / auth_source | baidu-document-parser/paddle-vl / qianfan_api_key |
| source_kind / source_file / source_sha256 | file_attachment、文件名、上传前原件字节 SHA-256；上传结束后再次核对 |
| parse_run_id / task_id | 本次本地执行 UUID / 远端异步任务 ID；续查共享原 task_id |
| parse_status / engine | success / base |
| raw_parse_file / raw_parse_sha256 | 同目录原始服务 JSON 归档文件名 / 该归档实际 UTF-8 字节的 SHA-256 |
| archive_redacted_paths | 已去除凭证或带查询参数 URL 的 JSON 路径；空数组代表无需脱敏 |
| markdown_file / markdown_sha256 | 同目录 Markdown 文件名 / 字节摘要 |
| pages / sections / layout_available | 保序页面与布局；完整 Markdown 的 document 节；是否存在可比对布局文本 |

`*_raw_parse.json` 保留服务原结构与数组顺序，不混入 API 请求头或签名下载地址。为避免归档敏感信息，已知凭证字段、实际配置的 Key 和带查询参数的 URL 会脱敏；哈希针对脱敏后的归档字节，不冒充服务端签名或未脱敏下载文件摘要。没有脱敏时，JSON 结构与服务一致，缩进与编码可能不同于下载字节。

`pages[].layouts[].layout_id` 必须是非空字符串或整数，bool 不接受；整数 0 有效，整数 0 和字符串 "0" 是不同 ID。唯一性范围是整份文档，跨页重复也报错。不同文档可重用同一原生 ID，由核心 `documentIndex` 区分。读取顺序是 pages/layouts 数组顺序；`page_num` 是显示线索，不是排序键。

layout 的 `text_raw` 保留补充表格前的服务 layout 文本；`text` 通过相同原生 ID 关联 tables 的 markdown/table_html。核心根据 text 生成 readingText，不修改 text 或 text_raw。归档保留完整 tables、position 和其他服务字段；缺少坐标不虚构。

`*_job.json` 仅记录 task_id、parser、source_file、source_sha256 和 parse_run_id，供相同原件续查。若原生布局不合格，仍保留脱敏 raw 归档与 job，且不写成功的 parsed JSON/MD。原件须由用户保留。

`parse_gate_check.py verify` 校验原件、Markdown、归档摘要、解析批次与服务元数据；`--require-layout` 额外检查全部布局的原生唯一 ID。该门控面向此脚本的云端成功产物。用户已有解析结果、模拟 fixture 的直接导入由 document-compare 核心负责，不需要伪造此元数据或重新上传。
