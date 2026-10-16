###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  文件：voice_enrollment.py
#  说明：音色克隆服务,调用 Qwen voice-enrollment API 进行音色克隆
#  许可证：Apache License 2.0
###############################################################################

import base64
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any
import aiohttp

from logger import logger
from config_manager import VoiceConfigManager


class VoiceEnrollmentService:
    """音色克隆服务"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_config_manager: Optional[VoiceConfigManager] = None
    ):
        """
        初始化音色克隆服务
        
        参数:
            api_key: Qwen API 密钥(如果不提供,从环境变量读取)
            voice_config_manager: 音色配置管理器实例
        """
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            logger.warning("DASHSCOPE_API_KEY not set, voice cloning will not work")
        
        self.voice_config_manager = voice_config_manager or VoiceConfigManager()
        
        # Qwen voice-enrollment API 端点
        self.enrollment_url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"
        self.target_model = os.getenv("QWEN_VOICE_CLONE_TARGET_MODEL", "qwen3-tts-vc-realtime-2026-01-15")

    def _make_preferred_name(self, voice_name: str) -> str:
        """Qwen requires 1-16 chars containing only letters, digits, and underscores."""
        raw_name = re.sub(r"[^0-9A-Za-z_]", "_", voice_name or "").strip("_").lower()
        if not raw_name:
            raw_name = "voice"
        if not re.match(r"^[A-Za-z]", raw_name):
            raw_name = f"v_{raw_name}"
        return raw_name[:16]

    def _guess_audio_mime_type(self, audio_path: str) -> str:
        suffix = Path(audio_path).suffix.lower()
        if suffix == ".mp3":
            return "audio/mpeg"
        if suffix in {".m4a", ".mp4"}:
            return "audio/mp4"
        return "audio/wav"
    
    async def _call_qwen_enrollment_api(
        self,
        audio_path: str,
        voice_name: str,
        voice_description: str
    ) -> tuple[bool, str, Optional[str]]:
        """
        调用 Qwen voice-enrollment API
        
        参数:
            audio_path: 音频文件路径
            voice_name: 音色名称
            voice_description: 音色描述
            
        返回:
            (是否成功, 错误消息或成功消息, voice_id)
        """
        try:
            # 读取音频文件并编码为 base64
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            mime_type = self._guess_audio_mime_type(audio_path)
            preferred_name = self._make_preferred_name(voice_name)
            
            # 构建请求数据
            request_data = {
                "model": "qwen-voice-enrollment",
                "input": {
                    "action": "create",
                    "target_model": self.target_model,
                    "preferred_name": preferred_name,
                    "audio": {
                        "data": f"data:{mime_type};base64,{audio_base64}"
                    },
                    "language": "zh"
                }
            }
            if voice_description:
                request_data["input"]["text"] = voice_description
            
            # 构建请求头
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 发送请求
            timeout = aiohttp.ClientTimeout(total=60)  # 60秒超时
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.enrollment_url,
                    headers=headers,
                    json=request_data
                ) as response:
                    response_text = await response.text()
                    
                    if response.status != 200:
                        logger.error(f"Qwen enrollment API error: {response.status} - {response_text}")
                        return False, f"API request failed: {response.status} - {response_text}", None
                    
                    # 解析响应
                    response_data = json.loads(response_text)
                    
                    # 检查响应格式
                    output = response_data.get("output", {})
                    if "voice" not in output:
                        logger.error(f"Invalid API response format: {response_text}")
                        return False, "Invalid API response format", None
                    
                    voice_id = output["voice"]
                    target_model = output.get("target_model") or self.target_model
                    
                    logger.info(f"Voice enrollment successful: {voice_id}")
                    return True, "Voice cloned successfully", {
                        "voice": voice_id,
                        "target_model": target_model,
                        "fallback_mode": output.get("fallback_mode"),
                        "fallback_reason": output.get("fallback_reason"),
                    }
            
        except aiohttp.ClientError as e:
            logger.error(f"Network error calling Qwen enrollment API: {e}")
            return False, f"Network error: {str(e)}", None
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse API response: {e}")
            return False, "Failed to parse API response", None
        
        except FileNotFoundError:
            logger.error(f"Audio file not found: {audio_path}")
            return False, f"Audio file not found: {audio_path}", None
        
        except Exception as e:
            logger.error(f"Unexpected error in voice enrollment: {e}")
            return False, f"Unexpected error: {str(e)}", None

    
    async def clone_voice(
        self,
        audio_path: str,
        voice_name: str,
        voice_description: str
        ) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        克隆音色主流程
        
        参数:
            audio_path: 音频文件路径
            voice_name: 音色名称
            voice_description: 音色描述
            
        返回:
            (是否成功, 错误消息或成功消息, 音色配置字典)
        """
        try:
            # 验证 API 密钥
            if not self.api_key:
                return False, "API key not configured", None
            
            # 验证音频文件路径
            if not Path(audio_path).exists():
                return False, f"Audio file not found: {audio_path}", None
            
            # 调用 Qwen API 进行音色克隆
            success, message, enrollment_result = await self._call_qwen_enrollment_api(
                audio_path,
                voice_name,
                voice_description
            )
            
            if not success:
                return False, message, None
            
            # 保存克隆的音色配置
            voice_config = self._save_cloned_voice_config(
                enrollment_result,
                voice_name,
                voice_description,
                audio_path
            )
            
            if voice_config is None:
                return False, "Failed to save voice config", None
            
            return True, "Voice cloned and saved successfully", voice_config
            
        except Exception as e:
            logger.error(f"Error in clone_voice: {e}")
            return False, f"Clone voice error: {str(e)}", None
    
    def _save_cloned_voice_config(
        self,
        enrollment_result: Dict[str, Any],
        voice_name: str,
        voice_description: str,
        audio_path: str
    ) -> Optional[Dict[str, Any]]:
        """
        保存克隆的音色配置到配置文件
        
        参数:
            voice_id: Qwen 返回的 voice_id
            voice_name: 音色名称
            voice_description: 音色描述
            audio_path: 音频文件路径
            
        返回:
            音色配置字典,失败返回 None
        """
        try:
            voice_id = enrollment_result["voice"]
            # 生成唯一的 voice_id(使用 cloned_ 前缀)
            config_voice_id = f"cloned_{voice_id}"
            
            # 构建音色配置
            voice_config = {
                "voice_id": config_voice_id,
                "name": voice_name,
                "description": voice_description,
                "type": "cloned",
                "qwen_config": {
                    "voice": voice_id,
                    "audio_path": audio_path,
                    "model": enrollment_result.get("target_model") or self.target_model,
                    "fallback_mode": enrollment_result.get("fallback_mode"),
                    "fallback_reason": enrollment_result.get("fallback_reason")
                },
                "icon": "bi bi-mic-fill"
            }
            
            # 添加到配置管理器
            success, message = self.voice_config_manager.add_voice(voice_config)
            
            if not success:
                logger.error(f"Failed to save voice config: {message}")
                return None
            
            logger.info(f"Saved cloned voice config: {config_voice_id}")
            return voice_config
            
        except Exception as e:
            logger.error(f"Error saving cloned voice config: {e}")
            return None
