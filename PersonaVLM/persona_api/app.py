"""Flask 应用工厂与 REST 路由。"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from flask import Flask, Response, g, jsonify, request, send_file
from werkzeug.exceptions import BadRequest, HTTPException, RequestEntityTooLarge

from .agent_service import AgentService
from .config import ApiSettings, PROJECT_DIR
from .errors import ApiError, ValidationError
from .locks import UserLockRegistry
from .memory_service import MemoryService


LOGGER = logging.getLogger("persona_api.http")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_app(
    settings: Optional[ApiSettings] = None,
    *,
    memory_service: Optional[MemoryService] = None,
    agent_service: Optional[AgentService] = None,
) -> Flask:
    """创建可测试、可注入依赖的 Flask 应用。"""

    current_settings = settings or ApiSettings.from_env()
    locks = UserLockRegistry()
    memories = memory_service or MemoryService(current_settings.output_root, locks)
    agents = agent_service or AgentService(current_settings, memories, locks)

    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.config["MAX_CONTENT_LENGTH"] = current_settings.max_body_bytes
    app.config["JSON_SORT_KEYS"] = False
    app.extensions["persona_settings"] = current_settings
    app.extensions["memory_service"] = memories
    app.extensions["agent_service"] = agents

    @app.before_request
    def before_request() -> None:
        supplied_id = request.headers.get("X-Request-Id", "").strip()
        g.request_id = supplied_id[:100] if supplied_id else f"req_{uuid.uuid4().hex[:12]}"
        g.request_started = time.perf_counter()
        LOGGER.info(
            "收到请求 | 编号=%s | 方法=%s | 路径=%s | 来源=%s",
            g.request_id,
            request.method,
            request.path,
            request.remote_addr or "未知",
        )

    @app.after_request
    def after_request(response: Response) -> Response:
        request_id = getattr(g, "request_id", f"req_{uuid.uuid4().hex[:12]}")
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"

        origin = request.headers.get("Origin")
        if origin and origin in current_settings.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Request-Id"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"

        elapsed_ms = (time.perf_counter() - getattr(g, "request_started", time.perf_counter())) * 1000
        LOGGER.info(
            "请求完成 | 编号=%s | 状态=%d | 用时=%.1f毫秒",
            request_id,
            response.status_code,
            elapsed_ms,
        )
        return response

    def success(data: Any, status_code: int = 200) -> tuple[Response, int]:
        return jsonify({
            "data": data,
            "meta": {
                "request_id": getattr(g, "request_id", None),
                "timestamp": _utc_timestamp(),
            },
        }), status_code

    def problem(error: ApiError) -> tuple[Response, int]:
        payload: dict[str, Any] = {
            "type": f"urn:persona-api:error:{error.code}",
            "title": error.title,
            "status": error.status_code,
            "detail": error.detail,
            "instance": request.path,
            "request_id": getattr(g, "request_id", None),
        }
        if error.errors:
            payload["errors"] = error.errors
        return jsonify(payload), error.status_code

    def parse_pagination() -> tuple[int, int]:
        try:
            page = int(request.args.get("page", "1"))
            per_page = int(request.args.get("per_page", "20"))
        except ValueError as exc:
            raise ValidationError("page 和 per_page 必须是整数。") from exc
        if page < 1:
            raise ValidationError("page 不能小于1。", "page")
        if per_page < 1 or per_page > 100:
            raise ValidationError("per_page 必须在1到100之间。", "per_page")
        return page, per_page

    def read_user_memory(user_name: str) -> dict[str, Any]:
        LOGGER.info("读取用户记忆 | 编号=%s | 用户=%s", g.request_id, user_name)
        return memories.read_memory(user_name)

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError) -> tuple[Response, int]:
        LOGGER.warning(
            "业务请求失败 | 编号=%s | 状态=%d | 错误=%s | 详情=%s",
            getattr(g, "request_id", "未知"),
            error.status_code,
            error.code,
            error.detail,
        )
        return problem(error)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_: RequestEntityTooLarge) -> tuple[Response, int]:
        return problem(ApiError(
            "请求内容过大",
            f"请求体不能超过 {current_settings.max_body_bytes} 字节。",
            413,
            "payload-too-large",
        ))

    @app.errorhandler(BadRequest)
    def handle_bad_request(_: BadRequest) -> tuple[Response, int]:
        return problem(ApiError("请求格式错误", "请求体不是有效的 JSON。", 400, "bad-request"))

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> tuple[Response, int]:
        return problem(ApiError(
            "HTTP请求失败",
            error.description,
            error.code or 500,
            f"http-{error.code or 500}",
        ))

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception) -> tuple[Response, int]:
        LOGGER.exception("未处理异常 | 编号=%s", getattr(g, "request_id", "未知"))
        return problem(ApiError(
            "服务内部错误",
            "服务处理请求时发生异常，请根据请求编号查看服务端日志。",
            500,
            "internal-error",
        ))

    @app.get("/health")
    def health() -> tuple[Response, int]:
        return success({"status": "healthy", "service": "persona-memory-api"})

    @app.get("/openapi.yaml")
    def openapi_specification() -> Response:
        return send_file(PROJECT_DIR / "openapi.yaml", mimetype="application/yaml")

    @app.get("/ready")
    def ready() -> tuple[Response, int]:
        checks = agents.readiness()
        ready_state = bool(checks.get("model_path_exists") and checks.get("model_config_exists"))
        status_code = 200 if ready_state else 503
        return success({"status": "ready" if ready_state else "not_ready", "checks": checks}, status_code)

    @app.get("/api/v1/users")
    def list_users() -> tuple[Response, int]:
        page, per_page = parse_pagination()
        result = memories.paginate(memories.list_users(), page, per_page)
        LOGGER.info("用户列表读取完成 | 编号=%s | 用户总数=%d", g.request_id, result["pagination"]["total"])
        return success(result)

    @app.get("/api/v1/users/<string:user_name>/memory")
    def get_memory(user_name: str) -> tuple[Response, int]:
        return success(read_user_memory(user_name))

    @app.get("/api/v1/users/<string:user_name>/memory-summary")
    def get_memory_summary(user_name: str) -> tuple[Response, int]:
        data = read_user_memory(user_name)
        return success(memories.build_summary(data))

    @app.get("/api/v1/users/<string:user_name>/profiles")
    def get_profiles(user_name: str) -> tuple[Response, int]:
        page, per_page = parse_pagination()
        records = memories.flatten_profiles(read_user_memory(user_name))
        return success(memories.paginate(records, page, per_page))

    @app.get("/api/v1/users/<string:user_name>/personality-history")
    def get_personality_history(user_name: str) -> tuple[Response, int]:
        page, per_page = parse_pagination()
        records = memories.flatten_personality_history(read_user_memory(user_name))
        return success(memories.paginate(records, page, per_page))

    @app.get("/api/v1/users/<string:user_name>/semantic-memories")
    def get_semantic_memories(user_name: str) -> tuple[Response, int]:
        page, per_page = parse_pagination()
        records = memories.flatten_semantic_memories(read_user_memory(user_name))
        decision = request.args.get("decision", "all").strip().lower()
        if decision not in {"all", "true", "false"}:
            raise ValidationError("decision 只能是 all、true 或 false。", "decision")
        if decision != "all":
            expected = decision == "true"
            records = [record for record in records if bool(record.get("decision")) is expected]
        return success(memories.paginate(records, page, per_page))

    @app.get("/api/v1/users/<string:user_name>/episodic-memories")
    def get_episodic_memories(user_name: str) -> tuple[Response, int]:
        page, per_page = parse_pagination()
        records = memories.flatten_episodic_memories(read_user_memory(user_name))
        return success(memories.paginate(records, page, per_page))

    @app.get("/api/v1/users/<string:user_name>/procedural-memories")
    def get_procedural_memories(user_name: str) -> tuple[Response, int]:
        page, per_page = parse_pagination()
        records = memories.flatten_procedural_memories(read_user_memory(user_name))
        return success(memories.paginate(records, page, per_page))

    @app.get("/api/v1/users/<string:user_name>/interactions")
    def get_interactions(user_name: str) -> tuple[Response, int]:
        page, per_page = parse_pagination()
        records = memories.flatten_interactions(read_user_memory(user_name))
        session_index_raw = request.args.get("session_index")
        if session_index_raw is not None:
            try:
                session_index = int(session_index_raw)
            except ValueError as exc:
                raise ValidationError("session_index 必须是整数。", "session_index") from exc
            if session_index < 0:
                raise ValidationError("session_index 不能小于0。", "session_index")
            records = [record for record in records if record["session_index"] == session_index]
        return success(memories.paginate(records, page, per_page))

    @app.post("/api/v1/users/<string:user_name>/messages")
    def create_message(user_name: str) -> tuple[Response, int]:
        payload = request.get_json()
        if not isinstance(payload, dict):
            raise ValidationError("请求体必须是 JSON 对象。")
        LOGGER.info(
            "进入推理接口 | 编号=%s | 用户=%s | 包含指定时间=%s | 包含人格输入=%s",
            g.request_id,
            user_name,
            bool(payload.get("time")),
            payload.get("personality") is not None,
        )
        result = agents.infer(
            user_name=user_name,
            query=payload.get("query"),
            request_time=payload.get("time"),
            personality=payload.get("personality"),
        )
        return success(result, 201)

    @app.post("/emollm")
    def emollm_compat() -> Response:
        """兼容 LiveTalking 自定义 EmoLLM 接口，内部复用 PersonaVLM 推理与记忆更新。"""

        payload = request.get_json()
        if not isinstance(payload, dict):
            raise ValidationError("请求体必须是 JSON 对象。")

        user_name = str(payload.get("user_name") or payload.get("user") or "").strip()
        if not user_name:
            raise ValidationError("user_name 不能为空。", "user_name")
        query = str(
            payload.get("asr")
            or payload.get("query")
            or payload.get("text")
            or payload.get("message")
            or ""
        ).strip()
        if not query:
            raise ValidationError("asr/query/text/message 至少需要提供一个非空文本。", "asr")

        LOGGER.info(
            "进入 EmoLLM 兼容接口 | 编号=%s | 用户=%s | session_id=%s | 情绪=%s",
            g.request_id,
            user_name,
            payload.get("session_id") or "未提供",
            payload.get("emotion") or "未提供",
        )
        result = agents.infer(
            user_name=user_name,
            query=query,
            request_time=payload.get("time"),
            personality=payload.get("personality"),
            external_knowledge=payload.get("external_knowledge"),
            memory_update=payload.get("memory_update", True),
        )
        response_text = result.get("response") or ""
        return jsonify(
            {
                "result": response_text,
                "response": response_text,
                "text": response_text,
                "source": "personavlm",
                "user_name": result.get("user_name"),
                "time": result.get("time"),
                "session_id": payload.get("session_id"),
                "duration_seconds": result.get("duration_seconds"),
                "memory_updated": result.get("memory_updated", True),
                "request_id": g.request_id,
                "persona": result,
            }
        )

    @app.delete("/api/v1/users/<string:user_name>/agent-cache")
    def delete_agent_cache(user_name: str) -> tuple[Response, int]:
        removed = agents.invalidate_agent(user_name)
        return success({"user_name": user_name, "cache_removed": removed})

    return app
