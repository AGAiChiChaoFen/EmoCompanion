from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from audio_emotion.load_models.load import load_audio_model
# from audio_emotion.load_models.load import load_emollm_model  # EmoLLM 已暂停使用（对话统一走 PersonaVLM）
from audio_emotion.utils.audio_asr_analysis import analysis_audio_with_path
# from audio_emotion.utils.emotion_llm_reply import emollm_reply_with_memory  # EmoLLM 已暂停使用
# from src.api.schemas.sch_emollm import EmoLLMInputRequest  # EmoLLM 已暂停使用
from src.api.schemas.sch_persona import PersonaChatRequest
from src.api.services.persona_agent import (
    compose_persona_query,
    manager as persona_manager,
    persona_configured,
)
from src.api.services.deepface import (
    analyze_face_dominant_emotion,
    read_deepface_home,
    save_uploaded_image,
)
from src.api.services.qwen_audio import cleanup_temp_file, save_uploaded_audio
from src.api.utils import read_model_path, read_server_host, read_server_port, read_server_reload, runtime_status
# from src.api.utils import normalize_session_id  # EmoLLM 已暂停使用

logger = logging.getLogger(__name__)


load_dotenv()  # 从 .env 文件加载环境变量


@dataclass
class ModelBundle:
    """
    模型对象集合。

    参数：
        audio_model: 音频分析模型对象。
        audio_processor: 音频分析处理器对象。
        # emollm_model: EmoLLM 文本生成模型对象。  # EmoLLM 已暂停使用
        # emollm_tokenizer: EmoLLM 分词器对象。  # EmoLLM 已暂停使用
        # qwen_tts_model: Qwen TTS 模型对象。

    返回：
        返回聚合后的模型集合，用于应用生命周期内复用。
    """

    audio_model: torch.nn.Module
    audio_processor: Any
    # emollm_model: torch.nn.Module  # EmoLLM 已暂停使用
    # emollm_tokenizer: Any  # EmoLLM 已暂停使用
    # qwen_tts_model: torch.nn.Module



def load_all_models() -> tuple[ModelBundle, dict[str, Any]]:
    """
    一次性加载全部模型并返回加载状态。

    参数：
        无。

    返回：
        返回二元组：
        {
            "第一个元素": ModelBundle 模型集合,
            "第二个元素": {
                "ready": 是否加载完成,
                "load_seconds": 各模型加载耗时,
                "loaded_at": 加载完成时间戳,
                "memory_after_load": 加载完成后的显存快照
            }
        }
    """
    load_seconds: dict[str, float] = {}

    started = time.time()
    audio_model_path = read_model_path("MODEL_PATH_QWEN_QWEN2_AUDIO_7B_INSTRUCT")
    audio_model, audio_processor = load_audio_model(audio_model_path)
    load_seconds["audio_model"] = round(time.time() - started, 3)

    # EmoLLM 已暂停使用（对话统一走 PersonaVLM 云端），仅保留音频模型
    # started = time.time()
    # emollm_model_path = read_model_path("MODEL_PATH_AJUPYTER_EMOLLM_QWEN2_7B_INSTRUCT_LORA")
    # emollm_model, emollm_tokenizer = load_emollm_model(emollm_model_path)
    # if getattr(emollm_tokenizer, "pad_token", None) is None:
    #     emollm_tokenizer.pad_token = emollm_tokenizer.eos_token
    # load_seconds["emollm_model"] = round(time.time() - started, 3)

    # started = time.time()
    # tts_model_path = read_model_path("MODEL_PATH_QWEN_QWEN3_TTS_12HZ_1_7B_CUSTOMVOICE")
    # qwen_tts_model = load_qwen_tts_model(tts_model_path)
    # load_seconds["tts_model"] = round(time.time() - started, 3)

    bundle = ModelBundle(
        audio_model=audio_model,
        audio_processor=audio_processor,
        # emollm_model=emollm_model,  # EmoLLM 已暂停使用
        # emollm_tokenizer=emollm_tokenizer,  # EmoLLM 已暂停使用
        # qwen_tts_model=qwen_tts_model,
    )
    status = {
        "ready": True,
        "load_seconds": load_seconds,
        "loaded_at": time.time(),
    }
    return bundle, status



