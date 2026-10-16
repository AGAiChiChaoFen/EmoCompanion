<template>
  <div class="multimodal-analysis">
    <div class="content-layout">
      <!-- 左侧：输入采集区 -->
      <div class="input-section">
        <div class="capture-card video-card">
          <h3 class="card-title">
            <i class="bi bi-camera-video"></i>
            视频采集
            <span class="test-badge" v-if="uploadedVideoFile">上传文件</span>
          </h3>
          <div class="video-preview">
            <div
              v-show="isCameraActive || uploadedVideoFile"
              class="video-preview-blur-layer"
              aria-hidden="true"
            >
              <video
                ref="videoBackdropElement"
                class="video-preview-backdrop"
                :autoplay="isCameraActive && !uploadedVideoFile"
                muted
                playsinline
                preload="metadata"
                :loop="false"
                :class="{ 'is-live-feed': isCameraActive && !uploadedVideoFile }"
              ></video>
            </div>
            <video
              v-show="isCameraActive || uploadedVideoFile"
              ref="videoElement"
              class="video-preview-main"
              :autoplay="isCameraActive && !uploadedVideoFile"
              muted
              playsinline
              preload="metadata"
              :loop="false"
              :class="{ 'is-live-feed': isCameraActive && !uploadedVideoFile }"
            ></video>
            <UploadMediaControls
              v-if="uploadedVideoFile && uploadedVideoPreviewUrl"
              class="video-inline-controls"
              :media-refs="[videoElement, videoBackdropElement]"
              :source="uploadedVideoPreviewUrl"
              :file-name="uploadedVideoFile.name"
              kind="video"
              :compact="true"
              :default-collapsed="true"
            />
            <div v-if="!isCameraActive && !uploadedVideoFile" class="preview-placeholder">
              <i class="bi bi-camera-video-off"></i>
              <p>摄像头未开启</p>
            </div>
          </div>
          <div class="button-group">
            <button
              class="btn-toggle"
              :class="{ active: isCameraActive }"
              @click="toggleCamera"
              :disabled="!!uploadedVideoFile"
            >
              <i :class="['bi', isCameraActive ? 'bi-camera-video-fill' : 'bi-camera-video']"></i>
              {{ isCameraActive ? '关闭摄像头' : '开启摄像头' }}
            </button>
            <button
              class="btn-upload"
              @click="triggerVideoUpload"
              :disabled="isCameraActive"
            >
              <i class="bi bi-upload"></i>
              {{ uploadedVideoFile ? '更换视频' : '上传视频' }}
            </button>
            <button
              v-if="uploadedVideoFile"
              class="btn-clear"
              @click="clearUploadedVideo"
            >
              <i class="bi bi-x-circle"></i>
            </button>
          </div>
          <input
            ref="videoFileInput"
            type="file"
            accept="video/*"
            style="display: none"
            @change="handleVideoUpload"
          />
        </div>

        <div class="capture-card audio-card">
          <h3 class="card-title">
            <i class="bi bi-mic"></i>
            音频采集
            <span class="test-badge" v-if="uploadedAudioFile">上传文件</span>
          </h3>
          <div class="audio-visualizer">
            <div class="waveform">
              <div
                v-for="i in 20"
                :key="i"
                class="wave-bar"
                :class="{ active: isAudioActive || uploadedAudioFile }"
                :style="{
                  animationDelay: `${i * 0.05}s`,
                  height: `${audioLevels[i - 1]}px`
                }"
              ></div>
            </div>
          </div>
          <div class="button-group">
            <button
              class="btn-toggle"
              :class="{ active: isAudioActive, recording: isRecording }"
              @mousedown="startRecording"
              @mouseup="stopRecording"
              @mouseleave="stopRecording"
              @touchstart.prevent="startRecording"
              @touchend="stopRecording"
              @touchcancel="stopRecording"
              :disabled="!!uploadedAudioFile"
            >
              <i :class="['bi', isRecording ? 'bi-mic-fill' : 'bi-mic']"></i>
              {{ isRecording ? '录音中...' : '按住说话' }}
            </button>
            <button
              class="btn-upload"
              @click="triggerAudioUpload"
              :disabled="isRecording"
            >
              <i class="bi bi-upload"></i>
              {{ uploadedAudioFile ? '更换音频' : '上传音频' }}
            </button>
            <button
              v-if="uploadedAudioFile"
              class="btn-clear"
              @click="clearUploadedAudio"
            >
              <i class="bi bi-x-circle"></i>
            </button>
          </div>
          <input
            ref="audioFileInput"
            type="file"
            accept="audio/*"
            style="display: none"
            @change="handleAudioUpload"
          />
          <audio
            ref="uploadedAudioElement"
            class="hidden-upload-audio"
            preload="metadata"
          ></audio>
          <UploadMediaControls
            v-if="uploadedAudioFile && uploadedAudioPreviewUrl"
            :media-refs="[uploadedAudioElement]"
            :source="uploadedAudioPreviewUrl"
            :file-name="uploadedAudioFile.name"
            kind="audio"
          />
        </div>

        <button
          class="btn-analyze"
          :disabled="!canAnalyze || isAnalyzing"
          @click="performAnalysis"
        >
          <i :class="['bi', isAnalyzing ? 'bi-hourglass-split' : 'bi-play-circle-fill']"></i>
          {{ isAnalyzing ? '分析中...' : '开始分析' }}
        </button>
      </div>

      <!-- 右侧：分析结果区 -->
      <div class="result-section">
        <div class="result-card">
          <h3 class="card-title">
            <i class="bi bi-graph-up"></i>
            心理状态分析报告
          </h3>

          <div v-if="!analysisResult && !isAnalyzing" class="empty-state">
            <i class="bi bi-clipboard-data"></i>
            <p>上传视频与音频素材后，点击“开始分析”</p>
          </div>

          <div v-if="isAnalyzing" class="analyzing-state">
            <div class="spinner"></div>
            <p>正在进行多模态心理状态分析...</p>
            <div class="progress-container">
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: `${analysisProgress}%` }"></div>
              </div>
              <p class="progress-text">{{ analysisStep }}</p>
            </div>
          </div>

          <div v-if="analysisResult && !isAnalyzing" class="result-content">
            <!-- 结论概览（仅日间温柔疗愈视图展示） -->
            <div v-if="isDayTheme" class="result-overview">
              <div class="overview-emotion">
                <span class="overview-emoji">{{ dominantEmoji }}</span>
                <div class="overview-emotion-text">
                  <span class="overview-kicker">当前主导情绪</span>
                  <strong>{{ dominantEmotionText }}</strong>
                </div>
              </div>
              <div class="overview-signals">
                <div
                  v-for="signal in emotionSignalItems"
                  :key="signal.label"
                  class="overview-signal"
                  :class="{ muted: signal.value === '未检测' }"
                >
                  <span class="overview-signal-label">{{ signal.label }}</span>
                  <strong>{{ signal.value }}</strong>
                </div>
                <div class="overview-signal consistency">
                  <span class="overview-signal-label">一致性</span>
                  <strong>{{ consistencyText }}</strong>
                </div>
              </div>
            </div>

            <div v-if="analysisResult.audioTranscript" class="result-block">
              <h4 class="block-title">
                <i class="bi bi-soundwave"></i>
                语音转写
              </h4>
              <div class="text-content-display">
                {{ analysisResult.audioTranscript }}
              </div>
            </div>

            <!-- 文本内容展示 -->
            <div v-if="analysisResult.textContent" class="result-block">
              <h4 class="block-title">
                <i class="bi bi-chat-text"></i>
                文本内容
              </h4>
              <div class="text-content-display">
                {{ analysisResult.textContent }}
              </div>
            </div>

            <!-- 情绪识别结果 -->
            <div class="result-block">
              <h4 class="block-title">
                <i class="bi bi-emoji-smile"></i>
                情绪识别
              </h4>
              <div class="emotion-grid">
                <div class="emotion-item">
                  <span class="emotion-label">面部情绪</span>
                  <span class="emotion-value" :class="`emotion-${analysisResult.faceEmotion}`">
                    {{ analysisResult.faceEmotion || '未检测' }}
                  </span>
                </div>
                <div class="emotion-item">
                  <span class="emotion-label">语音情绪</span>
                  <span class="emotion-value" :class="`emotion-${analysisResult.audioEmotion}`">
                    {{ analysisResult.audioEmotion || '未检测' }}
                  </span>
                </div>
                <div class="emotion-item">
                  <span class="emotion-label">文本情绪</span>
                  <span class="emotion-value" :class="`emotion-${analysisResult.textEmotion}`">
                    {{ analysisResult.textEmotion || '未检测' }}
                  </span>
                </div>
              </div>
              <p
                v-if="analysisResult.faceAnalysisMessage && analysisResult.faceAnalysisStatus !== 'detected'"
                class="emotion-note"
              >
                <i class="bi bi-info-circle"></i>
                {{ analysisResult.faceAnalysisMessage }}
              </p>
            </div>

            <!-- 视频关键帧 -->
            <div v-if="analysisResult.videoFrames && analysisResult.videoFrames.length > 0" class="result-block">
              <h4 class="block-title">
                <i class="bi bi-film"></i>
                视频关键帧
              </h4>
              <div class="keyframes-grid">
                <div
                  v-for="(frame, index) in analysisResult.videoFrames"
                  :key="index"
                  class="keyframe-item"
                >
                  <div class="keyframe-image">
                    <img :src="frame.url" :alt="`关键帧 ${index + 1}`" />
                    <div class="keyframe-overlay">
                      <span class="keyframe-time">{{ frame.time }}</span>
                    </div>
                  </div>
                  <div class="keyframe-emotion">{{ frame.emotion }}</div>
                </div>
              </div>
            </div>

            <div class="result-block knowledge-bridge-block">
              <h4 class="block-title">
                <i class="bi bi-journal-medical"></i>
                知识库引用与情绪解析准备
              </h4>
              <div class="knowledge-bridge-grid">
                <div class="knowledge-bridge-panel">
                  <div class="bridge-panel-head">
                    <span class="bridge-panel-label">知识引用</span>
                    <span class="bridge-status">{{ lightragStatusText }}</span>
                  </div>
                  <div class="knowledge-source-list">
                    <div
                      v-for="(source, index) in displayedKnowledgeSources"
                      :key="`${formatReference(source, index)}-${index}`"
                      class="knowledge-source-chip"
                    >
                      <i class="bi bi-file-earmark-text"></i>
                      <span>{{ formatReference(source, index) }}</span>
                    </div>
                  </div>
                  <p class="bridge-footnote">
                    检索上下文 {{ lightragContextText }}，用于支撑后续心理状态评估与干预策略生成。
                  </p>
                </div>

                <div class="knowledge-bridge-panel emotion-bridge-panel">
                  <div class="bridge-panel-head">
                    <span class="bridge-panel-label">当前情绪解析</span>
                    <span class="bridge-status accent">{{ dominantEmotionText }}</span>
                  </div>
                  <div class="emotion-signal-row">
                    <span
                      v-for="signal in emotionSignalItems"
                      :key="signal.label"
                      class="emotion-signal-pill"
                    >
                      <strong>{{ signal.label }}</strong>
                      {{ signal.value }}
                    </span>
                  </div>
                  <p class="emotion-bridge-summary">
                    {{ emotionBridgeSummary }}
                  </p>
                </div>
              </div>
            </div>

            <!-- 分析时间 -->
            <div class="result-meta">
              <i class="bi bi-clock"></i>
              分析时间: {{ analysisResult.timestamp }}
            </div>

            <router-link class="assessment-entry" to="/assessment-intervention">
              <span>
                <small>下一步 · 知识增强决策</small>
                <strong>查看心理评估结果与干预建议</strong>
              </span>
              <i class="bi bi-arrow-right-circle-fill"></i>
            </router-link>

          </div>
        </div>
      </div>
    </div>

    <!-- 隐藏的sessionid输入框 -->
    <input type="hidden" id="sessionid" />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import UploadMediaControls from '../components/UploadMediaControls.vue';
