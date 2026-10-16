###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  作者信息：LiveTalking@lipku（原仓库注释保留同等含义）
#  许可证：Apache License 2.0（本文件受该许可证约束）
#  许可证全文： http://www.apache.org/licenses/LICENSE-2.0
#
#  说明：本文件提供多后端 TTS 适配，把文本流统一转换为 16kHz/20ms 音频帧。
###############################################################################
from __future__ import annotations
import time
import numpy as np
import soundfile as sf
import resampy
import asyncio
import edge_tts

import os
import hmac
import hashlib
import base64
import json
import uuid

from typing import Iterator

import requests

import queue
from queue import Queue
from io import BytesIO
import copy,websockets,gzip
import azure.cognitiveservices.speech as speechsdk

from threading import Thread, Event
from enum import Enum

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from basereal import BaseReal

from logger import logger
class State(Enum):
    RUNNING=0
    PAUSE=1

class BaseTTS:
    def __init__(self, opt, parent:BaseReal):
        self.opt=opt
        self.parent = parent

        self.fps = opt.fps # 单帧时长由 fps 决定，默认 50fps 即 20ms
        self.sample_rate = 16000
        self.chunk = self.sample_rate // self.fps # 每帧采样点数，16kHz 下通常为 320
        self.input_stream = BytesIO()

        # 生产者-消费者队列：上游塞入文本消息，TTS 线程异步取出并合成。
        # 防止内存泄漏：限制队列最大长度为 1000 条消息
        self.msgqueue = Queue(maxsize=1000)
        self._pending_msg = None
        self.state = State.RUNNING

    def flush_talk(self):
        # 打断当前播报：清空待播消息，并让后续流式分发立即停止。
        self.msgqueue.queue.clear()
        self._pending_msg = None
        self.state = State.PAUSE

    def put_msg_txt(self,msg:str,datainfo:dict={}): 
        if len(msg)>0:
            self.msgqueue.put((msg,datainfo))

    def render(self,quit_event):
        # 每个会话独立启动一个 TTS 线程，避免阻塞主渲染循环。
        process_thread = Thread(target=self.process_tts, args=(quit_event,))
        process_thread.start()

    def _can_merge_datainfo(self, left: dict, right: dict) -> bool:
        left_stream = left.get("chat_stream_id")
        right_stream = right.get("chat_stream_id")

        # 带有流标识时仅合并同一会话同一消息流，避免串流。
        if left_stream or right_stream:
            return (
                left_stream == right_stream
                and left.get("chat_sessionid") == right.get("chat_sessionid")
            )

        return left == right

    def _merge_text_batch(self, first_msg: tuple[str, dict]) -> tuple[str, dict]:
        text, datainfo = first_msg
        merged_text = text
        merged_chars = len(text)
        # 小窗口批处理：在极短时间内合并同流文本，减少“每字一请求”的开销。
        deadline = time.time() + 0.12

        while merged_chars < 120:
            remain = deadline - time.time()
            if remain <= 0:
                break

            try:
                next_msg: tuple[str, dict] = self.msgqueue.get(timeout=min(0.03, remain))
            except queue.Empty:
                break

            next_text, next_datainfo = next_msg
            if self._can_merge_datainfo(datainfo, next_datainfo):
                merged_text += next_text
                merged_chars += len(next_text)
            else:
                self._pending_msg = next_msg
                break

        return merged_text, datainfo
    
    def process_tts(self,quit_event):        
        while not quit_event.is_set():
            try:
                if self._pending_msg is not None:
                    msg = self._pending_msg
                    self._pending_msg = None
                else:
                    msg:tuple[str, dict] = self.msgqueue.get(block=True, timeout=1)
                self.state=State.RUNNING
            except queue.Empty:
                continue
            # 合并后再送入具体后端，保证低延迟与请求数之间的平衡。
            merged_msg = self._merge_text_batch(msg)
            self.txt_to_audio(merged_msg)
        logger.info('ttsreal thread stop')
    
    def txt_to_audio(self,msg:tuple[str, dict]):
        pass
    

