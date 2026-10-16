import threading
import queue
import numpy as np
import traceback
from tqdm import tqdm

from core.atomic_components.avatar_registrar import AvatarRegistrar, smooth_x_s_info_lst
from core.atomic_components.condition_handler import ConditionHandler, _mirror_index
from core.atomic_components.audio2motion import Audio2Motion
from core.atomic_components.motion_stitch import MotionStitch
from core.atomic_components.warp_f3d import WarpF3D
from core.atomic_components.decode_f3d import DecodeF3D
from core.atomic_components.putback import PutBack
from core.atomic_components.writer import VideoWriterByImageIO
from core.atomic_components.wav2feat import Wav2Feat
from core.atomic_components.cfg import parse_cfg, print_cfg


"""
流式数字人主流程。

数据时序说明：
1. 输入侧通过 run_chunk 推入音频块；
2. 音频特征进入音频驱动阶段并转为逐帧运动参数；
3. 运动参数依次经过运动拼接、特征形变、解码、回贴、写盘。

线程与队列关系：
audio2motion_queue -> motion_stitch_queue -> warp_f3d_queue -> decode_f3d_queue -> putback_queue -> writer_queue。

容错策略：
- 任一工作线程异常会设置 stop_event，并在 close 时向调用方抛出；
- 通过 None 作为哨兵值级联通知下游线程安全退出；
- 队列写入采用超时重试，避免长时间阻塞导致死锁。
"""


