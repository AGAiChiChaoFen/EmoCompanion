<p align="center"><strong>English</strong> · <a href="README.md">简体中文</a></p>

<h1 align="center">Beyond Reactive Comfort: A Knowledge-Enhanced Multimodal Agent with Long-Term Memory for Proactive Emotional Care</h1>

<h3 align="center">A Multimodal Emotional Care Agent with Psychological Knowledge and Long-Term Memory</h3>

<p align="center">Multimodal Emotion Perception · Psychological Knowledge Retrieval · Personal Long-Term Memory · Real-Time Avatar Interaction</p>

<p align="center"><img src="https://img.shields.io/badge/GPU-NVIDIA_RTX_PRO_6000-76B900?logo=nvidia&logoColor=white" alt="NVIDIA RTX PRO 6000" /></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-3776AB?logo=python&logoColor=white" alt="Python 3.10" />
  <img src="https://img.shields.io/badge/Web-Vue_3-4FC08D?logo=vuedotjs&logoColor=white" alt="Vue 3" />
  <img src="https://img.shields.io/badge/Avatar-Ditto-8B5CF6" alt="Ditto avatar" />
  <img src="https://img.shields.io/badge/Memory-PersonaVLM-0284C7" alt="PersonaVLM memory" />
  <img src="https://img.shields.io/badge/Streaming-WebRTC-F97316" alt="WebRTC streaming" />
</p>

<p align="center"><a href="#project-overview">Overview</a> · <a href="#ditto-checkpoints">Ditto checkpoints</a> · <a href="#personavlm-setup">PersonaVLM setup</a> · <a href="#system-startup">System startup</a></p>

---

## 📰 NEWS

Future releases and feature updates will be announced here.

## 🏗️ System architecture

<p align="center">
  <img src="docs/system_architecture.png" alt="EmoCompanion system architecture" width="100%" />
</p>

**Figure 1.** The paper's overall architecture: multimodal emotion analysis, cognitive intervention, presentation and interaction, data construction with a psychological knowledge base, and the user profile form the emotional-care loop.

<a id="project-overview"></a>

## 💬 Project overview

EmoCompanion targets everyday emotional support and long-term companionship. Its service pipeline follows “perception, retrieval, reasoning, expression, and memory update”. Given text, audio, or video input, it combines multimodal emotional cues, personal interaction history, and psychological knowledge to generate a response, then delivers it through speech synthesis and a Ditto-driven real-time avatar.

Long-term memory carries user experiences, preferences, and conversation history into subsequent interactions. Shared psychological knowledge provides context for response generation, while selective memory updates help future conversations build on previous exchanges. Personal memory and shared knowledge are managed separately.

## 📂 Repository layout

- `web/`: Vue frontend, normally served at `http://localhost:9010`.
- `LiveTalking/`: application APIs, WebRTC, TTS, ASR/emotion interfaces, and LightRAG forwarding.
- `Audio-Emotion-Analysis/`: Qwen2-Audio transcription and emotion analysis, plus DeepFace facial emotion analysis.
- `ditto-talkinghead/`: Ditto inference implementation called by LiveTalking.
- `PersonaVLM/`: long-term memory and personalized response API.
- `config.env.example`: a credential-free Linux/WSL configuration template; copy it to the local, ignored `config.env` and fill in the values. `start_emocompanion.sh` is the integrated launcher.

## 🙏 Acknowledgments

