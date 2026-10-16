import numpy as np
import torch
from ..utils.load_model import load_model


class MotionExtractor:
    """运动参数提取器。

    用于从裁剪头像图中回归姿态、位移、尺度、表情与关键点参数，
    输出字段会作为后续运动拼接与形变阶段的核心输入。
    """

    def __init__(self, model_path, device="cuda"):
        kwargs = {
            "module_name": "MotionExtractor",
        }
        self.model, self.model_type = load_model(model_path, device=device, **kwargs)
        self.device = device

        self.output_names = [
            "pitch",
            "yaw",
            "roll",
            "t",
            "exp",
            "scale",
            "kp",
        ]

    def __call__(self, image):
        """
                执行一次运动参数前向推理并统一输出格式。

                输入：
                - image: 标准化人脸输入，通常为 [1, 3, 256, 256]。

                输出：
                - dict，字段固定为 pitch/yaw/roll/t/exp/scale/kp。

                形状约定：
                - exp 与 kp 在返回前被 reshape 为 [1, -1]，
                    便于与下游 MotionStitch/transform_keypoint 直接对接。
        """
        outputs = {}
        if self.model_type == "onnx":
            out_list = self.model.run(None, {"image": image})
            for i, name in enumerate(self.output_names):
                outputs[name] = out_list[i]
        elif self.model_type == "tensorrt":
            self.model.setup({"image": image})
            self.model.infer()
            for name in self.output_names:
                outputs[name] = self.model.buffer[name][0].copy()
        elif self.model_type == "pytorch":
            with torch.no_grad(), torch.autocast(device_type=self.device[:4], dtype=torch.float16, enabled=True):
                pred = self.model(torch.from_numpy(image).to(self.device))
                for i, name in enumerate(self.output_names):
                    outputs[name] = pred[i].float().cpu().numpy()
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")
        outputs["exp"] = outputs["exp"].reshape(1, -1)
        outputs["kp"] = outputs["kp"].reshape(1, -1)
        return outputs


