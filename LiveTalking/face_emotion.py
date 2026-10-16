###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  文件：face_emotion.py
#  说明：DeepFace 人脸情绪识别配置、API 调用与会话缓存。
#  许可证：Apache License 2.0
###############################################################################

from __future__ import annotations

import asyncio
import os
import time
from threading import Lock
from typing import Any, Dict, Optional

from logger import logger

opt: Any = None


def configure_face_emotion_runtime(options: Any) -> None:
    """注入 app.py 启动阶段解析出的 DeepFace 相关配置。"""
    global opt
    opt = options


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


# 🆕 人脸情绪识别相关全局变量
# 人脸情绪缓存：sessionid -> 人脸情绪信息
face_emotion_cache: Dict[int, Dict[str, Any]] = {}
face_emotion_cache_lock = Lock()



# 🆕 ========== DeepFace 人脸情绪识别相关函数 ==========

def _is_deepface_enabled() -> bool:
    """
    检查是否启用了 DeepFace 人脸情绪识别功能
    
    返回:
        bool: 如果启用返回 True，否则返回 False
    """
    return bool(getattr(opt, 'DEEPFACE_ENABLE', False))


def _get_deepface_api_url() -> str:
    """
    获取 DeepFace API 服务地址
    
    返回:
        str: DeepFace API URL，默认为 'http://127.0.0.1:9020'
    """
    return str(getattr(opt, 'DEEPFACE_API_URL', 'http://127.0.0.1:9020') or 'http://127.0.0.1:9020').strip()


def _get_deepface_timeout() -> Optional[float]:
    """
    获取 DeepFace API 调用超时时间（秒）
    
    返回:
        Optional[float]: 超时时间；当配置值 <= 0 时禁用超时
    """
    timeout_s = _safe_float(getattr(opt, 'DEEPFACE_TIMEOUT_S', 0.0), 0.0)
    return timeout_s if timeout_s > 0 else None


def _get_deepface_analyze_every_n() -> int:
    """
    获取 DeepFace 分析频率：每隔 N 个保存的视频帧分析一次
    
    返回:
        int: 分析频率，默认为 3（每3个保存的帧分析一次）
    """
    return max(1, _safe_int(getattr(opt, 'DEEPFACE_ANALYZE_EVERY_N', 3), 3))


def _get_deepface_cache_max_age_ms() -> int:
    """
    获取人脸情绪缓存的最大有效期（毫秒）
    
    返回:
        int: 缓存有效期，默认为 10000 毫秒（10秒）
    """
    return max(1000, _safe_int(getattr(opt, 'DEEPFACE_CACHE_MAX_AGE_MS', 10000), 10000))


