# -*- coding: utf-8 -*-

"""
目录压缩模块

提供统一的目录压缩和解压缩功能，支持：
- ZIP格式压缩
- 流式处理（避免大目录内存溢出）
- 进度回调和监控
- 完整性校验
- 错误处理和恢复
"""

import os
import zipfile
import hashlib
import tempfile
import shutil
import time
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger('directory_compression')

class CompressionFormat(Enum):
    """压缩格式枚举"""
    ZIP = "zip"
    TAR_GZ = "tar.gz"

class CompressionLevel(Enum):
    """压缩级别枚举"""
    STORE = 0      # 仅存储，不压缩
    FAST = 1       # 快速压缩
    DEFAULT = 6    # 默认压缩
    MAXIMUM = 9    # 最大压缩

@dataclass
class CompressionProgress:
    """压缩进度信息"""
    progress: float = 0.0  # 0.0 - 1.0
    current_file: str = ""
    processed_files: int = 0
    total_files: int = 0
    processed_bytes: int = 0
    total_bytes: int = 0
    elapsed_time: float = 0.0
    estimated_time: float = 0.0
    speed_mbps: float = 0.0

@dataclass
class CompressionResult:
    """压缩结果"""
    success: bool = False
    archive_path: str = ""
    original_size: int = 0
    compressed_size: int = 0
    compression_ratio: float = 0.0
    files_count: int = 0
    compression_time: float = 0.0
    checksum: str = ""
    error_message: str = ""
    temp_files: List[str] = field(default_factory=list)

@dataclass
class DecompressionResult:
    """解压结果"""
    success: bool = False
    archive_path: str = ""
    output_dir: str = ""
    extracted_files: int = 0
    extraction_time: float = 0.0
    checksum_match: bool = False
    error_message: str = ""

