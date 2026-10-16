###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  作者信息：LiveTalking@lipku（原仓库注释保留同等含义）
#  许可证：Apache License 2.0（本文件受该许可证约束）
#  许可证全文： http://www.apache.org/licenses/LICENSE-2.0
#
#  说明：本文件是 WebRTC 主服务入口，负责会话编排、ASR/TTS/LLM 数据流与状态管理。
###############################################################################

# Web 服务主入口
import json
import importlib
#import gevent
#from gevent import pywsgi
#from geventwebsocket.handler import WebSocketHandler
import re
from difflib import SequenceMatcher
import numpy as np
from threading import Event, Lock
#import multiprocessing
import torch.multiprocessing as mp

from aiohttp import web
import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceCandidate
from aiortc.rtcrtpsender import RTCRtpSender
try:
    from av.audio.resampler import AudioResampler
except Exception:
    AudioResampler = None
from webrtc import HumanPlayer
from basereal import BaseReal
from custom_api_handlers import call_emollm_api, emollm_response
from asr_backends import build_asr_backend
from app_config import build_arg_parser
from media_utils import _sanitize_filename_fragment, _get_cv2_module
from turn_config import configure_turn_runtime, resolve_turn_urls, build_ice_servers, rtc_config
from face_emotion import (
    configure_face_emotion_runtime,
    face_emotion_cache,
    face_emotion_cache_lock,
    _is_deepface_enabled,
    _get_deepface_api_url,
    _get_deepface_timeout,
    _get_deepface_analyze_every_n,
    _get_deepface_cache_max_age_ms,
    call_deepface_api_with_status,
    _analyze_face_emotion_async,
    _get_latest_face_emotion,
)
from voice_api import (
    configure_voice_api_runtime,
    init_voice_services,
    get_voices,
    get_avatars,
    delete_avatar,
    upload_audio,
    upload_avatar,
    clone_voice,
    generate_speech,
    generate_video,
)
from lightrag_client import (
    configure_lightrag_runtime,
    get_document_status_counts,
    get_documents_paginated,
    get_graph,
    get_graph_labels,
    get_pipeline_status,
    retrieve_lightrag_context,
    scan_lightrag_documents,
    upload_lightrag_document,
)

import argparse
import random
import asyncio
import time
import io
import wave
import os
import tempfile
import base64
import urllib.request
import urllib.error
from typing import Any, Callable, Dict, List, Set, Optional, Tuple
from logger import logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# 会话容器映射：sessionid -> BaseReal 实例。
nerfreals:Dict[int, BaseReal] = {} # sessionid:BaseReal

# SSE 订阅与聊天流状态。
chat_subscribers: Dict[int, Set[asyncio.Queue]] = {}
chat_stream_states: Dict[str, Dict[str, Any]] = {}
chat_stream_states_lock = Lock()

# WebRTC 上行媒体状态与后台任务集合。
webrtc_media_states: Dict[int, Dict[str, Any]] = {}
webrtc_media_tasks: Dict[int, Set[asyncio.Task]] = {}
webrtc_media_lock = Lock()