- Ditto: [code](https://github.com/antgroup/ditto-talkinghead), [paper](https://arxiv.org/abs/2411.19509), [Hugging Face checkpoints](https://huggingface.co/digital-avatar/ditto-talkinghead).
- PersonaVLM: [code](https://github.com/MiG-NJU/PersonaVLM), [paper](https://arxiv.org/abs/2604.13074), [Hugging Face checkpoints](https://huggingface.co/ClareNie/PersonaVLM).

We thank these open-source projects for their models and inference implementations.

<a id="ditto-checkpoints"></a>

## 🎭 Ditto checkpoints

The source tree does not retain these large files. Download them from ModelScope first, then use the directory layout below as the deployment target.

The current launcher uses the PyTorch pipeline. Download the official files with Git LFS, then copy `ditto_cfg/` and `ditto_pytorch/` into the project-level `checkpoints/` directory:

```bash
cd EmoCompanion
git lfs install
git clone https://huggingface.co/digital-avatar/ditto-talkinghead /tmp/ditto-checkpoints
mkdir -p checkpoints
cp -r /tmp/ditto-checkpoints/ditto_cfg checkpoints/
cp -r /tmp/ditto-checkpoints/ditto_pytorch checkpoints/
```

The required files include `ditto_cfg/v0.4_hubert_cfg_pytorch.pkl`, the auxiliary ONNX models, and the six PyTorch model files under `ditto_pytorch/models/`. Set `DITTO_DATA_ROOT`, `DITTO_CFG_PKL`, and `DITTO_SOURCE_PATH` in `config.env`. The source path must point to an existing portrait image. ONNX/TensorRT checkpoints are available upstream but are not the default path here and depend on GPU architecture.

<a id="personavlm-setup"></a>

## 🧠 PersonaVLM setup

After deployment, `PersonaVLM/checkpoints/rl`, CLIP, and MiniLM must be present. The source tree does not retain these large files; restore them using the [ModelScope resource download](#modelscope-resources) section.

The official PersonaVLM release requires Python 3.10 and `transformers==4.51.3`. Download the fine-tuned model into `PersonaVLM/checkpoints/rl`, then prepare the local retrieval models:

```bash
cd EmoCompanion/PersonaVLM
git clone https://huggingface.co/ClareNie/PersonaVLM /tmp/personavlm-checkpoints
mkdir -p checkpoints/rl
cp -r /tmp/personavlm-checkpoints/* checkpoints/rl/
git clone https://huggingface.co/openai/clip-vit-base-patch32 checkpoints/openai-clip
git clone https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 checkpoints/sentence-transformers/all-MiniLM-L6-v2
```

CLIP is used for image retrieval and MiniLM for text retrieval. The first image-memory operation may also download a GroundingDINO detector. A CUDA GPU with bfloat16 support is required by the current model loader.

```bash
conda activate PersonaVLM
pip install -r requirements.txt
python api_server.py --host 0.0.0.0 --port 9001 \
  --model-path ./checkpoints/rl --output-root ./output --preload-model
```

Verify `GET http://127.0.0.1:9001/ready` returns HTTP 200. A healthy `/health` response alone does not prove that the model is loaded.

<a id="modelscope-resources"></a>

## 📦 Download project resources from ModelScope

All project checkpoints are published in the [AGAiChiChaoFen/EmoCompanion](https://modelscope.cn/datasets/AGAiChiChaoFen/EmoCompanion) dataset repository. It contains Ditto, PersonaVLM, CLIP, MiniLM, Qwen2-Audio, Qwen3-TTS, EmoLLM, and DeepFace resources. The downloaded `checkpoints/`, `PersonaVLM/`, and `Audio-Emotion-Analysis/` directories should be merged directly into the project root; do not add an extra `EmoCompanion-resources/` directory level.

Install the ModelScope SDK in a separate Python environment and download the public dataset:

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

Merge the downloaded resources on Linux/WSL:

```bash
rsync -a EmoCompanion-resources/checkpoints/ EmoCompanion/checkpoints/
rsync -a EmoCompanion-resources/PersonaVLM/checkpoints/ EmoCompanion/PersonaVLM/checkpoints/
rsync -a EmoCompanion-resources/Audio-Emotion-Analysis/ EmoCompanion/Audio-Emotion-Analysis/
```

On Windows PowerShell:

```powershell
robocopy D:\EmoCompanion-resources\checkpoints .\checkpoints /E
robocopy D:\EmoCompanion-resources\PersonaVLM\checkpoints .\PersonaVLM\checkpoints /E
robocopy D:\EmoCompanion-resources\Audio-Emotion-Analysis .\Audio-Emotion-Analysis /E
```

The commands merge files and do not use `/MIR`, so they do not delete existing project files. After merging, check `checkpoints/ditto_pytorch/`, `PersonaVLM/checkpoints/rl/`, `PersonaVLM/checkpoints/openai-clip/`, `PersonaVLM/checkpoints/sentence-transformers/all-MiniLM-L6-v2/`, `Audio-Emotion-Analysis/audio_emotion/pretrained_models/`, `Audio-Emotion-Analysis/deepface_weights/`, and `Audio-Emotion-Analysis/checkpoints/`.

Configure Audio model paths in `Audio-Emotion-Analysis/.env`, using `deployment.env.example` as a template. Third-party model licenses and usage terms are described in `WEIGHTS_README.md` in the downloaded resources.

## 🛠️ Environment and service configuration

The reference environment uses Ubuntu 24.04, Python 3.10, CUDA 12.8, and an NVIDIA RTX PRO 6000. Prepare Conda, FFmpeg, a CUDA-compatible PyTorch build, Node.js 18+, and npm.

Install dependencies per service: `LiveTalking/requirements.txt` for LiveTalking and `PersonaVLM/requirements.txt` for PersonaVLM. Use separate Conda environments because they specify different Transformers versions. Set the launcher's `CONDA_ENV_NAME` to the LiveTalking environment.

### 🎙️ Qwen2-Audio and DeepFace

In a separate terminal, run from the project root:

```bash
cd Audio-Emotion-Analysis
cp deployment.env.example .env
uv sync --python 3.10
uv run --python 3.10 python -m src.api.main
```

Before starting, set `MODEL_PATH_QWEN_QWEN2_AUDIO_7B_INSTRUCT` and `DEEPFACE_HOME` in `.env` to the Qwen2-Audio model and DeepFace weights. This service provides transcription, speech emotion analysis, and facial emotion analysis.

### ⚙️ LiveTalking configuration

Copy the project-level `config.env.example` to `config.env` and configure:

- **Environment and avatar**: `CONDA_SH`, `CONDA_ENV_NAME`, `CUDA_VISIBLE_DEVICES`, and the three `DITTO_*` paths above. Set `TENSORRT_LIB_DIR` when using TensorRT.
- **Conversation and memory**: `PERSONA_API_MODEL_PATH`, `PERSONA_API_OUTPUT_ROOT`, and `LLM_PROVIDER="personavlm"`. Start PersonaVLM in its own environment as described above, then set `PERSONA_API_ENABLE="0"` so the main service connects to the running memory service.
- **Perception**: point `QWENAUDIO_API_URL` to the Audio service's `/asr` route and `DEEPFACE_API_URL` to its base URL, for example `http://127.0.0.1:9100/asr` and `http://127.0.0.1:9100`.
- **Psychological knowledge**: deploy LightRAG, import the knowledge documents, and set `LIGHTRAG_BASE_URL` and authentication settings.
- **Speech and networking**: supply DashScope/Qwen TTS credentials. For public-network WebRTC, configure the TURN server, credentials, and server forwarding rules.

<a id="system-startup"></a>

## 🚀 System startup

Start PersonaVLM, Audio, and LightRAG and complete the configuration above. Then run in the main service's Conda environment:

```bash
cd EmoCompanion
bash start_emocompanion.sh
```

The launcher loads Ditto and starts LiveTalking using `config.env`.

### 🌐 Frontend

Copy `web/.env.example` to `web/.env`. Set `VITE_API_BASE_URL` and `VITE_PERSONA_API_BASE_URL` to browser-accessible LiveTalking and PersonaVLM addresses, and select a user with `VITE_PERSONA_USER_NAME`. Then run:

```bash
cd EmoCompanion/web
npm install
npm run dev -- --host 0.0.0.0 --port 9010
```

Open `http://localhost:9010/integrated-system` to begin text, audio, or video interactions.
