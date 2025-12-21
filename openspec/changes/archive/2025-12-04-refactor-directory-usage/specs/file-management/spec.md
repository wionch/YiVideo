## MODIFIED Requirements

### Requirement: 文件存储目录规范

系统 SHALL 将所有任务相关文件存储在 `/share/workflows/{task_id}` 目录下，而不是之前的 `/share/single_tasks/{task_id}` 路径。

#### Scenario: 任务文件存储路径更新

-   **WHEN** 创建新的任务上下文或执行工作流
-   **THEN** 文件应存储在 `/share/workflows/{task_id}/` 路径下

#### Scenario: 兼容现有任务

-   **WHEN** 访问 `/share/single_tasks/{task_id}` 路径的现有任务
-   **THEN** 系统应优先查找 `/share/workflows/{task_id}`，如不存在则回退到原路径

### Requirement: 临时文件目录管理

系统 SHALL 将所有临时文件存储在任务特定的临时目录 `/share/workflows/{task_id}/tmp/` 下，而不是系统级 `/tmp` 目录。

#### Scenario: 临时文件生成

-   **WHEN** 需要创建临时文件用于压缩、转换等操作
-   **THEN** 应在 `/share/workflows/{task_id}/tmp/` 下创建文件

#### Scenario: 临时文件清理

-   **WHEN** 任务完成或失败时
-   **THEN** 系统应清理对应任务 ID 下的 `/share/workflows/{task_id}/tmp/` 临时文件

## ADDED Requirements

### Requirement: 目录结构验证

系统 MUST 在访问目录前验证目录存在性，并在必要时自动创建所需的目录结构。

#### Scenario: 自动目录创建

-   **WHEN** 尝试访问 `/share/workflows/{task_id}/` 或其子目录
-   **THEN** 如果目录不存在，系统应自动创建完整的目录路径

#### Scenario: 权限验证

-   **WHEN** 执行文件操作前
-   **THEN** 系统应验证当前用户对目标目录具有适当的读写权限