# WebRTC ASR 运行时（分段录音缓存、partial 状态等）。
webrtc_asr_runtime: Dict[int, Dict[str, Any]] = {}
WEBRTC_ASR_PARTIAL_INTERVAL_S = 1.0
WEBRTC_ASR_MIN_PCM_BYTES = 6400
WEBRTC_ASR_SPEECH_LEVEL = 220.0
WEBRTC_ASR_MIN_PARTIAL_SPEECH_FRAMES = 4
WEBRTC_ASR_MIN_FINAL_SPEECH_FRAMES = 6
WEBRTC_ASR_MIN_FINAL_PEAK_LEVEL = 260.0
WEBRTC_ASR_ECHO_GUARD_MS = 4500
WEBRTC_ASR_ECHO_SIMILARITY = 0.88
CHAT_STREAM_VOICE_START_TIMEOUT_S = 6.0
WEBRTC_CONNECTING_TIMEOUT_S = 90.0
opt = None
model = None
avatar = None
asr_backend = None
webrtc_final_asr_backend = None
webrtc_final_asr_backend_name = 'none'
webrtc_final_cloud_verify_backend = None
webrtc_final_cloud_verify_backend_name = 'none'
chat_record_dir = ''
llm_handler: Callable[..., str] = emollm_response
recent_assistant_utterances: Dict[int, Dict[str, Any]] = {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_compare_text(text: str) -> str:
    # 归一化文本用于“回声抑制”相似度比较：去掉空白和标点，保留有效内容。
    raw = str(text or '').strip().lower()
    if not raw:
        return ''
    return re.sub(r'[\s，。！？、,.!?;；:：“”"\'\-（）()\[\]{}【】]+', '', raw)


def _remember_assistant_utterance(sessionid: int, text: str) -> None:
    normalized = str(text or '').strip()
    if not normalized:
        return

    with webrtc_media_lock:
        recent_assistant_utterances[sessionid] = {
            'text': normalized,
            'ts_ms': int(time.time() * 1000),
        }


def _is_probable_tts_echo(sessionid: int, transcript: str) -> bool:
    normalized_transcript = _normalize_compare_text(transcript)
    if len(normalized_transcript) < 2:
        return False

    guard_ms = max(
        0,
        _safe_int(
            getattr(opt, 'WEBRTC_ASR_ECHO_GUARD_MS', WEBRTC_ASR_ECHO_GUARD_MS),
            WEBRTC_ASR_ECHO_GUARD_MS,
        ),
    )
    similarity_threshold = _safe_float(
        getattr(opt, 'WEBRTC_ASR_ECHO_SIMILARITY', WEBRTC_ASR_ECHO_SIMILARITY),
        WEBRTC_ASR_ECHO_SIMILARITY,
    )
    similarity_threshold = max(0.5, min(0.99, similarity_threshold))

    now_ms = int(time.time() * 1000)
    with webrtc_media_lock:
        latest = recent_assistant_utterances.get(sessionid)

    if not latest:
        return False

    latest_text = str(latest.get('text', '') or '').strip()
    latest_ts_ms = _safe_int(latest.get('ts_ms', 0), 0)
    if not latest_text or latest_ts_ms <= 0:
        return False
    if guard_ms > 0 and now_ms - latest_ts_ms > guard_ms:
        return False

    normalized_latest = _normalize_compare_text(latest_text)
    if len(normalized_latest) < 2:
        return False

    if normalized_transcript in normalized_latest or normalized_latest in normalized_transcript:
        return True

    similarity = SequenceMatcher(None, normalized_transcript, normalized_latest).ratio()
    return similarity >= similarity_threshold


def _is_realtime_free_talk_mode(mode: str) -> bool:
    value = str(mode or '').strip().lower()
    if not value:
        return False
    return ('realtime' in value) or ('free' in value)


def _load_custom_callable(handler_path: str, backend_name: str) -> Callable[..., Any]:
    if not handler_path or ':' not in handler_path:
        raise ValueError(
            f'{backend_name} custom handler must be in module:function format'
        )

    module_name, func_name = handler_path.split(':', 1)
    module = importlib.import_module(module_name)
    func = getattr(module, func_name, None)
    if not callable(func):
        raise ValueError(f'{backend_name} custom handler is not callable: {handler_path}')
    return func


def _resolve_llm_handler() -> Callable[..., str]:
    backend = str(getattr(opt, 'llm_backend', 'custom') or 'custom').strip().lower()
    if backend == 'custom':
        custom_handler = str(getattr(opt, 'LLM_CUSTOM_HANDLER', '') or '').strip()
        handler = _load_custom_callable(custom_handler or 'custom_api_handlers:emollm_response', 'llm')
        logger.info('LLM backend: custom (%s)', custom_handler)
        return handler

    raise ValueError(f'Unsupported llm_backend: {backend}; only custom EmoLLM is supported')


def _asr_result_to_payload(result: Any) -> Dict[str, Any]:
    if result is None:
        return {}

    if isinstance(result, dict):
        return dict(result)

    to_dict_fn = getattr(result, 'to_dict', None)
    if callable(to_dict_fn):
        data = to_dict_fn()
        if isinstance(data, dict):
            return dict(data)

    payload: Dict[str, Any] = {
        'transcript': str(getattr(result, 'transcript', '') or '').strip(),
        'source': str(getattr(result, 'source', '') or '').strip(),
    }
    request_id = str(getattr(result, 'request_id', '') or '').strip()
    if request_id:
        payload['request_id'] = request_id

    extra = getattr(result, 'extra', None)
    if isinstance(extra, dict):
        payload.update(extra)
    return payload


def _json_safe_value(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        return str(value)


def _extract_emotion_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    result: Dict[str, Any] = {}
    emotion_label = str(payload.get('emotion_label', '') or '').strip()
    if emotion_label:
        result['emotion_label'] = emotion_label

    raw_score = payload.get('emotion_score', None)
    if raw_score is not None and str(raw_score).strip() != '':
        try:
            result['emotion_score'] = float(raw_score)
        except (TypeError, ValueError):
            pass

    if 'emotion_extra' in payload and payload.get('emotion_extra') is not None:
        result['emotion_extra'] = _json_safe_value(payload.get('emotion_extra'))

    return result


def _extract_cloud_verify_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    result: Dict[str, Any] = {}
    for key, value in payload.items():
        key_str = str(key or '').strip()
        if not key_str.startswith('cloud_verify_'):
            continue
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        result[key_str] = _json_safe_value(value)
    return result


def _build_llm_user_text_with_emotion(
    user_text: str,
    emotion_label: str = '',
    emotion_score: Optional[float] = None,
    emotion_extra: Any = None,
) -> str:
    text = str(user_text or '').strip()
    if not text:
        return ''

    label = str(emotion_label or '').strip()
    has_score = emotion_score is not None
    has_extra = emotion_extra is not None
    if not label and not has_score and not has_extra:
        return text

    parts: List[str] = []
    if label:
        parts.append(f'label={label}')
    if has_score:
        try:
            parts.append(f'score={float(emotion_score):.4f}')
        except (TypeError, ValueError):
            pass
    if has_extra:
        parts.append(f'extra={json.dumps(_json_safe_value(emotion_extra), ensure_ascii=False)}')

    emotion_line = '；'.join([p for p in parts if p])
    if not emotion_line:
        return text
    return f'【语音情感】{emotion_line}\n【用户原话】{text}'



def _build_llm_user_text_with_multimodal_emotions(
    user_text: str,
    audio_emotion: str = '',
    face_emotion: str = ''
) -> str:
    """
    构建包含音频和人脸情绪的用户消息（多模态情绪融合）
    
    参数:
        user_text: 用户原始文本
        audio_emotion: 音频情绪标签（来自 ASR）
        face_emotion: 人脸情绪标签（来自 DeepFace）
        
    返回:
        str: 包含情绪信息的用户消息
        
    示例:
        输入: user_text="你好", audio_emotion="高兴", face_emotion="微笑"
        输出: "【多模态情绪】语音情绪=高兴；面部表情=微笑\n【用户原话】你好"
    """
    text = str(user_text or '').strip()
    if not text:
        return ''
    
    audio_emo = str(audio_emotion or '').strip()
    face_emo = str(face_emotion or '').strip()
    
    # 如果两种情绪都没有，直接返回原文
    if not audio_emo and not face_emo:
        return text
    
    # 构建情绪信息
    emotion_parts: List[str] = []
    if audio_emo:
        emotion_parts.append(f'语音情绪={audio_emo}')
    if face_emo:
        emotion_parts.append(f'面部表情={face_emo}')
    
    emotion_line = '；'.join(emotion_parts)
    if not emotion_line:
        return text
    
    return f'【多模态情绪】{emotion_line}\n【用户原话】{text}'


def _build_chat_rag_query(
    user_text: str,
    *,
    audio_emotion: str = '',
    face_emotion: str = '',
) -> str:
    text = str(user_text or '').strip()
    parts = [
        '请检索情感陪护虚拟数字人系统中与用户对话相关的知识，重点关注心理陪伴、共情回复、风险识别和干预边界。',
    ]
    if audio_emotion:
        parts.append(f'语音情绪：{audio_emotion}')
    if face_emotion:
        parts.append(f'面部情绪：{face_emotion}')
    if text:
        parts.append(f'用户原话：{text}')
    return '\n'.join(parts)


def _resolve_webrtc_final_asr_mode() -> str:
    return str(getattr(opt, 'WEBRTC_FINAL_ASR_BACKEND', 'same') or 'same').strip().lower()


def _resolve_webrtc_final_cloud_verify_enabled() -> bool:
    return _safe_int(getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_ENABLE', 0), 0) == 1


def _resolve_webrtc_final_cloud_verify_mode() -> str:
    return str(getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_BACKEND', 'funasr') or 'funasr').strip().lower()


def _is_webrtc_final_http_backend() -> bool:
    return _resolve_webrtc_final_asr_mode() == 'http'


def _is_webrtc_final_cloud_verify_http_backend() -> bool:
    return _resolve_webrtc_final_cloud_verify_mode() == 'http'


def _resolve_active_webrtc_asr_backend(backend_role: str) -> Tuple[Any, str]:
    if backend_role == 'final':
        final_mode = _resolve_webrtc_final_asr_mode()
        if final_mode == 'same':
            return asr_backend, str(getattr(asr_backend, 'name', 'none') or 'none')
        if final_mode == 'http':
            return None, 'http_final'
        return webrtc_final_asr_backend, str(webrtc_final_asr_backend_name or final_mode)
    return asr_backend, str(getattr(asr_backend, 'name', 'none') or 'none')


def _resolve_active_webrtc_cloud_verify_backend() -> Tuple[Any, str]:
    verify_mode = _resolve_webrtc_final_cloud_verify_mode()
    if verify_mode == 'same':
        return asr_backend, str(getattr(asr_backend, 'name', 'none') or 'none')
    if verify_mode == 'http':
        return None, 'http_cloud_verify'
    return webrtc_final_cloud_verify_backend, str(webrtc_final_cloud_verify_backend_name or verify_mode)


def _transcribe_with_http_asr_backend(
    *,
    audio_bytes: bytes,
    filename: str,
    hint_text: str,
    sessionid: int,
    mode: str,
    url: str,
    auth_token: str,
    timeout_s: float,
    backend_role: str,
) -> Dict[str, Any]:
    target_url = str(url or '').strip()
    if not target_url:
        raise RuntimeError(f'{backend_role} http asr url is empty')

    call_started = time.perf_counter()
    timeout_seconds = max(1.0, _safe_float(timeout_s, 15.0))
    audio_size_bytes = int(len(audio_bytes or b''))
    request_meta = {
        'backend_role': str(backend_role or ''),
        'url': target_url,
        'sessionid': int(sessionid),
        'mode': str(mode or 'chat'),
        'filename': str(filename or 'webrtc_stream.wav'),
        'audio_size_bytes': audio_size_bytes,
        'audio_mime_type': 'audio/wav',
        'browser_transcript_hint': str(hint_text or ''),
    }

    req_payload = {
        'sessionid': int(sessionid),
        'mode': str(mode or 'chat'),
        'filename': str(filename or 'webrtc_stream.wav'),
        'audio_mime_type': 'audio/wav',
        'browser_transcript_hint': str(hint_text or ''),
        'audio_base64': base64.b64encode(audio_bytes or b'').decode('ascii'),
    }

    req_data = json.dumps(req_payload, ensure_ascii=False).encode('utf-8')
    req_headers = {
        'Content-Type': 'application/json',
    }
    if auth_token:
        req_headers['Authorization'] = f'Bearer {auth_token}'

    request_obj = urllib.request.Request(
        url=target_url,
        data=req_data,
        headers=req_headers,
        method='POST',
    )

    try:
        with urllib.request.urlopen(request_obj, timeout=timeout_seconds) as response:
            status_code = int(getattr(response, 'status', 200) or 200)
            raw_body = response.read()
    except urllib.error.HTTPError as exc:
        err_body = ''
        try:
            err_body = exc.read().decode('utf-8', errors='ignore')
        except Exception:
            err_body = ''

        _append_chat_record_api_call(
            sessionid=sessionid,
            api_name=f'asr_http_backend.{backend_role}',
            status='error',
            mode=mode,
            source=backend_role,
            duration_ms=int((time.perf_counter() - call_started) * 1000),
            request_payload=request_meta,
            response_payload={
                'status_code': int(getattr(exc, 'code', 0) or 0),
                'error_body': (err_body or '')[:500],
            },
            error_message=f'http_status={int(getattr(exc, "code", 0) or 0)}',
        )
        raise RuntimeError(
            f'{backend_role} http asr request failed: status={exc.code}, body={(err_body or "")[:300]}'
        )
    except urllib.error.URLError as exc:
        _append_chat_record_api_call(
            sessionid=sessionid,
            api_name=f'asr_http_backend.{backend_role}',
            status='error',
            mode=mode,
            source=backend_role,
            duration_ms=int((time.perf_counter() - call_started) * 1000),
            request_payload=request_meta,
            error_message=f'url_error={exc}',
        )
        raise RuntimeError(f'{backend_role} http asr url error: {exc}')

    if status_code >= 400:
        _append_chat_record_api_call(
            sessionid=sessionid,
            api_name=f'asr_http_backend.{backend_role}',
            status='error',
            mode=mode,
            source=backend_role,
            duration_ms=int((time.perf_counter() - call_started) * 1000),
            request_payload=request_meta,
            response_payload={'status_code': int(status_code)},
            error_message=f'http_status={int(status_code)}',
        )
        raise RuntimeError(f'{backend_role} http asr request failed: status={status_code}')

    text_body = raw_body.decode('utf-8', errors='ignore').strip()
    if not text_body:
        _append_chat_record_api_call(
            sessionid=sessionid,
            api_name=f'asr_http_backend.{backend_role}',
            status='ok',
            mode=mode,
            source=backend_role,
            duration_ms=int((time.perf_counter() - call_started) * 1000),
            request_payload=request_meta,
            response_payload={'status_code': int(status_code), 'empty_body': True},
        )
        return {}

    try:
        data = json.loads(text_body)
    except Exception as exc:
        raise RuntimeError(f'{backend_role} http asr response is not valid json: {exc}')

    if not isinstance(data, dict):
        raise RuntimeError(f'{backend_role} http asr response must be a JSON object')

    if isinstance(data.get('data'), dict):
        flattened = dict(data.get('data') or {})
        for key, value in data.items():
            if key not in flattened and key != 'data':
                flattened[key] = value
        data = flattened

    code_val = data.get('code', None)
    if code_val is not None:
        code_num = _safe_int(code_val, 0)
        if code_num != 0:
            _append_chat_record_api_call(
                sessionid=sessionid,
                api_name=f'asr_http_backend.{backend_role}',
                status='error',
                mode=mode,
                source=backend_role,
                duration_ms=int((time.perf_counter() - call_started) * 1000),
                request_payload=request_meta,
                response_payload={
                    'status_code': int(status_code),
                    'code': int(code_num),
                    'msg': str(data.get('msg', '') or ''),
                    'transcript': str(data.get('transcript', '') or ''),
                    'request_id': str(data.get('request_id', '') or ''),
                },
                error_message=f'response_code={int(code_num)}',
            )
            raise RuntimeError(
                f'{backend_role} http asr response code={code_num}, msg={str(data.get("msg", "") or "")}'
            )

    _append_chat_record_api_call(
        sessionid=sessionid,
        api_name=f'asr_http_backend.{backend_role}',
        status='ok',
        mode=mode,
        source=backend_role,
        duration_ms=int((time.perf_counter() - call_started) * 1000),
        request_payload=request_meta,
        response_payload={
            'status_code': int(status_code),
            'code': _safe_int(data.get('code', 0), 0) if data.get('code', None) is not None else None,
            'source': str(data.get('source', '') or ''),
            'request_id': str(data.get('request_id', '') or ''),
            'transcript': str(data.get('transcript', '') or ''),
            'keys': sorted([str(k) for k in data.keys()]),
        },
    )

    return data


def _transcribe_with_webrtc_final_http_backend(
    *,
    audio_bytes: bytes,
    filename: str,
    hint_text: str,
    sessionid: int,
    mode: str,
) -> Dict[str, Any]:
    return _transcribe_with_http_asr_backend(
        audio_bytes=audio_bytes,
        filename=filename,
        hint_text=hint_text,
        sessionid=sessionid,
        mode=mode,
        url=str(getattr(opt, 'WEBRTC_FINAL_ASR_HTTP_URL', '') or '').strip(),
        auth_token=str(getattr(opt, 'WEBRTC_FINAL_ASR_HTTP_AUTH_TOKEN', '') or '').strip(),
        timeout_s=_safe_float(getattr(opt, 'WEBRTC_FINAL_ASR_HTTP_TIMEOUT_S', 15.0), 15.0),
        backend_role='final',
    )


def _transcribe_with_webrtc_cloud_verify_http_backend(
    *,
    audio_bytes: bytes,
    filename: str,
    hint_text: str,
    sessionid: int,
    mode: str,
) -> Dict[str, Any]:
    return _transcribe_with_http_asr_backend(
        audio_bytes=audio_bytes,
        filename=filename,
        hint_text=hint_text,
        sessionid=sessionid,
        mode=mode,
        url=str(getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_HTTP_URL', '') or '').strip(),
        auth_token=str(getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_HTTP_AUTH_TOKEN', '') or '').strip(),
        timeout_s=_safe_float(getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_HTTP_TIMEOUT_S', 12.0), 12.0),
        backend_role='cloud_verify',
    )


def _estimate_audio_duration_seconds(audio_bytes: bytes) -> float:
    if not audio_bytes:
        return 0.0
    # 仅用于近似展示：按 16kHz/16bit/mono 的 PCM 基准估算时长。
    return float(len(audio_bytes)) / 32000.0








def _resolve_chat_record_dir() -> str:
    configured_dir = str(getattr(opt, 'CHAT_RECORD_DIR', '') or '').strip()
    if not configured_dir:
        return ''

    if os.path.isabs(configured_dir):
        resolved = configured_dir
    else:
        resolved = os.path.abspath(os.path.join(os.getcwd(), configured_dir))

    os.makedirs(resolved, exist_ok=True)
    return resolved


def _normalize_chat_mode(mode: str) -> str:
    value = str(mode or 'chat').strip().lower()
    if not value:
        value = 'chat'
    return value


def _is_realtime_like_mode(mode: str) -> bool:
    normalized = _normalize_chat_mode(mode)
    return ('realtime' in normalized) or normalized.startswith('free_')


def _resolve_chat_record_policy() -> str:
    value = str(getattr(opt, 'CHAT_RECORD_POLICY', 'auto') or 'auto').strip().lower()
    if value not in {'auto', 'full', 'text-only', 'off'}:
        value = 'auto'
    return value


def _chat_record_enabled() -> bool:
    if not bool(getattr(opt, 'CHAT_RECORD_ENABLE', False)):
        return False
    if _resolve_chat_record_policy() == 'off':
        return False
    return bool(chat_record_dir)


chat_record_lock = Lock()
chat_record_runtime: Dict[int, Dict[str, Any]] = {}


def _resolve_chat_record_targets(mode: str, source: str = '') -> Dict[str, bool]:
    policy = _resolve_chat_record_policy()
    if policy == 'off':
        return {'text': False, 'audio': False, 'video': False}
    if policy == 'text-only':
        return {'text': True, 'audio': False, 'video': False}

    if policy == 'full':
        return {'text': True, 'audio': True, 'video': True}

    # auto 策略（默认）：
    # - 文本：所有模式都存；
    # - 音频：语音来源存；
    # - 视频：仅实时类模式存。
    source_value = str(source or '').strip().lower()
    realtime_like = _is_realtime_like_mode(mode)
    audio_like_source = source_value in {
        'voice',
        'voice_webrtc',
        'webrtc_asr',
        'free_talk',
        'asr_upload',
    }
    return {
        'text': True,
        'audio': bool(audio_like_source or realtime_like),
        'video': bool(realtime_like),
    }


def _ensure_chat_record_session(sessionid: int) -> Optional[Dict[str, Any]]:
    if not _chat_record_enabled() or sessionid <= 0:
        return None

    with chat_record_lock:
        runtime = chat_record_runtime.get(sessionid)
        if runtime is not None:
            return runtime

        ts = time.strftime('%Y%m%d-%H%M%S', time.localtime())
        session_dir = os.path.join(chat_record_dir, f'sid{sessionid}_{ts}')
        audio_dir = os.path.join(session_dir, 'audio')
        os.makedirs(audio_dir, exist_ok=True)

        events_path = os.path.join(session_dir, 'events.jsonl')
        meta_path = os.path.join(session_dir, 'session_meta.json')

        runtime = {
            'sessionid': int(sessionid),
            'created_at_ms': int(time.time() * 1000),
            'updated_at_ms': int(time.time() * 1000),
            'session_dir': session_dir,
            'audio_dir': audio_dir,
            'events_path': events_path,
            'api_calls_path': os.path.join(session_dir, 'api_calls.jsonl'),
            'event_index': 0,
            'audio_index': 0,
        }
        chat_record_runtime[sessionid] = runtime

        try:
            with open(meta_path, 'w', encoding='utf-8') as fp:
                json.dump(
                    {
                        'sessionid': int(sessionid),
                        'created_at_ms': runtime['created_at_ms'],
                        'chat_record_policy': _resolve_chat_record_policy(),
                        'chat_record_dir': session_dir,
                        'events_path': events_path,
                        'api_calls_path': runtime['api_calls_path'],
                    },
                    fp,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            logger.exception('sessionid=%d write chat record session meta failed', sessionid)
        return runtime


def _append_chat_record_event(sessionid: int, event_type: str, payload: Dict[str, Any]) -> None:
    runtime = _ensure_chat_record_session(sessionid)
    if runtime is None:
        return

    event_payload = dict(payload or {})
    event_payload.pop('event', None)
    event_payload.pop('event_index', None)

    with chat_record_lock:
        runtime = chat_record_runtime.get(sessionid)
        if runtime is None:
            return

        runtime['event_index'] = int(runtime.get('event_index', 0)) + 1
        runtime['updated_at_ms'] = int(time.time() * 1000)

        event = {
            'event_index': int(runtime['event_index']),
            'event': str(event_type),
            'ts_ms': int(time.time() * 1000),
        }
        event.update(event_payload)

        try:
            with open(runtime['events_path'], 'a', encoding='utf-8') as fp:
                fp.write(json.dumps(event, ensure_ascii=False) + '\n')
        except Exception:
            logger.exception('sessionid=%d append chat record event failed: %s', sessionid, event_type)


def _compact_record_value(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        return '<max_depth>'

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if len(value) <= 1600:
            return value
        remain = len(value) - 1600
        return f'{value[:1600]}...(truncated {remain} chars)'

    if isinstance(value, (bytes, bytearray)):
        return f'<bytes:{len(value)}>'

    if isinstance(value, dict):
        compact: Dict[str, Any] = {}
        total = len(value)
        for idx, (k, v) in enumerate(value.items()):
            if idx >= 80:
                compact['__truncated_keys__'] = max(0, total - 80)
                break
            compact[str(k)] = _compact_record_value(v, depth + 1)
        return compact

    if isinstance(value, (list, tuple, set)):
        seq = list(value)
        compact_list = [_compact_record_value(item, depth + 1) for item in seq[:80]]
        if len(seq) > 80:
            compact_list.append(f'...(truncated {len(seq) - 80} items)')
        return compact_list

    try:
        return str(value)
    except Exception:
        return '<unserializable>'


def _append_chat_record_api_call(
    *,
    sessionid: int,
    api_name: str,
    status: str,
    request_payload: Optional[Dict[str, Any]] = None,
    response_payload: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[int] = None,
    mode: str = '',
    source: str = '',
    error_message: str = '',
) -> None:
    runtime = _ensure_chat_record_session(sessionid)
    if runtime is None:
        return

    now_ms = int(time.time() * 1000)
    record: Dict[str, Any] = {
        'ts_ms': now_ms,
        'sessionid': int(sessionid),
        'api': str(api_name or ''),
        'status': str(status or 'ok'),
    }
    if mode:
        record['mode'] = _normalize_chat_mode(mode)
    if source:
        record['source'] = str(source or '')
    if duration_ms is not None:
        record['duration_ms'] = max(0, int(duration_ms))
    if request_payload is not None:
        record['request'] = _compact_record_value(request_payload)
    if response_payload is not None:
        record['response'] = _compact_record_value(response_payload)
    if error_message:
        record['error'] = _compact_record_value(str(error_message))

    _append_chat_record_event(
        sessionid,
        'api_call',
        {
            'api': record['api'],
            'status': record['status'],
            'mode': record.get('mode', ''),
            'source': record.get('source', ''),
            'duration_ms': record.get('duration_ms', 0),
            'error': str(error_message or ''),
        },
    )

    with chat_record_lock:
        runtime = chat_record_runtime.get(sessionid)
        if runtime is None:
            return

        api_calls_path = str(runtime.get('api_calls_path', '') or '')
        if not api_calls_path:
            session_dir = str(runtime.get('session_dir', '') or '')
            if not session_dir:
                return
            api_calls_path = os.path.join(session_dir, 'api_calls.jsonl')
            runtime['api_calls_path'] = api_calls_path

        runtime['updated_at_ms'] = now_ms

        try:
            with open(api_calls_path, 'a', encoding='utf-8') as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + '\n')
        except Exception:
            logger.exception('sessionid=%d append api record failed: %s', sessionid, api_name)


def _record_chat_text_if_needed(
    *,
    sessionid: int,
    role: str,
    text: str,
    mode: str,
    source: str,
) -> None:
    if not _chat_record_enabled():
        return
    targets = _resolve_chat_record_targets(mode=mode, source=source)
    if not targets.get('text'):
        return

    normalized = str(text or '').strip()
    if not normalized:
        return

    if str(role or '').strip().lower() == 'assistant':
        _remember_assistant_utterance(sessionid, normalized)

    _append_chat_record_event(
        sessionid,
        'chat_text',
        {
            'role': str(role or ''),
            'mode': _normalize_chat_mode(mode),
            'source': str(source or ''),
            'text': normalized,
            'text_length': len(normalized),
        },
    )


def _save_chat_record_pcm_wav_if_needed(
    *,
    sessionid: int,
    mode: str,
    source: str,
    pcm16_bytes: bytes,
    transcript: str,
) -> str:
    if not _chat_record_enabled():
        return ''
    targets = _resolve_chat_record_targets(mode=mode, source=source)
    if not targets.get('audio'):
        return ''
    if not pcm16_bytes:
        return ''

    runtime = _ensure_chat_record_session(sessionid)
    if runtime is None:
        return ''

    with chat_record_lock:
        runtime = chat_record_runtime.get(sessionid)
        if runtime is None:
            return ''
        runtime['audio_index'] = int(runtime.get('audio_index', 0)) + 1
        audio_index = int(runtime['audio_index'])
        audio_dir = runtime.get('audio_dir')

    if not audio_dir:
        return ''

    ts = time.strftime('%Y%m%d-%H%M%S', time.localtime())
    ms = int((time.time() % 1) * 1000)
    safe_mode = _sanitize_filename_fragment(mode or 'chat', 'chat')
    wav_name = f'sid{sessionid}_{safe_mode}_{audio_index:04d}_{ts}-{ms:03d}.wav'
    wav_path = os.path.join(audio_dir, wav_name)

    try:
        wav_bytes = _pcm16_to_wav_bytes(pcm16_bytes, sample_rate=16000, channels=1)
        with open(wav_path, 'wb') as fp:
            fp.write(wav_bytes)

        _append_chat_record_event(
            sessionid,
            'chat_audio',
            {
                'mode': _normalize_chat_mode(mode),
                'source': str(source or ''),
                'audio_path': wav_path,
                'size_bytes': len(wav_bytes),
                'duration_s': round(float(len(pcm16_bytes)) / 32000.0, 3),
                'transcript_hint': str(transcript or ''),
            },
        )
        return wav_path
    except Exception:
        logger.exception('sessionid=%d save chat record pcm wav failed', sessionid)
        return ''


def _record_chat_video_frame_if_needed(
    *,
    sessionid: int,
    mode: str,
    frame_index: int,
    frame_path: str,
    width: int,
    height: int,
) -> None:
    if not _chat_record_enabled():
        return
    targets = _resolve_chat_record_targets(mode=mode, source='camera_frame')
    if not targets.get('video'):
        return
    if not frame_path:
        return

    _append_chat_record_event(
        sessionid,
        'chat_video_frame',
        {
            'mode': _normalize_chat_mode(mode),
            'frame_index': int(frame_index),
            'frame_path': frame_path,
            'width': int(width),
            'height': int(height),
        },
    )










def _build_default_webrtc_media_state(sessionid: int) -> Dict[str, Any]:
    now_ms = int(time.time() * 1000)
    return {
        "sessionid": sessionid,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
        "audio_frame_count": 0,
        "video_frame_count": 0,
        "last_asr": None,
    }


def _ensure_webrtc_media_state(sessionid: int) -> Dict[str, Any]:
    with webrtc_media_lock:
        if sessionid not in webrtc_media_states:
            webrtc_media_states[sessionid] = _build_default_webrtc_media_state(sessionid)
        return webrtc_media_states[sessionid]


def _build_default_webrtc_asr_runtime() -> Dict[str, Any]:
    # 字段约定：
    # recording: 是否处于一次“按住说话”录音段；
    # mode: 本段会话模式（chat/free_talk 等）；
    # utterance_id: 递增段号，用于过滤过期异步任务；
    # pcm16_buffer: 当前段累积音频缓存（16k/mono/s16）；
    # partial_inflight: 是否已有 partial ASR 任务在执行，避免并发风暴；
    # last_partial_request_ms: 上次 partial 请求时间戳（限频）；
    # last_partial_transcript: 去重用，避免重复推送相同 partial 文本。
    return {
        "recording": False,
        "mode": "chat",
        "utterance_id": 0,
        "pcm16_buffer": bytearray(),
        "partial_inflight": False,
        "last_partial_request_ms": 0,
        "last_partial_transcript": "",
        "speech_frame_count": 0,
        "total_frame_count": 0,
        "max_audio_level": 0.0,
        "dropped_avatar_frames": 0,
    }


def _ensure_webrtc_asr_runtime(sessionid: int) -> Dict[str, Any]:
    with webrtc_media_lock:
        runtime = webrtc_asr_runtime.get(sessionid)
        if runtime is None:
            runtime = _build_default_webrtc_asr_runtime()
            webrtc_asr_runtime[sessionid] = runtime
        return runtime


def _pcm16_to_wav_bytes(pcm16_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    if not pcm16_bytes:
        return b""

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16_bytes)
    return buf.getvalue()


def _resample_mono_int16(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if samples.size == 0 or src_rate <= 0 or src_rate == dst_rate:
        return samples

    dst_len = max(1, int(round(samples.shape[0] * float(dst_rate) / float(src_rate))))
    src_idx = np.linspace(0, samples.shape[0] - 1, num=samples.shape[0], dtype=np.float32)
    dst_idx = np.linspace(0, samples.shape[0] - 1, num=dst_len, dtype=np.float32)
    resampled = np.interp(dst_idx, src_idx, samples.astype(np.float32))
    return np.clip(resampled, -32768, 32767).astype(np.int16)


def _create_webrtc_audio_resampler():
    if AudioResampler is None:
        return None

    try:
        return AudioResampler(format="s16", layout="mono", rate=16000)
    except Exception:
        logger.warning("pyav audio resampler init failed, fallback to numpy path")
        return None


def _resample_frame_to_mono16k_with_av(frame, frame_resampler) -> np.ndarray:
    if frame_resampler is None:
        return np.empty(0, dtype=np.int16)

    try:
        out_frames = frame_resampler.resample(frame)
    except Exception:
        logger.debug("pyav frame resample failed, fallback to numpy path", exc_info=True)
        return np.empty(0, dtype=np.int16)

    if out_frames is None:
        return np.empty(0, dtype=np.int16)

    if not isinstance(out_frames, list):
        out_frames = [out_frames]

    chunks: List[np.ndarray] = []
    for out_frame in out_frames:
        if out_frame is None:
            continue
        try:
            arr = out_frame.to_ndarray()
        except Exception:
            continue

        if arr is None or arr.size == 0:
            continue

        mono = arr.reshape(-1)
        chunk = np.clip(mono, -32768, 32767).astype(np.int16, copy=False)
        if chunk.size > 0:
            chunks.append(chunk)

    if not chunks:
        return np.empty(0, dtype=np.int16)

    if len(chunks) == 1:
        return chunks[0]
    return np.concatenate(chunks)


def _frame_to_pcm16_mono_16k(frame, frame_resampler=None) -> Tuple[bytes, float]:
    resampled = _resample_frame_to_mono16k_with_av(frame, frame_resampler)
    if resampled.size > 0:
        avg_level = float(np.mean(np.abs(resampled))) if resampled.size > 0 else 0.0
        return resampled.tobytes(), avg_level

    samples = frame.to_ndarray()
    if samples.size == 0:
        return b"", 0.0

    layout = getattr(frame, "layout", None)
    channels = getattr(layout, "channels", None)
    channel_count = 0
    if channels is not None:
        try:
            channel_count = len(channels)
        except Exception:
            channel_count = 0

    if samples.ndim == 1:
        mono = samples
    elif samples.ndim == 2:
        # ndarray 在不同 format/layout 下会有不同排列，这里尽量按声道数做稳健处理。
        if channel_count > 1 and samples.shape[0] == 1 and samples.shape[1] % channel_count == 0:
            mono = samples.reshape(-1, channel_count).mean(axis=1)
        elif channel_count > 1 and samples.shape[1] == 1 and samples.shape[0] % channel_count == 0:
            mono = samples.reshape(channel_count, -1).mean(axis=0)
        elif channel_count > 0 and samples.shape[0] == channel_count:
            mono = samples.mean(axis=0)
        elif channel_count > 0 and samples.shape[1] == channel_count:
            mono = samples.mean(axis=1)
        else:
            mono = samples.mean(axis=0) if samples.shape[0] <= samples.shape[1] else samples.mean(axis=1)
    else:
        mono = samples.reshape(-1)

    if np.issubdtype(mono.dtype, np.integer):
        mono_i16 = np.clip(mono, -32768, 32767).astype(np.int16)
    else:
        mono_f32 = mono.astype(np.float32)
        peak = float(np.max(np.abs(mono_f32))) if mono_f32.size > 0 else 0.0
        if peak <= 1.5:
            mono_i16 = (np.clip(mono_f32, -1.0, 1.0) * 32767.0).astype(np.int16)
        else:
            mono_i16 = np.clip(mono_f32, -32768.0, 32767.0).astype(np.int16)

    in_rate = _safe_int(getattr(frame, "sample_rate", 16000), 16000)
    mono_16k = _resample_mono_int16(mono_i16, in_rate, 16000)
    avg_level = float(np.mean(np.abs(mono_16k))) if mono_16k.size > 0 else 0.0
    return mono_16k.tobytes(), avg_level


def _build_webrtc_asr_state_payload(
    *,
    transcript: str,
    source: str,
    backend: str,
    mode: str,
    status: str,
    utterance_id: int,
    duration_s: float,
    request_id: str = "",
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "mode": mode,
        "backend": backend,
        "source": source,
        "status": status,
        "utterance_id": utterance_id,
        "duration_s": round(duration_s, 3),
        "transcript": transcript,
        "ts_ms": int(time.time() * 1000),
    }
    if request_id:
        payload["request_id"] = request_id
    if extra_fields:
        for key, value in extra_fields.items():
            if value is None:
                continue
            payload[key] = _json_safe_value(value)
    return payload


def _run_webrtc_final_cloud_verify(
    *,
    sessionid: int,
    wav_bytes: bytes,
    mode: str,
    hint_text: str,
    transcript: str,
    source: str,
    request_id: str,
) -> Dict[str, Any]:
    resolved_transcript = str(transcript or '').strip()
    resolved_source = str(source or '').strip() or 'webrtc_stream_asr'
    resolved_request_id = str(request_id or '').strip()
    verify_enabled = _resolve_webrtc_final_cloud_verify_enabled()
    verify_extra: Dict[str, Any] = {
        'cloud_verify_enabled': bool(verify_enabled),
    }

    result: Dict[str, Any] = {
        'transcript': resolved_transcript,
        'source': resolved_source,
        'request_id': resolved_request_id,
        'extra_payload': verify_extra,
    }

    local_normalized = _normalize_compare_text(resolved_transcript)
    local_len = len(local_normalized)
    verify_extra['cloud_verify_local_len'] = local_len

    if not verify_enabled:
        verify_extra['cloud_verify_action'] = 'disabled'
        return result

    if not wav_bytes:
        verify_extra['cloud_verify_action'] = 'skip_empty_audio'
        return result

    if local_len <= 0:
        verify_extra['cloud_verify_action'] = 'skip_empty_local'
        return result

    active_verify_backend, verify_backend_name = _resolve_active_webrtc_cloud_verify_backend()
    verify_extra['cloud_verify_backend'] = verify_backend_name

    verify_payload: Dict[str, Any] = {}
    try:
        if _is_webrtc_final_cloud_verify_http_backend():
            verify_payload = _transcribe_with_webrtc_cloud_verify_http_backend(
                audio_bytes=wav_bytes,
                filename='webrtc_stream.wav',
                hint_text=hint_text,
                sessionid=sessionid,
                mode=mode,
            )
        elif active_verify_backend is not None and hasattr(active_verify_backend, 'transcribe'):
            verify_payload = _asr_result_to_payload(
                active_verify_backend.transcribe(
                    audio_bytes=wav_bytes,
                    filename='webrtc_stream.wav',
                    hint_text=hint_text,
                    sessionid=sessionid,
                    mode=mode,
                )
            )
        else:
            verify_extra['cloud_verify_action'] = 'skip_backend_unavailable'
            return result
    except Exception as exc:
        verify_extra['cloud_verify_action'] = 'verify_error_keep_local'
        verify_extra['cloud_verify_error'] = str(exc)[:180]
        logger.warning(
            'sessionid=%d final cloud verify failed, keep local transcript: %s',
            sessionid,
            str(exc),
        )
        return result

    cloud_transcript = str(verify_payload.get('transcript', '') or '').strip()
    cloud_source = str(verify_payload.get('source', '') or '').strip() or 'cloud_verify_empty'
    cloud_request_id = str(verify_payload.get('request_id', '') or '').strip()
    cloud_normalized = _normalize_compare_text(cloud_transcript)
    cloud_len = len(cloud_normalized)
    verify_extra['cloud_verify_source'] = cloud_source
    verify_extra['cloud_verify_cloud_len'] = cloud_len

    short_text_chars = max(
        1,
        _safe_int(
            getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_SHORT_TEXT_CHARS', 8),
            8,
        ),
    )
    min_cloud_chars = max(
        1,
        _safe_int(
            getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_MIN_CLOUD_CHARS', 2),
            2,
        ),
    )
    similarity_threshold = _safe_float(
        getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_SIMILARITY', 0.56),
        0.56,
    )
    similarity_threshold = max(0.3, min(0.99, similarity_threshold))
    replace_with_cloud = _safe_int(
        getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_REPLACE_WITH_CLOUD', 1),
        1,
    ) == 1

    if cloud_len < min_cloud_chars:
        if local_len <= short_text_chars:
            verify_extra['cloud_verify_action'] = 'reject_short_cloud_empty'
            result['transcript'] = ''
            result['source'] = 'webrtc_stream_cloud_verify_rejected'
            return result
        verify_extra['cloud_verify_action'] = 'keep_local_cloud_empty'
        return result

    similarity = SequenceMatcher(None, local_normalized, cloud_normalized).ratio()
    verify_extra['cloud_verify_similarity'] = round(similarity, 4)

    if similarity >= similarity_threshold:
        if replace_with_cloud and len(cloud_transcript) > len(resolved_transcript) + 2:
            verify_extra['cloud_verify_action'] = 'replace_confirmed_longer_cloud'
            result['transcript'] = cloud_transcript
            result['source'] = f'cloud_verify_refined:{cloud_source}'
            if cloud_request_id and not resolved_request_id:
                result['request_id'] = cloud_request_id
            return result
        verify_extra['cloud_verify_action'] = 'confirmed_keep_local'
        return result

    if replace_with_cloud and cloud_len >= max(min_cloud_chars, local_len):
        verify_extra['cloud_verify_action'] = 'replace_disagree_use_cloud'
        result['transcript'] = cloud_transcript
        result['source'] = f'cloud_verify_replaced:{cloud_source}'
        if cloud_request_id and not resolved_request_id:
            result['request_id'] = cloud_request_id
        return result

    if local_len <= short_text_chars:
        verify_extra['cloud_verify_action'] = 'reject_short_disagree'
        result['transcript'] = ''
        result['source'] = 'webrtc_stream_cloud_verify_rejected'
        return result

    verify_extra['cloud_verify_action'] = 'keep_local_disagree'
    return result


def _transcribe_webrtc_pcm_bytes(
    *,
    sessionid: int,
    pcm16_bytes: bytes,
    mode: str,
    hint_text: str = "",
    backend_role: str = 'partial',
    strict_backend: bool = False,
    speech_frame_count: int = 0,
    total_frame_count: int = 0,
    max_audio_level: float = 0.0,
    dropped_avatar_frames: int = 0,
) -> Dict[str, Any]:
    duration_s = round(float(len(pcm16_bytes)) / 32000.0, 3)
    active_backend, backend_name = _resolve_active_webrtc_asr_backend(backend_role)

    speech_frames = max(0, _safe_int(speech_frame_count, 0))
    all_frames = max(0, _safe_int(total_frame_count, 0))
    peak_audio_level = max(0.0, _safe_float(max_audio_level, 0.0))
    dropped_avatar_frame_count = max(0, _safe_int(dropped_avatar_frames, 0))
    if all_frames <= 0 and pcm16_bytes:
        all_frames = max(1, int(round(float(len(pcm16_bytes)) / 640.0)))

    if backend_role == 'final':
        min_speech_frames = max(
            0,
            _safe_int(
                getattr(opt, 'WEBRTC_ASR_MIN_FINAL_SPEECH_FRAMES', WEBRTC_ASR_MIN_FINAL_SPEECH_FRAMES),
                WEBRTC_ASR_MIN_FINAL_SPEECH_FRAMES,
            ),
        )
        min_peak_level = max(
            0.0,
            _safe_float(
                getattr(opt, 'WEBRTC_ASR_MIN_FINAL_PEAK_LEVEL', WEBRTC_ASR_MIN_FINAL_PEAK_LEVEL),
                WEBRTC_ASR_MIN_FINAL_PEAK_LEVEL,
            ),
        )
    else:
        min_speech_frames = max(
            0,
            _safe_int(
                getattr(opt, 'WEBRTC_ASR_MIN_PARTIAL_SPEECH_FRAMES', WEBRTC_ASR_MIN_PARTIAL_SPEECH_FRAMES),
                WEBRTC_ASR_MIN_PARTIAL_SPEECH_FRAMES,
            ),
        )
        min_peak_level = 0.0

    transcript = ""
    source = "webrtc_stream_empty"
    request_id = ""
    backend_error = ""
    wav_bytes = b""
    extra_payload: Dict[str, Any] = {}
    silence_filtered = False

    if pcm16_bytes:
        if speech_frames < min_speech_frames:
            silence_filtered = True
        if (not silence_filtered) and min_peak_level > 0.0 and peak_audio_level < min_peak_level:
            silence_filtered = True

    if silence_filtered:
        source = "webrtc_stream_silence_filtered"
        logger.info(
            "sessionid=%d %s asr skipped by silence filter: speech_frames=%d total_frames=%d peak=%.1f dropped_avatar_frames=%d",
            sessionid,
            backend_role,
            speech_frames,
            all_frames,
            peak_audio_level,
            dropped_avatar_frame_count,
        )

    if pcm16_bytes and not silence_filtered:
        wav_bytes = _pcm16_to_wav_bytes(pcm16_bytes, sample_rate=16000, channels=1)

    if wav_bytes:
        try:
            if backend_role == 'final' and _is_webrtc_final_http_backend():
                backend_payload = _transcribe_with_webrtc_final_http_backend(
                    audio_bytes=wav_bytes,
                    filename='webrtc_stream.wav',
                    hint_text=hint_text,
                    sessionid=sessionid,
                    mode=mode,
                )
            elif active_backend is not None and hasattr(active_backend, 'transcribe'):
                backend_payload = _asr_result_to_payload(
                    active_backend.transcribe(
                        audio_bytes=wav_bytes,
                        filename='webrtc_stream.wav',
                        hint_text=hint_text,
                        sessionid=sessionid,
                        mode=mode,
                    )
                )
            else:
                raise RuntimeError(f'ASR backend is unavailable for role={backend_role}')

            transcript = str(backend_payload.get("transcript", "") or "").strip()
            source = str(backend_payload.get("source", "") or "").strip() or "webrtc_stream_asr"
            request_id = str(backend_payload.get("request_id", "") or "").strip()
            for key, value in backend_payload.items():
                if key in {"transcript", "source", "request_id", "code", "msg"}:
                    continue
                extra_payload[key] = _json_safe_value(value)

            if transcript and _is_probable_tts_echo(sessionid, transcript):
                logger.info(
                    "sessionid=%d %s asr transcript suppressed as probable tts echo: transcript=%s",
                    sessionid,
                    backend_role,
                    transcript[:120],
                )
                transcript = ""
                source = "webrtc_stream_echo_filtered"

            if backend_role == 'final':
                verify_decision = _run_webrtc_final_cloud_verify(
                    sessionid=sessionid,
                    wav_bytes=wav_bytes,
                    mode=mode,
                    hint_text=hint_text,
                    transcript=transcript,
                    source=source,
                    request_id=request_id,
                )
                transcript = str(verify_decision.get('transcript', transcript) or '').strip()
                source = str(verify_decision.get('source', source) or source).strip() or source
                verify_request_id = str(verify_decision.get('request_id', '') or '').strip()
                if verify_request_id and not request_id:
                    request_id = verify_request_id

                verify_extra_payload = verify_decision.get('extra_payload', {})
                if isinstance(verify_extra_payload, dict):
                    for key, value in verify_extra_payload.items():
                        if value is None:
                            continue
                        extra_payload[key] = _json_safe_value(value)
        except Exception:
            backend_error = 'asr_transcribe_exception'
            logger.exception("sessionid=%d webrtc stream asr transcribe exception", sessionid)
            if strict_backend:
                raise
            source = "webrtc_stream_asr_error"

    allow_hint_fallback = (
        (not strict_backend)
        and (not silence_filtered)
        and (not _is_realtime_free_talk_mode(mode))
        and (source != 'webrtc_stream_cloud_verify_rejected')
    )
    if not transcript and hint_text and allow_hint_fallback:
        transcript = hint_text.strip()
        source = "browser_hint_fallback"

    if not source:
        source = "asr_empty"

    return {
        "transcript": transcript,
        "source": source,
        "request_id": request_id,
        "backend": backend_name,
        "duration_s": duration_s,
        "backend_error": backend_error,
        "speech_frame_count": speech_frames,
        "total_frame_count": all_frames,
        "max_audio_level": round(peak_audio_level, 3),
        "dropped_avatar_frames": dropped_avatar_frame_count,
        "silence_filtered": silence_filtered,
        **extra_payload,
    }


def _register_webrtc_media_task(sessionid: int, task: asyncio.Task) -> None:
    with webrtc_media_lock:
        tasks = webrtc_media_tasks.setdefault(sessionid, set())
        tasks.add(task)

    def _cleanup_done_task(done_task: asyncio.Task) -> None:
        with webrtc_media_lock:
            task_set = webrtc_media_tasks.get(sessionid)
            if task_set is not None:
                task_set.discard(done_task)
                if not task_set:
                    webrtc_media_tasks.pop(sessionid, None)

    task.add_done_callback(_cleanup_done_task)


def _cleanup_webrtc_media_session(sessionid: int) -> None:
    with webrtc_media_lock:
        tasks = list(webrtc_media_tasks.pop(sessionid, set()))
        webrtc_media_states.pop(sessionid, None)
        webrtc_asr_runtime.pop(sessionid, None)
        recent_assistant_utterances.pop(sessionid, None)
    
    # 🔧 清理人脸情绪缓存，防止内存泄漏
    with face_emotion_cache_lock:
        face_emotion_cache.pop(sessionid, None)

    for task in tasks:
        if not task.done():
            task.cancel()


def _publish_chat_event(sessionid: int, payload: Dict[str, Any]) -> None:
    subscribers = chat_subscribers.get(sessionid)
    if not subscribers:
        return

    # SSE 队列满时丢弃最旧事件，优先保证“最新状态”可达。
    for queue in list(subscribers):
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(payload)
        except Exception:
            pass


def _emit_chat_payloads(
    loop: asyncio.AbstractEventLoop,
    sessionid: int,
    payloads: List[Dict[str, Any]],
) -> None:
    for payload in payloads:
        try:
            loop.call_soon_threadsafe(_publish_chat_event, sessionid, payload)
        except RuntimeError:
            break


def _register_chat_stream_state(
    stream_id: str,
    sessionid: int,
    loop: asyncio.AbstractEventLoop,
) -> Event:
    # 每条 chat_stream 对应一个状态机：
    # LLM 先持续产出 delta；真正 start 要等 TTS 第一帧音频事件触发。
    speech_started_event = Event()
    with chat_stream_states_lock:
        chat_stream_states[stream_id] = {
            "sessionid": sessionid,
            "loop": loop,
            "speech_started": False,
            "speech_started_event": speech_started_event,
            "pending_chunks": [],
            "llm_finished": False,
            "full_text": "",
        }
    return speech_started_event


def _buffer_or_build_chunk_payloads(stream_id: str, delta: str):
    with chat_stream_states_lock:
        state = chat_stream_states.get(stream_id)
        if state is None:
            return None

        if state["speech_started"]:
            payloads = [{"event": "chunk", "stream_id": stream_id, "text": delta}]
            return state["loop"], state["sessionid"], payloads

        # 语音尚未开始时先缓存文本，避免前端出现“先出字后出声”的错位感。
        state["pending_chunks"].append(delta)
        return None


def _mark_chat_stream_voice_started(stream_id: str):
    with chat_stream_states_lock:
        state = chat_stream_states.get(stream_id)
        if state is None or state["speech_started"]:
            return None

        # start 仅触发一次，并把等待中的增量文本按顺序回放给前端。
        state["speech_started"] = True
        state["speech_started_event"].set()

        buffered_chunks = list(state["pending_chunks"])
        state["pending_chunks"].clear()

        payloads = [{"event": "start", "stream_id": stream_id}]
        for chunk in buffered_chunks:
            if chunk:
                payloads.append({"event": "chunk", "stream_id": stream_id, "text": chunk})

        if state["llm_finished"]:
            end_text = state["full_text"] or "".join(buffered_chunks)
            payloads.append({"event": "end", "stream_id": stream_id, "text": end_text})
            chat_stream_states.pop(stream_id, None)

        return state["loop"], state["sessionid"], payloads


def _mark_chat_stream_llm_finished(stream_id: str, full_text: str):
    with chat_stream_states_lock:
        state = chat_stream_states.get(stream_id)
        if state is None:
            return None

        state["full_text"] = full_text or ""
        state["llm_finished"] = True

        payloads: List[Dict[str, Any]] = []
        if state["speech_started"]:
            payloads.append({"event": "end", "stream_id": stream_id, "text": state["full_text"]})
            chat_stream_states.pop(stream_id, None)

        return state["loop"], state["sessionid"], payloads, state["speech_started_event"]


def _force_emit_chat_stream_without_voice_start(stream_id: str):
    with chat_stream_states_lock:
        state = chat_stream_states.pop(stream_id, None)
        if state is None:
            return None

        state["speech_started_event"].set()
        pending_chunks = list(state["pending_chunks"])
        fallback_text = state["full_text"] or "".join(pending_chunks)
        payloads = [{"event": "start", "stream_id": stream_id}]
        if pending_chunks:
            for chunk in pending_chunks:
                if chunk:
                    payloads.append({"event": "chunk", "stream_id": stream_id, "text": chunk})
        elif fallback_text:
            payloads.append({"event": "chunk", "stream_id": stream_id, "text": fallback_text})
        payloads.append({"event": "end", "stream_id": stream_id, "text": fallback_text})
        return state["loop"], state["sessionid"], payloads


def _abort_chat_stream(stream_id: str, message: str):
    with chat_stream_states_lock:
        state = chat_stream_states.pop(stream_id, None)
        if state is None:
            return None
        state["speech_started_event"].set()
        payloads = [{"event": "error", "stream_id": stream_id, "message": message}]
        return state["loop"], state["sessionid"], payloads


def _clear_chat_stream_states_for_session(sessionid: int) -> None:
    with chat_stream_states_lock:
        stream_ids = [
            stream_id
            for stream_id, state in chat_stream_states.items()
            if state.get("sessionid") == sessionid
        ]
        for stream_id in stream_ids:
            state = chat_stream_states.pop(stream_id, None)
            if state is not None:
                state["speech_started_event"].set()


def _handle_audio_event_for_chat_stream(eventpoint: Dict[str, Any]) -> None:
    if not isinstance(eventpoint, dict):
        return
    if eventpoint.get("status") != "start":
        return

    stream_id = eventpoint.get("chat_stream_id")
    if not stream_id:
        return

    result = _mark_chat_stream_voice_started(stream_id)
    if result is None:
        return

    loop, sessionid, payloads = result
    _emit_chat_payloads(loop, sessionid, payloads)


def _run_llm_with_chat_stream(
    user_text: str,
    sessionid: int,
    nerfreal: BaseReal,
    loop: asyncio.AbstractEventLoop,
    mode: str = 'chat',
    audio_emotion: str = '',
    face_emotion: str = '',
    emotion_score: Optional[float] = None,
    emotion_extra: Any = None,
    user_name: str = '',
) -> None:
    stream_id = f"{sessionid}-{randN(8)}"
    llm_call_started = time.perf_counter()
    delta_chunk_count = 0
    delta_char_count = 0
    speech_started_event = _register_chat_stream_state(stream_id, sessionid, loop)
    _emit_chat_payloads(
        loop,
        sessionid,
        [{"event": "thinking", "stream_id": stream_id}],
    )

    def on_delta(delta: str) -> None:
        nonlocal delta_chunk_count, delta_char_count
        if not delta:
            return
        delta_chunk_count += 1
        delta_char_count += len(delta)

        # LLM 增量文本与 TTS 事件解耦：
        # 未开口前先缓存；开口后直接向 SSE 推送 chunk。
        result = _buffer_or_build_chunk_payloads(stream_id, delta)
        if result is None:
            return
        emit_loop, emit_sessionid, payloads = result
        _emit_chat_payloads(emit_loop, emit_sessionid, payloads)

    try:
        llm_user_text = _build_llm_user_text_with_multimodal_emotions(
            user_text,
            audio_emotion=audio_emotion,
            face_emotion=face_emotion,
        )
        rag_result = retrieve_lightrag_context(
            _build_chat_rag_query(
                user_text,
                audio_emotion=audio_emotion,
                face_emotion=face_emotion,
            ),
            hl_keywords=['心理陪伴', '共情回复', '风险识别', '干预边界'],
            ll_keywords=[str(user_text or '').strip(), audio_emotion, face_emotion],
        )
        rag_context = str(rag_result.get('context', '') or '').strip()
        full_text_raw = llm_handler(
            llm_user_text,
            nerfreal,
            on_delta=on_delta,
            tts_event={
                "chat_stream_id": stream_id,
                "chat_sessionid": sessionid,
                "persona_user_name": user_name,
                "external_knowledge": rag_context,
            },
        )
        full_text = str(full_text_raw or '')
        llm_elapsed_ms = int((time.perf_counter() - llm_call_started) * 1000)

        _append_chat_record_api_call(
            sessionid=sessionid,
            api_name='llm.generate',
            status='ok',
            mode=mode,
            source='llm',
            duration_ms=llm_elapsed_ms,
            request_payload={
                'stream_id': stream_id,
                'user_text': str(user_text or ''),
                'llm_user_text': llm_user_text,
                'audio_emotion': str(audio_emotion or ''),
                'face_emotion': str(face_emotion or ''),
                'emotion_score': emotion_score,
                'emotion_extra': emotion_extra,
                'lightrag_status': rag_result.get('status'),
                'lightrag_context_len': len(rag_context),
                'lightrag_references': rag_result.get('references', []),
            },
            response_payload={
                'stream_id': stream_id,
                'assistant_text': full_text,
                'assistant_text_len': len(full_text),
                'delta_chunk_count': int(delta_chunk_count),
                'delta_char_count': int(delta_char_count),
            },
        )

        _record_chat_text_if_needed(
            sessionid=sessionid,
            role='assistant',
            text=full_text,
            mode=mode,
            source='llm',
        )

        result = _mark_chat_stream_llm_finished(stream_id, full_text)
        if result is not None:
            emit_loop, emit_sessionid, payloads, _ = result
            if payloads:
                _emit_chat_payloads(emit_loop, emit_sessionid, payloads)
            elif not speech_started_event.wait(timeout=CHAT_STREAM_VOICE_START_TIMEOUT_S):
                # 容错：若 TTS 未按时触发 start，则强制补发 start/chunk/end，避免前端悬挂。
                fallback = _force_emit_chat_stream_without_voice_start(stream_id)
                if fallback is not None:
                    fallback_loop, fallback_sessionid, fallback_payloads = fallback
                    _emit_chat_payloads(fallback_loop, fallback_sessionid, fallback_payloads)
    except Exception as e:
        llm_elapsed_ms = int((time.perf_counter() - llm_call_started) * 1000)
        _append_chat_record_api_call(
            sessionid=sessionid,
            api_name='llm.generate',
            status='error',
            mode=mode,
            source='llm',
            duration_ms=llm_elapsed_ms,
            request_payload={
                'stream_id': stream_id,
                'user_text': str(user_text or ''),
                'audio_emotion': str(audio_emotion or ''),
                'face_emotion': str(face_emotion or ''),
                'emotion_score': emotion_score,
                'emotion_extra': emotion_extra,
            },
            response_payload={
                'delta_chunk_count': int(delta_chunk_count),
                'delta_char_count': int(delta_char_count),
            },
            error_message=str(e),
        )
        logger.exception('llm stream exception:')
        _append_chat_record_event(
            sessionid,
            'chat_error',
            {
                'mode': _normalize_chat_mode(mode),
                'stage': 'llm_stream',
                'message': str(e),
            },
        )
        aborted = _abort_chat_stream(stream_id, str(e))
        if aborted is None:
            _emit_chat_payloads(
                loop,
                sessionid,
                [{"event": "error", "stream_id": stream_id, "message": str(e)}],
            )
        else:
            emit_loop, emit_sessionid, payloads = aborted
            _emit_chat_payloads(emit_loop, emit_sessionid, payloads)


async def _run_webrtc_partial_asr_job(
    *,
    sessionid: int,
    utterance_id: int,
    mode: str,
    pcm16_bytes: bytes,
    speech_frame_count: int,
    total_frame_count: int,
    max_audio_level: float,
    dropped_avatar_frames: int,
) -> None:
    payload: Dict[str, Any] = {}
    try:
        # partial ASR 放到线程池执行，避免阻塞事件循环中的媒体接收协程。
        loop = asyncio.get_running_loop()
        payload = await loop.run_in_executor(
            None,
            lambda: _transcribe_webrtc_pcm_bytes(
                sessionid=sessionid,
                pcm16_bytes=pcm16_bytes,
                mode=mode,
                hint_text="",
                speech_frame_count=speech_frame_count,
                total_frame_count=total_frame_count,
                max_audio_level=max_audio_level,
                dropped_avatar_frames=dropped_avatar_frames,
            ),
        )

        transcript = str(payload.get("transcript", "") or "").strip()
        source = str(payload.get("source", "") or "webrtc_stream_asr")
        
        # 🔧 修复：检测到静音时清空缓冲区，防止溢出
        if source == "webrtc_stream_silence_filtered":
            with webrtc_media_lock:
                runtime = webrtc_asr_runtime.get(sessionid)
                if runtime is not None and int(runtime.get("utterance_id", 0)) == int(utterance_id):
                    # 清空缓冲区和统计数据，避免静音数据累积导致溢出
                    buffer_size = len(runtime.get("pcm16_buffer", bytearray()))
                    runtime["pcm16_buffer"] = bytearray()
                    runtime["speech_frame_count"] = 0
                    runtime["total_frame_count"] = 0
                    runtime["max_audio_level"] = 0.0
                    runtime["dropped_avatar_frames"] = 0
                    logger.debug(
                        "sessionid=%d partial asr silence detected, cleared buffer (%d bytes)",
                        sessionid,
                        buffer_size,
                    )
            return
        
        if not transcript:
            return

        backend_name = str(payload.get("backend", "") or str(getattr(asr_backend, "name", "none") or "none"))
        request_id = str(payload.get("request_id", "") or "")
        duration_s = float(payload.get("duration_s", 0.0) or 0.0)
        
        # 🆕 2.3 提取 partial 状态的情绪标签（可能为空）
        emotion_payload = _extract_emotion_payload(payload)
        if emotion_payload.get('emotion_label'):
            logger.debug(
                "[ASR Emotion Partial] sessionid=%d, emotion_label='%s', transcript='%s'",
                sessionid,
                emotion_payload.get('emotion_label', ''),
                transcript[:50] if len(transcript) > 50 else transcript,
            )

        with webrtc_media_lock:
            runtime = webrtc_asr_runtime.get(sessionid)
            if runtime is None or int(runtime.get("utterance_id", 0)) != int(utterance_id):
                # 录音段已切换，丢弃旧任务结果，防止跨段串写。
                return

            if transcript == str(runtime.get("last_partial_transcript", "") or ""):
                # 去重：避免短周期 partial 回传同样文本造成前端抖动。
                return

            runtime["last_partial_transcript"] = transcript

            state = webrtc_media_states.get(sessionid)
            if state is None:
                state = _build_default_webrtc_media_state(sessionid)
                webrtc_media_states[sessionid] = state

            state["last_asr"] = _build_webrtc_asr_state_payload(
                transcript=transcript,
                source=source,
                backend=backend_name,
                mode=mode,
                status="partial",
                utterance_id=utterance_id,
                duration_s=duration_s,
                request_id=request_id,
                extra_fields=emotion_payload,  # 🆕 2.3 传递情绪标签
            )
            state["updated_at_ms"] = int(time.time() * 1000)
    except Exception:
        logger.exception("sessionid=%d webrtc partial asr task exception", sessionid)
    finally:
        with webrtc_media_lock:
            runtime = webrtc_asr_runtime.get(sessionid)
            if runtime is not None and int(runtime.get("utterance_id", 0)) == int(utterance_id):
                runtime["partial_inflight"] = False


async def _consume_webrtc_audio_track(sessionid: int, track) -> None:
    _ensure_webrtc_media_state(sessionid)
    _ensure_webrtc_asr_runtime(sessionid)
    frame_resampler = _create_webrtc_audio_resampler()

    try:
        while True:
            # 按 aiortc 上行时钟持续收帧，统一转成 16k/mono/s16。
            frame = await track.recv()
            pcm16_bytes, avg_level = _frame_to_pcm16_mono_16k(
                frame,
                frame_resampler=frame_resampler,
            )

            should_run_partial = False
            partial_pcm = b""
            partial_mode = "chat"
            partial_utterance_id = 0
            partial_speech_frame_count = 0
            partial_total_frame_count = 0
            partial_max_audio_level = 0.0
            partial_dropped_avatar_frames = 0
            now_ms = int(time.time() * 1000)

            avatar_speaking = False
            session_real = nerfreals.get(sessionid)
            if session_real is not None and hasattr(session_real, 'is_speaking'):
                try:
                    avatar_speaking = bool(session_real.is_speaking())
                except Exception:
                    avatar_speaking = False

            speech_level = max(
                0.0,
                _safe_float(
                    getattr(opt, 'WEBRTC_ASR_SPEECH_LEVEL', WEBRTC_ASR_SPEECH_LEVEL),
                    WEBRTC_ASR_SPEECH_LEVEL,
                ),
            )
            drop_while_avatar_speaking = bool(
                _safe_int(getattr(opt, 'WEBRTC_ASR_DROP_WHILE_AVATAR_SPEAKING', 1), 1)
            )

            with webrtc_media_lock:
                # 所有共享状态更新都走同一把锁，避免 track 结束与控制指令竞争。
                state = webrtc_media_states.get(sessionid)
                if state is None:
                    state = _build_default_webrtc_media_state(sessionid)
                    webrtc_media_states[sessionid] = state
                state["audio_frame_count"] = int(state.get("audio_frame_count", 0)) + 1
                state["updated_at_ms"] = now_ms

                runtime = webrtc_asr_runtime.get(sessionid)
                if runtime is None:
                    runtime = _build_default_webrtc_asr_runtime()
                    webrtc_asr_runtime[sessionid] = runtime

                if runtime.get("recording") and pcm16_bytes:
                    runtime["total_frame_count"] = _safe_int(runtime.get("total_frame_count", 0), 0) + 1
                    if avg_level >= speech_level:
                        runtime["speech_frame_count"] = _safe_int(runtime.get("speech_frame_count", 0), 0) + 1
                    runtime["max_audio_level"] = max(
                        _safe_float(runtime.get("max_audio_level", 0.0), 0.0),
                        float(avg_level),
                    )

                    if avatar_speaking and drop_while_avatar_speaking:
                        runtime["dropped_avatar_frames"] = _safe_int(runtime.get("dropped_avatar_frames", 0), 0) + 1
                    else:
                        # 防止内存泄漏：限制 pcm16_buffer 最大为 30 秒音频（960KB）
                        MAX_PCM16_BUFFER_SIZE = 16000 * 2 * 30  # 30秒 @ 16kHz/16bit/mono = 960,000 bytes
                        current_size = len(runtime["pcm16_buffer"])
                        if current_size + len(pcm16_bytes) > MAX_PCM16_BUFFER_SIZE:
                            # 缓冲区已满，丢弃最旧的数据，保留最新的 30 秒
                            overflow = current_size + len(pcm16_bytes) - MAX_PCM16_BUFFER_SIZE
                            runtime["pcm16_buffer"] = runtime["pcm16_buffer"][overflow:]
                            logger.warning(
                                "sessionid=%d pcm16_buffer overflow, dropped %d bytes (current=%d, max=%d)",
                                sessionid, overflow, current_size, MAX_PCM16_BUFFER_SIZE
                            )
                        runtime["pcm16_buffer"].extend(pcm16_bytes)

                    elapsed_ms = now_ms - int(runtime.get("last_partial_request_ms", 0))
                    if (
                        not runtime.get("partial_inflight")
                        and len(runtime["pcm16_buffer"]) >= WEBRTC_ASR_MIN_PCM_BYTES
                        and elapsed_ms >= int(WEBRTC_ASR_PARTIAL_INTERVAL_S * 1000)
                    ):
                        # partial 触发条件：
                        # 1) 当前无在飞任务；2) 缓冲长度达阈值；3) 距上次请求间隔达标。
                        runtime["partial_inflight"] = True
                        runtime["last_partial_request_ms"] = now_ms
                        partial_utterance_id = int(runtime.get("utterance_id", 0))
                        partial_mode = str(runtime.get("mode", "chat") or "chat")
                        partial_pcm = bytes(runtime["pcm16_buffer"])
                        partial_speech_frame_count = _safe_int(runtime.get("speech_frame_count", 0), 0)
                        partial_total_frame_count = _safe_int(runtime.get("total_frame_count", 0), 0)
                        partial_max_audio_level = _safe_float(runtime.get("max_audio_level", 0.0), 0.0)
                        partial_dropped_avatar_frames = _safe_int(runtime.get("dropped_avatar_frames", 0), 0)
                        should_run_partial = True

            if should_run_partial:
                # partial 异步执行，不阻塞主接收协程，保证音频上行持续可读。
                partial_task = asyncio.create_task(
                    _run_webrtc_partial_asr_job(
                        sessionid=sessionid,
                        utterance_id=partial_utterance_id,
                        mode=partial_mode,
                        pcm16_bytes=partial_pcm,
                        speech_frame_count=partial_speech_frame_count,
                        total_frame_count=partial_total_frame_count,
                        max_audio_level=partial_max_audio_level,
                        dropped_avatar_frames=partial_dropped_avatar_frames,
                    )
                )
                _register_webrtc_media_task(sessionid, partial_task)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.info('sessionid=%d incoming audio track ended: %s', sessionid, e)


async def _consume_webrtc_video_track(sessionid: int, track) -> None:
    _ensure_webrtc_media_state(sessionid)

    total_video_frames = 0
    face_analyze_every_n = _get_deepface_analyze_every_n()

    try:
        while True:
            frame = await track.recv()
            image = frame.to_ndarray(format="bgr24")
            if image.size == 0:
                continue

            total_video_frames += 1

            with webrtc_media_lock:
                state = webrtc_media_states.get(sessionid)
                if state is None:
                    state = _build_default_webrtc_media_state(sessionid)
                    webrtc_media_states[sessionid] = state
                state["video_frame_count"] = int(state.get("video_frame_count", 0)) + 1
                state["updated_at_ms"] = int(time.time() * 1000)

            if _is_deepface_enabled() and total_video_frames % face_analyze_every_n == 0:
                cv2_mod = _get_cv2_module()
                if cv2_mod is not None:
                    temp_frame_path = ''
                    try:
                        with tempfile.NamedTemporaryFile(
                            prefix=f'sid{sessionid}_face_',
                            suffix='.jpg',
                            delete=False,
                        ) as temp_frame:
                            temp_frame_path = temp_frame.name

                        ok = cv2_mod.imwrite(
                            temp_frame_path,
                            image,
                            [int(cv2_mod.IMWRITE_JPEG_QUALITY), 90],
                        )
                        if ok and os.path.exists(temp_frame_path) and os.path.getsize(temp_frame_path) > 0:
                            asyncio.create_task(
                                _analyze_face_emotion_async(
                                    sessionid=sessionid,
                                    image_path=temp_frame_path,
                                    frame_index=total_video_frames,
                                    delete_after=True,
                                )
                            )
                        elif temp_frame_path:
                            try:
                                os.remove(temp_frame_path)
                            except FileNotFoundError:
                                pass
                    except Exception:
                        if temp_frame_path:
                            try:
                                os.remove(temp_frame_path)
                            except FileNotFoundError:
                                pass
                        logger.debug('sessionid=%d temporary face frame write failed', sessionid, exc_info=True)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.info('sessionid=%d incoming video track ended: %s', sessionid, e)
        

#####webrtc###############################
pcs = set()
# 当前会话正在使用的 RTCPeerConnection。
# 用于在前端 profile 重试时复用 session，避免重复 build_nerfreal。
session_peer_connections: Dict[int, Any] = {}



def randN(N)->int:
    '''生成长度为 N的随机数 '''
    min = pow(10, N - 1)
    max = pow(10, N)
    return random.randint(min, max - 1)

def build_nerfreal(sessionid:int)->BaseReal:
    opt.sessionid=sessionid
    from dittoreal import DittoReal
    return DittoReal(opt,model,avatar)

#@app.route('/offer', methods=['POST'])
async def offer(request):
    offer_start_ts = time.perf_counter()
    sessionid = 0
    requested_sessionid = 0
    offer_sdp = ''
    offer_type = ''
    can_reuse_session = False

    try:
        params = await request.json()
        if not isinstance(params, dict):
            return web.json_response({'code': -1, 'msg': 'invalid offer payload: expected json object'}, status=400)

        offer_sdp = str(params.get('sdp', '') or '')
        offer_type = str(params.get('type', '') or '')
        requested_sessionid = _safe_int(params.get('sessionid', 0), 0)

        if (not offer_sdp) or (not offer_type):
            return web.json_response({'code': -1, 'msg': 'invalid offer payload: missing sdp/type'}, status=400)

        try:
            offer = RTCSessionDescription(sdp=offer_sdp, type=offer_type)
        except Exception as exc:
            return web.json_response({'code': -1, 'msg': f'invalid offer payload: {str(exc)}'}, status=400)

        # if len(nerfreals) >= opt.max_session:
        #     logger.info('reach max session')
        #     return web.Response(
        #         content_type="application/json",
        #         text=json.dumps(
        #             {"code": -1, "msg": "reach max session"}
        #         ),
        #     )
        # profile 重试时复用既有 session：
        # - 前端若把上一次 /offer 返回的 sessionid 带回，本分支将跳过 build_nerfreal；
        # - 只重建 peer connection 与 track consumer，显著降低“connecting->重试”成本。
        can_reuse_session = (
            requested_sessionid > 0
            and requested_sessionid in nerfreals
            and nerfreals.get(requested_sessionid) is not None
        )

        if can_reuse_session:
            sessionid = requested_sessionid
            nerfreal = nerfreals[sessionid]

            old_pc = session_peer_connections.get(sessionid)
            if old_pc is not None:
                # 先摘掉映射再 close，防止旧 pc 的 closed 回调把会话整体清理掉。
                session_peer_connections[sessionid] = None
                try:
                    await old_pc.close()
                except Exception:
                    logger.exception('sessionid=%d close old pc failed during offer reuse', sessionid)
                pcs.discard(old_pc)

            _clear_chat_stream_states_for_session(sessionid)
            _cleanup_webrtc_media_session(sessionid)
            _ensure_webrtc_media_state(sessionid)
            _ensure_webrtc_asr_runtime(sessionid)
            logger.info('sessionid=%d reuse existing session for offer retry', sessionid)
            _append_chat_record_event(
                sessionid,
                'offer_retry_reuse_session',
                {
                    'requested_sessionid': int(requested_sessionid),
                },
            )
        else:
            sessionid = randN(6) #len(nerfreals)
            nerfreals[sessionid] = None
            logger.info('sessionid=%d, session num=%d',sessionid,len(nerfreals))

            init_start_ts = time.perf_counter()
            nerfreal = await asyncio.get_event_loop().run_in_executor(None, build_nerfreal,sessionid)
            init_elapsed_ms = int((time.perf_counter() - init_start_ts) * 1000)
            logger.info('sessionid=%d, build_nerfreal elapsed=%dms', sessionid, init_elapsed_ms)
            nerfreal.on_audio_event = _handle_audio_event_for_chat_stream
            nerfreals[sessionid] = nerfreal
            _ensure_webrtc_media_state(sessionid)
            _ensure_webrtc_asr_runtime(sessionid)
            _append_chat_record_event(
                sessionid,
                'offer_new_session',
                {
                    'session_num': int(len(nerfreals)),
                    'build_nerfreal_elapsed_ms': int(init_elapsed_ms),
                },
            )

        ice_servers = build_ice_servers()
        pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=ice_servers))
        pcs.add(pc)
        session_peer_connections[sessionid] = pc
        connect_watchdog_task = None

        async def _close_if_stuck_connecting() -> None:
            await asyncio.sleep(WEBRTC_CONNECTING_TIMEOUT_S)

            # 只处理当前 session 的“在位 pc”，避免误杀已切换后的新连接。
            if session_peer_connections.get(sessionid) is not pc:
                return

            if pc.connectionState in ("new", "connecting"):
                logger.warning(
                    "sessionid=%d connecting watchdog timeout, force close pc (state=%s)",
                    sessionid,
                    pc.connectionState,
                )
                try:
                    await pc.close()
                except Exception:
                    logger.exception("sessionid=%d watchdog close pc failed", sessionid)

        connect_watchdog_task = asyncio.create_task(_close_if_stuck_connecting())

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info("sessionid=%d, connection state is %s", sessionid, pc.connectionState)
            _append_chat_record_event(
                sessionid,
                'pc_connection_state',
                {
                    'state': str(pc.connectionState),
                },
            )

            # 当前 session 已被更新到新 pc 时，旧 pc 状态变化不应触发会话清理。
            if session_peer_connections.get(sessionid) is not pc:
                return

            if pc.connectionState == "connected":
                if connect_watchdog_task is not None and not connect_watchdog_task.done():
                    connect_watchdog_task.cancel()
                return

            if pc.connectionState == "failed":
                if connect_watchdog_task is not None and not connect_watchdog_task.done():
                    connect_watchdog_task.cancel()
                await pc.close()
                pcs.discard(pc)
                session_peer_connections.pop(sessionid, None)
                nerfreals.pop(sessionid, None)
                chat_subscribers.pop(sessionid, None)
                _clear_chat_stream_states_for_session(sessionid)
                _cleanup_webrtc_media_session(sessionid)
                _append_chat_record_event(
                    sessionid,
                    'pc_cleanup',
                    {
                        'reason': 'failed',
                    },
                )
            if pc.connectionState == "closed":
                if connect_watchdog_task is not None and not connect_watchdog_task.done():
                    connect_watchdog_task.cancel()
                pcs.discard(pc)
                session_peer_connections.pop(sessionid, None)
                nerfreals.pop(sessionid, None)
                chat_subscribers.pop(sessionid, None)
                _clear_chat_stream_states_for_session(sessionid)
                _cleanup_webrtc_media_session(sessionid)
                _append_chat_record_event(
                    sessionid,
                    'pc_cleanup',
                    {
                        'reason': 'closed',
                    },
                )
                # gc.collect()

        player = HumanPlayer(nerfreals[sessionid])
        audio_sender = pc.addTrack(player.audio)
        video_sender = pc.addTrack(player.video)
        capabilities = RTCRtpSender.getCapabilities("video")
        if opt.prefer_h264:
            preferences = list(filter(lambda x: x.name == "H264", capabilities.codecs))
            preferences += list(filter(lambda x: x.name == "VP8", capabilities.codecs))
        else:
            # 默认将 VP8 放在前面，兼容性更稳；H264 作为后备。
            preferences = list(filter(lambda x: x.name == "VP8", capabilities.codecs))
            preferences += list(filter(lambda x: x.name == "H264", capabilities.codecs))
        preferences += list(filter(lambda x: x.name == "rtx", capabilities.codecs))
        transceiver = next((t for t in pc.getTransceivers() if t.sender == video_sender), None)
        if transceiver and preferences:
            transceiver.setCodecPreferences(preferences)

        @pc.on("track")
        def on_track(track):
            logger.info('sessionid=%d, receive incoming %s track from frontend', sessionid, track.kind)

            consume_task = None
            if track.kind == "audio":
                consume_task = asyncio.create_task(_consume_webrtc_audio_track(sessionid, track))
            elif track.kind == "video":
                consume_task = asyncio.create_task(_consume_webrtc_video_track(sessionid, track))

            if consume_task is not None:
                _register_webrtc_media_task(sessionid, consume_task)

            @track.on("ended")
            def on_ended():
                logger.info('sessionid=%d, incoming %s track ended', sessionid, track.kind)

        await pc.setRemoteDescription(offer)

        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        offer_elapsed_ms = int((time.perf_counter() - offer_start_ts) * 1000)
        logger.info('sessionid=%d, offer total elapsed=%dms', sessionid, offer_elapsed_ms)

        response_payload: Dict[str, Any] = {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "sessionid": sessionid,
            "reused": bool(can_reuse_session),
        }

        _append_chat_record_api_call(
            sessionid=sessionid,
            api_name='/offer',
            status='ok',
            mode='webrtc',
            source='offer',
            duration_ms=offer_elapsed_ms,
            request_payload={
                'requested_sessionid': int(requested_sessionid),
                'offer_type': offer_type,
                'sdp_len': len(offer_sdp),
            },
            response_payload={
                'sessionid': int(sessionid),
                'reused': bool(can_reuse_session),
                'answer_type': str(pc.localDescription.type or ''),
                'answer_sdp_len': len(str(pc.localDescription.sdp or '')),
            },
        )

        return web.json_response(response_payload)
    except Exception as e:
        offer_elapsed_ms = int((time.perf_counter() - offer_start_ts) * 1000)
        logger.exception('offer exception:')

        pc = session_peer_connections.get(sessionid) if sessionid > 0 else None
        if pc is not None:
            try:
                await pc.close()
            except Exception:
                logger.exception('sessionid=%d close pc failed after offer exception', sessionid)
            pcs.discard(pc)
            if session_peer_connections.get(sessionid) is pc:
                session_peer_connections.pop(sessionid, None)

        if sessionid > 0 and (not can_reuse_session):
            chat_subscribers.pop(sessionid, None)
            nerfreals.pop(sessionid, None)
            _clear_chat_stream_states_for_session(sessionid)
            _cleanup_webrtc_media_session(sessionid)

        log_sessionid = sessionid if sessionid > 0 else requested_sessionid
        if log_sessionid > 0:
            _append_chat_record_event(
                log_sessionid,
                'offer_error',
                {
                    'requested_sessionid': int(requested_sessionid),
                    'message': str(e),
                    'elapsed_ms': int(offer_elapsed_ms),
                },
            )
            _append_chat_record_api_call(
                sessionid=log_sessionid,
                api_name='/offer',
                status='error',
                mode='webrtc',
                source='offer',
                duration_ms=offer_elapsed_ms,
                request_payload={
                    'requested_sessionid': int(requested_sessionid),
                    'offer_type': offer_type,
                    'sdp_len': len(offer_sdp),
                },
                error_message=str(e),
            )

        return web.json_response({'code': -1, 'msg': f'offer failed: {str(e)}'}, status=500)

async def candidate(request):
    """
    Handle incoming ICE candidates from frontend for trickle ICE support.
    This endpoint receives ICE candidates generated by the frontend peer connection
    and adds them to the backend peer connection to enable connectivity checks.
    """
    try:
        params = await request.json()
        if not isinstance(params, dict):
            return web.json_response({'code': -1, 'msg': 'invalid candidate payload: expected json object'}, status=400)

        sessionid = _safe_int(params.get('sessionid', 0), 0)
        candidate_dict = params.get('candidate')

        if sessionid <= 0:
            return web.json_response({'code': -1, 'msg': 'invalid candidate payload: missing or invalid sessionid'}, status=400)

        if not isinstance(candidate_dict, dict):
            return web.json_response({'code': -1, 'msg': 'invalid candidate payload: candidate must be an object'}, status=400)

        # Check if session exists and has an active peer connection
        pc = session_peer_connections.get(sessionid)
        if pc is None:
            logger.warning('sessionid=%d candidate received but no active peer connection', sessionid)
            return web.json_response({'code': -1, 'msg': 'session not found or peer connection not active'}, status=404)

        # Convert candidate dict to RTCIceCandidate object
        try:
            ice_candidate = RTCIceCandidate(
                sdpMid=candidate_dict.get('sdpMid'),
                sdpMLineIndex=candidate_dict.get('sdpMLineIndex'),
                candidate=candidate_dict.get('candidate')
            )
        except Exception as exc:
            logger.warning('sessionid=%d invalid candidate format: %s', sessionid, str(exc))
            return web.json_response({'code': -1, 'msg': f'invalid candidate format: {str(exc)}'}, status=400)

        # Add the candidate to the peer connection
        try:
            await pc.addIceCandidate(ice_candidate)
            logger.info('sessionid=%d added ICE candidate: %s', sessionid, candidate_dict.get('candidate', '')[:80])
        except Exception as exc:
            logger.warning('sessionid=%d failed to add ICE candidate: %s', sessionid, str(exc))
            return web.json_response({'code': -1, 'msg': f'failed to add candidate: {str(exc)}'}, status=500)

        return web.json_response({'status': 'ok'})

    except Exception as e:
        logger.exception('candidate endpoint exception:')
        return web.json_response({'code': -1, 'msg': f'candidate failed: {str(e)}'}, status=500)

async def human(request):
    try:
        params = await request.json()

        sessionid = params.get('sessionid',0)
        user_name = str(params.get('user_name', '') or '').strip()
        mode = _normalize_chat_mode(params.get('mode', 'chat'))
        source = str(params.get('source', 'manual_text') or 'manual_text').strip().lower()
        # 获取音频情绪（来自 ASR）
        audio_emotion = str(params.get('emotion_label', '') or '').strip()
        emotion_score = None
        raw_emotion_score = params.get('emotion_score', None)
        if raw_emotion_score is not None and str(raw_emotion_score).strip() != '':
            try:
                emotion_score = float(raw_emotion_score)
            except (TypeError, ValueError):
                emotion_score = None
        emotion_extra = params.get('emotion_extra', None)
        
        # 获取人脸情绪（从缓存中读取）
        face_emotion = _get_latest_face_emotion(sessionid)
        
        if params.get('interrupt'):
            nerfreals[sessionid].flush_talk()

        if params['type']=='echo':
            nerfreals[sessionid].put_msg_txt(params['text'])
        elif params['type']=='chat':
            _record_chat_text_if_needed(
                sessionid=sessionid,
                role='user',
                text=str(params.get('text', '') or ''),
                mode=mode,
                source=source,
            )
            loop = asyncio.get_running_loop()
            loop.run_in_executor(
                None,
                _run_llm_with_chat_stream,
                params['text'],
                sessionid,
                nerfreals[sessionid],
                loop,
                mode,
                audio_emotion,
                face_emotion,
                emotion_score,
                emotion_extra,
                user_name,
            )
            #nerfreals[sessionid].put_msg_txt(res)

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg":"ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )

async def chat_stream(request):
    sessionid_raw = request.query.get('sessionid', '0')
    try:
        sessionid = int(sessionid_raw)
    except ValueError:
        sessionid = 0

    if sessionid <= 0:
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": "invalid sessionid"}),
            status=400,
        )

    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    chat_subscribers.setdefault(sessionid, set()).add(queue)

    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'X-Accel-Buffering': 'no',
        },
    )
    await response.prepare(request)
    await response.write(b': connected\n\n')

    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=20)
                data = json.dumps(payload, ensure_ascii=False)
                await response.write(f"data: {data}\n\n".encode('utf-8'))
            except asyncio.TimeoutError:
                await response.write(b': ping\n\n')
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError, RuntimeError):
        pass
    finally:
        subscribers = chat_subscribers.get(sessionid)
        if subscribers is not None:
            subscribers.discard(queue)
            if not subscribers:
                chat_subscribers.pop(sessionid, None)
        try:
            await response.write_eof()
        except Exception:
            pass

    return response


async def ai_conversation(request):
    try:
        params = await request.json()
        if not isinstance(params, dict):
            return web.json_response({'code': -1, 'msg': 'invalid json payload'}, status=400)

        user_text = str(params.get('text', '') or '').strip()
        if not user_text:
            return web.json_response({'code': -1, 'msg': 'text is required'}, status=400)

        raw_history = params.get('history', [])
        conversation_history: List[Dict[str, str]] = []
        if isinstance(raw_history, list):
            for item in raw_history[-10:]:
                if not isinstance(item, dict):
                    continue
                role = str(item.get('role', '') or '').strip()
                content = str(item.get('content', '') or '').strip()
                if role in {'user', 'assistant'} and content:
                    conversation_history.append({'role': role, 'content': content})

        rag_result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: retrieve_lightrag_context(
                user_text,
                hl_keywords=['心理陪伴', '共情回复', '风险识别', '干预边界'],
                ll_keywords=[user_text],
                conversation_history=conversation_history,
            ),
        )
        rag_context = str(rag_result.get('context', '') or '').strip()

        llm_result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: call_emollm_api(
                user_text=user_text,
                emotion_label='neutral',
                face_emotion='中性/平静',
                session_id='ai-conversation',
                user_name=str(params.get('user_name', '') or '').strip(),
                external_knowledge=rag_context,
            ),
        )
        answer = str(llm_result.get('text', '') or '').strip()
        return web.json_response({
            'code': 0,
            'msg': 'ok',
            'data': {
                'answer': str(answer or '').strip(),
                'lightrag': {
                    'status': rag_result.get('status'),
                    'contextLength': len(str(rag_result.get('context', '') or '')),
                    'references': rag_result.get('references', []),
                },
            },
        })
    except Exception as e:
        logger.exception('ai_conversation exception:')
        return web.json_response({'code': -1, 'msg': str(e)}, status=500)


