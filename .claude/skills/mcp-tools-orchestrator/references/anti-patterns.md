# 反模式案例库

> 本文件记录常见违规模式及其后果，用于教学和警示。

---

## 反模式 1：盲写（Blind Coding）

### 定义
未用 serena 读取文件/符号上下文就直接产生代码补丁。

### 典型表现

❌ **错误示例**：
```
用户：修复 FunASR 模型加载的 bug
Agent：我猜测问题在 load_model 函数，给你一个补丁：
[直接给出 20 行代码修改]
```

✅ **正确做法**：
```
用户：修复 FunASR 模型加载的 bug
Agent：
1. serena.activate_project("YiVideo")
2. serena.find_symbol("load_model", relative_path="services/workers/funasr_service/")
3. [读取当前实现]
4. serena.find_referencing_symbols（评估影响面）
5. [基于实际代码给出最小改动]
```

### 后果
- 补丁与实际代码不匹配（函数签名、变量名错误）
- 破坏现有逻辑（未考虑边缘情况）
- 引入新 bug（未评估调用方影响）

### 真实案例
**场景**：用户要求"优化 Paraformer 模型加载逻辑"
- **盲写版本**：agent 直接给出"改用懒加载"的代码，但实际代码已经是懒加载
- **正确版本**：serena 读取后发现已优化，建议"当前已是最佳实践"

---

## 反模式 2：幻觉 API（Hallucinated APIs）

### 定义
未用 context7 或一手文档验证就使用可能不存在的接口。

### 典型表现

❌ **错误示例**：
```
用户：FastAPI 如何做异步依赖注入？
Agent：使用 `AsyncDepends` 装饰器：
@app.get("/items")
async def read_items(db = AsyncDepends(get_db)):
    ...
```
（实际 FastAPI 没有 `AsyncDepends`，只有 `Depends`）

✅ **正确做法**：
```
用户：FastAPI 如何做异步依赖注入？
Agent：
1. context7.resolve_library_id("fastapi")
2. context7.query_docs("/tiangolo/fastapi", "async dependency injection")
3. [基于官方文档给出正确示例：用 Depends + async def]
```

### 后果
- 代码无法运行（导入错误、语法错误）
- 浪费用户时间调试"不存在的 API"
- 降低信任度

### 真实案例
**场景**：用户要求"集成 Pydantic v2 的配置验证"
- **幻觉版本**：agent 使用 `@validator` 装饰器（Pydantic v1 语法，v2 已废弃）
- **正确版本**：context7 查询后使用 `@field_validator`（v2 正确语法）

---

## 反模式 3：跳跃结论（Jump to Solution）

### 定义
复杂问题不经 sequential-thinking 分析就给"尝试性修复"。

### 典型表现

❌ **错误示例**：
```
用户：FunASR 推理速度慢，如何优化？
Agent：直接建议"改用 batch 推理"
[未分析瓶颈在哪里：模型加载？VAD？解码？]
```

✅ **正确做法**：
```
用户：FunASR 推理速度慢，如何优化？
Agent：
1. sequential-thinking 分解：
   - thought_1: 定位瓶颈（模型加载？推理？后处理？）
   - thought_2: 列举可能方案（batch/量化/缓存）
   - thought_3: 评估权衡（精度 vs 速度）
2. serena 读取当前实现，确认瓶颈
3. 给出针对性建议（基于实际瓶颈）
```

### 后果
- 解决了表面问题但未触及根本（如瓶颈在 VAD，优化 batch 无效）
- 引入不必要的复杂度（如已经是 batch，再套一层）
- 浪费时间在错误方向

### 真实案例
**场景**：用户反馈"字幕生成耗时 2 分钟"
- **跳跃版本**：agent 直接建议"并行处理"
- **正确版本**：sequential-thinking 分析后发现瓶颈在 LLM API 调用（串行），建议"批量合并 prompt"（耗时降到 20 秒）

---

## 反模式 4：无证据输出（Uncited Facts）

### 定义
外部事实（最新信息/版本变化/官方说明）未提供来源链。

### 典型表现

❌ **错误示例**：
```
用户：FunASR 最新版本有什么变化？
Agent：最新版本 v1.2.0 增加了 SenseVoice 模型。
[未提供来源，用户无法验证]
```

✅ **正确做法**：
```
用户：FunASR 最新版本有什么变化？
Agent：
1. brave.web_search("FunASR release notes 2024")
2. exa.web_search("FunASR changelog")
3. tavily.extract("https://github.com/modelscope/FunASR/releases")
4. 输出：
   - 最新版本：v1.2.0（2024-01-15）
   - 关键变化：新增 SenseVoice
   - 来源：[GitHub Release](链接) + [ModelScope 官方](链接)
```

### 后果
- 用户无法验证信息真实性
- 过时信息导致错误决策
- 版本冲突（如推荐的库版本不兼容）

### 真实案例
**场景**：用户问"Whisper v3 是否支持中文？"
- **无证据版本**：agent 回答"支持"（但未说明 WER 指标）
- **有证据版本**：brave + exa 找到官方 benchmark，回答"支持，中文 WER 4.5%，来源：OpenAI 官方 blog"

---

## 反模式 5：批量操作不用 filesystem

### 定义
用循环 Read/Write/Edit 处理多文件，而不用 filesystem 批量工具。

### 典型表现

