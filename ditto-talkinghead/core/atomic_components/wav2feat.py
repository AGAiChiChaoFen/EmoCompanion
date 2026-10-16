import librosa
import numpy as np
import math

from ..aux_models.hubert_stream import HubertStreaming

"""
音频特征提取模块。

提供统一入口，将原始波形转换为后续音频驱动网络所需的特征序列。
"""


class Wav2Feat:
    """
    音频特征提取封装器。

    当前支持按类型路由到对应提取器，并暴露统一调用接口。
    """

    def __init__(self, w2f_cfg, w2f_type="hubert"):
        self.w2f_type = w2f_type.lower()
        if self.w2f_type == "hubert":
            self.w2f = Wav2FeatHubert(hubert_cfg=w2f_cfg)
            self.feat_dim = 1024
            self.support_streaming = True
        else:
            raise ValueError(f"Unsupported w2f_type: {w2f_type}")
        
    def __call__(
        self, 
        audio, 
        sr=16000, 
        norm_mean_std=None,   # 归一化参数，特定分支使用。
        chunksize=(3, 5, 2),   # 流式窗口参数。
    ):
        """
        提取单段音频特征。

        输入：音频数组与采样率。
        输出：二维特征序列。
        """

        if self.w2f_type == "hubert":
            feat = self.w2f(audio, chunksize=chunksize)
        elif self.w2f_type == "s2g":
            feat = self.w2f(audio, sr=sr, norm_mean_std=norm_mean_std)
        else:
            raise ValueError(f"Unsupported w2f_type: {self.w2f_type}")
        return feat
    
    def wav2feat(
        self,
        audio, 
        sr=16000, 
        norm_mean_std=None,   # 归一化参数，特定分支使用。
        chunksize=(3, 5, 2),
    ):
        """
        离线提取接口。

        与实时接口区别在于会遍历整段音频并拼接全部结果。
        """

        if self.w2f_type == "hubert":
            feat = self.w2f.wav2feat(audio, sr=sr, chunksize=chunksize)
        elif self.w2f_type == "s2g":
            feat = self.w2f(audio, sr=sr, norm_mean_std=norm_mean_std)
        else:
            raise ValueError(f"Unsupported w2f_type: {self.w2f_type}")
        return feat
    

class Wav2FeatHubert:
    """
    流式音频特征提取实现。
    """

    def __init__(
        self,
        hubert_cfg,
    ):
        self.hubert = HubertStreaming(**hubert_cfg)

    def __call__(self, audio_chunk, chunksize=(3, 5, 2)):
        """
        处理单个流式窗口并返回有效特征段。

        输入窗口通常包含前文、有效区和后文；
        输出仅保留中间有效区域，供实时推理使用。
        """
        valid_feat_s = - sum(chunksize[1:]) * 2   # -7
        valid_feat_e = - chunksize[2] * 2   # -2

        encoding_chunk = self.hubert(audio_chunk)
        valid_encoding = encoding_chunk[valid_feat_s:valid_feat_e]
        valid_feat = valid_encoding.reshape(chunksize[1], 2, 1024).mean(1)    # [5, 1024]
        return valid_feat

    def wav2feat(self, audio, sr, chunksize=(3, 5, 2)):
        """
        离线遍历整段音频，按窗口步长累计特征。

        边界策略：
        - 先在首尾补零，保证边界窗口可计算；
        - 最终按理论帧数截断，避免补齐区影响长度。
        """

        if sr != 16000:
            audio_16k = librosa.resample(audio, orig_sr=sr, target_sr=16000)
        else:
            audio_16k = audio

        num_f = math.ceil(len(audio_16k) / 16000 * 25)
        split_len = int(sum(chunksize) * 0.04 * 16000) + 80    # 6480

        speech_pad = np.concatenate([
            np.zeros((split_len - int(sum(chunksize[1:]) * 0.04 * 16000),), dtype=audio_16k.dtype),
            audio_16k,
            np.zeros((split_len,), dtype=audio_16k.dtype),
        ], 0)
        
        i = 0
        res_lst = []
        while i < num_f:
            sss = int(i * 0.04 * 16000)
            eee = sss + split_len
            audio_chunk = speech_pad[sss:eee]
            valid_feat = self.__call__(audio_chunk, chunksize)
            res_lst.append(valid_feat)
            i += chunksize[1]
        
        ret = np.concatenate(res_lst, 0)
        ret = ret[:num_f]
        return ret