async def lightrag_graph_labels(request):
    try:
        limit = _safe_int(request.query.get('limit', 80), 80)
        labels = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: get_graph_labels(limit),
        )
        return web.json_response({'code': 0, 'msg': 'ok', 'data': {'labels': labels}})
    except Exception as e:
        logger.exception('lightrag_graph_labels exception:')
        return web.json_response({'code': -1, 'msg': str(e)}, status=500)


async def lightrag_graph(request):
    try:
        label = str(request.query.get('label', '') or '').strip()
        if not label:
            return web.json_response({'code': -1, 'msg': 'label is required'}, status=400)
        max_depth = _safe_int(request.query.get('max_depth', 3), 3)
        max_nodes = _safe_int(request.query.get('max_nodes', 120), 120)
        graph = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: get_graph(label, max_depth=max_depth, max_nodes=max_nodes),
        )
        return web.json_response({'code': 0, 'msg': 'ok', 'data': graph})
    except Exception as e:
        logger.exception('lightrag_graph exception:')
        return web.json_response({'code': -1, 'msg': str(e)}, status=500)


async def lightrag_documents(request):
    try:
        if request.method.upper() == 'POST':
            params = await request.json()
            if not isinstance(params, dict):
                params = {}
        else:
            params = dict(request.query)
        page = _safe_int(params.get('page', 1), 1)
        page_size = _safe_int(params.get('page_size', 20), 20)
        status_filter = str(params.get('status_filter', '') or '').strip()
        sort_field = str(params.get('sort_field', 'updated_at') or 'updated_at').strip()
        sort_direction = str(params.get('sort_direction', 'desc') or 'desc').strip()
        docs = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: get_documents_paginated(
                page=page,
                page_size=page_size,
                status_filter=status_filter,
                sort_field=sort_field,
                sort_direction=sort_direction,
            ),
        )
        return web.json_response({'code': 0, 'msg': 'ok', 'data': docs})
    except Exception as e:
        logger.exception('lightrag_documents exception:')
        return web.json_response({'code': -1, 'msg': str(e)}, status=500)