###########################################################################################
class EdgeTTS(BaseTTS):
    def txt_to_audio(self,msg:tuple[str, dict]):
        voicename = self.opt.REF_FILE # 例如 "zh-CN-YunxiaNeural"
        text,textevent = msg
        t = time.time()
        asyncio.new_event_loop().run_until_complete(self.__main(voicename,text))
        logger.info(f'-------edge tts time:{time.time()-t:.4f}s')
        if self.input_stream.getbuffer().nbytes<=0: # EdgeTTS 无输出时直接返回，避免推送空帧
            logger.error('edgetts err!!!!!')
            return
        
        self.input_stream.seek(0)
        stream = self.__create_bytes_stream(self.input_stream)
        streamlen = stream.shape[0]
        idx=0
        while streamlen >= self.chunk and self.state==State.RUNNING:
            eventpoint={}
            streamlen -= self.chunk
            if idx==0:
                eventpoint={'status':'start','text':text}
                eventpoint.update(**textevent) # 起始帧绑定 start 事件，驱动前端流式状态切换
            elif streamlen<self.chunk:
                eventpoint={'status':'end','text':text}
                eventpoint.update(**textevent) # 末帧绑定 end 事件，保证一次文本播报闭环
            self.parent.put_audio_frame(stream[idx:idx+self.chunk],eventpoint)
            idx += self.chunk
        # if streamlen>0:  # 末尾不足 20ms 的残片默认丢弃，保持固定帧节拍
        #    self.queue.put(stream[idx:])
        self.input_stream.seek(0)
        self.input_stream.truncate() 

    def __create_bytes_stream(self,byte_stream):
        # 统一音频格式：转 float32、单声道、16kHz，确保后续帧切分一致。
        stream, sample_rate = sf.read(byte_stream) # [T*sample_rate,] float64
        logger.info(f'[INFO]tts audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)

        if stream.ndim > 1:
            logger.info(f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]
    
        if sample_rate != self.sample_rate and stream.shape[0]>0:
            logger.info(f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            stream = resampy.resample(x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)

        return stream
    
    async def __main(self,voicename: str, text: str):
        try:
            communicate = edge_tts.Communicate(text, voicename)

            # 流式读取云端返回的音频块并写入内存流，后续统一做 20ms 切片。
            first = True
            async for chunk in communicate.stream():
                if first:
                    first = False
                if chunk["type"] == "audio" and self.state==State.RUNNING:
                    # self.push_audio(chunk["data"])
                    self.input_stream.write(chunk["data"])
                    # file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    pass
        except Exception as e:
            logger.exception('edgetts')

###########################################################################################
class FishTTS(BaseTTS):
    def txt_to_audio(self,msg:tuple[str, dict]): 
        text,textevent = msg
        self.stream_tts(
            self.fish_speech(
                text,
                self.opt.REF_FILE,  
                self.opt.REF_TEXT,
                "zh", # 语种标识
                self.opt.TTS_SERVER, # TTS 服务地址
            ),
            msg
        )

    def fish_speech(self, text, reffile, reftext,language, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        req={
            'text':text,
            'reference_id':reffile,
            'format':'wav',
            'streaming':True,
            'use_memory_cache':'on'
        }
        try:
            res = requests.post(
                f"{server_url}/v1/tts",
                json=req,
                stream=True,
                headers={
                    "content-type": "application/json",
                },
            )
            end = time.perf_counter()
            logger.info(f"fish_speech Time to make POST: {end-start}s")

            if res.status_code != 200:
                logger.error("Error:%s", res.text)
                return
                
            first = True
        
            for chunk in res.iter_content(chunk_size=17640): # 44.1kHz、20ms、16bit 单声道约 1764 字节
                # print('chunk len:',len(chunk))
                if first:
                    end = time.perf_counter()
                    logger.info(f"fish_speech Time to first chunk: {end-start}s")
                    first = False
                if chunk and self.state==State.RUNNING:
                    yield chunk
            # print("fish_speech response.elapsed:", res.elapsed)
        except Exception as e:
            logger.exception('fishtts')

    def stream_tts(self,audio_stream,msg:tuple[str, dict]):
        text,textevent = msg
        first = True
        # 数据流：网络音频块 -> 重采样到 16k -> 20ms 切片 -> 推入 ASR/渲染总线。
        for chunk in audio_stream:
            if chunk is not None and len(chunk)>0:          
                stream = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767
                stream = resampy.resample(x=stream, sr_orig=44100, sr_new=self.sample_rate)
                # byte_stream=BytesIO(buffer)
                # stream = self.__create_bytes_stream(byte_stream)
                streamlen = stream.shape[0]
                idx=0
                while streamlen >= self.chunk:
                    eventpoint={}
                    if first:
                        eventpoint={'status':'start','text':text}
                        eventpoint.update(**textevent) # 首帧携带 start，驱动前端进入播报状态
                        first = False
                    self.parent.put_audio_frame(stream[idx:idx+self.chunk],eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
        eventpoint={'status':'end','text':text}
        eventpoint.update(**textevent) # 结束补一个 end 事件，保证状态机可闭环
        self.parent.put_audio_frame(np.zeros(self.chunk,np.float32),eventpoint) 

###########################################################################################
class SovitsTTS(BaseTTS):
    def txt_to_audio(self,msg:tuple[str, dict]): 
        text,textevent = msg
        self.stream_tts(
            self.gpt_sovits(
                text=text,
                reffile=self.opt.REF_FILE,
                reftext=self.opt.REF_TEXT,
                language="zh", # 语种标识
                server_url=self.opt.TTS_SERVER, # TTS 服务地址
            ),
            msg
        )

    def gpt_sovits(self, text, reffile, reftext,language, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        req={
            'text':text,
            'text_lang':language,
            'ref_audio_path':reffile,
            'prompt_text':reftext,
            'prompt_lang':language,
            'media_type':'ogg',
            'streaming_mode':True
        }
        # 历史兼容字段示例：text_language/character/emotion 等。
        # 若后端协议变更，可在这里统一调整映射。
        try:
            res = requests.post(
                f"{server_url}/tts",
                json=req,
                stream=True,
            )
            end = time.perf_counter()
            logger.info(f"gpt_sovits Time to make POST: {end-start}s")

            if res.status_code != 200:
                logger.error("Error:%s", res.text)
                return
                
            first = True
        
            for chunk in res.iter_content(chunk_size=None): # 按服务端原始块大小流式接收
                logger.info('chunk len:%d',len(chunk))
                if first:
                    end = time.perf_counter()
                    logger.info(f"gpt_sovits Time to first chunk: {end-start}s")
                    first = False
                if chunk and self.state==State.RUNNING:
                    yield chunk
            # print("gpt_sovits response.elapsed:", res.elapsed)
        except Exception as e:
            logger.exception('sovits')

    def __create_bytes_stream(self,byte_stream):
        # 统一转为单声道 float32，必要时重采样到 16kHz。
        stream, sample_rate = sf.read(byte_stream) # [T*sample_rate,] float64
        logger.info(f'[INFO]tts audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)

        if stream.ndim > 1:
            logger.info(f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]
    
        if sample_rate != self.sample_rate and stream.shape[0]>0:
            logger.info(f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            stream = resampy.resample(x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)

        return stream

    def stream_tts(self,audio_stream,msg:tuple[str, dict]):
        text,textevent = msg
        first = True
        for chunk in audio_stream:
            if chunk is not None and len(chunk)>0:          
                # 也可走“原始 PCM + 固定重采样”路径，这里统一走容器解码更稳健。
                byte_stream=BytesIO(chunk)
                stream = self.__create_bytes_stream(byte_stream)
                streamlen = stream.shape[0]
                idx=0
                while streamlen >= self.chunk:
                    eventpoint={}
                    if first:
                        eventpoint={'status':'start','text':text}
                        eventpoint.update(**textevent) 
                        first = False
                    self.parent.put_audio_frame(stream[idx:idx+self.chunk],eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
        eventpoint={'status':'end','text':text}
        eventpoint.update(**textevent) 
        self.parent.put_audio_frame(np.zeros(self.chunk,np.float32),eventpoint)

###########################################################################################
class CosyVoiceTTS(BaseTTS):
    def txt_to_audio(self,msg:tuple[str, dict]):
        text,textevent = msg 
        self.stream_tts(
            self.cosy_voice(
                text,
                self.opt.REF_FILE,  
                self.opt.REF_TEXT,
                "zh", # 语种标识
                self.opt.TTS_SERVER, # TTS 服务地址
            ),
            msg
        )

    def cosy_voice(self, text, reffile, reftext,language, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        payload = {
            'tts_text': text,
            'prompt_text': reftext
        }
        try:
            files = [('prompt_wav', ('prompt_wav', open(reffile, 'rb'), 'application/octet-stream'))]
            res = requests.request("GET", f"{server_url}/inference_zero_shot", data=payload, files=files, stream=True)
            
            end = time.perf_counter()
            logger.info(f"cosy_voice Time to make POST: {end-start}s")

            if res.status_code != 200:
                logger.error("Error:%s", res.text)
                return
                
            first = True
        
            for chunk in res.iter_content(chunk_size=9600): # 24kHz、20ms、16bit 单声道约 960 字节
                if first:
                    end = time.perf_counter()
                    logger.info(f"cosy_voice Time to first chunk: {end-start}s")
                    first = False
                if chunk and self.state==State.RUNNING:
                    yield chunk
        except Exception as e:
            logger.exception('cosyvoice')

    def stream_tts(self,audio_stream,msg:tuple[str, dict]):
        text,textevent = msg
        first = True
        for chunk in audio_stream:
            if chunk is not None and len(chunk)>0:          
                stream = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767
                stream = resampy.resample(x=stream, sr_orig=24000, sr_new=self.sample_rate)
                # byte_stream=BytesIO(buffer)
                # stream = self.__create_bytes_stream(byte_stream)
                streamlen = stream.shape[0]
                idx=0
                while streamlen >= self.chunk:
                    eventpoint={}
                    if first:
                        eventpoint={'status':'start','text':text}
                        eventpoint.update(**textevent) 
                        first = False
                    self.parent.put_audio_frame(stream[idx:idx+self.chunk],eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
        eventpoint={'status':'end','text':text}
        eventpoint.update(**textevent) 
        self.parent.put_audio_frame(np.zeros(self.chunk,np.float32),eventpoint) 

###########################################################################################
_PROTOCOL = "https://"
_HOST = "tts.cloud.tencent.com"
_PATH = "/stream"
_ACTION = "TextToStreamAudio"

class TencentTTS(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt,parent)
        self.appid = os.getenv("TENCENT_APPID")
        self.secret_key = os.getenv("TENCENT_SECRET_KEY")
        self.secret_id = os.getenv("TENCENT_SECRET_ID")
        self.voice_type = int(opt.REF_FILE)
        self.codec = "pcm"
        self.sample_rate = 16000
        self.volume = 0
        self.speed = 0
    
    def __gen_signature(self, params):
        sort_dict = sorted(params.keys())
        sign_str = "POST" + _HOST + _PATH + "?"
        for key in sort_dict:
            sign_str = sign_str + key + "=" + str(params[key]) + '&'
        sign_str = sign_str[:-1]
        hmacstr = hmac.new(self.secret_key.encode('utf-8'),
                           sign_str.encode('utf-8'), hashlib.sha1).digest()
        s = base64.b64encode(hmacstr)
        s = s.decode('utf-8')
        return s

    def __gen_params(self, session_id, text):
        params = dict()
        params['Action'] = _ACTION
        params['AppId'] = int(self.appid)
        params['SecretId'] = self.secret_id
        params['ModelType'] = 1
        params['VoiceType'] = self.voice_type
        params['Codec'] = self.codec
        params['SampleRate'] = self.sample_rate
        params['Speed'] = self.speed
        params['Volume'] = self.volume
        params['SessionId'] = session_id
        params['Text'] = text

        timestamp = int(time.time())
        params['Timestamp'] = timestamp
        params['Expired'] = timestamp + 24 * 60 * 60
        return params

    def txt_to_audio(self,msg:tuple[str, dict]):
        text,textevent = msg 
        self.stream_tts(
            self.tencent_voice(
                text,
                self.opt.REF_FILE,  
                self.opt.REF_TEXT,
                "zh", # 语种标识
                self.opt.TTS_SERVER, # TTS 服务地址
            ),
            msg
        )

    def tencent_voice(self, text, reffile, reftext,language, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        session_id = str(uuid.uuid1())
        params = self.__gen_params(session_id, text)
        signature = self.__gen_signature(params)
        headers = {
            "Content-Type": "application/json",
            "Authorization": str(signature)
        }
        url = _PROTOCOL + _HOST + _PATH
        try:
            res = requests.post(url, headers=headers,
                          data=json.dumps(params), stream=True)
            
            end = time.perf_counter()
            logger.info(f"tencent Time to make POST: {end-start}s")
                
            first = True
        
            for chunk in res.iter_content(chunk_size=6400): # 16kHz、20ms、16bit 单声道约 640 字节
                # logger.info('chunk len:%d',len(chunk))
                if first:
                    try:
                        rsp = json.loads(chunk)
                        # response["Code"] = rsp["Response"]["Error"]["Code"]
                        # response["Message"] = rsp["Response"]["Error"]["Message"]
                        logger.error("tencent tts:%s",rsp["Response"]["Error"]["Message"])
                        return
                    except:
                        end = time.perf_counter()
                        logger.info(f"tencent Time to first chunk: {end-start}s")
                        first = False                    
                if chunk and self.state==State.RUNNING:
                    yield chunk
        except Exception as e:
            logger.exception('tencent')

    def stream_tts(self,audio_stream,msg:tuple[str, dict]):
        text,textevent = msg
        first = True
        last_stream = np.array([],dtype=np.float32)
        for chunk in audio_stream:
            if chunk is not None and len(chunk)>0:          
                stream = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767
                stream = np.concatenate((last_stream,stream))
                # stream = resampy.resample(x=stream, sr_orig=24000, sr_new=self.sample_rate)
                # byte_stream=BytesIO(buffer)
                # stream = self.__create_bytes_stream(byte_stream)
                streamlen = stream.shape[0]
                idx=0
                while streamlen >= self.chunk:
                    eventpoint={}
                    if first:
                        eventpoint={'status':'start','text':text}
                        eventpoint.update(**textevent) 
                        first = False
                    self.parent.put_audio_frame(stream[idx:idx+self.chunk],eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
                last_stream = stream[idx:] # 保存不足一帧的尾部，拼接到下一个网络块
        eventpoint={'status':'end','text':text}
        eventpoint.update(**textevent) 
        self.parent.put_audio_frame(np.zeros(self.chunk,np.float32),eventpoint) 

###########################################################################################


class DoubaoTTS(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        # 从配置中读取火山引擎参数
        self.appid = os.getenv("DOUBAO_APPID")
        self.token = os.getenv("DOUBAO_TOKEN")
        _cluster = 'volcano_tts'
        _host = "openspeech.bytedance.com"
        self.api_url = f"wss://{_host}/api/v1/tts/ws_binary"
        
        self.request_json = {
            "app": {
                "appid": self.appid,
                "token": "access_token",
                "cluster": _cluster
            },
            "user": {
                "uid": "xxx"
            },
            "audio": {
                "voice_type": "xxx",
                "encoding": "pcm",
                "rate": 16000,
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": "xxx",
                "text": "字节跳动语音合成。",
                "text_type": "plain",
                "operation": "xxx"
            }
        }

    async def doubao_voice(self, text): # 流式返回 PCM 字节块
        start = time.perf_counter()
        voice_type = self.opt.REF_FILE

        try:
            # 创建请求对象
            default_header = bytearray(b'\x11\x10\x11\x00')
            submit_request_json = copy.deepcopy(self.request_json)
            submit_request_json["user"]["uid"] = self.parent.sessionid
            submit_request_json["audio"]["voice_type"] = voice_type
            submit_request_json["request"]["text"] = text
            submit_request_json["request"]["reqid"] = str(uuid.uuid4())
            submit_request_json["request"]["operation"] = "submit"
            payload_bytes = str.encode(json.dumps(submit_request_json))
            payload_bytes = gzip.compress(payload_bytes)  # 协议允许压缩，降低首包体积
            full_client_request = bytearray(default_header)
            full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))  # payload 长度（4 字节）
            full_client_request.extend(payload_bytes)  # payload 主体

            header = {"Authorization": f"Bearer; {self.token}"}
            first = True
            async with websockets.connect(self.api_url, extra_headers=header, ping_interval=None) as ws:
                await ws.send(full_client_request)
                while True:
                    res = await ws.recv()
                    header_size = res[0] & 0x0f
                    message_type = res[1] >> 4
                    message_type_specific_flags = res[1] & 0x0f
                    payload = res[header_size*4:]

                    if message_type == 0xb:  # 纯音频数据包
                        if message_type_specific_flags == 0:  # 无序号 ACK 包
                            # print("Payload size: 0")
                            continue
                        else:
                            if first:
                                end = time.perf_counter()
                                logger.info(f"doubao tts Time to first chunk: {end-start}s")
                                first = False
                            sequence_number = int.from_bytes(payload[:4], "big", signed=True)
                            payload_size = int.from_bytes(payload[4:8], "big", signed=False)
                            payload = payload[8:]
                            yield payload
                        if sequence_number < 0:
                            break
                    else:
                        break
        except Exception as e:
            logger.exception('doubao')
        # 旧版 HTTP 返回解析逻辑已废弃，保留 WebSocket 流式路径即可。

    def txt_to_audio(self, msg:tuple[str, dict]):
        text, textevent = msg
        asyncio.new_event_loop().run_until_complete(
            self.stream_tts(
                self.doubao_voice(text),
                msg
            )
        )

    async def stream_tts(self, audio_stream, msg:tuple[str, dict]):
        text, textevent = msg
        first = True
        last_stream = np.array([],dtype=np.float32)
        async for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767
                stream = np.concatenate((last_stream,stream))
                # stream = resampy.resample(x=stream, sr_orig=24000, sr_new=self.sample_rate)
                # byte_stream=BytesIO(buffer)
                # stream = self.__create_bytes_stream(byte_stream)
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    eventpoint = {}
                    if first:
                        eventpoint={'status':'start','text':text}
                        eventpoint.update(**textevent) 
                        first = False
                    self.parent.put_audio_frame(stream[idx:idx + self.chunk], eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
                last_stream = stream[idx:] # 保存不足一帧的尾部，拼接到下一块
        eventpoint={'status':'end','text':text}
        eventpoint.update(**textevent) 
        self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)

###########################################################################################
class IndexTTS2(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        # IndexTTS2 配置参数
        self.server_url = opt.TTS_SERVER  # Gradio服务器地址，如 "http://127.0.0.1:7860/"
        self.ref_audio_path = opt.REF_FILE  # 参考音频文件路径
        self.max_tokens = getattr(opt, 'MAX_TOKENS', 120)  # 最大token数
        
        # 初始化Gradio客户端
        try:
            from gradio_client import Client, handle_file
            self.client = Client(self.server_url)
            self.handle_file = handle_file
            logger.info(f"IndexTTS2 Gradio客户端初始化成功: {self.server_url}")
        except ImportError:
            logger.error("IndexTTS2 需要安装 gradio_client: pip install gradio_client")
            raise
        except Exception as e:
            logger.error(f"IndexTTS2 Gradio客户端初始化失败: {e}")
            raise
        
    def txt_to_audio(self, msg):
        text, textevent = msg
        try:
            # 先进行文本分割
            segments = self.split_text(text)
            if not segments:
                logger.error("IndexTTS2 文本分割失败")
                return
            
            logger.info(f"IndexTTS2 文本分割为 {len(segments)} 个片段")
            
            # 循环生成每个片段的音频
            for i, segment_text in enumerate(segments):
                if self.state != State.RUNNING:
                    break
                    
                logger.info(f"IndexTTS2 正在生成第 {i+1}/{len(segments)} 段音频...")
                audio_file = self.indextts2_generate(segment_text)
                
                if audio_file:
                    # 为每个片段创建事件信息
                    segment_msg = (segment_text, textevent)
                    self.file_to_stream(audio_file, segment_msg, is_first=(i==0), is_last=(i==len(segments)-1))
                else:
                    logger.error(f"IndexTTS2 第 {i+1} 段音频生成失败")
                    
        except Exception as e:
            logger.exception(f"IndexTTS2 txt_to_audio 错误: {e}")

    def split_text(self, text):
        """使用 IndexTTS2 API 分割文本"""
        try:
            logger.info(f"IndexTTS2 开始分割文本，长度: {len(text)}")
            
            # 调用文本分割 API
            result = self.client.predict(
                text=text,
                max_text_tokens_per_segment=self.max_tokens,
                api_name="/on_input_text_change"
            )
            
            # 解析分割结果
            if 'value' in result and 'data' in result['value']:
                data = result['value']['data']
                logger.info(f"IndexTTS2 共分割为 {len(data)} 个片段")
                
                segments = []
                for i, item in enumerate(data):
                    序号 = item[0] + 1
                    分句内容 = item[1]
                    token数 = item[2]
                    logger.info(f"片段 {序号}: {len(分句内容)} 字符, {token数} tokens")
                    segments.append(分句内容)
                
                return segments
            else:
                logger.error(f"IndexTTS2 文本分割结果格式异常: {result}")
                return [text]  # 如果分割失败，返回原文本
                
        except Exception as e:
            logger.exception(f"IndexTTS2 文本分割失败: {e}")
            return [text]  # 如果分割失败，返回原文本

    def indextts2_generate(self, text):
        """调用 IndexTTS2 Gradio API 生成语音"""
        start = time.perf_counter()
        
        try:
            # 调用 gen_single API
            result = self.client.predict(
                emo_control_method="Same as the voice reference",
                prompt=self.handle_file(self.ref_audio_path),
                text=text,
                emo_ref_path=self.handle_file(self.ref_audio_path),
                emo_weight=0.8,
                vec1=0.5,
                vec2=0,
                vec3=0,
                vec4=0,
                vec5=0,
                vec6=0,
                vec7=0,
                vec8=0,
                emo_text="",
                emo_random=False,
                max_text_tokens_per_segment=self.max_tokens,
                param_16=True,
                param_17=0.8,
                param_18=30,
                param_19=0.8,
                param_20=0,
                param_21=3,
                param_22=10,
                param_23=1500,
                api_name="/gen_single"
            )
            
            end = time.perf_counter()
            logger.info(f"IndexTTS2 片段生成完成，耗时: {end-start:.2f}s")
            
            # 返回生成的音频文件路径
            if 'value' in result:
                audio_file = result['value']
                return audio_file
            else:
                logger.error(f"IndexTTS2 结果格式异常: {result}")
                return None
                
        except Exception as e:
            logger.exception(f"IndexTTS2 API调用失败: {e}")
            return None

    def file_to_stream(self, audio_file, msg, is_first=False, is_last=False):
        """将音频文件转换为音频流"""
        text, textevent = msg
        
        try:
            # 读取音频文件
            stream, sample_rate = sf.read(audio_file)
            logger.info(f'IndexTTS2 音频文件 {sample_rate}Hz: {stream.shape}')
            
            # 转换为float32
            stream = stream.astype(np.float32)
            
            # 如果是多声道，只取第一个声道
            if stream.ndim > 1:
                logger.info(f'IndexTTS2 音频有 {stream.shape[1]} 个声道，只使用第一个')
                stream = stream[:, 0]
            
            # 重采样到目标采样率
            if sample_rate != self.sample_rate and stream.shape[0] > 0:
                logger.info(f'IndexTTS2 重采样: {sample_rate}Hz -> {self.sample_rate}Hz')
                stream = resampy.resample(x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)
            
            # 分块发送音频流
            streamlen = stream.shape[0]
            idx = 0
            first_chunk = True
            
            while streamlen >= self.chunk and self.state == State.RUNNING:
                eventpoint = None
                
                # 只在第一个片段的第一个chunk发送start事件
                if is_first and first_chunk:
                    eventpoint = {'status': 'start', 'text': text, 'msgevent': textevent}
                    first_chunk = False
                
                self.parent.put_audio_frame(stream[idx:idx + self.chunk], eventpoint)
                idx += self.chunk
                streamlen -= self.chunk
            
            # 只在最后一个片段发送end事件
            if is_last:
                eventpoint = {'status': 'end', 'text': text, 'msgevent': textevent}
                self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)
            
            # 清理临时文件
            try:
                if os.path.exists(audio_file):
                    os.remove(audio_file)
                    logger.info(f"IndexTTS2 已删除临时文件: {audio_file}")
            except Exception as e:
                logger.warning(f"IndexTTS2 删除临时文件失败: {e}")
                
        except Exception as e:
            logger.exception(f"IndexTTS2 音频流处理失败: {e}")

###########################################################################################
class XTTS(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt,parent)
        self.speaker = self.get_speaker(opt.REF_FILE, opt.TTS_SERVER)

    def txt_to_audio(self,msg:tuple[str, dict]):
        text,textevent = msg  
        self.stream_tts(
            self.xtts(
                text,
                self.speaker,
                "zh-cn", # 语种标识
                self.opt.TTS_SERVER, # XTTS 服务地址
                "20" # 流式分块大小参数
            ),
            msg
        )

    def get_speaker(self,ref_audio,server_url):
        files = {"wav_file": ("reference.wav", open(ref_audio, "rb"))}
        response = requests.post(f"{server_url}/clone_speaker", files=files)
        return response.json()

    def xtts(self,text, speaker, language, server_url, stream_chunk_size) -> Iterator[bytes]:
        start = time.perf_counter()
        speaker["text"] = text
        speaker["language"] = language
        speaker["stream_chunk_size"] = stream_chunk_size  # 值更小可降首包延迟，但可能影响音质
        try:
            res = requests.post(
                f"{server_url}/tts_stream",
                json=speaker,
                stream=True,
            )
            end = time.perf_counter()
            logger.info(f"xtts Time to make POST: {end-start}s")

            if res.status_code != 200:
                print("Error:", res.text)
                return

            first = True
        
            for chunk in res.iter_content(chunk_size=None): # 按服务端原始块大小持续拉流
                if first:
                    end = time.perf_counter()
                    logger.info(f"xtts Time to first chunk: {end-start}s")
                    first = False
                if chunk:
                    yield chunk
        except Exception as e:
            print(e)
    
    def stream_tts(self,audio_stream,msg:tuple[str, dict]):
        text,textevent = msg
        first = True
        last_stream = np.array([],dtype=np.float32)
        for chunk in audio_stream:
            if chunk is not None and len(chunk)>0:          
                stream = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767
                stream = resampy.resample(x=stream, sr_orig=24000, sr_new=self.sample_rate)
                stream = np.concatenate((last_stream,stream))
                # byte_stream=BytesIO(buffer)
                # stream = self.__create_bytes_stream(byte_stream)
                streamlen = stream.shape[0]
                idx=0
                while streamlen >= self.chunk:
                    eventpoint={}
                    if first:
                        eventpoint={'status':'start','text':text}
                        eventpoint.update(**textevent) 
                        first = False
                    self.parent.put_audio_frame(stream[idx:idx+self.chunk],eventpoint)
                    streamlen -= self.chunk
                    idx += self.chunk
                last_stream = stream[idx:] # 保存不足一帧的尾部，拼接到下一个块
        eventpoint={'status':'end','text':text}
        eventpoint.update(**textevent) 
        self.parent.put_audio_frame(np.zeros(self.chunk,np.float32),eventpoint)  

###########################################################################################
class AzureTTS(BaseTTS):
    CHUNK_SIZE = 640  # 16kHz、20ms、16bit 单声道 PCM 字节数
    def __init__(self, opt, parent):
        super().__init__(opt,parent)
        self.audio_buffer = b''
        voicename = self.opt.REF_FILE   # 比如"zh-CN-XiaoxiaoMultilingualNeural"
        speech_key = os.getenv("AZURE_SPEECH_KEY")
        tts_region = os.getenv("AZURE_TTS_REGION")
        speech_endpoint = f"wss://{tts_region}.tts.speech.microsoft.com/cognitiveservices/websocket/v2"
        speech_config = speechsdk.SpeechConfig(subscription=speech_key,endpoint=speech_endpoint)
        speech_config.speech_synthesis_voice_name = voicename
        speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Raw16Khz16BitMonoPcm)
        
        # 获取内存中流形式的结果
        self.speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
        self.speech_synthesizer.synthesizing.connect(self._on_synthesizing)
        
    def txt_to_audio(self,msg:tuple[str, dict]):
        msg_text: str = msg[0]
        result=self.speech_synthesizer.speak_text(msg_text)

        
        # 延迟指标
        fb_latency = int(result.properties.get_property(
            speechsdk.PropertyId.SpeechServiceResponse_SynthesisFirstByteLatencyMs
        ))
        fin_latency = int(result.properties.get_property(
            speechsdk.PropertyId.SpeechServiceResponse_SynthesisFinishLatencyMs
        ))
        logger.info(f"azure音频生成相关：首字节延迟: {fb_latency} ms, 完成延迟: {fin_latency} ms, result_id: {result.result_id}")



    # === 回调 ===
    def _on_synthesizing(self, evt: speechsdk.SpeechSynthesisEventArgs):
        if evt.result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.info("SynthesizingAudioCompleted")
        elif evt.result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = evt.result.cancellation_details
            logger.info(f"Speech synthesis canceled: {cancellation_details.reason}")
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                if cancellation_details.error_details:
                    logger.info(f"Error details: {cancellation_details.error_details}")        
        if self.state != State.RUNNING:
            self.audio_buffer = b''
            return

        # evt.result.audio_data 是刚到的一小段原始 PCM
        self.audio_buffer += evt.result.audio_data
        while len(self.audio_buffer) >= self.CHUNK_SIZE:
            chunk = self.audio_buffer[:self.CHUNK_SIZE]
            self.audio_buffer = self.audio_buffer[self.CHUNK_SIZE:]

            frame = (np.frombuffer(chunk, dtype=np.int16)
                       .astype(np.float32) / 32767.0)
            self.parent.put_audio_frame(frame)

###########################################################################################
class Qwen3TTS(BaseTTS):
    """DashScope Qwen-TTS 流式适配器。

    从流式响应中提取 base64 PCM 音频块，完成 24kHz 到 16kHz 的重采样，
    再按 20ms 固定帧长投递到 LiveTalking 的统一音频流水线。
    """

    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self.api_key = opt.QWEN_API_KEY or os.getenv("DASHSCOPE_API_KEY", "")
        self.model = getattr(opt, "QWEN_MODEL", "qwen3-tts-flash")
        self.base_url = getattr(opt, "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")
        self.language_type = getattr(opt, "QWEN_LANGUAGE_TYPE", "Chinese")
        self.instructions = getattr(opt, "QWEN_INSTRUCTIONS", "")
        self.optimize_instructions = bool(getattr(opt, "QWEN_OPTIMIZE_INSTRUCTIONS", False))

        if opt.REF_FILE == "zh-CN-YunxiaNeural":
            self.voice = "Cherry"
        else:
            self.voice = opt.REF_FILE

        self.dashscope = None
        try:
            import dashscope

            dashscope.base_http_api_url = self.base_url
            self.dashscope = dashscope
        except Exception:
            logger.exception("qwen3tts import dashscope failed")

    def txt_to_audio(self, msg:tuple[str, dict]):
        text, _ = msg
        if not self.dashscope:
            logger.error("qwen3tts unavailable: dashscope is not installed")
            return
        if not self.api_key:
            logger.error("qwen3tts unavailable: missing api key, set --QWEN_API_KEY or DASHSCOPE_API_KEY")
            return
        if not text:
            return
        self.stream_tts(self.qwen_tts(text), msg)

    def _safe_map_get(self, container, key, default=None):
        if container is None:
            return default
        if isinstance(container, dict):
            return container.get(key, default)
        try:
            return container[key]
        except Exception:
            return default

    def _extract_audio_b64(self, event):
        # DashScopeResponse 重载了 __getattr__，这里统一用映射访问以避免误判。
        output = self._safe_map_get(event, "output", {})
        audio = self._safe_map_get(output, "audio", {})
        chunk_b64 = self._safe_map_get(audio, "data", "")
        return chunk_b64 if isinstance(chunk_b64, str) else ""

    def qwen_tts(self, text) -> Iterator[bytes]:
        start = time.perf_counter()
        payload = {
            "model": self.model,
            "api_key": self.api_key,
            "text": text,
            "voice": self.voice,
            "language_type": self.language_type,
            "stream": True,
        }
        if self.instructions:
            payload["instructions"] = self.instructions
            payload["optimize_instructions"] = self.optimize_instructions

        first = True
        try:
            response_stream = self.dashscope.MultiModalConversation.call(**payload)
            for event in response_stream:
                if self.state != State.RUNNING:
                    break
                chunk_b64 = self._extract_audio_b64(event)
                if not chunk_b64:
                    continue
                try:
                    chunk = base64.b64decode(chunk_b64)
                except Exception:
                    continue
                if not chunk:
                    continue
                if first:
                    logger.info("qwen3tts Time to first chunk: %.4fs", time.perf_counter() - start)
                    first = False
                yield chunk
        except Exception:
            logger.exception("qwen3tts stream failed")

    def stream_tts(self, audio_stream, msg:tuple[str, dict]):
        text, textevent = msg
        first = True
        last_stream = np.array([], dtype=np.float32)

        for chunk in audio_stream:
            if chunk is None or len(chunk) == 0:
                continue

            # Qwen-TTS 输出是 24kHz 单声道 PCM，需要先重采样再做 20ms 切片。
            stream = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767.0
            stream = resampy.resample(x=stream, sr_orig=24000, sr_new=self.sample_rate)
            stream = np.concatenate((last_stream, stream))

            streamlen = stream.shape[0]
            idx = 0
            while streamlen >= self.chunk and self.state == State.RUNNING:
                eventpoint = {}
                if first:
                    eventpoint = {'status':'start','text':text}
                    eventpoint.update(**textevent)
                    first = False
                self.parent.put_audio_frame(stream[idx:idx+self.chunk], eventpoint)
                streamlen -= self.chunk
                idx += self.chunk
            last_stream = stream[idx:]

        eventpoint = {'status':'end','text':text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)