import numpy as np
import torch
from ..utils.load_model import load_model


class AppearanceExtractor:
    """外观特征提取器。

    职责：把标准化头像输入编码为高维外观特征 f_s，
    供后续 WarpingNetwork 使用，实现“源外观 + 目标运动”的可控合成。
    """

    def __init__(self, model_path, device="cuda"):
        kwargs = {
            "module_name": "AppearanceFeatureExtractor",
        }
        self.model, self.model_type = load_model(model_path, device=device, **kwargs)
        self.device = device

    def __call__(self, image):
        """
        执行一次外观特征前向推理。

        输入：
        - image: 形状通常为 [1, 3, 256, 256] 的 float32 张量（NCHW）。

        输出：
        - pred: 模型外观特征张量，具体通道维度取决于训练配置。

        兼容性：
        - 支持 onnx / tensorrt / pytorch 三种后端；
        - 统一返回 numpy，便于与后续模块无缝衔接。
        """
        if self.model_type == "onnx":
            pred = self.model.run(None, {"image": image})[0]
        elif self.model_type == "tensorrt":
            self.model.setup({"image": image})
            self.model.infer()
            pred = self.model.buffer["pred"][0].copy()
        elif self.model_type == 'pytorch':
            with torch.no_grad(), torch.autocast(device_type=self.device[:4], dtype=torch.float16, enabled=True):
                pred = self.model(torch.from_numpy(image).to(self.device)).float().cpu().numpy()
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")
        return pred