async def lightrag_document_counts(request):
    try:
        counts = await asyncio.get_running_loop().run_in_executor(None, get_document_status_counts)
        return web.json_response({'code': 0, 'msg': 'ok', 'data': counts})
    except Exception as e:
        logger.exception('lightrag_document_counts exception:')
        return web.json_response({'code': -1, 'msg': str(e)}, status=500)


async def lightrag_pipeline_status(request):
    try:
        status = await asyncio.get_running_loop().run_in_executor(None, get_pipeline_status)
        return web.json_response({'code': 0, 'msg': 'ok', 'data': status})
    except Exception as e:
        logger.exception('lightrag_pipeline_status exception:')
        return web.json_response({'code': -1, 'msg': str(e)}, status=500)


async def lightrag_scan_documents(request):
    try:
        result = await asyncio.get_running_loop().run_in_executor(None, scan_lightrag_documents)
        return web.json_response({'code': 0, 'msg': 'ok', 'data': result})
    except Exception as e:
        logger.exception('lightrag_scan_documents exception:')
        return web.json_response({'code': -1, 'msg': str(e)}, status=500)


async def lightrag_upload_document(request):
    try:
        form = await request.post()
        fileobj = form.get('file')
        if fileobj is None or not hasattr(fileobj, 'file'):
            return web.json_response({'code': -1, 'msg': 'file is required'}, status=400)
        raw_filename = os.path.basename(str(getattr(fileobj, 'filename', '') or 'upload.txt'))
        filename = raw_filename.replace('\\', '_').replace('/', '_') or 'upload.txt'
        content_type = str(getattr(fileobj, 'content_type', '') or 'application/octet-stream')
        file_bytes = fileobj.file.read()
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: upload_lightrag_document(filename, file_bytes, content_type),
        )
        return web.json_response({'code': 0, 'msg': 'ok', 'data': result})
    except Exception as e:
        logger.exception('lightrag_upload_document exception:')
        return web.json_response({'code': -1, 'msg': str(e)}, status=500)


