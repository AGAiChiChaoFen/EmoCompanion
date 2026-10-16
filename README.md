<p align="center"><a href="README.en.md">English</a> · <strong>简体中文</strong></p>

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
  <a href="#system-start">启动指南</a> ·
  <a href="#reproduction-status">复现缺口</a>
</p>

---

## 更新日志

| 日期 | 更新内容 |
| --- | --- |
| 2026-10-14 | 完整加入 Audio-Emotion-Analysis 服务器备份（含 Qwen2-Audio、DeepFace、停用的 EmoLLM/TTS 权重），补齐其 MiniLM/CLIP；详见 [Audio 服务分析](docs/Audio服务代码分析_20261014.md)。 |
| 2026-10-14 | 移除固定演示报告、知识回退快照与预置记忆覆盖；本地整合 PersonaVLM、CLIP、MiniLM、Ditto 权重。详见 [真实功能整理说明](docs/真实功能整理说明_20261014.md)。 |
| 2026-10-14 | 补充参考 GPU 环境：NVIDIA RTX PRO 6000。 |
| 2026-10-13 | 清理比赛演示残留，保留国赛实时交互代码；统一项目名为 EmoCompanion，前端目录统一为 `web/`。 |
| 2026-10-13 | 补充 Ditto 与 PersonaVLM 官方权重、论文、启动方式和外部服务依赖说明。 |

## 系统架构

<p align="center">
  <img src="docs/system_architecture.png" alt="EmoCompanion 系统总体架构图" width="100%" />
</p>

图 1. 论文中的系统总体架构图：多模态情感解析、认知干预、呈现交互、数据构建与心理学知识底座，以及用户画像共同形成情感陪护闭环。图中模块是论文方案层面的总体结构；具体服务、模型和外部依赖以本文档后续配置说明为准。

<a id="project-overview"></a>

## 项目介绍

EmoCompanion 面向日常情绪支持与长期陪伴场景，围绕“感知—检索—推理—表达—记忆更新”组织系统。系统接收文本、语音或视频输入，结合多模态情绪线索、个人历史记忆和心理知识生成回复，再通过语音合成与 Ditto 驱动的数字人完成实时交互。

论文中的方法重点不是重新训练基础模型，而是将多模态感知、心理知识、个体长期记忆、选择性记忆更新和数字人输出连接为一个可运行的服务链路。当前代码以国赛工程为实现基础，论文中的方案描述、历史演示指标和本仓库可复现实测需要分别看待。

---

## 目录

- `web/`：Vue 前端，默认开发地址为 `http://localhost:9010`。
- `LiveTalking/`：业务 API、WebRTC、TTS、ASR/情绪接口和 LightRAG 转发。
- `ditto-talkinghead/`：Ditto 推理实现；本工程通过 LiveTalking 调用它。
- `PersonaVLM/`：长期记忆和个性化回复 API。
- `Audio-Emotion-Analysis/`：独立 uv 环境的语音转写/情绪与 DeepFace 服务；另保留云端 PersonaVLM 适配代码和停用的 EmoLLM/TTS 资源。主工程保持原接口配置，部署差异见 [代码分析](docs/Audio服务代码分析_20261014.md)。
- `config.env.example`：不含密钥的 Linux/WSL 配置模板；复制为本机 `config.env` 后填写配置。`start_emocompanion.sh` 是组合启动脚本。

## 官方实现与论文

