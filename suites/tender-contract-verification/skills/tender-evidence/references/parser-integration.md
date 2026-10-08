# 解析接入边界与运行方法

套件使用宿主已配置的文档解析能力取得原件对应的原始布局结果。当前包不包含生产解析 API 客户端，不自动上传文件、不读取其他套件密钥、不声明不存在的 Connector。

超长输入、跨页保真、任务缓存与失败恢复先读 [long-documents.md](long-documents.md)。调用 document_chunks.py split/verify；完成真实解析和 import-layouts 后调用 map-layouts 显式映射页码，再注册文档。不把旧测试脚本的硬编码路径、任务 ID 或鉴权写回套件。接口的当前页数/字节限制与实际响应由部署方核实；分片脚本参数不是供应商永久规格。

在 DuMate 中先确认可用解析工具及实际返回结构。若宿主只提供 Markdown、没有原始 layoutId，停止正式证据构建并说明缺少原始布局返回；不能用 AI 或旧脚本补号。已有旧合同套件的解析接入可作平台配置参考，但必须取得未补号的原始响应。

1. 保存原件、原始解析 JSON 到项目工作区。持久配置遵循宿主 XDG_CONFIG_HOME 约定，客户数据不写入安装包。
2. 记录原件摘要、解析响应摘要和 parseRunId；使用宿主文件工具或 Python hashlib 对真实字节计算，不编写假摘要。
3. 运行下列命令（将脚本路径和数据路径换为实际绝对路径）。Python 3.10+，仅标准库：

```text
python <套件>/skills/tender-evidence/scripts/evidence.py import-layouts raw.json layouts.json
python <套件>/skills/tender-evidence/scripts/evidence.py validate project.json
python <套件>/skills/tender-evidence/scripts/evidence.py locate project.json 0 12
python <套件>/skills/tender-evidence/scripts/evidence.py validate project.json --final
python <套件>/skills/tender-evidence/scripts/evidence.py report project.json report-directory
python <套件>/skills/tender-evidence/scripts/evidence.py report project.json process-report-directory --process
```

locate 最后参数为 JSON 字面量，12 是数值 ID，字符串 ID 则传入含双引号的 JSON 字符串，按当前 shell 正确引用。输出路径不得已存在，以免覆盖。report-directory 必须是新目录。--process 只导出明确标注的过程报告，仍须通过基础证据校验，同时记录 final 门控失败原因；不将过程报告伪装为正式报告。

import-layouts 输出 layouts 与 rawParseSha256；材料 skill 将其原样并入文档记录，补齐原件摘要和批次。工具不自动识别项目、文档角色或语义，不自动生成 facts/checks；这些由专用 skills 执行。

发布前真实接入验证：原件和批次对应；layout ID 原生且文档内唯一；页码起算明确；整表及跨页结构；原文定位可回原件；鉴权/漏页失败可辨识。未取得真实响应前，只能声明支持本契约和模拟测试，不能声明平台已联调。