❌ **错误示例**：
```
用户：批量修改所有 config.yml 的 redis_db
Agent：
for file in [file1, file2, ...]:
    Read(file)
    Edit(file, ...)
[逐个调用内置工具]
```

✅ **正确做法**：
```
用户：批量修改所有 config.yml 的 redis_db
Agent：
1. filesystem.search_files(pattern="**/config.yml")
2. filesystem.read_multiple_files(paths=[...])
3. filesystem.edit_file(path=file1, dryRun=True)  # 预览
4. [用户确认后] filesystem.edit_file(dryRun=False)
```

### 后果
- Token 消耗大（每次 Read/Write 都计 token）
- 无法预览 diff（直接改，出错难回滚）
- 操作不原子（中途失败，部分文件已改）

### 真实案例
**场景**：用户要求"统一所有 Worker 的 timeout 配置"
- **循环版本**：逐个 Read + Edit，消耗 5000 tokens
- **批量版本**：filesystem.search + read_multiple + edit(dryRun)，消耗 1000 tokens，还能预览 diff

---

## 反模式 6：忽略 serena 项目激活

### 定义
serena 返回 "No active project" 后，直接放弃使用而不激活。

### 典型表现

❌ **错误示例**：
```
serena.find_symbol(...) → "No active project"
Agent：serena 不可用，我改用 grep
[直接降级，未尝试激活]
```

✅ **正确做法**：
```
serena.find_symbol(...) → "No active project"
Agent：
1. serena.activate_project("YiVideo")
2. [立即重试] serena.find_symbol(...)
3. [如仍失败才降级]
```

### 后果
- 失去符号级定位能力（降级到文本搜索）
- 无法评估重构影响面
- 容易出现"盲写"问题

### 真实案例
**场景**：用户要求"查找 GPU 锁的调用链"
- **未激活版本**：grep 搜索"gpu_lock"（找到 50 个文本匹配，但无法区分定义/引用/注释）
- **激活版本**：serena 定位到装饰器定义 + 12 个实际调用点，清晰展示调用链

---

## 反模式 7：不做交叉验证

### 定义
时间敏感或高风险结论只用单一来源，未互证。

### 典型表现

❌ **错误示例**：
```
用户：FunASR v1.2 是否修复了 VAD bug？
Agent：[只调用 brave-search 一次]
根据搜索结果，已修复。
```

✅ **正确做法**：
```
用户：FunASR v1.2 是否修复了 VAD bug？
Agent：
1. brave.web_search("FunASR v1.2 VAD bug fix")
2. exa.web_search("FunASR VAD issue")
3. tavily.extract(GitHub Release Notes)
4. 输出：
   - 结论：v1.2 已修复
   - 证据 1：GitHub Release Notes [链接]
   - 证据 2：Issue #123 marked as closed [链接]
   - 双来源互证，可信度高
```

### 后果
- 信息不准确（单一来源可能过时/错误）
- 用户基于错误信息做决策
- 浪费时间调试"已修复的 bug"

### 真实案例
**场景**：用户问"Whisper v3 是否支持实时流式推理？"
- **单来源版本**：brave 搜到一篇博客说"支持"（实际是社区魔改版）
- **双来源版本**：brave + 官方文档，发现官方不支持，博客指的是第三方封装

---

## 反模式 8：文件操作不预览

### 定义
直接 edit_file(dryRun=False)，不先预览 diff。

### 典型表现

❌ **错误示例**：
```
Agent：我帮你改配置
filesystem.edit_file(path="config.yml", edits=[...], dryRun=False)
[直接应用，未预览]
```

✅ **正确做法**：
```
Agent：我先预览改动
filesystem.edit_file(path="config.yml", edits=[...], dryRun=True)
[输出 diff 供用户确认]
用户确认后：
filesystem.edit_file(..., dryRun=False)
```

### 后果
- 误改配置（如正则匹配错误，改了不该改的行）
- 难以回滚（用户不知道原值是什么）
- 破坏工作环境（如改坏 docker-compose.yml）

### 真实案例
**场景**：用户要求"修改 Redis DB 配置"
- **不预览版本**：直接改，结果把注释中的 `redis_db` 也改了，导致配置文件损坏
- **预览版本**：dryRun 显示 diff，用户发现问题并调整正则

---

## 总结：如何避免反模式

| 反模式 | 检查点 | 快速自检 |
|-------|-------|---------|
| 盲写 | 是否先用 serena 读取？ | "我知道这个文件的当前内容吗？" |
| 幻觉 API | 是否用 context7 验证？ | "这个 API 我 100% 确定存在吗？" |
| 跳跃结论 | 是否先用 sequential-thinking？ | "我分析过根本原因了吗？" |
| 无证据 | 是否提供来源链？ | "用户能验证这个信息吗？" |
| 忽略批量工具 | 是否用 filesystem？ | "我在循环调用 Read/Write 吗？" |
| 未激活项目 | serena 失败后是否先激活？ | "我尝试过 activate_project 了吗？" |
| 不交叉验证 | 时间敏感结论是否双来源？ | "这是高风险结论吗？" |
| 不预览 | edit_file 是否先 dryRun？ | "我让用户看到改动了吗？" |

**记住**：技能的核心是"约束层"，不是"操作手册"。这些反模式是真实场景中常见的违规，避免它们就能显著提升输出质量。
