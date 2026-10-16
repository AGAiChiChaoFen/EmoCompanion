from pathlib import Path
from modelscope import snapshot_download
from typing import Optional
import re



def _model_env_key(model_id: str) -> str:
    """
    将模型ID转换为环境变量键名，格式为 MODEL_PATH_{MODEL_ID}，其中 MODEL_ID 中的非字母数字字符被替换为下划线，并转换为大写。
    例如，模型ID "Qwen/Qwen2-Audio-7B-Instruct" 将被转换为环境变量键 "MODEL_PATH_QWEN_QWEN2_AUDIO_7B_INSTRUCT"。
    """
    safe = re.sub(r"[^A-Za-z0-9]+", "_", model_id).upper().strip("_")
    return f"MODEL_PATH_{safe}"



def _upsert_env_value(env_path: Path, key: str, value: str) -> None:
    """
    在 .env 文件中更新或插入环境变量键值对，如果键已存在则更新其值，否则添加新的键值对。

    参数:
        env_path: .env 文件路径
        key: 环境变量键
        value: 环境变量值

    返回: 无
    """
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    new_line = f"{key}={value}"
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = new_line
            updated = True
            break
    if not updated:
        lines.append(new_line)

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")



def download_model(
    model_id: str,
    local_dir: Optional[str] = None,
) -> Path:
    """
    下载/缓存模型到本地目录；已存在则直接复用。
    下载目录固定为与当前文件所在的 `load_models` 目录同级的 `pretrained_models` 下。

    参数:
        model_id: 模型ID
        local_dir: 本地存储目录，若为 None 则放在 audio_emotion 目录下的 `pretrained_models/<model_id>` 目录中
        
    返回:
        模型本地路径
    """

    # 找到该文件的祖父目录 -> audio_emotion 目录
    model_dir = Path(__file__).resolve().parent.parent

    # 若未指定 local_dir，则放在 project/pretrained_models/<model_id>
    local_dir_path = Path(local_dir) if local_dir else model_dir / "pretrained_models" / model_id
    local_dir_path.mkdir(parents=True, exist_ok=True)

    model_path = snapshot_download(
        model_id=model_id,
        local_dir=str(local_dir_path),
    )

    model_path = Path(model_path).resolve()
    repo_root = model_dir.parent
    env_path = repo_root / ".env"
    env_key = _model_env_key(model_id)
    _upsert_env_value(env_path, env_key, str(model_path))


    return model_path