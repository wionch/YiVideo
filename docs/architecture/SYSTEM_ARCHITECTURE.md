# 系统总体架构设计 (SYSTEM_ARCHITECTURE.md)

**版本**: 1.1
**状态**: 讨论中

## 1. 核心思想：动态工作流引擎

本系统的核心定位是一个**动态、可配置的AI视频处理工作流引擎**。其设计目标是脱离写死的、单一的处理流水线，转向一个能够根据用户需求，灵活地、即插即用地编排组合各种原子化AI功能（如语音识别、OCR、语言模型、文本转语音等）的平台。

系统的驱动力是“**配置而非编码**”。通过一份描述“做什么”和“怎么做”的工作流配置文件，系统应能自动构建并执行一个复杂的处理链条，而无需修改任何服务端的代码。

---

## 2. 架构组件与职责

系统采用标准的微服务架构，各组件职责清晰、独立部署。

```mermaid
graph TD
    A[用户/客户端] -- "1. 发起HTTP请求 (含workflow_config)" --> B(API网关);
    
    B -- "2. 动态构建任务链" --> C(Celery Broker);
    B -- "8. 状态查询" --> D(State Store - Redis);

    C -- "3. 任务分发" --> W1[ffmpeg_service];
    C -- " " --> W2[faster_whisper_service];
    C -- " " --> W3[pyannote_audio_service];
    C -- " " --> W4[paddleocr_service];
    C -- " " --> W4[llm_service];

    W1 -- "4. 更新状态" --> D;
    W2 -- " " --> D;
    W3 -- " " --> D;
    W4 -- " " --> D;

    W1 -- "5. 读写文件" --> E(共享存储);
    W2 -- " " --> E;
    W3 -- " " --> E;
    W4 -- " " --> E;

    W1 -- "6. 竞争GPU" --> G((GPU Hardware));
    W2 -- " " --> G;
    W3 -- " " --> G;

    subgraph AI Workers
        W1
        W2
        W3
        W4
    end
```

- **API网关 (`api_gateway`)**: **系统的总入口和大脑**。
  - 接收用户的HTTP请求，解析`workflow_config`。
  - **动态构建** Celery任务链，并启动工作流。
  - 创建并管理Redis中的工作流状态记录。
  - 提供工作流状态查询接口。
  - **集成GPU锁监控系统**：提供实时监控、健康检查和自动恢复功能。

- **AI功能服务 (Workers)**: **系统的“手和脚”**，每个服务都是一个独立的Celery worker。
  - `ffmpeg_service`: 基础视频操作。
  - `faster_whisper_service`: 语音识别（ASR）。
  - `pyannote_audio_service`: 说话人分离。
  - `paddleocr_service`: 光学字符识别（OCR）。
  - `llm_service`: (新) 与大语言模型交互（校对、翻译）。
  - `indextts_service` / `gptsovits_service`: 文本转语音（TTS）。

- **基础设施 (Infrastructure)**:
  - **Celery Broker (Redis)**: 任务消息队列。
  - **State Store (Redis)**: 集中化的工作流JSON状态存储。
  - **共享存储**: 存放所有视频、音频、图片等文件。

---

## 3. 关键设计

### 3.1. API 设计与 `workflow_config`
- **端点**: `POST /v1/workflows`
- **请求体 (Body)**:
  ```json
  {
      "video_path": "/share/videos/input/example.mp4",
      "workflow_config": {
          "subtitle_generation": { "strategy": "asr", "provider": "faster_whisper" },
          "subtitle_refinement": { "strategy": "llm_proofread", "provider": "gemini" }
      }
  }
  ```

