###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  文件：media_utils.py
#  说明：媒体处理通用小工具。
#  许可证：Apache License 2.0
###############################################################################

from __future__ import annotations

import re

from logger import logger

_cv2_module = None
_cv2_import_attempted = False


def _sanitize_filename_fragment(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[^0-9a-zA-Z._-]+', '_', str(value or ''))
    cleaned = cleaned.strip('._-')
    if not cleaned:
        cleaned = fallback
    return cleaned[:80]


def _get_cv2_module():
    global _cv2_module, _cv2_import_attempted
    if _cv2_import_attempted:
        return _cv2_module

    _cv2_import_attempted = True
    try:
        import cv2

        _cv2_module = cv2
    except Exception:
        _cv2_module = None
        logger.warning('cv2 import failed; image frame encoding is unavailable')
    return _cv2_module
