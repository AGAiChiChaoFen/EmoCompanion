"""集中管理 API 服务配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PROJECT_DIR = Path(__file__).resolve().parents[1]


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须是整数，当前值为：{raw}") from exc
    if value < minimum:
        raise ValueError(f"环境变量 {name} 不能小于 {minimum}。")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"环境变量 {name} 必须是 true/false，当前值为：{raw}")


@dataclass(frozen=True)
class ApiSettings:
    """Flask API 的不可变运行配置。"""

    host: str
    port: int
    output_root: Path
    model_path: Path
    allowed_origins: tuple[str, ...]
    log_level: str
    max_body_bytes: int
    force_retrieve: bool
    reasoning_mode: bool

    @classmethod
    def from_env(cls) -> "ApiSettings":
        origins = tuple(
            item.strip()
            for item in os.getenv(
                "PERSONA_API_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:9010,http://127.0.0.1:9010,http://119.45.194.33:9010",
            ).split(",")
            if item.strip()
        )
        log_level = os.getenv("PERSONA_API_LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"PERSONA_API_LOG_LEVEL 不受支持：{log_level}")
        return cls(
            host=os.getenv("PERSONA_API_HOST", "0.0.0.0").strip(),
            port=_env_int("PERSONA_API_PORT", 9001),
            output_root=Path(
                os.getenv("PERSONA_API_OUTPUT_ROOT", str(PROJECT_DIR / "output"))
            ).expanduser().resolve(strict=False),
            model_path=Path(
                os.getenv("PERSONA_API_MODEL_PATH", str(PROJECT_DIR / "checkpoints" / "rl"))
            ).expanduser().resolve(strict=False),
            allowed_origins=origins,
            log_level=log_level,
            max_body_bytes=_env_int("PERSONA_API_MAX_BODY_BYTES", 1024 * 1024),
            force_retrieve=_env_bool("PERSONA_API_FORCE_RETRIEVE", False),
            reasoning_mode=_env_bool("PERSONA_API_REASONING_MODE", True),
        )

    def with_overrides(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        output_root: Optional[Path] = None,
        model_path: Optional[Path] = None,
        log_level: Optional[str] = None,
    ) -> "ApiSettings":
        return ApiSettings(
            host=host or self.host,
            port=port or self.port,
            output_root=(output_root or self.output_root).expanduser().resolve(strict=False),
            model_path=(model_path or self.model_path).expanduser().resolve(strict=False),
            allowed_origins=self.allowed_origins,
            log_level=(log_level or self.log_level).upper(),
            max_body_bytes=self.max_body_bytes,
            force_retrieve=self.force_retrieve,
            reasoning_mode=self.reasoning_mode,
        )