### 3.2. 标准化工作流上下文 (Standardized Workflow Context)
所有任务间传递一个统一的、不断丰富的“工作流上下文”字典。
- **数据结构**:
  ```json
  {
      "workflow_id": "...",
      "input_params": { "video_path": "..." },
      "shared_storage_path": "/share/workflows/...",
      "stages": {
          "subtitle_generation": {
              "status": "SUCCESS",
              "output": { "subtitle_file": "/path/to/raw.srt" }
          },
          "subtitle_refinement": { "status": "PENDING" }
      },
      "error": null
  }
  ```
- **传递方式**: 作为每个Celery任务的唯一参数和返回值。

### 3.3. 标准化任务接口 (Standardized Task Interface)
所有worker中的Celery任务必须遵循统一的函数签名。
- **函数签名**: `def standard_task_interface(self: Task, context: dict) -> dict:`

### 3.4. 分布式GPU锁与监控系统

#### 3.4.1 智能GPU锁机制
采用基于Redis的`@gpu_lock`装饰器，通过`SETNX`原子命令实现，支持智能轮询和指数退避算法。

**核心特性**：
- **V3智能锁管理器**：提供详细的统计信息和健康状态监控
- **智能轮询**：支持指数退避和随机抖动，避免thundering herd问题
- **心跳集成**：任务执行期间自动更新心跳状态
- **自动恢复**：分级超时处理和自动释放机制

#### 3.4.2 GPU锁监控系统
集成的GPU锁监控系统提供实时监控和自动恢复能力：

**监控组件**：
- **GPULockMonitor**：主动监控GPU锁状态，定期健康检查
- **TaskHeartbeatManager**：管理任务心跳，检测任务存活状态
- **TimeoutManager**：分级超时处理（警告/软超时/硬超时）
- **监控API**：完整的RESTful API接口

**监控能力**：
- 实时锁状态查询
- 锁获取成功率统计
- 任务心跳监控
- 自动死锁检测和恢复
- 历史记录和性能分析

#### 3.4.3 配置管理
GPU锁系统支持动态配置调整：

```yaml
gpu_lock:
  poll_interval: 0.5          # 轮询间隔（秒）
  max_wait_time: 300         # 最大等待时间（5分钟）
  lock_timeout: 600          # 锁超时时间（10分钟）
  exponential_backoff: true  # 启用指数退避
  max_poll_interval: 5        # 最大轮询间隔（秒）

gpu_lock_monitor:
  monitor_interval: 30        # 监控间隔（秒）
  timeout_levels:
    warning: 1800            # 警告级别（30分钟）
    soft_timeout: 3600       # 软超时（60分钟）
    hard_timeout: 7200       # 硬超时（120分钟）
  heartbeat:
    interval: 60             # 心跳间隔（秒）
    timeout: 300             # 心跳超时（5分钟）
```

### 3.5. 状态追踪与持久化
工作流的完整状态记录被持久化在Redis中。
- **键**: `workflow_state:{workflow_id}`
- **值**: 一个详细的JSON对象，记录工作流生命周期。
- **更新**: `api_gateway`创建记录；每个任务执行前后更新自己的状态。
- **过期**: 为每条记录设置可配置的TTL（例如7天）。

---

## 4. 示例工作流：OCR字幕提取

为了具体说明各组件如何协同工作，我们以一个从视频中提取字幕的OCR工作流为例，分解其详细步骤。

1.  **[用户]**: 用户向`api_gateway`的`POST /v1/workflows`端点发起请求，`workflow_config`中指定`"strategy": "ocr"`。

2.  **[API网关: 入口]**: `api_gateway`服务接收到请求。它负责：
    *   生成一个全局唯一的 `workflow_id`。
    *   在Redis中创建初始的状态JSON，并设置TTL。
    *   根据`"strategy": "ocr"`，构建一个Celery任务链: `chain(extract_keyframes.s() | detect_subtitle_area.s() | crop_subtitle_images.s() | perform_ocr.s() | postprocess_and_finalize.s())`。
    *   调用 `.apply_async()` 启动任务链，并将初始的`WorkflowContext`作为参数传入。
    *   立即向用户返回 `workflow_id`。

