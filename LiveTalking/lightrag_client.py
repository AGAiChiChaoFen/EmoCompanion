import json
import os
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from logger import logger


@dataclass
class LightRAGConfig:
    enabled: bool = True
    base_url: str = "http://101.200.57.208:9622"
    username: str = "admin"
    password: str = "admin"
    timeout_s: float = 8.0
    query_mode: str = "mix"
    top_k: int = 8
    chunk_top_k: int = 6
    max_total_tokens: int = 2200


_config = LightRAGConfig()
_token = ""
_token_lock = Lock()


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "")
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def configure_lightrag_runtime(opt: Any = None) -> None:
    global _config

    _config = LightRAGConfig(
        enabled=bool(getattr(opt, "LIGHTRAG_ENABLE", _env_bool("LIGHTRAG_ENABLE", True))),
        base_url=str(
            getattr(opt, "LIGHTRAG_BASE_URL", os.getenv("LIGHTRAG_BASE_URL", _config.base_url))
            or _config.base_url
        ).rstrip("/"),
        username=str(
            getattr(opt, "LIGHTRAG_USERNAME", os.getenv("LIGHTRAG_USERNAME", _config.username))
            or _config.username
        ),
        password=str(
            getattr(opt, "LIGHTRAG_PASSWORD", os.getenv("LIGHTRAG_PASSWORD", _config.password))
            or _config.password
        ),
        timeout_s=max(
            1.0,
            float(getattr(opt, "LIGHTRAG_TIMEOUT_S", _env_float("LIGHTRAG_TIMEOUT_S", _config.timeout_s))),
        ),
        query_mode=str(
            getattr(opt, "LIGHTRAG_QUERY_MODE", os.getenv("LIGHTRAG_QUERY_MODE", _config.query_mode))
            or _config.query_mode
        ),
        top_k=max(1, int(getattr(opt, "LIGHTRAG_TOP_K", _env_int("LIGHTRAG_TOP_K", _config.top_k)))),
        chunk_top_k=max(
            1,
            int(getattr(opt, "LIGHTRAG_CHUNK_TOP_K", _env_int("LIGHTRAG_CHUNK_TOP_K", _config.chunk_top_k))),
        ),
        max_total_tokens=max(
            256,
            int(getattr(opt, "LIGHTRAG_MAX_TOTAL_TOKENS", _env_int("LIGHTRAG_MAX_TOTAL_TOKENS", _config.max_total_tokens))),
        ),
    )
    logger.info(
        "LightRAG runtime: enabled=%s base_url=%s mode=%s timeout=%.1fs",
        _config.enabled,
        _config.base_url,
        _config.query_mode,
        _config.timeout_s,
    )


def is_lightrag_enabled() -> bool:
    return bool(_config.enabled)


def _request_json(
    path: str,
    *,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_s: Optional[float] = None,
) -> Any:
    url = f"{_config.base_url}{path if path.startswith('/') else '/' + path}"
    body = None
    request_headers = dict(headers or {})

    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, method=method.upper(), headers=request_headers)
    with urllib.request.urlopen(req, timeout=float(timeout_s or _config.timeout_s)) as response:
        raw = response.read().decode("utf-8", errors="replace")
    if not raw:
        return None
    return json.loads(raw)


def _request_raw(
    path: str,
    *,
    method: str = "GET",
    body: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_s: Optional[float] = None,
) -> Any:
    url = f"{_config.base_url}{path if path.startswith('/') else '/' + path}"
    req = urllib.request.Request(url, data=body, method=method.upper(), headers=dict(headers or {}))
    with urllib.request.urlopen(req, timeout=float(timeout_s or _config.timeout_s)) as response:
        raw = response.read().decode("utf-8", errors="replace")
    if not raw:
        return None
    return json.loads(raw)


def _login() -> str:
    form = urllib.parse.urlencode({
        "username": _config.username,
        "password": _config.password,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{_config.base_url}/login",
        data=form,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=float(_config.timeout_s)) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))
    token = str(data.get("access_token", "") or "").strip()
    if not token:
        raise RuntimeError("LightRAG login response missing access_token")
    return token


def _get_token() -> str:
    global _token
    with _token_lock:
        if _token:
            return _token
        _token = _login()
        return _token