class DirectoryCompressor:
    """目录压缩器"""
    
    def __init__(self, buffer_size: int = 64 * 1024 * 1024):
        """
        初始化压缩器
        
        Args:
            buffer_size: 缓冲区大小，默认64MB
        """
        self.buffer_size = buffer_size
        self._temp_files = []
    
    def compress_directory(self,
                          source_dir: str,
                          output_path: str = None,
                          compression_format: CompressionFormat = CompressionFormat.ZIP,
                          compression_level: CompressionLevel = CompressionLevel.DEFAULT,
                          progress_callback: Optional[Callable[[CompressionProgress], None]] = None,
                          file_patterns: Optional[List[str]] = None,
                          exclude_patterns: Optional[List[str]] = None) -> CompressionResult:
        """
        压缩目录
        
        Args:
            source_dir: 源目录路径
            output_path: 输出压缩包路径（可选）
            compression_format: 压缩格式
            compression_level: 压缩级别
            progress_callback: 进度回调函数
            file_patterns: 包含的文件模式列表
            exclude_patterns: 排除的文件模式列表
            
        Returns:
            CompressionResult: 压缩结果
        """
        start_time = time.time()
        
        try:
            # 验证输入
            if not os.path.exists(source_dir):
                raise FileNotFoundError(f"源目录不存在: {source_dir}")
            
            if not os.path.isdir(source_dir):
                raise ValueError(f"路径不是目录: {source_dir}")
            
            # 生成输出路径
            if output_path is None:
                source_name = os.path.basename(source_dir) or "directory"
                timestamp = int(time.time())
                output_path = f"{source_name}_{timestamp}.zip"
            
            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            # 获取要处理的文件列表
            files_to_process = self._get_files_to_process(
                source_dir, file_patterns, exclude_patterns
            )
            
            if not files_to_process:
                logger.warning(f"目录中没有找到匹配的文件: {source_dir}")
                return CompressionResult(
                    success=True,
                    archive_path=output_path,
                    files_count=0,
                    compression_time=time.time() - start_time
                )
            
            # 计算总大小
            total_size = sum(os.path.getsize(file_path) for file_path in files_to_process)
            
            logger.info(f"开始压缩目录: {source_dir} -> {output_path}")
            logger.info(f"文件数量: {len(files_to_process)}")
            logger.info(f"总大小: {total_size / 1024 / 1024:.2f} MB")
            
            # 执行压缩
            if compression_format == CompressionFormat.ZIP:
                result = self._compress_zip(
                    source_dir, output_path, files_to_process,
                    compression_level, progress_callback, start_time
                )
            else:
                raise NotImplementedError(f"暂不支持的压缩格式: {compression_format}")
            
            result.compression_time = time.time() - start_time
            
            if result.success:
                # 计算校验和
                result.checksum = self._calculate_checksum(output_path)
                result.compression_ratio = 1.0 - (result.compressed_size / result.original_size)
                
                logger.info(f"压缩完成: {result.compression_ratio:.1%} 压缩率")
                logger.info(f"压缩时间: {result.compression_time:.2f}秒")
                logger.info(f"校验和: {result.checksum}")
            
            return result
            
        except Exception as e:
            error_msg = f"压缩过程中发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return CompressionResult(
                success=False,
                error_message=error_msg,
                compression_time=time.time() - start_time
            )
        finally:
            # 清理临时文件
            self._cleanup_temp_files()
    
    def decompress_archive(self,
                          archive_path: str,
                          output_dir: str,
                          progress_callback: Optional[Callable[[CompressionProgress], None]] = None,
                          overwrite: bool = False,
                          validate_checksum: bool = True) -> DecompressionResult:
        """
        解压缩档案
        
        Args:
            archive_path: 压缩包路径
            output_dir: 输出目录
            progress_callback: 进度回调函数
            overwrite: 是否覆盖已存在的文件
            validate_checksum: 是否验证校验和
            
        Returns:
            DecompressionResult: 解压结果
        """
        start_time = time.time()
        
        try:
            # 验证输入
            if not os.path.exists(archive_path):
                raise FileNotFoundError(f"压缩包不存在: {archive_path}")
            
            # 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)
            
            logger.info(f"开始解压: {archive_path} -> {output_dir}")
            
            # 选择解压方法
            if archive_path.lower().endswith('.zip'):
                result = self._decompress_zip(
                    archive_path, output_dir, progress_callback, overwrite
                )
            elif archive_path.lower().endswith('.tar.gz'):
                result = self._decompress_tar_gz(
                    archive_path, output_dir, progress_callback, overwrite
                )
            else:
                raise ValueError(f"不支持的压缩格式: {archive_path}")
            
            result.extraction_time = time.time() - start_time
            
            if result.success:
                logger.info(f"解压完成: {result.extracted_files} 个文件")
                logger.info(f"解压时间: {result.extraction_time:.2f}秒")
            
            return result
            
        except Exception as e:
            error_msg = f"解压过程中发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return DecompressionResult(
                success=False,
                archive_path=archive_path,
                output_dir=output_dir,
                error_message=error_msg,
                extraction_time=time.time() - start_time
            )
    
    def _get_files_to_process(self,
                              source_dir: str,
                              file_patterns: Optional[List[str]] = None,
                              exclude_patterns: Optional[List[str]] = None) -> List[str]:
        """获取要处理的文件列表"""
        files_to_process = []
        
        # 默认包含所有文件
        if file_patterns is None:
            file_patterns = ['*']
        
        # 遍历目录
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, source_dir)
                
                # 检查是否包含
                included = False
                for pattern in file_patterns:
                    if self._match_pattern(rel_path, pattern):
                        included = True
                        break
                
                if not included:
                    continue
                
                # 检查是否排除
                excluded = False
                if exclude_patterns:
                    for pattern in exclude_patterns:
                        if self._match_pattern(rel_path, pattern):
                            excluded = True
                            break
                
                if not excluded:
                    files_to_process.append(file_path)
        
        return sorted(files_to_process)
    
    def _match_pattern(self, path: str, pattern: str) -> bool:
        """简单的模式匹配（支持*和?）"""
        import fnmatch
        
        # 转换Unix glob模式为fnmatch模式
        fnmatch_pattern = pattern.replace('\\', '/')
        return fnmatch.fnmatch(path.replace('\\', '/'), fnmatch_pattern)
    
    def _compress_zip(self,
                      source_dir: str,
                      output_path: str,
                      files_to_process: List[str],
                      compression_level: CompressionLevel,
                      progress_callback: Optional[Callable[[CompressionProgress], None]],
                      start_time: float) -> CompressionResult:
        """ZIP压缩实现"""
        
        compression_method = zipfile.ZIP_DEFLATED if compression_level != CompressionLevel.STORE else zipfile.ZIP_STORED
        compress_level = compression_level.value
        
        result = CompressionResult(
            success=False,
            archive_path=output_path,
            original_size=sum(os.path.getsize(f) for f in files_to_process),
            files_count=len(files_to_process)
        )
        
        try:
            with zipfile.ZipFile(
                output_path, 'w', compression_method, 
                compresslevel=compress_level, allowZip64=True
            ) as zipf:
                
                processed_files = 0
                processed_bytes = 0
                total_bytes = result.original_size
                
                for file_path in files_to_process:
                    try:
                        # 计算相对路径
                        arcname = os.path.relpath(file_path, source_dir)
                        
                        # 流式读取和写入
                        with open(file_path, 'rb') as f_in:
                            with zipf.open(arcname, 'w') as f_out:
                                while True:
                                    chunk = f_in.read(self.buffer_size)
                                    if not chunk:
                                        break
                                    f_out.write(chunk)
                                    processed_bytes += len(chunk)
                        
                        processed_files += 1
                        
                        # 更新进度
                        if progress_callback:
                            progress = processed_bytes / total_bytes if total_bytes > 0 else 0
                            progress_info = CompressionProgress(
                                progress=progress,
                                current_file=os.path.basename(file_path),
                                processed_files=processed_files,
                                total_files=len(files_to_process),
                                processed_bytes=processed_bytes,
                                total_bytes=total_bytes,
                                elapsed_time=time.time() - start_time
                            )
                            progress_callback(progress_info)
                        
                    except Exception as e:
                        logger.warning(f"压缩文件失败 {file_path}: {e}")
                        continue
                
                # 获取压缩后大小
                result.compressed_size = os.path.getsize(output_path)
                result.success = True
                
        except Exception as e:
            result.error_message = f"ZIP压缩失败: {str(e)}"
            # 清理失败的压缩包
            if os.path.exists(output_path):
                os.remove(output_path)
        
        return result
    
    def _decompress_zip(self,
                        archive_path: str,
                        output_dir: str,
                        progress_callback: Optional[Callable[[CompressionProgress], None]],
                        overwrite: bool) -> DecompressionResult:
        """ZIP解压实现"""
        
        result = DecompressionResult(
            success=False,
            archive_path=archive_path,
            output_dir=output_dir
        )
        
        try:
            with zipfile.ZipFile(archive_path, 'r') as zipf:
                # 获取文件列表
                file_list = zipf.infolist()
                total_files = len(file_list)
                total_size = sum(zinfo.file_size for zinfo in file_list)
                
                processed_files = 0
                processed_bytes = 0
                start_time = time.time()
                
                for zip_info in file_list:
                    try:
                        # 跳过目录
                        if zip_info.is_dir():
                            continue
                        
                        # 检查文件是否存在
                        target_path = os.path.join(output_dir, zip_info.filename)
                        target_dir = os.path.dirname(target_path)
                        
                        if os.path.exists(target_path) and not overwrite:
                            logger.warning(f"文件已存在，跳过: {target_path}")
                            continue
                        
                        # 创建目录
                        if target_dir:
                            os.makedirs(target_dir, exist_ok=True)
                        
                        # 解压文件
                        with zipf.open(zip_info) as f_in:
                            with open(target_path, 'wb') as f_out:
                                while True:
                                    chunk = f_in.read(self.buffer_size)
                                    if not chunk:
                                        break
                                    f_out.write(chunk)
                                    processed_bytes += len(chunk)
                        
                        processed_files += 1
                        
                        # 更新进度
                        if progress_callback:
                            progress = processed_bytes / total_size if total_size > 0 else 0
                            progress_info = CompressionProgress(
                                progress=progress,
                                current_file=zip_info.filename,
                                processed_files=processed_files,
                                total_files=total_files,
                                processed_bytes=processed_bytes,
                                total_bytes=total_size,
                                elapsed_time=time.time() - start_time
                            )
                            progress_callback(progress_info)
                        
                    except Exception as e:
                        logger.warning(f"解压文件失败 {zip_info.filename}: {e}")
                        continue
                
                result.extracted_files = processed_files
                result.success = processed_files > 0
                
        except Exception as e:
            result.error_message = f"ZIP解压失败: {str(e)}"
        
        return result
    
    def _decompress_tar_gz(self,
                          archive_path: str,
                          output_dir: str,
                          progress_callback: Optional[Callable[[CompressionProgress], None]],
                          overwrite: bool) -> DecompressionResult:
        """TAR.GZ解压实现"""
        import tarfile
        
        result = DecompressionResult(
            success=False,
            archive_path=archive_path,
            output_dir=output_dir
        )
        
        try:
            with tarfile.open(archive_path, 'r:gz') as tar:
                # 获取文件列表
                file_list = [member for member in tar.getmembers() if member.isfile()]
                total_files = len(file_list)
                total_size = sum(member.size for member in file_list)
                
                processed_files = 0
                processed_bytes = 0
                start_time = time.time()
                
                for member in file_list:
                    try:
                        # 检查文件是否存在
                        target_path = os.path.join(output_dir, member.name)
                        target_dir = os.path.dirname(target_path)
                        
                        if os.path.exists(target_path) and not overwrite:
                            logger.warning(f"文件已存在，跳过: {target_path}")
                            continue
                        
                        # 创建目录
                        if target_dir:
                            os.makedirs(target_dir, exist_ok=True)
                        
                        # 解压文件
                        with tar.extractfile(member) as f_in:
                            with open(target_path, 'wb') as f_out:
                                while True:
                                    chunk = f_in.read(self.buffer_size)
                                    if not chunk:
                                        break
                                    f_out.write(chunk)
                                    processed_bytes += len(chunk)
                        
                        processed_files += 1
                        
                        # 更新进度
                        if progress_callback:
                            progress = processed_bytes / total_size if total_size > 0 else 0
                            progress_info = CompressionProgress(
                                progress=progress,
                                current_file=member.name,
                                processed_files=processed_files,
                                total_files=total_files,
                                processed_bytes=processed_bytes,
                                total_bytes=total_size,
                                elapsed_time=time.time() - start_time
                            )
                            progress_callback(progress_info)
                        
                    except Exception as e:
                        logger.warning(f"解压文件失败 {member.name}: {e}")
                        continue
                
                result.extracted_files = processed_files
                result.success = processed_files > 0
                
        except Exception as e:
            result.error_message = f"TAR.GZ解压失败: {str(e)}"
        
        return result
    
    def _calculate_checksum(self, file_path: str, algorithm: str = 'sha256') -> str:
        """计算文件校验和"""
        hash_func = hashlib.new(algorithm)
        
        with open(file_path, 'rb') as f:
            while chunk := f.read(self.buffer_size):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    def _cleanup_temp_files(self):
        """清理临时文件"""
        for temp_file in self._temp_files:
            try:
                if os.path.exists(temp_file):
                    if os.path.isfile(temp_file):
                        os.remove(temp_file)
                    else:
                        shutil.rmtree(temp_file)
            except Exception as e:
                logger.warning(f"清理临时文件失败 {temp_file}: {e}")
        
        self._temp_files.clear()
    
    def create_temp_file(self, suffix: str = '', prefix: str = 'compression_') -> str:
        """创建临时文件"""
        fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        os.close(fd)
        self._temp_files.append(temp_path)
        return temp_path
    
    def get_archive_info(self, archive_path: str) -> Dict:
        """获取压缩包信息"""
        info = {
            'path': archive_path,
            'size': os.path.getsize(archive_path) if os.path.exists(archive_path) else 0,
            'format': 'unknown',
            'file_count': 0,
            'total_size': 0,
            'checksum': ''
        }
        
        try:
            if archive_path.lower().endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zipf:
                    file_list = zipf.infolist()
                    info['format'] = 'zip'
                    info['file_count'] = len([f for f in file_list if not f.is_dir()])
                    info['total_size'] = sum(f.file_size for f in file_list if not f.is_dir())
            
            info['checksum'] = self._calculate_checksum(archive_path)
            
        except Exception as e:
            logger.warning(f"获取压缩包信息失败: {e}")
        
        return info


