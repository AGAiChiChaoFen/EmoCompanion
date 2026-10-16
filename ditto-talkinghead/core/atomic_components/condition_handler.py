import numpy as np
from scipy.special import softmax
import copy


def _get_emo_avg(idx=6):
    """
    根据情绪标签生成平滑概率分布。

    输入可为单个标签或标签列表，输出固定为 8 维分布。
    """

    emo_avg = np.zeros(8, dtype=np.float32)
    if isinstance(idx, (list, tuple)):
        for i in idx:
            emo_avg[i] = 8
    else:
        emo_avg[idx] = 8
    emo_avg = softmax(emo_avg)
    # 通过 softmax 平滑为概率，避免使用硬标签造成突变。
    # 标签顺序与训练时定义保持一致。
    return emo_avg


def _mirror_index(index, size):
    """
    蛇形镜像索引。

    作用：当驱动帧超过模板长度时，按前进再回退的方式循环，
    避免纯取模带来的首尾跳变。
    """

    turn = index // size
    res = index % size
    if turn % 2 == 0:
        return res
    else:
        return size - res - 1
    

class ConditionHandler:
    """
    条件拼接器。

    输入为音频特征与可选控制信号，输出为模型条件序列。
    """
    def __init__(
        self,
        use_emo=True,
        use_sc=True,
        use_eye_open=True,
        use_eye_ball=True,
        seq_frames=80,
    ):
        self.use_emo = use_emo
        self.use_sc = use_sc
        self.use_eye_open = use_eye_open
        self.use_eye_ball = use_eye_ball

        self.seq_frames = seq_frames

    def setup(self, setup_info, emo, eye_f0_mode=False, ch_info=None):
        """
        初始化静态与动态条件缓存。

        输入：
        - setup_info：模板提取结果；
        - emo：情绪配置，可为标签或序列；
        - eye_f0_mode：是否固定使用首帧眼部状态；
        - ch_info：外部条件覆盖。

        边界处理：当条件长度为 1 时自动扩展为整窗常量序列。
        """
        if ch_info is None:
            source_info = copy.deepcopy(setup_info)
        else:
            source_info = ch_info

        self.eye_f0_mode = eye_f0_mode
        self.x_s_info_0 = source_info['x_s_info_lst'][0]

        if self.use_sc:
            self.sc = source_info["sc"]    # 63
            self.sc_seq = np.stack([self.sc] * self.seq_frames, 0)
        
        if self.use_eye_open:
            self.eye_open_lst = np.concatenate(source_info["eye_open_lst"], 0)  # 眼睛开合序列。
            self.num_eye_open = len(self.eye_open_lst)
            if self.num_eye_open == 1 or self.eye_f0_mode:
                self.eye_open_seq = np.stack([self.eye_open_lst[0]] * self.seq_frames, 0)
            else:
                self.eye_open_seq = None
        
        if self.use_eye_ball:
            self.eye_ball_lst = np.concatenate(source_info["eye_ball_lst"], 0)  # 眼球位移序列。
            self.num_eye_ball = len(self.eye_ball_lst)
            if self.num_eye_ball == 1 or self.eye_f0_mode:
                self.eye_ball_seq = np.stack([self.eye_ball_lst[0]] * self.seq_frames, 0)
            else:
                self.eye_ball_seq = None

        if self.use_emo:
            self.emo_lst = self._parse_emo_seq(emo)
            self.num_emo = len(self.emo_lst)
            if self.num_emo == 1:
                self.emo_seq = np.concatenate([self.emo_lst] * self.seq_frames, 0)
            else:
                self.emo_seq = None

    @staticmethod
    def _parse_emo_seq(emo, seq_len=-1):
        """
        将多种情绪输入格式规范化为二维序列。

        容错策略：
        - 支持标签、标签集合、标签序列、概率序列；
        - 当提供 seq_len 时自动裁剪或扩展；
        - 不可匹配长度时显式抛错，避免静默对齐错误。
        """

        if isinstance(emo, np.ndarray) and emo.ndim == 2 and emo.shape[1] == 8:
            # 直接使用外部概率序列。
            emo_seq = emo   # 形状为 [长度, 8]。
        elif isinstance(emo, int) and 0 <= emo < 8:
            # 单标签输入。
            emo_seq = _get_emo_avg(emo).reshape(1, 8)    # [1, 8]
        elif isinstance(emo, (list, tuple)) and 0 < len(emo) < 8 and isinstance(emo[0], int):
            # 多标签混合输入。
            emo_seq = _get_emo_avg(emo).reshape(1, 8)    # [1, 8]
        elif isinstance(emo, list) and emo and isinstance(emo[0], (list, tuple)):
            # 按帧标签序列输入。
            emo_seq = np.stack([_get_emo_avg(i) for i in emo], 0)    # 形状为 [长度, 8]。
        else:
            raise ValueError(f"Unsupported emo type: {emo}")
    
        if seq_len > 0:
            if len(emo_seq) == seq_len:
                return emo_seq
            elif len(emo_seq) == 1:
                return np.concatenate([emo_seq] * seq_len, 0)
            elif len(emo_seq) > seq_len:
                return emo_seq[:seq_len]
            else:
                raise ValueError(f"emo len {len(emo_seq)} can not match seq len ({seq_len})")
        else:
            return emo_seq
        
    def __call__(self, aud_feat, idx, emo=None):
        """
        生成当前窗口的完整条件序列。

        输入：
        - aud_feat：音频特征窗口；
        - idx：全局起始索引，允许小于 0；
        - emo：可选临时情绪覆盖。

        输出：
        - 若启用额外条件则按最后一维拼接；
        - 否则直接返回音频特征。

        边界策略：
        - idx 小于 0 时按 0 处理，避免负索引越界；
        - 条件长度不足时通过镜像索引或常量扩展补齐。
        """

        frame_num = len(aud_feat)
        more_cond = [aud_feat]
        if self.use_emo:
            if emo is not None:
                emo_seq = self._parse_emo_seq(emo, frame_num)
            elif self.emo_seq is not None and len(self.emo_seq) == frame_num:
                emo_seq = self.emo_seq
            else:
                emo_idx_list = [max(i, 0) % self.num_emo for i in range(idx, idx + frame_num)]
                emo_seq = self.emo_lst[emo_idx_list]
            more_cond.append(emo_seq)

        if self.use_eye_open:
            if self.eye_open_seq is not None and len(self.eye_open_seq) == frame_num:
                eye_open_seq = self.eye_open_seq
            else:
                if self.eye_f0_mode:
                    eye_idx_list = [0] * frame_num
                else:
                    eye_idx_list = [_mirror_index(max(i, 0), self.num_eye_open) for i in range(idx, idx + frame_num)]
                eye_open_seq = self.eye_open_lst[eye_idx_list]
            more_cond.append(eye_open_seq)

        if self.use_eye_ball:
            if self.eye_ball_seq is not None and len(self.eye_ball_seq) == frame_num:
                eye_ball_seq = self.eye_ball_seq
            else:
                if self.eye_f0_mode:
                    eye_idx_list = [0] * frame_num
                else:
                    eye_idx_list = [_mirror_index(max(i, 0), self.num_eye_ball) for i in range(idx, idx + frame_num)]
                eye_ball_seq = self.eye_ball_lst[eye_idx_list]
            more_cond.append(eye_ball_seq)

        if self.use_sc:
            if len(self.sc_seq) == frame_num:
                sc_seq = self.sc_seq
            else:
                sc_seq = np.stack([self.sc] * frame_num, 0)
            more_cond.append(sc_seq)

        if len(more_cond) > 1:
            cond_seq = np.concatenate(more_cond, -1)    # 拼接得到模型条件输入。
        else:
            cond_seq = aud_feat

        return cond_seq
