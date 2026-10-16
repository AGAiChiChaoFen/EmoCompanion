from pathlib import Path
import tempfile

from fastapi import HTTPException, UploadFile



def safe_audio_suffix(upload: UploadFile) -> str:
    """
    推断上传音频文件后缀并进行白名单校验。

    参数：
        upload: FastAPI 上传文件对象，包含文件名与 MIME 信息。

    返回：
        返回可用后缀（如 .mp3/.wav）。
        若后缀不在支持范围，将抛出 HTTPException。
    """
    allowed_suffixes = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
    file_name = upload.filename or ""
    suffix = Path(file_name).suffix.lower()
    if not suffix:
        content_type_map = {
            "audio/mpeg": ".mp3",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/mp4": ".m4a",
            "audio/flac": ".flac",
            "audio/ogg": ".ogg",
            "audio/aac": ".aac",
        }
        suffix = content_type_map.get(upload.content_type or "", "")

    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的音频格式: {suffix or 'unknown'}，支持: {sorted(allowed_suffixes)}",
        )
    return suffix



async def save_uploaded_audio(upload: UploadFile) -> Path:
    """
    将上传音频保存到临时文件并返回路径。

    参数：
        upload: FastAPI 上传文件对象。

    返回：
        返回本地临时文件路径。
        若文件为空或写入失败，将抛出 HTTPException。
    """
    suffix = safe_audio_suffix(upload)
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")

    with tempfile.NamedTemporaryFile(prefix="audio_upload_", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    return tmp_path



def cleanup_temp_file(file_path: Path | None) -> None:
    """
    清理本地临时音频文件。

    参数：
        file_path: 待删除的临时文件路径，可为空。

    返回：
        无。文件不存在或删除失败时静默跳过。
    """
    if not file_path:
        return
    try:
        if file_path.exists():
            file_path.unlink()
    except OSError:
        pass