#!/usr/bin/env python3
"""启动 PersonaVLM Flask API 服务。"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import warnings
from pathlib import Path
from typing import Optional, Sequence


warnings.filterwarnings("ignore")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="启动 PersonaVLM 记忆读取与推理 Flask API。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", help="监听地址，默认读取 PERSONA_API_HOST")
    parser.add_argument("--port", type=int, help="监听端口，默认读取 PERSONA_API_PORT")
    parser.add_argument("--output-root", type=Path, help="用户记忆输出根目录")
    parser.add_argument("--model-path", type=Path, help="PersonaVLM 模型目录")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="控制台日志级别")
    parser.add_argument("--preload-model", action="store_true", help="启动监听前加载 PersonaVLM 共享模型")
    parser.add_argument("--debug", action="store_true", help="启用 Flask 调试模式；生产环境不要使用")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        from persona_api import ApiSettings, create_app

        settings = ApiSettings.from_env().with_overrides(
            host=args.host,
            port=args.port,
            output_root=args.output_root,
            model_path=args.model_path,
            log_level=args.log_level,
        )
        configure_logging(settings.log_level)
        logger = logging.getLogger("persona_api.startup")
        logger.info("=" * 72)
        logger.info("PersonaVLM 记忆与推理 API 正在启动")
        logger.info("监听地址 | http://%s:%d", settings.host, settings.port)
        logger.info("记忆目录 | %s", settings.output_root)
        logger.info("模型目录 | %s", settings.model_path)
        logger.info("允许跨域 | %s", "，".join(settings.allowed_origins) or "未配置")
        logger.info("推理模式 | reasoning=%s | force_retrieve=%s", settings.reasoning_mode, settings.force_retrieve)
        logger.info("模型加载策略 | %s", "启动时预加载" if args.preload_model else "首次推理时懒加载")
        logger.info("=" * 72)

        settings.output_root.mkdir(parents=True, exist_ok=True)
        app = create_app(settings)
        if args.preload_model:
            logger.info("正在预加载 PersonaVLM 共享模型")
            app.extensions["agent_service"].preload_model()
            logger.info("PersonaVLM 共享模型预加载完成")
        app.run(
            host=settings.host,
            port=settings.port,
            debug=args.debug,
            threaded=True,
            use_reloader=args.debug,
        )
        return 0
    except KeyboardInterrupt:
        logging.getLogger("persona_api.startup").info("收到停止信号，API 服务已退出。")
        return 0
    except Exception:
        logging.basicConfig(level=logging.INFO, stream=sys.stdout, force=True)
        logging.getLogger("persona_api.startup").exception("API 服务启动失败")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
