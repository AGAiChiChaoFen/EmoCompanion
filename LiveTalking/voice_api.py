###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  文件：voice_api.py
#  说明：音色、形象配置、语音合成和离线数字人视频生成相关 aiohttp 路由。
#  许可证：Apache License 2.0
###############################################################################

from __future__ import annotations

import argparse
import asyncio
import io
import os
import tempfile
import time
import wave
from typing import Any, Dict, Optional, Tuple
from pathlib import Path

import aiohttp
from aiohttp import web
import numpy as np

from logger import logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
opt: Any = None


def configure_voice_api_runtime(options: Any, base_dir: Optional[str] = None) -> None:
    """注入 app.py 启动阶段解析出的运行时配置。"""
    global opt, BASE_DIR
    opt = options
    if base_dir:
        BASE_DIR = base_dir


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_static_media_path(path_value: str) -> str:
    path = str(path_value or '').strip().replace('\\', '/')
    if not path:
        return ''

    data_index = path.find('/data/')
    if data_index >= 0:
        return path[data_index + 1:]

    livetalking_marker = 'LiveTalking/data/'
    marker_index = path.find(livetalking_marker)
    if marker_index >= 0:
        return path[marker_index + len('LiveTalking/'):]

    if path.startswith('data/'):
        return path

    avatars_index = path.find('/avatars/')
    if avatars_index >= 0:
        return f"data{path[avatars_index:]}"

    return path.lstrip('/')


def _resolve_livetalking_file_path(path_value: str) -> str:
    path = str(path_value or '').strip()
    if not path:
        return ''
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, _normalize_static_media_path(path))


def _make_uploaded_avatar_config(image_path: str, original_filename: str) -> Dict[str, Any]:
    safe_stem = Path(original_filename or 'uploaded_avatar').stem[:40] or 'uploaded_avatar'
    timestamp = int(time.time() * 1000)
    avatar_id = f"custom_avatar_{timestamp}"

    return {
        'avatar_id': avatar_id,
        'name': f'自定义形象 {safe_stem}',
        'description': '用户上传的数字人形象',
        'type': 'custom',
        'image_path': image_path,
        'image_url': f'/{image_path}',
        'icon': 'bi bi-person-circle',
    }


###########################################################################################
# 🆕 音色和形象配置 API 路由
###########################################################################################

# 全局配置管理器实例（预加载）
_voice_config_manager = None
_avatar_config_manager = None
_file_upload_handler = None
_voice_enrollment_service = None


def init_voice_services():
    """
    预加载音色和数字人生成相关服务（服务器启动时调用）
    
    这个函数应该在 app.py 的启动代码中调用，以便预加载模型
    """
    global _voice_config_manager, _avatar_config_manager, _file_upload_handler, _voice_enrollment_service
    
    try:
        logger.info('[Voice Services] 开始预加载音色和数字人生成服务...')
        
        # 1. 加载音色配置管理器
        from config_manager import VoiceConfigManager
        _voice_config_manager = VoiceConfigManager()
        logger.info('[Voice Services] ✅ 音色配置管理器加载完成')
        
        # 2. 加载头像配置管理器
        from config_manager import AvatarConfigManager
        _avatar_config_manager = AvatarConfigManager()
        logger.info('[Voice Services] ✅ 头像配置管理器加载完成')
        
        # 3. 加载文件上传处理器
        from file_handler import FileUploadHandler
        _file_upload_handler = FileUploadHandler()
        logger.info('[Voice Services] ✅ 文件上传处理器加载完成')
        
        # 4. 加载音色克隆服务
        from voice_enrollment import VoiceEnrollmentService
        _voice_enrollment_service = VoiceEnrollmentService(
            voice_config_manager=_voice_config_manager
        )
        logger.info('[Voice Services] ✅ 音色克隆服务加载完成')
        
        logger.info('[Voice Services] ✅ 所有服务预加载完成！')
        
    except Exception as e:
        logger.error(f'[Voice Services] ❌ 服务预加载失败: {e}')
        raise


def _get_voice_config_manager():
    """获取音色配置管理器实例"""
    global _voice_config_manager
    if _voice_config_manager is None:
        raise RuntimeError('[Voice Services] 音色配置管理器未初始化，请先调用 init_voice_services()')
    return _voice_config_manager

