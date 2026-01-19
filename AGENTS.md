# 仓库贡献指南

## 项目结构与模块组织

-   `services/`: Python 微服务与 worker，共享逻辑在 `services/common/`。
-   `tests/`: pytest 测试，按 `unit/`、`integration/`、`api_gateway/` 分组。
-   `docs/`: 产品、技术与 API 文档。
-   `config.yml` 与 `config/`: 运行配置。
-   `videos/`、`share/`、`tmp/`、`locks/`、`logs/`: 运行数据与缓存。

## 构建、运行与开发命令

项目通过 Docker Compose 运行服务。

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose down
```

## 测试与验证（必须容器内）

所有 pytest 与调试必须在容器内执行，严禁在宿主机运行。容器名从 `docker ps` 获取。

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
docker exec -it <container_name> bash
pytest /app/tests -v
```

单测示例：

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/test_gpu_lock_error_handling.py -v
```

## 编码风格与命名

-   Python 使用 4 空格缩进，遵循 PEP8。
-   命名：模块/函数 `snake_case`，类 `PascalCase`，常量 `UPPER_CASE`。
-   注释与文档字符串使用中文，保持简洁、面向行为。

## 语言约束规则

-   本仓库所有贡献必须使用中文：文档、注释、日志文案、Issue/PR 描述与评审说明。
-   提交信息使用 Conventional Commits 前缀 + 中文主题，例如 `feat(api_gateway): 修复任务删除超时`。

## 提交与 PR 指南

-   PR 需说明目的、影响范围、容器内测试命令；未运行测试需说明原因。
-   涉及配置或环境变量变更时，同步更新 `.env.example` 或相关文档。

## 配置与安全

-   运行配置集中在 `.env`、`config.yml` 与 `config/`。
-   禁止提交密钥、访问令牌或个人凭证。

## 🏛️ 全局架构约束 (Principles)

所有重构和设计任务必须通过以下过滤网：

1. **KISS (保持简单)**：如果简单的 `if/else` 能工作，严禁引入复杂的工厂模式或策略模式。
2. **DRY (拒绝重复)**：看到重复代码，必须提取为 Utility 或 Mixin。
3. **YAGNI (拒绝过度设计)**：只写当前需要的代码，不要为未来写"钩子"。
4. **SOLID**：特别是 **单一职责 (SRP)** —— 每个 Worker 只做一件事。

**违规检查**：在输出代码前，自问："我是否把事情搞复杂了？" 如果是，**请重写**。
