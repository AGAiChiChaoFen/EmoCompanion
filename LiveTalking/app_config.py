###############################################################################
#  项目：EmoCompanion（基于 LiveTalking）
#  文件：app_config.py
#  说明：LiveTalking 服务启动参数定义。
#  许可证：Apache License 2.0
###############################################################################

from __future__ import annotations

import argparse


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    
    # 音频帧率（默认 50fps，即 20ms 一帧）。
    parser.add_argument('--fps', type=int, default=50, help="audio fps,must be 50")
    # ASR/特征处理滑窗长度：左/中/右（单位均为 20ms）。
    parser.add_argument('-l', type=int, default=10)
    parser.add_argument('-m', type=int, default=8)
    parser.add_argument('-r', type=int, default=10)

    parser.add_argument('--batch_size', type=int, default=16, help="infer batch")

    parser.add_argument('--customvideo_config', type=str, default='', help="custom action json")

    parser.add_argument('--tts', type=str, default='edgetts', help="tts service type") #xtts gpt-sovits cosyvoice fishtts tencent doubao indextts2 azuretts qwen3tts
    parser.add_argument('--REF_FILE', type=str, default="zh-CN-YunxiaNeural",help="参考文件名或语音模型ID，默认值为 edgetts的语音模型ID zh-CN-YunxiaNeural, 若--tts指定为azuretts, 可以使用Azure语音模型ID, 如zh-CN-XiaoxiaoMultilingualNeural")
    parser.add_argument('--REF_TEXT', type=str, default=None)
    parser.add_argument('--TTS_SERVER', type=str, default='http://127.0.0.1:9880') # http://localhost:9000
    parser.add_argument('--QWEN_API_KEY', type=str, default='', help='qwen3tts api key, empty means read DASHSCOPE_API_KEY from env')
    parser.add_argument('--QWEN_MODEL', type=str, default='qwen3-tts-flash', help='qwen3tts model id')
    parser.add_argument('--QWEN_BASE_URL', type=str, default='https://dashscope.aliyuncs.com/api/v1', help='dashscope base url')
    parser.add_argument('--QWEN_LANGUAGE_TYPE', type=str, default='Chinese', help='Auto/Chinese/English/... for qwen3tts')
    parser.add_argument('--QWEN_INSTRUCTIONS', type=str, default='', help='optional qwen3tts instructions')
    parser.add_argument('--QWEN_OPTIMIZE_INSTRUCTIONS', action='store_true', help='optimize qwen3tts instructions')
    parser.add_argument('--asr_backend', type=str, default='auto', choices=['auto', 'funasr', 'custom'], help='ASR backend for /asr route')
    parser.add_argument('--ASR_CUSTOM_HANDLER', type=str, default='', help='custom ASR handler module:function')
    parser.add_argument('--FUNASR_API_KEY', type=str, default='', help='funasr api key; empty means fallback to QWEN_API_KEY or DASHSCOPE_API_KEY')
    parser.add_argument('--FUNASR_MODEL', type=str, default='fun-asr-realtime', help='funasr model id')
    parser.add_argument('--FUNASR_BASE_URL', type=str, default='https://dashscope.aliyuncs.com/api/v1', help='funasr base url')
    parser.add_argument('--FUNASR_SAMPLE_RATE', type=int, default=16000, help='funasr input sample rate')
    parser.add_argument('--FUNASR_LANGUAGE_HINT', type=str, default='zh', help='funasr language hint, e.g. zh/en/ja')
    parser.add_argument('--FUNASR_MAX_SENTENCE_SILENCE', type=int, default=1000, help='funasr max sentence silence in ms')
    parser.add_argument('--FUNASR_SEMANTIC_PUNCTUATION', action='store_true', help='enable semantic punctuation for funasr')
    parser.add_argument('--WEBRTC_FINAL_ASR_BACKEND', type=str, default='same', choices=['same', 'auto', 'funasr', 'custom', 'http'], help='ASR backend for webrtc final recognition stage')
    parser.add_argument('--WEBRTC_FINAL_ASR_CUSTOM_HANDLER', type=str, default='', help='custom ASR handler for webrtc final stage when backend=custom')
    parser.add_argument('--WEBRTC_FINAL_ASR_HTTP_URL', type=str, default='', help='http endpoint for webrtc final stage when backend=http')
    parser.add_argument('--WEBRTC_FINAL_ASR_HTTP_AUTH_TOKEN', type=str, default='', help='bearer token for webrtc final http asr')
    parser.add_argument('--WEBRTC_FINAL_ASR_HTTP_TIMEOUT_S', type=float, default=15.0, help='timeout seconds for webrtc final http asr request')
    parser.add_argument('--WEBRTC_FINAL_ASR_STRICT_FAILURE', action='store_true', help='return error directly when final asr fails')
    parser.add_argument('--WEBRTC_FINAL_ASR_CLOUD_VERIFY_ENABLE', type=int, default=0, choices=[0, 1], help='enable cloud verify for webrtc final transcript suppression')
    parser.add_argument('--WEBRTC_FINAL_ASR_CLOUD_VERIFY_BACKEND', type=str, default='funasr', choices=['same', 'auto', 'funasr', 'custom', 'http'], help='cloud verify backend for webrtc final transcript')
    parser.add_argument('--WEBRTC_FINAL_ASR_CLOUD_VERIFY_CUSTOM_HANDLER', type=str, default='', help='custom cloud verify ASR handler when cloud verify backend=custom')
    parser.add_argument('--WEBRTC_FINAL_ASR_CLOUD_VERIFY_HTTP_URL', type=str, default='', help='http endpoint for cloud verify ASR when backend=http')
    parser.add_argument('--WEBRTC_FINAL_ASR_CLOUD_VERIFY_HTTP_AUTH_TOKEN', type=str, default='', help='bearer token for cloud verify http asr')
    parser.add_argument('--WEBRTC_FINAL_ASR_CLOUD_VERIFY_HTTP_TIMEOUT_S', type=float, default=12.0, help='timeout seconds for cloud verify http asr request')
    parser.add_argument('--WEBRTC_FINAL_ASR_CLOUD_VERIFY_SIMILARITY', type=float, default=0.56, help='minimum similarity threshold to treat local/cloud final transcript as consistent')
    parser.add_argument('--WEBRTC_FINAL_ASR_CLOUD_VERIFY_SHORT_TEXT_CHARS', type=int, default=8, help='reject local transcript on cloud mismatch when normalized text length <= this threshold')
    parser.add_argument('--WEBRTC_FINAL_ASR_CLOUD_VERIFY_MIN_CLOUD_CHARS', type=int, default=2, help='minimum normalized cloud transcript length to be treated as valid verify evidence')
    parser.add_argument('--WEBRTC_FINAL_ASR_CLOUD_VERIFY_REPLACE_WITH_CLOUD', type=int, default=1, choices=[0, 1], help='replace local transcript with cloud transcript when verify decision allows')
    parser.add_argument('--WEBRTC_ASR_SPEECH_LEVEL', type=float, default=220.0, help='frame avg level threshold regarded as speech activity')
    parser.add_argument('--WEBRTC_ASR_MIN_PARTIAL_SPEECH_FRAMES', type=int, default=4, help='minimum active-speech frames required for partial ASR')
    parser.add_argument('--WEBRTC_ASR_MIN_FINAL_SPEECH_FRAMES', type=int, default=6, help='minimum active-speech frames required for final ASR')
    parser.add_argument('--WEBRTC_ASR_MIN_FINAL_PEAK_LEVEL', type=float, default=260.0, help='minimum peak level required for final ASR')
    parser.add_argument('--WEBRTC_ASR_DROP_WHILE_AVATAR_SPEAKING', type=int, default=1, choices=[0, 1], help='drop uplink audio frames while avatar is speaking to reduce echo')
    parser.add_argument('--WEBRTC_ASR_ECHO_GUARD_MS', type=int, default=4500, help='recent assistant text guard window(ms) for echo transcript suppression')
    parser.add_argument('--WEBRTC_ASR_ECHO_SIMILARITY', type=float, default=0.88, help='text similarity threshold for echo transcript suppression')
    # 🆕 DeepFace 人脸情绪识别相关参数
    parser.add_argument('--DEEPFACE_ENABLE', action='store_true', help='enable DeepFace face emotion recognition')
    parser.add_argument('--DEEPFACE_API_URL', type=str, default='http://127.0.0.1:9020', help='DeepFace API service URL')
    parser.add_argument('--DEEPFACE_TIMEOUT_S', type=float, default=0.0, help='DeepFace API call timeout in seconds; <= 0 disables timeout')
    parser.add_argument('--DEEPFACE_ANALYZE_EVERY_N', type=int, default=3, help='analyze face emotion every N saved video frames')
    parser.add_argument('--DEEPFACE_CACHE_MAX_AGE_MS', type=int, default=10000, help='face emotion cache max age in milliseconds')
    
    parser.add_argument('--CHAT_RECORD_ENABLE', action='store_true', help='enable chat session record archive')
    parser.add_argument('--CHAT_RECORD_DIR', type=str, default='debug/chat_records', help='directory for saved chat session records')
    parser.add_argument('--CHAT_RECORD_POLICY', type=str, default='auto', choices=['auto', 'full', 'text-only', 'off'], help='chat record archive policy')
    parser.add_argument('--llm_backend', type=str, default='custom', choices=['custom'], help='LLM backend for chat stream; only EmoLLM custom backend is supported')
    parser.add_argument('--LLM_CUSTOM_HANDLER', type=str, default='custom_api_handlers:emollm_response', help='custom EmoLLM handler module:function')
    parser.add_argument('--LIGHTRAG_ENABLE', type=int, default=1, choices=[0, 1], help='enable LightRAG knowledge retrieval before LLM calls')
    parser.add_argument('--LIGHTRAG_BASE_URL', type=str, default='http://101.200.57.208:9622', help='LightRAG server base URL')
    parser.add_argument('--LIGHTRAG_USERNAME', type=str, default='admin', help='LightRAG username')
    parser.add_argument('--LIGHTRAG_PASSWORD', type=str, default='admin', help='LightRAG password')
    parser.add_argument('--LIGHTRAG_TIMEOUT_S', type=float, default=8.0, help='LightRAG request timeout seconds')
    parser.add_argument('--LIGHTRAG_QUERY_MODE', type=str, default='mix', choices=['local', 'global', 'hybrid', 'naive', 'mix'], help='LightRAG query mode')
    parser.add_argument('--LIGHTRAG_TOP_K', type=int, default=8, help='LightRAG top_k for entity/relation retrieval')
    parser.add_argument('--LIGHTRAG_CHUNK_TOP_K', type=int, default=6, help='LightRAG chunk_top_k for vector retrieval')
    parser.add_argument('--LIGHTRAG_MAX_TOTAL_TOKENS', type=int, default=2200, help='LightRAG context token budget')
    # parser.add_argument('--CHARACTER', type=str, default='test')
    # parser.add_argument('--EMOTION', type=str, default='default')

    parser.add_argument('--model', type=str, default='ditto', choices=['ditto'], help='only ditto is supported')
    parser.add_argument('--ditto_root', type=str, default='../ditto-talkinghead', help='ditto-talkinghead project root')
    parser.add_argument('--ditto_cfg_pkl', type=str, default='', help='ditto cfg pkl path')
    parser.add_argument('--ditto_data_root', type=str, default='', help='ditto trt data root path')
    parser.add_argument('--ditto_source_path', type=str, default='', help='ditto source avatar image/video path')
    parser.add_argument('--ditto_chunksize', type=int, nargs=3, default=[3, 5, 2], help='ditto run_chunk chunksize, e.g. 3 5 2')

    # 兼容历史命令行参数：保留 --transport，但仅允许 webrtc。
    parser.add_argument('--transport', type=str, default='webrtc', choices=['webrtc'], help='only webrtc is supported')

    parser.add_argument('--turn_url', type=str, default='', help='turn server url, comma-separated supported')
    parser.add_argument('--turn_host', type=str, default='', help='turn server host, used when turn_url is empty')
    parser.add_argument('--turn_port', type=int, default=3478, help='turn server port')
    parser.add_argument('--turn_tls_port', type=int, default=5349, help='turn server tls port')
    parser.add_argument('--turn_enable_udp', type=int, default=1, choices=[0, 1], help='enable turn over udp when turn_url is empty')
    parser.add_argument('--turn_enable_tcp', type=int, default=1, choices=[0, 1], help='enable turn over tcp when turn_url is empty')
    parser.add_argument('--turn_enable_tls', type=int, default=0, choices=[0, 1], help='enable turns over tcp when turn_url is empty')
    parser.add_argument('--ice_transport_policy', type=str, default='relay', choices=['relay', 'all'], help='frontend RTCPeerConnection iceTransportPolicy')
    parser.add_argument('--prefer_h264', type=int, default=0, choices=[0, 1], help='prefer H264 over VP8 for smoother playback on some browsers')
    parser.add_argument('--turn_username', type=str, default='', help='turn username')
    parser.add_argument('--turn_password', type=str, default='', help='turn password')

    parser.add_argument('--listenport', type=int, default=8010, help="web listen port")

    return parser
