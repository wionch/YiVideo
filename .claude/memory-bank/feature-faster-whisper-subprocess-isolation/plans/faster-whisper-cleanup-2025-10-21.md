# faster_whisper_service 冗余代码清理执行计划

**计划创建日期：** 2025-10-21
**目标分支：** feature/faster-whisper-subprocess-isolation
**计划状态：** 待执行
**预估执行时间：** 2-3 小时

---

## 📋 执行概览

### 目标
清理 `services/workers/faster_whisper_service` 目录中的冗余代码和文件，这些冗余是由近期的架构改造（从直接模型加载到 subprocess 隔离）产生的。

### 清理范围
- **明确冗余：** 1 个备份文件 + 多个缓存目录
- **疑似冗余：** 4 个模块文件（需验证后决定）
- **保留文件：** 所有核心功能和测试脚本

### 风险评估
- **总体风险：** 🟡 中等
- **回滚难度：** 🟢 低（所有操作可通过 Git 回滚）
- **业务影响：** 🟢 最小（主要清理未使用代码）

---

## 🎯 前置条件检查

### 1.1 环境验证
**执行前必须确认以下条件：**

```bash
# 检查当前分支
git branch --show-current
# 预期输出：feature/faster-whisper-subprocess-isolation

# 检查工作区状态
git status
# 预期输出：working tree clean 或只有未跟踪文件

# 检查 Docker 服务状态
docker-compose ps faster_whisper_service
# 预期输出：服务运行中或已停止（可接受）
```

**前置条件清单：**
- [ ] 在正确的分支上
- [ ] 工作区干净（或已保存当前更改）
- [ ] 已阅读完整计划
- [ ] 有完整的备份或 Git 提交记录
- [ ] 有权限执行文件删除操作

### 1.2 备份当前状态

```bash
# 创建安全点
git add .
git commit -m "backup: 清理前的状态保存点 - $(date +%Y%m%d-%H%M%S)"

# 或创建新分支作为备份
git branch backup/pre-cleanup-$(date +%Y%m%d)
```

**成功标准：**
- ✅ Git 显示新的 commit 或分支创建成功
- ✅ 可以通过 `git log` 看到备份点

---

## 🔍 阶段 1：依赖关系验证（30分钟）

### 目标
在删除任何文件前，彻底验证是否有其他模块依赖疑似冗余的文件。

### 步骤 1.1：搜索项目级引用

```bash
# 进入项目根目录
cd D:/WSL2/docker/YiVideo

# 搜索 model_manager 引用
echo "=== 搜索 model_manager 引用 ==="
grep -r "model_manager" --include="*.py" services/ | grep -v "__pycache__" | grep -v ".pyc"

# 搜索 model_health 引用
echo "=== 搜索 model_health 引用 ==="
grep -r "model_health" --include="*.py" services/ | grep -v "__pycache__" | grep -v ".pyc"

# 搜索 performance_api 引用
echo "=== 搜索 performance_api 引用 ==="
grep -r "performance_api" --include="*.py" services/ | grep -v "__pycache__" | grep -v ".pyc"

# 搜索 performance_monitoring 引用
echo "=== 搜索 performance_monitoring 引用 ==="
grep -r "performance_monitoring" --include="*.py" services/ | grep -v "__pycache__" | grep -v ".pyc"
```

**预期结果分析：**
- 如果只在自身文件或 `__pycache__` 中出现 → 可安全删除
- 如果在其他服务中出现 → 需进一步评估
- 如果在 API 路由、健康检查端点中出现 → **不能删除**

**记录结果：**
```
验证结果（填写日期时间）：____________________

model_manager.py:
□ 仅在 model_health.py 中引用 → 可删除
□ 在其他服务中引用 → 需保留
□ 在 API 端点中使用 → 需保留

model_health.py:
□ 未被任何外部文件引用 → 可删除
□ 在健康检查服务中使用 → 需保留

performance_api.py:
□ 未被任何外部文件引用 → 可删除
□ 在监控系统中使用 → 需保留

performance_monitoring.py:
□ 仅在 performance_api.py 中引用 → 可删除
□ 在其他服务中引用 → 需保留
```

