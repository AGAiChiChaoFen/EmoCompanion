from __future__ import annotations

import importlib
import inspect
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol

from logger import logger

# ASR 统一适配层：
# 1) 把不同后端输出归一化为 AsrResult，便于上层按统一字段消费；
# 2) 在空音频、SDK 版本差异、网络异常等场景下做可控回退；
# 3) 保持“尽量返回可用文本”的策略，降低实时链路中断概率。


@dataclass
class AsrResult:
    transcript: str
    source: str
    request_id: str = ""
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "transcript": self.transcript,
            "source": self.source,
        }
        if self.request_id:
            payload["request_id"] = self.request_id
        if self.extra:
            payload.update(self.extra)
        return payload


class AsrBackend(Protocol):
    name: str

    def transcribe(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        hint_text: str,
        sessionid: int,
        mode: str,
    ) -> AsrResult:
        ...


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _estimate_audio_duration_seconds(audio_bytes: bytes) -> float:
    if not audio_bytes:
        return 0.0
    return float(len(audio_bytes)) / 32000.0


def _extract_text_from_obj(obj: Any) -> str:
    def _looks_like_request_id(text: str) -> bool:
        value = (text or "").strip().lower()
        if len(value) < 24:
            return False
        if re.fullmatch(r"[0-9a-f]{24,64}", value):
            return True
        if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f\-]{27,}", value):
            return True
        return False

    def _extract(value: Any, key_hint: str = "") -> str:
        hint = (key_hint or "").strip().lower()

        if value is None:
            return ""

        if isinstance(value, str):
            text = value.strip()
            if not text:
                return ""

            # 避免把 request_id、trace_id 这类元数据误当作转写文本。
            if _looks_like_request_id(text):
                return ""
            if any(token in hint for token in ("request", "trace", "task", "status", "code", "message", "msg", "id")):
                return ""
            return text

        if isinstance(value, list):
            chunks = [_extract(x, key_hint=hint) for x in value]
            return "".join([x for x in chunks if x]).strip()

        if isinstance(value, dict):
            preferred_keys = [
                "text",
                "transcript",
                "sentence",
                "content",
                "utterance",
            ]
            for key in preferred_keys:
                if key in value:
                    text = _extract(value.get(key), key_hint=key)
                    if text:
                        return text

            container_keys = [
                "output",
                "data",
                "result",
                "results",
                "payload",
                "response",
                "sentences",
                "segments",
                "alternatives",
            ]
            for key in container_keys:
                if key in value:
                    text = _extract(value.get(key), key_hint=key)
                    if text:
                        return text

            for key, nested in value.items():
                key_lower = str(key).strip().lower()
                if any(token in key_lower for token in ("request", "trace", "task", "status", "code", "message", "msg", "id", "usage", "latency", "timestamp")):
                    continue
                text = _extract(nested, key_hint=key_lower)
                if text:
                    return text

        return ""

    return _extract(obj)


def _normalize_custom_result(raw: Any, default_source: str) -> AsrResult:
    if isinstance(raw, AsrResult):
        return raw

    if isinstance(raw, str):
        return AsrResult(transcript=raw.strip(), source=default_source)

    if isinstance(raw, dict):
        transcript = str(
            raw.get("transcript")
            or raw.get("text")
            or raw.get("sentence")
            or ""
        ).strip()
        source = str(raw.get("source") or default_source)
        request_id = str(raw.get("request_id") or raw.get("requestId") or "")
        extra = dict(raw)
        for key in ("transcript", "text", "sentence", "source", "request_id", "requestId"):
            extra.pop(key, None)
        return AsrResult(
            transcript=transcript,
            source=source,
            request_id=request_id,
            extra=extra or None,
        )

    return AsrResult(transcript="", source=default_source)


class CustomAsrBackend:
    name = "custom"

    def __init__(self, handler_path: str):
        self.handler_path = handler_path
        self.handler = self._load_handler(handler_path)

    def _load_handler(self, handler_path: str) -> Callable[..., Any]:
        if not handler_path or ":" not in handler_path:
            raise ValueError(
                "ASR custom handler must be in module:function format, e.g. mypkg.asr:transcribe"
            )
        module_name, func_name = handler_path.split(":", 1)
        module = importlib.import_module(module_name)
        handler = getattr(module, func_name, None)
        if not callable(handler):
            raise ValueError(f"ASR custom handler is not callable: {handler_path}")
        return handler

    def transcribe(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        hint_text: str,
        sessionid: int,
        mode: str,
    ) -> AsrResult:
        try:
            result = self.handler(
                audio_bytes=audio_bytes,
                filename=filename,
                hint_text=hint_text,
                sessionid=sessionid,
                mode=mode,
            )
        except TypeError:
            result = self.handler(audio_bytes, filename, hint_text, sessionid, mode)
        return _normalize_custom_result(result, default_source="custom_asr")


