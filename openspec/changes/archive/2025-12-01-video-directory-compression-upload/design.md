# 视频图片目录压缩上传技术设计方案

## 设计概览

本文档详细描述了为YiVideo平台视频图片处理功能添加目录压缩上传能力的架构设计和实现方案。该方案旨在解决大量图片文件上传的性能问题，通过压缩技术显著提高传输效率和系统性能。

## 系统架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     YiVideo Workflow Engine                  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ ffmpeg.extract  │  │ ffmpeg.crop_    │  │ paddleocr.   │ │
│  │ _keyframes      │  │ subtitle_images │  │ detect_area  │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│         │                      │                    │       │
│         ▼                      ▼                    ▼       │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │           Directory Compression Layer                   │ │
│  │  ┌─────────────────┐  ┌─────────────────────────────────┐ │ │
│  │  │ Compression     │  │ MinIO Directory Upload          │ │ │
│  │  │ Module          │  │ (Enhanced)                      │ │ │
│  │  └─────────────────┘  └─────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
│                               │                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │           MinIO Object Storage                          │ │
│  │  ┌──────────────┐  ┌──────────────────────────────────┐ │ │
│  │  │ Individual   │  │ Compressed Archives              │ │ │
│  │  │ Images       │  │ (.zip files)                     │ │ │
│  │  └──────────────┘  └──────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件设计

#### 1. Directory Compression Module (`directory_compression.py`)

**职责**: 提供统一的目录压缩功能

```python
class DirectoryCompressor:
    """目录压缩器"""
    
    def compress_directory(self, 
                          source_dir: str, 
                          output_path: str = None,
                          compression_format: str = "zip",
                          progress_callback: callable = None) -> CompressionResult:
        """
        压缩目录
        
        Args:
            source_dir: 源目录路径
            output_path: 输出压缩包路径（可选）
            compression_format: 压缩格式（zip, tar.gz）
            progress_callback: 进度回调函数
            
        Returns:
            CompressionResult: 压缩结果
        """
        pass
    
    def decompress_archive(self,
                          archive_path: str,
                          output_dir: str,
                          progress_callback: callable = None) -> DecompressionResult:
        """
        解压缩档案
        
        Args:
            archive_path: 压缩包路径
            output_dir: 输出目录
            progress_callback: 进度回调函数
            
        Returns:
            DecompressionResult: 解压结果
        """
        pass
```

**核心特性**:
- **流式处理**: 避免大目录时的内存溢出
- **进度跟踪**: 实时反馈压缩进度
- **完整性校验**: MD5/SHA256校验和验证
- **多格式支持**: ZIP, TAR.GZ等主流格式
- **错误恢复**: 压缩失败时自动清理临时文件

#### 2. Enhanced MinIO Directory Upload

**职责**: 扩展现有的目录上传功能，支持压缩包上传

```python
class EnhancedMinioDirectoryUploader(MinioDirectoryUploader):
    """增强的MinIO目录上传器"""
    
    def upload_directory_compressed(self,
                                   local_dir: str,
                                   minio_base_path: str,
                                   compression_format: str = "zip",
                                   delete_after_upload: bool = False,
                                   **kwargs) -> UploadResult:
        """
        压缩目录并上传
        
        Args:
            local_dir: 本地目录
            minio_base_path: MinIO基础路径
            compression_format: 压缩格式
            delete_after_upload: 上传后删除本地文件
            
        Returns:
            UploadResult: 上传结果
        """
        pass
    
    def download_and_extract(self,
                            minio_url: str,
                            local_dir: str,
                            auto_extract: bool = True) -> DownloadResult:
        """
        下载并自动解压
        
        Args:
            minio_url: MinIO压缩包URL
            local_dir: 本地目录
            auto_extract: 是否自动解压
            
        Returns:
            DownloadResult: 下载和解压结果
        """
        pass
```

#### 3. Workflow Node Enhancements

**ffmpeg.crop_subtitle_images 增强**:
```python
# 新增参数
compress_before_upload: bool = False
compression_format: str = "zip"
auto_cleanup_temp: bool = True

# 输出增强
output_data = {
    "cropped_images_path": "/path/to/local/dir",
    "cropped_images_minio_url": "http://minio/individual/images",
    "compressed_archive_url": "http://minio/compressed/cropped.zip",  # 新增
    "compression_info": {                                           # 新增
        "format": "zip",
        "size": "150MB",
        "original_size": "450MB",
        "compression_ratio": 0.33,
        "file_count": 15230
    }
}
```