@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    管理 FastAPI 生命周期并在启动时完成模型加载。

    参数：
        app: FastAPI 应用对象。

    返回：
        无。该异步上下文在进入时完成模型加载并写入 app.state，
        在退出时执行资源释放钩子（当前无需额外清理）。
    """
    load_dotenv()
    app.state.started_at = time.time()
    app.state.infer_lock = asyncio.Lock()
    # app.state.conversation_store = {}  # EmoLLM 已暂停使用（本地会话记忆不再需要）
    app.state.status = {
        "ready": False,
        "load_seconds": {},
        "loaded_at": None,
    }

    # 本地模型加载失败时降级启动：服务仍可用（PersonaVLM 云端路由不受影响），
    # 依赖本地模型的路由经 _require_local_models 返回 503。
    try:
        models, status = load_all_models()
    except Exception as exc:
        logger.exception("本地模型加载失败，服务以降级模式启动")
        models = None
        status = {
            "ready": False,
            "load_error": str(exc),
            "load_seconds": {},
            "loaded_at": None,
        }

    app.state.models = models
    app.state.status = status
    app.state.persona_configured = persona_configured()

    try:
        yield
    finally:
        # 当前模型对象由进程生命周期托管，此处预留资源释放扩展点。
        pass



def _require_local_models(app: FastAPI, need: set[str]) -> ModelBundle:
    """
    校验本地模型是否已加载，缺失时抛出 503。

    参数：
        app: FastAPI 应用对象。
        need: 所需子模型名称集合，如 {"audio_model"}。

    返回：
        已加载的 ModelBundle 模型集合。

    异常：
        本地模型未加载或所需子模型缺失时抛出 HTTPException(503)。
    """
    models: ModelBundle | None = app.state.models
    if models is None:
        detail = app.state.status.get("load_error", "本地模型未加载")
        raise HTTPException(status_code=503, detail=f"本地模型不可用：{detail}")
    missing = need - {name for name in dir(models) if not name.startswith("_")}
    if missing:
        raise HTTPException(status_code=503, detail=f"本地模型未加载：{sorted(missing)}")
    return models



# EmoLLM 已暂停使用：以下 helper 与 /emollm 路由整体注释，对话服务统一走
# /persona/chat（PersonaVLM 云端，模型 API 驱动）。恢复时取消注释即可。

# async def _run_emollm_local(
#     app: FastAPI, req: EmoLLMInputRequest, started: float
# ) -> dict[str, Any]:
#     """
#     使用本地 EmoLLM 模型生成陪护回复（带内存会话记忆）。
#
#     参数：
#         app: FastAPI 应用对象（读取模型与会话存储）。
#         req: 包含 asr、emotion、face_emotion、session_id 字段的请求对象。
#         started: 请求开始时间戳（秒），用于计算耗时。
#
#     返回：
#         返回阶段执行结果字典，结构为：
#         {
#             "result": 陪护回复文本,
#             "duration_seconds": 0.0,
#             "session_id": 会话标识符,
#             "prompt_tokens": 本轮输入 token 数,
#             "chat_history": 更新后的会话历史,
#             "history_rounds": 已保存对话轮数,
#             "provider": "emollm",
#         }
#
#     异常：
#         本地模型未加载时抛出 HTTPException(503)。
#     """
#     session_id = normalize_session_id(req.session_id)
#     models: ModelBundle = _require_local_models(app, {"emollm_model", "emollm_tokenizer"})
#     conversation_store: dict[str, list[dict[str, str]]] = app.state.conversation_store
#     history = conversation_store.get(session_id, [])
#     async with app.state.infer_lock:
#         memory_result = await emollm_reply_with_memory(
#             req.model_dump(),
#             conversation=history,
#             emollm_model=models.emollm_model,
#             emollm_tokenizer=models.emollm_tokenizer,
#         )
#         conversation_store[session_id] = memory_result["conversation"]
#     return {
#         "result": memory_result["reply"],
#         "duration_seconds": round(time.time() - started, 3),
#         "session_id": session_id,
#         "prompt_tokens": memory_result["prompt_tokens"],
#         "chat_history": memory_result["conversation"],
#         "history_rounds": len(memory_result["conversation"]) // 2,
#         "provider": "emollm",
#     }