### 步骤 1.2：检查配置文件引用

```bash
# 检查 docker-compose.yml
grep -n "model_health\|model_manager\|performance" docker-compose.yml

# 检查 config.yml
grep -n "model_health\|model_manager\|performance" config.yml

# 检查 Dockerfile
grep -n "model_health\|model_manager\|performance" services/workers/faster_whisper_service/Dockerfile
```

**成功标准：**
- ✅ 无配置文件引用这些模块，或引用已失效

### 步骤 1.3：检查 API 路由和健康检查

```bash
# 搜索 FastAPI 路由定义
grep -r "@app\|@router" services/workers/faster_whisper_service/ --include="*.py" | grep -E "model_health|performance"

# 搜索健康检查端点
grep -r "health" services/workers/faster_whisper_service/ --include="*.py" -A 5 -B 5
```

**决策点：**
- 如果发现活跃的 API 端点使用这些模块 → **终止清理，保留所有文件**
- 如果未发现活跃引用 → 继续执行阶段 2

**检查点验证：**
```bash
# 验证检查完成
echo "阶段 1 验证完成时间：$(date)"
echo "决策：继续清理 / 终止清理（选择一个）"
```

---

## 🗑️ 阶段 2：安全清理（高置信度文件）（15分钟）

### 目标
删除明确无用的备份文件和缓存，这些操作风险极低。

### 步骤 2.1：清理备份文件

```bash
# 验证文件存在
ls -lh "services/workers/faster_whisper_service/app/tasks.py.backup"

# 查看文件差异（可选，确认这是真的备份）
diff "services/workers/faster_whisper_service/app/tasks.py" "services/workers/faster_whisper_service/app/tasks.py.backup" | head -50

# 删除备份文件
rm "services/workers/faster_whisper_service/app/tasks.py.backup"

# 验证删除成功
ls -lh "services/workers/faster_whisper_service/app/tasks.py.backup" 2>&1
# 预期输出：No such file or directory
```

**成功标准：**
- ✅ `tasks.py.backup` 文件已删除
- ✅ `tasks.py` 文件仍然存在且未损坏

### 步骤 2.2：清理 Python 缓存目录

```bash
# 查看当前缓存目录
find "services/workers/faster_whisper_service" -type d -name "__pycache__"

# 查看缓存文件数量
find "services/workers/faster_whisper_service" -type f -name "*.pyc" | wc -l

# 删除所有 __pycache__ 目录
find "services/workers/faster_whisper_service" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# 删除所有 .pyc 文件
find "services/workers/faster_whisper_service" -type f -name "*.pyc" -delete

# 验证清理完成
find "services/workers/faster_whisper_service" -type d -name "__pycache__" | wc -l
# 预期输出：0
```

**成功标准：**
- ✅ 所有 `__pycache__` 目录已删除
- ✅ 所有 `.pyc` 文件已删除

### 步骤 2.3：更新 .gitignore

```bash
# 检查 .gitignore 是否已包含 Python 缓存规则
grep -E "__pycache__|\.pyc|\.backup" .gitignore

# 如果未包含，添加规则
cat >> .gitignore << 'EOF'

# Python 缓存
__pycache__/
*.py[cod]
*.pyo
*.pyd

# 备份文件
*.backup
*.bak
EOF

# 验证添加成功
tail -10 .gitignore
```

**成功标准：**
- ✅ `.gitignore` 包含 Python 缓存和备份文件规则

### 步骤 2.4：提交阶段 2 更改

```bash
# 查看当前状态
git status

# 添加删除记录
git add -A

# 创建提交
git commit -m "chore(faster_whisper): 清理备份文件和Python缓存

- 删除 tasks.py.backup（改造前的备份）
- 清理所有 __pycache__ 目录和 .pyc 文件
- 更新 .gitignore 规则防止未来提交缓存文件

影响范围：无业务影响，仅清理冗余文件
风险等级：低"

# 验证提交成功
git log -1 --oneline
```

