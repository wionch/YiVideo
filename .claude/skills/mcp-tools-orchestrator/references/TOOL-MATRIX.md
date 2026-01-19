# references/TOOL-MATRIX.md

# 工具矩阵（Tool Matrix）——以实际 MCP schema 为准

> 目的：给出“何时用哪个工具”的细粒度规则 + 常用输入要素。
> 注意：不同 MCP server 暴露的函数名/参数可能不同；以你环境中实际列出的 tools 为准。

## serena（代码符号/LSP）

适用：

-   定义/引用/调用链/跨文件定位
-   重构影响面评估、重命名建议、入口定位

最小输入要素：

-   symbol（类/函数/变量名）
-   scope（目录/包/语言）
-   ask（找定义/找引用/找调用链/找入口/评估影响面）

硬约束提示：

-   遇到 `"No active project"`：先 activate_project，再重试原始操作（见主 Skill 的硬规则）。

## context7（版本特定文档）

适用：

-   “最新 API 是否存在/该怎么用/版本差异/官方推荐写法”

典型两步：

1. resolve library id（包名 → library id）
2. get docs（library id + topic + tokens）

输出要求：

-   明确版本前提（如 docs 指向某个版本/日期）
-   不杜撰 API；不确定就继续查 docs 或回到官方源

## sequential-thinking（分步推理）

适用：

-   多约束规划、排障、方案评估、架构变更、多文件联动

建议输出要素：

-   steps（分步计划）
-   assumptions（假设）
-   alternatives（备选方案）
-   evidence_needed（证据缺口）
-   next_action（下一步最小动作）

## brave-search（广覆盖检索）

适用：

-   先找线索/候选页面（web/news/video/image）
    策略：
-   先 broad，再用 exa 精筛；需要原文证据则用 tavily-remote 抽取

## exa（高精度/研究级/代码证据）

适用：

-   高质量来源、学术/专业内容、GitHub/代码证据
    策略：
-   优先官方/规范/权威机构来源；对时间敏感结论做互证

## tavily-remote（URL 抽取/结构化提取/站点 crawl）

适用：

-   给定 URL 列表抽取
-   需要 map/crawl 站点汇总与结构化字段

策略：

-   抽取时记录日期/版本/原文位置，便于复核
-   抽取失败：回退 brave/exa 重新找可访问的官方镜像/等价页面

## filesystem（文件读写/目录管理）

适用：

-   对工作区做**内容级文件操作**：读写/批量读取/目录遍历/搜索/目录树/元数据
-   处理长日志、配置/模板、数据文件等（serena 侧重符号语义，filesystem 侧重 I/O）

硬约束与最佳实践：

-   先 `list_allowed_directories`，确保所有路径都在允许根目录内
-   **先读后写**：先 `read_text_file` / `read_multiple_files` / `list_directory` / `search_files` 再决定改动
-   `edit_file` 必须先 `dryRun=true` 预览 diff，再应用
-   `write_file` 会覆盖，慎用；需要覆盖时，先读出原内容并在输出里给出回滚路径

常用工具（以官方 server-filesystem 为准）：

-   读：`read_text_file`, `read_multiple_files`, `read_media_file`
-   写：`edit_file`, `write_file`, `create_directory`, `move_file`
-   查：`list_directory`, `list_directory_with_sizes`, `directory_tree`, `search_files`, `get_file_info`
-   安全：`list_allowed_directories`
