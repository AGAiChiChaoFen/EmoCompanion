###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  文件：file_handler.py
#  说明：文件上传处理器,负责验证和保存上传的音频和图片文件
#  许可证：Apache License 2.0
###############################################################################

import os
import uuid
import wave
from pathlib import Path
from typing import Optional, Dict, Any, List
from PIL import Image

from logger import logger

BASE_DIR = Path(__file__).resolve().parent


def _resolve_local_path(path_value: str | Path) -> Path:
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate
    if candidate.parts and candidate.parts[0] == BASE_DIR.name:
        return BASE_DIR.parent / candidate
    return BASE_DIR / candidate


def _to_livetalking_relative_path(path_value: str | Path) -> str:
    path = Path(path_value).resolve()
    try:
        return path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return path.as_posix()


class FileUploadHandler:
    """文件上传处理器"""
    
    def __init__(
        self,
        audio_upload_dir: str = "data/uploaded_audio",
        avatar_upload_dir: str = "data/avatars/custom"
    ):
        """
        初始化文件上传处理器
        
        参数:
            audio_upload_dir: 音频文件上传目录
            avatar_upload_dir: 形象图片上传目录
        """
        self.audio_upload_dir = _resolve_local_path(audio_upload_dir)
        self.avatar_upload_dir = _resolve_local_path(avatar_upload_dir)
        
        # 确保目录存在
        self.audio_upload_dir.mkdir(parents=True, exist_ok=True)
        self.avatar_upload_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_audio_file(
        self,
        file_path: str,
        min_duration: float = 10.0,
        max_duration: float = 20.0,
        required_sample_rate: int = 16000,
        required_channels: int = 1
    ) -> tuple[bool, str, List[str]]:
        """
        验证音频文件是否符合要求
        
        参数:
            file_path: 音频文件路径
            min_duration: 最小时长(秒)
            max_duration: 最大时长(秒)
            required_sample_rate: 要求的采样率
            required_channels: 要求的声道数
            
        返回:
            (是否有效, 错误消息, 警告列表)
        """
        warnings = []
        
        try:
            path = Path(file_path)
            
            # 检查文件是否存在
            if not path.exists():
                return False, f"Audio file not found: {file_path}", []
            
            # 检查文件大小(最大 10MB)
            file_size = path.stat().st_size
            max_size = 10 * 1024 * 1024  # 10MB
            if file_size > max_size:
                return False, f"Audio file too large: {file_size / 1024 / 1024:.2f}MB (max 10MB)", []
            
            # 检查文件扩展名
            valid_extensions = {'.wav', '.mp3', '.flac', '.m4a'}
            if path.suffix.lower() not in valid_extensions:
                return False, f"Invalid audio file extension: {path.suffix} (supported: {', '.join(valid_extensions)})", []
            
            # 对于 WAV 文件,进行详细检查
            if path.suffix.lower() == '.wav':
                try:
                    with wave.open(str(path), 'rb') as wav_file:
                        # 获取音频参数
                        channels = wav_file.getnchannels()
                        sample_rate = wav_file.getframerate()
                        frames = wav_file.getnframes()
                        duration = frames / float(sample_rate)
                        
                        # 检查时长
                        if duration < min_duration:
                            return False, f"Audio too short: {duration:.1f}s (min {min_duration}s required)", []
                        
                        if duration > max_duration:
                            warnings.append(f"Audio longer than recommended: {duration:.1f}s (recommended {max_duration}s)")
                        
                        # 检查采样率
                        if sample_rate != required_sample_rate:
                            warnings.append(f"Sample rate {sample_rate}Hz (recommended {required_sample_rate}Hz)")
                        
                        # 检查声道数
                        if channels != required_channels:
                            warnings.append(f"Audio has {channels} channel(s) (recommended {required_channels})")
                        
                        logger.info(f"Audio validation passed: {path.name} ({duration:.1f}s, {sample_rate}Hz, {channels}ch)")
                        
                except wave.Error as e:
                    return False, f"Invalid WAV file: {str(e)}", []
            
            else:
                # 对于其他格式,只做基本检查
                warnings.append(f"Audio format {path.suffix} - detailed validation not available, please ensure it meets requirements")
            
            return True, "", warnings
            
        except Exception as e:
            logger.error(f"Error validating audio file {file_path}: {e}")
            return False, f"Audio validation error: {str(e)}", []

    
    def validate_image_file(
        self,
        file_path: str,
        max_size_mb: float = 5.0
    ) -> tuple[bool, str]:
        """
        验证图片文件是否符合要求
        
        参数:
            file_path: 图片文件路径
            max_size_mb: 最大文件大小(MB)
            
        返回:
            (是否有效, 错误消息)
        """
        try:
            path = Path(file_path)
            
            # 检查文件是否存在
            if not path.exists():
                return False, f"Image file not found: {file_path}"
            
            # 检查文件大小
            file_size = path.stat().st_size
            max_size = max_size_mb * 1024 * 1024
            if file_size > max_size:
                return False, f"Image file too large: {file_size / 1024 / 1024:.2f}MB (max {max_size_mb}MB)"
            
            # 检查文件扩展名
            valid_extensions = {'.png', '.jpg', '.jpeg', '.webp'}
            if path.suffix.lower() not in valid_extensions:
                return False, f"Invalid image file extension: {path.suffix} (supported: {', '.join(valid_extensions)})"
            
            # 尝试打开图片验证格式
            try:
                with Image.open(path) as img:
                    # 验证图片格式
                    if img.format.lower() not in ['png', 'jpeg', 'webp']:
                        return False, f"Unsupported image format: {img.format}"
                    
                    # 获取图片尺寸
                    width, height = img.size
                    logger.info(f"Image validation passed: {path.name} ({width}x{height}, {img.format})")
                    
            except Exception as e:
                return False, f"Invalid image file: {str(e)}"
            
            return True, ""
            
        except Exception as e:
            logger.error(f"Error validating image file {file_path}: {e}")
            return False, f"Image validation error: {str(e)}"
    
    def generate_unique_filename(self, original_filename: str) -> str:
        """
        生成唯一的文件名
        
        参数:
            original_filename: 原始文件名
            
        返回:
            唯一文件名
        """
        # 获取文件扩展名
        path = Path(original_filename)
        extension = path.suffix
        
        # 生成 UUID
        unique_id = uuid.uuid4().hex[:12]
        
        # 组合新文件名
        new_filename = f"{unique_id}{extension}"
        
        return new_filename
    
    async def save_audio_file(
        self,
        file_data: bytes,
        original_filename: str
    ) -> tuple[bool, str, Optional[str]]:
        """
        保存音频文件
        
        参数:
            file_data: 文件数据
            original_filename: 原始文件名
            
        返回:
            (是否成功, 错误消息或成功消息, 保存的文件路径)
        """
        try:
            # 生成唯一文件名
            filename = self.generate_unique_filename(original_filename)
            file_path = self.audio_upload_dir / filename
            
            # 保存文件
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            logger.info(f"Saved audio file: {file_path}")
            
            # 验证保存的文件
            is_valid, error_msg, warnings = self.validate_audio_file(str(file_path))
            
            if not is_valid:
                # 删除无效文件
                file_path.unlink()
                return False, f"Audio validation failed: {error_msg}", None
            
            # 返回相对路径
            relative_path = _to_livetalking_relative_path(file_path)
            
            if warnings:
                warning_msg = "; ".join(warnings)
                return True, f"Audio saved with warnings: {warning_msg}", relative_path
            
            return True, "Audio file saved successfully", relative_path
            
        except Exception as e:
            logger.error(f"Error saving audio file: {e}")
            return False, f"Failed to save audio: {str(e)}", None
    
    async def save_image_file(
        self,
        file_data: bytes,
        original_filename: str
    ) -> tuple[bool, str, Optional[str]]:
        """
        保存图片文件
        
        参数:
            file_data: 文件数据
            original_filename: 原始文件名
            
        返回:
            (是否成功, 错误消息或成功消息, 保存的文件路径)
        """
        try:
            # 生成唯一文件名
            filename = self.generate_unique_filename(original_filename)
            file_path = self.avatar_upload_dir / filename
            
            # 保存文件
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            logger.info(f"Saved image file: {file_path}")
            
            # 验证保存的文件
            is_valid, error_msg = self.validate_image_file(str(file_path))
            
            if not is_valid:
                # 删除无效文件
                file_path.unlink()
                return False, f"Image validation failed: {error_msg}", None
            
            # 返回相对路径
            relative_path = _to_livetalking_relative_path(file_path)
            
            return True, "Image file saved successfully", relative_path
            
        except Exception as e:
            logger.error(f"Error saving image file: {e}")
            return False, f"Failed to save image: {str(e)}", None