import { useTheme } from '../composables/useTheme';
import { buildApiUrl } from '../utils/api';
import { personaUserName, useAnalysisResult } from '../composables/useAnalysisResult';

const { isDayTheme } = useTheme();

const videoElement = ref(null);
const videoBackdropElement = ref(null);
const isCameraActive = ref(false);
const isAudioActive = ref(false);
const isRecording = ref(false);
const hasAudioCapture = ref(false);
const isAnalyzing = ref(false);
const { analysisResult, setAnalysisResult } = useAnalysisResult();
const analysisProgress = ref(0);
const analysisStep = ref('');
const isConnected = ref(false);
const isConnecting = ref(false);
const sessionid = ref(0);
const audioLevels = ref(Array.from({ length: 20 }, () => 12));
const localVideoStream = ref(null);
const localAudioStream = ref(null);

// 上传分析相关
const videoFileInput = ref(null);
const audioFileInput = ref(null);
const uploadedVideoFile = ref(null);
const uploadedAudioFile = ref(null);
const uploadedVideoPreviewUrl = ref('');
const uploadedAudioPreviewUrl = ref('');
const uploadedAudioElement = ref(null);

// 轮询定时器
let pollTimer = null;
let latestFaceEmotion = '未检测';
let latestAudioEmotion = '';
let audioContext = null;
let audioAnalyser = null;
let audioSourceNode = null;
let audioAnimationFrame = 0;
let originalOnWebRTCConnected = null;
let originalOnWebRTCDisconnected = null;
let lastMediaSignature = 'v0-a0';
let isRecordPressActive = false;

