###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  作者信息：LiveTalking@lipku（原仓库注释保留同等含义）
#  许可证：Apache License 2.0（本文件受该许可证约束）
#  许可证全文： http://www.apache.org/licenses/LICENSE-2.0
#
#  说明：本文件为 ASR 基类，负责音频帧缓冲、静音回退与输出队列管理。
###############################################################################

import time
import numpy as np

import queue
from queue import Queue
import torch.multiprocessing as mp

from basereal import BaseReal


class BaseASR:
    def __init__(self, opt, parent:BaseReal = None):
        self.opt = opt
        self.parent = parent

        # ASR 输入按固定帧率切片。
        # 例如 fps=50 时，每帧时长为 20ms。
        self.fps = opt.fps # 每帧 20ms（当 fps=50 时）
        self.sample_rate = 16000

        # chunk 表示“每帧包含多少采样点”。
        # 16kHz 下，20ms 对应 320 个采样。
        self.chunk = self.sample_rate // self.fps # 16kHz 下每帧约 320 个采样点

        # queue：上游（TTS/外部音频）输入到 ASR 的原始音频帧队列。
        # output_queue：ASR 处理后输出给渲染线程的音频帧队列。
        # 防止内存泄漏：限制队列最大长度
        self.queue = Queue(maxsize=3000)  # 约 60 秒音频 @ 50fps
        self.output_queue = mp.Queue(maxsize=3000)

        # batch_size 由推理线程控制每次处理多少帧。
        self.batch_size = opt.batch_size

        # 以下参数常用于“滑动窗口特征拼接”场景。
        # BaseASR 本身不实现特征提取，只提供通用字段供子类复用。
        self.frames = []
        self.stride_left_size = opt.l
        self.stride_right_size = opt.r
        self.feat_queue = mp.Queue(2)

    def flush_talk(self):
        # 清空等待播报的音频帧，常用于“打断当前说话”。
        self.queue.queue.clear()

    def put_audio_frame(self,audio_chunk,datainfo:dict): # 16kHz、20ms 的 PCM 帧
        # datainfo 会随音频帧一起传递，用于事件同步（例如 chat_stream 的 start/end）。
        self.queue.put((audio_chunk,datainfo))

    # 返回值说明：
    # frame: 音频 PCM 帧（float32，范围通常在 [-1,1]）
    # type:  0=正常语音；1=静音；>1=自定义音频类型
    # eventpoint: 与该帧绑定的事件点（用于文本流与音频起止对齐）
    def get_audio_frame(self):        
        try:
            frame,eventpoint = self.queue.get(block=True,timeout=0.01)
            type = 0
        except queue.Empty:
            # 当上游暂时无帧时：
            # 1) 若父对象处于自定义素材状态，继续输出自定义音轨；
            # 2) 否则补零（静音帧），保证音频时钟连续不抖动。
            if self.parent and self.parent.curr_state>1: #播放自定义音频
                frame = self.parent.get_audio_stream(self.parent.curr_state)
                type = self.parent.curr_state
            else:
                frame = np.zeros(self.chunk, dtype=np.float32)
                type = 1
            eventpoint = None

        return frame,type,eventpoint 

    # 从输出队列获取下一帧，供渲染线程消费。
    def get_audio_out(self): 
        return self.output_queue.get()
    
    def warm_up(self):
        # 预热：先填满左右上下文窗口，再丢弃左侧过渡段。
        # 这样可让第一批可用帧在窗口对齐后再进入主流程。
        for _ in range(self.stride_left_size + self.stride_right_size):
            audio_frame,type,eventpoint=self.get_audio_frame()
            self.frames.append(audio_frame)
            self.output_queue.put((audio_frame,type,eventpoint))
        for _ in range(self.stride_left_size):
            self.output_queue.get()
        
        # 防止内存泄漏：限制 frames 列表大小
        max_frames = self.stride_left_size + self.stride_right_size + 100
        if len(self.frames) > max_frames:
            self.frames = self.frames[-max_frames:]

    def run_step(self):
        # 由子类实现：定义“每一步如何从输入队列取帧并产出到输出队列”。
        pass

    def get_next_feat(self,block,timeout):        
        # 由特征提取子类向该队列投递声学特征，渲染侧按需拉取。
        return self.feat_queue.get(block,timeout)