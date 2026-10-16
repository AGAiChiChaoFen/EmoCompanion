# Audio-Emotion-Analysis API 接口文档

语音陪护服务 HTTP 接口说明。

- **服务名称**：Audio Emotion Analysis API
- **启动命令**：`uv run python -m src.api.main`（必须从项目根目录）
- **监听地址**：`FASTAPI_HOST` / `FASTAPI_PORT`（`.env` 配置，默认 `127.0.0.1:9010`）
- **数据格式**：请求/响应均为 UTF-8；文件上传用 `multipart/form-data`，其余用 `application/json`
- **鉴权**：无（内网部署）
- **错误格式**：`{"detail": "错误说明"}`

---

## 接口总览

| 序号 | 接口路径 | 请求方式 | 接口名称 | 说明 |
|---|---|---|---|---|
| 1 | `/health` | GET | 服务健康状态查询 | 查询服务状态、模型加载与后端配置信息 |
| 2 | `/asr` | POST | 音频转写与情绪识别 | 上传音频，返回转写文本与情绪标签（本地 Qwen2-Audio） |
| 3 | `/face-emotion` | POST | 人脸情绪识别 | 上传图片，返回主导面部情绪中文标签（DeepFace） |
| 4 | `/persona/chat` | POST | PersonaVLM 陪护对话 | 带长期记忆与人格演化的陪护回复 |
| 5 | `/persona/chat/stream` | POST | PersonaVLM 流式陪护对话 | 同上，SSE 流式返回 |

---

## 1. 服务健康状态查询

- **接口路径**：`/health`
- **请求方式**：GET
- **Content-Type**：无

### 请求参数

无。

### 响应参数

| 参数名 | 类型 | 说明 |
|---|---|---|
| `ready` | boolean | 本地模型（ASR/EmoLLM）是否加载成功 |
| `load_error` | string \| null | 本地模型加载失败原因（降级启动时返回，正常为 null） |
| `load_seconds` | object | 各模型加载耗时（秒），如 `{"audio_model": 12.3}` |
| `loaded_at` | number \| null | 模型加载完成时间戳（Unix 秒） |
| `uptime_seconds` | number | 服务已运行时长（秒） |
| `persona` | object | PersonaVLM 云端后端配置状态，见下方嵌套字段 |
| `persona.configured` | boolean | 是否配置 DASHSCOPE_API_KEY（未配置时 persona 相关接口返回 503） |
| `deepface_home` | string | DeepFace 权重目录路径 |

### 响应示例

```json
{
  "ready": true,
  "load_error": null,
  "load_seconds": {
    "audio_model": 12.3
  },
  "loaded_at": 1754800000.0,
  "uptime_seconds": 395.5,
  "persona": {
    "configured": true
  },
  "deepface_home": "D:\\GitHub\\Audio-Emotion-Analysis\\deepface_weights"
}
```

### 错误码

无（200）。

---

## 2. 音频转写与情绪识别

- **接口路径**：`/asr`
- **请求方式**：POST
- **Content-Type**：`multipart/form-data`

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `audio_file` | file | 是 | 音频文件，支持格式：.wav / .mp3 / .m4a / .flac / .ogg / .aac |

### 请求示例

```bash
curl -X POST http://127.0.0.1:9100/asr \
  -F "audio_file=@test_audio/测试音频001.mp3"
```

### 响应参数

| 参数名 | 类型 | 说明 |
|---|---|---|
| `result` | object | 识别结果 |
| `result.asr` | string | 音频转写文本 |
| `result.emotion` | string | 音频情绪标签（如 疲惫、平静、悲伤） |
| `duration_seconds` | number | 处理耗时（秒） |

### 响应示例

```json
{
  "result": {
    "asr": "今天头有点疼，不太想动",
    "emotion": "疲惫"
  },
  "duration_seconds": 8.2
}
```

### 错误码

