<p align="center"><a href="README.md">English</a> · <strong>简体中文</strong></p>

<h1 align="center">Beyond Reactive Comfort: A Knowledge-Enhanced Multimodal Agent with Long-Term Memory for Proactive Emotional Care</h1>

<h3 align="center">融合心理知识与长期记忆的多模态情感关怀智能体</h3>

<p align="center">多模态情绪感知 · 心理知识检索 · 个体长期记忆 · 实时数字人交互</p>

<p align="center"><img src="https://img.shields.io/badge/GPU-NVIDIA_RTX_PRO_6000-76B900?logo=nvidia&logoColor=white" alt="NVIDIA RTX PRO 6000" /></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-3776AB?logo=python&logoColor=white" alt="Python 3.10" />
  <img src="https://img.shields.io/badge/Web-Vue_3-4FC08D?logo=vuedotjs&logoColor=white" alt="Vue 3" />
  <img src="https://img.shields.io/badge/Avatar-Ditto-8B5CF6" alt="Ditto 数字人" />
  <img src="https://img.shields.io/badge/Memory-PersonaVLM-0284C7" alt="PersonaVLM 长期记忆" />
  <img src="https://img.shields.io/badge/Streaming-WebRTC-F97316" alt="WebRTC 实时通信" />
</p>

<p align="center">
  <a href="#project-overview">项目介绍</a> ·
  <a href="#ditto-setup">Ditto 权重</a> ·
  <a href="#persona-setup">PersonaVLM 配置</a> ·
  <a href="#system-start">启动指南</a>
</p>

---

## 📰 NEWS

后续版本与功能更新将在此发布。

## 🏗️ 系统架构

<p align="center">
  <img src="docs/system_architecture.png" alt="EmoCompanion 系统总体架构图" width="100%" />
</p>

图 1. EmoCompanion 系统总体架构：多模态情感解析、认知干预、呈现交互、数据构建与心理学知识底座，以及用户画像共同形成情感陪护闭环。

<a id="project-overview"></a>

## 💬 项目介绍

EmoCompanion 面向日常情绪支持与长期陪伴场景，围绕“感知—检索—推理—表达—记忆更新”组织系统。系统接收文本、语音或视频输入，结合多模态情绪线索、个人历史记忆和心理知识生成回复，再通过语音合成与 Ditto 驱动的数字人完成实时交互。

系统通过长期记忆延续对用户经历、偏好和历史对话的理解，并将共享心理知识作为回复的参考。交互后选择性更新个人记忆，使后续交流能够承接已有上下文。个人记忆与共享知识分别管理，共同支持持续、个性化的情感陪伴。

---

## 📂 目录

- `web/`：Vue 前端，默认开发地址为 `http://localhost:9010`。
- `LiveTalking/`：业务 API、WebRTC、TTS、ASR/情绪接口和 LightRAG 转发。
- `ditto-talkinghead/`：Ditto 推理实现；本工程通过 LiveTalking 调用它。
- `PersonaVLM/`：长期记忆和个性化回复 API。
- `Audio-Emotion-Analysis/`：Qwen2-Audio 语音转写与情绪分析，以及 DeepFace 面部情绪分析服务。
- `config.env.example`：不含密钥的 Linux/WSL 配置模板；复制为本机 `config.env` 后填写配置。`start_emocompanion.sh` 是组合启动脚本。

## 🙏 开源致谢

