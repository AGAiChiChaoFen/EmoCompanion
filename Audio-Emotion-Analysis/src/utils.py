"""
工具函数模块。

提供图片编码、prompt 解析等辅助功能。
"""

import base64
import re
from pathlib import Path
from typing import Optional


def encode_image_to_base64(image_path: str) -> str:
    """将本地图片文件编码为 base64 data URI。

    自动识别常见图片格式（PNG、JPEG、GIF、WebP）。

    Args:
        image_path: 图片文件的本地路径。

    Returns:
        形如 'data:image/png;base64,...' 的 data URI 字符串。
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    # 根据扩展名确定 MIME 类型
    ext_to_mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    mime_type = ext_to_mime.get(path.suffix.lower(), "image/png")

    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{encoded}"


def count_img_fill(prompt: str) -> int:
    """统计 prompt 中 <img_fill> 占位符的数量。

    Args:
        prompt: PersonaVLM 格式的 prompt 文本。

    Returns:
        <img_fill> 出现次数。
    """
    return prompt.count("<img_fill>")


def strip_img_fill(prompt: str) -> str:
    """移除 prompt 中的 <img_fill> 占位符及紧随的换行符。

    Args:
        prompt: 包含 <img_fill> 的 prompt 文本。

    Returns:
        清理后的纯文本 prompt。
    """
    # 移除 <img_fill>\n 或 <img_fill>
    cleaned = re.sub(r"<img_fill>\n?", "", prompt)
    return cleaned.strip()
