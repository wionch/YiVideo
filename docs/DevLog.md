# 开发日志

## 合并字幕条功能调试

```markdown
请检查`paddleocr.create_stitched_images`是否支持input_data方式的参数传入? 输出传入的参数列表和说明

  | 参数名                 | 类型        | 来源         | 说明            | 默认值 |
  |---------------------|-----------|------------|---------------|-----|
  | concat_batch_size   | int       | 全局配置或工作流参数 | 每个拼接图包含的字幕条数量 | 10  |
  | stitching_workers   | int       | 全局配置或工作流参数 | 并发处理进程数       | 10  |
  | cropped_images_path | str       | 上游任务输出     | 输入的裁剪图像目录路径   | 必填  |
  | subtitle_area       | dict/list | 上游任务输出     | 字幕区域坐标信息      | 必填  |
  
参数是否支持input_data方式的传参? 如下: 如果支持请同步文档@docs\technical\reference\WORKFLOW_NODES_REFERENCE.md 
"""
{
    "task_name": "ffmpeg.crop_subtitle_images",
    "task_id": "task_id",
    "callback": "{{ $execution.resumeUrl }}/t3",
    "input_data": {
        "video_path": "http://host.docker.internal:9000/yivideo/task_id/223.mp4",
        "subtitle_area":  [
                0,
                607,
                1280,
                679
              ],
        "upload_cropped_images_to_minio": true
    }
}
"""

 ## 目标
 - 实现`cropped_images_path`支持minio目录下载: 如果此参数传入的是http格式完整链接, 尝试使用项目中mino目录下载模块负责下载
 - 输出结果`multi_frames_path`实现mino目录上传: 拼接完成后上传到minio. 并返回minio链接
 
 请先制定详细的施工计划todolist, 确定后再开始施工
  

```

### 是否为gpu任务

请从代码逻辑上确定`paddleocr.create_stitched_images`是否是gpu任务?

答案: 不是gpu任务

### 是否支持单步任务参数输入