async def asr(request):
    sessionid = 0
    mode = 'chat'
    hint_text = ''
    audio_mime_type = ''
    filename = ''
    audio_bytes = b''
    try:
        form = await request.post()
        sessionid = _safe_int(form.get('sessionid', 0))
        mode = str(form.get('mode', 'chat')).strip() or 'chat'
        hint_text = str(form.get('browser_transcript_hint', '')).strip()
        audio_mime_type = str(form.get('audio_mime_type', '')).strip()

        fileobj = form.get('file')
        if fileobj is not None:
            filename = getattr(fileobj, 'filename', '')
            if hasattr(fileobj, 'file'):
                audio_bytes = fileobj.file.read()

        duration_s = round(_estimate_audio_duration_seconds(audio_bytes), 2)
        backend_name = str(getattr(asr_backend, 'name', 'none') or 'none')

        backend_payload: Dict[str, Any] = {}
        if asr_backend is not None and hasattr(asr_backend, 'transcribe'):
            loop = asyncio.get_running_loop()
            backend_payload = await loop.run_in_executor(
                None,
                lambda: _asr_result_to_payload(
                    asr_backend.transcribe(
                        audio_bytes=audio_bytes,
                        filename=filename,
                        hint_text=hint_text,
                        sessionid=sessionid,
                        mode=mode,
                    )
                ),
            )

        transcript = str(backend_payload.get('transcript', '') or '').strip()
        source = str(backend_payload.get('source', '') or '').strip()
        request_id = str(backend_payload.get('request_id', '') or '').strip()

        if not transcript and hint_text:
            transcript = hint_text
            source = source or 'browser_hint_fallback'

        if not transcript and duration_s <= 0.15:
            transcript = ''

        if not source:
            source = 'asr_empty'

        _append_chat_record_event(
            sessionid,
            'asr_upload_result',
            {
                'mode': _normalize_chat_mode(mode),
                'source': str(source),
                'backend': backend_name,
                'duration_s': float(duration_s),
                'filename': str(filename or ''),
                'audio_mime_type': str(audio_mime_type or ''),
                'transcript': transcript,
            },
        )
        _record_chat_text_if_needed(
            sessionid=sessionid,
            role='user',
            text=transcript,
            mode=mode,
            source='asr_upload',
        )

        response_payload: Dict[str, Any] = {
            'code': 0,
            'msg': 'ok',
            'transcript': transcript,
            'durationSec': duration_s,
            'mode': mode,
            'audio_mime_type': audio_mime_type,
            'source': source,
            'backend': backend_name,
        }
        if request_id:
            response_payload['request_id'] = request_id
        response_payload.update(_extract_emotion_payload(backend_payload))

        _append_chat_record_api_call(
            sessionid=sessionid,
            api_name='/asr',
            status='ok',
            mode=mode,
            source=source,
            duration_ms=int(duration_s * 1000),
            request_payload={
                'mode': mode,
                'filename': filename,
                'audio_mime_type': audio_mime_type,
                'audio_size_bytes': len(audio_bytes or b''),
                'browser_transcript_hint': hint_text,
                'backend': backend_name,
            },
            response_payload=response_payload,
        )

        return web.json_response(response_payload)
    except Exception as e:
        _append_chat_record_api_call(
            sessionid=sessionid,
            api_name='/asr',
            status='error',
            mode=mode,
            source='asr_upload',
            request_payload={
                'mode': mode,
                'filename': filename,
                'audio_mime_type': audio_mime_type,
                'audio_size_bytes': len(audio_bytes or b''),
                'browser_transcript_hint': hint_text,
            },
            error_message=str(e),
        )
        logger.exception('asr exception:')
        return web.json_response({'code': -1, 'msg': str(e)}, status=500)


