import numpy as np
import torch
from ..utils.load_model import load_model


class WarpNetwork:
    """特征形变网络封装。

    输入源外观特征与关键点对（source/driving），输出驱动后的 3D 特征，
    是“运动迁移”到“像素解码”之间的关键桥接模块。
    """

    def __init__(self, model_path, device="cuda"):
        kwargs = {
            "module_name": "WarpingNetwork",
        }
        self.model, self.model_type = load_model(model_path, device=device, **kwargs)
        self.device = device

    def __call__(self, feature_3d, kp_source, kp_driving):
        """
        执行一次关键点驱动的特征形变推理。

        输入：
        - feature_3d: 源外观三维特征；
        - kp_source: 源关键点；
        - kp_driving: 目标驱动关键点。

        输出：
        - pred: 驱动后的 3D 特征，直接送入解码器生成渲染图。

        兼容后端：onnx / tensorrt / pytorch。
        """
        if self.model_type == "onnx":
            pred = self.model.run(None, {"feature_3d": feature_3d, "kp_source": kp_source, "kp_driving": kp_driving})[0]
        elif self.model_type == "tensorrt":
            self.model.setup({"feature_3d": feature_3d, "kp_source": kp_source, "kp_driving": kp_driving})
            self.model.infer()
            pred = self.model.buffer["out"][0].copy()
        elif self.model_type == 'pytorch':
            with torch.no_grad(), torch.autocast(device_type=self.device[:4], dtype=torch.float16, enabled=True):
                pred = self.model(
                    torch.from_numpy(feature_3d).to(self.device), 
                    torch.from_numpy(kp_source).to(self.device), 
                    torch.from_numpy(kp_driving).to(self.device)
                ).float().cpu().numpy()
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")
        
        return pred