| 状态码 | 说明 |
|---|---|
| 400 | 上传文件为空或格式不支持 |
| 503 | 本地模型未加载（服务降级启动或模型缺失） |

---

## 3. 人脸情绪识别

- **接口路径**：`/face-emotion`
- **请求方式**：POST
- **Content-Type**：`multipart/form-data`

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `image_file` | file | 是 | 图片文件，支持格式：.jpg / .jpeg / .png / .webp / .bmp |

### 请求示例

```bash
curl -X POST http://127.0.0.1:9100/face-emotion \
  -F "image_file=@test_photos/sad001.jpg"
```

### 响应参数

| 参数名 | 类型 | 说明 |
|---|---|---|
| `dominant_emotion` | string | 主导面部情绪中文标签：`愤怒` / `厌恶` / `恐惧` / `高兴` / `悲伤` / `惊讶` / `中性/平静`（未识别英文标签时原样返回） |

### 响应示例

```json
{
  "dominant_emotion": "悲伤"
}
```

### 错误码

| 状态码 | 说明 |
|---|---|
| 400 | 图片格式不支持、文件为空、未检测到清晰人脸 |
| 500 | DeepFace 权重目录不存在 |

> 说明：DeepFace 首次请求懒加载（约 10-30s）；权重目录取 `.env` 的 `DEEPFACE_HOME`，缺省项目根 `deepface_weights/`。

---

## 4. PersonaVLM 陪护对话

- **接口路径**：`/persona/chat`
- **请求方式**：POST
- **Content-Type**：`application/json`

### 接口说明

使用 PersonaVLM 云端后端（模型 API 驱动）生成陪护回复，具备长期记忆（核心画像/语义/情景/程序性四类记忆）、大五人格（OCEAN）EMA 演化、推理链（think → retrieve → answer）与多轮会话管理。用户数据持久化到 `output/{user_id}/user_data.json`。

### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `user_id` | string | 是 | — | 用户标识，记忆与人格的持久化主键，格式 `^[a-zA-Z0-9_-]{1,64}$` |
| `asr` | string | 否 | `""` | 音频转写文本 |
| `emotion` | string | 否 | `""` | 音频情绪标签，如 悲伤、孤独 |
| `face_emotion` | string | 否 | `中性/平静` | 人脸情绪标签 |
| `new_session` | boolean | 否 | `false` | 为 true 时先归纳当前会话并开新会话，本条消息落在新会话 |
| `session_index` | integer \| null | 否 | `null` | 继续指定会话（sessions[] 整数索引，-1 表示最新） |
| `timestamp` | string \| null | 否 | `null` | 消息时间戳，格式 `YYYY-MM-DD HH:MM`，不传用服务端当前时间 |

### 请求示例

```bash
curl -X POST http://127.0.0.1:9100/persona/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "tester",
    "asr": "今天头有点疼，不太想动",
    "emotion": "疲惫",
    "face_emotion": "中性/平静"
  }'
```

### 响应参数

| 参数名 | 类型 | 说明 |
|---|---|---|
| `user_id` | string | 用户标识（与请求一致） |
| `response` | string | 陪护回复文本 |
| `remembering` | object \| null | 记忆决策，字段：`decision`(boolean) / `content` / `reason` / `keywords` |
| `reasoning` | array | 推理链步骤列表，元素为 `{"think": "..."}` |
| `alignment` | object | 大五人格分数，字段：`openness` / `conscientiousness` / `extraversion` / `agreeableness` / `neuroticism` |
| `duration_seconds` | number | 处理耗时（秒） |

### 响应示例

