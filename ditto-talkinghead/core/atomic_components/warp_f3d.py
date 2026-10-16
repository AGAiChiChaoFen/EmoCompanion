from ..models.warp_network import WarpNetwork

# 形变模块封装。
# 输入：源外观特征与源/目标关键点。
# 输出：驱动后的三维特征图。
class WarpF3D:
    def __init__(self, warp_network_cfg):
        """
        三维特征形变器。
        """
        self.warp_net = WarpNetwork(**warp_network_cfg)

    def __call__(self, f_s, x_s, x_d):
        """
        执行一次形变推理。
        """

        out = self.warp_net(f_s, x_s, x_d)
        return out
    