class FunAsrBackend:
    name = "funasr"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        sample_rate: int,
        language_hint: str,
        max_sentence_silence: int,
        semantic_punctuation_enabled: bool,
    ):
        self.api_key = api_key.strip()
        self.base_url = (base_url or "").strip() or "https://dashscope.aliyuncs.com/api/v1"
        self.model = (model or "").strip() or "fun-asr-realtime"
        self.sample_rate = int(sample_rate or 16000)
        self.language_hint = (language_hint or "").strip().lower()
        self.max_sentence_silence = int(max_sentence_silence or 1000)
        self.semantic_punctuation_enabled = bool(semantic_punctuation_enabled)

        self._Recognition = None
        self._RecognitionCallback = None
        self._dashscope = None
        self._available = False
        self._init_sdk()

    def _init_sdk(self) -> None:
        if not self.api_key:
            logger.warning("funasr disabled: missing api key, set --FUNASR_API_KEY or --QWEN_API_KEY or DASHSCOPE_API_KEY")
            return

        try:
            import dashscope
            from dashscope.audio.asr import Recognition, RecognitionCallback

            self._dashscope = dashscope
            dashscope.base_http_api_url = self.base_url
            dashscope.api_key = self.api_key
            os.environ["DASHSCOPE_API_KEY"] = self.api_key
            self._Recognition = Recognition
            self._RecognitionCallback = RecognitionCallback
            self._available = True
        except Exception:
            logger.exception("funasr init failed: cannot import dashscope.audio.asr.Recognition")
            self._available = False

    @property
    def available(self) -> bool:
        return bool(self._available and self._Recognition is not None)

    def _ensure_auth_context(self) -> None:
        if not self.api_key:
            return

        # 部分 DashScope SDK 版本只会从全局环境读取 key，这里做双写以提升兼容性。
        os.environ["DASHSCOPE_API_KEY"] = self.api_key
        if self._dashscope is not None:
            try:
                self._dashscope.api_key = self.api_key
            except Exception:
                pass
            try:
                self._dashscope.base_http_api_url = self.base_url
            except Exception:
                pass

    def _create_noop_callback(self):
        callback_base = self._RecognitionCallback
        if callback_base is None:
            class _FallbackNoopCallback:
                def on_open(self):
                    pass

                def on_event(self, result):
                    pass

                def on_complete(self):
                    pass

                def on_error(self, result):
                    pass

                def on_close(self):
                    pass

            return _FallbackNoopCallback()

        class _NoopCallback(callback_base):
            def on_open(self):
                pass

            def on_event(self, result):
                pass

            def on_complete(self):
                pass

            def on_error(self, result):
                pass

            def on_close(self):
                pass

        return _NoopCallback()

    def _build_recognition_kwargs(self) -> Dict[str, Any]:
        if self._Recognition is None:
            raise RuntimeError("funasr backend is not initialized")

        init_sig = inspect.signature(self._Recognition.__init__)
        params = init_sig.parameters
        supported = {name for name in params.keys() if name != "self"}

        raw_kwargs: Dict[str, Any] = {
            "model": self.model,
            "format": "wav",
            "sample_rate": self.sample_rate,
            "punctuation_prediction_enabled": True,
            "semantic_punctuation_enabled": self.semantic_punctuation_enabled,
            "max_sentence_silence": self.max_sentence_silence,
            "language_hints": [self.language_hint] if self.language_hint else None,
            "api_key": self.api_key,
        }
        alias_map = {
            "sample_rate": ["sampleRate"],
            "punctuation_prediction_enabled": ["punctuationPredictionEnabled"],
            "semantic_punctuation_enabled": ["semanticPunctuationEnabled"],
            "max_sentence_silence": ["maxSentenceSilence"],
            "language_hints": ["languageHints"],
            "api_key": ["apiKey"],
        }

        kwargs: Dict[str, Any] = {}
        for key, value in raw_kwargs.items():
            if value is None:
                continue
            if key in supported:
                kwargs[key] = value
                continue
            for alias in alias_map.get(key, []):
                if alias in supported:
                    kwargs[alias] = value
                    break

        callback_param = next((name for name in supported if "callback" in name.lower()), None)
        if callback_param and callback_param not in kwargs:
            kwargs[callback_param] = self._create_noop_callback()

        required = [
            p.name
            for p in params.values()
            if p.name != "self"
            and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
            and p.default is inspect._empty
        ]

        fallback_values = {
            "model": self.model,
            "format": "wav",
            "sample_rate": self.sample_rate,
            "sampleRate": self.sample_rate,
            "api_key": self.api_key,
            "apiKey": self.api_key,
        }
        for req_name in required:
            if req_name not in kwargs and req_name in fallback_values:
                kwargs[req_name] = fallback_values[req_name]

        missing = [name for name in required if name not in kwargs]
        if missing:
            raise RuntimeError(
                f"funasr recognition init missing required args after adaptation: {missing}"
            )

        return kwargs

    def _invoke_recognition_call(self, recognition, wav_path: str):
        self._ensure_auth_context()
        call_fn = recognition.call
        try:
            call_sig = inspect.signature(call_fn)
            call_params = call_sig.parameters
            api_key_param = None
            if "api_key" in call_params:
                api_key_param = "api_key"
            elif "apiKey" in call_params:
                api_key_param = "apiKey"

            call_kwargs: Dict[str, Any] = {}
            if api_key_param:
                call_kwargs[api_key_param] = self.api_key

            if "file" in call_params:
                call_kwargs["file"] = wav_path
                return call_fn(**call_kwargs)
            if "audio" in call_params:
                call_kwargs["audio"] = wav_path
                return call_fn(**call_kwargs)

            if api_key_param:
                try:
                    return call_fn(wav_path, **{api_key_param: self.api_key})
                except TypeError:
                    pass
            return call_fn(wav_path)
        except TypeError:
            # 最后兜底：面对未知签名时再尝试一次宽松调用。
            try:
                return call_fn(file=wav_path, api_key=self.api_key)
            except TypeError:
                return call_fn(wav_path)

    def _convert_to_wav_16k(self, src_path: str, out_path: str) -> bool:
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            src_path,
            "-ac",
            "1",
            "-ar",
            str(self.sample_rate),
            "-acodec",
            "pcm_s16le",
            out_path,
        ]
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            if proc.returncode != 0:
                logger.warning("funasr ffmpeg convert failed: code=%s, stderr=%s", proc.returncode, (proc.stderr or "")[:500])
                return False
            return os.path.exists(out_path) and os.path.getsize(out_path) > 44
        except FileNotFoundError:
            logger.warning("funasr ffmpeg is not installed, cannot convert uploaded audio to wav")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("funasr ffmpeg convert timeout")
            return False
        except Exception:
            logger.exception("funasr ffmpeg convert exception")
            return False

    def _extract_transcript(self, result: Any) -> str:
        # 先尝试 SDK 文档推荐的 sentence 访问路径。
        try:
            sentence = result.get_sentence()
            text = _extract_text_from_obj(sentence)
            if text:
                return text
        except Exception:
            pass

        # 若失败，再回退到原始 response 结构中提取文本。
        try:
            response = result.get_response()
            text = _extract_text_from_obj(response)
            if text:
                return text
        except Exception:
            pass

        text = _extract_text_from_obj(result)
        return text

    def _extract_request_id(self, result: Any) -> str:
        try:
            request_id = result.get_request_id()
            return str(request_id or "")
        except Exception:
            return ""

    def _recognize_wav(self, wav_path: str) -> AsrResult:
        if not self.available:
            raise RuntimeError("funasr backend is not available")

        self._ensure_auth_context()
        start = time.perf_counter()
        recognition_kwargs = self._build_recognition_kwargs()
        recognition = self._Recognition(**recognition_kwargs)
        try:
            setattr(recognition, "api_key", self.api_key)
        except Exception:
            pass
        result = self._invoke_recognition_call(recognition, wav_path)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        transcript = self._extract_transcript(result).strip()
        request_id = self._extract_request_id(result)
        logger.info("funasr call finished in %dms request_id=%s", elapsed_ms, request_id)
        return AsrResult(
            transcript=transcript,
            source="funasr_api",
            request_id=request_id,
            extra={"elapsedMs": elapsed_ms},
        )

    def transcribe(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        hint_text: str,
        sessionid: int,
        mode: str,
    ) -> AsrResult:
        duration_s = round(_estimate_audio_duration_seconds(audio_bytes), 2)
        if not audio_bytes:
            if hint_text:
                return AsrResult(
                    transcript=hint_text,
                    source="browser_hint",
                    extra={"durationSec": duration_s, "mode": mode, "filename": filename},
                )
            return AsrResult(
                transcript="",
                source="funasr_empty_audio",
                extra={"durationSec": duration_s, "mode": mode, "filename": filename},
            )

        if not self.available:
            fallback_source = "browser_hint_fallback" if hint_text else "funasr_unavailable"
            return AsrResult(
                transcript=hint_text.strip(),
                source=fallback_source,
                extra={"durationSec": duration_s, "mode": mode, "filename": filename},
            )

        suffix = os.path.splitext(filename or "")[1].lower() or ".bin"
        with tempfile.TemporaryDirectory(prefix="funasr_upload_") as temp_dir:
            src_path = os.path.join(temp_dir, f"input{suffix}")
            wav_path = os.path.join(temp_dir, "input_16k.wav")
            with open(src_path, "wb") as fp:
                fp.write(audio_bytes)

            converted = self._convert_to_wav_16k(src_path, wav_path)
            if not converted:
                fallback_source = "browser_hint_fallback" if hint_text else "funasr_convert_failed"
                return AsrResult(
                    transcript=hint_text.strip(),
                    source=fallback_source,
                    extra={
                        "durationSec": duration_s,
                        "mode": mode,
                        "filename": filename,
                    },
                )

            try:
                result = self._recognize_wav(wav_path)
            except Exception:
                logger.exception("funasr recognize failed")
                fallback_source = "browser_hint_fallback" if hint_text else "funasr_request_failed"
                return AsrResult(
                    transcript=hint_text.strip(),
                    source=fallback_source,
                    extra={
                        "durationSec": duration_s,
                        "mode": mode,
                        "filename": filename,
                    },
                )

            extra = dict(result.extra or {})
            extra.update({"durationSec": duration_s, "mode": mode, "filename": filename})
            return AsrResult(
                transcript=result.transcript,
                source=result.source,
                request_id=result.request_id,
                extra=extra,
            )


