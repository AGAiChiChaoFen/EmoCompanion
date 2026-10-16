# PersonaVLM 记忆与推理 API

该服务将 PersonaVLM 的 `user_data.json` 记忆读取和 Agent 推理封装为 Flask REST API。
模型采用懒加载：启动、健康检查和读取记忆时不会加载模型，第一次发送消息时才占用显存。

## 安装与启动

```bash
cd EmoCompanion/PersonaVLM
pip install -r requirements.txt
python api_server.py
```

指定服务器路径：

```bash
python api_server.py \
  --host 0.0.0.0 \
  --port 5000 \
  --output-root /data/EmoCompanion/PersonaVLM/output \
  --model-path /data/EmoCompanion/PersonaVLM/checkpoints/rl \
  --preload-model
```

也可以复制 `api.env.example` 中的变量到服务器运行环境。脚本不会自动读取 `.env` 文件，
避免引入额外依赖；请由 Shell、systemd、Docker 或服务器控制台注入环境变量。

## 主要接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 存活检查，不加载模型 |
| GET | `/ready` | 检查模型和记忆目录状态 |
| GET | `/openapi.yaml` | 获取 OpenAPI 3.1 接口说明 |
| GET | `/api/v1/users` | 获取已有记忆的用户列表 |
| GET | `/api/v1/users/{用户名}/memory` | 获取完整 `user_data.json` |
| GET | `/api/v1/users/{用户名}/memory-summary` | 获取记忆数量和最新画像 |
| GET | `/api/v1/users/{用户名}/profiles` | 分页获取画像版本 |
| GET | `/api/v1/users/{用户名}/personality-history` | 分页获取逐轮大五人格历史 |
| GET | `/api/v1/users/{用户名}/semantic-memories` | 分页获取逐轮信息判断 |
| GET | `/api/v1/users/{用户名}/episodic-memories` | 分页获取生活主题 |
| GET | `/api/v1/users/{用户名}/procedural-memories` | 分页获取习惯与目标版本 |
| GET | `/api/v1/users/{用户名}/interactions` | 分页获取原始对话 |
| POST | `/api/v1/users/{用户名}/messages` | 调用 Agent 推理并更新记忆 |
| DELETE | `/api/v1/users/{用户名}/agent-cache` | 清除用户 Agent 缓存，下次推理重新读取文件 |

所有列表接口支持 `page` 和 `per_page`，其中 `per_page` 最大为100。

重要信息可按是否保留筛选：

```bash
curl "http://127.0.0.1:9001/api/v1/users/王秀兰/semantic-memories?decision=true&page=1&per_page=20"
```

原始对话可按从0开始的会话下标筛选：

```bash
curl "http://127.0.0.1:9001/api/v1/users/王秀兰/interactions?session_index=0"
```

## 执行推理

时间可省略，服务会使用服务器当前时间。系统仅接受文本输入，不接收图片字段。

```bash
curl -X POST "http://127.0.0.1:9001/api/v1/users/王秀兰/messages" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "你还记得我女儿现在在哪里工作吗？",
    "time": "2026-08-04 21:30"
  }'
```

请求成功后会返回数字人回复、人格分析和推理过程，并按照 PersonaVLM 原有流程更新
`output/王秀兰/user_data.json`。

## 初始化记忆与人格历史快照

升级人格历史功能后，旧快照不包含逐轮 `personality_history`。普通运行初始化脚本时，
脚本会检查“人格历史条数是否等于已保存交互轮数”，旧快照或残缺快照不会被静默复用。

服务器上第一次生成包含完整人格历史的新版快照：

```bash
cd EmoCompanion/PersonaVLM
python seed_memory.py --user-name 王秀兰 --regenerate
```

该命令会忽略旧快照、重新执行全部预设对话，并在全部成功后把完整用户目录保存到
`memory_backups/王秀兰`。旧快照在生成成功前不会被覆盖。

之后普通启动初始化脚本即可直接恢复新版快照，不再执行推理：

```bash
python seed_memory.py --user-name 王秀兰
```

可先用演练模式查看脚本准备恢复还是重新生成：

```bash
python seed_memory.py --user-name 王秀兰 --dry-run
```

只有明确接受“没有完整人格历史”时，才允许手动恢复旧快照：

```bash
python seed_memory.py --user-name 王秀兰 --restore-backup-only --allow-legacy-snapshot
```

该兼容方式只能恢复旧记忆，无法产生历史人格趋势，不建议作为新的比赛演示基准。

可选人格输入：

```json
{
  "query": "今天想和你聊聊天。",
  "personality": {
    "openness": 3.5,
    "conscientiousness": 4.0,
    "extraversion": 3.0,
    "agreeableness": 4.0,
    "neuroticism": 2.5
  }
}
```

## 并发与缓存

- 大模型全服务只加载一次，多个用户共享模型，避免重复占用显存。
- 每个用户拥有独立 Agent、检索器和记忆目录。
- 模型推理串行执行，避免共享对话上下文互相污染。
- 同一用户的记忆读取和写入使用同一把锁，避免读到半写入的 JSON。
- 如果在 API 外部替换了某个用户的 `user_data.json`，先删除其 Agent 缓存再推理。

## 生产部署提示

开发和比赛演示可以直接运行 `python api_server.py`。正式部署建议使用单进程 Gunicorn，
因为多个工作进程会分别加载一份模型并重复占用显存：

```bash
gunicorn --workers 1 --threads 8 --timeout 600 --bind 0.0.0.0:9001 "persona_api:create_app()"
```

生产环境必须通过 `PERSONA_API_CORS_ORIGINS` 配置准确的前端域名，不要开放任意来源。
