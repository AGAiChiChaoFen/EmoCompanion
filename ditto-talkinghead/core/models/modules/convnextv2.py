
"""
核心网络封装模块：提供模型构建、权重加载与前向调用接口。
"""

import torch
import torch.nn as nn
from .util import LayerNorm, DropPath, trunc_normal_, GRN

__all__ = ['convnextv2_tiny']


class Block(nn.Module):
    """
    类说明：该类负责封装当前阶段处理流程，输入输出与边界策略见方法注释。
    """

    def __init__(self, dim, drop_path=0.):
        super().__init__()
        self.dwconv = nn.Conv2d(dim, dim, kernel_size=7, padding=3, groups=dim) 
        self.norm = LayerNorm(dim, eps=1e-6)
        self.pwconv1 = nn.Linear(dim, 4 * dim) 
        self.act = nn.GELU()
        self.grn = GRN(4 * dim)
        self.pwconv2 = nn.Linear(4 * dim, dim)
        self.drop_path = DropPath(drop_path) if drop_path > 0. else nn.Identity()

    def forward(self, x):
        input = x
        x = self.dwconv(x)
        x = x.permute(0, 2, 3, 1) 
        x = self.norm(x)
        x = self.pwconv1(x)
        x = self.act(x)
        x = self.grn(x)
        x = self.pwconv2(x)
        x = x.permute(0, 3, 1, 2) 

        x = input + self.drop_path(x)
        return x


class ConvNeXtV2(nn.Module):
    """
    类说明：该类负责封装当前阶段处理流程，输入输出与边界策略见方法注释。
    """

    def __init__(
        self,
        in_chans=3,
        depths=[3, 3, 9, 3],
        dims=[96, 192, 384, 768],
        drop_path_rate=0.,
        **kwargs
    ):
        super().__init__()
        self.depths = depths
        self.downsample_layers = nn.ModuleList() 
        stem = nn.Sequential(
            nn.Conv2d(in_chans, dims[0], kernel_size=4, stride=4),
            LayerNorm(dims[0], eps=1e-6, data_format="channels_first")
        )
        self.downsample_layers.append(stem)
        for i in range(3):
            downsample_layer = nn.Sequential(
                LayerNorm(dims[i], eps=1e-6, data_format="channels_first"),
                nn.Conv2d(dims[i], dims[i+1], kernel_size=2, stride=2),
            )
            self.downsample_layers.append(downsample_layer)

        self.stages = nn.ModuleList() 
        dp_rates = [x.item() for x in torch.linspace(0, drop_path_rate, sum(depths))]
        cur = 0
        for i in range(4):
            stage = nn.Sequential(
                *[Block(dim=dims[i], drop_path=dp_rates[cur + j]) for j in range(depths[i])]
            )
            self.stages.append(stage)
            cur += depths[i]

        self.norm = nn.LayerNorm(dims[-1], eps=1e-6) 

       
        num_bins = kwargs.get('num_bins', 66)
        num_kp = kwargs.get('num_kp', 24) 
        self.fc_kp = nn.Linear(dims[-1], 3 * num_kp) 

       
        self.fc_scale = nn.Linear(dims[-1], 1) 
        self.fc_pitch = nn.Linear(dims[-1], num_bins) 
        self.fc_yaw = nn.Linear(dims[-1], num_bins) 
        self.fc_roll = nn.Linear(dims[-1], num_bins) 
        self.fc_t = nn.Linear(dims[-1], 3) 
        self.fc_exp = nn.Linear(dims[-1], 3 * num_kp)  # 表情分量处理。

    def _init_weights(self, m):
        if isinstance(m, (nn.Conv2d, nn.Linear)):
            trunc_normal_(m.weight, std=.02)
            nn.init.constant_(m.bias, 0)

    def forward_features(self, x):
        for i in range(4):
            x = self.downsample_layers[i](x)
            x = self.stages[i](x)
        return self.norm(x.mean([-2, -1])) 

    def forward(self, x):
        x = self.forward_features(x)

       
        kp = self.fc_kp(x)

        # 姿态分量处理。
        pitch = self.fc_pitch(x)
        yaw = self.fc_yaw(x)
        roll = self.fc_roll(x)
        t = self.fc_t(x)
        exp = self.fc_exp(x)
        scale = self.fc_scale(x)

       
       
       
       
       
        # 表情分量处理。
       

       
        # }

       
        return pitch, yaw, roll, t, exp, scale, kp


def convnextv2_tiny(**kwargs):
    model = ConvNeXtV2(depths=[3, 3, 9, 3], dims=[96, 192, 384, 768], **kwargs)
    return model