def _get_avatar_config_manager():
    """获取形象配置管理器实例"""
    global _avatar_config_manager
    if _avatar_config_manager is None:
        raise RuntimeError('[Voice Services] 头像配置管理器未初始化，请先调用 init_voice_services()')
    return _avatar_config_manager

def _get_file_upload_handler():
    """获取文件上传处理器实例"""
    global _file_upload_handler
    if _file_upload_handler is None:
        raise RuntimeError('[Voice Services] 文件上传处理器未初始化，请先调用 init_voice_services()')
    return _file_upload_handler

def _get_voice_enrollment_service():
    """获取音色克隆服务实例"""
    global _voice_enrollment_service
    if _voice_enrollment_service is None:
        raise RuntimeError('[Voice Services] 音色克隆服务未初始化，请先调用 init_voice_services()')
    return _voice_enrollment_service


async def get_voices(request):
    """
    GET /api/voices
    获取所有音色配置列表
    """
    try:
        manager = _get_voice_config_manager()
        voices = manager.get_all_voices()
        
        logger.info(f"Successfully loaded {len(voices)} voices from config")
        
        return web.json_response({
            'code': 0,
            'msg': 'success',
            'data': {
                'voices': voices
            }
        })
    
    except RuntimeError as e:
        # 配置文件加载失败的明确错误
        logger.error(f'Voice config error: {str(e)}')
        return web.json_response({
            'code': -1,
            'msg': f'配置文件错误: {str(e)}'
        }, status=500)
    
    except Exception as e:
        logger.exception('get_voices exception:')
        return web.json_response({
            'code': -1,
            'msg': f'Failed to get voices: {str(e)}'
        }, status=500)


async def get_avatars(request):
    """
    GET /api/avatars
    获取所有形象配置列表
    """
    try:
        manager = _get_avatar_config_manager()
        avatars = manager.get_all_avatars()
        
        return web.json_response({
            'code': 0,
            'msg': 'success',
            'data': {
                'avatars': avatars
            }
        })
    
    except Exception as e:
        logger.exception('get_avatars exception:')
        return web.json_response({
            'code': -1,
            'msg': f'Failed to get avatars: {str(e)}'
        }, status=500)


async def upload_audio(request):
    """
    POST /api/upload/audio
    上传音频文件用于音色克隆
    """
    try:
        # 读取 multipart/form-data
        reader = await request.multipart()
        
        audio_file = None
        audio_filename = None
        
        # 解析表单数据
        async for field in reader:
            if field.name == 'audio':
                audio_filename = field.filename
                audio_file = await field.read()
                break
        
        if not audio_file or not audio_filename:
            return web.json_response({
                'code': -1,
                'msg': 'No audio file provided'
            }, status=400)
        
        # 保存音频文件
        handler = _get_file_upload_handler()
        success, message, file_path = await handler.save_audio_file(audio_file, audio_filename)
        
        if not success:
            return web.json_response({
                'code': -1,
                'msg': message
            }, status=400)
        
        # 返回文件路径和警告信息
        return web.json_response({
            'code': 0,
            'msg': 'success',
            'data': {
                'audio_path': file_path,
                'warnings': message if 'warnings' in message else None
            }
        })
    
    except Exception as e:
        logger.exception('upload_audio exception:')
        return web.json_response({
            'code': -1,
            'msg': f'Failed to upload audio: {str(e)}'
        }, status=500)


async def upload_avatar(request):
    """
    POST /api/upload/avatar
    上传形象图片
    """
    try:
        # 读取 multipart/form-data
        reader = await request.multipart()
        
        image_file = None
        image_filename = None
        
        # 解析表单数据
        async for field in reader:
            if field.name == 'image':
                image_filename = field.filename
                image_file = await field.read()
                break
        
        if not image_file or not image_filename:
            return web.json_response({
                'code': -1,
                'msg': 'No image file provided'
            }, status=400)
        
        # 保存图片文件
        handler = _get_file_upload_handler()
        success, message, file_path = await handler.save_image_file(image_file, image_filename)
        
        if not success:
            return web.json_response({
                'code': -1,
                'msg': message
            }, status=400)

        image_path = _normalize_static_media_path(file_path)
        avatar_manager = _get_avatar_config_manager()
        avatar_config = _make_uploaded_avatar_config(image_path, image_filename)
        add_success, add_message = avatar_manager.add_avatar(avatar_config)

        if not add_success:
            return web.json_response({
                'code': -1,
                'msg': f'Image saved but avatar registration failed: {add_message}'
            }, status=500)
        
        # 返回文件路径
        return web.json_response({
            'code': 0,
            'msg': 'success',
            'data': {
                'image_path': image_path,
                'avatar': avatar_config,
                'avatar_id': avatar_config['avatar_id']
            }
        })
    
    except Exception as e:
        logger.exception('upload_avatar exception:')
        return web.json_response({
            'code': -1,
            'msg': f'Failed to upload avatar: {str(e)}'
        }, status=500)