**成功标准：**
- ✅ Git 显示新的 commit
- ✅ 工作区再次干净

---

## ⚠️ 阶段 3：条件清理（疑似冗余文件）（45分钟）

### 重要声明
**⚠️ 仅在阶段 1 验证确认这些文件未被使用时才执行此阶段！**

### 决策检查点

**在继续前，请确认阶段 1 的验证结果：**

□ `model_manager.py` - 仅被 `model_health.py` 引用，无其他依赖
□ `model_health.py` - 未被任何外部文件引用
□ `performance_api.py` - 未被任何外部文件引用
□ `performance_monitoring.py` - 仅被 `performance_api.py` 引用

**如果上述任一条件不满足，跳过此阶段！**

### 步骤 3.1：创建删除前的详细记录

```bash
# 创建文件内容快照
mkdir -p /tmp/faster_whisper_cleanup_snapshot

# 备份将要删除的文件
cp "services/workers/faster_whisper_service/app/model_manager.py" \
   "/tmp/faster_whisper_cleanup_snapshot/model_manager.py"

cp "services/workers/faster_whisper_service/app/model_health.py" \
   "/tmp/faster_whisper_cleanup_snapshot/model_health.py"

cp "services/workers/faster_whisper_service/app/performance_api.py" \
   "/tmp/faster_whisper_cleanup_snapshot/performance_api.py"

cp "services/workers/faster_whisper_service/app/performance_monitoring.py" \
   "/tmp/faster_whisper_cleanup_snapshot/performance_monitoring.py"

# 记录文件信息
ls -lh services/workers/faster_whisper_service/app/{model_manager,model_health,performance_api,performance_monitoring}.py > /tmp/faster_whisper_cleanup_snapshot/file_info.txt

echo "备份完成时间：$(date)" >> /tmp/faster_whisper_cleanup_snapshot/file_info.txt
```

**成功标准：**
- ✅ 4 个文件已备份到 `/tmp/faster_whisper_cleanup_snapshot/`

### 步骤 3.2：删除疑似冗余文件

```bash
# 删除 model_manager.py
rm "services/workers/faster_whisper_service/app/model_manager.py"
echo "已删除 model_manager.py"

# 删除 model_health.py
rm "services/workers/faster_whisper_service/app/model_health.py"
echo "已删除 model_health.py"

# 删除 performance_api.py
rm "services/workers/faster_whisper_service/app/performance_api.py"
echo "已删除 performance_api.py"

# 删除 performance_monitoring.py
rm "services/workers/faster_whisper_service/app/performance_monitoring.py"
echo "已删除 performance_monitoring.py"

# 验证删除成功
ls -lh services/workers/faster_whisper_service/app/{model_manager,model_health,performance_api,performance_monitoring}.py 2>&1
# 预期输出：全部显示 "No such file or directory"
```

**成功标准：**
- ✅ 4 个文件已从文件系统删除

### 步骤 3.3：验证服务仍可正常启动

```bash
# 如果服务正在运行，先停止
docker-compose stop faster_whisper_service

# 重新构建镜像（可选，如果 Dockerfile 有变化）
docker-compose build faster_whisper_service

# 启动服务
docker-compose up -d faster_whisper_service

# 等待服务启动（30秒）
sleep 30

# 检查服务状态
docker-compose ps faster_whisper_service

# 查看服务日志（最后50行）
docker-compose logs --tail=50 faster_whisper_service

# 检查是否有导入错误
docker-compose logs faster_whisper_service | grep -i "importerror\|modulenotfounderror"
```

**成功标准：**
- ✅ 服务启动成功（状态为 "Up"）
- ✅ 日志中无 ImportError 或 ModuleNotFoundError
- ✅ 日志中无其他明显错误

**失败处理：**
如果服务启动失败或有错误：

```bash
# 立即回滚
cp /tmp/faster_whisper_cleanup_snapshot/*.py services/workers/faster_whisper_service/app/

# 重启服务
docker-compose restart faster_whisper_service

# 验证回滚成功
docker-compose ps faster_whisper_service
```