# async def _run_persona_emollm(
#     app: FastAPI, req: EmoLLMInputRequest, started: float
# ) -> dict[str, Any]:
#     """
#     使用 PersonaVLM 云端后端生成陪护回复（长期记忆/人格演化）。
#
#     参数：
#         app: FastAPI 应用对象（读取 persona 配置状态）。
#         req: 包含 asr、emotion、face_emotion、user_id 字段的请求对象。
#         started: 请求开始时间戳（秒），用于计算耗时。
#
#     返回：
#         返回阶段执行结果字典，结构为：
#         {
#             "result": 陪护回复文本,
#             "duration_seconds": 0.0,
#             "session_id": user_id（persona 的记忆主键）,
#             "provider": "persona",
#             "remembering": 记忆信息字典或 None,
#             "reasoning": 推理链步骤列表,
#             "alignment": 大五人格分数字典,
#         }
#
#     异常：
#         DASHSCOPE_API_KEY 未配置时抛出 HTTPException(503)。
#     """
#     if not app.state.persona_configured:
#         raise HTTPException(
#             status_code=503,
#             detail="PersonaVLM 未配置：缺少 DASHSCOPE_API_KEY 环境变量",
#         )
#     query = compose_persona_query(req.asr, req.emotion, req.face_emotion)
#     result = await persona_manager.send_message(
#         user_id=req.user_id,
#         query=query,
#     )
#     return {
#         "result": result["response"],
#         "duration_seconds": round(time.time() - started, 3),
#         "session_id": req.user_id,
#         "provider": "persona",
#         "remembering": result.get("remembering"),
#         "reasoning": result.get("reasoning", []),
#         "alignment": result.get("alignment", {}),
#     }



