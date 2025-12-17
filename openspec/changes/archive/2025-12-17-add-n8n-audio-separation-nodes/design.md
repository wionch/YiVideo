# Design: add-n8n-audio-separation-nodes

## 目标

在 n8n 的 `YiVideoNodes` 工作流中增加“音频分离”节点模板，使用户能通过 YiVideo 单步任务接口一次性获得：

- 人声文件（Vocals）
- 全部拆分音轨（All stems，数量依模型而定）

并强制使用模型：`UVR-MDX-NET-Inst_HQ_5.onnx`。

## 现状与缺口

### 单任务模式数据流

1. n8n `HTTP Request` 调用 `POST http://api_gateway/v1/tasks`
2. API Gateway 创建单任务上下文，将 `input_data` 作为 `workflow_context.input_params.input_data` 传给 worker
3. worker 执行后返回 `WorkflowContext`（包含 `stages.<task_name>.output`）
4. API Gateway 尝试从结果中提取文件路径并上传 MinIO，随后将 `result` 与 `minio_files` 回调到 n8n `Wait` webhook

### 当前阻断点

- worker 输出缺少“全部音轨”这一通用结构，n8n 无法稳定感知除人声之外的其它轨道。
- 单任务输入中的模型/质量参数未被 worker 读取，导致 n8n 无法通过单任务接口稳定固定模型。
- API Gateway 的 `_extract_file_paths` 未包含音频分离产物字段，导致 `minio_files` 不包含分离产物。

## 方案设计

### 1) YiVideo 侧（实施阶段）

1. **audio_separator 输出结构补齐**
   - `stages.audio_separator.separate_vocals.output` 仅暴露两类语义：`vocal_audio`（人声文件）与 `all_audio_files`（本次分离产生的所有轨道列表），满足不同模型拆分 stem 的可扩展性。

2. **单任务模式参数透传与优先级**
   - 支持从 `input_data.audio_separator_config`（以及 `node_params`）读取模型/质量参数，与现有解析逻辑一致。
   - **优先级**：`node_params.audio_separator_config` > `input_data.audio_separator_config` > `config.yml` 默认值（demucs/mdx 等），以保证单步请求显式指定模型时立即覆盖全局配置。
   - 明确模型固定策略：n8n 节点始终传 `model_name="UVR-MDX-NET-Inst_HQ_5.onnx"`，YiVideo 侧将其作为最高优先级，并在 `model_used` 字段中返回最终生效的模型名。

3. **单任务结果文件上传覆盖音频分离字段**
   - API Gateway `_extract_file_paths` 识别并提取 `vocal_audio` 与 `all_audio_files`，自动上传并返回对应的 MinIO URLs（同样是 `vocal`/`all` 双层结构）。

### 2) n8n 侧（实施阶段）

在 `YiVideoNodes` 工作流中新增一组节点模板（保持与现有模板一致）：

- `请求:audio_separator分离（UVR Inst HQ 5）`（HTTP Request）
  - `method=POST`
  - `url=http://api_gateway/v1/tasks`
  - `jsonBody` 包含：
    - `task_name="audio_separator.separate_vocals"`
    - `task_id` 占位符
    - `callback="{{ $execution.resumeUrl }}/t_audio_sep"`
    - `input_data.audio_path`（MinIO URL 示例）
    - `input_data.audio_separator_config.model_name="UVR-MDX-NET-Inst_HQ_5.onnx"`
- `Wait:audio_separator`（Wait / webhook resume）
  - `options.webhookSuffix="t_audio_sep"`
- `提取分离结果URL`（可选 Code/Set）
  - 从 `{{$json.minio_files}}` 按文件名模式匹配所需音轨，输出为 `vocals_url`（人声）与 `all_audio_urls`（数组，列出所有音轨）。

## 兼容性与约束

- 不新增新的 Celery task 名称；复用 `audio_separator.separate_vocals` 以降低队列与文档维护成本。
- 保持现有输出字段不变，只做“新增字段”方式扩展，避免破坏既有工作流。
- callback URL 必须通过 YiVideo 的安全校验（禁止 localhost/127.0.0.1/.local），n8n 部署需提供可达域名/地址。

## 备选方案（未选）

1. 新增 `audio_separator.separate_background` 任务：语义清晰但会引入额外 task/队列、文档与运维成本。
2. n8n 直接读取 `/share` 路径：耦合部署环境，且不利于远程/托管 n8n 使用；不推荐。