def _format_seconds_as_mmss(seconds_value: float) -> str:
    total_seconds = max(0, int(round(_safe_float(seconds_value, 0.0))))
    minutes, seconds = divmod(total_seconds, 60)
    return f'{minutes:02d}:{seconds:02d}'


def _guess_image_mime_type(path: str) -> str:
    ext = os.path.splitext(str(path or ''))[1].lower()
    if ext == '.png':
        return 'image/png'
    if ext == '.webp':
        return 'image/webp'
    return 'image/jpeg'


def _image_bytes_to_data_url(image_bytes: bytes, mime_type: str = 'image/jpeg') -> str:
    if not image_bytes:
        return ''
    encoded = base64.b64encode(image_bytes).decode('ascii')
    return f'data:{mime_type};base64,{encoded}'


def _image_path_to_data_url(image_path: str) -> str:
    path = str(image_path or '').strip()
    if not path or (not os.path.exists(path)):
        return ''
    try:
        with open(path, 'rb') as fp:
            return _image_bytes_to_data_url(fp.read(), _guess_image_mime_type(path))
    except Exception:
        logger.exception('failed to encode image as data url: %s', path)
        return ''


def _is_negative_multimodal_emotion(label: str) -> bool:
    normalized = str(label or '').strip()
    if not normalized or normalized in {'未检测', '中性', '中性/平静', '平静', '积极'}:
        return False

    negative_tokens = ['悲伤', '愤怒', '恐惧', '厌恶', '消极', '焦虑', '担心', '害怕', '压抑', '烦躁', '沮丧', '紧张', '痛苦']
    return any(token in normalized for token in negative_tokens)


_MULTIMODAL_HIGH_RISK_RULES = [
    ('自伤或自杀意图', r'自杀|轻生|结束生命|结束自己的生命'),
    ('自伤行为', r'自残|割腕|伤害自己'),
    ('生存意愿显著下降', r'不想活了?|活着(?:也)?没(?:有)?意思'),
    ('伤害他人意图', r'(?:杀了|伤害|报复).{0,4}(?:别人|他人|家人|同学|同事)'),
    ('无法保证安全', r'无法保证.{0,6}(?:自己|他人).{0,4}安全'),
]

_MULTIMODAL_ATTENTION_RISK_RULES = [
    ('睡眠持续受扰', r'睡不着|睡不好|失眠|睡眠.{0,4}(?:受扰|很差|不好)'),
    ('绝望或无助', r'绝望|无助|撑不住|受不了'),
    ('明显焦虑或恐惧', r'焦虑|恐惧|害怕|持续低落|压抑'),
    ('情绪失控', r'情绪失控|控制不住.{0,3}情绪'),
    ('社交退缩', r'不想见人|不愿见人|社交退缩'),
    ('强烈自我否定', r'我没用|自己没用|一无是处|什么都做不好|工作也做不好'),
    ('日常功能下降', r'无法工作|不能工作|日常生活.{0,4}(?:受影响|做不了)'),
]


def _is_negated_risk_match(text: str, match_start: int) -> bool:
    prefix = str(text or '')[max(0, int(match_start) - 8):int(match_start)]
    return bool(re.search(r'(?:没有想过|没有|没想过|从未|未曾|不会|并不|否认|不打算|不准备|不想|不)\s*$', prefix))


def _match_multimodal_risk_rules(text: str, rules: List[Tuple[str, str]]) -> List[str]:
    normalized = str(text or '').strip()
    if not normalized:
        return []

    matched_labels: List[str] = []
    for label, pattern in rules:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            if _is_negated_risk_match(normalized, match.start()):
                continue
            matched_labels.append(label)
            break
    return matched_labels


def _build_multimodal_risk_assessment(
    *,
    analysis_text: str,
    face_emotion: str,
    audio_emotion: str,
    text_emotion: str,
) -> Dict[str, Any]:
    high_risk_matches = _match_multimodal_risk_rules(
        analysis_text,
        _MULTIMODAL_HIGH_RISK_RULES,
    )
    attention_matches = _match_multimodal_risk_rules(
        analysis_text,
        _MULTIMODAL_ATTENTION_RISK_RULES,
    )
    negative_modalities = [
        label
        for label, emotion in (
            ('面部', face_emotion),
            ('语音', audio_emotion),
            ('文本', text_emotion),
        )
        if _is_negative_multimodal_emotion(emotion)
    ]

    if high_risk_matches:
        return {
            'severity': 'high',
            'level': '高风险',
            'route': '高危安全路径',
            'description': '检测到需要优先处置的高危表达，系统将切换至安全支持与人工求助引导。',
            'attentionFlag': True,
            'highRiskFlag': True,
            'matchedSignals': high_risk_matches,
            'basis': [f'高危语义：{"、".join(high_risk_matches)}'],
        }

    if attention_matches or len(negative_modalities) >= 2:
        basis: List[str] = []
        if attention_matches:
            basis.append(f'风险关注语义：{"、".join(attention_matches)}')
        if negative_modalities:
            basis.append(f'负性情绪信号：{"、".join(negative_modalities)}（{len(negative_modalities)}/3）')
        return {
            'severity': 'attention',
            'level': '中风险',
            'route': '风险关注路径',
            'description': '检测到持续关注信号，建议采用倾听陪伴并继续观察后续情绪变化。',
            'attentionFlag': True,
            'highRiskFlag': False,
            'matchedSignals': attention_matches,
            'basis': basis,
        }

    basis = ['未命中风险关注或高危语义']
    if negative_modalities:
        basis.append(f'单项负性情绪信号：{"、".join(negative_modalities)}')
    return {
        'severity': 'low',
        'level': '低风险',
        'route': '常规陪护路径',
        'description': '当前未发现明显风险信号，可继续进行常规情绪支持与陪伴沟通。',
        'attentionFlag': False,
        'highRiskFlag': False,
        'matchedSignals': [],
        'basis': basis,
    }


def _summarize_detected_face_emotions(labels: List[str], fallback: str) -> str:
    valid_labels = [str(label or '').strip() for label in labels if str(label or '').strip() and str(label or '').strip() != '未检测']
    if not valid_labels:
        fallback_label = str(fallback or '').strip()
        return fallback_label or '未检测'

    counts: Dict[str, int] = {}
    last_indexes: Dict[str, int] = {}
    for idx, label in enumerate(valid_labels):
        counts[label] = counts.get(label, 0) + 1
        last_indexes[label] = idx

    best_label = valid_labels[-1]
    best_count = counts.get(best_label, 0)
    best_last_index = last_indexes.get(best_label, -1)

    for label, count in counts.items():
        last_index = last_indexes.get(label, -1)
        if count > best_count or (count == best_count and last_index > best_last_index):
            best_label = label
            best_count = count
            best_last_index = last_index

    return best_label


def _extract_json_object_from_text(text: str) -> Dict[str, Any]:
    normalized = str(text or '').strip()
    if not normalized:
        raise ValueError('empty emollm response text')

    candidates: List[str] = []
    fenced_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', normalized, flags=re.IGNORECASE)
    if fenced_match:
        candidates.append(str(fenced_match.group(1) or '').strip())

    if normalized.startswith('{') and normalized.endswith('}'):
        candidates.append(normalized)

    first_brace = normalized.find('{')
    last_brace = normalized.rfind('}')
    if first_brace >= 0 and last_brace > first_brace:
        candidates.append(normalized[first_brace:last_brace + 1].strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ValueError('emollm response does not contain valid JSON object')


def _normalize_multimodal_suggestions(value: Any) -> List[str]:
    if isinstance(value, list):
        suggestions = [str(item or '').strip() for item in value if str(item or '').strip()]
        if suggestions:
            return suggestions[:4]

    if isinstance(value, str):
        parts = re.split(r'[\n；;。]+', value)
        suggestions = [str(part or '').strip(' -•\t') for part in parts if str(part or '').strip(' -•\t')]
        if suggestions:
            return suggestions[:4]

    return []


def _normalize_multimodal_status(
    raw_status: Any,
    raw_status_text: Any,
    fallback_status: str,
    fallback_status_text: str,
) -> Tuple[str, str]:
    status_map = {
        'good': ('good', '心理状态良好'),
        'normal': ('normal', '状态正常'),
        'warning': ('warning', '需要关注'),
        '心理状态良好': ('good', '心理状态良好'),
        '状态正常': ('normal', '状态正常'),
        '需要关注': ('warning', '需要关注'),
    }

    normalized_status = str(raw_status or '').strip()
    if normalized_status in status_map:
        status_value, default_text = status_map[normalized_status]
        resolved_text = str(raw_status_text or '').strip() or default_text
        return status_value, resolved_text

    normalized_status_lower = normalized_status.lower()
    if normalized_status_lower in status_map:
        status_value, default_text = status_map[normalized_status_lower]
        resolved_text = str(raw_status_text or '').strip() or default_text
        return status_value, resolved_text

    normalized_status_text = str(raw_status_text or '').strip()
    if normalized_status_text in status_map:
        status_value, default_text = status_map[normalized_status_text]
        return status_value, normalized_status_text or default_text

    return fallback_status, fallback_status_text


def _env_truthy(name: str, default: str = '0') -> bool:
    raw = str(os.getenv(name, default) or default).strip().lower()
    return raw in {'1', 'true', 'yes', 'on'}


def _build_multimodal_observations(
    *, manual_text: str, audio_transcript: str, face_emotion: str,
    audio_emotion: str, video_frames: List[Dict[str, Any]],
) -> Dict[str, Any]:
    # 输入记录不包含推断结论；报告内容只来自实际模型响应。
    return {
        'textContent': str(manual_text or '').strip() or None,
        'audioTranscript': str(audio_transcript or '').strip() or None,
        'faceEmotion': str(face_emotion or '未检测').strip() or '未检测',
        'audioEmotion': str(audio_emotion or '未检测').strip() or '未检测',
        'videoFrames': video_frames,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
    }


def _build_multimodal_emollm_prompt(
    *,
    manual_text: str,
    audio_transcript: str,
    face_emotion: str,
    audio_emotion: str,
    rag_context: str = '',
) -> str:
    text_content = str(manual_text or '').strip() or '无'
    transcript = str(audio_transcript or '').strip() or '无'
    resolved_audio_emotion = str(audio_emotion or '').strip() or '未检测'
    resolved_face_emotion = str(face_emotion or '').strip() or '未检测'
    resolved_rag_context = str(rag_context or '').strip() or '无'

    return (
        '你是一个多模态心理状态分析助手。'
        '请根据用户主动输入文本、音频转写文本、语音情绪和面部情绪，输出严格 JSON，不要 markdown，不要额外解释。'
        'JSON 格式必须为：'
        '{"textEmotion":"积极|消极|复杂|中性|未检测",'
        '"overallStatus":"good|normal|warning",'
        '"overallStatusText":"心理状态良好|状态正常|需要关注",'
        '"description":"一句中文分析结论",'
        '"suggestions":["建议1","建议2","建议3"]}'
        '要求：'
        '1. textEmotion 只根据文本内容和音频转写体现的情绪来判断；'
        '2. overallStatus 需要综合文本、语音情绪和面部情绪；'
        '3. description 使用 40 到 80 字中文；'
        '4. suggestions 返回 3 到 4 条简短中文建议；'
        '5. 必须优先参考知识库上下文，但不要照搬上下文，不要编造医学诊断。'
        f'知识库上下文：{resolved_rag_context}。'
        f'用户主动输入：{text_content}。'
        f'音频转写：{transcript}。'
        f'语音情绪：{resolved_audio_emotion}。'
        f'面部情绪：{resolved_face_emotion}。'
    )


def _merge_multimodal_llm_payload(
    *,
    llm_payload: Dict[str, Any],
    observations_payload: Dict[str, Any],
    report_source: str,
) -> Dict[str, Any]:
    resolved_text_emotion = str(llm_payload.get('textEmotion') or llm_payload.get('text_emotion') or '').strip()
    if resolved_text_emotion not in {'积极', '消极', '复杂', '中性', '未检测'}:
        raise ValueError('模型报告缺少有效的文本情绪字段')

    resolved_status, resolved_status_text = _normalize_multimodal_status(
        llm_payload.get('overallStatus') or llm_payload.get('overall_status') or llm_payload.get('status'),
        llm_payload.get('overallStatusText') or llm_payload.get('overall_status_text') or llm_payload.get('statusText'),
        '',
        '',
    )
    if not resolved_status:
        raise ValueError('模型报告缺少有效的综合状态字段')
    resolved_description = str(
        llm_payload.get('description')
        or llm_payload.get('summary')
        or ''
    ).strip()
    if not resolved_description:
        raise ValueError('模型报告缺少分析结论')
    resolved_suggestions = _normalize_multimodal_suggestions(llm_payload.get('suggestions'))
    if not resolved_suggestions:
        raise ValueError('模型报告缺少有效的建议内容')

    result_payload = dict(observations_payload)
    result_payload.update({
        'textEmotion': resolved_text_emotion,
        'overallStatus': resolved_status,
        'overallStatusText': resolved_status_text,
        'description': resolved_description,
        'suggestions': resolved_suggestions,
        'reportSource': report_source,
    })
    return result_payload


async def _build_multimodal_summary(
    *,
    manual_text: str,
    audio_transcript: str,
    face_emotion: str,
    audio_emotion: str,
    video_frames: List[Dict[str, Any]],
    sessionid: int,
    user_name: str = '',
) -> Dict[str, Any]:
    observations_payload = _build_multimodal_observations(
        manual_text=manual_text,
        audio_transcript=audio_transcript,
        face_emotion=face_emotion,
        audio_emotion=audio_emotion,
        video_frames=video_frames,
    )
    rag_query = (
        '请检索情感陪护虚拟数字人系统中与多模态心理状态分析相关的知识，'
        '重点关注情绪识别、风险判断、干预建议、数字人陪伴边界和安全提示。\n'
        f'用户主动输入：{str(manual_text or "").strip() or "无"}\n'
        f'音频转写：{str(audio_transcript or "").strip() or "无"}\n'
        f'语音情绪：{str(audio_emotion or "").strip() or "未检测"}\n'
        f'面部情绪：{str(face_emotion or "").strip() or "未检测"}'
    )
    rag_result = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: retrieve_lightrag_context(
            rag_query,
            hl_keywords=['多模态心理状态分析', '情绪识别', '心理干预', '数字人陪伴'],
            ll_keywords=[
                str(manual_text or '').strip(),
                str(audio_transcript or '').strip(),
                str(audio_emotion or '').strip(),
                str(face_emotion or '').strip(),
            ],
        ),
    )
    rag_context = str(rag_result.get('context', '') or '').strip()

    try:
        llm_prompt = _build_multimodal_emollm_prompt(
            manual_text=manual_text,
            audio_transcript=audio_transcript,
            face_emotion=face_emotion,
            audio_emotion=audio_emotion,
        )
        llm_session_id = f'multimodal-analysis-{sessionid or int(time.time() * 1000)}'
        llm_result = call_emollm_api(
            user_text=llm_prompt,
            emotion_label=(str(audio_emotion or '').strip() or 'neutral') if str(audio_emotion or '').strip() != '未检测' else 'neutral',
            face_emotion=(str(face_emotion or '').strip() or '中性/平静') if str(face_emotion or '').strip() != '未检测' else '中性/平静',
            session_id=llm_session_id,
            user_name=user_name,
            external_knowledge=rag_context,
            memory_update=False,
        )
        llm_text = str(llm_result.get('text', '') or '').strip()
        llm_payload = _extract_json_object_from_text(llm_text)
        payload = _merge_multimodal_llm_payload(
            llm_payload=llm_payload,
            observations_payload=observations_payload,
            report_source='emollm',
        )
        payload['lightrag'] = {
            'status': rag_result.get('status'),
            'contextLength': len(rag_context),
            'references': rag_result.get('references', []),
        }
        return payload
    except Exception:
        logger.exception('failed to build multimodal summary via emollm')
        raise


def _analyze_uploaded_audio_for_multimodal(
    *,
    audio_bytes: bytes,
    filename: str,
    sessionid: int,
) -> Dict[str, Any]:
    if not audio_bytes:
        return {
            'audioEmotion': '未检测',
            'audioTranscript': '',
            'audioSource': '',
        }

    backend_payload: Dict[str, Any] = {}
    if asr_backend is not None and hasattr(asr_backend, 'transcribe'):
        backend_payload = _asr_result_to_payload(
            asr_backend.transcribe(
                audio_bytes=audio_bytes,
                filename=str(filename or 'analysis_upload.wav'),
                hint_text='',
                sessionid=sessionid,
                mode='multimodal_analysis',
            )
        )

    emotion_payload = _extract_emotion_payload(backend_payload)
    transcript = str(backend_payload.get('transcript', '') or '').strip()
    audio_emotion = str(emotion_payload.get('emotion_label', '') or '').strip() or '未检测'

    return {
        'audioEmotion': audio_emotion,
        'audioTranscript': transcript,
        'audioSource': str(backend_payload.get('source', '') or '').strip(),
        'audioMeta': emotion_payload.get('emotion_extra', None),
    }