def build_asr_backend(opt) -> AsrBackend:
    asr_backend = str(getattr(opt, "asr_backend", "auto") or "auto").strip().lower()
    custom_handler_path = str(getattr(opt, "ASR_CUSTOM_HANDLER", "") or "").strip()

    # auto 模式下优先使用显式配置的自定义处理器，便于快速插拔私有 ASR。
    if asr_backend == "custom" or (asr_backend == "auto" and custom_handler_path):
        backend = CustomAsrBackend(custom_handler_path)
        if asr_backend == "custom":
            logger.info("ASR backend: custom (%s)", custom_handler_path)
        else:
            logger.info("ASR backend: custom(auto) (%s)", custom_handler_path)
        return backend

    # 默认路径：优先 funasr；不可用时仍返回 funasr 后端，由调用处得到明确的 unavailable 状态。
    funasr_api_key = (
        str(getattr(opt, "FUNASR_API_KEY", "") or "").strip()
        or str(getattr(opt, "QWEN_API_KEY", "") or "").strip()
        or str(os.getenv("DASHSCOPE_API_KEY", "") or "").strip()
    )
    funasr_backend = FunAsrBackend(
        api_key=funasr_api_key,
        base_url=str(getattr(opt, "FUNASR_BASE_URL", "") or "").strip() or str(getattr(opt, "QWEN_BASE_URL", "") or "").strip(),
        model=str(getattr(opt, "FUNASR_MODEL", "fun-asr-realtime") or "fun-asr-realtime").strip(),
        sample_rate=int(_safe_float(getattr(opt, "FUNASR_SAMPLE_RATE", 16000), 16000.0)),
        language_hint=str(getattr(opt, "FUNASR_LANGUAGE_HINT", "zh") or "zh").strip(),
        max_sentence_silence=int(_safe_float(getattr(opt, "FUNASR_MAX_SENTENCE_SILENCE", 1000), 1000.0)),
        semantic_punctuation_enabled=bool(getattr(opt, "FUNASR_SEMANTIC_PUNCTUATION", False)),
    )

    if asr_backend == "funasr":
        if funasr_backend.available:
            logger.info("ASR backend: funasr")
        else:
            logger.warning("ASR backend=funasr but unavailable; no fallback transcript will be generated")
        return funasr_backend

    if funasr_backend.available:
        logger.info("ASR backend: funasr(auto)")
        return funasr_backend

    logger.warning("ASR backend auto found no available real backend; using unavailable funasr backend")
    return funasr_backend