def build_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用。

    参数：
        无。

    返回：
        返回已注册路由与生命周期事件的 FastAPI 应用实例。
    """
    app = FastAPI(
        title="Audio Emotion Analysis API",
        description="音频转写、情绪识别、陪护回复服务",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        """
        查询服务健康状态与模型加载信息。

        参数：
            无。

        返回：
            返回状态字典，包含 ready、load_seconds、memory_after_load、uptime_seconds、
            persona 配置状态、deepface_home 等字段。
        """
        status = runtime_status(app)
        status["persona"] = {"configured": app.state.persona_configured}
        status["deepface_home"] = str(read_deepface_home())
        return status

    @app.post("/asr")
    async def run_asr(audio_file: UploadFile = File(..., description="待处理音频文件")) -> dict[str, Any]:
        """
        接收上传音频并执行转写与情绪识别。

        参数：
            audio_file: 表单上传的音频文件字段，字段名固定为 audio_file。

        返回：
            返回阶段执行结果，结构为：
            {
                "result": {"asr": "...", "emotion": "..."},
                "duration_seconds": 0.0,
            }
        """
        temp_audio: Path | None = None
        models: ModelBundle = _require_local_models(app, {"audio_model", "audio_processor"})
        started = time.time()
        try:
            temp_audio = await save_uploaded_audio(audio_file)
            async with app.state.infer_lock:
                result = await analysis_audio_with_path(
                    temp_audio,
                    audio_model=models.audio_model,
                    audio_processor=models.audio_processor,
                )
            return {
                "result": result,
                "duration_seconds": round(time.time() - started, 3),
            }
        finally:
            cleanup_temp_file(temp_audio)

 
    @app.post("/face-emotion")
    async def run_face_emotion(image_file: UploadFile = File(..., description="待处理图片文件")) -> dict[str, str]:
        """
        接收上传图片并返回主导面部情绪（中文标签）。

        参数：
            image_file: 表单上传的图片文件字段，字段名固定为 image_file。

        返回：
            返回字典：
            {
                "dominant_emotion": "主导情绪标签（中文）"
            }
            权重目录缺失时返回 500；图片无清晰人脸或格式不支持时返回 400。
        """
        temp_image: Path | None = None
        try:
            temp_image = await save_uploaded_image(image_file)
            dominant_emotion = await analyze_face_dominant_emotion(temp_image)
            return {"dominant_emotion": dominant_emotion}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            cleanup_temp_file(temp_image)

    # EmoLLM 已暂停使用：/emollm 路由整体注释，对话服务统一走 /persona/chat。
    # @app.post("/emollm")
    # async def run_emollm(req: EmoLLMInputRequest) -> dict[str, Any]:
    #     """
    #     根据音频转写文本与情绪标签生成陪护回复。
    #
    #     provider 为 persona 时走 PersonaVLM 云端（长期记忆/人格）；为
    #     emollm 时走本地模型；为 auto 时优先 persona，失败自动回退本地。
    #
    #     参数：
    #         req: 包含 asr、emotion、face_emotion、provider、user_id 字段的请求对象。
    #
    #     返回：
    #         返回阶段执行结果，结构为：
    #         {
    #             "result": "陪护回复文本",
    #             "duration_seconds": 0.0,
    #             "session_id": "会话标识符（本地后端）或 user_id（persona 后端）",
    #             "prompt_tokens": "本轮输入 token 数（仅本地后端）",
    #             "chat_history": "会话历史（仅本地后端）",
    #             "history_rounds": "当前已保存对话轮数（仅本地后端）",
    #             "provider": "实际使用的后端 persona/emollm",
    #             "reasoning": "推理链（仅 persona 后端）",
    #             "alignment": "大五人格分数（仅 persona 后端）",
    #         }
    #
    #     异常：
    #         本地后端模型未加载或 persona 未配置时抛出 HTTPException(503)。
    #     """
    #     started = time.time()
    #
    #     if req.provider == "emollm":
    #         return await _run_emollm_local(app, req, started)
    #     if req.provider == "persona":
    #         return await _run_persona_emollm(app, req, started)
    #
    #     # auto：优先 persona，异常记日志后回退本地
    #     persona_error: Exception | None = None
    #     try:
    #         if app.state.persona_configured:
    #             return await _run_persona_emollm(app, req, started)
    #     except Exception as exc:
    #         persona_error = exc
    #         logger.warning("PersonaVLM 回复失败，回退本地 EmoLLM：%s", exc)
    #     try:
    #         return await _run_emollm_local(app, req, started)
    #     except Exception as exc:
    #         detail = f"persona 失败：{persona_error}；emollm 失败：{exc}" if persona_error else f"emollm 失败：{exc}"
    #         raise HTTPException(status_code=503, detail=detail) from exc

    @app.post("/persona/chat")
    async def run_persona_chat(req: PersonaChatRequest) -> dict[str, Any]:
        """
        使用 PersonaVLM 生成带长期记忆与人格演化的陪护回复。

        参数：
            req: 包含 user_id、asr、emotion、face_emotion、session_index 等字段的请求对象。

        返回：
            返回阶段执行结果，结构为：
            {
                "user_id": 用户标识,
                "response": 陪护回复文本,
                "remembering": 记忆信息字典或 None,
                "reasoning": 推理链步骤列表,
                "alignment": 大五人格分数字典,
                "duration_seconds": 0.0,
            }

        异常：
            DASHSCOPE_API_KEY 未配置时抛出 HTTPException(503)。
        """
        if not app.state.persona_configured:
            raise HTTPException(
                status_code=503,
                detail="PersonaVLM 未配置：缺少 DASHSCOPE_API_KEY 环境变量",
            )
        query = compose_persona_query(req.asr, req.emotion, req.face_emotion)
        started = time.time()
        result = await persona_manager.send_message(
            user_id=req.user_id,
            query=query,
            timestamp=req.timestamp,
            new_session=req.new_session,
            session_index=req.session_index,
        )
        return {
            "user_id": req.user_id,
            "response": result["response"],
            "remembering": result.get("remembering"),
            "reasoning": result.get("reasoning", []),
            "alignment": result.get("alignment", {}),
            "duration_seconds": round(time.time() - started, 3),
        }

    @app.post("/persona/chat/stream")
    async def run_persona_chat_stream(req: PersonaChatRequest):
        """
        使用 PersonaVLM 流式生成陪护回复（SSE）。

        参数：
            req: 包含 user_id、asr、emotion、face_emotion、session_index 等字段的请求对象。

        返回：
            SSE 事件流，事件序列为 think_chunk / step / answer_chunk / done / error，
            每个事件格式为 "event: {type}\\ndata: {json}\\n\\n"。

        异常：
            DASHSCOPE_API_KEY 未配置时抛出 HTTPException(503)。
        """
        if not app.state.persona_configured:
            raise HTTPException(
                status_code=503,
                detail="PersonaVLM 未配置：缺少 DASHSCOPE_API_KEY 环境变量",
            )
        query = compose_persona_query(req.asr, req.emotion, req.face_emotion)

        async def gen():
            try:
                async for ev in persona_manager.stream_chat(
                    user_id=req.user_id,
                    query=query,
                    timestamp=req.timestamp,
                    new_session=req.new_session,
                    session_index=req.session_index,
                ):
                    payload = {k: v for k, v in ev.items() if k != "type"}
                    yield f"event: {ev['type']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logger.exception("PersonaVLM 流式对话失败")
                yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    #region
    # @app.post("/tts")
    # async def run_tts(req: TTSInputRequest) -> dict[str, Any]:
    #     """
    #     执行文本转语音。

    #     参数：
    #         req: 包含 text 字段的请求对象。

    #     返回：
    #         返回阶段执行结果，结构为：
    #         {
    #             "result": "生成音频路径",
    #             "duration_seconds": 0.0,
    #         }
    #     """
    #     models: ModelBundle = app.state.models
    #     started = time.time()
    #     async with app.state.infer_lock:
    #         result_path = await audio_tts(req.text, qwen_tts_model=models.qwen_tts_model)
    #     return {
    #         "result": str(result_path),
    #         "duration_seconds": round(time.time() - started, 3),
    #     }
    

    # @app.post("/asr-emollm")
    # async def run_asr_emollm(
    #     audio_file: UploadFile = File(..., description="待处理音频文件"),
    #     session_id: str = Form("default", description="会话标识符"),
    # ) -> dict[str, Any]:
    #     """
    #     接收上传音频并执行 ASR 与 EmoLLM 两阶段流程。

    #     参数：
    #         audio_file: 表单上传的音频文件字段，字段名固定为 audio_file。
    #         session_id: 会话标识符。相同 session_id 会共享最近 10 轮对话记忆。
    #     返回：
    #         返回阶段执行结果，结构为：
    #         {
    #             "asr": {...},
    #             "emollm": {...},
    #             "session_id": "会话标识符",
    #             "total_seconds": 0.0
    #         }
    #     """
    #     normalized_session_id = normalize_session_id(session_id)
    #     temp_audio: Path | None = None
    #     models: ModelBundle = app.state.models
    #     conversation_store: dict[str, list[dict[str, str]]] = app.state.conversation_store
    #     history = conversation_store.get(normalized_session_id, [])
    #     started = time.time()
    #     try:
    #         temp_audio = await save_uploaded_audio(audio_file)
    #         async with app.state.infer_lock:
    #             asr_started = time.time()
    #             asr_result = await analysis_audio_with_path(
    #                 temp_audio,
    #                 audio_model=models.audio_model,
    #                 audio_processor=models.audio_processor,
    #             )
    #             asr_stage = {
    #                 "result": asr_result,
    #                 "duration_seconds": round(time.time() - asr_started, 3),
    #             }

    #             emollm_started = time.time()
    #             memory_result = await emollm_reply_with_memory(
    #                 asr_result,
    #                 conversation=history,
    #                 emollm_model=models.emollm_model,
    #                 emollm_tokenizer=models.emollm_tokenizer,
    #             )
    #             conversation_store[normalized_session_id] = memory_result["conversation"]
    #             emollm_stage = {
    #                 "result": memory_result["reply"],
    #                 "duration_seconds": round(time.time() - emollm_started, 3),
    #                 "prompt_tokens": memory_result["prompt_tokens"],
    #                 "history_rounds": len(memory_result["conversation"]) // 2,
    #             }

    #         return {
    #             "asr": asr_stage,
    #             "emollm": emollm_stage,
    #             "session_id": normalized_session_id,
    #             "total_seconds": round(time.time() - started, 3),
    #         }
    #     finally:
    #         cleanup_temp_file(temp_audio)

    # @app.post("/pipeline")
    # async def run_pipeline(
    #     audio_file: UploadFile = File(..., description="待处理音频文件"),
    #     session_id: str = Form("default", description="会话标识符"),
    # ) -> dict[str, Any]:
    #     """
    #     接收上传音频并执行端到端流程：ASR/情绪识别 -> EmoLLM -> TTS。

    #     参数：
    #         audio_file: 表单上传的音频文件字段，字段名固定为 audio_file。
    #         session_id: 会话标识符。相同 session_id 会共享最近 10 轮对话记忆。

    #     返回：
    #         返回完整流程结果，结构为：
    #         {
    #             "asr": {...},
    #             "emollm": {...},
    #             "tts": {...},
    #             "session_id": "会话标识符",
    #             "total_seconds": 0.0
    #         }
    #     """
    #     normalized_session_id = normalize_session_id(session_id)
    #     temp_audio: Path | None = None
    #     models: ModelBundle = app.state.models
    #     conversation_store: dict[str, list[dict[str, str]]] = app.state.conversation_store
    #     history = conversation_store.get(normalized_session_id, [])
    #     started = time.time()
    #     try:
    #         temp_audio = await save_uploaded_audio(audio_file)
    #         async with app.state.infer_lock:
    #             asr_started = time.time()
    #             asr_result = await analysis_audio_with_path(
    #                 temp_audio,
    #                 audio_model=models.audio_model,
    #                 audio_processor=models.audio_processor,
    #             )
    #             asr_stage = {
    #                 "result": asr_result,
    #                 "duration_seconds": round(time.time() - asr_started, 3),
    #             }

    #             emollm_started = time.time()
    #             memory_result = await emollm_reply_with_memory(
    #                 asr_result,
    #                 conversation=history,
    #                 emollm_model=models.emollm_model,
    #                 emollm_tokenizer=models.emollm_tokenizer,
    #             )
    #             conversation_store[normalized_session_id] = memory_result["conversation"]
    #             emollm_stage = {
    #                 "result": memory_result["reply"],
    #                 "duration_seconds": round(time.time() - emollm_started, 3),
    #                 "prompt_tokens": memory_result["prompt_tokens"],
    #                 "history_rounds": len(memory_result["conversation"]) // 2,
    #             }

    #             tts_started = time.time()
    #             tts_result_path = await audio_tts(
    #                 memory_result["reply"],
    #                 qwen_tts_model=models.qwen_tts_model,
    #             )
    #             tts_stage = {
    #                 "result": str(tts_result_path),
    #                 "duration_seconds": round(time.time() - tts_started, 3),
    #             }

    #         return {
    #             "asr": asr_stage,
    #             "emollm": emollm_stage,
    #             "tts": tts_stage,
    #             "session_id": normalized_session_id,
    #             "total_seconds": round(time.time() - started, 3),
    #         }
    #     finally:
    #         cleanup_temp_file(temp_audio)
    #endregion
        

    return app


app = build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=read_server_host(),
        port=read_server_port(),
        reload=read_server_reload(),
    )