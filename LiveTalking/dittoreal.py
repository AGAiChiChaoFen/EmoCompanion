import sys
import time
import queue
import cv2
import numpy as np

from pathlib import Path
from queue import Queue
from threading import Thread, Event

from basereal import BaseReal
from baseasr import BaseASR
from logger import logger


def _resolve_ditto_root(explicit_root: str = "") -> Path:
    # 解析 ditto-talkinghead 根目录：
    # - 若用户显式传入路径且存在，则优先使用；
    # - 否则回退到项目默认相对路径 ../ditto-talkinghead。
    if explicit_root:
        root = Path(explicit_root).expanduser().resolve()
        if root.exists():
            return root
    return (Path(__file__).resolve().parent.parent / "ditto-talkinghead").resolve()


def _safe_imread(path: str) -> np.ndarray:
    # 头像源图读取失败时回退为黑帧，避免初始化阶段直接崩溃。
    # 这样即便输入路径错误，系统仍能启动并输出明确日志。
    frame = cv2.imread(path)
    if frame is None:
        logger.warning("failed to read ditto source image: %s, fallback to black frame", path)
        return np.zeros((512, 512, 3), dtype=np.uint8)
    return frame


class DittoASR(BaseASR):
    """Ditto 场景下的 ASR 适配器。

    该实现不做声学特征提取，只负责把 20ms PCM 帧原样转发到 output_queue，
    让下游 Ditto 推理线程按统一节拍消费。
    """

    def run_step(self):
        # Ditto 采用“每次取 batch_size*2 帧”的节拍：
        # 其中 2 对应视频 25fps 与音频 50fps 的常见倍频关系。
        for _ in range(self.batch_size * 2):
            frame, audio_type, eventpoint = self.get_audio_frame()
            self.output_queue.put((frame, audio_type, eventpoint))