class StreamSDK:
    """
    管线调度器，负责组件初始化、线程编排、队列衔接与异常回收。
    """

    def __init__(self, cfg_pkl, data_root, **kwargs):

        [
            avatar_registrar_cfg,
            condition_handler_cfg,
            lmdm_cfg,
            stitch_network_cfg,
            warp_network_cfg,
            decoder_cfg,
            wav2feat_cfg,
            default_kwargs,
        ] = parse_cfg(cfg_pkl, data_root, kwargs)
        
        self.default_kwargs = default_kwargs
        
        self.avatar_registrar = AvatarRegistrar(**avatar_registrar_cfg)
        self.condition_handler = ConditionHandler(**condition_handler_cfg)
        self.audio2motion = Audio2Motion(lmdm_cfg)
        self.motion_stitch = MotionStitch(stitch_network_cfg)
        self.warp_f3d = WarpF3D(warp_network_cfg)
        self.decode_f3d = DecodeF3D(decoder_cfg)
        self.putback = PutBack()

        self.wav2feat = Wav2Feat(**wav2feat_cfg)

    def _merge_kwargs(self, default_kwargs, run_kwargs):
        for k, v in default_kwargs.items():
            if k not in run_kwargs:
                run_kwargs[k] = v
        return run_kwargs

    def setup_Nd(self, N_d, fade_in=-1, fade_out=-1, ctrl_info=None):
        """
        设置目标帧数并预计算逐帧控制信息。

        输入：
        - N_d：目标帧数；
        - fade_in、fade_out：首尾渐入渐出长度；
        - ctrl_info：可选逐帧控制字典。

        边界处理：
        - 渐入或渐出长度小于等于 0 时跳过对应阶段；
        - 未提供 ctrl_info 时复用已有控制表。
        """

        # 将目标帧数同步给运动拼接模块，用于眨眼节奏与循环边界计算。
        self.motion_stitch.set_Nd(N_d)

        # 在控制表中写入 fade_alpha，使首尾过渡更平滑。
        if ctrl_info is None:
            ctrl_info = self.ctrl_info
        if fade_in > 0:
            for i in range(fade_in):
                alpha = i / fade_in
                item = ctrl_info.get(i, {})
                item["fade_alpha"] = alpha
                ctrl_info[i] = item
        if fade_out > 0:
            ss = N_d - fade_out - 1
            ee = N_d - 1
            for i in range(ss, N_d):
                alpha = max((ee - i) / (ee - ss), 0)
                item = ctrl_info.get(i, {})
                item["fade_alpha"] = alpha
                ctrl_info[i] = item
        self.ctrl_info = ctrl_info

    def setup(self, source_path, output_path, **kwargs):
        """
        完整初始化一次流式推理会话。

        输入：
        - source_path：模板图像或视频；
        - output_path：输出视频路径；
        - kwargs：覆盖默认参数的运行时配置。

        时序：
        1. 合并配置并初始化各阶段模块；
        2. 注册模板头像并生成条件序列；
        3. 建立音频缓冲、队列和工作线程。

        容错：
        - 在线模式下要求特征提取器支持流式；
        - 队列均设置上限，避免内存无限增长。
        """

        # 合并默认配置与运行时覆盖参数，确保未显式传入的项也有稳定值。
        kwargs = self._merge_kwargs(self.default_kwargs, kwargs)
        print("=" * 20, "setup kwargs", "=" * 20)
        print_cfg(**kwargs)
        print("=" * 50)

        # 模板读取参数：限制输入分辨率，控制模板抽帧长度。
        self.max_size = kwargs.get("max_size", 1920)
        self.template_n_frames = kwargs.get("template_n_frames", -1)

        # 人脸裁剪参数：控制缩放、平移与是否旋转对齐。
        self.crop_scale = kwargs.get("crop_scale", 2.3)
        self.crop_vx_ratio = kwargs.get("crop_vx_ratio", 0)
        self.crop_vy_ratio = kwargs.get("crop_vy_ratio", -0.125)
        self.crop_flag_do_rot = kwargs.get("crop_flag_do_rot", True)
        
        # 视频场景处理。
        self.smo_k_s = kwargs.get('smo_k_s', 13)

        # 条件控制参数：情绪、眼睛模式和外部条件覆盖。
        self.emo = kwargs.get("emo", 4)    # 情绪控制可为单标签、标签序列或概率序列。
        self.eye_f0_mode = kwargs.get("eye_f0_mode", False)    # 视频场景处理。
        self.ch_info = kwargs.get("ch_info", None)    # 传入时优先使用外部条件而非模板统计。

        # 音频驱动参数：重叠窗口、采样步数、在线模式与裁剪边界。
        self.overlap_v2 = kwargs.get("overlap_v2", 10)
        self.fix_kp_cond = kwargs.get("fix_kp_cond", 0)
        self.fix_kp_cond_dim = kwargs.get("fix_kp_cond_dim", None)  # 仅重置指定维度时使用。
        self.sampling_timesteps = kwargs.get("sampling_timesteps", 50)
        self.online_mode = kwargs.get("online_mode", False)
        self.v_min_max_for_clip = kwargs.get('v_min_max_for_clip', None)
        self.smo_k_d = kwargs.get("smo_k_d", 3)

        # 运动拼接参数：控制驱动键、相对驱动、眼部驱动和渐变策略。
        self.N_d = kwargs.get("N_d", -1)
        self.use_d_keys = kwargs.get("use_d_keys", None)
        self.relative_d = kwargs.get("relative_d", True)
        self.drive_eye = kwargs.get("drive_eye", None)    # 为 None 时按图像/视频模板自动选择。
        self.delta_eye_arr = kwargs.get("delta_eye_arr", None)
        self.delta_eye_open_n = kwargs.get("delta_eye_open_n", 0)
        self.fade_type = kwargs.get("fade_type", "")    # 渐变目标可选空、初始驱动或源模板。
        self.fade_out_keys = kwargs.get("fade_out_keys", ("exp",))
        self.flag_stitching = kwargs.get("flag_stitching", True)

        self.ctrl_info = kwargs.get("ctrl_info", dict())
        self.overall_ctrl_info = kwargs.get("overall_ctrl_info", dict())
        """
        控制信息说明：
        - ctrl_info 可以是按帧索引的字典或列表；
        - 每帧可注入 fade_alpha、姿态偏移、表情偏移等控制项；
        - overall_ctrl_info 会在每帧控制之前合并，作为全局默认值。
        """

        # 在线模式必须由支持流式特征提取的实现提供输入，否则直接拦截。
        assert self.wav2feat.support_streaming or not self.online_mode

        # 注册模板并缓存每一帧的几何与外观信息，后续线程直接复用。
        crop_kwargs = {
            "crop_scale": self.crop_scale,
            "crop_vx_ratio": self.crop_vx_ratio,
            "crop_vy_ratio": self.crop_vy_ratio,
            "crop_flag_do_rot": self.crop_flag_do_rot,
        }
        n_frames = self.template_n_frames if self.template_n_frames > 0 else self.N_d
        source_info = self.avatar_registrar(
            source_path, 
            max_dim=self.max_size, 
            n_frames=n_frames, 
            **crop_kwargs,
        )

        if len(source_info["x_s_info_lst"]) > 1 and self.smo_k_s > 1:
            source_info["x_s_info_lst"] = smooth_x_s_info_lst(source_info["x_s_info_lst"], smo_k=self.smo_k_s)

        self.source_info = source_info
        self.source_info_frames = len(source_info["x_s_info_lst"])

        # 生成音频条件控制器，统一拼接情绪、眼部与形状先验。
        self.condition_handler.setup(source_info, self.emo, eye_f0_mode=self.eye_f0_mode, ch_info=self.ch_info)

        # 初始化音频驱动模块，确定窗口长度、重叠策略与平滑参数。
        x_s_info_0 = self.condition_handler.x_s_info_0
        self.audio2motion.setup(
            x_s_info_0, 
            overlap_v2=self.overlap_v2,
            fix_kp_cond=self.fix_kp_cond,
            fix_kp_cond_dim=self.fix_kp_cond_dim,
            sampling_timesteps=self.sampling_timesteps,
            online_mode=self.online_mode,
            v_min_max_for_clip=self.v_min_max_for_clip,
            smo_k_d=self.smo_k_d,
        )

        # 初始化运动拼接模块，决定眼部驱动、淡出策略及关键点融合方式。
        is_image_flag = source_info["is_image_flag"]
        x_s_info = source_info['x_s_info_lst'][0]
        self.motion_stitch.setup(
            N_d=self.N_d,
            use_d_keys=self.use_d_keys,
            relative_d=self.relative_d,
            drive_eye=self.drive_eye,
            delta_eye_arr=self.delta_eye_arr,
            delta_eye_open_n=self.delta_eye_open_n,
            fade_out_keys=self.fade_out_keys,
            fade_type=self.fade_type,
            flag_stitching=self.flag_stitching,
            is_image_flag=is_image_flag,
            x_s_info=x_s_info,
            d0=None,
            ch_info=self.ch_info,
            overall_ctrl_info=self.overall_ctrl_info,
        )

        # 初始化写盘器：先写临时文件，收尾阶段由外部流程处理重命名。
        self.output_path = output_path
        self.tmp_output_path = output_path + ".tmp.mp4"
        self.writer = VideoWriterByImageIO(self.tmp_output_path)
        self.writer_pbar = tqdm(desc="writer")

        # 初始化音频特征缓存；在线模式先写入重叠缓冲，保证首段条件长度充足。
        if self.online_mode:
            # 首段使用静音占位，确保第一批窗口长度满足网络输入要求。
            self.audio_feat = self.wav2feat.wav2feat(np.zeros((self.overlap_v2 * 640,), dtype=np.float32), sr=16000)
            assert len(self.audio_feat) == self.overlap_v2, f"{len(self.audio_feat)}"
        else:
            self.audio_feat = np.zeros((0, self.wav2feat.feat_dim), dtype=np.float32)
        self.cond_idx_start = 0 - len(self.audio_feat)

        # 创建有界队列和线程：通过限长队列实现背压，避免任一阶段无限积压。
        QUEUE_MAX_SIZE = 100
        # 队列按管线顺序级联，None 作为终止哨兵向下游传播。

        self.worker_exception = None
        self.stop_event = threading.Event()

        self.audio2motion_queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)
        self.motion_stitch_queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)
        self.warp_f3d_queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)
        self.decode_f3d_queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)
        self.putback_queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)
        self.writer_queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)

        self.thread_list = [
            threading.Thread(target=self.audio2motion_worker),
            threading.Thread(target=self.motion_stitch_worker),
            threading.Thread(target=self.warp_f3d_worker),
            threading.Thread(target=self.decode_f3d_worker),
            threading.Thread(target=self.putback_worker),
            threading.Thread(target=self.writer_worker),
        ]

        for thread in self.thread_list:
            thread.start()

    def _get_ctrl_info(self, fid):
        """
        读取某一帧的控制字典。

        容错策略：
        - 支持字典和列表两种控制容器；
        - 越界或类型异常时打印堆栈并返回空控制，保证主流程不中断。
        """
        try:
            if isinstance(self.ctrl_info, dict):
                return self.ctrl_info.get(fid, {})
            elif isinstance(self.ctrl_info, list):
                return self.ctrl_info[fid]
            else:
                return {}
        except Exception as e:
            traceback.print_exc()
            return {}

    def writer_worker(self):
        """
        写盘线程包装器。

        作用：捕获子线程异常并触发全局停止事件，避免其余线程继续阻塞等待。
        """
        try:
            self._writer_worker()
        except Exception as e:
            self.worker_exception = e
            self.stop_event.set()

    def _writer_worker(self):
        """
        最末级消费者：从 writer_queue 取帧并写入视频。

        队列语义：收到 None 立即退出，表示上游已完成全部帧投递。
        """
        while not self.stop_event.is_set():
            try:
                item = self.writer_queue.get(timeout=1)
            except queue.Empty:
                continue

            if item is None:
                break
            res_frame_rgb = item
            self.writer(res_frame_rgb, fmt="rgb")
            self.writer_pbar.update()

    def putback_worker(self):
        """
        回贴线程包装器，统一异常上报与停止信号广播。
        """
        try:
            self._putback_worker()
        except Exception as e:
            self.worker_exception = e
            self.stop_event.set()

    def _putback_worker(self):
        """
        将渲染区域回贴到原图坐标系。

        输入：来自 putback_queue 的 [帧索引, 渲染图]。
        输出：完整帧写入 writer_queue。
        时序：接收 None 时向 writer_queue 继续传递 None，保证下游同步收尾。
        """
        while not self.stop_event.is_set():
            try:
                item = self.putback_queue.get(timeout=1)
            except queue.Empty:
                continue
            if item is None:
                self.writer_queue.put(None)
                break
            frame_idx, render_img = item
            frame_rgb = self.source_info["img_rgb_lst"][frame_idx]
            M_c2o = self.source_info["M_c2o_lst"][frame_idx]
            res_frame_rgb = self.putback(frame_rgb, render_img, M_c2o)
            self.writer_queue.put(res_frame_rgb)

    def decode_f3d_worker(self):
        """
        解码线程包装器，负责异常透传与停机触发。
        """
        try:
            self._decode_f3d_worker()
        except Exception as e:
            self.worker_exception = e
            self.stop_event.set()

    def _decode_f3d_worker(self):
        """
        将三维特征解码为渲染图像。

        队列关系：decode_f3d_queue -> putback_queue。
        边界处理：空队列超时重试，收到 None 级联通知下游退出。
        """
        while not self.stop_event.is_set():
            try:
                item = self.decode_f3d_queue.get(timeout=1)
            except queue.Empty:
                continue
            if item is None:
                self.putback_queue.put(None)
                break
            frame_idx, f_3d = item
            render_img = self.decode_f3d(f_3d)
            self.putback_queue.put([frame_idx, render_img])

    def warp_f3d_worker(self):
        """
        形变线程包装器，负责异常捕获与全局停机联动。
        """
        try:
            self._warp_f3d_worker()
        except Exception as e:
            self.worker_exception = e
            self.stop_event.set()

    def _warp_f3d_worker(self):
        """
        根据源特征与目标关键点生成驱动后的三维特征。

        输入：warp_f3d_queue 中的 [帧索引, 源关键点, 目标关键点]。
        输出：decode_f3d_queue 中的 [帧索引, 三维特征]。
        """
        while not self.stop_event.is_set():
            try:
                item = self.warp_f3d_queue.get(timeout=1)
            except queue.Empty:
                continue
            if item is None:
                self.decode_f3d_queue.put(None)
                break
            frame_idx, x_s, x_d = item
            f_s = self.source_info["f_s_lst"][frame_idx]
            f_3d = self.warp_f3d(f_s, x_s, x_d)
            self.decode_f3d_queue.put([frame_idx, f_3d])

    def motion_stitch_worker(self):
        """
        运动拼接线程包装器，统一异常与停机状态。
        """
        try:
            self._motion_stitch_worker()
        except Exception as e:
            self.worker_exception = e
            self.stop_event.set()

    def _motion_stitch_worker(self):
        """
        将音频驱动结果与模板关键点融合，生成送入形变网络的关键点对。

        队列关系：motion_stitch_queue -> warp_f3d_queue。
        容错：队列超时继续轮询，收到 None 后透传终止信号。
        """
        while not self.stop_event.is_set():
            try:
                item = self.motion_stitch_queue.get(timeout=1)
            except queue.Empty:
                continue
            if item is None:
                self.warp_f3d_queue.put(None)
                break
            
            frame_idx, x_d_info, ctrl_kwargs = item
            x_s_info = self.source_info["x_s_info_lst"][frame_idx]
            x_s, x_d = self.motion_stitch(x_s_info, x_d_info, **ctrl_kwargs)
            self.warp_f3d_queue.put([frame_idx, x_s, x_d])

    def audio2motion_worker(self):
        """
        音频驱动线程包装器，确保异常可回传到主线程。
        """
        try:
            self._audio2motion_worker()
        except Exception as e:
            self.worker_exception = e
            self.stop_event.set()
        
    def _audio2motion_worker(self):
        """
        首级生产者：消费音频特征并产出逐帧驱动参数。

        时序与窗口：
        - 采用 seq_frames 长窗推理，按 valid_clip_len 增量推进；
        - 在线模式首段需先建立融合起点，再输出有效帧。

        边界与容错：
        - 末段不足一窗时用最后一帧特征补齐；
        - 队列满时超时重试，避免阻塞死锁；
        - 数据缓存超过两窗时截断旧数据，控制内存增长。
        """
        is_end = False
        seq_frames = self.audio2motion.seq_frames
        valid_clip_len = self.audio2motion.valid_clip_len
        aud_feat_dim = self.wav2feat.feat_dim
        item_buffer = np.zeros((0, aud_feat_dim), dtype=np.float32)

        res_kp_seq = None
        res_kp_seq_valid_start = None if self.online_mode else 0
        
        global_idx = 0   # 全局帧号：用于条件序列对齐模板索引。
        local_idx = 0    # 本地游标：指向当前缓冲中待处理起始位置。
        gen_frame_idx = 0
        while not self.stop_event.is_set():
            try:
                item = self.audio2motion_queue.get(timeout=1)    # 从输入队列读取新音频特征块。
            except queue.Empty:
                continue
            if item is None:
                is_end = True
            else:
                item_buffer = np.concatenate([item_buffer, item], 0)

            if not is_end and item_buffer.shape[0] < valid_clip_len:
                # 未达到最小有效长度时继续等待，避免过短窗口导致结果抖动。
                continue
            else:
                self.audio_feat = np.concatenate([self.audio_feat, item_buffer], 0)
                item_buffer = np.zeros((0, aud_feat_dim), dtype=np.float32)

            while True:
                # 每轮尝试取一个完整窗口；在线模式可能因新数据不足而提前退出循环。
                aud_feat = self.audio_feat[local_idx: local_idx+seq_frames]
                real_valid_len = valid_clip_len
                if len(aud_feat) == 0:
                    break
                elif len(aud_feat) < seq_frames:
                    if not is_end:
                        # 非结束态且窗口不足时等待后续音频块。
                        break
                    else:
                        # 结束态下对尾段补齐，确保网络输入维度合法。
                        real_valid_len = len(aud_feat)
                        pad = np.stack([aud_feat[-1]] * (seq_frames - len(aud_feat)), 0)
                        aud_feat = np.concatenate([aud_feat, pad], 0)

                aud_cond = self.condition_handler(aud_feat, global_idx + self.cond_idx_start)[None]
                res_kp_seq = self.audio2motion(aud_cond, res_kp_seq)
                if res_kp_seq_valid_start is None:
                    # 在线模式首窗仅用于建立融合基准，不立即下发到下游队列。
                    res_kp_seq_valid_start = res_kp_seq.shape[1] - self.audio2motion.fuse_length
                    d0 = self.audio2motion.cvt_fmt(res_kp_seq[0:1])[0]
                    self.motion_stitch.d0 = d0

                    local_idx += real_valid_len
                    global_idx += real_valid_len
                    continue
                else:
                    valid_res_kp_seq = res_kp_seq[:, res_kp_seq_valid_start: res_kp_seq_valid_start + real_valid_len]
                    x_d_info_list = self.audio2motion.cvt_fmt(valid_res_kp_seq)

                    for x_d_info in x_d_info_list:
                        frame_idx = _mirror_index(gen_frame_idx, self.source_info_frames)
                        ctrl_kwargs = self._get_ctrl_info(gen_frame_idx)

                        while not self.stop_event.is_set():
                            try:
                                self.motion_stitch_queue.put([frame_idx, x_d_info, ctrl_kwargs], timeout=1)
                                break
                            except queue.Full:
                                continue

                        gen_frame_idx += 1

                    res_kp_seq_valid_start += real_valid_len
                
                    local_idx += real_valid_len
                    global_idx += real_valid_len

                L = res_kp_seq.shape[1] 
                if L > seq_frames * 2:
                    cut_L = L - seq_frames * 2
                    res_kp_seq = res_kp_seq[:, cut_L:]
                    res_kp_seq_valid_start -= cut_L

                if local_idx >= len(self.audio_feat):
                    break

            L = len(self.audio_feat)
            if L > seq_frames * 2:
                cut_L = L - seq_frames * 2
                self.audio_feat = self.audio_feat[cut_L:]
                local_idx -= cut_L

            if is_end:
                break
        
        self.motion_stitch_queue.put(None)

    def close(self):
        """
        关闭管线并等待所有线程安全退出。

        时序：先向首级队列写入 None，再 join 全部线程，最后关闭写盘器。
        容错：若任一工作线程曾抛异常，会在此统一向外抛出。
        """

        # 向首级队列投递哨兵值，触发整条队列链路逐级收尾。
        self.audio2motion_queue.put(None)
        # 等待所有工作线程结束，保证文件句柄和缓存均已回收。
        for thread in self.thread_list:
            thread.join()

        try:
            self.writer.close()
            self.writer_pbar.close()
        except:
            traceback.print_exc()

        # 若后台线程有异常，最终在 close 阶段抛出，避免静默失败。
        if self.worker_exception is not None:
            raise self.worker_exception
        
    def run_chunk(self, audio_chunk, chunksize=(3, 5, 2)):
        """
        推入一段实时音频。

        输入：
        - audio_chunk：单段波形数据；
        - chunksize：特征提取窗口配置。

        容错：当首级队列已满时采用超时重试，避免直接丢帧。
        """

        # 将原始音频转换为模型可消费的特征序列。
        aud_feat = self.wav2feat(audio_chunk, chunksize=chunksize)
        while not self.stop_event.is_set():
            try:
                self.audio2motion_queue.put(aud_feat, timeout=1)
                break
            except queue.Full:
                continue



