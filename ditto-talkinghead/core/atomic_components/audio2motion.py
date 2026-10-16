import numpy as np
from ..models.lmdm import LMDM


"""
音频到运动参数模块。

职责：
- 将条件特征序列映射为逐帧驱动参数；
- 在相邻窗口间执行重叠融合，降低片段边界抖动；
- 在在线与离线模式下保持统一的数据格式输出。
"""


def _cvt_LP_motion_info(inp, mode, ignore_keys=()):
    """
    在字典格式与向量格式之间转换运动信息。

    输入：
    - mode 为 dic2arr 时，输入为关键点字典；
    - mode 为 arr2dic 时，输入为一维向量。

    输出：
    - dic2arr 输出拼接后的向量；
    - arr2dic 输出与模型约定一致的字段字典。
    """

    ks_shape_map = [
        ['scale', (1, 1), 1], 
        ['pitch', (1, 66), 66],
        ['yaw',   (1, 66), 66],
        ['roll',  (1, 66), 66],
        ['t',     (1, 3), 3], 
        ['exp', (1, 63), 63],
        ['kp',  (1, 63), 63],
    ]
    
    def _dic2arr(_dic):
        arr = []
        for k, _, ds in ks_shape_map:
            if k not in _dic or k in ignore_keys:
                continue
            v = _dic[k].reshape(ds)
            if k == 'scale':
                v = v - 1
            arr.append(v)
        arr = np.concatenate(arr, -1)  # (133)
        return arr
    
    def _arr2dic(_arr):
        dic = {}
        s = 0
        for k, ds, ss in ks_shape_map:
            if k in ignore_keys:
                continue
            v = _arr[s:s + ss].reshape(ds)
            if k == 'scale':
                v = v + 1
            dic[k] = v
            s += ss
            if s >= len(_arr):
                break
        return dic
    
    if mode == 'dic2arr':
        assert isinstance(inp, dict)
        return _dic2arr(inp)   # 字典转向量，供网络直接消费。
    elif mode == 'arr2dic':
        assert inp.shape[0] >= 265, f"{inp.shape}"
        return _arr2dic(inp)   # 向量还原为字段字典，供后续几何模块使用。
    else:
        raise ValueError()
    