class DittoReal(BaseReal):
    def __init__(self, opt, model, avatar):
        super().__init__(opt)

        self.fps = opt.fps
        self.batch_size = opt.batch_size
        self.res_frame_queue = Queue(maxsize=max(32, self.batch_size * 4))

        # ditto_chunksize 为 [left, center, right] 三段窗口配置。
        # split_len 是每次送入 SDK 的总采样长度；slice_step 决定窗口滑动步长。
        self.ditto_chunksize = tuple(opt.ditto_chunksize)
        self.ditto_split_len = int(sum(self.ditto_chunksize) * 0.04 * 16000) + 80
        self.ditto_slice_step = self.ditto_chunksize[1] * 640

        # sdk_frame_queue 用于接收 StreamSDK 产出的渲染帧。
        self.sdk_frame_queue = Queue(maxsize=256)
        self.ditto_audio_frames_consumed = 0
        self.sdk = model["streamsdk_cls"](model["cfg_pkl"], model["data_root"])
        _bind_ditto_writer_to_queue(self.sdk, self.sdk_frame_queue)
        output_path = f"temp_ditto_session_{self.sessionid}_{int(time.time())}.mp4"
        self.sdk.setup(model["source_path"], output_path)

        source_img = avatar["source_img"]
        self.frame_list_cycle = [source_img]

        self.asr = DittoASR(opt, self)
        self.asr.warm_up()

    def paste_back_frame(self, pred_frame, idx: int):
        # Ditto 输出已是完整目标帧，这里无需额外贴回。
        return pred_frame

    def _build_audio_frames_for_video(self, audio_meta_queue: Queue):
        # 每个视频帧对应打包 2 个 20ms 音频帧（总计 40ms），与 25fps 对齐。
        # 若音频元数据暂时不足，则补静音帧维持时钟稳定。
        audio_frames = []
        for _ in range(2):
            try:
                audio_frames.append(audio_meta_queue.get_nowait())
            except queue.Empty:
                audio_frames.append((np.zeros(self.chunk, dtype=np.float32), 1, None))
        return audio_frames

    def _drain_sdk_frames(self, audio_meta_queue: Queue):
        # 持续拉取 SDK 已完成帧，并与对应音频包打包后送入总渲染队列。
        pushed = 0
        while True:
            try:
                frame_rgb = self.sdk_frame_queue.get_nowait()
            except queue.Empty:
                break

            # StreamSDK 输出为 RGB，这里转换为 BGR 以适配 OpenCV/后续编码链路。
            frame_bgr = frame_rgb[..., ::-1].copy()
            audio_frames = self._build_audio_frames_for_video(audio_meta_queue)
            self.res_frame_queue.put((frame_bgr, 0, audio_frames))
            pushed += 1
        return pushed

    def _append_asr_output(self, audio_for_ditto: np.ndarray, audio_meta_queue: Queue, item):
        frame, audio_type, eventpoint = item
        audio_meta_queue.put((frame, audio_type, eventpoint))
        self.ditto_audio_frames_consumed += 1
        return np.concatenate([audio_for_ditto, frame], axis=0)

    def _run_ready_ditto_chunks(self, audio_for_ditto: np.ndarray):
        ran_chunks = 0
        while len(audio_for_ditto) >= self.ditto_split_len:
            # 当缓存达到一个完整窗口时，送入 SDK 推理并按中心窗口步长滑动。
            audio_chunk = audio_for_ditto[:self.ditto_split_len].copy()
            self.sdk.run_chunk(audio_chunk, self.ditto_chunksize)
            audio_for_ditto = audio_for_ditto[self.ditto_slice_step:]
            ran_chunks += 1
        return audio_for_ditto, ran_chunks

    def _drain_asr_output_queue(self, audio_for_ditto: np.ndarray, audio_meta_queue: Queue):
        # 离线导出时 ASR 生产远快于 PyTorch Ditto 推理。退出前必须把已生产但
        # 尚未消费的音频帧全部送入 Ditto，否则只会生成开头一小段视频。
        drained = 0
        idle_deadline = time.time() + 0.2
        while True:
            try:
                item = self.asr.output_queue.get_nowait()
            except queue.Empty:
                self._drain_sdk_frames(audio_meta_queue)
                if time.time() >= idle_deadline:
                    break
                time.sleep(0.01)
                continue

            audio_for_ditto = self._append_asr_output(audio_for_ditto, audio_meta_queue, item)
            audio_for_ditto, ran_chunks = self._run_ready_ditto_chunks(audio_for_ditto)
            if ran_chunks:
                self._drain_sdk_frames(audio_meta_queue)
            drained += 1
            idle_deadline = time.time() + 0.2

        if drained:
            logger.info("drained pending ditto ASR frames before tail flush: %s", drained)
        return audio_for_ditto

    def _close_sdk_and_drain_frames(self, audio_meta_queue: Queue):
        close_errors = []

        def close_sdk():
            try:
                self.sdk.close()
            except Exception as e:
                close_errors.append(e)

        close_thread = Thread(target=close_sdk, daemon=True, name="ditto_sdk_close")
        close_thread.start()
        while close_thread.is_alive():
            pushed = self._drain_sdk_frames(audio_meta_queue)
            if pushed == 0:
                time.sleep(0.01)
        close_thread.join()

        self._drain_sdk_frames(audio_meta_queue)
        if close_errors:
            logger.warning("ditto sdk close error: %s", close_errors[0])

    def _inference_loop(self, quit_event: Event, drain_pending: bool = False, max_audio_frames=None):
        # 初始化左侧预卷积上下文，避免首段直接推理带来边界伪影。
        audio_for_ditto = np.zeros((self.ditto_chunksize[0] * 640,), dtype=np.float32)
        audio_meta_queue = Queue(maxsize=6000)

        logger.info("start ditto inference adapter loop")
        while not quit_event.is_set():
            if max_audio_frames is not None and self.ditto_audio_frames_consumed >= max_audio_frames:
                logger.info(
                    "ditto inference reached target audio frames: %s/%s",
                    self.ditto_audio_frames_consumed,
                    max_audio_frames,
                )
                break

            did_work = False
            try:
                item = self.asr.output_queue.get(timeout=0.02)
                audio_for_ditto = self._append_asr_output(audio_for_ditto, audio_meta_queue, item)
                did_work = True
            except queue.Empty:
                pass

            audio_for_ditto, ran_chunks = self._run_ready_ditto_chunks(audio_for_ditto)
            if ran_chunks:
                did_work = True

            pushed = self._drain_sdk_frames(audio_meta_queue)
            if pushed > 0:
                did_work = True

            if not did_work:
                # 空闲时短暂让出 CPU，防止忙等。
                time.sleep(0.005)

        if drain_pending:
            audio_for_ditto = self._drain_asr_output_queue(audio_for_ditto, audio_meta_queue)

        # 收尾：把最后不足窗口的一段补零后推理，避免尾音被截断。
        if len(audio_for_ditto) > 0:
            tail = np.pad(audio_for_ditto, (0, max(0, self.ditto_split_len - len(audio_for_ditto))), mode="constant")
            self.sdk.run_chunk(tail, self.ditto_chunksize)

        self._close_sdk_and_drain_frames(audio_meta_queue)
        logger.info("ditto inference adapter loop stop")

    def render(self, quit_event, loop=None, audio_track=None, video_track=None):
        # 渲染主入口：
        # 1) 启动 TTS 生产音频帧；
        # 2) 启动 Ditto 推理线程；
        # 3) 启动音视频发送线程；
        # 4) 主线程按节拍驱动 ASR run_step。
        self.init_customindex()
        self.tts.render(quit_event)

        infer_quit_event = Event()
        infer_thread = Thread(target=self._inference_loop, args=(infer_quit_event,), daemon=True, name="ditto_infer")
        infer_thread.start()

        process_quit_event = Event()
        process_thread = Thread(
            target=self.process_frames,
            args=(process_quit_event, loop, audio_track, video_track),
            daemon=True,
            name="ditto_process",
        )
        process_thread.start()

        try:
            while not quit_event.is_set():
                self.asr.run_step()
                if video_track and video_track._queue.qsize() >= 5:
                    # 下游积压过多时进行动态退避，避免内存与时延失控。
                    time.sleep(0.04 * video_track._queue.qsize() * 0.8)
        finally:
            infer_quit_event.set()
            infer_thread.join()

            process_quit_event.set()
            process_thread.join()

            logger.info("dittoreal thread stop")