async def delete_avatar(request):
    """
    DELETE /api/avatars/{avatar_id}
    删除自定义形象
    """
    try:
        avatar_id = request.match_info.get('avatar_id', '').strip()
        if not avatar_id:
            return web.json_response({
                'code': -1,
                'msg': 'avatar_id is required'
            }, status=400)

        avatar_manager = _get_avatar_config_manager()
        success, message, image_path = avatar_manager.remove_avatar(avatar_id)

        if not success:
            status = 404 if 'not found' in message.lower() else 400
            return web.json_response({
                'code': -1,
                'msg': message
            }, status=status)

        return web.json_response({
            'code': 0,
            'msg': 'success',
            'data': {
                'avatar_id': avatar_id,
                'image_path': _normalize_static_media_path(image_path or '')
            }
        })

    except Exception as e:
        logger.exception('delete_avatar exception:')
        return web.json_response({
            'code': -1,
            'msg': f'Failed to delete avatar: {str(e)}'
        }, status=500)


async def clone_voice(request):
    """
    POST /api/voices/clone
    克隆音色
    
    请求体:
    {
        "audio_path": "上传的音频文件路径",
        "voice_name": "音色名称",
        "voice_description": "音色描述"
    }
    """
    try:
        params = await request.json()
        
        audio_path = params.get('audio_path', '')
        voice_name = params.get('voice_name', '')
        voice_description = params.get('voice_description', '')
        
        if not audio_path:
            return web.json_response({
                'code': -1,
                'msg': 'audio_path is required'
            }, status=400)
        
        if not voice_name:
            return web.json_response({
                'code': -1,
                'msg': 'voice_name is required'
            }, status=400)
        
        resolved_audio_path = _resolve_livetalking_file_path(audio_path)

        # 调用音色克隆服务
        service = _get_voice_enrollment_service()
        success, message, voice_config = await service.clone_voice(
            resolved_audio_path,
            voice_name,
            voice_description
        )
        
        if not success:
            return web.json_response({
                'code': -1,
                'msg': message
            }, status=400)
        
        return web.json_response({
            'code': 0,
            'msg': 'success',
            'data': {
                'voice': voice_config
            }
        })
    
    except Exception as e:
        logger.exception('clone_voice exception:')
        return web.json_response({
            'code': -1,
            'msg': f'Failed to clone voice: {str(e)}'
        }, status=500)