class Audio2Motion:
    """
    音频驱动器，封装窗口推理、结果融合、平滑与状态更新。
    """

    def __init__(
        self,
        lmdm_cfg,
    ):
        self.lmdm = LMDM(**lmdm_cfg)

    def setup(
        self, 
        x_s_info, 
        overlap_v2=10,
        fix_kp_cond=0,
        fix_kp_cond_dim=None,
        sampling_timesteps=50,
        online_mode=False,
        v_min_max_for_clip=None,
        smo_k_d=3,
    ):
        """
        初始化驱动状态。

        输入：源模板参数与窗口相关超参。
        关键边界：
        - valid_clip_len 由窗口长度减重叠长度得到；
        - 当启用裁剪区间时，后续输出会被限制在给定上下界。
        """

        self.smo_k_d = smo_k_d
        self.overlap_v2 = overlap_v2
        self.seq_frames = self.lmdm.seq_frames
        self.valid_clip_len = self.seq_frames - self.overlap_v2

        # 在线模式为了降低实时延迟，融合长度不超过有效输出长度。
        self.online_mode = online_mode
        if self.online_mode:
            self.fuse_length = min(self.overlap_v2, self.valid_clip_len)
        else:
            self.fuse_length = self.overlap_v2
        self.fuse_alpha = np.arange(self.fuse_length, dtype=np.float32).reshape(1, -1, 1) / self.fuse_length

        self.fix_kp_cond = fix_kp_cond
        self.fix_kp_cond_dim = fix_kp_cond_dim
        self.sampling_timesteps = sampling_timesteps
        
        self.v_min_max_for_clip = v_min_max_for_clip
        if self.v_min_max_for_clip is not None:
            self.v_min = self.v_min_max_for_clip[0][None]    # 下界用于削减异常峰值。
            self.v_max = self.v_min_max_for_clip[1][None]

        kp_source = _cvt_LP_motion_info(x_s_info, mode='dic2arr', ignore_keys={'kp'})[None]
        self.s_kp_cond = kp_source.copy().reshape(1, -1)
        self.kp_cond = self.s_kp_cond.copy()

        self.lmdm.setup(sampling_timesteps)

        self.clip_idx = 0

    def _fuse(self, res_kp_seq, pred_kp_seq):
        """
        融合前后两个窗口的重叠区域。

        处理逻辑：
        - 取历史结果尾部与当前预测头部的重叠区间；
        - 使用线性权重做平滑过渡；
        - 再拼接当前窗口的非重叠区，形成连续序列。
        """

        fuse_r1_s = res_kp_seq.shape[1] - self.fuse_length
        fuse_r1_e = res_kp_seq.shape[1]
        fuse_r2_s = self.seq_frames - self.valid_clip_len - self.fuse_length
        fuse_r2_e = self.seq_frames - self.valid_clip_len

        r1 = res_kp_seq[:, fuse_r1_s:fuse_r1_e]     # 历史结果重叠段。
        r2 = pred_kp_seq[:, fuse_r2_s: fuse_r2_e]   # 当前结果重叠段。
        r_fuse = r1 * (1 - self.fuse_alpha) + r2 * self.fuse_alpha

        res_kp_seq[:, fuse_r1_s:fuse_r1_e] = r_fuse    # 将融合结果写回历史序列尾部。
        res_kp_seq = np.concatenate([res_kp_seq, pred_kp_seq[:, fuse_r2_e:]], 1)  # 追加当前窗口非重叠区。

        return res_kp_seq
    
    def _update_kp_cond(self, res_kp_seq, idx):
        """
        更新下一窗口的关键点条件。

        边界策略：
        - fix_kp_cond 为 0 时持续沿用最新结果；
        - fix_kp_cond 大于 0 时按周期回退到源条件，可抑制长期漂移。
        """

        if self.fix_kp_cond == 0:  # 不重置
            self.kp_cond = res_kp_seq[:, idx-1]
        elif self.fix_kp_cond > 0:
            if self.clip_idx % self.fix_kp_cond == 0:  # 重置
                self.kp_cond = self.s_kp_cond.copy()  # 重置所有
                if self.fix_kp_cond_dim is not None:
                    ds, de = self.fix_kp_cond_dim
                    self.kp_cond[:, ds:de] = res_kp_seq[:, idx-1, ds:de]
            else:
                self.kp_cond = res_kp_seq[:, idx-1]

    def _smo(self, res_kp_seq, s, e):
        """
        对指定区间做滑动平均平滑，降低关键点跳变。
        """

        if self.smo_k_d <= 1:
            return res_kp_seq
        new_res_kp_seq = res_kp_seq.copy()
        n = res_kp_seq.shape[1]
        half_k = self.smo_k_d // 2
        for i in range(s, e):
            ss = max(0, i - half_k)
            ee = min(n, i + half_k + 1)
            res_kp_seq[:, i, :202] = np.mean(new_res_kp_seq[:, ss:ee, :202], axis=1)
        return res_kp_seq
    
    def __call__(self, aud_cond, res_kp_seq=None):
        """
        执行一次窗口推理并更新连续结果序列。

        输入：
        - aud_cond：当前窗口条件特征；
        - res_kp_seq：历史累计结果，可为空。

        输出：
        - 更新后的累计运动序列。

        时序：
        - 首窗直接作为基础序列；
        - 后续窗口先融合再平滑；
        - 每次结束后刷新下一窗条件。
        """

        pred_kp_seq = self.lmdm(self.kp_cond, aud_cond, self.sampling_timesteps)
        if res_kp_seq is None:
            res_kp_seq = pred_kp_seq   # 首窗无历史序列，直接作为初值。
            res_kp_seq = self._smo(res_kp_seq, 0, res_kp_seq.shape[1])
        else:
            res_kp_seq = self._fuse(res_kp_seq, pred_kp_seq)  # 对重叠区做平滑衔接。
            res_kp_seq = self._smo(res_kp_seq, res_kp_seq.shape[1] - self.valid_clip_len - self.fuse_length, res_kp_seq.shape[1] - self.valid_clip_len + 1)

        self.clip_idx += 1

        idx = res_kp_seq.shape[1] - self.overlap_v2
        self._update_kp_cond(res_kp_seq, idx)

        return res_kp_seq
    
    def cvt_fmt(self, res_kp_seq):
        # 将模型输出裁剪并转换为下游可消费的字段字典列表。
        if self.v_min_max_for_clip is not None:
            tmp_res_kp_seq = np.clip(res_kp_seq[0], self.v_min, self.v_max)
        else:
            tmp_res_kp_seq = res_kp_seq[0]

        x_d_info_list = []
        for i in range(tmp_res_kp_seq.shape[0]):
            x_d_info = _cvt_LP_motion_info(tmp_res_kp_seq[i], 'arr2dic')   # 将每帧向量还原为字段字典。
            x_d_info_list.append(x_d_info)
        return x_d_info_list