### 步骤 3.4：功能测试（如果服务启动成功）

```bash
# 测试 1：检查 Celery worker 是否正常
docker-compose exec faster_whisper_service celery -A app.celery_app inspect active

# 测试 2：检查任务队列连接
docker-compose exec faster_whisper_service celery -A app.celery_app inspect stats

# 测试 3：运行简单的转录任务（可选，需要准备测试音频）
# 这一步需要根据实际 API 接口调整
```

**成功标准：**
- ✅ Celery worker 正常响应
- ✅ 可以连接到 Redis 队列
- ✅ （可选）测试任务执行成功

### 步骤 3.5：提交阶段 3 更改

**⚠️ 仅在所有验证通过后才执行提交！**

```bash
# 查看删除的文件
git status

# 添加删除记录
git add -A

# 创建提交
git commit -m "refactor(faster_whisper): 移除subprocess改造后的冗余模块

移除以下不再使用的模块：
- model_manager.py：原用于直接加载模型，subprocess模式下不再需要
- model_health.py：依赖model_manager的健康检查
- performance_api.py：独立的性能监控API
- performance_monitoring.py：性能监控模块

改造背景：
服务已从'直接加载模型'改为'subprocess隔离'模式，
使用 faster_whisper_infer.py 独立脚本执行推理。

验证记录：
- 阶段1：确认无外部依赖引用这些模块
- 阶段3：服务启动成功，功能测试通过
- 备份位置：/tmp/faster_whisper_cleanup_snapshot/

影响范围：无业务影响，移除未使用代码
风险等级：中等（已充分验证）
回滚方案：git revert 或从备份恢复"

# 验证提交成功
git log -1 --stat
```

**成功标准：**
- ✅ Git commit 包含 4 个文件的删除记录
- ✅ Commit message 清晰描述了更改原因和验证过程

---

## ✅ 阶段 4：最终验证和文档更新（30分钟）

### 步骤 4.1：运行完整测试套件

```bash
# 如果项目有测试套件，运行测试
# 以下命令需要根据实际项目调整

# 运行单元测试（如果存在）
docker-compose exec faster_whisper_service pytest tests/unit/ -v

# 运行集成测试（如果存在）
docker-compose exec faster_whisper_service pytest tests/integration/ -v

# 或使用项目特定的测试命令
# docker-compose exec faster_whisper_service python -m pytest
```

**成功标准：**
- ✅ 所有测试通过（或失败数量未增加）
- ✅ 无新增的测试错误

### 步骤 4.2：更新 README 文档

检查并更新以下文档（如果需要）：

```bash
# 编辑服务 README
# 文件位置：services/workers/faster_whisper_service/README.md

# 需要更新的内容：
# 1. 移除对已删除模块的引用
# 2. 更新架构说明（强调subprocess隔离模式）
# 3. 更新文件结构列表
```

**文档更新建议：**

在 `services/workers/faster_whisper_service/README.md` 中：

1. **架构说明部分** 应明确说明：
   ```markdown
   ## 架构设计

   本服务采用 **subprocess 隔离模式** 执行语音转录：

   - **Celery Task (tasks.py)**: 接收任务，准备参数
   - **独立推理脚本 (faster_whisper_infer.py)**: 在独立进程中加载模型并执行推理
   - **进程通信**: 通过临时 JSON 文件传递结果

   优势：
   - 解决 Celery prefork pool 与 CUDA 初始化冲突
   - 进程隔离，避免内存泄漏
   - 模型加载失败不影响 Celery worker
   ```

2. **文件结构部分** 应移除已删除文件的说明

### 步骤 4.3：创建清理总结报告