async def generate_speech(request):
    """
    POST /api/generate/speech
    纯语音合成(不生成视频)
    
    请求体:
    {
        "text": "要合成的文本",
        "voice_id": "音色ID(可选,默认使用第一个音色)"
    }
    
    返回: 音频文件(WAV格式)
    """
    try:
        params = await request.json()
        
        text = params.get('text', '')
        voice_id = params.get('voice_id', '')
        
        if not text:
            return web.json_response({
                'code': -1,
                'msg': 'text is required'
            }, status=400)
        
        # 获取音色配置
        voice_manager = _get_voice_config_manager()
        if voice_id:
            voice_config = voice_manager.get_voice_by_id(voice_id)
            if voice_config is None:
                return web.json_response({
                    'code': -1,
                    'msg': f'Voice not found: {voice_id}'
                }, status=400)
        else:
            # 使用默认音色(第一个)
            voices = voice_manager.get_all_voices()
            voice_config = voices[0] if voices else None
            if voice_config is None:
                return web.json_response({
                    'code': -1,
                    'msg': 'No voices available'
                }, status=500)
        
        # 使用 TTS 适配器生成语音
        from tts_adapter import Qwen3TTSAdapter
        tts_adapter = Qwen3TTSAdapter(voice_config_manager=voice_manager)
        
        # 收集所有音频帧
        audio_frames = []
        async for frame in tts_adapter.generate_speech(text, voice_config['voice_id']):
            audio_frames.append(frame)
        
        if not audio_frames:
            return web.json_response({
                'code': -1,
                'msg': 'Failed to generate speech'
            }, status=500)
        
        # 合并所有音频帧
        audio_data = np.concatenate(audio_frames)
        
        # 转换为 16bit PCM
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        # 创建 WAV 文件
        import io
        import wave
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # 单声道
            wav_file.setsampwidth(2)  # 16bit
            wav_file.setframerate(16000)  # 16kHz
            wav_file.writeframes(audio_int16.tobytes())
        
        wav_buffer.seek(0)
        
        # 返回音频文件
        return web.Response(
            body=wav_buffer.read(),
            content_type='audio/wav',
            headers={
                'Content-Disposition': f'attachment; filename="speech_{int(time.time())}.wav"'
            }
        )
    
    except Exception as e:
        logger.exception('generate_speech exception:')
        return web.json_response({
            'code': -1,
            'msg': f'Failed to generate speech: {str(e)}'
        }, status=500)


async def generate_video(request):
    """
    POST /api/generate/video
    生成数字人视频
    
    请求体:
    {
        "text": "要合成的文本",
        "voice_id": "音色ID(可选,默认使用第一个音色)",
        "avatar_id": "形象ID(可选,默认使用第一个形象)"
    }
    
    返回: MP4 视频文件流
    """
    try:
        params = await request.json()
        
        text = params.get('text', '')
        voice_id = params.get('voice_id', '')
        avatar_id = params.get('avatar_id', '')
        
        if not text:
            return web.json_response({
                'code': -1,
                'msg': 'text is required'
            }, status=400)
        
        logger.info(f"Generating video: text='{text}', voice_id='{voice_id}', avatar_id='{avatar_id}'")
        
        # 获取音色配置
        voice_manager = _get_voice_config_manager()
        if voice_id:
            voice_config = voice_manager.get_voice_by_id(voice_id)
            if voice_config is None:
                return web.json_response({
                    'code': -1,
                    'msg': f'Voice not found: {voice_id}'
                }, status=400)
        else:
            # 使用默认音色(第一个)
            voices = voice_manager.get_all_voices()
            voice_config = voices[0] if voices else None
            if voice_config is None:
                return web.json_response({
                    'code': -1,
                    'msg': 'No voices available'
                }, status=500)
        
        # 获取形象配置
        avatar_manager = _get_avatar_config_manager()
        if avatar_id:
            avatar_config = avatar_manager.get_avatar_by_id(avatar_id)
            if avatar_config is None:
                return web.json_response({
                    'code': -1,
                    'msg': f'Avatar not found: {avatar_id}'
                }, status=400)
        else:
            # 使用默认形象(第一个)
            avatars = avatar_manager.get_all_avatars()
            avatar_config = avatars[0] if avatars else None
            if avatar_config is None:
                return web.json_response({
                    'code': -1,
                    'msg': 'No avatars available'
                }, status=500)
        
        # 生成唯一的会话ID用于临时文件
        import uuid
        session_id = str(uuid.uuid4())[:8]
        
        # 调用离线视频生成函数
        video_path = await _generate_offline_video(
            text=text,
            voice_config=voice_config,
            avatar_config=avatar_config,
            session_id=session_id
        )
        
        if not video_path or not os.path.exists(video_path):
            return web.json_response({
                'code': -1,
                'msg': 'Failed to generate video file'
            }, status=500)
        
        # 返回视频文件
        return web.FileResponse(
            video_path,
            headers={
                'Content-Type': 'video/mp4',
                'Content-Disposition': f'attachment; filename="avatar_{session_id}.mp4"'
            }
        )
    
    except Exception as e:
        logger.exception('generate_video exception:')
        return web.json_response({
            'code': -1,
            'msg': f'Failed to generate video: {str(e)}'
        }, status=500)