const restoreMultimodalState = () => {
  if (analysisResult.value) {
    analysisProgress.value = 100;
    analysisStep.value = '已保存的模型分析';
  }
};

const canAnalyze = computed(() => {
  return (
    (isCameraActive.value && isConnected.value) ||
    uploadedVideoFile.value ||
    hasAudioCapture.value ||
    uploadedAudioFile.value
  );
});


const normalizeReference = (item) => {
  if (!item) return null;
  if (typeof item === 'string') {
    const value = item.trim();
    return value ? { reference_id: value, file_path: value } : null;
  }

  if (typeof item !== 'object') return null;

  const referenceId = String(
    item.reference_id || item.referenceId || item.id || item.title || item.name || ''
  ).trim();
  const filePath = String(
    item.file_path || item.filePath || item.path || item.source || item.document || ''
  ).trim();

  if (!referenceId && !filePath) return null;
  return {
    reference_id: referenceId,
    file_path: filePath,
  };
};

const lightragReferences = computed(() => {
  const references = analysisResult.value?.lightrag?.references;
  if (!Array.isArray(references)) return [];

  const seen = new Set();
  return references
    .map(normalizeReference)
    .filter(Boolean)
    .filter((item) => {
      const key = `${item.reference_id}|${item.file_path}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 6);
});

const displayedKnowledgeSources = computed(() =>
  lightragReferences.value
);

const lightragStatusText = computed(() => {
  const status = String(analysisResult.value?.lightrag?.status || '').toLowerCase();
  if (['success', 'ok', 'cached'].includes(status)) return '检索成功';
  if (['disabled', 'skipped', 'skipped_realtime'].includes(status)) return '知识库待启用';
  if (['error', 'failed', 'timeout'].includes(status)) return '检索失败';
  if (!status && lightragReferences.value.length) return '检索成功';
  return status === 'fallback' ? '降级检索' : '未取得引用';
});

const lightragContextText = computed(() => {
  const length = Number(analysisResult.value?.lightrag?.contextLength || 0);
  if (Number.isFinite(length) && length > 0) return `${length} 字符`;
  return lightragReferences.value.length ? '已命中引用' : '未取得上下文';
});

const formatReference = (reference, index) => {
  const rawName = String(reference?.file_path || reference?.reference_id || '').trim();
  if (!rawName) return `知识来源 ${index + 1}`;

  const normalized = rawName.replace(/\\/g, '/');
  const fileName = normalized.split('/').filter(Boolean).pop() || rawName;
  return fileName
    .replace(/\.(pdf|docx?|txt|md|json|csv)$/i, '')
    .replace(/^[-_\s]+|[-_\s]+$/g, '');
};

const cleanEmotionValue = (value) => {
  const text = String(value || '').trim();
  return text && text !== '未检测' ? text : '未检测';
};

const emotionSignalItems = computed(() => {
  const result = analysisResult.value || {};
  return [
    { label: '面部', value: cleanEmotionValue(result.faceEmotion) },
    { label: '语音', value: cleanEmotionValue(result.audioEmotion) },
    { label: '文本', value: cleanEmotionValue(result.textEmotion) },
  ];
});

const dominantEmotionText = computed(() => {
  const result = analysisResult.value || {};
  const candidates = [
    result.overallStatusText,
    result.dominantEmotion,
    result.textEmotion,
    result.audioEmotion,
    result.faceEmotion,
  ];
  const emotion = candidates.map(cleanEmotionValue).find((item) => item !== '未检测');
  return emotion || '综合研判中';
});

// ===== 结论概览（仅日间展示） =====
const EMOTION_EMOJI = [
  { keys: ['开心', '快乐', '高兴', '愉悦', '积极', '喜悦'], emoji: '😊' },
  { keys: ['悲伤', '难过', '低落', '抑郁', '伤心', '沮丧'], emoji: '😔' },
  { keys: ['恐惧', '害怕', '焦虑', '紧张', '担忧', '不安'], emoji: '😰' },
  { keys: ['愤怒', '生气', '恼怒', '烦躁'], emoji: '😠' },
  { keys: ['厌恶', '反感'], emoji: '😖' },
  { keys: ['惊讶', '震惊'], emoji: '😲' },
  { keys: ['平静', '中性', '安定', '放松'], emoji: '😌' },
  { keys: ['关注', '警惕', '预警', '风险'], emoji: '🫧' },
];

const dominantEmoji = computed(() => {
  const text = dominantEmotionText.value || '';
  const hit = EMOTION_EMOJI.find((item) => item.keys.some((key) => text.includes(key)));
  return hit ? hit.emoji : '🧠';
});

const consistencyText = computed(() => {
  const detected = emotionSignalItems.value.filter((item) => item.value !== '未检测');
  if (!detected.length) return '等待信号';

  const counts = detected.reduce((acc, item) => {
    acc[item.value] = (acc[item.value] || 0) + 1;
    return acc;
  }, {});
  const top = Math.max(...Object.values(counts));
  return `${top}/${detected.length} 模态一致`;
});

const emotionBridgeSummary = computed(() => {
  const detectedSignals = emotionSignalItems.value
    .filter((item) => item.value !== '未检测')
    .map((item) => `${item.label}${item.value}`);

  const sourceText = detectedSignals.length
    ? detectedSignals.join('、')
    : '当前多模态输入';
  const baseDescription = String(analysisResult.value?.description || '').trim();
  const conciseDescription = baseDescription
    ? `初步结论显示：${baseDescription.replace(/\s+/g, ' ').slice(0, 72)}`
    : `系统已形成以“${dominantEmotionText.value}”为核心的情绪线索。`;

  return `${sourceText}已完成融合解析，${conciseDescription} 该结果将同步作为心理知识库页面生成评估报告和干预建议的输入依据。`;
});

const revokeUploadedVideoPreviewUrl = () => {
  if (!uploadedVideoPreviewUrl.value) return;
  URL.revokeObjectURL(uploadedVideoPreviewUrl.value);
  uploadedVideoPreviewUrl.value = '';
};

const revokeUploadedAudioPreviewUrl = () => {
  if (!uploadedAudioPreviewUrl.value) return;
  URL.revokeObjectURL(uploadedAudioPreviewUrl.value);
  uploadedAudioPreviewUrl.value = '';
};

const getVideoPreviewElements = () =>
  [videoBackdropElement.value, videoElement.value].filter(Boolean);

const resetVideoPreview = () => {
  getVideoPreviewElements().forEach((element) => {
    try {
      element.pause?.();
    } catch (_) {
      // 忽略暂停失败，继续清理媒体源。
    }
    element.srcObject = null;
    element.removeAttribute('src');
    element.load?.();
  });
};

const resetUploadedAudioPreview = () => {
  const element = uploadedAudioElement.value;
  if (!element) return;

  try {
    element.pause();
  } catch (_) {
    // 忽略暂停失败，继续清理音频源。
  }

  try {
    element.currentTime = 0;
  } catch (_) {
    // 元数据未加载时部分浏览器不允许重置 currentTime。
  }

  element.removeAttribute('src');
  element.load?.();
};

const updateVideoPreview = async () => {
  await nextTick();

  const previewElements = getVideoPreviewElements();
  if (!previewElements.length) return;

  if (uploadedVideoPreviewUrl.value) {
    previewElements.forEach((element) => {
      element.pause?.();
      element.srcObject = null;
      element.src = uploadedVideoPreviewUrl.value;
      element.load();
    });
    return;
  }

  previewElements.forEach((element) => {
    element.removeAttribute('src');
    element.srcObject = localVideoStream.value || null;
  });

  if (localVideoStream.value) {
    await Promise.all(
      previewElements.map((element) => element.play().catch(() => {}))
    );
  }
};

const updateUploadedAudioPreview = async () => {
  await nextTick();

  const element = uploadedAudioElement.value;
  if (!element) return;

  if (uploadedAudioPreviewUrl.value) {
    element.src = uploadedAudioPreviewUrl.value;
    element.load?.();
    return;
  }

  element.removeAttribute('src');
  element.load?.();
};

// ===== 上传文件 =====
const triggerVideoUpload = () => {
  videoFileInput.value?.click();
};

const triggerAudioUpload = () => {
  audioFileInput.value?.click();
};

const handleVideoUpload = async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;

  try {
    uploadedVideoFile.value = file;
    setAnalysisResult(null);

    revokeUploadedVideoPreviewUrl();
    uploadedVideoPreviewUrl.value = URL.createObjectURL(file);
    await updateVideoPreview();

    console.log('视频上传成功:', file.name);
  } catch (error) {
    console.error('视频上传失败:', error);
    alert('视频上传失败，请重试');
  }
};

const handleAudioUpload = async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;

  try {
    uploadedAudioFile.value = file;
    setAnalysisResult(null);
    hasAudioCapture.value = true;
    revokeUploadedAudioPreviewUrl();
    uploadedAudioPreviewUrl.value = URL.createObjectURL(file);
    await updateUploadedAudioPreview();

    console.log('音频上传成功:', file.name);
  } catch (error) {
    console.error('音频上传失败:', error);
    alert('音频上传失败，请重试');
  }
};

const clearUploadedVideo = () => {
  resetVideoPreview();
  uploadedVideoFile.value = null;
  setAnalysisResult(null);
  revokeUploadedVideoPreviewUrl();
  
  // 重置文件输入
  if (videoFileInput.value) {
    videoFileInput.value.value = '';
  }

};

const clearUploadedAudio = () => {
  resetUploadedAudioPreview();
  uploadedAudioFile.value = null;
  hasAudioCapture.value = hasLiveTrack(localAudioStream.value, 'audio') || Boolean(latestAudioEmotion);
  setAnalysisResult(null);
  revokeUploadedAudioPreviewUrl();
  
  // 重置文件输入
  if (audioFileInput.value) {
    audioFileInput.value.value = '';
  }
  
  resetAudioLevels();
};

const hasLiveTrack = (stream, kind) => {
  if (!(stream instanceof MediaStream)) return false;

  return stream.getTracks().some(
    (track) => track.kind === kind && track.readyState === 'live'
  );
};

const stopStream = (stream) => {
  if (!(stream instanceof MediaStream)) return;
  stream.getTracks().forEach((track) => track.stop());
};

const resetAudioLevels = () => {
  audioLevels.value = Array.from({ length: 20 }, () => 12);
};

watch(localVideoStream, () => {
  updateVideoPreview();
}, { immediate: true });

const stopAudioVisualizer = async () => {
  if (audioAnimationFrame) {
    cancelAnimationFrame(audioAnimationFrame);
    audioAnimationFrame = 0;
  }

  if (audioSourceNode) {
    audioSourceNode.disconnect();
    audioSourceNode = null;
  }

  audioAnalyser = null;

  if (audioContext) {
    const ctx = audioContext;
    audioContext = null;
    await ctx.close().catch(() => {});
  }

  resetAudioLevels();
};

const startAudioVisualizer = async (stream) => {
  await stopAudioVisualizer();

  if (!(stream instanceof MediaStream)) return;

  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) return;

  try {
    audioContext = new AudioContextCtor();
    if (audioContext.state === 'suspended') {
      await audioContext.resume();
    }

    audioAnalyser = audioContext.createAnalyser();
    audioAnalyser.fftSize = 128;
    audioAnalyser.smoothingTimeConstant = 0.78;

    audioSourceNode = audioContext.createMediaStreamSource(stream);
    audioSourceNode.connect(audioAnalyser);

    const frequencyData = new Uint8Array(audioAnalyser.frequencyBinCount);
    const render = () => {
      if (!audioAnalyser) return;

      audioAnalyser.getByteFrequencyData(frequencyData);
      const groupSize = Math.max(1, Math.floor(frequencyData.length / 20));

      audioLevels.value = Array.from({ length: 20 }, (_, index) => {
        const start = index * groupSize;
        const end = Math.min(frequencyData.length, start + groupSize);
        let total = 0;

        for (let cursor = start; cursor < end; cursor += 1) {
          total += frequencyData[cursor];
        }

        const average = end > start ? total / (end - start) : 0;
        return 10 + Math.round((average / 255) * 30);
      });

      audioAnimationFrame = requestAnimationFrame(render);
    };

    render();
  } catch (error) {
    console.warn('启动音频可视化失败:', error);
    resetAudioLevels();
  }
};

const syncPublishStream = () => {
  const hasVideo = hasLiveTrack(localVideoStream.value, 'video');
  const hasAudio = hasLiveTrack(localAudioStream.value, 'audio');
  const nextSignature = `v${hasVideo ? 1 : 0}-a${hasAudio ? 1 : 0}`;
  const mediaChanged = nextSignature !== lastMediaSignature;

  lastMediaSignature = nextSignature;

  const publishStream = hasVideo || hasAudio ? new MediaStream() : null;
  if (publishStream) {
    if (hasVideo) {
      localVideoStream.value
        .getVideoTracks()
        .filter((track) => track.readyState === 'live')
        .forEach((track) => publishStream.addTrack(track));
    }
    if (hasAudio) {
      localAudioStream.value
        .getAudioTracks()
        .filter((track) => track.readyState === 'live')
        .forEach((track) => publishStream.addTrack(track));
    }
  }

  if (typeof window.setPublishStream === 'function') {
    window.setPublishStream(publishStream, {
      audio: hasAudio,
      video: hasVideo,
      audioActive: isRecording.value,
    });
  }

  if (typeof window.configurePublishMedia === 'function') {
    window.configurePublishMedia({
      audio: hasAudio,
      video: hasVideo,
      audioActive: isRecording.value,
    });
  }

  return {
    hasAudio,
    hasVideo,
    mediaChanged,
  };
};

const getCurrentSessionId = () => {
  const sidEl = document.getElementById('sessionid');
  return parseInt(sidEl?.value || '0', 10);
};

const ensureSessionIdReady = async (maxRetry = 24) => {
  for (let i = 0; i < maxRetry; i += 1) {
    const sid = getCurrentSessionId();
    if (sid > 0) return sid;
    await new Promise(resolve => setTimeout(resolve, 120));
  }
  return 0;
};

const startWebRTCConnection = async () => {
  if (isConnecting.value || isConnected.value) return;

  isConnecting.value = true;

  try {
    syncPublishStream();

    // 调用 public/client.js 中的 start() 函数建立WebRTC连接
    if (typeof window.start === 'function') {
      const started = await window.start();
      if (!started) {
        return;
      }

      // 等待sessionid就绪
      const sid = await ensureSessionIdReady();
      if (sid > 0) {
        sessionid.value = sid;
        isConnected.value = true;
        console.log('WebRTC连接成功, sessionid:', sid);
        
        // 开始轮询媒体状态
        startPollingMediaState();
      } else {
        console.warn('无法获取sessionid');
      }
    } else {
      console.warn('WebRTC客户端未加载');
    }
  } catch (error) {
    console.error('WebRTC连接失败:', error);
  } finally {
    isConnecting.value = false;
  }
};

const stopWebRTCConnection = () => {
  if (typeof window.stop === 'function') {
    window.stop();
  }
  isConnected.value = false;
  sessionid.value = 0;
  stopPollingMediaState();
};

const restartWebRTCConnection = async () => {
  stopWebRTCConnection();
  await new Promise((resolve) => setTimeout(resolve, 250));
  await startWebRTCConnection();
};

const startPollingMediaState = () => {
  stopPollingMediaState();

  pollTimer = setInterval(async () => {
    const sid = sessionid.value;
    if (sid <= 0) return;

    try {
      const response = await fetch(buildApiUrl(`/webrtc_media_state?sessionid=${sid}`));
      if (!response.ok) return;

      const result = await response.json();
      
      // 🔧 修复：后端返回的数据在 result.data 中
      if (result.code !== 0 || !result.data) return;
      
      const data = result.data;

      // 提取人脸情绪
      if (data.face_emotion && data.face_emotion.emotion) {
        latestFaceEmotion = data.face_emotion.emotion;
        console.log('更新面部情绪:', latestFaceEmotion);
      }

      // 提取语音情绪
      if (data.last_asr && data.last_asr.emotion_label) {
        latestAudioEmotion = data.last_asr.emotion_label;
        hasAudioCapture.value = true;
        console.log('更新语音情绪:', latestAudioEmotion);
      }

      console.log('媒体状态更新:', {
        face: latestFaceEmotion,
        audio: latestAudioEmotion,
        sessionid: sid
      });
    } catch (error) {
      console.error('获取媒体状态失败:', error);
    }
  }, 1000); // 每秒轮询一次
};

const stopPollingMediaState = () => {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
};

const ensureAudioCaptureReady = async () => {
  if (hasLiveTrack(localAudioStream.value, 'audio')) {
    return localAudioStream.value;
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
    },
    video: false,
  });

  localAudioStream.value = stream;
  hasAudioCapture.value = true;
  return stream;
};

const toggleCamera = async () => {
  if (isCameraActive.value) {
    // 关闭摄像头并同步更新上行媒体
    stopStream(localVideoStream.value);
    localVideoStream.value = null;
    isCameraActive.value = false;

    const { hasAudio, mediaChanged } = syncPublishStream();
    if (isConnected.value && mediaChanged) {
      if (hasAudio) {
        await restartWebRTCConnection();
      } else {
        stopWebRTCConnection();
      }
    }
  } else {
    // 开启摄像头
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: 'user'
        },
        audio: false
      });

      localVideoStream.value = stream;
      isCameraActive.value = true;

      const { mediaChanged } = syncPublishStream();
      if (!isConnected.value) {
        await startWebRTCConnection();
      } else if (mediaChanged) {
        await restartWebRTCConnection();
      }
    } catch (error) {
      console.error('无法访问摄像头:', error);
      isCameraActive.value = false;
    }
  }
};

const startRecording = async () => {
  isRecordPressActive = true;
  if (isRecording.value) return;

  try {
    const stream = await ensureAudioCaptureReady();
    if (!isRecordPressActive) {
      return;
    }

    isRecording.value = true;
    isAudioActive.value = true;
    const { mediaChanged } = syncPublishStream();
    await startAudioVisualizer(stream);

    if (!isConnected.value) {
      await startWebRTCConnection();
    } else if (mediaChanged) {
      await restartWebRTCConnection();
    }

    console.log('开始录音');

    // 如果有WebRTC连接，尝试调用后端API
    if (isConnected.value && sessionid.value > 0) {
      try {
        const response = await fetch(buildApiUrl('/webrtc_asr_control'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sessionid: sessionid.value,
            action: 'start',
            mode: 'chat'
          })
        });

        if (response.ok) {
          console.log('后端录音已启动');
        }
      } catch (error) {
        console.log('后端录音启动失败（预期行为）:', error.message);
      }
    }
  } catch (error) {
    console.error('无法访问麦克风:', error);
    isRecording.value = false;
    isAudioActive.value = false;
    syncPublishStream();
    await stopAudioVisualizer();
  }
};

const stopRecording = async () => {
  isRecordPressActive = false;
  if (!isRecording.value) return;

  isRecording.value = false;
  syncPublishStream();
  console.log('停止录音');

  // 如果有WebRTC连接，尝试调用后端API
  if (isConnected.value && sessionid.value > 0) {
    try {
      const response = await fetch(buildApiUrl('/webrtc_asr_control'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sessionid: sessionid.value,
          action: 'stop',
          mode: 'chat'
        })
      });

      if (response.ok) {
        const data = await response.json();
        console.log('录音完成，识别结果:', data.transcript);

        // 提取语音情绪
        if (data.emotion_label) {
          latestAudioEmotion = data.emotion_label;
          hasAudioCapture.value = true;
        }
      }
    } catch (error) {
      console.log('后端录音停止失败（预期行为）:', error.message);
    }
  }

  await stopAudioVisualizer();
  isAudioActive.value = false;
};

const performAnalysis = async () => {
  if (!canAnalyze.value || isAnalyzing.value) return;

  isAnalyzing.value = true;
  setAnalysisResult(null);
  analysisStep.value = '正在准备分析数据...';
  analysisProgress.value = 10;

  try {
    const resolvedSessionId = sessionid.value > 0
      ? sessionid.value
      : (isConnected.value ? await ensureSessionIdReady(10) : 0);
    const usingLiveAnalysis = (
      (isCameraActive.value && !uploadedVideoFile.value) ||
      (isConnected.value && hasAudioCapture.value && !uploadedAudioFile.value)
    );

    if (usingLiveAnalysis && resolvedSessionId <= 0) {
      throw new Error('实时会话尚未准备完成，请重新开启摄像头或录音后再试');
    }

    const formData = new FormData();
    if (resolvedSessionId > 0) {
      sessionid.value = resolvedSessionId;
      formData.append('sessionid', String(resolvedSessionId));
    }
    formData.append('user_name', personaUserName);

    if (uploadedVideoFile.value) {
      formData.append('video_file', uploadedVideoFile.value);
    }

    if (uploadedAudioFile.value) {
      formData.append('audio_file', uploadedAudioFile.value);
    }

    analysisStep.value = '正在调用后端进行多模态分析...';
    analysisProgress.value = 35;

    const response = await fetch(buildApiUrl('/multimodal_analysis'), {
      method: 'POST',
      body: formData,
    });

    analysisProgress.value = 80;
    analysisStep.value = '正在整理分析报告...';

    const result = await response.json();
    if (!response.ok || result.code !== 0 || !result.data) {
      throw new Error(result.msg || '多模态分析失败');
    }

    analysisProgress.value = 100;
    setAnalysisResult(result.data);

    if (result.data.faceEmotion) {
      latestFaceEmotion = result.data.faceEmotion;
    }
    if (result.data.audioEmotion && result.data.audioEmotion !== '未检测') {
      latestAudioEmotion = result.data.audioEmotion;
      hasAudioCapture.value = true;
    }
  } catch (error) {
    console.error('分析失败:', error);
    alert(error.message || '分析过程中出现错误，请重试');
  } finally {
    isAnalyzing.value = false;
  }
};


onMounted(() => {
  restoreMultimodalState();

  originalOnWebRTCConnected = window.onWebRTCConnected;
  originalOnWebRTCDisconnected = window.onWebRTCDisconnected;

  window.onWebRTCConnected = () => {
    isConnected.value = true;
    isConnecting.value = false;
    const sid = getCurrentSessionId();
    if (sid > 0) {
      sessionid.value = sid;
    }
    startPollingMediaState();

    if (typeof originalOnWebRTCConnected === 'function') {
      originalOnWebRTCConnected();
    }
  };

  window.onWebRTCDisconnected = () => {
    isConnected.value = false;
    isConnecting.value = false;
    sessionid.value = 0;
    stopPollingMediaState();

    if (typeof originalOnWebRTCDisconnected === 'function') {
      originalOnWebRTCDisconnected();
    }
  };

  syncPublishStream();
});

// 组件卸载时清理资源
onUnmounted(() => {
  stopPollingMediaState();
  window.onWebRTCConnected = originalOnWebRTCConnected;
  window.onWebRTCDisconnected = originalOnWebRTCDisconnected;
  resetVideoPreview();
  revokeUploadedVideoPreviewUrl();
  resetUploadedAudioPreview();
  revokeUploadedAudioPreviewUrl();

  stopWebRTCConnection();
  stopStream(localVideoStream.value);
  stopStream(localAudioStream.value);
  localVideoStream.value = null;
  localAudioStream.value = null;
  stopAudioVisualizer();
});
</script>

<style scoped>
@import '../assets/multimodal-theme.css';

.multimodal-analysis {
  width: 100%;
  height: 100%;
  padding: 24px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: transparent;
}

.content-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  height: 100%;
  overflow: hidden;
}

/* 输入采集区 */
.input-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.capture-card {
  background: var(--theme-bg-card);
  border: 1px solid var(--theme-border);
  border-radius: 16px;
  padding: 16px;
  backdrop-filter: blur(10px);
  transition: background 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
}

.video-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.audio-card {
  flex: 0 0 auto;
}

.card-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--theme-text-primary);
  margin: 0 0 12px 0;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: color 0.3s ease;
}

.card-title i {
  color: var(--theme-primary);
  transition: color 0.3s ease;
}

.video-preview {
  position: relative;
  flex: 1;
  min-height: 0;
  border-radius: 12px;
  overflow: hidden;
  background:
    radial-gradient(circle at 30% 24%, var(--theme-gradient-2), transparent 42%),
    linear-gradient(180deg, var(--theme-bg-card), var(--theme-bg-input));
  margin-bottom: 12px;
  isolation: isolate;
  transition: background 0.3s ease;
}

.video-preview::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background:
    radial-gradient(circle at center, transparent 42%, var(--theme-gradient-3)),
    linear-gradient(180deg, var(--theme-gradient-1), var(--theme-gradient-2));
}

.video-inline-controls {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 12px;
  z-index: 3;
  pointer-events: auto;
}

.video-preview-blur-layer {
  position: absolute;
  inset: -10%;
  z-index: 0;
  pointer-events: none;
}

.video-preview-backdrop {
  width: 100%;
  height: 100%;
  object-fit: cover;
  filter: blur(28px) saturate(1.2) brightness(0.72);
  transform: scale(1.18);
  opacity: 0.92;
}

.video-preview-main {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.video-preview-main.is-live-feed {
  transform: scaleX(-1);
}

.video-preview-backdrop.is-live-feed {
  transform: scale(1.18) scaleX(-1);
}

.preview-placeholder {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--theme-primary);
  transition: color 0.3s ease;
}

.preview-placeholder i {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.preview-placeholder p {
  font-size: 0.9rem;
  color: var(--theme-text-muted);
  margin: 0;
  transition: color 0.3s ease;
}

.keyframe-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.audio-visualizer {
  padding: 24px 20px;
  background: var(--theme-bg-input);
  border-radius: 12px;
  margin-bottom: 12px;
  transition: background 0.3s ease;
}

.waveform {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 40px;
}

.wave-bar {
  width: 4px;
  min-height: 10px;
  background: var(--theme-gradient-1);
  border-radius: 2px;
  transition: height 0.12s ease, background-color 0.2s ease;
}

.wave-bar.active {
  background: var(--theme-primary);
}

.hidden-upload-audio {
  display: none;
}

.btn-toggle {
  width: 100%;
  padding: 8px;
  background: var(--theme-bg-input);
  border: 1px solid var(--theme-border);
  border-radius: 10px;
  color: var(--theme-text-primary);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.3s ease;
}

.btn-toggle:hover {
  background: var(--theme-gradient-1);
  border-color: var(--theme-primary);
}

.btn-toggle.active {
  background: linear-gradient(135deg, var(--theme-primary) 0%, var(--theme-primary-light) 100%);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 4px 12px var(--theme-gradient-2);
}

.btn-toggle.recording {
  animation: pulse 1.5s ease-in-out infinite;
}

.btn-toggle:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 🆕 测试上传功能样式 */
.test-badge {
  display: inline-block;
  padding: 2px 8px;
  margin-left: 8px;
  background: rgba(255, 193, 7, 0.2);
  border: 1px solid rgba(255, 193, 7, 0.5);
  border-radius: 12px;
  color: #ffc107;
  font-size: 0.75rem;
  font-weight: 600;
}

.button-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.button-group .btn-toggle {
  flex: 1;
}

.btn-upload {
  flex: 1;
  padding: 8px;
  background: var(--theme-gradient-2);
  border: 1px solid var(--theme-border);
  border-radius: 10px;
  color: var(--theme-primary-dark);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.3s ease;
}

.btn-upload:hover:not(:disabled) {
  background: var(--theme-gradient-3);
  border-color: var(--theme-primary);
}

.btn-upload:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-clear {
  padding: 8px 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 10px;
  color: #ef4444;
  font-size: 0.9rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
}

.btn-clear:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: #ef4444;
}

@keyframes pulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(255, 107, 129, 0.7);
  }
  50% {
    box-shadow: 0 0 0 10px rgba(255, 107, 129, 0);
  }
}

.btn-analyze {
  width: 100%;
  padding: 12px;
  background: linear-gradient(135deg, var(--theme-primary) 0%, var(--theme-primary-light) 100%);
  border: none;
  border-radius: 12px;
  color: #fff;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.3s ease;
  box-shadow: var(--theme-shadow);
  flex-shrink: 0;
}

.btn-analyze:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: var(--theme-shadow-hover);
}

.btn-analyze:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

/* 结果区 */
.result-section {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.result-card {
  flex: 1;
  background: var(--theme-bg-card);
  border: 1px solid var(--theme-border);
  border-radius: 16px;
  padding: 20px;
  backdrop-filter: blur(10px);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  transition: background 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
}

.result-card::-webkit-scrollbar {
  width: 6px;
}

.result-card::-webkit-scrollbar-track {
  background: transparent;
}

.result-card::-webkit-scrollbar-thumb {
  background: var(--theme-primary);
  border-radius: 10px;
  transition: background 0.3s ease;
}

.result-card::-webkit-scrollbar-thumb:hover {
  background: var(--theme-primary-dark);
}

.emotion-note {
  margin: 12px 0 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--theme-gradient-1);
  border: 1px solid var(--theme-border);
  color: var(--theme-primary-dark);
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.82rem;
  line-height: 1.5;
  transition: background 0.3s ease, border-color 0.3s ease, color 0.3s ease;
}

.empty-state,
.analyzing-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #94a3b8;
}

.empty-state i {
  font-size: 64px;
  color: var(--theme-primary);
  opacity: 0.3;
  margin-bottom: 16px;
  transition: color 0.3s ease;
}

.spinner {
  width: 48px;
  height: 48px;
  margin-bottom: 16px;
  border: 4px solid var(--theme-gradient-1);
  border-top-color: var(--theme-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.progress-container {
  width: 100%;
  max-width: 400px;
  margin-top: 20px;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--theme-gradient-1);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 12px;
  transition: background 0.3s ease;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--theme-primary) 0%, var(--theme-primary-light) 100%);
  border-radius: 4px;
  transition: width 0.3s ease, background 0.3s ease;
}

.progress-text {
  font-size: 0.9rem;
  color: var(--theme-primary);
  text-align: center;
  margin: 0;
  transition: color 0.3s ease;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.result-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-block {
  padding: 16px;
  background: var(--theme-bg-input);
  border: 1px solid var(--theme-border);
  border-radius: 12px;
  transition: background 0.3s ease, border-color 0.3s ease;
}

.block-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--theme-text-primary);
  margin: 0 0 12px 0;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: color 0.3s ease;
}

.block-title i {
  color: var(--theme-primary);
  transition: color 0.3s ease;
}


.emotion-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.emotion-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  background: var(--theme-bg-card);
  border-radius: 8px;
  transition: background 0.3s ease;
}

.emotion-label {
  font-size: 0.75rem;
  color: var(--theme-text-muted);
  transition: color 0.3s ease;
}

.emotion-value {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--theme-text-primary);
  transition: color 0.3s ease;
}

.overall-status {
  text-align: center;
}

.status-badge {
  display: inline-block;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 10px;
}

.status-good {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.status-warning {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.status-alert {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.status-description {
  font-size: 0.85rem;
  color: var(--theme-text-secondary);
  line-height: 1.5;
  margin: 0;
  transition: color 0.3s ease;
}

.suggestions-list {
  margin: 0;
  padding-left: 20px;
  color: var(--theme-text-secondary);
  line-height: 1.6;
  font-size: 0.85rem;
  transition: color 0.3s ease;
}

.suggestions-list li {
  margin-bottom: 6px;
}

.text-content-display {
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 8px;
  color: #e2e8f0;
  font-size: 0.9rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.btn-use-in-avatar {
  width: 100%;
  margin-top: 12px;
  padding: 10px 16px;
  background: linear-gradient(135deg, var(--theme-primary-dark) 0%, var(--theme-primary) 100%);
  border: none;
  border-radius: 10px;
  color: #fff;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.3s ease;
  box-shadow: var(--theme-shadow);
}

.btn-use-in-avatar:hover {
  transform: translateY(-2px);
  box-shadow: var(--theme-shadow-hover);
}

.keyframes-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.knowledge-bridge-block {
  background:
    linear-gradient(135deg, rgba(14, 165, 233, 0.12), rgba(34, 197, 94, 0.08)),
    var(--theme-bg-input);
  border-color: rgba(125, 211, 252, 0.22);
}

.knowledge-bridge-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

.knowledge-bridge-panel {
  min-width: 0;
  padding: 12px;
  background: rgba(15, 23, 42, 0.42);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 10px;
}

.bridge-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.bridge-panel-label {
  color: var(--theme-text-primary);
  font-size: 0.82rem;
  font-weight: 700;
}

.bridge-status {
  flex: 0 0 auto;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.14);
  color: #7dd3fc;
  font-size: 0.72rem;
  font-weight: 700;
}

.bridge-status.accent {
  background: rgba(34, 197, 94, 0.14);
  color: #86efac;
}

.knowledge-source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.knowledge-source-chip {
  max-width: 100%;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 9px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  color: #dbeafe;
  font-size: 0.78rem;
  line-height: 1.25;
}

.knowledge-source-chip span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-source-chip i {
  flex: 0 0 auto;
  color: #93c5fd;
}

.bridge-footnote,
.emotion-bridge-summary {
  margin: 10px 0 0;
  color: var(--theme-text-secondary);
  font-size: 0.8rem;
  line-height: 1.55;
}

.emotion-signal-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.emotion-signal-pill {
  min-width: 0;
  padding: 8px 7px;
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(134, 239, 172, 0.14);
  border-radius: 8px;
  color: #e2e8f0;
  font-size: 0.78rem;
  line-height: 1.25;
  text-align: center;
}

.emotion-signal-pill strong {
  display: block;
  margin-bottom: 3px;
  color: #86efac;
  font-size: 0.72rem;
}

.keyframe-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.keyframe-image {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 8px;
  overflow: hidden;
  background: var(--theme-bg-input);
  transition: background 0.3s ease;
}

.keyframe-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.keyframe-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 6px 8px;
  background: linear-gradient(to top, var(--theme-bg-base), transparent);
  display: flex;
  align-items: center;
  justify-content: center;
}

.keyframe-time {
  font-size: 0.75rem;
  font-weight: 600;
  color: #fff;
  text-shadow: 0 1px 2px var(--theme-shadow);
}

.keyframe-emotion {
  font-size: 0.8rem;
  color: #cbd5e1;
  text-align: center;
}

.result-meta {
  padding-top: 12px;
  border-top: 1px solid rgba(255, 107, 129, 0.15);
  font-size: 0.8rem;
  color: #94a3b8;
  display: flex;
  align-items: center;
  gap: 6px;
}

.assessment-entry {
  min-height: 68px;
  padding: 13px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid color-mix(in srgb, var(--theme-primary) 36%, transparent);
  border-radius: 15px;
  color: var(--theme-text-primary);
  text-decoration: none;
  background:
    radial-gradient(circle at 88% 20%, rgba(124, 92, 255, .22), transparent 30%),
    linear-gradient(135deg, var(--theme-gradient-1), var(--theme-bg-input));
  transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease;
}

.assessment-entry:hover {
  transform: translateY(-2px);
  border-color: var(--theme-primary);
  box-shadow: var(--theme-shadow-hover);
}

.assessment-entry span,
.assessment-entry small,
.assessment-entry strong {
  display: block;
}

.assessment-entry small {
  margin-bottom: 4px;
  color: var(--theme-primary);
  font-size: .7rem;
  font-weight: 800;
  letter-spacing: .06em;
}

.assessment-entry strong {
  font-size: .92rem;
}

.assessment-entry > i {
  flex: 0 0 auto;
  color: var(--theme-primary);
  font-size: 1.45rem;
}

/* ===== 结论概览条（日间温柔疗愈视图） ===== */
.result-overview {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  padding: 18px 20px;
  border: 1px solid var(--theme-border);
  border-radius: 18px;
  background:
    radial-gradient(circle at 12% 18%, var(--theme-gradient-1), transparent 48%),
    radial-gradient(circle at 92% 82%, var(--theme-gradient-2), transparent 52%),
    var(--theme-bg-card);
  box-shadow: var(--theme-shadow);
}

.overview-emotion {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.overview-emoji {
  font-size: 2.6rem;
  line-height: 1;
  filter: drop-shadow(0 4px 10px rgba(224, 122, 151, 0.28));
}

.overview-emotion-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.overview-kicker {
  font-size: 0.72rem;
  letter-spacing: 0.05em;
  color: var(--theme-text-muted);
}

.overview-emotion-text strong {
  font-size: 1.35rem;
  font-weight: 800;
  line-height: 1.15;
  color: var(--theme-text-primary);
}

.overview-signals {
  display: flex;
  align-items: stretch;
  flex-wrap: wrap;
  gap: 8px;
}

.overview-signal {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 64px;
  padding: 8px 12px;
  border: 1px solid var(--theme-border);
  border-radius: 12px;
  background: rgba(255, 252, 250, 0.62);
  text-align: center;
}

.overview-signal-label {
  font-size: 0.66rem;
  color: var(--theme-text-muted);
}

.overview-signal strong {
  font-size: 0.86rem;
  font-weight: 700;
  color: var(--theme-text-primary);
}

.overview-signal.muted {
  opacity: 0.5;
}

.overview-signal.consistency {
  background: rgba(124, 174, 155, 0.12);
  border-color: rgba(124, 174, 155, 0.24);
}

.overview-signal.consistency strong {
  color: var(--heal-sage-strong, #5f9a85);
}

@media (max-width: 1024px) {
  .content-layout {
    grid-template-columns: 1fr;
  }
  
  .keyframes-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .knowledge-bridge-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .emotion-grid,
  .emotion-signal-row {
    grid-template-columns: 1fr;
  }
}
</style>
