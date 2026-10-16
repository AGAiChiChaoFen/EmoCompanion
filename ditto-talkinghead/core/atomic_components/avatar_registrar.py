import numpy as np

from .loader import load_source_frames
from .source2info import Source2Info


def _mean_filter(arr, k):
    """
    一维时间轴滑动平均。
    """

    n = arr.shape[0]
    half_k = k // 2
    res = []
    for i in range(n):
        s = max(0, i - half_k)
        e = min(n, i + half_k + 1)
        res.append(arr[s:e].mean(0))
    res = np.stack(res, 0)
    return res


def smooth_x_s_info_lst(x_s_info_list, ignore_keys=(), smo_k=13):
    """
    对模板关键点序列做逐字段平滑。

    输入为逐帧字典列表，输出保持相同结构，
    仅对未忽略字段执行时间平滑。
    """

    keys = x_s_info_list[0].keys()
    N = len(x_s_info_list)
    smo_dict = {}
    for k in keys:
        _lst = [x_s_info_list[i][k] for i in range(N)]
        if k not in ignore_keys:
            _lst = np.stack(_lst, 0)
            _smo_lst = _mean_filter(_lst, smo_k)
        else:
            _smo_lst = _lst
        smo_dict[k] = _smo_lst

    smo_res = []
    for i in range(N):
        x_s_info = {k: smo_dict[k][i] for k in keys}
        smo_res.append(x_s_info)
    return smo_res


class AvatarRegistrar:
    """
    模板注册器。

    负责将输入图像或视频转换为后续推理所需的模板缓存。
    """
    def __init__(
        self,
        insightface_det_cfg,
        landmark106_cfg,
        landmark203_cfg,
        landmark478_cfg,
        appearance_extractor_cfg,
        motion_extractor_cfg,
    ):
        self.source2info = Source2Info(
            insightface_det_cfg,
            landmark106_cfg,
            landmark203_cfg,
            landmark478_cfg,
            appearance_extractor_cfg,
            motion_extractor_cfg,
        )

    def register(
        self,
        source_path,  # 模板图像或视频路径。
        max_dim=1920,
        n_frames=-1,
        **kwargs,
    ):
        """
        注册模板并构建源信息缓存。

        输出字段包含：
        - x_s_info_lst：逐帧关键点与姿态信息；
        - f_s_lst：逐帧外观特征；
        - M_c2o_lst：裁剪到原图的仿射矩阵；
        - eye_open_lst、eye_ball_lst：眼部控制序列；
        - sc：首帧形状先验。

        边界：
        - 图像输入通常只有一帧；
        - 视频输入按 n_frames 限制截取长度。
        """
        rgb_list, is_image_flag = load_source_frames(source_path, max_dim=max_dim, n_frames=n_frames)
        source_info = {
            "x_s_info_lst": [],
            "f_s_lst": [],
            "M_c2o_lst": [],
            "eye_open_lst": [],
            "eye_ball_lst": [],
        }
        keys = ["x_s_info", "f_s", "M_c2o", "eye_open", "eye_ball"]
        last_lmk = None
        for rgb in rgb_list:
            info = self.source2info(rgb, last_lmk, **kwargs)
            for k in keys:
                source_info[f"{k}_lst"].append(info[k])

            last_lmk = info["lmk203"]

        sc_f0 = source_info['x_s_info_lst'][0]['kp'].flatten()

        source_info["sc"] = sc_f0
        source_info["is_image_flag"] = is_image_flag
        source_info["img_rgb_lst"] = rgb_list

        return source_info
    
    def __call__(self, *args, **kwargs):
        """
        调用别名，保持与函数式接口一致。
        """

        return self.register(*args, **kwargs)
    