def _analyze_saved_image_paths_for_multimodal(
    *,
    image_paths: List[str],
    fallback_emotion: str,
    time_label_builder: Optional[Callable[[str, int], str]] = None,
    force_deepface: bool = False,
) -> Dict[str, Any]:
    frames: List[Dict[str, Any]] = []
    detected_labels: List[str] = []
    should_call_deepface = force_deepface or _is_deepface_enabled()
    face_analysis_status = 'disabled' if not should_call_deepface else 'no_frames'
    face_analysis_message = 'DeepFace 人脸分析未启用' if not should_call_deepface else '未能获取可分析的视频关键帧'

    for index, image_path in enumerate(image_paths):
        path = str(image_path or '').strip()
        if (not path) or (not os.path.exists(path)):
            continue

        data_url = _image_path_to_data_url(path)
        if not data_url:
            continue

        emotion = str(fallback_emotion or '').strip() or '未检测'
        if should_call_deepface:
            try:
                deepface_result = call_deepface_api_with_status(path, force=force_deepface)
                detected = str(deepface_result.get('emotion', '') or '').strip()
                status = str(deepface_result.get('status', '') or '').strip() or 'unknown'
                message = str(deepface_result.get('message', '') or '').strip()
                if detected:
                    emotion = detected
                    face_analysis_status = 'detected'
                    face_analysis_message = ''
                elif face_analysis_status != 'detected':
                    face_analysis_status = status
                    if message:
                        face_analysis_message = message
            except Exception:
                if face_analysis_status != 'detected':
                    face_analysis_status = 'unexpected_error'
                    face_analysis_message = 'DeepFace 分析关键帧时发生异常'
                logger.exception('failed to analyze saved frame with deepface: %s', path)

        detected_labels.append(emotion)
        if callable(time_label_builder):
            time_label = str(time_label_builder(path, index) or '').strip()
        else:
            time_label = time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(path)))

        frames.append({
            'url': data_url,
            'time': time_label or f'帧{index + 1}',
            'emotion': emotion or '未检测',
        })

    face_emotion = _summarize_detected_face_emotions(detected_labels, fallback_emotion)
    if should_call_deepface and frames and face_analysis_status != 'detected' and not face_analysis_message:
        face_analysis_status = 'no_face'
        face_analysis_message = '关键帧中未识别到可用面部情绪'
    return {
        'faceEmotion': face_emotion,
        'videoFrames': frames,
        'faceAnalysisStatus': face_analysis_status,
        'faceAnalysisMessage': face_analysis_message,
    }


def _analyze_uploaded_video_for_multimodal(
    *,
    video_bytes: bytes,
    filename: str,
) -> Dict[str, Any]:
    result = {
        'faceEmotion': '未检测',
        'videoFrames': [],
        'faceAnalysisStatus': 'no_video',
        'faceAnalysisMessage': '未上传视频文件',
    }
    if not video_bytes:
        return result

    cv2_mod = _get_cv2_module()
    if cv2_mod is None:
        result['faceAnalysisStatus'] = 'missing_cv2'
        result['faceAnalysisMessage'] = '当前环境缺少 OpenCV，无法抽取视频关键帧'
        return result

    safe_name = _sanitize_filename_fragment(os.path.splitext(str(filename or 'upload'))[0], 'upload')
    suffix = os.path.splitext(str(filename or ''))[1].lower()
    if not re.fullmatch(r'\.[a-z0-9]{1,10}', suffix or ''):
        suffix = '.mp4'

    try:
        with tempfile.TemporaryDirectory(prefix='multimodal_video_') as temp_dir:
            video_path = os.path.join(temp_dir, f'{safe_name}{suffix}')
            with open(video_path, 'wb') as fp:
                fp.write(video_bytes)

            capture = cv2_mod.VideoCapture(video_path)
            if not capture.isOpened():
                result['faceAnalysisStatus'] = 'invalid_video'
                result['faceAnalysisMessage'] = '上传视频无法打开或格式不受支持'
                return result

            try:
                total_frames = max(0, int(capture.get(cv2_mod.CAP_PROP_FRAME_COUNT) or 0))
                fps = _safe_float(capture.get(cv2_mod.CAP_PROP_FPS) or 0.0, 0.0)
                if fps <= 0:
                    fps = 25.0

                sample_count = 4
                if total_frames > 1:
                    if total_frames <= sample_count:
                        sample_indexes = list(range(total_frames))
                    else:
                        points = np.linspace(0, total_frames - 1, num=sample_count + 2)[1:-1]
                        sample_indexes = sorted(set(int(point) for point in points))
                else:
                    sample_indexes = [0]

                frame_paths: List[str] = []
                time_labels: Dict[str, str] = {}

                for index, frame_index in enumerate(sample_indexes):
                    capture.set(cv2_mod.CAP_PROP_POS_FRAMES, int(frame_index))
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        continue

                    frame_path = os.path.join(temp_dir, f'frame_{index:02d}.jpg')
                    try:
                        write_ok = cv2_mod.imwrite(frame_path, frame, [int(cv2_mod.IMWRITE_JPEG_QUALITY), 90])
                    except Exception:
                        write_ok = False
                    if not write_ok or (not os.path.exists(frame_path)):
                        continue

                    frame_paths.append(frame_path)
                    time_labels[frame_path] = _format_seconds_as_mmss(float(frame_index) / fps)

                analyzed = _analyze_saved_image_paths_for_multimodal(
                    image_paths=frame_paths,
                    fallback_emotion='未检测',
                    time_label_builder=lambda path, _index: time_labels.get(path, f'帧{_index + 1}'),
                    force_deepface=True,
                )
                result['faceEmotion'] = analyzed.get('faceEmotion', '未检测')
                result['videoFrames'] = analyzed.get('videoFrames', [])
                result['faceAnalysisStatus'] = analyzed.get('faceAnalysisStatus', 'no_frames')
                result['faceAnalysisMessage'] = analyzed.get('faceAnalysisMessage', '')
            finally:
                capture.release()
    except Exception:
        logger.exception('failed to analyze uploaded video for multimodal analysis')
        result['faceAnalysisStatus'] = 'unexpected_error'
        result['faceAnalysisMessage'] = '上传视频抽帧分析失败'

    return result


async def multimodal_analysis(request):
    sessionid = 0
    manual_text = ''
    audio_bytes = b''
    audio_filename = ''
    video_bytes = b''
    video_filename = ''
    user_name = ''
    try:
        content_type = str(request.content_type or '').lower()
        if 'application/json' in content_type:
            params = await request.json()
            if not isinstance(params, dict):
                return web.json_response({'code': -1, 'msg': 'invalid json payload'}, status=400)
            sessionid = _safe_int(params.get('sessionid', 0), 0)
            manual_text = str(params.get('text', '') or '').strip()
            user_name = str(params.get('user_name', '') or '').strip()
        else:
            form = await request.post()
            sessionid = _safe_int(form.get('sessionid', 0), 0)
            manual_text = str(form.get('text', '') or '').strip()
            user_name = str(form.get('user_name', '') or '').strip()

            audio_field = form.get('audio_file')
            if audio_field is not None and hasattr(audio_field, 'file'):
                audio_filename = str(getattr(audio_field, 'filename', '') or '').strip()
                audio_bytes = audio_field.file.read()

            video_field = form.get('video_file')
            if video_field is not None and hasattr(video_field, 'file'):
                video_filename = str(getattr(video_field, 'filename', '') or '').strip()
                video_bytes = video_field.file.read()

        if sessionid <= 0 and (not manual_text) and (not audio_bytes) and (not video_bytes):
            return web.json_response({'code': -1, 'msg': 'no multimodal input provided'}, status=400)

        face_emotion = '未检测'
        video_frames: List[Dict[str, Any]] = []
        face_analysis_status = ''
        face_analysis_message = ''
        audio_emotion = '未检测'
        audio_transcript = ''

        loop = asyncio.get_running_loop()

        if video_bytes:
            video_result = await loop.run_in_executor(
                None,
                lambda: _analyze_uploaded_video_for_multimodal(
                    video_bytes=video_bytes,
                    filename=video_filename,
                ),
            )
            face_emotion = str(video_result.get('faceEmotion', '未检测') or '未检测').strip() or '未检测'
            video_frames = list(video_result.get('videoFrames', []) or [])
            face_analysis_status = str(video_result.get('faceAnalysisStatus', '') or '').strip()
            face_analysis_message = str(video_result.get('faceAnalysisMessage', '') or '').strip()
        elif sessionid > 0:
            fallback_face = '未检测'
            with face_emotion_cache_lock:
                face_cache = face_emotion_cache.get(sessionid)
            if face_cache:
                fallback_face = str(face_cache.get('emotion', '未检测') or '未检测').strip() or '未检测'

            face_emotion = fallback_face

        if audio_bytes:
            audio_result = await loop.run_in_executor(
                None,
                lambda: _analyze_uploaded_audio_for_multimodal(
                    audio_bytes=audio_bytes,
                    filename=audio_filename,
                    sessionid=sessionid,
                ),
            )
            audio_emotion = str(audio_result.get('audioEmotion', '未检测') or '未检测').strip() or '未检测'
            audio_transcript = str(audio_result.get('audioTranscript', '') or '').strip()
        elif sessionid > 0:
            with webrtc_media_lock:
                state = webrtc_media_states.get(sessionid) or {}
                last_asr = state.get('last_asr') or {}

            if isinstance(last_asr, dict):
                audio_transcript = str(last_asr.get('transcript', '') or '').strip()
                if str(last_asr.get('status', '') or '').strip().lower() == 'final':
                    audio_emotion = str(last_asr.get('emotion_label', '') or '').strip() or '未检测'

        analysis_payload = await _build_multimodal_summary(
            manual_text=manual_text,
            audio_transcript=audio_transcript,
            face_emotion=face_emotion,
            audio_emotion=audio_emotion,
            video_frames=video_frames,
            sessionid=sessionid,
            user_name=user_name,
        )
        analysis_payload['sessionid'] = sessionid
        analysis_payload['faceAnalysisStatus'] = face_analysis_status
        analysis_payload['faceAnalysisMessage'] = face_analysis_message
        analysis_payload['riskAssessment'] = _build_multimodal_risk_assessment(
            analysis_text=manual_text or audio_transcript,
            face_emotion=analysis_payload.get('faceEmotion', face_emotion),
            audio_emotion=analysis_payload.get('audioEmotion', audio_emotion),
            text_emotion=analysis_payload.get('textEmotion', ''),
        )

        logger.info(
            'multimodal_analysis finished: sessionid=%s text=%s audio_upload=%s video_upload=%s face=%s audio=%s text_emotion=%s risk=%s',
            sessionid,
            bool(manual_text),
            bool(audio_bytes),
            bool(video_bytes),
            analysis_payload.get('faceEmotion', ''),
            analysis_payload.get('audioEmotion', ''),
            analysis_payload.get('textEmotion', ''),
            analysis_payload.get('riskAssessment', {}).get('severity', ''),
        )

        return web.json_response({'code': 0, 'msg': 'ok', 'data': analysis_payload})
    except Exception as e:
        logger.exception('multimodal_analysis exception:')
        return web.json_response({'code': -1, 'msg': str(e)}, status=500)


async def webrtc_media_state(request):
    sessionid_raw = request.query.get('sessionid', '0')
    sessionid = _safe_int(sessionid_raw, 0)
    if sessionid <= 0:
        return web.json_response({"code": -1, "msg": "invalid sessionid"}, status=400)

    with webrtc_media_lock:
        state = webrtc_media_states.get(sessionid)
        if state is None:
            snapshot = _build_default_webrtc_media_state(sessionid)
        else:
            snapshot = json.loads(json.dumps(state, ensure_ascii=False))
    
    # 🆕 2.4 确保 last_asr.emotion_label 字段存在并记录调试日志
    if snapshot.get('last_asr'):
        last_asr = snapshot['last_asr']
        if 'emotion_label' not in last_asr:
            last_asr['emotion_label'] = ''
            logger.debug(
                "[MediaState API] Missing emotion_label in last_asr, sessionid=%d, added empty string",
                sessionid,
            )
        
        # 记录 API 返回的 last_asr 内容（仅在有情绪标签时记录）
        if last_asr.get('emotion_label'):
            logger.debug(
                "[MediaState API] sessionid=%d, last_asr_status=%s, emotion_label='%s', transcript='%s'",
                sessionid,
                last_asr.get('status', ''),
                last_asr.get('emotion_label', ''),
                (last_asr.get('transcript', '')[:30] if last_asr.get('transcript') else ''),
            )
    
    # 🆕 添加人脸情绪信息到返回数据中
    if _is_deepface_enabled():
        with face_emotion_cache_lock:
            face_cache = face_emotion_cache.get(sessionid)
        
        # 🆕 2.4 记录人脸情绪缓存调试日志
        if face_cache:
            logger.debug(
                "[MediaState API] sessionid=%d, face_cache emotion='%s', timestamp_ms=%d, frame_index=%d",
                sessionid,
                face_cache.get('emotion', ''),
                face_cache.get('timestamp_ms', 0),
                face_cache.get('frame_index', 0),
            )
        
        if face_cache:
            current_time_ms = int(time.time() * 1000)
            timestamp_ms = _safe_int(face_cache.get('timestamp_ms', 0), 0)
            age_ms = current_time_ms - timestamp_ms if timestamp_ms > 0 else 0
            
            # 🆕 4.5 实现缓存过期警告
            cache_max_age_ms = _get_deepface_cache_max_age_ms()
            if age_ms > cache_max_age_ms:
                logger.warning(
                    '[MediaState API] Stale face emotion: sessionid=%d, age_ms=%d, max_age_ms=%d, emotion=%s',
                    sessionid,
                    age_ms,
                    cache_max_age_ms,
                    face_cache.get('emotion', '')
                )
            
            snapshot['face_emotion'] = {
                'emotion': str(face_cache.get('emotion', '中性/平静') or '中性/平静'),
                'timestamp_ms': timestamp_ms,
                'frame_index': _safe_int(face_cache.get('frame_index', 0), 0),
                'age_ms': age_ms,
            }
        else:
            snapshot['face_emotion'] = {
                'emotion': '中性/平静',
                'timestamp_ms': 0,
                'frame_index': 0,
                'age_ms': 0,
            }

    return web.json_response({"code": 0, "msg": "ok", "data": snapshot})