def _bind_ditto_writer_to_queue(sdk, frame_queue: Queue):
    # 重绑 SDK 写线程：把 writer_queue 中的帧转发到本地 frame_queue。
    # 这样可直接接入 LiveTalking 自己的合成/推流主循环。
    def custom_writer_worker():
        while not sdk.stop_event.is_set():
            try:
                item = sdk.writer_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                break
            frame_queue.put(item)
            pbar = getattr(sdk, "writer_pbar", None)
            if pbar is not None:
                pbar.update()

    sdk._writer_worker = custom_writer_worker


def load_model(opt):
    # 构造 Ditto 模型描述字典。
    # 注意：此处只做路径与配置校验，不在这里创建每会话 SDK 实例。
    ditto_root = _resolve_ditto_root(getattr(opt, "ditto_root", ""))
    if str(ditto_root) not in sys.path:
        sys.path.insert(0, str(ditto_root))

    from stream_pipeline_online import StreamSDK

    cfg_pkl = getattr(opt, "ditto_cfg_pkl", "")
    data_root = getattr(opt, "ditto_data_root", "")
    source_path = getattr(opt, "ditto_source_path", "")

    if not cfg_pkl or not data_root or not source_path:
        raise ValueError("ditto model needs --ditto_cfg_pkl --ditto_data_root --ditto_source_path")

    return {
        "streamsdk_cls": StreamSDK,
        "cfg_pkl": cfg_pkl,
        "data_root": data_root,
        "source_path": source_path,
    }


def load_avatar(opt):
    # 头像加载与模型加载拆分，便于后续替换成视频源或多头像热切换。
    source_path = getattr(opt, "ditto_source_path", "")
    if not source_path:
        raise ValueError("ditto model needs --ditto_source_path")
    return {
        "source_img": _safe_imread(source_path),
    }


def warm_up(batch_size, model, avatar):
    # DittoReal 在每个会话启动时都会新建 StreamSDK，
    # 因此这里不执行全局预热，保持启动逻辑简单可控。
    return