def _normalize_offline_recording_size(source_width: int, source_height: int) -> Tuple[int, int]:
    """Cap offline avatar export size while preserving aspect ratio and even dimensions."""
    width = max(2, int(source_width or 512))
    height = max(2, int(source_height or 512))
    max_side = _safe_int(os.getenv('OFFLINE_AVATAR_MAX_RENDER_SIDE', '1280'), 1280)
    max_side = max(256, min(1920, max_side))

    largest_side = max(width, height)
    if largest_side > max_side:
        scale = max_side / float(largest_side)
        width = max(2, int(round(width * scale)))
        height = max(2, int(round(height * scale)))

    width -= width & 1
    height -= height & 1
    return max(2, width), max(2, height)


async def _generate_offline_video(text: str, voice_config: Dict[str, Any], avatar_config: Dict[str, Any], session_id: str) -> Optional[str]:
    """
    离线生成数字人视频
    
    参数:
        text: 要合成的文本
        voice_config: 音色配置
        avatar_config: 形象配置
        session_id: 会话ID
        
    返回:
        生成的视频文件路径，失败返回 None
    """
    import tempfile
    import asyncio
    import threading
    import numpy as np
    from tts_adapter import Qwen3TTSAdapter
    
    try:
        logger.info(f"Starting offline video generation for session {session_id}")
        
        # 1. 使用当前 Qwen3-TTS 适配器生成 WAV 音频
        logger.info(f"Step 1: Generating audio with TTS")
        voice_manager = _get_voice_config_manager()
        tts_adapter = Qwen3TTSAdapter(voice_config_manager=voice_manager)
        audio_frames = []
        async for frame in tts_adapter.generate_speech(text, voice_config['voice_id']):
            if frame is not None and len(frame) > 0:
                audio_frames.append(frame)

        if not audio_frames:
            logger.error("Failed to generate audio frames from TTS")
            return None

        audio_data = np.concatenate(audio_frames)
        audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_int16.tobytes())

        audio_data = wav_buffer.getvalue()
        if not audio_data:
            logger.error("Failed to generate audio from TTS")
            return None
        
        # 保存音频到临时文件
        temp_audio_path = os.path.join(tempfile.gettempdir(), f"audio_{session_id}.wav")
        with open(temp_audio_path, 'wb') as f:
            f.write(audio_data)
        logger.info(f"Audio saved to {temp_audio_path}, size: {len(audio_data)} bytes")
        
        # 2. 使用现有的数字人生成逻辑
        logger.info(f"Step 2: Generating video with ditto-talkinghead")
        
        # 获取形象图片路径
        avatar_image_path = avatar_config.get('image_path', opt.ditto_source_path)
        avatar_image_path = _resolve_livetalking_file_path(avatar_image_path)
        if not os.path.exists(avatar_image_path):
            logger.warning(f"Avatar image not found: {avatar_image_path}, using default")
            avatar_image_path = opt.ditto_source_path
        
        logger.info(f"Using avatar image: {avatar_image_path}")
        
        qwen_config = voice_config.get('qwen_config', {})

        # 直接复用主服务启动时的完整 opt，避免遗漏 DittoReal/ASR 依赖字段。
        temp_opt = argparse.Namespace(**vars(opt).copy())
        temp_opt.sessionid = session_id
        temp_opt.ditto_source_path = avatar_image_path
        temp_opt.customopt = []
        temp_opt.QWEN_INSTRUCTIONS = qwen_config.get('instructions', opt.QWEN_INSTRUCTIONS)
        temp_opt.QWEN_OPTIMIZE_INSTRUCTIONS = qwen_config.get('optimize_instructions', opt.QWEN_OPTIMIZE_INSTRUCTIONS)
        temp_opt.REF_FILE = qwen_config.get('voice', 'Cherry')
        temp_opt.REF_TEXT = None
        
        # 加载模型和头像
        from dittoreal import load_model, load_avatar, DittoReal
        
        logger.info("Loading ditto model and avatar...")
        model = load_model(temp_opt)
        avatar = load_avatar(temp_opt)
        
        # 创建 DittoReal 实例
        logger.info("Creating DittoReal instance...")
        nerfreal = DittoReal(temp_opt, model, avatar)
        
        # 离线导出不直接沿用超大源图尺寸。大图会显著拖慢 Ditto/FFmpeg，
        # 进而导致固定等待时间内只录出前半段语音。
        source_image = avatar.get("source_img")
        source_height, source_width = 512, 512
        if isinstance(source_image, np.ndarray) and source_image.ndim >= 2:
            source_height, source_width = source_image.shape[:2]

        nerfreal.width, nerfreal.height = _normalize_offline_recording_size(source_width, source_height)
        logger.info(
            "Offline recording resolution set to %sx%s (source=%sx%s)",
            nerfreal.width,
            nerfreal.height,
            source_width,
            source_height,
        )
        
        # 开始录制
        logger.info("Starting recording...")
        nerfreal.start_recording()
        
        # 读取音频文件
        with open(temp_audio_path, 'rb') as f:
            audio_file_bytes = f.read()
        
        logger.info(f"Read audio file: {len(audio_file_bytes)} bytes")
        
        # 使用 put_audio_file 将音频数据送入处理队列
        logger.info("Feeding audio data into processing queue...")
        nerfreal.put_audio_file(audio_file_bytes, {})
        
        # 计算音频时长（用于等待处理完成）
        import soundfile as sf
        from io import BytesIO
        audio_stream, sample_rate = sf.read(BytesIO(audio_file_bytes), dtype='float32')
        if len(audio_stream.shape) > 1:
            audio_stream = audio_stream.mean(axis=1)
        audio_duration = len(audio_stream) / sample_rate
        logger.info(f"Audio duration: {audio_duration:.2f} seconds")
        audio_frame_count = max(1, int(len(audio_stream) // max(1, nerfreal.chunk)))
        warmup_audio_frames = max(0, int(getattr(nerfreal.asr, 'stride_right_size', 0)))
        target_audio_frames = audio_frame_count + warmup_audio_frames
        target_audio_samples = target_audio_frames * nerfreal.chunk
        target_video_frames = max(1, (target_audio_frames + 1) // 2)
        frames_per_asr_step = max(1, int(getattr(nerfreal.asr, 'batch_size', 1)) * 2)
        logger.info(
            "Offline Ditto targets: audio_frames=%s video_frames=%s audio_samples=%s frames_per_asr_step=%s",
            target_audio_frames,
            target_video_frames,
            target_audio_samples,
            frames_per_asr_step,
        )
        
        # 创建退出事件
        quit_event = threading.Event()
        infer_quit_event = threading.Event()
        
        # 启动推理线程（处理音频 -> 视频帧）
        logger.info("Starting inference thread...")
        infer_thread = threading.Thread(
            target=nerfreal._inference_loop,
            args=(infer_quit_event, False, target_audio_frames),
            daemon=True,
            name="offline_ditto_infer"
        )
        infer_thread.start()

        # 启动帧处理线程（消费推理结果并写入录制管线）。
        logger.info("Starting frame processing thread...")
        process_quit_event = threading.Event()
        process_thread = threading.Thread(
            target=nerfreal.process_frames,
            args=(process_quit_event,),
            daemon=True,
            name="offline_ditto_process"
        )
        process_thread.start()
        
        # 在后台线程中驱动 ASR run_step（从队列取音频帧并处理）
        def asr_driver():
            try:
                logger.info("Starting ASR driver thread...")
                total_steps = max(
                    1,
                    ((audio_frame_count + warmup_audio_frames + frames_per_asr_step - 1) // frames_per_asr_step) + 2,
                )
                for i in range(total_steps):
                    if quit_event.is_set():
                        break
                    nerfreal.asr.run_step()
                    time.sleep(0.005)
                logger.info(
                    "ASR driver thread completed: steps=%s, audio_frames=%s, frames_per_step=%s",
                    total_steps,
                    audio_frame_count,
                    frames_per_asr_step,
                )
            except Exception as e:
                logger.exception(f"Error in ASR driver thread: {e}")
        
        asr_thread = threading.Thread(target=asr_driver, daemon=True, name="offline_asr_driver")
        asr_thread.start()
        
        asr_timeout = max(15.0, audio_duration + 8.0)
        logger.info(
            "Waiting for ASR driver before Ditto tail flush: timeout=%.2fs, target_video_frames=%s, target_audio_frames=%s",
            asr_timeout,
            target_video_frames,
            target_audio_frames,
        )
        asr_deadline = time.time() + asr_timeout
        while asr_thread.is_alive() and time.time() < asr_deadline:
            await asyncio.sleep(0.05)

        quit_event.set()
        if asr_thread.is_alive():
            logger.warning("ASR driver timed out, forcing offline render finalization")
        asr_thread.join(timeout=3)

        inference_consume_timeout = max(60.0, audio_duration * 20.0)
        inference_consume_deadline = time.time() + inference_consume_timeout
        last_consume_progress_log = 0.0
        while time.time() < inference_consume_deadline:
            consumed_audio_frames = int(getattr(nerfreal, 'ditto_audio_frames_consumed', 0))
            if consumed_audio_frames >= target_audio_frames:
                logger.info(
                    "Ditto consumed target ASR frames: audio_frames=%s/%s",
                    consumed_audio_frames,
                    target_audio_frames,
                )
                break

            if not infer_thread.is_alive():
                logger.warning(
                    "Ditto inference thread stopped before consuming target ASR frames: audio_frames=%s/%s",
                    consumed_audio_frames,
                    target_audio_frames,
                )
                break

            now = time.time()
            if now - last_consume_progress_log >= 5.0:
                try:
                    asr_queue_size = nerfreal.asr.output_queue.qsize()
                except Exception:
                    asr_queue_size = -1
                logger.info(
                    "Waiting for Ditto to consume ASR frames: audio_frames=%s/%s, asr_q=%s",
                    consumed_audio_frames,
                    target_audio_frames,
                    asr_queue_size,
                )
                last_consume_progress_log = now

            await asyncio.sleep(0.1)

        final_consumed_audio_frames = int(getattr(nerfreal, 'ditto_audio_frames_consumed', 0))
        if final_consumed_audio_frames < target_audio_frames:
            logger.warning(
                "Proceeding to Ditto tail flush before full ASR consumption: audio_frames=%s/%s",
                final_consumed_audio_frames,
                target_audio_frames,
            )

        # ASR 喂完后再通知 Ditto 推理线程退出，这样 _inference_loop 会补零 flush 尾帧，
        # 避免最后几个字还没生成视频就被 stop_recording 截断。
        logger.info("Flushing Ditto inference tail...")
        infer_quit_event.set()

        render_timeout = max(60.0, audio_duration * 20.0)
        render_deadline = time.time() + render_timeout
        last_progress_log = 0.0
        reached_target = False

        while time.time() < render_deadline:
            recorded_video_frames = int(getattr(nerfreal, 'recorded_video_frames', 0))
            recorded_audio_samples = int(getattr(nerfreal, 'recorded_audio_samples', 0))

            target_video_tolerance = 1
            target_audio_sample_tolerance = nerfreal.chunk * 2
            if (
                recorded_video_frames + target_video_tolerance >= target_video_frames
                and recorded_audio_samples + target_audio_sample_tolerance >= target_audio_samples
            ):
                reached_target = True
                logger.info(
                    "Offline recording reached target: video=%s/%s, audio_samples=%s/%s",
                    recorded_video_frames,
                    target_video_frames,
                    recorded_audio_samples,
                    target_audio_samples,
                )
                break

            queues_empty = nerfreal.res_frame_queue.empty() and nerfreal.sdk_frame_queue.empty()
            if not infer_thread.is_alive() and queues_empty:
                logger.warning(
                    "Offline render queues drained before target: video=%s/%s, audio_samples=%s/%s",
                    recorded_video_frames,
                    target_video_frames,
                    recorded_audio_samples,
                    target_audio_samples,
                )
                break

            now = time.time()
            if now - last_progress_log >= 5.0:
                logger.info(
                    "Offline render progress: video=%s/%s, audio=%.2fs/%.2fs, res_q=%s, sdk_q=%s",
                    recorded_video_frames,
                    target_video_frames,
                    recorded_audio_samples / 16000.0,
                    target_audio_samples / 16000.0,
                    nerfreal.res_frame_queue.qsize(),
                    nerfreal.sdk_frame_queue.qsize(),
                )
                last_progress_log = now

            await asyncio.sleep(0.2)

        if not reached_target:
            logger.warning(
                "Offline recording finalized without full target: video=%s/%s, audio_samples=%s/%s",
                int(getattr(nerfreal, 'recorded_video_frames', 0)),
                target_video_frames,
                int(getattr(nerfreal, 'recorded_audio_samples', 0)),
                target_audio_samples,
            )

        infer_thread.join(timeout=10)

        # 给 process_frames 一点时间把剩余渲染结果写入录制管线。
        drain_deadline = time.time() + 5.0
        while time.time() < drain_deadline:
            if nerfreal.res_frame_queue.empty() and nerfreal.sdk_frame_queue.empty():
                break
            await asyncio.sleep(0.05)
        
        process_quit_event.set()
        process_thread.join(timeout=10)
        
        # 停止录制
        logger.info("Stopping recording...")
        nerfreal.stop_recording()
        
        # 检查生成的文件
        video_temp_path = f"temp{session_id}.mp4"
        audio_temp_path = f"temp{session_id}.aac"
        output_video_path = os.path.join(tempfile.gettempdir(), f"avatar_{session_id}.mp4")
        
        logger.info(f"Checking temporary files: video={video_temp_path}, audio={audio_temp_path}")
        logger.info(f"Video exists: {os.path.exists(video_temp_path)}, Audio exists: {os.path.exists(audio_temp_path)}")
        
        if os.path.exists(video_temp_path):
            video_size = os.path.getsize(video_temp_path)
            logger.info(f"Video file size: {video_size} bytes")
        if os.path.exists(audio_temp_path):
            audio_size = os.path.getsize(audio_temp_path)
            logger.info(f"Audio file size: {audio_size} bytes")
        
        # 使用 ffmpeg 合成视频和音频
        if os.path.exists(video_temp_path) and os.path.exists(audio_temp_path):
            logger.info("Merging video and audio with ffmpeg...")
            merge_command = [
                'ffmpeg', '-nostdin', '-y',
                '-i', video_temp_path,
                '-i', audio_temp_path,
                '-c:v', 'copy',
                '-c:a', 'copy',
                output_video_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *merge_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"ffmpeg merge failed: {stderr.decode()}")
                return None
            
            # 清理临时文件
            try:
                os.remove(video_temp_path)
                os.remove(audio_temp_path)
                os.remove(temp_audio_path)
                logger.info("Cleaned up temporary files")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary files: {e}")
            
            logger.info(f"Video generated successfully: {output_video_path}")
            return output_video_path
        else:
            logger.error(f"Temporary video files not found: video_exists={os.path.exists(video_temp_path)}, audio_exists={os.path.exists(audio_temp_path)}")
            # 列出当前目录的文件以帮助调试
            import glob
            temp_files = glob.glob(f"temp{session_id}*")
            logger.error(f"Found temp files matching pattern: {temp_files}")
            all_temp_files = glob.glob("temp*")
            logger.error(f"All temp files in directory: {all_temp_files}")
            return None
    
    except Exception as e:
        logger.exception(f"Error in _generate_offline_video: {e}")
        return None


async def _call_tts_api(tts_params: Dict[str, Any]) -> Optional[bytes]:
    """
    调用 TTS API 生成音频
    
    参数:
        tts_params: TTS 参数
        
    返回:
        音频数据（WAV 格式），失败返回 None
    """
    try:
        import aiohttp
        
        # 使用 Qwen3-TTS API
        api_key = tts_params.get('api_key', opt.QWEN_API_KEY)
        model = tts_params.get('model', opt.QWEN_MODEL)
        base_url = tts_params.get('base_url', opt.QWEN_BASE_URL)
        
        url = f"{base_url}/audio/speech"
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': model,
            'input': tts_params.get('text', ''),
            'voice': tts_params.get('voice', 'Cherry'),
            'response_format': 'wav'
        }
        
        # 添加可选参数
        if 'instructions' in tts_params:
            payload['instructions'] = tts_params['instructions']
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    audio_data = await response.read()
                    logger.info(f"TTS API returned {len(audio_data)} bytes")
                    return audio_data
                else:
                    error_text = await response.text()
                    logger.error(f"TTS API error: {response.status} - {error_text}")
                    return None
    
    except Exception as e:
        logger.exception(f"Error calling TTS API: {e}")
        return None


###########################################################################################
