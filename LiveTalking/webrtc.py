###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  作者信息：LiveTalking@lipku（原仓库注释保留同等含义）
#  许可证：Apache License 2.0（本文件受该许可证约束）
#  许可证全文： http://www.apache.org/licenses/LICENSE-2.0
#
#  说明：本文件负责把数字人渲染结果封装为 WebRTC 轨道并按时钟发送。
###############################################################################

import asyncio
import json
import logging
import os
import threading
import time
from typing import Tuple, Dict, Optional, Set, Union
from av.frame import Frame
from av.packet import Packet
from av import AudioFrame, VideoFrame
import fractions
import numpy as np

# 每个音频包对应 20ms。
AUDIO_PTIME = 0.020  # 音频打包时长 20ms
VIDEO_CLOCK_RATE = 90000
# 每个视频包对应 40ms，即 25fps。
VIDEO_PTIME = 0.040 #1 / 25  # 30fps
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)
SAMPLE_RATE = 16000
AUDIO_SAMPLES_PER_FRAME = int(SAMPLE_RATE * AUDIO_PTIME)
AUDIO_TIME_BASE = fractions.Fraction(1, SAMPLE_RATE)


def _float_env(name: str, default: float, min_value: float, max_value: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(max(value, min_value), max_value)


# 把 WebRTC 输出从“实时直吐”改成“带缓冲的播放器模型”：
# - 初始先攒一段帧，后端推理慢时只表现为首帧更晚；
# - 中途短暂断粮时，视频重复最后一帧、音频补静音，避免浏览器播放元素停住。
WEBRTC_INITIAL_BUFFER_S = _float_env("WEBRTC_INITIAL_BUFFER_S", 2.5, 0.0, 30.0)
WEBRTC_QUEUE_BUFFER_S = _float_env("WEBRTC_QUEUE_BUFFER_S", 6.0, 1.0, 60.0)
WEBRTC_UNDERFLOW_WAIT_S = _float_env("WEBRTC_UNDERFLOW_WAIT_S", 0.18, 0.0, 2.0)


def _frames_for_duration(kind: str, duration_s: float) -> int:
    if duration_s <= 0:
        return 0
    ptime = VIDEO_PTIME if kind == "video" else AUDIO_PTIME
    return max(1, int(round(duration_s / ptime)))

#from aiortc.contrib.media import MediaPlayer, MediaRelay
#from aiortc.rtcrtpsender import RTCRtpSender
from aiortc import (
    MediaStreamTrack,
)

logging.basicConfig()
logger = logging.getLogger(__name__)
from logger import logger as mylogger


class PlayerStreamTrack(MediaStreamTrack):
    """LiveTalking 自定义媒体轨道。

    功能说明：
    1) 维护音频/视频各自的发送时间戳；
    2) 从内部队列取帧并补齐 pts/time_base；
    3) 在音频帧输出时回调事件点，用于文本流状态同步。
    """

    def __init__(self, player, kind):
        super().__init__()  # 必须先初始化父类轨道状态
        self.kind = kind
        self._player = player
        self._initial_buffer_frames = _frames_for_duration(kind, WEBRTC_INITIAL_BUFFER_S)
        queue_max_frames = max(
            100,
            _frames_for_duration(kind, WEBRTC_QUEUE_BUFFER_S),
            self._initial_buffer_frames + 2,
        )
        self._queue = asyncio.Queue(maxsize=queue_max_frames)
        self._buffer_ready = self._initial_buffer_frames <= 1
        self._last_frame: Optional[Frame] = None
        self._last_video_snapshot: Optional[np.ndarray] = None
        self._underflow_count = 0
        self._last_underflow_log_at = 0.0
        # timelist 用于调试，但不应无限增长，只保留最近 10 个时间戳
        self.timelist = []
        self._max_timelist_size = 10
        self.current_frame_count = 0
        if self.kind == 'video':
            self.framecount = 0
            self.lasttime = time.perf_counter()
            self.totaltime = 0

    async def _wait_for_initial_buffer(self) -> None:
        if self._buffer_ready:
            return

        last_log_at = 0.0
        while self.readyState == "live" and self._queue.qsize() < self._initial_buffer_frames:
            now = time.time()
            if now - last_log_at >= 2.0:
                last_log_at = now
                mylogger.info(
                    "webrtc %s track buffering: %d/%d frames",
                    self.kind,
                    self._queue.qsize(),
                    self._initial_buffer_frames,
                )
            await asyncio.sleep(0.02)

        self._buffer_ready = True
        mylogger.info(
            "webrtc %s track initial buffer ready: %d frames",
            self.kind,
            self._queue.qsize(),
        )

    def _remember_real_frame(self, frame: Optional[Frame]) -> None:
        if frame is None:
            return

        self._last_frame = frame
        if self.kind == "video":
            self._last_video_snapshot = None

    def _build_gap_frame(self) -> Optional[Frame]:
        self._underflow_count += 1
        now = time.time()
        if now - self._last_underflow_log_at >= 2.0:
            self._last_underflow_log_at = now
            mylogger.warning(
                "webrtc %s track underflow, using buffered fallback frame; count=%d",
                self.kind,
                self._underflow_count,
            )

        if self.kind == "audio":
            frame = AudioFrame(format="s16", layout="mono", samples=AUDIO_SAMPLES_PER_FRAME)
            frame.planes[0].update(np.zeros((AUDIO_SAMPLES_PER_FRAME,), dtype=np.int16).tobytes())
            frame.sample_rate = SAMPLE_RATE
            return frame

        if self._last_frame is None:
            return None

        try:
            if self._last_video_snapshot is None:
                self._last_video_snapshot = self._last_frame.to_ndarray(format="bgr24")
            return VideoFrame.from_ndarray(self._last_video_snapshot.copy(), format="bgr24")
        except Exception as exc:
            mylogger.warning("webrtc video fallback frame build failed: %s", exc)
            return None

    async def _get_frame_with_fallback(self) -> Tuple[Frame, Optional[Dict]]:
        try:
            frame, eventpoint = await asyncio.wait_for(
                self._queue.get(),
                timeout=WEBRTC_UNDERFLOW_WAIT_S,
            )
            self._remember_real_frame(frame)
            return frame, eventpoint
        except asyncio.TimeoutError:
            frame = self._build_gap_frame()
            if frame is not None:
                return frame, None

            frame, eventpoint = await self._queue.get()
            self._remember_real_frame(frame)
            return frame, eventpoint
    
    _start: float
    _timestamp: int

    async def next_timestamp(self) -> Tuple[int, fractions.Fraction]:
        if self.readyState != "live":
            raise Exception

        if self.kind == 'video':
            if hasattr(self, "_timestamp"):
                # 采用固定步长推进视频时间戳，保持输出帧率稳定。
                self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
                self.current_frame_count += 1
                wait = self._start + self.current_frame_count * VIDEO_PTIME - time.time()
                if wait>0:
                    await asyncio.sleep(wait)
            else:
                # 首帧初始化时钟基准。
                self._start = time.time()
                self._timestamp = 0
                # 限制 timelist 大小，防止内存泄漏
                if len(self.timelist) >= self._max_timelist_size:
                    self.timelist.pop(0)
                self.timelist.append(self._start)
                mylogger.info('video start:%f',self._start)
            return self._timestamp, VIDEO_TIME_BASE
        else: #audio
            if hasattr(self, "_timestamp"):
                # 音频同样用固定步长推进，避免因为处理抖动导致累计误差。
                self._timestamp += int(AUDIO_PTIME * SAMPLE_RATE)
                self.current_frame_count += 1
                wait = self._start + self.current_frame_count * AUDIO_PTIME - time.time()
                if wait>0:
                    await asyncio.sleep(wait)
            else:
                self._start = time.time()
                self._timestamp = 0
                # 限制 timelist 大小，防止内存泄漏
                if len(self.timelist) >= self._max_timelist_size:
                    self.timelist.pop(0)
                self.timelist.append(self._start)
                mylogger.info('audio start:%f',self._start)
            return self._timestamp, AUDIO_TIME_BASE

    async def recv(self) -> Union[Frame, Packet]:
        # 确保底层生产线程已启动。
        self._player._start(self)
        await self._wait_for_initial_buffer()

        # 队列元素由上游组织为 (frame, eventpoint)：
        # - frame: 音频或视频帧对象
        # - eventpoint: 事件点（例如 start/end），用于同步聊天流状态
        frame,eventpoint = await self._get_frame_with_fallback()
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base
        if eventpoint and self._player is not None:
            self._player.notify(eventpoint)
        if frame is None:
            self.stop()
            raise Exception
        if self.kind == 'video':
            # 统计实际输出 FPS，便于观察时钟漂移与积压情况。
            self.totaltime += (time.perf_counter() - self.lasttime)
            self.framecount += 1
            self.lasttime = time.perf_counter()
            if self.framecount==100:
                mylogger.info(f"------actual avg final fps:{self.framecount/self.totaltime:.4f}")
                self.framecount = 0
                self.totaltime=0
        return frame
    
    def stop(self):
        super().stop()
        # 清空剩余队列帧并释放 player 引用，防止连接断开后的资源泄漏。
        while not self._queue.empty():
            item = self._queue.get_nowait()
            del item
        if self._player is not None:
            self._player._stop(self)
            self._player = None

def player_worker_thread(
    quit_event,
    loop,
    container,
    audio_track,
    video_track
):
    # 工作线程中调用容器的 render 主循环，持续向轨道队列投递帧。
    container.render(quit_event,loop,audio_track,video_track)

class HumanPlayer:

    def __init__(
        self, nerfreal, format=None, options=None, timeout=None, loop=False, decode=True
    ):
        self.__thread: Optional[threading.Thread] = None
        self.__thread_quit: Optional[threading.Event] = None

        # 记录当前已激活的轨道集合。
        # 当最后一个轨道停止时，自动停止底层 worker 线程。
        self.__started: Set[PlayerStreamTrack] = set()
        self.__audio: Optional[PlayerStreamTrack] = None
        self.__video: Optional[PlayerStreamTrack] = None

        self.__audio = PlayerStreamTrack(self, kind="audio")
        self.__video = PlayerStreamTrack(self, kind="video")

        self.__container = nerfreal

    def notify(self,eventpoint):
        if self.__container is not None:
            self.__container.notify(eventpoint)

    @property
    def audio(self) -> MediaStreamTrack:
        """返回音频轨道对象（aiortc.MediaStreamTrack）。"""
        return self.__audio

    @property
    def video(self) -> MediaStreamTrack:
        """返回视频轨道对象（aiortc.MediaStreamTrack）。"""
        return self.__video

    def _start(self, track: PlayerStreamTrack) -> None:
        # 首个轨道启动时创建 worker 线程；后续轨道复用同一线程。
        self.__started.add(track)
        if self.__thread is None:
            self.__log_debug("Starting worker thread")
            self.__thread_quit = threading.Event()
            self.__thread = threading.Thread(
                name="media-player",
                target=player_worker_thread,
                args=(
                    self.__thread_quit,
                    asyncio.get_event_loop(),
                    self.__container,
                    self.__audio,
                    self.__video                   
                ),
            )
            self.__thread.start()

    def _stop(self, track: PlayerStreamTrack) -> None:
        # 轨道停止后从集合移除；当集合为空时停止 worker。
        self.__started.discard(track)

        if not self.__started and self.__thread is not None:
            self.__log_debug("Stopping worker thread")
            self.__thread_quit.set()
            self.__thread.join()
            self.__thread = None

        if not self.__started and self.__container is not None:
            # 仅释放引用，具体资源清理由上层会话生命周期管理。
            self.__container = None

    def __log_debug(self, msg: str, *args) -> None:
        mylogger.debug(f"HumanPlayer {msg}", *args)