def call_deepface_api_with_status(image_path: str, *, force: bool = False) -> Dict[str, Any]:
    """
    调用 DeepFace API 识别人脸情绪（同步调用，会阻塞）
    
    参数:
        image_path: 图片文件路径（支持 jpg, jpeg, png, webp, bmp）
        force: True 时忽略 DEEPFACE_ENABLE 开关，直接尝试调用上传分析链路所需的 DeepFace 服务
        
    返回:
        Dict[str, Any]: 结构为 {'emotion': Optional[str], 'status': str, 'message': str}
        
    注意:
        - 此函数会阻塞 4-5 秒，必须在线程池中异步调用
        - 失败时不会抛出异常，调用方可通过 status/message 判断失败原因
    """
    if (not force) and (not _is_deepface_enabled()):
        return {
            'emotion': None,
            'status': 'disabled',
            'message': 'DeepFace 人脸分析未启用',
        }
    
    # 🆕 4.2 增强错误处理：检查文件是否存在
    if not os.path.exists(image_path):
        logger.warning('[DeepFace] Image file not found: path=%s', image_path)
        return {
            'emotion': None,
            'status': 'missing_file',
            'message': '待分析关键帧不存在',
        }
    
    api_url = _get_deepface_api_url()
    timeout_s = _get_deepface_timeout()
    timeout_label = f'{timeout_s:.0f}s' if timeout_s else 'disabled'
    
    # 🆕 4.1 增强日志：记录调用开始
    logger.info(
        '[DeepFace] Calling API: url=%s, image=%s, timeout=%s',
        api_url,
        os.path.basename(image_path),
        timeout_label
    )
    
    try:
        # 导入 requests 库（延迟导入，避免启动时依赖）
        import requests
        from requests.exceptions import Timeout, ConnectionError, RequestException
        
        # 打开图片文件并上传
        with open(image_path, 'rb') as f:
            files = {
                'image_file': (os.path.basename(image_path), f, 'image/jpeg')
            }
            response = requests.post(
                f'{api_url}/face-emotion',
                files=files,
                timeout=timeout_s
            )
        
        # 检查响应状态
        if response.status_code == 200:
            # 🆕 4.3 验证响应格式
            try:
                data = response.json()
            except Exception as json_exc:
                logger.warning(
                    '[DeepFace] Invalid JSON response: image=%s, error=%s',
                    os.path.basename(image_path),
                    str(json_exc)
                )
                return {
                    'emotion': None,
                    'status': 'invalid_json',
                    'message': 'DeepFace 返回了无法解析的结果',
                }
            
            # 🆕 4.3 验证响应是否为字典类型
            if not isinstance(data, dict):
                logger.warning(
                    '[DeepFace] Invalid response type: expected dict, got %s, image=%s',
                    type(data).__name__,
                    os.path.basename(image_path)
                )
                return {
                    'emotion': None,
                    'status': 'invalid_response',
                    'message': 'DeepFace 返回了非预期响应格式',
                }
            
            # 🆕 4.3 验证是否包含 dominant_emotion 字段
            if 'dominant_emotion' not in data:
                logger.warning(
                    '[DeepFace] Missing dominant_emotion field: image=%s, response_keys=%s',
                    os.path.basename(image_path),
                    list(data.keys())
                )
                return {
                    'emotion': None,
                    'status': 'invalid_response',
                    'message': 'DeepFace 未返回 dominant_emotion 字段',
                }
            
            emotion = str(data.get('dominant_emotion', '') or '').strip()
            if not emotion:
                logger.warning(
                    '[DeepFace] Empty dominant_emotion field: image=%s',
                    os.path.basename(image_path),
                )
                return {
                    'emotion': None,
                    'status': 'empty_emotion',
                    'message': 'DeepFace 未识别到有效面部情绪',
                }
            
            # 🆕 4.1 增强日志：记录成功
            logger.info(
                '[DeepFace] Success: image=%s, emotion=%s',
                os.path.basename(image_path),
                emotion
            )
            return {
                'emotion': emotion,
                'status': 'detected',
                'message': '',
            }
        else:
            # 🆕 4.1 增强日志：记录 HTTP 错误
            logger.warning(
                '[DeepFace] HTTP error: status=%d, image=%s, url=%s',
                response.status_code,
                os.path.basename(image_path),
                api_url
            )
            return {
                'emotion': None,
                'status': f'http_{response.status_code}',
                'message': f'DeepFace 接口返回异常状态 {response.status_code}',
            }
    
    # 🆕 4.2 增强错误处理：超时异常
    except Timeout:
        logger.warning(
            '[DeepFace] Timeout: image=%s, timeout=%s, url=%s',
            os.path.basename(image_path),
            timeout_label,
            api_url
        )
        return {
            'emotion': None,
            'status': 'timeout',
            'message': f'DeepFace 服务响应超时（{timeout_label}）',
        }
    
    # 🆕 4.2 增强错误处理：连接错误
    except ConnectionError as conn_exc:
        logger.error(
            '[DeepFace] Connection error: image=%s, url=%s, error=%s',
            os.path.basename(image_path),
            api_url,
            str(conn_exc)
        )
        return {
            'emotion': None,
            'status': 'connection_error',
            'message': f'无法连接到 DeepFace 服务（{api_url}）',
        }
    
    # 🆕 4.2 增强错误处理：文件读取错误
    except FileNotFoundError:
        logger.error(
            '[DeepFace] File not found during read: path=%s',
            image_path
        )
        return {
            'emotion': None,
            'status': 'missing_file',
            'message': '待分析关键帧不存在',
        }
    
    # 🆕 4.2 增强错误处理：导入错误
    except ImportError:
        logger.error('[DeepFace] requests library not installed, please run: pip install requests')
        return {
            'emotion': None,
            'status': 'missing_dependency',
            'message': '缺少 DeepFace 请求依赖 requests',
        }
    
    # 🆕 4.2 增强错误处理：通用异常
    except Exception as exc:
        logger.exception(
            '[DeepFace] Unexpected error: image=%s, url=%s, error=%s',
            os.path.basename(image_path),
            api_url,
            str(exc)
        )
        return {
            'emotion': None,
            'status': 'unexpected_error',
            'message': 'DeepFace 分析过程中出现异常',
        }


