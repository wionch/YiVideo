---
name: yivideo-docker-testing
description: YiVideo 的测试/调试必须在 Docker 容器内执行。当你让我“跑 pytest/调试脚本/验证依赖/复现问题/写测试步骤/给出验证命令”时启用。输出可直接复制的 docker exec + pytest/python 命令序列，并禁止建议在宿主机直接运行。
---

# YiVideo 测试与调试（必须容器内执行）

## 强制原则（项目约束）

由于项目真实运行环境位于 Docker 容器内：

- ✅ 必须在容器内执行：所有 `pytest`、Python 脚本调试、依赖验证等
- ❌ 禁止在宿主机执行：宿主机缺少必要依赖、GPU 驱动、网络配置等，结果不可靠

## 标准执行流程（输出模板）

当用户需要测试/调试/验证时，你必须先从`@docker-compose.yml`文件获取正确的映射路径; 然后输出如下步骤（并用项目实际容器名替换占位符）：

```bash
# 1) 进入目标服务容器
docker exec -it <container_name> bash

# 2) 在容器内执行测试（如需）
pip install pytest  # 仅在容器未包含 pytest 时使用
pytest /{容器映射路径}/test_xxx.py -v

# 3) 或执行调试脚本
python /{容器映射路径}/debug_xxx.py
```

## 交互与容错规则

- 如果用户未提供容器名：
    - 先给出“如何识别容器名”的建议（例如让用户从 `docker ps` 中选择目标服务容器），但仍然输出上面的标准模板，保持可执行。

- 如果用户提供了服务名但不是容器名：
    - 建议用户把该服务对应的容器名贴出（或从 `docker compose ps`/`docker ps` 获取），然后你再生成最终命令。

- 若用户要求“快速验证”：
    - 优先给出最小命令集（进入容器 + 单条 pytest 或 python 命令），避免冗长步骤。

## 输出要求

- 命令必须可复制执行（bash fence）。
- 明确标注在哪里执行：宿主机 vs 容器内。
- 任何涉及验证/复现的回答，都必须以“容器内命令”为主。