```bash
# 创建清理总结文档
cat > /tmp/faster_whisper_cleanup_report.md << 'EOF'
# faster_whisper_service 清理总结报告

**执行日期：** $(date +%Y-%m-%d)
**执行人：** [填写执行人]
**分支：** feature/faster-whisper-subprocess-isolation

## 清理概览

### 已删除文件（阶段2）
- `app/tasks.py.backup` - 改造前备份文件
- 所有 `__pycache__/` 目录
- 所有 `.pyc` 编译文件

### 已删除文件（阶段3）
- `app/model_manager.py` - 原模型管理器
- `app/model_health.py` - 模型健康检查
- `app/performance_api.py` - 性能监控API
- `app/performance_monitoring.py` - 性能监控模块

### 保留文件
- 核心功能模块（tasks.py, faster_whisper_infer.py等）
- 说话人处理模块（speaker_diarization.py等）
- 测试脚本（test_*.py）
- 所有配置和文档文件

## 验证结果

- [ ] 服务启动成功
- [ ] Celery worker 正常
- [ ] 测试套件通过
- [ ] 无导入错误
- [ ] 文档已更新

## 回滚信息

**备份位置：** /tmp/faster_whisper_cleanup_snapshot/

**Git 回滚命令：**
```bash
# 回滚到清理前（如果在同一天执行）
git log --oneline --since="1 day ago"
git reset --hard [清理前的commit hash]
```

## 后续建议

1. 监控服务运行 24-48 小时，确保无异常
2. 如果一切正常，可删除临时备份：`rm -rf /tmp/faster_whisper_cleanup_snapshot/`
3. 考虑将此清理经验应用于其他服务
EOF

# 查看报告
cat /tmp/faster_whisper_cleanup_report.md
```

### 步骤 4.4：最终检查清单

**执行以下最终检查：**

```bash
# 1. 检查 Git 状态
git status
# 预期：clean 或只有文档更新未提交

# 2. 查看所有相关 commits
git log --oneline --since="1 day ago"

# 3. 检查服务健康状态
docker-compose ps faster_whisper_service

# 4. 查看最新日志
docker-compose logs --tail=20 faster_whisper_service

# 5. 验证目录结构
tree services/workers/faster_whisper_service/app -L 1
```

**最终检查清单：**

- [ ] 工作区干净或只有文档更新
- [ ] 至少有 1 个（阶段2）或 2 个（阶段2+3）新 commit
- [ ] 服务状态为 "Up"
- [ ] 最新日志无错误
- [ ] 目录结构清晰，无冗余文件

---

## 🔄 回滚方案

### 场景 1：阶段 2 执行后需要回滚

```bash
# 方法 1：Git reset（如果还未 push）
git log --oneline -5
git reset --hard [阶段2执行前的commit hash]

# 方法 2：Git revert（如果已 push）
git revert [阶段2的commit hash]
```

### 场景 2：阶段 3 执行后需要回滚

```bash
# 方法 1：从备份恢复文件
cp /tmp/faster_whisper_cleanup_snapshot/*.py services/workers/faster_whisper_service/app/

# 重启服务
docker-compose restart faster_whisper_service

# 提交恢复
git add services/workers/faster_whisper_service/app/
git commit -m "revert: 恢复删除的模块文件

由于 [具体原因]，需要恢复以下文件：
- model_manager.py
- model_health.py
- performance_api.py
- performance_monitoring.py"

# 方法 2：Git reset（如果还未 push）
git log --oneline -5
git reset --hard [阶段3执行前的commit hash]

# 方法 3：Git revert（如果已 push）
git revert [阶段3的commit hash]
```

### 场景 3：服务启动失败的紧急回滚

```bash
# 立即执行
git reset --hard HEAD~1  # 回滚最后一次 commit
docker-compose restart faster_whisper_service

# 或从备份恢复
cp /tmp/faster_whisper_cleanup_snapshot/*.py services/workers/faster_whisper_service/app/
docker-compose restart faster_whisper_service
```

---

## 📊 预期结果

### 代码库改善
- **减少文件数量：** 5-6 个文件
- **减少代码行数：** 约 500-800 行（估计）
- **清理缓存：** 所有 `__pycache__` 和 `.pyc`

### 可维护性提升
- 移除混淆的备份文件
- 清晰的架构边界（subprocess 模式）
- 减少开发者困惑