- Ditto 代码：[antgroup/ditto-talkinghead](https://github.com/antgroup/ditto-talkinghead)，论文：[arXiv:2411.19509](https://arxiv.org/abs/2411.19509)，权重：[Hugging Face](https://huggingface.co/digital-avatar/ditto-talkinghead)。
- PersonaVLM 代码：[MiG-NJU/PersonaVLM](https://github.com/MiG-NJU/PersonaVLM)，论文：[arXiv:2604.13074](https://arxiv.org/abs/2604.13074)，权重：[ClareNie/PersonaVLM](https://huggingface.co/ClareNie/PersonaVLM)。

感谢上述开源项目提供的模型与推理实现。

<a id="ditto-setup"></a>

## 🎭 1. Ditto 权重

模型文件不随源码目录保留；请先按[从 ModelScope 下载本项目权重](#modelscope-resources)下载，再执行下面的目录检查。以下目录结构是部署完成后的目标结构。

当前 `config.env` 使用 Ditto 的 PyTorch 推理链路。官方 Hugging Face 仓库需要 Git LFS：

```bash
cd EmoCompanion
git lfs install
git clone https://huggingface.co/digital-avatar/ditto-talkinghead /tmp/ditto-checkpoints
mkdir -p checkpoints
cp -r /tmp/ditto-checkpoints/ditto_cfg checkpoints/
cp -r /tmp/ditto-checkpoints/ditto_pytorch checkpoints/
```

Windows 不使用 `/tmp` 时，可先把仓库克隆到任意临时目录，再将 `ditto_cfg/` 和 `ditto_pytorch/` 复制到项目根目录的 `checkpoints/`。最终至少应存在：

```text
checkpoints/
├── ditto_cfg/v0.4_hubert_cfg_pytorch.pkl
└── ditto_pytorch/
    ├── aux_models/
    │   ├── 2d106det.onnx
    │   ├── det_10g.onnx
    │   ├── face_landmarker.task
    │   ├── hubert_streaming_fix_kv.onnx
    │   └── landmark203.onnx
    └── models/
        ├── appearance_extractor.pth
        ├── decoder.pth
        ├── lmdm_v0.4_hubert.pth
        ├── motion_extractor.pth
        ├── stitch_network.pth
        └── warp_network.pth
```

`config.env` 中对应的三个路径是 `DITTO_DATA_ROOT`、`DITTO_CFG_PKL` 和 `DITTO_SOURCE_PATH`。`DITTO_SOURCE_PATH` 必须是实际存在的人像图片，例如仓库内 `LiveTalking/data/avatars/default_avatar.png`。官方也提供 ONNX/TensorRT 权重，但当前启动脚本没有将它们作为默认链路；TensorRT engine 还受 GPU 架构限制。

<a id="persona-setup"></a>

## 🧠 2. PersonaVLM 权重和检索模型

部署完成后，`PersonaVLM/checkpoints/rl`、CLIP 和 MiniLM 应存在；源码目录本身不保留这些大文件。可按[从 ModelScope 下载本项目权重](#modelscope-resources)恢复。

PersonaVLM 官方 README 要求 Python 3.10、`transformers==4.51.3`，并将微调模型放在 `checkpoints/rl`。本仓库的服务读取 `PersonaVLM/checkpoints/rl`：

```bash
cd EmoCompanion/PersonaVLM
git clone https://huggingface.co/ClareNie/PersonaVLM /tmp/personavlm-checkpoints
mkdir -p checkpoints/rl
cp -r /tmp/personavlm-checkpoints/* checkpoints/rl/
```

同时准备检索依赖（不要依赖运行时首次联网下载）：

```bash
cd EmoCompanion/PersonaVLM
git clone https://huggingface.co/openai/clip-vit-base-patch32 checkpoints/openai-clip
git clone https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 checkpoints/sentence-transformers/all-MiniLM-L6-v2
```

其中 `openai-clip` 和 `all-MiniLM-L6-v2` 分别由 `PersonaVLM/PersonaVLM/retriever.py` 用于图像和文本检索。首次处理带图片的记忆时，`autodistill-grounding-dino` 还可能下载 GroundingDINO 检测模型；应提前准备缓存或允许该次联网下载。模型加载需要支持 bfloat16 的 CUDA GPU；仅有 CPU 或显存不足时，官方模型和本项目 API 都不能按当前配置启动。

检查目录后可先单独启动 API：

```bash
cd EmoCompanion/PersonaVLM
conda activate PersonaVLM
pip install -r requirements.txt
python api_server.py --host 0.0.0.0 --port 9001 \
  --model-path ./checkpoints/rl --output-root ./output --preload-model
```

成功条件是 `GET http://127.0.0.1:9001/ready` 返回 200；仅 `/health` 返回 200 不能证明模型已经加载。官方 PersonaVLM 的 `inference.py` 交互命令可用于独立验证，但它不包含本项目的 WebRTC 和 LiveTalking 集成。

<a id="modelscope-resources"></a>

## 📦 3. 从 ModelScope 下载本项目权重

项目权重已集中上传到 [AGAiChiChaoFen/EmoCompanion](https://modelscope.cn/datasets/AGAiChiChaoFen/EmoCompanion)。该仓库是数据集仓库，包含 Ditto、PersonaVLM、CLIP、MiniLM、Qwen2-Audio、Qwen3-TTS、EmoLLM 和 DeepFace 权重。下载时不要把仓库目录再套一层放进项目；下载目录中的 `checkpoints/`、`PersonaVLM/` 和 `Audio-Emotion-Analysis/` 应直接合并到本项目根目录。

推荐使用独立的 Python 环境安装 ModelScope SDK：

```bash
python -m pip install modelscope
python - <<'PY'
from modelscope.hub.snapshot_download import dataset_snapshot_download

dataset_snapshot_download(
    dataset_id="AGAiChiChaoFen/EmoCompanion",
    local_dir="./EmoCompanion-resources",
)
PY
```

Windows PowerShell 可使用同一段 Python 代码（把 `./EmoCompanion-resources` 改为绝对路径也可以）：

```powershell
python -m pip install modelscope
@'
from modelscope.hub.snapshot_download import dataset_snapshot_download
dataset_snapshot_download(
    dataset_id="AGAiChiChaoFen/EmoCompanion",
    local_dir=r"D:\EmoCompanion-resources",
)
'@ | python -
```

下载完成后，将资源目录内容合并到项目根目录 `EmoCompanion/`。Linux/WSL：

```bash
rsync -a EmoCompanion-resources/checkpoints/ EmoCompanion/checkpoints/
rsync -a EmoCompanion-resources/PersonaVLM/checkpoints/ EmoCompanion/PersonaVLM/checkpoints/
rsync -a EmoCompanion-resources/Audio-Emotion-Analysis/ EmoCompanion/Audio-Emotion-Analysis/
```

Windows PowerShell：

```powershell
robocopy D:\EmoCompanion-resources\checkpoints .\checkpoints /E
robocopy D:\EmoCompanion-resources\PersonaVLM\checkpoints .\PersonaVLM\checkpoints /E
robocopy D:\EmoCompanion-resources\Audio-Emotion-Analysis .\Audio-Emotion-Analysis /E
```

这些命令只合并资源，不使用 `/MIR`，不会删除项目中已有文件。合并后应检查以下目录：

```text
EmoCompanion/checkpoints/ditto_cfg/
EmoCompanion/checkpoints/ditto_pytorch/
EmoCompanion/PersonaVLM/checkpoints/rl/
EmoCompanion/PersonaVLM/checkpoints/openai-clip/
EmoCompanion/PersonaVLM/checkpoints/sentence-transformers/all-MiniLM-L6-v2/
EmoCompanion/Audio-Emotion-Analysis/audio_emotion/pretrained_models/
EmoCompanion/Audio-Emotion-Analysis/deepface_weights/
EmoCompanion/Audio-Emotion-Analysis/checkpoints/
```

Audio 服务的模型路径通过 `Audio-Emotion-Analysis/.env` 配置，可参考 `deployment.env.example`。第三方模型的许可证和使用要求见权重下载目录中的 `WEIGHTS_README.md`。

## 🛠️ 运行环境与服务配置

参考环境为 Ubuntu 24.04、Python 3.10、CUDA 12.8 和 NVIDIA RTX PRO 6000。准备 Conda、FFmpeg、与 CUDA 匹配的 PyTorch，以及 Node.js 18+ 和 npm。

依赖按服务分别安装：LiveTalking 使用 `LiveTalking/requirements.txt`，PersonaVLM 使用 `PersonaVLM/requirements.txt`。两者的 Transformers 版本不同，分别建立 Conda 环境；主启动脚本中的 `CONDA_ENV_NAME` 指向 LiveTalking 环境。

### 🎙️ Qwen2-Audio 与 DeepFace

在独立终端中，从项目根目录执行：

```bash
cd Audio-Emotion-Analysis
cp deployment.env.example .env
uv sync --python 3.10
uv run --python 3.10 python -m src.api.main
```

启动前，在 `.env` 中设置 `MODEL_PATH_QWEN_QWEN2_AUDIO_7B_INSTRUCT` 和 `DEEPFACE_HOME`，分别指向 Qwen2-Audio 模型和 DeepFace 权重目录。该服务同时提供语音转写、语音情绪与面部情绪分析。

### ⚙️ LiveTalking 配置

将项目根目录的 `config.env.example` 复制为 `config.env`，填写以下配置：

- **环境与数字人**：设置 `CONDA_SH`、`CONDA_ENV_NAME`、`CUDA_VISIBLE_DEVICES` 和前文的三个 `DITTO_*` 路径；使用 TensorRT 时设置 `TENSORRT_LIB_DIR`。
- **对话与记忆**：设置 `PERSONA_API_MODEL_PATH`、`PERSONA_API_OUTPUT_ROOT`，保持 `LLM_PROVIDER="personavlm"`。按第 2 节在独立环境启动 PersonaVLM 后，设置 `PERSONA_API_ENABLE="0"`，由主服务连接已有的记忆服务。
- **感知服务**：`QWENAUDIO_API_URL` 指向 Audio 服务的 `/asr`，`DEEPFACE_API_URL` 指向同一服务的基地址，例如 `http://127.0.0.1:9100/asr` 和 `http://127.0.0.1:9100`。
- **心理知识**：部署 LightRAG 并导入心理知识文档，填写 `LIGHTRAG_BASE_URL` 及对应认证信息。
- **语音与网络**：填写 DashScope/Qwen TTS 凭据；公网 WebRTC 配置 TURN 地址、认证信息及服务端网络转发规则。

<a id="system-start"></a>

## 🚀 4. 完整系统启动

启动 PersonaVLM、Audio 与 LightRAG 服务并完成上述配置后，在主服务的 Conda 环境中执行：

```bash
cd EmoCompanion
bash start_emocompanion.sh
```

主脚本根据 `config.env` 加载 Ditto 并启动 LiveTalking。

### 🌐 前端

复制 `web/.env.example` 为 `web/.env`，将 `VITE_API_BASE_URL` 与 `VITE_PERSONA_API_BASE_URL` 设置为浏览器可访问的 LiveTalking 和 PersonaVLM 地址，通过 `VITE_PERSONA_USER_NAME` 选择用户，然后执行：

```bash
cd EmoCompanion/web
npm install
npm run dev -- --host 0.0.0.0 --port 9010
```

浏览器打开 `http://localhost:9010/integrated-system`，开始文本、语音或视频交互。
