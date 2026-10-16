import os
import re
from datetime import datetime, timezone, timedelta
import secrets



def _sanitize_for_dirname(name: str) -> str:
    """
    清理字符串，使其适合作为目录名。
    仅移除字符串末尾的下划线，保留中间的下划线和其他字符。
    
    参数:
        name: 原始字符串
    返回:
        清理后的字符串，适合作为目录名
    """
    # 仅移除末尾的下划线，保留中间的下划线
    sanitized = name.rstrip('_')
    # 移除空格和连字符
    sanitized = re.sub(r'[\-\s]+', '', sanitized)
    # 移除所有非字母数字字符（保留中文字符和下划线）
    sanitized = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fa5]', '', sanitized)
    # 如果清理后为空，使用默认名称
    if not sanitized:
        sanitized = "default"
    return sanitized



def unique_output_path(prefix: str, ext: str = ".json", out_dir: str | None = None) -> str:
    """
    生成唯一输出文件路径，避免覆盖已有文件。
    根据 prefix 创建对应的子目录，并将文件保存在该子目录中。

    参数:
        prefix: 文件名前缀，将用于创建子目录（清理非法字符后）
        ext: 文件扩展名，默认为 ".json"
        out_dir: 输出根目录，默认创建位置是该脚本所在目录的同级 "output" 目录
    返回:
        唯一的输出文件路径字符串
    """
    if out_dir is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        out_dir = os.path.join(base_dir, "output")
    
    # 使用中国标准时间（UTC+8，Asia/Shanghai）
    tz = timezone(timedelta(hours=8), name="CST")
    now = datetime.now(tz)
    ts = now.strftime("%Y%m%dT%H%M%S")
    us = f"{now.microsecond:06d}"
    rand = secrets.token_hex(4)
    
    # 清理 prefix 并创建子目录
    subdir_name = _sanitize_for_dirname(prefix)
    subdir_path = os.path.join(out_dir, subdir_name)
    os.makedirs(subdir_path, exist_ok=True)
    
    # 生成文件名（保留原始 prefix）
    filename = f"{prefix}{ts}_{us}_{rand}{ext}"
    return os.path.join(subdir_path, filename)