def call_deepface_api(image_path: str, *, force: bool = False) -> Optional[str]:
    """
    调用 DeepFace API 并仅返回情绪标签，兼容既有调用方。
    """
    result = call_deepface_api_with_status(image_path, force=force)
    emotion = str(result.get('emotion', '') or '').strip()
    return emotion or None


async def _analyze_face_emotion_async(
    sessionid: int,
    image_path: str,
    frame_index: int,
    delete_after: bool = False,
) -> None:
    """
    异步分析人脸情绪并更新缓存（不阻塞主流程）
    
    参数:
        sessionid: 会话ID
        image_path: 图片文件路径
        frame_index: 视频帧索引
        
    说明:
        - 在线程池中执行 DeepFace API 调用，避免阻塞事件循环
        - 分析成功后更新全局缓存 face_emotion_cache
        - 失败时仅记录日志，不影响主流程
    """
    if not _is_deepface_enabled():
        return
    
    # 🆕 4.1 增强日志：记录异步任务开始
    logger.debug(
        '[DeepFace] Starting async analysis: sessionid=%d, frame_index=%d, image=%s',
        sessionid,
        frame_index,
        os.path.basename(image_path)
    )
    
    try:
        # 在线程池中执行同步的 DeepFace API 调用
        loop = asyncio.get_event_loop()
        emotion = await loop.run_in_executor(
            None,  # 使用默认线程池
            call_deepface_api,
            image_path
        )
        
        # 如果识别成功，更新缓存
        if emotion:
            timestamp_ms = int(time.time() * 1000)
            
            # 🆕 4.4 添加缓存更新日志
            with face_emotion_cache_lock:
                face_emotion_cache[sessionid] = {
                    'emotion': emotion,
                    'timestamp_ms': timestamp_ms,
                    'frame_index': frame_index,
                    'image_path': image_path
                }
            
            logger.info(
                '[DeepFace] Cache updated: sessionid=%d, emotion=%s, timestamp_ms=%d, frame_index=%d, image=%s',
                sessionid,
                emotion,
                timestamp_ms,
                frame_index,
                os.path.basename(image_path)
            )
        else:
            # 🆕 4.1 增强日志：记录识别失败
            logger.debug(
                '[DeepFace] Analysis returned None: sessionid=%d, frame_index=%d, image=%s',
                sessionid,
                frame_index,
                os.path.basename(image_path)
            )
            
    except Exception as exc:
        # 🆕 4.2 增强错误处理：记录完整错误堆栈
        logger.exception(
            '[DeepFace] Async analysis failed: sessionid=%d, frame_index=%d, image=%s, error=%s',
            sessionid,
            frame_index,
            os.path.basename(image_path),
            str(exc)
        )
    finally:
        if delete_after:
            try:
                os.remove(image_path)
            except FileNotFoundError:
                pass
            except Exception:
                logger.debug('[DeepFace] failed to remove temp frame: %s', image_path, exc_info=True)


def _get_latest_face_emotion(sessionid: int, max_age_ms: Optional[int] = None) -> str:
    """
    获取最新的人脸情绪（从缓存中读取）
    
    参数:
        sessionid: 会话ID
        max_age_ms: 最大有效期（毫秒），超过此时间的缓存视为过期
                    如果为 None，则使用配置的默认值
        
    返回:
        str: 人脸情绪标签，默认 "中性/平静"
        
    说明:
        - 如果缓存不存在或已过期，返回默认值 "中性/平静"
        - 缓存过期时间可通过 --DEEPFACE_CACHE_MAX_AGE_MS 配置
    """
    if not _is_deepface_enabled():
        return '中性/平静'
    
    if max_age_ms is None:
        max_age_ms = _get_deepface_cache_max_age_ms()
    
    with face_emotion_cache_lock:
        cache = face_emotion_cache.get(sessionid)
        
    if not cache:
        return '中性/平静'
    
    # 检查是否过期
    now_ms = int(time.time() * 1000)
    cache_ts_ms = _safe_int(cache.get('timestamp_ms', 0), 0)
    age_ms = now_ms - cache_ts_ms
    
    if age_ms > max_age_ms:
        logger.debug(
            f'sessionid={sessionid} face_emotion cache expired: '
            f'age={age_ms}ms, max_age={max_age_ms}ms'
        )
        return '中性/平静'
    
    emotion = str(cache.get('emotion', '中性/平静') or '中性/平静').strip()
    return emotion
