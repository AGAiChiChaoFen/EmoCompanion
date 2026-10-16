"""API 业务异常。"""

from __future__ import annotations

from typing import Any, Optional


class ApiError(Exception):
    """可安全返回给调用方的业务异常。"""

    def __init__(
        self,
        title: str,
        detail: str,
        status_code: int,
        code: str,
        errors: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        super().__init__(detail)
        self.title = title
        self.detail = detail
        self.status_code = status_code
        self.code = code
        self.errors = errors or []


class ValidationError(ApiError):
    def __init__(self, detail: str, field: Optional[str] = None) -> None:
        errors = [{"field": field, "message": detail, "code": "INVALID_VALUE"}] if field else []
        super().__init__("请求参数不正确", detail, 422, "validation-error", errors)


class UserNotFoundError(ApiError):
    def __init__(self, user_name: str) -> None:
        super().__init__(
            "未找到用户记忆",
            f"用户“{user_name}”尚未生成记忆文件。",
            404,
            "memory-not-found",
        )


class MemoryFileError(ApiError):
    def __init__(self, detail: str) -> None:
        super().__init__("记忆文件不可用", detail, 500, "memory-file-error")


class ServiceNotReadyError(ApiError):
    def __init__(self, detail: str) -> None:
        super().__init__("推理服务尚未就绪", detail, 503, "service-not-ready")
