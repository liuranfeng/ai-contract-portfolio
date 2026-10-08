# 超长文档：传输拆分、阅读窗口与原件保真

本策略适用于文件超过解析接口限制，或完整解析文本超过单次模型上下文的情形。两种拆分分别记录：**上传用物理 PDF 分片**解决传输限制；**基于原生 layoutId 的阅读窗口**解决上下文限制。它们都不改变业务文件归属，也不代表已经完成事实审查。

## 1. 物理分片：复制原 PDF 页面

运行插件自带的离线工具，PDF 操作需要当前 Python 环境提供 `pypdf`：

```sh
python skills/tender-evidence/scripts/document_chunks.py split source.pdf run-new/chunks --parent-document-index 2 --child-index-start 10 --max-pages 60 --max-bytes 35000000
python skills/tender-evidence/scripts/document_chunks.py verify run-new/chunks/manifest.json
```

`60` 页、`35000000` 字节是可配置起点，来自已验证流程，并非接口永久限制；使用部署环境确认的限制，必要时为传输封装预留余量。先按页数分组，序列化后检查实际字节，超限则递归二分。单页仍超限必须停止并报告原始页码；不得静默降低画质、删页或截断。不要默认把 PDF 转成截图再拼 PDF。

工具创建全新的目录，已有目录直接拒绝。分片写完先保存 `status=pending` 的 manifest，校验成功后才原子发布 `status=complete`；校验失败标记 `failed`，中断可能保留 pending 或部分分片。只有 complete 且通过 `verify` 的目录可用于上传；修正后使用新运行目录。源 PDF 保留，所有分片均为派生副本，不能代替签署原件。

### 身份与页码

- `parentDocumentIndex` 指原始业务文件。每个独立解析分片占用一个项目内未使用的 `documentIndex`。调用方预先预留足够编号区间；工具可检查父子别名，不能知道项目中未传入的其他编号。
- 原始文件哈希、各分片哈希、实际大小、原始总页数、分片顺序以及每页映射都保存在 `manifest.json`。
- `chunkPage`、`originalPage` 均从 1 开始，逐页映射。业务上显示原文件名和 `originalPage`；原件跳转使用父文件，解析证据定位使用子文件索引。
- 解析结果原生 `layoutId` 和其类型原样保留。`1` 与 `"1"` 不等价。不同分片重用相同 ID 是正常情况；严禁为合并方便全局重排。
- 在固定快照内用 `(documentIndex, layoutId)` 定位；跨解析运行再带 `parseRunId` 或固定快照版本。重新解析产生新版本，不覆盖旧事实的出处。

导入示意（字段名仅展示映射，layoutId 必须来自真实解析结果）：

```json
{
  "documentIndex": 10,
  "parentDocumentIndex": 2,
  "parseRunId": "run-2026-09-10-a",
  "layouts": [
    {"layoutId": "parser-native-value", "page": 1, "originalPage": 61, "text": "原生解析文本"}
  ]
}
```

若解析器连单个分片内部也重置 ID，不能擅自加后缀，也不能按页自动划分单次解析响应以规避重复校验。检查适配器是否错取页面内编号，确认服务实际独立的文档命名空间，或要求服务修正为文档内唯一的原生 ID 后再导入。只有确认为独立解析文档的结果才单独注册文档索引。

### 将解析页码落到原文件

使用标准 `import-layouts` 输出，再显式指定解析器页码从 0 还是 1 开始：

```sh
python skills/tender-evidence/scripts/evidence.py import-layouts parser-raw.json imported-layouts.json
python skills/tender-evidence/scripts/document_chunks.py map-layouts run-new/chunks/manifest.json 10 imported-layouts.json mapped-layouts-new.json --page-base 1
```

工具先验证整个分片 manifest，然后通过 `chunkPage = parserPage + 1 - pageBase` 查逐页映射并添加 `originalPage`。它保留原生 `page`、`layoutId` 和文本，拒绝布尔值、字符串或小数页码、无法映射的页码、已有 `originalPage` 冲突和同文档重复 ID；不凭最小页码猜测页码基数。

输出顶层提供 `documentIndex`、`parentDocumentIndex`、子文件 `sourcePath/sourceSha256`、`chunkSha256`、父文件 `parentSourcePath/parentSourceSha256`、`splitManifestSha256`、原始页范围和 `parserPageBase`，并保留 `rawParseSha256`。宿主将该结果加入文档注册表时仍需补充真实 `parseRunId`、角色和展示名称。此步骤映射已有块，不证明每页都被解析；空白页、失败页和漏块仍由覆盖审核单独记录。输出文件必须为新路径，不覆盖此前结果。