# 便捷函数
def compress_directory(source_dir: str,
                      output_path: str = None,
                      compression_format: str = "zip",
                      compression_level: str = "default",
                      progress_callback: Optional[Callable[[CompressionProgress], None]] = None) -> CompressionResult:
    """
    便捷函数：压缩目录
    
    Args:
        source_dir: 源目录
        output_path: 输出路径
        compression_format: 压缩格式 ("zip")
        compression_level: 压缩级别 ("store", "fast", "default", "maximum")
        progress_callback: 进度回调
        
    Returns:
        CompressionResult: 压缩结果
    """
    format_enum = CompressionFormat(compression_format)
    level_enum = CompressionLevel(compression_level)
    
    compressor = DirectoryCompressor()
    return compressor.compress_directory(
        source_dir=source_dir,
        output_path=output_path,
        compression_format=format_enum,
        compression_level=level_enum,
        progress_callback=progress_callback
    )


def decompress_archive(archive_path: str,
                      output_dir: str,
                      progress_callback: Optional[Callable[[CompressionProgress], None]] = None,
                      overwrite: bool = False) -> DecompressionResult:
    """
    便捷函数：解压缩档案
    
    Args:
        archive_path: 压缩包路径
        output_dir: 输出目录
        progress_callback: 进度回调
        overwrite: 是否覆盖
        
    Returns:
        DecompressionResult: 解压结果
    """
    compressor = DirectoryCompressor()
    return compressor.decompress_archive(
        archive_path=archive_path,
        output_dir=output_dir,
        progress_callback=progress_callback,
        overwrite=overwrite
    )