### 性能影响
- **构建时间：** 可能略微减少（更少的文件）
- **运行时性能：** 无影响（未使用的代码不影响运行时）
- **Docker 镜像大小：** 略微减小

---

## 🚨 风险和缓解措施

### 风险 1：误删仍在使用的文件
**概率：** 低（通过阶段1充分验证）
**影响：** 高（服务启动失败）
**缓解：**
- 阶段1 的彻底验证
- 阶段3 的服务启动测试
- 完整的备份和回滚方案

### 风险 2：删除后发现隐藏依赖
**概率：** 低-中
**影响：** 中（某些边缘功能失效）
**缓解：**
- 运行完整测试套件
- 监控生产日志 24-48 小时
- 保留备份至少 1 周

### 风险 3：Docker 缓存问题
**概率：** 低
**影响：** 低（重建即可解决）
**缓解：**
- 删除后重建镜像：`docker-compose build --no-cache faster_whisper_service`

---

## 📅 执行时间表

**推荐执行时间：** 非高峰期或测试环境

| 阶段 | 预估时间 | 可独立执行 | 回滚难度 |
|------|---------|----------|---------|
| 前置检查 | 10分钟 | 是 | N/A |
| 阶段1（验证） | 30分钟 | 是 | N/A |
| 阶段2（安全清理） | 15分钟 | 是 | 低 |
| 阶段3（条件清理） | 45分钟 | 否，依赖阶段1 | 中 |
| 阶段4（验证文档） | 30分钟 | 否，依赖阶段2/3 | 低 |
| **总计** | **2-3小时** | - | - |

**建议分批执行：**
- **第一次：** 执行阶段1 + 阶段2，观察 24 小时
- **第二次：** 确认无问题后执行阶段3 + 阶段4

---

## ✅ 成功标准

### 技术指标
- [ ] 所有目标文件已删除
- [ ] Git 历史清晰，commit message 规范
- [ ] 服务正常启动运行
- [ ] 测试套件通过（或失败数未增加）
- [ ] 无导入错误或运行时错误

### 文档指标
- [ ] README 更新准确反映当前架构
- [ ] 清理总结报告已创建
- [ ] 回滚方案已验证可行

### 业务指标
- [ ] 无业务功能受影响
- [ ] 无性能退化
- [ ] 团队成员理解了清理内容

---

## 📞 支持和联系

**执行过程中遇到问题：**

1. **立即停止** 当前操作
2. **不要继续** 执行后续步骤
3. **保存当前状态**（git commit 或截图）
4. **查看回滚方案** 评估是否需要回滚
5. **记录问题** 详细描述错误信息

**问题报告模板：**
```
问题描述：[具体错误信息]
执行阶段：[阶段1/2/3/4]
执行步骤：[具体步骤编号]
错误日志：[粘贴相关日志]
当前状态：[服务是否运行，Git状态等]
```

---

## 📚 参考资料

- **架构改造 Commit：** cb77ed7 (refactor: 改造 _execute_transcription 使用 subprocess 隔离)
- **推理脚本添加：** 06f5b30 (feat: 添加 faster_whisper 独立推理脚本)
- **研究报告：** [链接到研究报告，如果已保存]
- **项目文档：** services/workers/faster_whisper_service/README.md

---

## 🎯 执行签核

**执行前确认（必填）：**

- [ ] 我已完整阅读此计划
- [ ] 我理解每个步骤的目的和风险
- [ ] 我已准备好回滚方案
- [ ] 我已备份当前状态
- [ ] 我有足够时间完成（2-3小时）

**签名：** ________________
**日期：** ________________

**执行后确认（必填）：**

- [ ] 所有阶段已成功完成
- [ ] 服务运行正常
- [ ] 测试通过
- [ ] 文档已更新
- [ ] 清理总结已创建

**签名：** ________________
**日期：** ________________

---

**计划版本：** v1.0
**最后更新：** 2025-10-21
**下次审核：** 执行后 1 周
