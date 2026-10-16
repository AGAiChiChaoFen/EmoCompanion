
"""
核心网络封装模块：提供模型构建、权重加载与前向调用接口。
"""

import torch
from torch import nn
from .util import SameBlock2d, DownBlock2d, ResBlock3d


class AppearanceFeatureExtractor(nn.Module):

    def __init__(
        self,
        image_channel=3,
        block_expansion=64,
        num_down_blocks=2,
        max_features=512,
        reshape_channel=32,
        reshape_depth=16,
        num_resblocks=6,
    ):
        super(AppearanceFeatureExtractor, self).__init__()
        self.image_channel = image_channel
        self.block_expansion = block_expansion
        self.num_down_blocks = num_down_blocks
        self.max_features = max_features
        self.reshape_channel = reshape_channel
        self.reshape_depth = reshape_depth

        self.first = SameBlock2d(
            image_channel, block_expansion, kernel_size=(3, 3), padding=(1, 1)
        )

        down_blocks = []
        for i in range(num_down_blocks):
            in_features = min(max_features, block_expansion * (2**i))
            out_features = min(max_features, block_expansion * (2 ** (i + 1)))
            down_blocks.append(
                DownBlock2d(
                    in_features, out_features, kernel_size=(3, 3), padding=(1, 1)
                )
            )
        self.down_blocks = nn.ModuleList(down_blocks)

        self.second = nn.Conv2d(
            in_channels=out_features, out_channels=max_features, kernel_size=1, stride=1
        )

        self.resblocks_3d = torch.nn.Sequential()
        for i in range(num_resblocks):
            self.resblocks_3d.add_module(
                "3dr" + str(i), ResBlock3d(reshape_channel, kernel_size=3, padding=1)
            )

    def forward(self, source_image):
        out = self.first(source_image) 

        for i in range(len(self.down_blocks)):
            out = self.down_blocks[i](out)
        out = self.second(out)
        bs, c, h, w = out.shape 

        f_s = out.view(
            bs, self.reshape_channel, self.reshape_depth, h, w
        ) 
        f_s = self.resblocks_3d(f_s) 
        return f_s

    def load_model(self, ckpt_path):
        self.load_state_dict(torch.load(ckpt_path, map_location=lambda storage, loc: storage))
        self.eval()
        return self