**ffmpeg.extract_keyframes 增强**:
```python
# 新增参数（与crop_subtitle_images保持一致）
compress_keyframes_before_upload: bool = False
compression_format: str = "zip"
```

## 技术实现细节

### 压缩算法选择

#### ZIP格式 - 主要选择
**优势**:
- Python内置支持（zipfile模块）
- 跨平台兼容性好
- 支持随机访问（不解压即可查看文件列表）
- 压缩率适中（图片文件30-50%）

**实现策略**:
```python
import zipfile
import os
from pathlib import Path

def compress_directory_zip(source_dir: str, output_path: str, 
                          progress_callback: callable = None) -> dict:
    """ZIP压缩实现"""
    
    total_files = sum([len(files) for r, d, files in os.walk(source_dir)])
    processed_files = 0
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                
                zipf.write(file_path, arcname)
                processed_files += 1
                
                if progress_callback:
                    progress = processed_files / total_files
                    progress_callback(progress, file, processed_files, total_files)
    
    return {"success": True, "compressed_size": os.path.getsize(output_path)}
```

### 内存管理策略

#### 流式压缩
- **分块处理**: 避免将整个目录加载到内存
- **缓冲区控制**: 设置合理的缓冲区大小（默认64MB）
- **临时文件**: 大目录压缩时使用临时文件

```python
def compress_large_directory_streaming(source_dir: str, output_path: str):
    """流式压缩大目录"""
    
    BUFFER_SIZE = 64 * 1024 * 1024  # 64MB buffer
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, 
                        allowZip64=True) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                
                # 流式读取和写入
                with open(file_path, 'rb') as f_in:
                    with zipf.open(arcname, 'w') as f_out:
                        while True:
                            chunk = f_in.read(BUFFER_SIZE)
                            if not chunk:
                                break
                            f_out.write(chunk)
```

### 并发压缩

#### 多进程压缩
**适用场景**: 大目录，多个独立子目录

```python
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

def compress_directory_parallel(source_dir: str, output_path: str, 
                               max_workers: int = None):
    """并行压缩"""
    
    if max_workers is None:
        max_workers = min(multiprocessing.cpu_count(), 4)
    
    # 按子目录分割任务
    subdirs = [d for d in os.listdir(source_dir) 
               if os.path.isdir(os.path.join(source_dir, d))]
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for subdir in subdirs:
            subdir_path = os.path.join(source_dir, subdir)
            future = executor.submit(compress_directory_zip, subdir_path, 
                                   f"{subdir}.zip")
            futures.append(future)
        
        # 合并压缩包
        with zipfile.ZipFile(output_path, 'w') as main_zip:
            for future in futures:
                sub_zip_path = future.result()
                with zipfile.ZipFile(sub_zip_path, 'r') as sub_zip:
                    for file_info in sub_zip.infolist():
                        main_zip.writestr(file_info, sub_zip.read(file_info))
```

### 错误处理与恢复

#### 压缩失败处理
```python
class CompressionError(Exception):
    """压缩异常基类"""
    pass

class InsufficientSpaceError(CompressionError):
    """磁盘空间不足"""
    pass

class PermissionError(CompressionError):
    """权限错误"""
    pass

def compress_with_retry(source_dir: str, output_path: str, 
                       max_retries: int = 3):
    """带重试的压缩"""
    
    for attempt in range(max_retries):
        try:
            return compress_directory_zip(source_dir, output_path)
        except InsufficientSpaceError as e:
            if attempt == max_retries - 1:
                raise
            # 清理临时文件并重试
            cleanup_temp_files()
            time.sleep(2 ** attempt)  # 指数退避
        except Exception as e:
            # 其他错误不重试
            raise
    
    # 清理临时文件
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)
```

### 性能监控

