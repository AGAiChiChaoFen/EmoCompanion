from ..models.decoder import Decoder


"""三维特征解码模块。

输入：
- 形变后的三维特征张量。

输出：
- 可回贴到原图坐标系的渲染图像。
"""


class DecodeF3D:
    """对 Decoder 的轻量封装，便于管线统一调用。"""

    def __init__(self, decoder_cfg):
        self.decoder = Decoder(**decoder_cfg)

    def __call__(self, f_s):
        """
        执行一次解码推理。
        """

        out = self.decoder(f_s)
        return out
    