3.  **[F模块: GPU任务] `extract_keyframes`**: F模块的worker获取任务。
    *   **获取GPU锁**。
    *   为区域检测高效抽取少量关键帧。
    *   更新Redis中的状态记录。
    *   返回包含帧路径的`WorkflowContext`。

4.  **[P模块: 回调任务] `detect_subtitle_area`**: P模块的worker获取任务。
    *   **获取GPU锁**。
    *   调用`SubtitleAreaDetector`计算字幕精确坐标。
    *   **负责删除已用过的关键帧图片**。
    *   更新Redis状态，返回包含坐标的`WorkflowContext`。

5.  **[F模块: GPU并发任务] `crop_subtitle_images`**: F模块的worker获取任务。
    *   **获取GPU锁**。
    *   高效地裁剪出所有字幕条图片。
    *   更新Redis状态，返回包含图片路径列表的`WorkflowContext`。

6.  **[P模块: 回调任务&GPU任务] `perform_ocr`**: P模块的worker获取任务。
    *   **获取GPU锁**。
    *   调用`MultiProcessOCREngine`并发执行OCR。
    *   **负责删除已用过的字幕条图片**。
    *   更新Redis状态，返回包含结构化OCR结果的`WorkflowContext`。

7.  **[P模块: 回调任务] `postprocess_and_finalize`**: P模块的worker获取任务。
    *   接收结构化的OCR结果，进行合并、排序和格式化，生成最终的字幕文件。
    *   **负责删除整个工作流的临时目录**。
    *   将Redis中顶层的`status`更新为`SUCCESS`，并填充`result`字段。

---

## 5. 监控系统架构扩展

### 5.1 GPU锁监控系统架构

系统集成了完整的GPU锁监控和自动恢复机制：

```mermaid
graph TD
    subgraph "API网关监控层"
        M1[GPULockMonitor]
        M2[TaskHeartbeatManager]
        M3[TimeoutManager]
        M4[监控API端点]
    end

    subgraph "Redis存储层"
        R1[GPU锁状态]
        R2[任务心跳数据]
        R3[监控统计数据]
        R4[配置信息]
    end

    subgraph "Worker服务层"
        W1[paddleocr_service]
        W2[ffmpeg_service]
        W3[faster_whisper_service]
        W4[pyannote_audio_service]
        W5[其他GPU服务]
    end

    M1 --> R1
    M2 --> R2
    M3 --> R3
    M4 --> R1
    M4 --> R2
    M4 --> R3

    W1 -- "@gpu_lock装饰器" --> R1
    W1 -- "心跳更新" --> R2
    W2 -- "@gpu_lock装饰器" --> R1
    W2 -- "心跳更新" --> R2
    W3 -- "@gpu_lock装饰器" --> R1
    W3 -- "心跳更新" --> R2

    M1 -- "健康检查" --> W1
    M1 -- "健康检查" --> W2
    M1 -- "健康检查" --> W3
    M2 -- "心跳检测" --> W1
    M2 -- "心跳检测" --> W2
    M2 -- "心跳检测" --> W3
    M3 -- "超时处理" --> R1
```

### 5.2 监控数据流

1. **锁状态监控**: GPULockMonitor定期检查GPU锁状态
2. **心跳更新**: 任务执行期间定期更新心跳
3. **健康检查**: 系统自动评估锁健康状态
4. **超时处理**: 分级超时机制自动处理异常
5. **API查询**: 外部系统通过REST API查询监控信息

### 5.3 自动恢复机制

系统提供多层次的自动恢复能力：

- **警告级别**: 记录警告日志，通知运维
- **软超时**: 尝试优雅终止任务
- **硬超时**: 强制释放锁，清理资源
- **心跳超时**: 标记任务为死亡，清理相关资源

**文档版本**: 1.2
**更新日期**: 2025-09-28
**更新内容**: 新增GPU锁监控系统架构说明