async def webrtc_asr_control(request):
    sessionid = 0
    action = ''
    mode = 'chat'
    hint_text = ''
    try:
        params = await request.json()
        if not isinstance(params, dict):
            params = {}

        sessionid = _safe_int(params.get('sessionid', 0), 0)
        action = str(params.get('action', '') or '').strip().lower()
        mode = str(params.get('mode', 'chat') or 'chat').strip() or 'chat'
        hint_text = str(params.get('browser_transcript_hint', '') or '').strip()

        if sessionid <= 0:
            return web.json_response({"code": -1, "msg": "invalid sessionid"}, status=400)

        if action == 'start':
            # start 仅做“开启新段 + 清空缓存”，不触发即时转写。
            with webrtc_media_lock:
                state = webrtc_media_states.get(sessionid)
                if state is None:
                    state = _build_default_webrtc_media_state(sessionid)
                    webrtc_media_states[sessionid] = state

                runtime = webrtc_asr_runtime.get(sessionid)
                if runtime is None:
                    runtime = _build_default_webrtc_asr_runtime()
                    webrtc_asr_runtime[sessionid] = runtime

                runtime['recording'] = True
                runtime['mode'] = mode
                runtime['utterance_id'] = int(runtime.get('utterance_id', 0)) + 1
                runtime['pcm16_buffer'] = bytearray()
                runtime['partial_inflight'] = False
                runtime['last_partial_request_ms'] = 0
                runtime['last_partial_transcript'] = ''
                runtime['speech_frame_count'] = 0
                runtime['total_frame_count'] = 0
                runtime['max_audio_level'] = 0.0
                runtime['dropped_avatar_frames'] = 0

                utterance_id = int(runtime['utterance_id'])
                backend_name = str(getattr(asr_backend, 'name', 'none') or 'none')
                state['last_asr'] = _build_webrtc_asr_state_payload(
                    transcript='',
                    source='webrtc_stream',
                    backend=backend_name,
                    mode=mode,
                    status='recording',
                    utterance_id=utterance_id,
                    duration_s=0.0,
                )
                state['updated_at_ms'] = int(time.time() * 1000)

            _append_chat_record_event(
                sessionid,
                'asr_segment_start',
                {
                    'mode': _normalize_chat_mode(mode),
                    'source': 'webrtc_asr',
                    'utterance_id': int(utterance_id),
                },
            )

            start_payload = {
                "code": 0,
                "msg": "ok",
                "sessionid": sessionid,
                "status": "recording",
                "utterance_id": utterance_id,
            }
            _append_chat_record_api_call(
                sessionid=sessionid,
                api_name='/webrtc_asr_control',
                status='ok',
                mode=mode,
                source='webrtc_asr',
                request_payload={
                    'action': 'start',
                    'mode': mode,
                    'browser_transcript_hint': hint_text,
                },
                response_payload=start_payload,
            )

            return web.json_response(start_payload)

        if action == 'stop':
            # stop 会冻结当前缓存并执行一次 final ASR，得到段级最终文本。
            with webrtc_media_lock:
                state = webrtc_media_states.get(sessionid)
                if state is None:
                    state = _build_default_webrtc_media_state(sessionid)
                    webrtc_media_states[sessionid] = state

                runtime = webrtc_asr_runtime.get(sessionid)
                if runtime is None:
                    runtime = _build_default_webrtc_asr_runtime()
                    webrtc_asr_runtime[sessionid] = runtime

                runtime['recording'] = False
                runtime['partial_inflight'] = False
                utterance_id = int(runtime.get('utterance_id', 0))
                runtime_mode = str(runtime.get('mode', mode) or mode)
                pcm_snapshot = bytes(runtime.get('pcm16_buffer', bytearray()))
                speech_frame_count = _safe_int(runtime.get('speech_frame_count', 0), 0)
                total_frame_count = _safe_int(runtime.get('total_frame_count', 0), 0)
                max_audio_level = _safe_float(runtime.get('max_audio_level', 0.0), 0.0)
                dropped_avatar_frames = _safe_int(runtime.get('dropped_avatar_frames', 0), 0)
                runtime['pcm16_buffer'] = bytearray()
                runtime['speech_frame_count'] = 0
                runtime['total_frame_count'] = 0
                runtime['max_audio_level'] = 0.0
                runtime['dropped_avatar_frames'] = 0

                _, backend_name = _resolve_active_webrtc_asr_backend('final')
                state['last_asr'] = _build_webrtc_asr_state_payload(
                    transcript='',
                    source='webrtc_stream',
                    backend=backend_name,
                    mode=runtime_mode,
                    status='processing',
                    utterance_id=utterance_id,
                    duration_s=(float(len(pcm_snapshot)) / 32000.0),
                )
                state['updated_at_ms'] = int(time.time() * 1000)

            loop = asyncio.get_running_loop()
            strict_final_backend = bool(getattr(opt, 'WEBRTC_FINAL_ASR_STRICT_FAILURE', False))
            final_call_started = time.perf_counter()
            try:
                payload = await loop.run_in_executor(
                    None,
                    lambda: _transcribe_webrtc_pcm_bytes(
                        sessionid=sessionid,
                        pcm16_bytes=pcm_snapshot,
                        mode=runtime_mode,
                        hint_text=hint_text,
                        backend_role='final',
                        strict_backend=strict_final_backend,
                        speech_frame_count=speech_frame_count,
                        total_frame_count=total_frame_count,
                        max_audio_level=max_audio_level,
                        dropped_avatar_frames=dropped_avatar_frames,
                    ),
                )
            except Exception as exc:
                _, failed_backend_name = _resolve_active_webrtc_asr_backend('final')
                with webrtc_media_lock:
                    state = webrtc_media_states.get(sessionid)
                    if state is None:
                        state = _build_default_webrtc_media_state(sessionid)
                        webrtc_media_states[sessionid] = state
                    state['last_asr'] = _build_webrtc_asr_state_payload(
                        transcript='',
                        source='webrtc_final_asr_error',
                        backend=failed_backend_name,
                        mode=runtime_mode,
                        status='error',
                        utterance_id=utterance_id,
                        duration_s=(float(len(pcm_snapshot)) / 32000.0),
                        extra_fields={'error_message': str(exc)},
                    )
                    state['updated_at_ms'] = int(time.time() * 1000)

                if strict_final_backend:
                    failed_payload = {
                        'code': -2,
                        'msg': f'final asr failed: {str(exc)}',
                        'sessionid': sessionid,
                        'status': 'error',
                        'mode': runtime_mode,
                        'backend': failed_backend_name,
                    }
                    _append_chat_record_api_call(
                        sessionid=sessionid,
                        api_name='/webrtc_asr_control',
                        status='error',
                        mode=runtime_mode,
                        source='webrtc_asr',
                        duration_ms=int((time.perf_counter() - final_call_started) * 1000),
                        request_payload={
                            'action': 'stop',
                            'mode': runtime_mode,
                            'pcm_size_bytes': len(pcm_snapshot or b''),
                            'browser_transcript_hint': hint_text,
                            'strict_final_backend': bool(strict_final_backend),
                        },
                        response_payload=failed_payload,
                        error_message=str(exc),
                    )
                    return web.json_response(
                        failed_payload,
                        status=502,
                    )
                payload = {
                    'transcript': hint_text,
                    'source': 'browser_hint_fallback',
                    'backend': failed_backend_name,
                    'duration_s': float(len(pcm_snapshot)) / 32000.0,
                }

            transcript = str(payload.get('transcript', '') or '').strip()
            source = str(payload.get('source', '') or '').strip() or 'asr_empty'
            backend_name = str(payload.get('backend', '') or str(getattr(asr_backend, 'name', 'none') or 'none'))
            request_id = str(payload.get('request_id', '') or '').strip()
            duration_s = float(payload.get('duration_s', 0.0) or 0.0)
            emotion_payload = _extract_emotion_payload(payload)
            
            # 🆕 2.2 记录 final 状态的情绪标签提取
            if emotion_payload.get('emotion_label'):
                logger.info(
                    "[ASR Emotion Final] sessionid=%d, emotion_label='%s', transcript='%s'",
                    sessionid,
                    emotion_payload.get('emotion_label', ''),
                    transcript[:50] if len(transcript) > 50 else transcript,
                )
            
            cloud_verify_payload = _extract_cloud_verify_payload(payload)
            chat_record_audio_path = _save_chat_record_pcm_wav_if_needed(
                sessionid=sessionid,
                mode=runtime_mode,
                source='webrtc_asr',
                pcm16_bytes=pcm_snapshot,
                transcript=transcript,
            )

            with webrtc_media_lock:
                runtime = webrtc_asr_runtime.get(sessionid)
                if runtime is not None and int(runtime.get('utterance_id', 0)) == utterance_id:
                    runtime['last_partial_transcript'] = transcript

                state = webrtc_media_states.get(sessionid)
                if state is None:
                    state = _build_default_webrtc_media_state(sessionid)
                    webrtc_media_states[sessionid] = state

                state['last_asr'] = _build_webrtc_asr_state_payload(
                    transcript=transcript,
                    source=source,
                    backend=backend_name,
                    mode=runtime_mode,
                    status='final',
                    utterance_id=utterance_id,
                    duration_s=duration_s,
                    request_id=request_id,
                    extra_fields={
                        **emotion_payload,
                        **cloud_verify_payload,
                    },
                )
                state['updated_at_ms'] = int(time.time() * 1000)

            _append_chat_record_event(
                sessionid,
                'asr_segment_final',
                {
                    'mode': _normalize_chat_mode(runtime_mode),
                    'source': 'webrtc_asr',
                    'status': 'final',
                    'utterance_id': int(utterance_id),
                    'duration_s': round(duration_s, 3),
                    'transcript': transcript,
                    'backend': backend_name,
                    'provider_source': source,
                    'chat_record_audio_path': chat_record_audio_path,
                    **emotion_payload,
                    **cloud_verify_payload,
                },
            )

            response_payload: Dict[str, Any] = {
                "code": 0,
                "msg": "ok",
                "sessionid": sessionid,
                "status": "final",
                "mode": runtime_mode,
                "transcript": transcript,
                "source": source,
                "backend": backend_name,
                "duration_s": round(duration_s, 3),
            }
            response_payload.update(emotion_payload)
            response_payload.update(cloud_verify_payload)
            if request_id:
                response_payload['request_id'] = request_id
            if chat_record_audio_path:
                response_payload['chat_record_audio_path'] = chat_record_audio_path

            _append_chat_record_api_call(
                sessionid=sessionid,
                api_name='/webrtc_asr_control',
                status='ok',
                mode=runtime_mode,
                source='webrtc_asr',
                duration_ms=int((time.perf_counter() - final_call_started) * 1000),
                request_payload={
                    'action': 'stop',
                    'mode': runtime_mode,
                    'pcm_size_bytes': len(pcm_snapshot or b''),
                    'browser_transcript_hint': hint_text,
                    'speech_frame_count': int(speech_frame_count),
                    'total_frame_count': int(total_frame_count),
                    'max_audio_level': float(max_audio_level),
                    'dropped_avatar_frames': int(dropped_avatar_frames),
                },
                response_payload=response_payload,
            )
            return web.json_response(response_payload)

        return web.json_response({"code": -1, "msg": "invalid action"}, status=400)
    except Exception as e:
        _append_chat_record_api_call(
            sessionid=sessionid,
            api_name='/webrtc_asr_control',
            status='error',
            mode=mode,
            source='webrtc_asr',
            request_payload={
                'action': action,
                'mode': mode,
                'browser_transcript_hint': hint_text,
            },
            error_message=str(e),
        )
        logger.exception('webrtc_asr_control exception:')
        return web.json_response({"code": -1, "msg": str(e)}, status=500)


###########################################################################################
# 音色、形象配置和离线数字人生成 API 已迁移到 voice_api.py。
###########################################################################################

async def on_shutdown(app):
    # 关闭所有 peer connection，并清理会话级状态与后台任务。
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()
    session_peer_connections.clear()

    with webrtc_media_lock:
        session_ids = list(webrtc_media_states.keys())
    for sid in session_ids:
        _append_chat_record_event(
            sid,
            'session_shutdown',
            {
                'reason': 'server_shutdown',
            },
        )
        _cleanup_webrtc_media_session(sid)

    with chat_record_lock:
        chat_record_runtime.clear()


async def periodic_memory_cleanup():
    """定期清理过期会话和内存，防止内存泄漏"""
    SESSION_TIMEOUT_SECONDS = 3600  # 1小时无活动则清理
    CLEANUP_INTERVAL_SECONDS = 300  # 每5分钟检查一次
    
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            now_ms = int(time.time() * 1000)
            timeout_ms = SESSION_TIMEOUT_SECONDS * 1000
            
            # 清理过期的 webrtc_media_states
            with webrtc_media_lock:
                expired_sessions = []
                for sid, state in list(webrtc_media_states.items()):
                    updated_at = state.get('updated_at_ms', 0)
                    if now_ms - updated_at > timeout_ms:
                        expired_sessions.append(sid)
                
                for sid in expired_sessions:
                    logger.info('periodic_cleanup: removing expired session %d', sid)
                    webrtc_media_states.pop(sid, None)
                    webrtc_asr_runtime.pop(sid, None)
                    webrtc_media_tasks.pop(sid, None)
                    nerfreals.pop(sid, None)
                    recent_assistant_utterances.pop(sid, None)
            
            # 清理过期的 chat_record_runtime
            with chat_record_lock:
                expired_records = []
                for sid, runtime in list(chat_record_runtime.items()):
                    updated_at = runtime.get('updated_at_ms', 0)
                    if now_ms - updated_at > timeout_ms:
                        expired_records.append(sid)
                
                for sid in expired_records:
                    logger.info('periodic_cleanup: removing expired chat_record %d', sid)
                    chat_record_runtime.pop(sid, None)
            
            # 清理过期的 chat_stream_states
            with chat_stream_states_lock:
                expired_streams = []
                for stream_id, state in list(chat_stream_states.items()):
                    updated_at = state.get('updated_at_ms', 0)
                    if now_ms - updated_at > timeout_ms:
                        expired_streams.append(stream_id)
                
                for stream_id in expired_streams:
                    logger.info('periodic_cleanup: removing expired chat_stream %s', stream_id)
                    chat_stream_states.pop(stream_id, None)
            
            # 🔧 清理过期的 face_emotion_cache
            expired_emotions = []
            with face_emotion_cache_lock:
                for sid, cache in list(face_emotion_cache.items()):
                    cache_ts_ms = cache.get('timestamp_ms', 0)
                    if now_ms - cache_ts_ms > timeout_ms:
                        expired_emotions.append(sid)
                
                for sid in expired_emotions:
                    logger.info('periodic_cleanup: removing expired face_emotion %d', sid)
                    face_emotion_cache.pop(sid, None)
            
            # 🔧 清理孤立的 chat_subscribers（会话已结束但订阅者未清理）
            orphaned_subscribers = []
            with webrtc_media_lock:
                for sid in list(chat_subscribers.keys()):
                    if sid not in webrtc_media_states and sid not in nerfreals:
                        orphaned_subscribers.append(sid)
                
                for sid in orphaned_subscribers:
                    logger.info('periodic_cleanup: removing orphaned chat_subscriber %d', sid)
                    chat_subscribers.pop(sid, None)
            
            if expired_sessions or expired_records or expired_streams or expired_emotions or orphaned_subscribers:
                logger.info(
                    'periodic_cleanup: cleaned %d sessions, %d records, %d streams, %d emotions, %d subscribers',
                    len(expired_sessions), len(expired_records), len(expired_streams),
                    len(expired_emotions), len(orphaned_subscribers)
                )
        except Exception:
            logger.exception('periodic_memory_cleanup error')
##########################################
# os.environ['MKL_SERVICE_FORCE_INTEL'] = '1'
# os.environ['MULTIPROCESSING_METHOD'] = 'forkserver'                                                    
if __name__ == '__main__':
    mp.set_start_method('spawn')
    parser = build_arg_parser()

    opt = parser.parse_args()
    #app.config.from_object(opt)
    #print(app.config)
    opt.customopt = []
    if opt.customvideo_config!='':
        with open(opt.customvideo_config,'r') as file:
            opt.customopt = json.load(file)

    if opt.CHAT_RECORD_ENABLE:
        chat_record_dir = _resolve_chat_record_dir()
        if chat_record_dir:
            logger.info(
                'Chat record enabled: dir=%s policy=%s',
                chat_record_dir,
                _resolve_chat_record_policy(),
            )
        else:
            logger.warning('Chat record requested but CHAT_RECORD_DIR is empty, recording disabled')
    
    configure_face_emotion_runtime(opt)

    # 🆕 DeepFace 人脸情绪识别启动日志
    if opt.DEEPFACE_ENABLE:
        logger.info(
            'DeepFace face emotion recognition enabled: '
            'api_url=%s timeout=%.1fs analyze_every_n=%d cache_max_age=%dms',
            _get_deepface_api_url(),
            _get_deepface_timeout(),
            _get_deepface_analyze_every_n(),
            _get_deepface_cache_max_age_ms(),
        )
    else:
        logger.info('DeepFace face emotion recognition disabled')

    configure_lightrag_runtime(opt)
    asr_backend = build_asr_backend(opt)

    final_mode = _resolve_webrtc_final_asr_mode()
    webrtc_final_asr_backend = None
    webrtc_final_asr_backend_name = 'none'
    if final_mode == 'same':
        webrtc_final_asr_backend = asr_backend
        webrtc_final_asr_backend_name = str(getattr(asr_backend, 'name', 'none') or 'none')
    elif final_mode == 'http':
        webrtc_final_asr_backend_name = 'http_final'
    else:
        final_opt = argparse.Namespace(**vars(opt))
        final_opt.asr_backend = final_mode
        if final_mode == 'custom':
            final_opt.ASR_CUSTOM_HANDLER = str(getattr(opt, 'WEBRTC_FINAL_ASR_CUSTOM_HANDLER', '') or '').strip()
        webrtc_final_asr_backend = build_asr_backend(final_opt)
        webrtc_final_asr_backend_name = str(getattr(webrtc_final_asr_backend, 'name', final_mode) or final_mode)

    cloud_verify_enabled = _resolve_webrtc_final_cloud_verify_enabled()
    cloud_verify_mode = _resolve_webrtc_final_cloud_verify_mode()
    webrtc_final_cloud_verify_backend = None
    webrtc_final_cloud_verify_backend_name = 'disabled'
    if cloud_verify_enabled:
        if cloud_verify_mode == 'same':
            webrtc_final_cloud_verify_backend = asr_backend
            webrtc_final_cloud_verify_backend_name = str(getattr(asr_backend, 'name', 'none') or 'none')
        elif cloud_verify_mode == 'http':
            webrtc_final_cloud_verify_backend_name = 'http_cloud_verify'
        else:
            verify_opt = argparse.Namespace(**vars(opt))
            verify_opt.asr_backend = cloud_verify_mode
            if cloud_verify_mode == 'custom':
                verify_opt.ASR_CUSTOM_HANDLER = str(getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_CUSTOM_HANDLER', '') or '').strip()
            verify_backend = build_asr_backend(verify_opt)
            verify_backend_name = str(getattr(verify_backend, 'name', cloud_verify_mode) or cloud_verify_mode)
            webrtc_final_cloud_verify_backend = verify_backend
            webrtc_final_cloud_verify_backend_name = verify_backend_name

    llm_handler = _resolve_llm_handler()
    logger.info('Resolved ASR backend: %s', str(getattr(asr_backend, 'name', 'unknown') or 'unknown'))
    logger.info(
        'Resolved final webrtc ASR backend: mode=%s backend=%s strict_failure=%s',
        final_mode,
        webrtc_final_asr_backend_name,
        bool(getattr(opt, 'WEBRTC_FINAL_ASR_STRICT_FAILURE', False)),
    )
    logger.info(
        'Resolved final cloud verify: enabled=%s mode=%s backend=%s similarity=%.2f short_text_chars=%d min_cloud_chars=%d replace_with_cloud=%s',
        cloud_verify_enabled,
        cloud_verify_mode,
        webrtc_final_cloud_verify_backend_name,
        max(0.3, min(0.99, _safe_float(getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_SIMILARITY', 0.56), 0.56))),
        max(1, _safe_int(getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_SHORT_TEXT_CHARS', 8), 8)),
        max(1, _safe_int(getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_MIN_CLOUD_CHARS', 2), 2)),
        _safe_int(getattr(opt, 'WEBRTC_FINAL_ASR_CLOUD_VERIFY_REPLACE_WITH_CLOUD', 1), 1) == 1,
    )

    configure_turn_runtime(opt)
    logger.info('Resolved TURN urls: %s', resolve_turn_urls())

    from dittoreal import load_model, load_avatar, warm_up
    logger.info(opt)
    model = load_model(opt)
    avatar = load_avatar(opt)
    warm_up(opt.batch_size,model,avatar)
    
    configure_voice_api_runtime(opt, BASE_DIR)

    # 🆕 预加载音色和数字人生成服务（避免第一次请求慢）
    try:
        logger.info('[Voice Services] 开始预加载音色和数字人生成服务...')
        init_voice_services()
        logger.info('[Voice Services] ✅ 音色和数字人生成服务预加载完成！')
    except Exception as e:
        logger.warning(f'[Voice Services] ⚠️  服务预加载失败（不影响其他功能）: {e}')

    #############################################################################
    appasync = web.Application(client_max_size=1024**2*100)
    appasync.on_shutdown.append(on_shutdown)
    appasync.router.add_post("/offer", offer)
    appasync.router.add_post("/candidate", candidate)
    appasync.router.add_get("/rtc_config", rtc_config)
    appasync.router.add_post("/human", human)
    appasync.router.add_get("/chat_stream", chat_stream)
    appasync.router.add_post("/ai_conversation", ai_conversation)
    appasync.router.add_get("/api/lightrag/graph_labels", lightrag_graph_labels)
    appasync.router.add_get("/api/lightrag/graph", lightrag_graph)
    appasync.router.add_get("/api/lightrag/documents", lightrag_documents)
    appasync.router.add_post("/api/lightrag/documents", lightrag_documents)
    appasync.router.add_get("/api/lightrag/document_counts", lightrag_document_counts)
    appasync.router.add_get("/api/lightrag/pipeline_status", lightrag_pipeline_status)
    appasync.router.add_post("/api/lightrag/scan", lightrag_scan_documents)
    appasync.router.add_post("/api/lightrag/upload", lightrag_upload_document)
    appasync.router.add_post("/asr", asr)
    appasync.router.add_get("/webrtc_media_state", webrtc_media_state)
    appasync.router.add_post("/webrtc_asr_control", webrtc_asr_control)
    appasync.router.add_post("/multimodal_analysis", multimodal_analysis)
    
    # 🆕 音色和形象配置 API 路由
    appasync.router.add_get("/api/voices", get_voices)
    appasync.router.add_get("/api/avatars", get_avatars)
    appasync.router.add_delete("/api/avatars/{avatar_id}", delete_avatar)
    appasync.router.add_post("/api/upload/audio", upload_audio)
    appasync.router.add_post("/api/upload/avatar", upload_avatar)
    appasync.router.add_post("/api/voices/clone", clone_voice)
    appasync.router.add_post("/api/generate/speech", generate_speech)  # 纯语音合成
    appasync.router.add_post("/api/generate/video", generate_video)
    appasync.router.add_static("/data", path=os.path.join(BASE_DIR, "data"), show_index=False)
    appasync.router.add_static("/avatars", path=os.path.join(BASE_DIR, "data", "avatars"), show_index=False)

    # 配置全局 CORS 默认策略。
    cors = aiohttp_cors.setup(appasync, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
            )
        })
    # 将 CORS 策略应用到所有已注册路由。
    for route in list(appasync.router.routes()):
        cors.add(route)

    logger.info('start http server: http://<serverip>:%s', str(opt.listenport))
    def run_server(runner):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, '0.0.0.0', opt.listenport)
        loop.run_until_complete(site.start())
        
        # 启动定期内存清理任务
        cleanup_task = loop.create_task(periodic_memory_cleanup())
        logger.info('periodic_memory_cleanup task started')
        
        loop.run_forever()    
    #Thread(target=run_server, args=(web.AppRunner(appasync),)).start()
    run_server(web.AppRunner(appasync))

    #app.on_shutdown.append(on_shutdown)
    #app.router.add_post("/offer", offer)

    # print('start websocket server')
    # server = pywsgi.WSGIServer(('0.0.0.0', 8000), app, handler_class=WebSocketHandler)
    # server.serve_forever()
    
    
