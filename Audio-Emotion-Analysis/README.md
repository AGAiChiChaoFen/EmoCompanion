# Audio-Emotion-Analysis

面向老人的语音陪护服务：用户语音输入 → ASR 转写 + 情绪识别 → 陪护回复生成（本地 EmoLLM 或云端 PersonaVLM）→ TTS 语音合成（待接入）。支持 DeepFace 人脸情绪作为补充输入。

## 核心能力

| 环节 | 方案 | 说明 |
|---|---|---|
| 音频转写 + 情绪识别 | `Qwen/Qwen2-Audio-7B-Instruct`（本地） | 输出固定结构 `{"asr": "...", "emotion": "..."}` |
| 陪护回复生成 | PersonaVLM（阿里云百炼 API，模型 API 驱动） | 长期记忆/人格演化，SSE 流式（本地 EmoLLM 已暂停使用） |
| 人脸情绪识别 | DeepFace（本地，集成进主服务） | 中文情绪标签，作为情绪补充输入 |
| 语音合成 | `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` | 模型与代码已就绪，服务尚未接入（见已知问题） |

**PersonaVLM 云端后端**：对话服务核心，纯 API 驱动（Qwen3.7-Plus，OpenAI 兼容接口），不加载本地大模型。用户数据（记忆/人格/会话）持久化到 `output/{user_id}/user_data.json`。

## 快速开始

### 1. 环境配置

环境由 uv 管理（`.python-version` = 3.12.10）：

```bash
uv sync
```

### 2. 准备模型

```bash
uv run downloadmodels.py   # 从 ModelScope 下载 Qwen2-Audio 到 audio_emotion/pretrained_models/，并把路径写入 .env
```

DeepFace 权重目录由 `.env` 的 `DEEPFACE_HOME` 指定（缺省项目根 `deepface_weights/`）。

### 3. 配置 .env

复制 `.env.example` 为 `.env` 并填写：

- `MODEL_PATH_*`：本地模型路径（`downloadmodels.py` 会自动写入）
- `DEEPFACE_HOME`：DeepFace 权重目录（Windows 用正斜杠绝对路径，如 `D:/path/deepface_weights`）
- `FASTAPI_HOST` / `FASTAPI_PORT`：服务监听地址（默认 `127.0.0.1:9010`）
- `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL` / `DASHSCOPE_DEFAULT_MODEL`：**对话服务依赖**（PersonaVLM 云端，未配置时 `/persona/chat` 返回 503）

### 4. 启动服务

```bash
uv run python -m src.api.main
```

服务启动时加载本地模型（audio + emollm），**加载失败自动降级启动**：`/health` 返回 `ready=false`，本地路由返回 503，PersonaVLM 云端与 DeepFace 路由不受影响。

## API 接口

接口文档见 [API-接口文档.md](API-接口文档.md)。

| 路径 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 服务健康状态 |
| `/asr` | POST | 音频转写 + 情绪识别 |
| `/face-emotion` | POST | 人脸情绪识别 |
| `/persona/chat` | POST | PersonaVLM 陪护对话（长期记忆/人格演化） |
| `/persona/chat/stream` | POST | PersonaVLM 流式对话（SSE） |

## 项目结构

```
src/api/            # FastAPI 服务层（main.py 主入口、schemas/、services/）
src/                # PersonaVLM 适配层（QwenAdapter 等，与上游保持一致以便同步）
PersonaVLM/         # PersonaVLM 智能体核心（长期记忆/人格演化/检索）
audio_emotion/      # 本地模型加载与推理（load_models/、utils/、qwen_tts/）
checkpoints/        # 嵌入模型权重（MiniLM）
output/{user_id}/   # PersonaVLM 用户数据（记忆/人格/会话）
```

## 部署说明

- 必须从项目根目录启动（`PersonaVLM/` 是 PEP 420 命名空间包，依赖项目根在 sys.path）
- `.env` 按部署机器维护：Linux 服务器用 `/mnt1/...` 路径，Windows 本机用正斜杠绝对路径
- 模型路径与 DeepFace 权重缺失时服务走降级路径，不影响 PersonaVLM 云端链路

## 已知问题

- **EmoLLM 已暂停使用**：`main.py` 中 EmoLLM 加载/路由/helper 已注释，对话服务统一走 PersonaVLM 云端（`/emollm` 返回 404）
- `/tts`、`/asr-emollm`、`/pipeline` 路由在 `src/api/main.py` 中被注释，TTS 模型加载未接入服务
- PersonaVLM 的 CLIP 视觉嵌入与 GroundingDINO 检测器依赖 `checkpoints/openai-clip` 与 `~/.cache/autodistill/` 权重（当前只复制了 MiniLM 文本模型；纯语音场景不触发视觉路径）
