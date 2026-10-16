import numpy as np
import torch
from ..utils.load_model import load_model


class Decoder:
    """图像解码器封装。

    输入为驱动后的特征张量，输出渲染图像（RGB）。
    """

    def __init__(self, model_path, device="cuda"):
        kwargs = {
            "module_name": "SPADEDecoder",
        }
        self.model, self.model_type = load_model(model_path, device=device, **kwargs)
        self.device = device
        
    def __call__(self, feature):
        """
        执行一次解码前向推理并转为可显示图像。

        输入：
        - feature: 来自 WarpingNetwork 的特征张量。

        输出：
        - pred: 形状为 [H, W, 3] 的图像数组，取值范围约为 [0, 255]。
        """

        if self.model_type == "onnx":
            pred = self.model.run(None, {"feature": feature})[0]
        elif self.model_type == "tensorrt":
            self.model.setup({"feature": feature})
            self.model.infer()
            pred = self.model.buffer["output"][0].copy()
        elif self.model_type == 'pytorch':
            with torch.no_grad(), torch.autocast(device_type=self.device[:4], dtype=torch.float16, enabled=True):
                pred = self.model(torch.from_numpy(feature).to(self.device)).float().cpu().numpy()
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")
        
        # 模型原始输出通常为 [N, C, H, W] 且归一化到 [0,1]，
        # 这里统一转为 HWC 并扩展到 [0,255] 以便后续回贴/编码。
        pred = np.transpose(pred[0], [1, 2, 0]).clip(0, 1) * 255   
        
        return pred
