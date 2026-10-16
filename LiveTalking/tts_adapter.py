###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  文件：tts_adapter.py
#  说明：Qwen3-TTS 适配器,根据音色类型动态构建 TTS 参数
#  许可证：Apache License 2.0
###############################################################################

import os
from typing import Optional, Dict, Any, Iterator, List, Tuple
import base64
import time
import numpy as np
import resampy

from logger import logger
from config_manager import VoiceConfigManager


class Qwen3TTSAdapter:
    """Qwen3-TTS 适配器,支持 preset/described/cloned 三种音色类型"""

    FALLBACK_VOICE = "Cherry"
    MALE_FALLBACK_VOICE = "Ethan"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_config_manager: Optional[VoiceConfigManager] = None
    ):
        """
        初始化 Qwen3-TTS 适配器
        
        参数:
            api_key: Qwen API 密钥(如果不提供,从环境变量读取)
            voice_config_manager: 音色配置管理器实例
        """
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            logger.warning("DASHSCOPE_API_KEY not set, TTS will not work")
        
        self.voice_config_manager = voice_config_manager or VoiceConfigManager()
        
        # 默认参数
        self.model = "qwen3-tts-flash"
        self.base_url = "https://dashscope.aliyuncs.com/api/v1"
        self.language_type = "Chinese"
        self.sample_rate = 16000  # 目标采样率
        self.chunk_size = 320  # 16kHz、20ms 的采样点数
        
        # 初始化 dashscope
        self.dashscope = None
        try:
            import dashscope
            dashscope.base_http_api_url = self.base_url
            self.dashscope = dashscope
            logger.info("Qwen3-TTS adapter initialized successfully")
        except ImportError:
            logger.error("dashscope not installed, please install: pip install dashscope")
        except Exception as e:
            logger.error(f"Failed to initialize dashscope: {e}")
    
    def _build_tts_params(
        self,
        text: str,
        voice_id: str,
        voice_override: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        根据音色类型构建 TTS 参数
        
        参数:
            text: 要合成的文本
            voice_id: 音色 ID
            
        返回:
            TTS 参数字典,失败返回 None
        """
        try:
            # 获取音色配置
            voice_config = self.voice_config_manager.get_voice_by_id(voice_id)
            
            if voice_config is None:
                logger.warning(f"Voice not found: {voice_id}, using default voice")
                # 使用默认音色
                return {
                    "model": self.model,
                    "api_key": self.api_key,
                    "text": text,
                    "voice": "Cherry",  # 默认音色
                    "language_type": self.language_type,
                    "stream": True
                }
            
            voice_type = voice_config.get("type")
            qwen_config = voice_config.get("qwen_config", {})
            
            # 基础参数
            params = {
                "model": self.model,
                "api_key": self.api_key,
                "text": text,
                "language_type": self.language_type,
                "stream": True
            }
            
            # 根据音色类型添加特定参数
            if voice_type == "preset":
                # 预设音色:使用 voice 参数
                voice_name = qwen_config.get("voice", "Cherry")
                params["voice"] = voice_name
                logger.info(f"Using preset voice: {voice_name}")
            
            elif voice_type == "described":
                # 描述音色:使用 instructions 参数
                instructions = qwen_config.get("instructions", "")
                if not instructions:
                    logger.warning(f"Voice {voice_id} has no instructions, using default voice")
                    params["voice"] = "Cherry"
                else:
                    params["instructions"] = instructions
                    params["optimize_instructions"] = qwen_config.get("optimize_instructions", False)
                    logger.info(f"Using described voice with instructions: {instructions[:50]}...")
            
            elif voice_type == "cloned":
                # 克隆音色:使用 voice 参数(Qwen API 返回的 voice_id)
                cloned_voice_id = qwen_config.get("voice")
                if not cloned_voice_id:
                    logger.error(f"Cloned voice {voice_id} has no voice field")
                    params["voice"] = "Cherry"
                else:
                    if qwen_config.get("model"):
                        params["model"] = qwen_config["model"]
                    params["voice"] = cloned_voice_id
                    logger.info(f"Using cloned voice: {cloned_voice_id}, model: {params['model']}")
            
            else:
                logger.warning(f"Unknown voice type: {voice_type}, using default voice")
                params["voice"] = "Cherry"

            if voice_override:
                params.pop("instructions", None)
                params.pop("optimize_instructions", None)
                params["voice"] = voice_override
                logger.warning(
                    "Retrying Qwen TTS with fallback voice: original_voice_id=%s fallback_voice=%s",
                    voice_id,
                    voice_override,
                )
            
            return params
            
        except Exception as e:
            logger.error(f"Error building TTS params: {e}")
            # 返回默认参数
            return {
                "model": self.model,
                "api_key": self.api_key,
                "text": text,
                "voice": "Cherry",
                "language_type": self.language_type,
                "stream": True
            }

    
    def _safe_map_get(self, container, key, default=None):
        """
        安全地从容器中获取值
        
        参数:
            container: 容器对象
            key: 键
            default: 默认值
            
        返回:
            值或默认值
        """
        if container is None:
            return default
        if isinstance(container, dict):
            return container.get(key, default)
        try:
            return container[key]
        except Exception:
            return default
    
    def _extract_audio_b64(self, event):
        """
        从 DashScope 响应事件中提取 base64 编码的音频数据
        
        参数:
            event: DashScope 响应事件
            
        返回:
            base64 编码的音频字符串
        """
        output = self._safe_map_get(event, "output", {})
        audio = self._safe_map_get(output, "audio", {})
        chunk_b64 = self._safe_map_get(audio, "data", "")
        return chunk_b64 if isinstance(chunk_b64, str) else ""

    def _safe_response_value(self, event, key: str, default=None):
        value = self._safe_map_get(event, key, None)
        if value is not None:
            return value
        try:
            return getattr(event, key)
        except Exception:
            return default

    def _extract_event_diagnostic(self, event) -> str:
        code = self._safe_response_value(event, "code", "")
        message = self._safe_response_value(event, "message", "")
        request_id = self._safe_response_value(event, "request_id", "")
        status_code = self._safe_response_value(event, "status_code", "")

        output = self._safe_map_get(event, "output", {})
        if not message:
            message = self._safe_map_get(output, "message", "")

        parts = []
        if status_code:
            parts.append(f"status={status_code}")
        if code:
            parts.append(f"code={code}")
        if message:
            parts.append(f"message={message}")
        if request_id:
            parts.append(f"request_id={request_id}")
        return ", ".join(parts)

    def _voice_fallback_candidates(self, voice_id: str) -> List[str]:
        voice_config = self.voice_config_manager.get_voice_by_id(voice_id)
        raw_parts = [voice_id]
        if voice_config:
            raw_parts.extend([
                str(voice_config.get("name", "")),
                str(voice_config.get("description", "")),
                str(voice_config.get("qwen_config", {}).get("voice", "")),
            ])

        descriptor = " ".join(raw_parts).lower()
        candidates = []
        if any(token in descriptor for token in ("male", "男", "mason", "alex", "noah", "oliver", "lucas", "james", "ethan")):
            candidates.append(self.MALE_FALLBACK_VOICE)
        candidates.append(self.FALLBACK_VOICE)

        unique_candidates = []
        for candidate in candidates:
            if candidate and candidate not in unique_candidates:
                unique_candidates.append(candidate)
        return unique_candidates
    
    async def _call_qwen_tts_api(
        self,
        text: str,
        voice_id: str,
        voice_override: Optional[str] = None
    ) -> Iterator[bytes]:
        """
        调用 Qwen TTS API 生成音频流
        
        参数:
            text: 要合成的文本
            voice_id: 音色 ID
            
        返回:
            音频字节流迭代器
        """
        if not self.dashscope:
            logger.error("dashscope not available")
            return
        
        if not self.api_key:
            logger.error("API key not configured")
            return
        
        if not text:
            logger.warning("Empty text provided")
            return
        
        # 构建 TTS 参数
        params = self._build_tts_params(text, voice_id, voice_override=voice_override)
        if params is None:
            logger.error("Failed to build TTS params")
            return
        
        start = time.perf_counter()
        first = True
        
        try:
            # 调用 DashScope API
            response_stream = self.dashscope.MultiModalConversation.call(**params)

            event_count = 0
            diagnostic_logged = False
            for event in response_stream:
                event_count += 1
                # 提取音频数据
                chunk_b64 = self._extract_audio_b64(event)
                if not chunk_b64:
                    if not diagnostic_logged:
                        diagnostic = self._extract_event_diagnostic(event)
                        if diagnostic:
                            logger.warning("Qwen TTS event without audio: %s", diagnostic)
                            diagnostic_logged = True
                    continue
                
                try:
                    chunk = base64.b64decode(chunk_b64)
                except Exception as e:
                    logger.warning(f"Failed to decode audio chunk: {e}")
                    continue
                
                if not chunk:
                    continue
                
                if first:
                    logger.info(f"Qwen TTS time to first chunk: {time.perf_counter() - start:.4f}s")
                    first = False
                
                yield chunk

            if first:
                logger.warning(
                    "Qwen TTS returned no audio chunks: voice_id=%s voice=%s events=%s",
                    voice_id,
                    params.get("voice", "<instructions>"),
                    event_count,
                )
        
        except Exception as e:
            logger.error(f"Qwen TTS API call failed: {e}")

    async def _collect_speech_frames(
        self,
        text: str,
        voice_id: str,
        voice_override: Optional[str] = None
    ) -> Tuple[List[np.ndarray], int]:
        frames: List[np.ndarray] = []
        last_stream = np.array([], dtype=np.float32)
        chunk_count = 0

        async for chunk in self._call_qwen_tts_api(text, voice_id, voice_override=voice_override):
            if chunk is None or len(chunk) == 0:
                continue

            chunk_count += 1
            # Qwen-TTS 输出是 24kHz 单声道 PCM,需要重采样到 16kHz
            stream = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767.0
            stream = resampy.resample(x=stream, sr_orig=24000, sr_new=self.sample_rate)
            stream = np.concatenate((last_stream, stream))

            # 切分为 20ms 帧
            streamlen = stream.shape[0]
            idx = 0
            while streamlen >= self.chunk_size:
                frames.append(stream[idx:idx + self.chunk_size])
                streamlen -= self.chunk_size
                idx += self.chunk_size

            # 保存不足一帧的尾部
            last_stream = stream[idx:]

        # 如果有剩余数据,补零到一帧
        if last_stream.shape[0] > 0:
            padding = np.zeros(self.chunk_size - last_stream.shape[0], dtype=np.float32)
            frames.append(np.concatenate((last_stream, padding)))

        return frames, chunk_count
    
    async def generate_speech(
        self,
        text: str,
        voice_id: str
    ) -> Iterator[np.ndarray]:
        """
        生成语音音频流(已重采样到 16kHz 并切分为 20ms 帧)
        
        参数:
            text: 要合成的文本
            voice_id: 音色 ID
            
        返回:
            音频帧迭代器(每帧 320 个采样点,16kHz,20ms)
        """
        attempts: List[Tuple[Optional[str], str]] = [(None, "configured")]
        for fallback_voice in self._voice_fallback_candidates(voice_id):
            attempts.append((fallback_voice, fallback_voice))

        tried = set()
        for voice_override, label in attempts:
            if label in tried:
                continue
            tried.add(label)

            frames, chunk_count = await self._collect_speech_frames(text, voice_id, voice_override=voice_override)
            if frames:
                if voice_override:
                    logger.warning(
                        "Qwen TTS fallback succeeded: voice_id=%s fallback_voice=%s frames=%s chunks=%s",
                        voice_id,
                        voice_override,
                        len(frames),
                        chunk_count,
                    )
                for frame in frames:
                    yield frame
                return

            logger.warning(
                "Qwen TTS produced no frames for attempt: voice_id=%s voice=%s chunks=%s",
                voice_id,
                label,
                chunk_count,
            )

        logger.error("Qwen TTS failed after all fallback attempts: voice_id=%s", voice_id)