### 保持文档效果

复制页面保留文字、矢量、原生资源、MediaBox、CropBox 和旋转角度；工具逐页校验内容流和几何属性，并验证哈希、页数、顺序、无缺页重页。自动校验不是视觉证明：抽查各切分边界的前后页、复杂表格、横向页、印章/签字页与原件的渲染，记录异常。

跨页表格不为了分片而重排内容。保存原表头、续表标识、合并单元格、列标题、章节编号和前置主体范围。分片开头缺表头时，从前一分片原页检索上下文；保留各自证据引用，不能把补充表头伪装成本页原文。页码标签、目录超链接、签名验证等文档级功能不保证在派生副本中继续有效；签署原件始终是视觉展示和身份核验的主文件。

## 2. OCR 任务状态、缓存与恢复

此工具不提交 OCR 请求。执行已有解析流程时将以下状态和血缘写入任务清单：

```text
prepared → submitting → pending / processing → success
                    ↘ submit_failed / submission_unknown
pending / processing → failed
```

提交之前持久化 `submitting`。网络中断导致是否提交不明时记为 `submission_unknown`，先查询或核对供应商记录；不得自动重复付费提交。已取得 taskId 的任务继续轮询同一个任务。鉴权、权限或配额失败停止提交，修复原因；限流按服务端要求有限退避。查询响应必须匹配 taskId。失败页/分片保留待复核覆盖记录，不生成“全量完成”结论。

成功缓存至少绑定：源哈希、分片哈希、解析引擎/版本、参数、parseRunId、taskId、原始结果哈希和完成状态。只有这些条件匹配且文件校验通过才复用。下载中断用临时文件，完成校验后落盘；重新解析另建运行版本。不得把访问密钥、令牌、带签名下载 URL 写入插件、报告、任务清单或测试夹具。

## 3. 阅读窗口：主责唯一，上下文可复用

```sh
python skills/tender-evidence/scripts/document_chunks.py chunk-plan snapshot.json windows-new.json --max-chars 24000 --context-blocks 2
```

输入是既有 `documents[].layouts[]` 快照。输出只含引用和预算信息，不复制或改写文本：

- 每块原文恰好出现在一个窗口的 `primaryRefs` 中，作为事实提取和覆盖统计的主责。
- 相邻块可作为多个窗口的 `contextRefs`，同一窗口去重；上下文复用不得重复计为新增事实或覆盖量。
- `totalChars` 包含主责与已装入上下文，不超过预算；单块超限保持完整，以 `oversizeBlock=true` 标明，转入专项阅读，严禁按字符截断后宣布完成。
- 没装入预算的相邻引用在 `deferredContextRefs` 中显式列出。审查主体、范围、例外、表头或续表需要它们时，追加读取后才能判定。字符数不是模型 token 数，调用方还须预留指令、输出和编码预算。
- 工具按已有 layouts 顺序规划。先验证解析阅读顺序与原件一致；多栏、表格或错序不能靠窗口工具修正。
- 当前自动邻接只在同一派生文档内。物理切分边界必须依 manifest 对前一/后一子文档取相邻原页；需要的表头可能距离更远，按章节/表格归属扩展读取。不要将“未自动列出”当成“不需要”。

核验模型先读取引用对应的完整原文，再提取主体、动作、对象、数值、条件、范围、例外和履行期限。跨窗口形成同一事项时关联原始事实，不覆盖原文，也不因摘要相似合并不同适用范围。将冲突证据和反向证据一并挂接，尤其是投标承诺纳入条款、合同优先条款、附件和修订版本。

## 4. 汇总与交付闸门

先验证物理 manifest；再以 `(documentIndex, native-layoutId-type, layoutId)` 统计主责覆盖，保持背景材料、未解 OCR、待上下文补读等状态可见。统计业务文档数量时按父文件归并，统计证据时保留子文档身份。禁止用分片数充当原文件数，禁止用提取到的主题数声称所有条款已重新审查。

报告可以把同一原文件的多个分片连续展示，显示原始页码并链接原件；证据锚点仍按子文件索引定位。原文 Diff 只对真实摘录计算，事实概括、结论与建议分层展示。长表、连续文档和关系连线的打印策略由报告导出流程处理，不能以隐藏缺失证据解决分页。

离线回归：

```sh
python skills/tender-evidence/scripts/test_document_chunks.py
```

测试覆盖大小自适应、单页超限、原文页文本和 CropBox/旋转保留、缺页/重页/丢分片/哈希变更、编号冲突、原生 ID 类型、窗口唯一主责和超长块不截断。测试不访问 API。
