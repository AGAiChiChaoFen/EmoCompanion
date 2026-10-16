from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, Optional, Tuple

from basereal import BaseReal
from logger import logger


PUNCTUATION = ",.!;:，。！？：；\n"
STRONG_PUNCTUATION = ".!?。！？\n"


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _resolve_requests_timeout(value: Any, default: float = 0.0) -> Optional[float]:
    resolved = _safe_float(value, default)
    return resolved if resolved > 0 else None


def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _build_auth_headers(prefix: str) -> Dict[str, str]:
    token = str(os.getenv(f"{prefix}_AUTH_TOKEN", "") or "").strip()
    if not token:
        token = str(os.getenv("CUSTOM_API_AUTH_TOKEN", "") or "").strip()

    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _parse_wrapped_message(message: str) -> Tuple[str, str, str]:
    text = str(message or "").strip()
    if not text:
        return "", "", ""

    marker = "\n【用户原话】"
    if marker in text:
        emotion_block, user_text = text.split(marker, 1)
        emotion_line = str(emotion_block or "").strip()
        emotion_label = ""
        face_emotion = ""

        if emotion_line.startswith("【语音情感】"):
            emotion_line = emotion_line.replace("【语音情感】", "", 1).strip()
            for item in emotion_line.split("；"):
                part = str(item or "").strip()
                if part.startswith("label="):
                    emotion_label = part.split("=", 1)[1].strip()
                    break
            return str(user_text or "").strip(), emotion_label, ""

        if emotion_line.startswith("【多模态情绪】"):
            emotion_line = emotion_line.replace("【多模态情绪】", "", 1).strip()
            for item in emotion_line.split("；"):
                part = str(item or "").strip()
                if part.startswith("语音情绪="):
                    emotion_label = part.split("=", 1)[1].strip()
                elif part.startswith("面部表情="):
                    face_emotion = part.split("=", 1)[1].strip()
                elif part.startswith("label=") and not emotion_label:
                    emotion_label = part.split("=", 1)[1].strip()
                elif part.startswith("face_emotion=") and not face_emotion:
                    face_emotion = part.split("=", 1)[1].strip()
            return str(user_text or "").strip(), emotion_label, face_emotion

    return text, "", ""