```json
{
  "user_id": "tester",
  "response": "哎呀，头疼确实最让人没精神了，辛苦了。既然身体在抗议，那今天就彻底给自己放个假吧，什么都别想，也别勉强自己动弹。\n\n我去帮你把窗帘拉上，让屋里暗一点，这样眼睛和脑子都能放松些。",
  "remembering": {
    "decision": true,
    "content": "2026年8月10日，用户表示头疼、不想动，情绪疲惫。",
    "reason": "用户明确表达了当前的身体状态（头疼）和情绪状态（疲惫），属于需要记录的健康与情绪背景信息。",
    "keywords": "头疼,疲惫,身体不适"
  },
  "reasoning": [
    {
      "think": "用户当前状态为头痛、疲惫，不想动，情绪画像显示疲惫。用户明确要求以家人身份用简体中文进行温暖回应。"
    }
  ],
  "alignment": {
    "openness": 3.0,
    "conscientiousness": 2.5,
    "extraversion": 2.0,
    "agreeableness": 3.5,
    "neuroticism": 3.0
  },
  "duration_seconds": 11.7
}
```

### 错误码

| 状态码 | 说明 |
|---|---|
| 422 | 参数校验失败（`user_id` 缺失或格式非法） |
| 503 | 未配置 DASHSCOPE_API_KEY |

---

## 5. PersonaVLM 流式陪护对话

- **接口路径**：`/persona/chat/stream`
- **请求方式**：POST
- **Content-Type**：`application/json`
- **响应类型**：`text/event-stream`（SSE）

### 接口说明

请求参数与 `/persona/chat` 完全一致。响应为 SSE 事件流，每个事件格式：

```
event: {事件类型}
data: {JSON 数据}

```

事件序列：`think_chunk` × N → `answer_chunk` × N → `step` → `done`（异常时发送 `error`）。

### 请求参数

同 `/persona/chat`。

### 请求示例

```bash
curl -N -X POST http://127.0.0.1:9100/persona/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "tester",
    "asr": "好点了，谢谢你陪我",
    "emotion": "平静"
  }'
```

### 响应参数（事件）

| 事件类型 | data 参数 | 说明 |
|---|---|---|
| `think_chunk` | `step`(number) 思考步骤序号、`delta`(string) 思考内容片段 | 思考链流式输出片段 |
| `answer_chunk` | `delta`(string) 回复内容片段 | 回复文本流式输出片段 |
| `step` | `think`(string) 等推理链字段 | 完整推理步骤 |
| `done` | `response`(string)、`remembering`(object)、`reasoning`(array)、`alignment`(object) | 完成事件，附带完整结果（字段同 `/persona/chat` 响应） |
| `error` | `message`(string) 错误信息 | 错误事件 |

### 响应示例

```
event: think_chunk
data: {"step": 1, "delta": "用户当前状态为头痛、疲惫"}

event: think_chunk
data: {"step": 1, "delta": "，需要温暖回应。"}

event: answer_chunk
data: {"delta": "哎呀，头疼确实最让人没精神了"}

event: answer_chunk
data: {"delta": "，辛苦了。"}

event: step
data: {"think": "用户当前状态为头痛、疲惫，需要温暖回应。"}

event: done
data: {"response": "哎呀，头疼确实最让人没精神了，辛苦了。", "remembering": null, "reasoning": [], "alignment": {"openness": 3.0, "conscientiousness": 2.5, "extraversion": 2.0, "agreeableness": 3.5, "neuroticism": 3.0}}

event: error
data: {"message": "DASHSCOPE_API_KEY 未配置"}
```

### 错误码

| 状态码 | 说明 |
|---|---|
| 422 | 参数校验失败 |
| 503 | 未配置 DASHSCOPE_API_KEY（响应为 `error` 事件，非 HTTP 状态码） |

---

## 附录：未开放接口

以下接口在代码中已注释，待后续接入：

| 接口路径 | 请求方式 | 说明 |
|---|---|---|
| `/emollm` | POST | 陪护回复生成（原本地 EmoLLM 后端，已暂停使用，对话统一走 /persona/chat） |
| `/tts` | POST | 文本转语音（Qwen3-TTS，模型加载已注释） |
| `/asr-emollm` | POST | ASR + EmoLLM 两阶段合并接口 |
| `/pipeline` | POST | ASR → EmoLLM → TTS 端到端接口 |