- Ditto 代码：[antgroup/ditto-talkinghead](https://github.com/antgroup/ditto-talkinghead)，论文：[arXiv:2411.19509](https://arxiv.org/abs/2411.19509)，权重：[Hugging Face](https://huggingface.co/digital-avatar/ditto-talkinghead)。
- PersonaVLM 代码：[MiG-NJU/PersonaVLM](https://github.com/MiG-NJU/PersonaVLM)，论文：[arXiv:2604.13074](https://arxiv.org/abs/2604.13074)，权重：[ClareNie/PersonaVLM](https://huggingface.co/ClareNie/PersonaVLM)。

本项目是对这两个项目的集成，不重新训练它们。官方仓库中的独立 demo、训练数据和评测集不是本项目运行的必要文件。

<a id="ditto-setup"></a>

## 1. Ditto 权重

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

## 2. PersonaVLM 权重和检索模型

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

## 3. 从 ModelScope 下载本项目权重

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

主工程资源完整性检查：

```bash
cd EmoCompanion
python scripts/verify_resources.py --hash
```

该检查覆盖主工程 Ditto、PersonaVLM、CLIP 和 MiniLM。Audio 服务的 Qwen2-Audio、Qwen3-TTS、EmoLLM 和 DeepFace 文件清单及 SHA-256 见 ModelScope 下载目录中的 `weights_manifest.json`；其服务路径还需要按 `Audio-Emotion-Analysis/deployment.env.example` 配置。权重仓库不包含 `.env`、访问令牌、用户记忆或运行日志。第三方模型的原始许可证仍然适用，详见下载目录中的 `WEIGHTS_README.md`。

<a id="system-start"></a>

## 4. 完整系统启动

启动脚本面向 Linux/WSL 服务器，不是 Windows PowerShell 脚本。先复制 `config.env.example` 为本机 `config.env`，再编辑其中的 `CONDA_SH`、`CONDA_ENV_NAME`、GPU、端口、模型路径、外部服务 URL，以及所有 API key/用户名密码占位项，然后：

```bash
cd EmoCompanion
bash start_emocompanion.sh
```

脚本会预加载 PersonaVLM（9001），再启动 LiveTalking（默认 9000）。前端开发：

```bash
cd EmoCompanion/web
npm install
npm run dev -- --host 0.0.0.0 --port 9010
```

浏览器打开 `http://localhost:9010/integrated-system`。生产构建使用 `npm run build`；它只构建前端，不会启动任何模型或后端。

<a id="reproduction-status"></a>

## 5. 当前复现还缺什么

本仓库目前不是下载后即可端到端运行的成品，缺口如下：

1. **模型文件**：模型权重已从本机移除，统一从 [AGAiChiChaoFen/EmoCompanion](https://modelscope.cn/datasets/AGAiChiChaoFen/EmoCompanion) 下载。下载后按上述目录结构放置模型文件。
2. **运行环境**：参考硬件为 NVIDIA RTX PRO 6000；还需要 Linux/WSL、CUDA、与 Ditto/LiveTalking 兼容的 PyTorch、TensorRT/FFmpeg 依赖，以及可用的 Conda 环境。Windows 原生不能直接执行 `start_emocompanion.sh`。其他显卡需要重新核对显存、CUDA、TensorRT 和 bfloat16 支持情况。
3. **依赖版本隔离**：PersonaVLM 官方要求 `transformers==4.51.3`，而 `LiveTalking/requirements.txt` 固定 `transformers==4.46.2`。建议为 PersonaVLM 和 LiveTalking 建立独立 Conda 环境并分别启动服务；若合并环境，必须自行验证导入和推理兼容性。
4. **语音识别**：默认 `QWENAUDIO_API_URL` 指向独立 QwenAudio HTTP 服务（9000 只调用它）。本地源码与权重已加入 `Audio-Emotion-Analysis/`，需更新其模型路径、建立独立 uv 环境并部署 `/asr`；本地 Qwen2-Audio 推理不需要云端 ASR 凭据。
5. **人脸情绪分析**：新增模块的 `/face-emotion` 与 ASR 在同一 9100 服务，源码与 DeepFace 权重已齐。主工程原 `DEEPFACE_API_URL` 默认 9020；部署时需要配置到实际服务基地址，或继续使用原独立服务。
6. **心理知识检索**：`LIGHTRAG_BASE_URL` 指向独立 LightRAG 服务（默认 9622），需要已有知识库、服务端认证信息和可访问网络。
7. **TTS 和 WebRTC**：Qwen3-TTS/DashScope 凭据必须有效；跨公网浏览器连接还需要可访问的 TURN 服务及正确的 UDP/TCP/TLS 配置。关闭 TURN 不能替代生产网络配置。
8. **数字人素材和业务数据**：已保留默认人像、头像与真实音色试听文件。演示用户记忆和固定回答生成脚本未纳入运行目录，用户记忆由真实交互产生；前端通过 `web/.env` 的 `VITE_PERSONA_USER_NAME` 选择用户。当前 Persona HTTP 接口传入文本及情绪，不传图像；上游图像记忆扩展仍需其 GroundingDINO 依赖。

此前已核验主工程本地权重、前端构建和功能回归；本次另加入并静态核对 ASR、DeepFace 服务及资源。Audio 模块中的 EmoLLM 不是 Emotion-LLaMA，其 EmoLLM/TTS 路由尚未启用；Emotion-LLaMA 如需使用仍待加入。实际 GPU 推理与全链路运行还需外部服务和部署环境联调。`LiveTalking/data/demo_voices` 是前端真实试听资源，保留不代表已经提供 TTS 服务。

## 6. 归档说明

旧服务器部署资料、预录对话视频、未引用的 Mock 数据和录屏脚本已移到论文项目根目录的 `清理暂存/`，不参与运行。原始比赛目录保持不变。