#### 压缩性能指标
```python
@dataclass
class CompressionMetrics:
    """压缩性能指标"""
    compression_time: float
    original_size: int
    compressed_size: int
    compression_ratio: float
    files_processed: int
    memory_peak: int
    cpu_usage: float

def monitor_compression_performance(func):
    """压缩性能监控装饰器"""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss
        
        result = func(*args, **kwargs)
        
        end_time = time.time()
        end_memory = psutil.Process().memory_info().rss
        
        metrics = CompressionMetrics(
            compression_time=end_time - start_time,
            original_size=result.get('original_size', 0),
            compressed_size=result.get('compressed_size', 0),
            compression_ratio=result.get('compression_ratio', 0),
            files_processed=result.get('files_processed', 0),
            memory_peak=end_memory - start_memory,
            cpu_usage=get_cpu_usage()  # 需要实现
        )
        
        logger.info(f"Compression metrics: {metrics}")
        return result
    
    return wrapper
```

## 向后兼容性设计

### 参数兼容策略

#### 默认行为保持
- 新参数默认值确保行为与原来一致
- 渐进式启用，用户可选择是否使用

#### API向后兼容
```python
# 现有API保持不变
@celery_app.task
def crop_subtitle_images(self, context):
    # 原有参数处理逻辑不变
    upload_to_minio = get_param_with_fallback(
        "upload_cropped_images_to_minio", 
        resolved_params, 
        workflow_context, 
        default=False
    )
    
    # 新增可选参数
    compress_before_upload = get_param_with_fallback(
        "compress_directory_before_upload",
        resolved_params,
        workflow_context,
        default=False  # 默认为False，保持原有行为
    )
    
    if upload_to_minio:
        if compress_before_upload:
            # 新的压缩上传流程
            result = upload_compressed_directory(...)
        else:
            # 原有单文件上传流程
            result = upload_directory_files(...)
```

### 配置兼容
```yaml
# config.yml
ffmpeg_service:
  upload:
    # 原有配置保持不变
    default_upload_method: "individual_files"  # 保持默认
    
    # 新增配置项
    compression:
      enabled: false  # 默认禁用，需要用户显式启用
      format: "zip"
      level: 6  # 压缩级别1-9
      parallel_processes: 2
```

## 部署策略

### 灰度发布方案

#### 阶段1: 功能开发完成
- 内部测试环境验证
- 性能基准测试
- 文档完善

#### 阶段2: 小范围试点
- 选择非关键工作流测试
- 监控性能和稳定性
- 收集用户反馈

#### 阶段3: 逐步推广
- 按用户群体逐步启用
- 实时监控和告警
- 快速回滚机制准备

#### 阶段4: 全面启用
- 默认启用压缩功能
- 性能优化调优
- 用户培训和文档

### 回滚策略

#### 自动回滚条件
- 压缩成功率<95%
- 平均处理时间增加>20%
- 错误率增加>50%
- 内存使用增加>100%

#### 回滚机制
```python
def should_rollback_upload_compression():
    """判断是否需要回滚压缩功能"""
    
    metrics = get_recent_metrics()  # 最近1小时指标
    
    success_rate = metrics.compression_success_rate
    avg_time = metrics.avg_processing_time
    error_rate = metrics.error_rate
    memory_usage = metrics.memory_usage
    
    return (success_rate < 0.95 or 
            avg_time > 1.2 * BASELINE_TIME or
            error_rate > 1.5 * BASELINE_ERROR_RATE or
            memory_usage > 2.0 * BASELINE_MEMORY)
```

## 监控与告警

### 关键指标

#### 性能指标
- 压缩成功率（目标>99%）
- 平均压缩时间（目标<5分钟/1000文件）
- 压缩率（目标30-60%）
- 内存峰值（目标<2GB）

#### 业务指标
- 使用压缩上传的任务占比
- 节省的网络传输量
- 用户满意度评分
- 任务完成时间改善

#### 系统指标
- CPU使用率变化
- 磁盘I/O使用率
- 网络带宽利用率
- 错误和异常数量

### 告警规则

```yaml
# 告警配置
alerts:
  compression_failure_rate:
    condition: "compression_success_rate < 0.95"
    severity: "warning"
    duration: "5m"
  
  performance_degradation:
    condition: "avg_processing_time > 1.5 * baseline"
    severity: "critical"
    duration: "10m"
  
  memory_leak:
    condition: "memory_usage > 3GB"
    severity: "critical"
    duration: "2m"
```

---

**设计版本**: v1.0  
**技术负责人**: 待定  
**评审状态**: 待评审  
**最后更新**: 2025-11-30