def _authorized_json(path: str, *, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Any:
    global _token
    token = _get_token()
    try:
        return _request_json(
            path,
            method=method,
            payload=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise
        with _token_lock:
            _token = ""
        token = _get_token()
        return _request_json(
            path,
            method=method,
            payload=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


def _authorized_raw(
    path: str,
    *,
    method: str = "GET",
    body: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_s: Optional[float] = None,
) -> Any:
    global _token
    token = _get_token()
    request_headers = dict(headers or {})
    request_headers["Authorization"] = f"Bearer {token}"
    try:
        return _request_raw(path, method=method, body=body, headers=request_headers, timeout_s=timeout_s)
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise
        with _token_lock:
            _token = ""
        token = _get_token()
        request_headers["Authorization"] = f"Bearer {token}"
        return _request_raw(path, method=method, body=body, headers=request_headers, timeout_s=timeout_s)


def _multipart_file_body(field_name: str, filename: str, file_bytes: bytes, content_type: str) -> Tuple[bytes, str]:
    boundary = f"----HeartTalkLightRAG{uuid.uuid4().hex}"
    safe_filename = str(filename or "upload.txt").replace('"', "")
    mime_type = str(content_type or "application/octet-stream")
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{safe_filename}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _normalize_references(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    refs: List[Dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            refs.append({
                "reference_id": str(item.get("reference_id", "") or ""),
                "file_path": str(item.get("file_path", "") or ""),
            })
    return refs


def retrieve_lightrag_context(
    query: str,
    *,
    hl_keywords: Optional[List[str]] = None,
    ll_keywords: Optional[List[str]] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    normalized_query = str(query or "").strip()
    if (not _config.enabled) or len(normalized_query) < 3:
        return {"context": "", "references": [], "status": "disabled"}

    started = time.perf_counter()
    payload = {
        "query": normalized_query,
        "mode": _config.query_mode,
        "only_need_context": True,
        "response_type": "Bullet Points",
        "top_k": _config.top_k,
        "chunk_top_k": _config.chunk_top_k,
        "max_total_tokens": _config.max_total_tokens,
        "include_references": True,
        "include_chunk_content": False,
        "hl_keywords": hl_keywords or [],
        "ll_keywords": ll_keywords or [],
        "conversation_history": conversation_history or None,
        "enable_rerank": True,
    }

    try:
        data = _authorized_json("/query", method="POST", payload=payload)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        context = str((data or {}).get("response", "") or "").strip()
        references = _normalize_references((data or {}).get("references"))
        logger.info(
            "LightRAG context retrieved: query_len=%d context_len=%d refs=%d elapsed=%dms",
            len(normalized_query),
            len(context),
            len(references),
            elapsed_ms,
        )
        return {
            "context": context,
            "references": references,
            "status": "ok" if context else "empty",
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.warning("LightRAG context retrieval skipped: elapsed=%dms error=%s", elapsed_ms, exc)
        return {
            "context": "",
            "references": [],
            "status": "error",
            "error": str(exc),
            "elapsed_ms": elapsed_ms,
        }


def build_rag_enhanced_prompt(user_text: str, rag_result: Optional[Dict[str, Any]]) -> str:
    text = str(user_text or "").strip()
    context = str((rag_result or {}).get("context", "") or "").strip()
    if not context:
        return text

    return (
        "请先参考下面的知识库上下文，再回复用户。"
        "要求：保持共情和边界感，不做医学诊断，不夸大风险；如出现明显危机信号，建议及时联系专业人员或可信赖的人。\n\n"
        "【知识库上下文】\n"
        f"{context}\n\n"
        "【用户输入】\n"
        f"{text}"
    )


def get_graph_labels(limit: int = 80) -> List[str]:
    if not _config.enabled:
        return []
    try:
        data = _authorized_json(f"/graph/label/popular?limit={max(1, min(1000, int(limit)))}")
        return [str(item or "").strip() for item in data if str(item or "").strip()] if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("LightRAG graph labels unavailable: %s", exc)
        return []


def get_graph(label: str, *, max_depth: int = 3, max_nodes: int = 120) -> Any:
    normalized_label = str(label or "").strip()
    if (not _config.enabled) or (not normalized_label):
        return None
    params = urllib.parse.urlencode({
        "label": normalized_label,
        "max_depth": max(1, int(max_depth)),
        "max_nodes": max(1, int(max_nodes)),
    })
    try:
        return _authorized_json(f"/graphs?{params}")
    except Exception as exc:
        logger.warning("LightRAG graph unavailable: label=%s error=%s", normalized_label, exc)
        return None


def get_documents_paginated(
    *,
    page: int = 1,
    page_size: int = 20,
    status_filter: str = "",
    sort_field: str = "updated_at",
    sort_direction: str = "desc",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "page": max(1, int(page)),
        "page_size": max(10, min(200, int(page_size))),
        "sort_field": sort_field if sort_field in {"created_at", "updated_at", "id", "file_path"} else "updated_at",
        "sort_direction": "asc" if sort_direction == "asc" else "desc",
    }
    normalized_status = str(status_filter or "").strip().lower()
    if normalized_status in {"pending", "processing", "preprocessed", "processed", "failed"}:
        payload["status_filter"] = normalized_status
    return _authorized_json("/documents/paginated", method="POST", payload=payload) or {}


def get_document_status_counts() -> Dict[str, Any]:
    return _authorized_json("/documents/status_counts") or {}


def get_pipeline_status() -> Dict[str, Any]:
    return _authorized_json("/documents/pipeline_status") or {}


def scan_lightrag_documents() -> Dict[str, Any]:
    return _authorized_json("/documents/scan", method="POST") or {}


def upload_lightrag_document(filename: str, file_bytes: bytes, content_type: str = "") -> Dict[str, Any]:
    if not file_bytes:
        raise ValueError("uploaded file is empty")
    body, multipart_type = _multipart_file_body("file", filename, file_bytes, content_type)
    return _authorized_raw(
        "/documents/upload",
        method="POST",
        body=body,
        headers={"Content-Type": multipart_type},
        timeout_s=max(30.0, float(_config.timeout_s)),
    ) or {}