* 请确定`paddleocr.create_stitched_images`是否支持单步任务的参数传入, 并详细介绍

  ```markdown
   📋 支持情况

    答案：✅ 支持 - 该函数通过统一的参数获取机制支持单步任务传入参数。

    🔧 参数传入机制

    1. API调用方式

    POST http://localhost:8000/v1/tasks
    Content-Type: application/json

    {
      "task_name": "paddleocr.create_stitched_images",
      "task_id": "task-123",
      "input_data": {
        "cropped_images_path": "/share/cropped_images/frames",
        "subtitle_area": {"x1": 0, "y1": 100, "x2": 1920, "y2": 200},
        "upload_stitched_images_to_minio": true,
        "delete_local_stitched_images_after_upload": false
      }
    }

    2. 参数处理流程

    步骤1: API网关接收请求（single_task_api.py:27）
    - 接收 input_data 参数
    - 创建任务上下文

    步骤2: 创建任务上下文（single_task_executor.py:196）
    context = {
        "workflow_id": task_id,
        "input_params": {
            "task_name": task_name,
            "input_data": input_data,  # 单步任务参数在这里
            "callback_url": callback_url
        },
        # ...
    }

    步骤3: 任务中获取参数（tasks.py:436-478）
    # 获取单步任务传入的参数（为空，因为单步任务不使用node_params）
    node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})

    # 通过 get_param_with_fallback 自动从 input_data 获取参数
    input_dir_str = get_param_with_fallback(
        "cropped_images_path",
        resolved_params,  # 空，因为单步任务没有node_params
        workflow_context,
        fallback_from_stage="ffmpeg.crop_subtitle_images"  # 回退到上游节点
    )

    3. 参数获取优先级（parameter_resolver.py:89）

    系统使用四层参数获取优先级：
    1. node_params - 工作流模式的节点参数（工作流专用）
    2. input_data - 单步任务传入的参数或动态引用（单步任务专用）
    3. 上游节点输出 - 自动从前置阶段获取
    4. 默认值 - 函数调用时指定的默认值

    📝 支持的参数

    必需参数（可通过单步任务传入）

    cropped_images_path: str  # 裁剪图像目录路径
    subtitle_area: dict       # 字幕区域坐标 {"x1": 0, "y1": 100, "x2": 1920, "y2": 200}

    可选参数（可通过单步任务传入）

    upload_stitched_images_to_minio: bool = True  # 是否上传到MinIO
    delete_local_stitched_images_after_upload: bool = False  # 上传后删除本地文件

    配置参数（自动从config.yml读取）

    batch_size: int = 50      # 拼接批大小（来自config.yml: pipeline.concat_batch_size）
    max_workers: int = 10     # 并发工作线程数（来自config.yml: pipeline.stitching_workers）

    💡 关键特点

    ✅ 自动回退机制

    - 如果单步任务没有传入 cropped_images_path，系统会自动从 ffmpeg.crop_subtitle_images 阶段获取
    - 如果没有传入 subtitle_area，系统会自动从 paddleocr.detect_subtitle_area 阶段获取
    - 这使得单步任务既可以完全独立运行，也可以依赖工作流上下文

    ✅ MinIO支持

    - 支持从MinIO URL下载输入图像
    - 支持将拼接结果上传到MinIO
    - 自动处理HTTP和minio://协议

    ✅ 动态引用支持

    单步任务的 input_data 支持动态引用：
    {
      "input_data": {
        "cropped_images_path": "${{workflow_context.shared_storage_path}}/cropped_frames",
        "subtitle_area": {"x1": 0, "y1": 100, "x2": 1920, "y2": 200}
      }
    }

    📊 工作模式对比

    | 特性      | 工作流模式                                | 单步任务模式                  |
    |---------|--------------------------------------|-------------------------|
    | 参数来源    | node_params + input_data             | input_data              |
    | 参数格式    | input_params.node_params.{task_name} | input_params.input_data |
    | 上游依赖    | 自动获取                                 | 可选，可手动传入                |
    | 动态引用    | ✅ 支持                                 | ✅ 支持                    |
    | MinIO支持 | ✅ 支持                                 | ✅ 支持                    |

    🔍 代码验证

    从 tasks.py:439-478 可以看到：
    # 单步任务模式下，node_params 为空
    node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})

    # get_param_with_fallback 会自动从 input_data 获取参数（第147行）
    input_data = context_dict.get("input_params", {}).get("input_data", {})

    总结

    paddleocr.create_stitched_images 原生支持单步任务参数传入，通过统一的 get_param_with_fallback 机制，可以从 input_data 中获取参数，同时保留从上游节点自动回退的能力，确保了单步任务和工作流模式的兼容性。
  ```

  ### 是否支持minio自动上传

  请介绍`paddleocr.create_stitched_images`执行结果, 确定是否支持minio自动上传

  ```markdown
    💡 默认行为总结

    | 配置项                              | 默认值   | 行为                          |
    |----------------------------------|-------|-----------------------------|
    | upload_stitched_images_to_minio  | True  | ✅ 默认自动上传                    |
    | delete_local_images_after_upload | False | ✅ 默认保留本地文件                  |
    | 目录结构                             | -     | ✅ 保留原始目录结构                  |
    | 上传路径                             | -     | workflow_id/stitched_images |
    | 失败处理                             | -     | 记录错误但不中断任务                  |

    📌 关键结论

    1. ✅ MinIO自动上传：默认启用，无需额外配置
    2. ✅ 灵活控制：可通过参数自定义是否上传、是否删除本地文件
    3. ✅ 容错处理：上传失败不会中断任务
    4. ✅ 完整追踪：提供本地路径和MinIO URL双重输出
    5. ✅ 目录保留：默认保留原始目录结构，便于后续处理
  ```

  ### 单步任务n8n http测试请求样例

  请输出`paddleocr.create_stitched_images`单步任务的n8n请求测试样例.

  **参考样例**:

  ```json
  {
    "nodes": [
      {
        "parameters": {
          "method": "POST",
          "url": "http://api_gateway/v1/tasks",
          "sendBody": true,
          "specifyBody": "json",
          "jsonBody": "={\n    "task_name": "ffmpeg.crop_subtitle_images",\n    "task_id": "task_id",\n    "callback": "{{ $execution.resumeUrl }}/t3",\n    "input_data": {\n        "video_path": "http://host.docker.internal:9000/yivideo/task_id/223.mp4",\n        "subtitle_area":  [\n                0,\n                607,\n                1280,\n                679\n              ],\n        "upload_cropped_images_to_minio": true\n    }\n}",
          "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.3,
        "position": [
          -208,
          1232
        ],
        "id": "92024e6e-134f-491d-865a-1d9593330434",
        "name": "HttpRequest3"
      }
    ],
    "connections": {
      "HttpRequest3": {
        "main": [
          []
        ]
      }
    },
    "pinData": {},
    "meta": {
      "templateCredsSetupCompleted": true,
      "instanceId": "ce62717b1b8e3f0f382d7655865d4cc25bd57832825813d5d8aa77789e762603"
    }
  }
  ```

  **http请求样例**:

  ```json
  步骤1：创建HTTP Request节点

    在n8n工作流中添加一个 HTTP Request 节点

    步骤2：设置基础参数

    Method: POST

    URL:
    http://api_gateway:8000/v1/tasks

    Send Body: ✅ 勾选

    Specify Body: 选择 JSON

    步骤3：配置JSON Body

    在JSON Body输入框中填入以下内容：

    {
        "task_name": "paddleocr.create_stitched_images",
        "task_id": "task-{{ $execution.id }}",
        "callback": "{{ $execution.resumeUrl }}/t4",
        "input_data": {
            "cropped_images_path": "/share/workflows/task-{{ $execution.id }}/cropped_images/frames",
            "subtitle_area": {
                "x1": 0,
                "y1": 607,
                "x2": 1280,
                "y2": 679
            },
            "upload_stitched_images_to_minio": true,
            "delete_local_stitched_images_after_upload": false
        }
    }

    步骤4：详解各参数含义

    必填参数

    1. task_name (字符串)
      - 固定值: "paddleocr.create_stitched_images"
      - 这是任务的标识符，不可更改
    2. task_id (字符串)
      - 推荐: "task-{{ $execution.id }}"
      - 或自定义: "crop_stitch_001"
      - 唯一标识这次任务
    3. callback (字符串，可选)
      - 格式: "{{ $execution.resumeUrl }}/t4"
      - 用于接收任务完成通知
      - 如果不需要回调，可删除此字段
    4. input_data (对象，包含所有任务参数)

    input_data 参数详解

    必需参数

    - cropped_images_path (字符串)
      - 格式: /share/workflows/{workflow_id}/cropped_images/frames
      - 例如: /share/workflows/task-123/cropped_images/frames
      - 这是从 ffmpeg.crop_subtitle_images 任务输出的路径
    - subtitle_area (对象)
    {
      "x1": 0,      // 字幕区域左上角X坐标
      "y1": 607,    // 字幕区域左上角Y坐标  
      "x2": 1280,   // 字幕区域右下角X坐标
      "y2": 679     // 字幕区域右下角Y坐标
    }
      - 这些值来自 paddleocr.detect_subtitle_area 任务的输出

    可选参数

    - upload_stitched_images_to_minio (布尔值)
      - true (默认) - 自动上传到MinIO
      - false - 不上传，仅保存本地
    - delete_local_stitched_images_after_upload (布尔值)
      - false (默认) - 上传后保留本地文件
      - true - 上传后删除本地文件

    步骤5：完整配置示例

    {
        "task_name": "paddleocr.create_stitched_images",
        "task_id": "my_task_001",
        "input_data": {
            "cropped_images_path": "/share/workflows/my_task_001/cropped_images/frames",
            "subtitle_area": {
                "x1": 0,
                "y1": 100,
                "x2": 1920,
                "y2": 200
            },
            "upload_stitched_images_to_minio": true
        }
    }

    步骤6：动态参数设置技巧

    使用n8n表达式

    - task_id: "task-" & $execution.id
    - 路径: "/share/workflows/" & $execution.id & "/cropped_images/frames"
    - 回调: {{ $execution.resumeUrl }}/callback

    从前置节点获取参数

    如果cropped_images_path来自前置节点，可使用：
    "cropped_images_path": "={{ $node['前置节点名称'].json.output.cropped_images_path }}"

    步骤7：验证配置

    配置完成后，节点应显示：
    - ✅ Method: POST
    - ✅ URL: http://api_gateway:8000/v1/tasks
    - ✅ Body: JSON格式
    - ✅ 参数格式正确

    常见错误排查

    1. URL错误
      - 确保是 http://api_gateway:8000/v1/tasks (不是9000)
      - 检查api_gateway服务名是否正确
    2. JSON格式错误
      - 所有字符串必须用双引号
      - 最后一项后面不能有逗号
      - 使用JSON在线验证工具检查
    3. 路径不存在
      - 确保cropped_images_path指向的目录确实存在
      - 检查权限是否可以访问
    4. 坐标错误
      - subtitle_area的坐标必须来自detect_subtitle_area的输出
      - 确保 x1 < x2, y1 < y2
  ```

  ### 排查报错

  **n8n http请求**

  ```json
  {
    "nodes": [
      {
        "parameters": {
          "method": "POST",
          "url": "http://api_gateway/v1/tasks",
          "sendBody": true,
          "specifyBody": "json",
          "jsonBody": "={\n    "task_name": "paddleocr.create_stitched_images",\n    "task_id": "task_id",\n    "callback": "{{ $execution.resumeUrl }}/t3",\n    "input_data": {\n        "cropped_images_path": "http://host.docker.internal:9000/yivideo/task_id/cropped_images",\n        "subtitle_area":  [\n                0,\n                607,\n                1280,\n                679\n              ],\n        "upload_stitched_images_to_minio": true\n    }\n}",
          "options": {}
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.3,
        "position": [
          -160,
          1264
        ],
        "id": "92024e6e-134f-491d-865a-1d9593330434",
        "name": "HttpRequest3"
      }
    ],
    "connections": {
      "HttpRequest3": {
        "main": [
          []
        ]
      }
    },
    "pinData": {},
    "meta": {
      "templateCredsSetupCompleted": true,
      "instanceId": "ce62717b1b8e3f0f382d7655865d4cc25bd57832825813d5d8aa77789e762603"
    }
  }
  ```

  **容器日志**

  ```log
  [2025-11-25 15:14:10,013: INFO/MainProcess] Task paddleocr.create_stitched_images[27800f11-ad6f-45d8-adaf-98e80446a39a] received
  [2025-11-25 15:14:10,015: INFO/ForkPoolWorker-29] 初始化文件服务: host.docker.internal:9000, bucket: yivideo, 重试次数: 3
  [2025-11-25 15:14:10,028: INFO/ForkPoolWorker-29] Callback管理器初始化完成
  [2025-11-25 15:14:10,028: INFO/ForkPoolWorker-29] 已更新 workflow_id='task_id' 的状态。
  [2025-11-25 15:14:10,029: INFO/ForkPoolWorker-29] [paddleocr.create_stitched_images] 检测到输入路径为URL，尝试从MinIO下载目录: http://host.docker.internal:9000/yivideo/task_id/cropped_images
  [2025-11-25 15:14:10,029: ERROR/ForkPoolWorker-29] [paddleocr.create_stitched_images] 发生错误: 无效的MinIO URL格式: http://host.docker.internal:9000/yivideo/task_id/cropped_images
  Traceback (most recent call last):
    File "/app/services/workers/paddleocr_service/app/tasks.py", line 496, in create_stitched_images
      download_result = download_directory_from_minio(
                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    File "/app/services/common/minio_directory_download.py", line 231, in download_directory_from_minio
      return downloader.download_directory(
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    File "/app/services/common/minio_directory_download.py", line 64, in download_directory
      raise ValueError(f"无效的MinIO URL格式: {minio_url}")
  ValueError: 无效的MinIO URL格式: http://host.docker.internal:9000/yivideo/task_id/cropped_images
  [2025-11-25 15:14:10,038: INFO/ForkPoolWorker-29] 开始发送callback，任务ID: task_id, URL: http://host.docker.internal:5678/webhook-waiting/1880/t3
  [2025-11-25 15:14:10,101: WARNING/ForkPoolWorker-29] Callback HTTP错误，任务ID: task_id, 尝试: 1/3, 错误: 409 Client Error: Conflict for url: http://host.docker.internal:5678/webhook-waiting/1880/t3
  [2025-11-25 15:14:10,101: ERROR/ForkPoolWorker-29] 所有callback尝试都失败，任务ID: task_id
  [2025-11-25 15:14:10,101: INFO/ForkPoolWorker-29] Callback发送完成: task_id, 状态: failed
  [2025-11-25 15:14:10,101: INFO/ForkPoolWorker-29] 已更新 workflow_id='task_id' 的状态。
  [2025-11-25 15:14:10,145: INFO/ForkPoolWorker-29] 实时读取配置 cleanup_temp_files: False
  [2025-11-25 15:14:10,161: INFO/ForkPoolWorker-29] Task paddleocr.create_stitched_images[27800f11-ad6f-45d8-adaf-98e80446a39a] succeeded in 0.14647888900071848s: {'workflow_id': 'task_id', 'create_at': '2025-11-25T15:14:09.9125
  52', 'input_params': {'task_name': 'paddleocr.create_stitched_images', 'input_data': {'cropped_images_path': 'http://host.docker.internal:9000/yivideo/task_id/cropped_images', 'subtitle_area': [...], 'upload_stitched_images_to
  _minio': True}, 'callback_url': 'http://host.docker.internal:5678/webhook-waiting/1880/t3'}, 'shared_storage_path': '/share/single_tasks/task_id', 'stages': {'paddleocr.create_stitched_images': {'status': 'FAILED', 'input_para
  ms': {...}, 'output': {...}, 'error': '无效的MinIO URL格式: http://host.docker.internal:9000/yivideo/task_id/cropped_images', 'duration': 0.022082805633544922}}, 'error': '在阶段 paddleocr.create_stitched_images 发生错误: 无效
  的MinIO URL格式: http://host.docker.internal:9000/yivideo/task_id/cropped_images'}
  ```

  **目标**

  分析并排查日志中的报错, 给出解决方案

  ### 返回结果增加数据项

  **返回结果**

  ```
  [
    {
      "headers": {
        "host": "host.docker.internal:5678",
        "user-agent": "YiVideo-API-Gateway/1.0",
        "accept-encoding": "gzip, deflate",
        "accept": "*/*",
        "connection": "keep-alive",
        "content-type": "application/json",
        "content-length": "1068"
      },
      "params": {},
      "query": {},
      "body": {
        "task_id": "task_id",
        "status": "completed",
        "result": {
          "workflow_id": "task_id",
          "create_at": "2025-11-25T15:21:31.310506",
          "input_params": {
            "task_name": "paddleocr.create_stitched_images",
            "input_data": {
              "cropped_images_path": "http://host.docker.internal:9000/yivideo/task_id/cropped_images",
              "subtitle_area": [
                0,
                607,
                1280,
                679
              ],
              "upload_stitched_images_to_minio": true
            },
            "callback_url": "http://host.docker.internal:5678/webhook-waiting/1881/t3"
          },
          "shared_storage_path": "/share/single_tasks/task_id",
          "stages": {
            "paddleocr.create_stitched_images": {
              "status": "SUCCESS",
              "input_params": {
                "cropped_images_path": "http://host.docker.internal:9000/yivideo/task_id/cropped_images",
                "subtitle_area": [
                  0,
                  607,
                  1280,
                  679
                ]
              },
              "output": {
                "multi_frames_path": "/share/single_tasks/task_id/multi_frames",
                "manifest_path": "/share/single_tasks/task_id/multi_frames.json",
                "multi_frames_minio_url": "http://host.docker.internal:9000/yivideo/task_id/stitched_images"
              },
              "error": null,
              "duration": 17.608853578567505
            }
          },
          "error": null
        },
        "timestamp": "2025-11-25T15:21:49.003693Z"
      },
      "webhookUrl": "http://host.docker.internal:5678/webhook-test/t3",
      "executionMode": "test"
    }
  ]
  ```

  **目标:**

  `output`增加`manifest_minio_url`,  设置为`manifest_path`上传`minio`返回的链接

  ## {已解决}排查wservice启动报错

  **容器日志**:

  ```log

  2025-11-25 11:08:33,197 - locks - INFO - 成功连接到Redis锁数据库 at host.docker.internal:6379/2
  2025-11-25 11:08:33,199 - locks - INFO - Redis Pub/Sub连接初始化成功
  2025-11-25 11:08:33,200 - locks - INFO - Pub/Sub监听线程启动
  2025-11-25 11:08:33,499 - state_manager - INFO - 状态管理器成功连接到Redis at host.docker.internal:6379/3
  2025-11-25 11:08:33,524 - gpu_memory_manager - WARNING - 未检测到可用的CUDA设备
  Usage: celery [OPTIONS] COMMAND [ARGS]...
  Try 'celery --help' for help.

  Error:
  Unable to load celery application.
  Type object 'config' has no attribute 'get_celery_config'  

  ```

  其他组件没有报这个错误, 均运行正常

  ```

  4c18ea872093   yivideo-audio_separator_service   "celery -A services.…"   2 days ago    Up 20 minutes (healthy)                                                                           audio_separator_service
  4a6e929e254c   yivideo-indextts_service          "celery -A services.…"   2 days ago    Up 20 minutes (healthy)         0.0.0.0:7860->7860/tcp, [::]:7860->7860/tcp                       indextts_service
  da15ce100442   yivideo-pyannote_audio_service    "celery -A services.…"   2 days ago    Up 20 minutes                                                                                     pyannote_audio_service
  f21aa9937917   yivideo-paddleocr_service         "/opt/venv/bin/celer…"   2 days ago    Up 20 minutes                                                                                     paddleocr_service
  89ce55d62898   yivideo-wservice                  "celery -A services.…"   2 days ago    Restarting (2) 33 seconds ago                                                                     wservice
  03111c7134a7   yivideo-faster_whisper_service    "celery -A services.…"   2 days ago    Up 20 minutes                                                                                     faster_whisper_service
  8349b7b63065   yivideo-ffmpeg_service            "celery -A app.tasks…"   2 days ago    Up 20 minutes                                                                                     ffmpeg_service
  ```

  **目标:**

  请对比其他组件, 并分析排查日志中的报错, 给出解决方案