def _extract_text_from_any(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        parts = [_extract_text_from_any(item) for item in value]
        return "".join([part for part in parts if part]).strip()

    if isinstance(value, dict):
        for key in ("result", "text", "reply", "response", "content", "message"):
            if key in value:
                candidate = _extract_text_from_any(value.get(key))
                if candidate:
                    return candidate
        for nested in value.values():
            candidate = _extract_text_from_any(nested)
            if candidate:
                return candidate

    return ""


def _push_text_to_tts_with_chunking(
    *,
    full_text: str,
    nerfreal: BaseReal,
    on_delta: Optional[Callable[[str], None]],
    tts_event: Optional[Dict[str, Any]],
    char_interval_s: float,
) -> str:
    result_buffer = ""
    emitted_chars = ""
    first_tts_sent = False
    tts_datainfo = tts_event or {}

    def flush_to_tts(text: str) -> None:
        nonlocal first_tts_sent
        if not text or not text.strip():
            return
        nerfreal.put_msg_txt(text, tts_datainfo)
        first_tts_sent = True

    def consume_char(ch: str) -> None:
        nonlocal result_buffer, emitted_chars
        if not ch:
            return

        emitted_chars += ch
        if on_delta is not None:
            on_delta(ch)

        result_buffer += ch
        if ch in PUNCTUATION:
            is_strong = ch in STRONG_PUNCTUATION
            if first_tts_sent:
                normal_threshold = 28
                strong_threshold = 6
            else:
                normal_threshold = 14
                strong_threshold = 4
            if len(result_buffer) >= normal_threshold or (is_strong and len(result_buffer) >= strong_threshold):
                flush_to_tts(result_buffer)
                result_buffer = ""

        force_threshold = 42 if first_tts_sent else 20
        while len(result_buffer) >= force_threshold:
            flush_to_tts(result_buffer[:force_threshold])
            result_buffer = result_buffer[force_threshold:]
            force_threshold = 42

    for ch in str(full_text or ""):
        consume_char(ch)
        if char_interval_s > 0:
            time.sleep(char_interval_s)

    flush_to_tts(result_buffer)
    return emitted_chars


def asr_http_handler(
    *,
    audio_bytes: bytes,
    filename: str,
    hint_text: str,
    sessionid: int,
    mode: str,
) -> Dict[str, Any]:
    import requests

    url = str(os.getenv("CUSTOM_ASR_API_URL", "") or "").strip()
    if not url:
        raise RuntimeError("CUSTOM_ASR_API_URL is empty")

    timeout_s = _resolve_requests_timeout(os.getenv("CUSTOM_ASR_TIMEOUT_S", "0"), 0.0)
    file_field = str(os.getenv("CUSTOM_ASR_FILE_FIELD", "audio_file") or "audio_file").strip() or "audio_file"

    payload: Dict[str, Any] = {}
    if _is_truthy(os.getenv("CUSTOM_ASR_SEND_SESSION", "1")):
        payload["session_id"] = str(sessionid)
    if _is_truthy(os.getenv("CUSTOM_ASR_SEND_MODE", "1")):
        payload["mode"] = str(mode or "")

    headers = _build_auth_headers("CUSTOM_ASR")
    upload_name = str(filename or "audio.wav")

    start = time.perf_counter()
    response = requests.post(
        url,
        data=payload,
        files={
            file_field: (
                upload_name,
                audio_bytes or b"",
                "audio/wav",
            )
        },
        headers=headers,
        timeout=timeout_s,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("custom ASR response must be a JSON object")

    result_obj = data.get("result") if isinstance(data.get("result"), dict) else {}
    transcript = str(
        result_obj.get("asr")
        or result_obj.get("transcript")
        or result_obj.get("text")
        or data.get("asr")
        or data.get("transcript")
        or data.get("text")
        or ""
    ).strip()

    emotion_label = str(
        result_obj.get("emotion")
        or result_obj.get("emotion_label")
        or data.get("emotion")
        or data.get("emotion_label")
        or ""
    ).strip()

    if not transcript and hint_text:
        transcript = str(hint_text or "").strip()
        source = "browser_hint_fallback"
    else:
        source = str(data.get("source") or "custom_api_asr").strip() or "custom_api_asr"

    request_id = str(data.get("request_id") or data.get("requestId") or "").strip()

    emotion_extra: Dict[str, Any] = {
        "duration_seconds": data.get("duration_seconds"),
        "memory_after": data.get("memory_after"),
    }
    if result_obj:
        emotion_extra["asr_result"] = result_obj

    payload_out: Dict[str, Any] = {
        "transcript": transcript,
        "source": source,
        "elapsedMs": elapsed_ms,
    }
    if request_id:
        payload_out["request_id"] = request_id
    if emotion_label:
        payload_out["emotion_label"] = emotion_label
    cleaned_emotion_extra = {k: v for k, v in emotion_extra.items() if v is not None}
    if cleaned_emotion_extra:
        payload_out["emotion_extra"] = cleaned_emotion_extra

    logger.info(
        "custom asr call finished: sessionid=%s mode=%s source=%s elapsed=%dms",
        sessionid,
        mode,
        source,
        elapsed_ms,
    )
    return payload_out


def call_emollm_api(
    *,
    user_text: str,
    emotion_label: str,
    face_emotion: str = "",
    session_id: str = "",
    timeout_s: Optional[float] = None,
    user_name: str = "",
    external_knowledge: str = "",
    memory_update: bool = True,
) -> Dict[str, Any]:
    import requests

    url = str(os.getenv("CUSTOM_EMOLLM_API_URL", "") or "").strip()
    if not url:
        raise RuntimeError("CUSTOM_EMOLLM_API_URL is empty")

    user_text = str(user_text or "").strip()
    if not user_text:
        raise RuntimeError("custom EmoLLM request text is empty")

    resolved_emotion = str(emotion_label or os.getenv("CUSTOM_EMOLLM_DEFAULT_EMOTION", "neutral") or "neutral").strip()
    resolved_face_emotion = str(face_emotion or "").strip()
    resolved_session_id = str(session_id or os.getenv("CUSTOM_EMOLLM_SESSION_ID", "default")).strip()
    resolved_user_name = str(
        user_name
        or os.getenv("CUSTOM_EMOLLM_USER_NAME", "")
        or os.getenv("PERSONA_API_DEFAULT_USER", "")
    ).strip()
    resolved_timeout_s = max(
        1.0,
        float(timeout_s if timeout_s is not None else _safe_float(os.getenv("CUSTOM_EMOLLM_TIMEOUT_S", "30"), 30.0)),
    )

    req_payload: Dict[str, Any] = {
        "asr": user_text,
        "emotion": resolved_emotion,
    }
    if resolved_face_emotion:
        req_payload["face_emotion"] = resolved_face_emotion
    if resolved_session_id:
        req_payload["session_id"] = resolved_session_id
    if resolved_user_name:
        req_payload["user_name"] = resolved_user_name
    resolved_external_knowledge = str(external_knowledge or "").strip()
    if resolved_external_knowledge:
        req_payload["external_knowledge"] = resolved_external_knowledge
    req_payload["memory_update"] = bool(memory_update)

    headers = _build_auth_headers("CUSTOM_EMOLLM")

    start = time.perf_counter()
    response = requests.post(
        url,
        json=req_payload,
        headers=headers,
        timeout=resolved_timeout_s,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("custom EmoLLM response must be a JSON object")

    full_text = _extract_text_from_any(data)
    if not full_text:
        raise RuntimeError("custom EmoLLM response has empty result text")

    logger.info(
        "custom emollm call finished: session_id=%s elapsed=%dms",
        resolved_session_id,
        elapsed_ms,
    )

    return {
        "text": full_text,
        "data": data,
        "elapsed_ms": elapsed_ms,
        "session_id": resolved_session_id,
        "request_payload": req_payload,
    }


def emollm_response(
    message: str,
    nerfreal: BaseReal,
    on_delta: Optional[Callable[[str], None]] = None,
    tts_event: Optional[Dict[str, Any]] = None,
) -> str:
    user_text, emotion_label, face_emotion = _parse_wrapped_message(message)
    if not user_text:
        return ""

    session_id = str((tts_event or {}).get("chat_sessionid") or os.getenv("CUSTOM_EMOLLM_SESSION_ID", "default")).strip()
    user_name = str((tts_event or {}).get("persona_user_name") or "").strip()
    external_knowledge = str((tts_event or {}).get("external_knowledge") or "").strip()
    timeout_s = max(1.0, _safe_float(os.getenv("CUSTOM_EMOLLM_TIMEOUT_S", "30"), 30.0))
    char_interval_ms = _safe_int(
        os.getenv("CUSTOM_EMOLLM_DELTA_INTERVAL_MS", os.getenv("LLM_NONSTREAM_DELTA_INTERVAL_MS", "16")),
        16,
    )
    char_interval_s = max(0.0, float(char_interval_ms) / 1000.0)

    api_result = call_emollm_api(
        user_text=user_text,
        emotion_label=emotion_label,
        face_emotion=face_emotion,
        session_id=session_id,
        timeout_s=timeout_s,
        user_name=user_name,
        external_knowledge=external_knowledge,
    )

    emitted_text = _push_text_to_tts_with_chunking(
        full_text=str(api_result.get("text", "") or ""),
        nerfreal=nerfreal,
        on_delta=on_delta,
        tts_event=tts_event,
        char_interval_s=char_interval_s,
    )
    return emitted_text
