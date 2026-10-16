"""
配置管理模块。

从 .env 文件和 CSV 密钥文件中加载 API 配置，
提供统一的配置访问接口，支持环境变量覆盖。
"""

import os
import csv
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# 项目根目录
ROOT_DIR = Path(__file__).resolve().parent.parent

# 环境变量前缀 → 提供商名称 映射
_PREFIX_TO_PROVIDER = {
    "DASHSCOPE": "qwen",
    "OPENAI": "openai",
    "ANTHROPIC": "anthropic",
}


def _resolve_env(key: str, default: str = "") -> str:
    """读取环境变量，同时检查带前缀和不带前缀的版本。

    优先级：带前缀变量 > 不带前缀变量 > default。
    例如 key="DASHSCOPE_API_KEY" 时，先查 DASHSCOPE_API_KEY，
    再查 API_KEY，都没有则返回 default。
    """
    value = os.getenv(key, "")
    if value:
        return value

    # 尝试去掉前缀查找通用变量
    parts = key.split("_", 1)
    if len(parts) == 2:
        generic_key = parts[1]
        return os.getenv(generic_key, default)

    return default


@dataclass
class APIConfig:
    """单个 API 提供商的配置。"""

    provider: str                         # 提供商名称，如 "qwen"、"openai"
    api_key: str                          # API 密钥
    base_url: str                         # API 端点 URL
    default_model: str                    # 默认模型名称
    enable_thinking: bool = False         # 是否启用模型内置思考模式
    extra_params: dict = field(default_factory=dict)  # 额外参数

    @classmethod
    def from_env(cls, provider: str) -> "APIConfig":
        """从环境变量或 .env 文件加载配置。

        环境变量查找规则（以 DASHSCOPE 前缀为例）：
            DASHSCOPE_API_KEY      → api_key（必需）
            DASHSCOPE_BASE_URL     → base_url
            DASHSCOPE_DEFAULT_MODEL → default_model
            DASHSCOPE_ENABLE_THINKING → enable_thinking
            若带前缀变量不存在，回退到不带前缀的通用变量
            （如 API_KEY、BASE_URL、DEFAULT_MODEL）。

        Args:
            provider: 提供商标识（环境变量前缀），如 "DASHSCOPE"。

        Returns:
            APIConfig 实例。

        Raises:
            ValueError: 缺少必要的 API Key 配置。
        """
        prefix = provider.upper()

        api_key = _resolve_env(f"{prefix}_API_KEY")
        base_url = _resolve_env(f"{prefix}_BASE_URL")
        default_model = _resolve_env(f"{prefix}_DEFAULT_MODEL")
        enable_thinking = (
            _resolve_env(f"{prefix}_ENABLE_THINKING", "false").lower() == "true"
        )

        if not api_key:
            raise ValueError(
                f"缺少 {prefix}_API_KEY 环境变量，"
                f"请在 .env 文件中设置或导出该变量"
            )

        # 将环境变量前缀映射为短名称
        short_name = _PREFIX_TO_PROVIDER.get(prefix, prefix.lower())

        return cls(
            provider=short_name,
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            enable_thinking=enable_thinking,
        )


def load_dotenv(env_path: Optional[Path] = None) -> None:
    """加载 .env 文件到环境变量。

    如果 python-dotenv 不可用，则手动解析 .env 文件。

    Args:
        env_path: .env 文件路径，默认为项目根目录下的 .env。
    """
    if env_path is None:
        env_path = ROOT_DIR / ".env"

    if not env_path.exists():
        return

    # 优先使用 python-dotenv
    try:
        from dotenv import load_dotenv as _load
        _load(env_path, override=True)
        return
    except ImportError:
        pass

    # 手动解析回退方案
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value


def load_csv_config(csv_path: Optional[Path] = None) -> dict[str, str]:
    """从阿里云百炼平台导出的 CSV 密钥文件中解析配置。

    CSV 格式示例:
        id,6080637
        apiKey,sk-ws-H.xxx
        apiHost,ws-xxx.cn-beijing.maas.aliyuncs.com
        openAiCompatible,https://ws-xxx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1

    Args:
        csv_path: CSV 文件路径，默认自动查找根目录下的 CSV 文件。

    Returns:
        包含 api_key, base_url, dashscope_url 的字典。
    """
    if csv_path is None:
        csv_files = list(ROOT_DIR.glob("*.csv"))
        if not csv_files:
            return {}
        csv_path = csv_files[0]

    config: dict[str, str] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2:
                key, value = row[0].strip(), row[1].strip()
                if key == "apiKey":
                    config["api_key"] = value
                elif key == "openAiCompatible":
                    config["base_url"] = value
                elif key == "dashScope":
                    config["dashscope_url"] = value
                elif key == "apiHost":
                    config["api_host"] = value
    return config


def init_config() -> APIConfig:
    """初始化全局配置。

    加载顺序：
        1. 手动设置的 os.environ 变量（最高优先级）
        2. .env 文件
        3. 根目录 CSV 文件（作为 API Key 的备选来源）

    Returns:
        APIConfig 实例。
    """
    # 加载 .env
    load_dotenv()

    # 如果环境变量中还没有 API Key，尝试从 CSV 读取
    if not os.getenv("DASHSCOPE_API_KEY"):
        csv_config = load_csv_config()
        if csv_config.get("api_key"):
            os.environ["DASHSCOPE_API_KEY"] = csv_config["api_key"]
        if csv_config.get("base_url") and not os.getenv("DASHSCOPE_BASE_URL"):
            os.environ["DASHSCOPE_BASE_URL"] = csv_config["base_url"]

    # 设置默认值
    os.environ.setdefault(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    os.environ.setdefault("DASHSCOPE_DEFAULT_MODEL", "qwen3.7-plus")

    return APIConfig.from_env("DASHSCOPE")
