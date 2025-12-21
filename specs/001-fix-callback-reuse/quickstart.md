# Quickstart: callback 复用覆盖修复

1) **准备环境**
- 安装依赖：`pip install -r requirements.txt`
- 启动依赖：`docker-compose up -d`（确保 Redis、MinIO、workers 均运行）

2) **核心用例验证（复用命中）**
- 步骤：顺序调用 `/v1/tasks` 提交 `ffmpeg.extract_audio` → 再次提交同任务（应命中）→ 提交 `audio_separator.separate_vocals` → 再次提交 `ffmpeg.extract_audio`。
- 期望：第 4 次同步响应 `status=completed` 且 `reuse_info.reuse_hit=true`，`stages` 中保留第一次提取结果并包含分离阶段。

3) **等待态验证**
- 在首次提交后立即重复同 `task_id+task_name`，检查同步响应 `status=pending`、`reuse_info.state=pending`，无新任务排队。

4) **未命中执行**
- 让缓存 `status=FAILED` 或 `output` 为空，再次请求应走正常调度并写入新阶段，`reuse_info.reuse_hit=false`。

5) **文档核对**
- 打开 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`，确认各节点小节包含复用判定、返回示例与字段说明，与接口行为一致。

6) **回归检查**
- 跑基础测试：`pytest`
- 按需补充接口/集成测试覆盖上述场景。
