from __future__ import annotations

import asyncio
from functools import lru_cache
import os
from pathlib import Path
import tempfile

from fastapi import HTTPException, UploadFile



def safe_image_suffix(upload: UploadFile) -> str:
    """
    推断上传图片文件后缀并进行白名单校验。

    参数：
        upload: FastAPI 上传文件对象，包含文件名与 MIME 信息。

    返回：
        返回可用后缀（如 .jpg/.png）。
        若后缀不在支持范围，将抛出 HTTPException。
    """
    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    file_name = upload.filename or ""
    suffix = Path(file_name).suffix.lower()
    if not suffix:
        content_type_map = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
        }
        suffix = content_type_map.get(upload.content_type or "", "")

    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式: {suffix or 'unknown'}，支持: {sorted(allowed_suffixes)}",
        )
    return suffix



async def save_uploaded_image(upload: UploadFile) -> Path:
    """
    将上传图片保存到临时文件并返回路径。

    参数：
        upload: FastAPI 上传文件对象。

    返回：
        返回本地临时文件路径。
        若文件为空或写入失败，将抛出 HTTPException。
    """
    suffix = safe_image_suffix(upload)
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")

    with tempfile.NamedTemporaryFile(prefix="image_upload_", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    return tmp_path


def read_deepface_home() -> Path:
    """
    读取 DeepFace 权重目录（优先 .env 的 DEEPFACE_HOME，缺省项目根）。

    参数：
        无。

    返回：
        返回 DeepFace 权重缓存目录 Path。优先取环境变量 DEEPFACE_HOME
        （由 main.py 的 load_dotenv 从 .env 加载），未配置时回退项目根
        deepface_weights，用于固定 DeepFace 模型缓存位置。
    """
    raw = os.getenv("DEEPFACE_HOME")
    if raw:
        return Path(raw)
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    return project_root / "deepface_weights"


@lru_cache(maxsize=1)
def load_deepface_module() -> object:
    """
    以 CPU 模式单例加载 DeepFace。

    参数：
        无。

    返回：
        返回 DeepFace 类对象。
        首次加载时会固定权重目录，并在 TensorFlow 导入前临时屏蔽 GPU，避免 FastAPI 进程中触发 TensorFlow 的 GPU 初始化与 PTX JIT 警告。
    """
    os.environ["DEEPFACE_HOME"] = str(read_deepface_home())

    original_cuda_visible_devices = os.environ.get("CUDA_VISIBLE_DEVICES")
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

    try:
        from deepface import DeepFace
    finally:
        if original_cuda_visible_devices is None:
            os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        else:
            os.environ["CUDA_VISIBLE_DEVICES"] = original_cuda_visible_devices

    return DeepFace



async def analyze_face_dominant_emotion(image_path: Path) -> str:
    """
    分析图片中的主导面部情绪（返回中文标签）。

    参数：
        image_path: 待分析图片路径。

    返回：
        返回中文 dominant_emotion 标签（愤怒/厌恶/恐惧/高兴/悲伤/惊讶/中性/平静，
        未知英文标签原样返回）。
        当权重目录不存在时抛 FileNotFoundError；图片中未检测到可用情绪结果时抛 ValueError。
    """
    deepface_home = read_deepface_home()
    if not deepface_home.exists():
        raise FileNotFoundError(f"DeepFace 权重目录不存在: {deepface_home}")

    DeepFace = load_deepface_module()

    analyze_result = await asyncio.to_thread(
        DeepFace.analyze,
        img_path=str(image_path),
        actions=["emotion"],
        detector_backend="retinaface",
        align=True,
        anti_spoofing=False,
    )

    dominant_emotion = analyze_result[0]['dominant_emotion']

    if not dominant_emotion:
        raise ValueError("未能识别人脸主导情绪，请确认图片中包含清晰人脸")

    # 英文标签 → 中文标签映射（与陪护场景的中文情绪画像保持一致）
    emotion_map = {
        'angry': '愤怒',
        'disgust': '厌恶',
        'fear': '恐惧',
        'happy': '高兴',
        'sad': '悲伤',
        'surprise': '惊讶',
        'neutral': '中性/平静',
    }
    return str(emotion_map.get(dominant_emotion, dominant_emotion))