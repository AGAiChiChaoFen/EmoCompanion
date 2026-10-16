<template>
  <!--
    全新设计：
    - 整个页面都是数字人视频（全屏）
    - 中间一个唤醒按钮
    - 聊天记录作为悬浮弹窗（可拖动/调整大小）
    - 摄像头组件悬浮显示
  -->
  <div class="digital-companion" :class="{ 'theme-day': isDayTheme }">
    <!-- 全屏数字人视频区 -->
    <section class="video-container">
      <div class="stage-aura" aria-hidden="true"></div>

      <canvas
        id="video-blur-bg"
        class="video-blur-bg"
        :style="{ opacity: isConnected && hasRemoteVideoFrame ? 1 : 0 }"
      ></canvas>

      <div
        id="video-placeholder"
        class="video-placeholder"
        v-show="showVideoPlaceholder"
        :class="{ loading: isConnecting || (isConnected && !hasRemoteVideoFrame) }"
      >
        <div class="placeholder-logo">
          <i class="bi bi-heart-pulse-fill"></i>
          <span class="logo-ring ring-a"></span>
          <span class="logo-ring ring-b"></span>
          <span class="logo-ring ring-c"></span>
        </div>
        <p class="placeholder-title">{{ placeholderTitle }}</p>
        <p class="placeholder-subtitle">{{ placeholderSubtitle }}</p>
      </div>

      <video
        id="video"
        autoplay
        preload="auto"
        playsinline
        @loadeddata="handleRemoteVideoReady"
        @playing="handleRemoteVideoReady"
      ></video>
      <audio id="audio" autoplay preload="auto"></audio>

      <div class="call-status" role="status" aria-live="polite">
        {{ connectionText }} · {{ isConnected ? asrStatusText : placeholderSubtitle }}
      </div>

      <!-- 页面中下方唤醒按钮 -->
      <div class="center-control">
        <button
          v-show="!isConnected && !isConnecting"
          @click="handleStart"
          class="btn-wake"
        >
          <i class="bi bi-heart-pulse-fill"></i>
          <span>唤醒数字人</span>
        </button>

        <button
          v-show="isConnected || isConnecting"
          @click="handleStop"
          class="btn-stop"
        >
          <i class="bi bi-x-circle-fill"></i>
          <span>结束对话</span>
        </button>
      </div>

      <!-- 摄像头采集卡片 -->
      <LocalCaptureCard
        v-if="isCameraEnabled"
        :is-camera-enabled="isCameraEnabled"
        :is-camera-starting="isCameraStarting"
        :local-stream="localCameraStream"
        :capture-status-text="captureStatusText"
        @toggle-camera="toggleCameraCapture"
      />

      <!-- 悬浮控制按钮组 -->
      <div class="floating-controls">
        <button
          v-if="isRealtimeMode"
          class="control-btn"
          :class="{ active: isAutoListeningRunning }"
          :disabled="!isConnected || isAutoCommitInFlight"
          @click="toggleRealtimeAutoListen"
          :title="freeTalkButtonText"
        >
          <i :class="['bi', isAutoListeningRunning ? 'bi-mic-fill' : 'bi-mic-mute-fill']"></i>
        </button>

        <button
          class="control-btn"
          @click="toggleCameraCapture"
          :disabled="!isConnected"
          :title="isCameraEnabled ? '关闭摄像头' : '开启摄像头'"
        >
          <i :class="['bi', isCameraEnabled ? 'bi-camera-video-fill' : 'bi-camera-video-off-fill']"></i>
        </button>

        <button
          class="control-btn"
          @click="toggleChatWindow"
          title="聊天记录"
        >
          <i class="bi bi-chat-dots-fill"></i>
        </button>

      </div>
    </section>

    <!-- 聊天记录悬浮窗 -->
    <div
      v-show="showChatWindow"
      class="chat-window"
      :class="{ 'theme-light': isDayTheme }"
      :style="chatWindowStyle"
      ref="chatWindowRef"
    >
      <div class="chat-header" @mousedown="startDrag">
        <div class="chat-title">
          <i class="bi bi-chat-dots-fill"></i>
          <span>对话记录</span>
        </div>
        <div class="chat-actions">
          <button
            class="header-btn"
            :disabled="!canClearHistory"
            @click="handleClearHistory"
            title="清空历史"
          >
            <i class="bi bi-trash3-fill"></i>
          </button>
          <button
            class="header-btn"
            :disabled="!canExportHistory"
            @click="handleExportChat"
            title="导出记录"
          >
            <i class="bi bi-download"></i>
          </button>
          <button
            class="header-btn"
            @click="toggleChatWindow"
            title="关闭"
          >
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
      </div>

      <div class="chat-body">
        <ChatMessageList ref="messageListRef" :messages="messages" />
      </div>
      <form class="chat-input" @submit.prevent="sendMessage">
        <textarea
          ref="chatTextarea"
          v-model="inputText"
          aria-label="对话消息"
          placeholder="输入想说的话…"
          rows="1"
          :disabled="!isConnected"
          @input="adjustTextareaHeight"
          @keydown.enter.exact.prevent="sendMessage"
        ></textarea>
        <button type="submit" :disabled="!isConnected || !inputText.trim()">发送</button>
      </form>
    </div>

    <input type="hidden" id="sessionid" />
  </div>
</template>

<script setup>
import {
  ref,
  computed,
  reactive,
  nextTick,
  onMounted,
  onUnmounted,
  watch,
} from "vue";
import ChatMessageList from "./ChatMessageList.vue";
import LocalCaptureCard from "./LocalCaptureCard.vue";
import { buildApiUrl } from "../utils/api";
import { useTheme } from "../composables/useTheme";
// 导入主题样式
import '@/assets/conversation-page-theme.css';

// ===== 路由模式参数 =====
const props = defineProps({
  pageMode: {
    type: String,
    default: "realtime",
  },
});

// 主题只由应用外壳（侧边栏/顶部栏）的全局开关控制。
const { isDayTheme } = useTheme();

const DEFAULT_WELCOME_MESSAGE = "欢迎使用 EmoCompanion，我会用心聆听您的每一句话。";
const HISTORY_STORAGE_KEY = "hearttalk-companion-history-v1";
const HISTORY_EXPORT_PREFIX = "emocompanion-history";
const HISTORY_PERSIST_DELAY_MS = 180;
const AVATAR_PLAYBACK_INTERRUPT_ON_SEND = false;
const MESSAGE_ROLE_LABELS = {
  system: "系统",
  user: "用户",
  ai: "AI",
};
const SUPPORTED_MESSAGE_TYPES = new Set(Object.keys(MESSAGE_ROLE_LABELS));
let messageSequence = 0;
let historyPersistTimer = null;

const nextMessageId = () => {
  messageSequence += 1;
  return `msg-${Date.now()}-${messageSequence}`;
};

const isNonEmptyText = (value) => String(value ?? "").trim().length > 0;

const createMessage = (
  type,
  text,
  extra = {}
) => {
  const { id, createdAt, ...rest } = extra;

  return {
    id: typeof id === "string" && id ? id : nextMessageId(),
    type,
    text: String(text ?? ""),
    createdAt:
      typeof createdAt === "string" && !Number.isNaN(Date.parse(createdAt))
        ? createdAt
        : new Date().toISOString(),
    ...rest,
  };
};

const createDefaultWelcomeMessage = () =>
  createMessage("system", DEFAULT_WELCOME_MESSAGE);

const isDefaultWelcomeMessage = (message) =>
  message?.type === "system" &&
  String(message?.text ?? "") === DEFAULT_WELCOME_MESSAGE;

const sanitizePersistedMessage = (raw) => {
  if (!raw || typeof raw !== "object") return null;

  const candidate = raw;
  const type = String(candidate.type ?? "");
  if (!SUPPORTED_MESSAGE_TYPES.has(type)) return null;

  const text = String(candidate.text ?? "");
  if (!isNonEmptyText(text)) return null;

  return createMessage(type, text, {
    id: candidate.id,
    createdAt: candidate.createdAt,
  });
};

const loadPersistedMessages = () => {
  if (typeof window === "undefined") {
    return [createDefaultWelcomeMessage()];
  }

  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) {
      return [createDefaultWelcomeMessage()];
    }

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [createDefaultWelcomeMessage()];
    }

    const restored = parsed
      .map((item) => sanitizePersistedMessage(item))
      .filter(Boolean);

    return restored.length > 0 ? restored : [createDefaultWelcomeMessage()];
  } catch (error) {
    console.warn("Failed to load persisted chat history:", error);
    return [createDefaultWelcomeMessage()];
  }
};

// 自由通话模式下传给后端 webrtc_asr_control 的 mode 标识。
const REALTIME_ASR_MODE = "realtime_free_talk";

// ===== 自由通话自动轮次阈值 =====
const AUTO_COMMIT_SILENCE_MS = 2500;
const AUTO_COMMIT_PUNCTUATION_IDLE_MS = 480;
const AUTO_COMMIT_MAX_SEGMENT_MS = 30000;
const AUTO_COMMIT_MIN_TEXT_CHARS = 2;
const FREE_TALK_RESTART_DELAY_MS = 120;

// 仅区分连续语音和文字聊天；两种模式都使用真实 WebRTC 会话。
const isRealtimeMode = computed(() => props.pageMode !== "chat");

// ===== 页面基础状态 =====
const isConnecting = ref(false);
const isConnected = ref(false);
const hasRemoteVideoFrame = ref(false);
const inputText = ref("");
const messages = ref(loadPersistedMessages());
const sessionid = ref("");
import { personaUserName } from "../composables/useAnalysisResult";
const chatTextarea = ref(null);
const messageListRef = ref(null);

// ===== 状态标签（UI chips） =====
const asrStatusText = ref("语音输入待命");
const asrStatusLevel = ref("idle");

const cameraStatusText = ref("摄像头未开启");
const cameraStatusLevel = ref("idle");

let latestUplinkAsrText = "";

// ===== 自由通话模式状态机 =====
// isAutoListeningEnabled：用户开关；
// isAutoListeningRunning：后端当前处于 recording 状态；
// isAutoCommitInFlight：正在执行 stop->转写->发送->restart。
const isAutoListeningEnabled = ref(true);
const isAutoListeningRunning = ref(false);
const isAutoCommitInFlight = ref(false);

// 自由通话运行时指标：用于自动切句判定与去重。
const freeTalkRuntime = reactive({
  partialText: "",
  lastPartialAt: 0,
  segmentStartedAt: 0,
  lastCommittedText: "",
  lastCommittedAt: 0,
  committedTurns: 0,
});

// ===== 本地摄像头采集状态 =====
const isCameraEnabled = ref(false);
const isCameraStarting = ref(false);
const localCameraStream = ref(null);
const captureStatusText = ref("");

// 🆕 ===== 情绪监控状态 =====
const audioEmotion = ref("");
const audioEmotionTimestamp = ref(0);
const faceEmotion = ref("中性/平静");
const faceEmotionTimestamp = ref(0);

// 连接质量状态
const packetLoss = ref(0);

// 延续轮询状态
let lastRecordingStopTime = 0;
const CONTINUE_POLLING_DURATION_MS = 10000;
const shouldContinuePollingAfterStop = () => {
  if (lastRecordingStopTime === 0) return false;
  const elapsed = Date.now() - lastRecordingStopTime;
  return elapsed < CONTINUE_POLLING_DURATION_MS;
};

// ===== 连接状态文案 =====
const modeLabel = computed(() =>
  isRealtimeMode.value ? "自由对话" : "聊天模式"
);

const connectionStatus = computed(() => {
  if (isConnected.value) return "connected";
  if (isConnecting.value) return "connecting";
  return "";
});

const connectionText = computed(() => {
  if (isConnected.value) return "已连接";
  if (isConnecting.value) return "连接中";
  return "未连接";
});

const showVideoPlaceholder = computed(
  () => !isConnected.value || !hasRemoteVideoFrame.value
);

const placeholderTitle = computed(() => {
  if (isConnected.value && !hasRemoteVideoFrame.value) {
    return "正在缓冲数字人视频...";
  }
  return isConnecting.value ? "正在唤醒您的AI情感伴侣..." : "AI伴侣待命中";
});

const placeholderSubtitle = computed(() => {
  if (isConnected.value && !hasRemoteVideoFrame.value) {
    return "后端正在攒首帧缓冲，完成后将连续播放";
  }
  return isRealtimeMode.value
    ? "连接后将开启智能聆听，理解您的情感需求"
    : "支持语音与文字交流，随时倾听您的心声";
});

const freeTalkButtonText = computed(() => {
  if (!isConnected.value) return "等待连接";
  return isAutoListeningRunning.value ? "暂停聆听" : "开始聆听";
});

const freeTalkTipText = computed(() => {
  if (!isConnected.value) {
    return "先点击“唤醒数字人”，连接成功后自动聆听才可生效。";
  }
  if (isAutoCommitInFlight.value) {
    return "正在自动切句并提交识别结果，请稍候。";
  }
  if (isAutoListeningRunning.value) {
    return "已进入自由通话：你停顿后会自动提交本句并触发数字人回复。";
  }
  return "自由聆听已暂停：可点击按钮恢复，或直接发送文本。";
});

const inputPlaceholder = computed(() => {
  return isAutoListeningRunning.value
    ? "正在聆听中..."
    : "语音交互模式";
});

// ===== 运行时句柄 =====
let chatEventSource = null;
let bgSyncReqId = null;
let connectionCheckTimer = null;
let mediaStatePollTimer = null;
let mediaStateFetchBusy = false;
let mediaStateFailCount = 0;
let mediaStateBackoffUntilMs = 0;
let originalOnWebRTCConnected = null;
let originalOnWebRTCDisconnected = null;
// ===== 流式文本渲染状态 =====
const streamingMsgIdMap = new Map();
const streamRenderStateMap = new Map();
const STREAM_RENDER_BASE_DELAY_MS = 150;
const STREAM_RENDER_FAST_DELAY_MS = 115;
const STREAM_RENDER_PUNCTUATION_DELAY_MS = 240;
const STREAM_RENDER_FAST_BUFFER_THRESHOLD = 240;
const STREAM_PAUSE_PUNCTUATION = new Set([
  "，",
  "。",
  "！",
  "？",
  "；",
  "：",
  ",",
  ".",
  "!",
  "?",
  ";",
  ":",
  "\n",
]);

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const getCurrentSessionId = () => {
  const sidEl = document.getElementById("sessionid");
  return parseInt(sidEl?.value || "0", 10);
};

const ensureSessionIdReady = async (maxRetry = 24) => {
  for (let i = 0; i < maxRetry; i += 1) {
    const sid = getCurrentSessionId();
    if (sid > 0) return sid;
    await delay(120);
  }
  return 0;
};

const pushSystemMessage = (text) => {
  messages.value.push(createMessage("system", text));
  scrollToBottom();
};

const adjustTextareaHeight = () => {
  if (!chatTextarea.value) return;
  chatTextarea.value.style.height = "44px";
  chatTextarea.value.style.height = `${chatTextarea.value.scrollHeight}px`;
};

const scrollToBottom = () => {
  nextTick(() => {
    messageListRef.value?.scrollToBottom?.();
  });
};

const handleRemoteVideoReady = () => {
  hasRemoteVideoFrame.value = true;
};

const normalizeTranscriptText = (value) =>
  String(value || "")
    .replace(/\s+/g, " ")
    .trim();

const getExportableMessages = () =>
  messages.value.filter(
    (msg) => isNonEmptyText(msg?.text) && !isDefaultWelcomeMessage(msg)
  );

const canClearHistory = computed(() => getExportableMessages().length > 0);
const canExportHistory = computed(() => getExportableMessages().length > 0);

const persistConversationHistory = () => {
  if (typeof window === "undefined") return;

  try {
    const persistableMessages = messages.value
      .filter((msg) => isNonEmptyText(msg?.text))
      .map((msg) => ({
        id: msg.id,
        type: msg.type,
        text: msg.text,
        createdAt: msg.createdAt,
      }));

    window.localStorage.setItem(
      HISTORY_STORAGE_KEY,
      JSON.stringify(persistableMessages)
    );
  } catch (error) {
    console.warn("Failed to persist chat history:", error);
  }
};

const schedulePersistConversationHistory = () => {
  if (historyPersistTimer) {
    clearTimeout(historyPersistTimer);
  }

  historyPersistTimer = setTimeout(() => {
    historyPersistTimer = null;
    persistConversationHistory();
  }, HISTORY_PERSIST_DELAY_MS);
};

const flushConversationHistoryPersistence = () => {
  if (historyPersistTimer) {
    clearTimeout(historyPersistTimer);
    historyPersistTimer = null;
  }

  persistConversationHistory();
};

const resetConversationHistory = (systemText = DEFAULT_WELCOME_MESSAGE) => {
  messages.value = [createMessage("system", systemText)];
  scrollToBottom();
};

const formatHistoryExportFileName = () => {
  const now = new Date();
  const timestamp = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
    "-",
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
    String(now.getSeconds()).padStart(2, "0"),
  ].join("");

  return `${HISTORY_EXPORT_PREFIX}-${timestamp}.json`;
};

const isMeaningfulTranscript = (value) => {
  const compact = normalizeTranscriptText(value).replace(
    /[，。！？、,.!?;；:：\s]/g,
    ""
  );
  return compact.length >= AUTO_COMMIT_MIN_TEXT_CHARS;
};

const resolveAsrLabel = (payload, fallbackLabel) => {
  const source = String(payload?.source || "");
  const backend = String(payload?.backend || "");

  if (source === "funasr_api" || backend === "funasr") {
    return "语音识别完成(FunASR)";
  }
  if (source === "custom_asr" || backend === "custom") {
    return "语音识别完成(自定义ASR)";
  }
  return fallbackLabel;
};

const extractEmotionPayload = (payload) => {
  const emotionPayload = {};
  const label = String(payload?.emotion_label || "").trim();
  if (label) {
    emotionPayload.emotion_label = label;
  }

  const scoreRaw = payload?.emotion_score;
  if (scoreRaw !== undefined && scoreRaw !== null && String(scoreRaw).trim() !== "") {
    const score = Number(scoreRaw);
    if (Number.isFinite(score)) {
      emotionPayload.emotion_score = score;
    }
  }

  if (payload && payload.emotion_extra !== undefined && payload.emotion_extra !== null) {
    emotionPayload.emotion_extra = payload.emotion_extra;
  }

  return emotionPayload;
};

// ===== SSE 流式回复相关 =====
const clearStreamRenderState = (streamId) => {
  const state = streamRenderStateMap.get(streamId);
  if (!state) return;
  if (state.timer) {
    clearTimeout(state.timer);
    state.timer = null;
  }
  streamRenderStateMap.delete(streamId);
};

const disconnectChatStream = () => {
  if (chatEventSource) {
    chatEventSource.close();
    chatEventSource = null;
  }

  for (const streamId of Array.from(streamRenderStateMap.keys())) {
    clearStreamRenderState(streamId);
  }

  for (const msg of streamingMsgIdMap.values()) {
    msg.streaming = false;
    msg.thinking = false;
  }
  streamingMsgIdMap.clear();
};

const ensureStreamingMessage = (streamId) => {
  if (!streamingMsgIdMap.has(streamId)) {
    const msg = reactive(
      createMessage("ai", "", {
        streaming: true,
        thinking: false,
        stream_id: streamId,
      })
    );
    messages.value.push(msg);
    streamingMsgIdMap.set(streamId, msg);
  }
  return streamingMsgIdMap.get(streamId);
};

const ensureStreamRenderState = (streamId) => {
  if (!streamRenderStateMap.has(streamId)) {
    streamRenderStateMap.set(streamId, {
      buffer: "",
      timer: null,
      ended: false,
      endText: "",
    });
  }
  return streamRenderStateMap.get(streamId);
};

const finalizeStreamingMessage = (streamId) => {
  const msg = streamingMsgIdMap.get(streamId);
  const state = streamRenderStateMap.get(streamId);

  if (!msg) {
    clearStreamRenderState(streamId);
    return;
  }

  if (!msg.text && state?.endText) {
    msg.text = state.endText;
  }

  msg.streaming = false;
  msg.thinking = false;
  streamingMsgIdMap.delete(streamId);
  clearStreamRenderState(streamId);
  scrollToBottom();
};

const scheduleStreamRender = (streamId) => {
  const state = ensureStreamRenderState(streamId);
  if (state.timer) return;

  const tick = () => {
    state.timer = null;
    const msg = streamingMsgIdMap.get(streamId);

    if (!msg) {
      clearStreamRenderState(streamId);
      return;
    }

    if (state.buffer.length > 0) {
      const chunk = state.buffer.slice(0, 1);
      msg.text += chunk;
      state.buffer = state.buffer.slice(1);
      msg.thinking = false;
      scrollToBottom();

      const lastChar = chunk[chunk.length - 1] || "";
      let nextDelay =
        state.buffer.length > STREAM_RENDER_FAST_BUFFER_THRESHOLD
          ? STREAM_RENDER_FAST_DELAY_MS
          : STREAM_RENDER_BASE_DELAY_MS;
      if (STREAM_PAUSE_PUNCTUATION.has(lastChar)) {
        nextDelay = STREAM_RENDER_PUNCTUATION_DELAY_MS;
      }

      state.timer = setTimeout(tick, nextDelay);
      return;
    }

    if (state.ended) {
      finalizeStreamingMessage(streamId);
    }
  };

  state.timer = setTimeout(tick, STREAM_RENDER_BASE_DELAY_MS);
};

const enqueueStreamText = (streamId, text) => {
  if (!text) return;
  const msg = ensureStreamingMessage(streamId);
  const state = ensureStreamRenderState(streamId);

  msg.thinking = false;
  state.buffer += text;
  scheduleStreamRender(streamId);
};

const handleChatStreamEvent = (payload) => {
  if (!payload || !payload.event || !payload.stream_id) return;

  if (payload.event === "thinking") {
    const msg = ensureStreamingMessage(payload.stream_id);
    ensureStreamRenderState(payload.stream_id);
    msg.thinking = true;
    msg.streaming = true;
    if (!msg.text) msg.text = "";
    scrollToBottom();
    return;
  }

  if (payload.event === "start") {
    const msg = ensureStreamingMessage(payload.stream_id);
    ensureStreamRenderState(payload.stream_id);
    msg.thinking = false;
    msg.streaming = true;
    scrollToBottom();
    return;
  }

  if (payload.event === "chunk") {
    enqueueStreamText(payload.stream_id, payload.text || "");
    return;
  }

  if (payload.event === "end") {
    const msg = ensureStreamingMessage(payload.stream_id);
    const state = ensureStreamRenderState(payload.stream_id);
    const endText = payload.text || "";

    msg.thinking = false;
    msg.streaming = true;
    state.ended = true;
    state.endText = endText;

    if (!state.buffer && endText && !msg.text) {
      state.buffer += endText;
    }
    scheduleStreamRender(payload.stream_id);
    return;
  }

  if (payload.event === "error") {
    const streamId = payload.stream_id;
    const msg = ensureStreamingMessage(streamId);
    const state = ensureStreamRenderState(streamId);

    state.buffer = "";
    state.ended = true;
    state.endText = `AI 生成失败：${payload.message || ""}`;
    msg.text = state.endText;
    msg.streaming = false;
    msg.thinking = false;

    finalizeStreamingMessage(streamId);
    scrollToBottom();
  }
};

const ensureChatStreamConnected = (forceReconnect = false) => {
  const sid = getCurrentSessionId();
  if (sid <= 0) return;

  if (!forceReconnect && chatEventSource && sessionid.value === sid) return;
  disconnectChatStream();

  sessionid.value = sid;
  chatEventSource = new EventSource(
    buildApiUrl(`/chat_stream?sessionid=${encodeURIComponent(String(sid))}`)
  );

  chatEventSource.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      handleChatStreamEvent(payload);
    } catch (err) {
      console.warn("Failed to parse stream JSON:", event.data);
    }
  };

  chatEventSource.onerror = (err) => {
    console.error("Chat Stream disconnected:", err);
  };
};

// ===== 消息发送 =====
const sendHumanMessage = async (text, source = "manual_text", emotionPayload = null) => {
  const msg = normalizeTranscriptText(text);
  if (!msg) return false;

  const sid = getCurrentSessionId();
  if (sid <= 0) {
    pushSystemMessage("请先建立连接！");
    return false;
  }

  ensureChatStreamConnected();
  messages.value.push(createMessage("user", msg));
  scrollToBottom();

  const requestPayload = {
    text: msg,
    type: "chat",
    // 保留后端已排队的数字人播报；服务器生成慢时只增加播放延迟，不清空口型队列。
    interrupt: AVATAR_PLAYBACK_INTERRUPT_ON_SEND,
    sessionid: sid,
    mode: props.pageMode,
    source,
    user_name: personaUserName,
  };

  if (emotionPayload && typeof emotionPayload === "object") {
    if (emotionPayload.emotion_label) {
      requestPayload.emotion_label = String(emotionPayload.emotion_label);
    }
    if (
      emotionPayload.emotion_score !== undefined &&
      emotionPayload.emotion_score !== null &&
      Number.isFinite(Number(emotionPayload.emotion_score))
    ) {
      requestPayload.emotion_score = Number(emotionPayload.emotion_score);
    }
    if (emotionPayload.emotion_extra !== undefined) {
      requestPayload.emotion_extra = emotionPayload.emotion_extra;
    }
  }

  try {
    const response = await fetch(buildApiUrl("/human"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload),
    });

    if (!response.ok) {
      throw new Error(`human status=${response.status}`);
    }
    return true;
  } catch (err) {
    console.error(err);
    pushSystemMessage("消息发送失败，请稍后重试。");
    return false;
  }
};

const sendMessage = async () => {
  const msg = inputText.value.trim();
  if (!msg) return;

  inputText.value = "";
  adjustTextareaHeight();
  await sendHumanMessage(msg);
};

// ===== WebRTC ASR 控制接口封装 =====
const requestWebrtcAsrControl = async ({ action, mode, hintText = "" }) => {
  const sid = await ensureSessionIdReady();
  if (sid <= 0) {
    throw new Error("invalid sessionid");
  }

  const response = await fetch(buildApiUrl("/webrtc_asr_control"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sessionid: sid,
      action,
      mode,
      browser_transcript_hint: hintText,
    }),
  });

  if (!response.ok) {
    throw new Error(`webrtc_asr_control ${action} status=${response.status}`);
  }
  return response.json();
};

// ===== 自由通话模式：自动轮次 =====
const resetFreeTalkSegmentState = () => {
  freeTalkRuntime.partialText = "";
  freeTalkRuntime.lastPartialAt = 0;
  freeTalkRuntime.segmentStartedAt = Date.now();
};

const startRealtimeAutoListen = async ({ resetSegment = true } = {}) => {
  if (!isRealtimeMode.value) return false;
  if (!isConnected.value || !isAutoListeningEnabled.value) return false;
  if (isAutoListeningRunning.value || isAutoCommitInFlight.value) return false;

  try {
    await requestWebrtcAsrControl({
      action: "start",
      mode: REALTIME_ASR_MODE,
    });

    isAutoListeningRunning.value = true;
    latestUplinkAsrText = "";
    if (resetSegment) {
      resetFreeTalkSegmentState();
    }

    asrStatusText.value = "自由通话聆听中，直接开口即可";
    asrStatusLevel.value = "recording";
    syncPublishMediaConfig();
    return true;
  } catch (err) {
    console.error("realtime auto listen start failed:", err);
    asrStatusText.value = "自由通话启动失败";
    asrStatusLevel.value = "error";
    pushSystemMessage("自由通话启动失败，请检查麦克风权限后重试。");
    syncPublishMediaConfig();
    return false;
  }
};

const commitRealtimeTurn = async ({ restart = true, reason = "silence" } = {}) => {
  if (!isRealtimeMode.value || !isConnected.value) return;
  if (isAutoCommitInFlight.value) return;

  isAutoCommitInFlight.value = true;
  isAutoListeningRunning.value = false;
  syncPublishMediaConfig();

  if (reason === "max_segment") {
    asrStatusText.value = "当前句子较长，自动切句中...";
  } else {
    asrStatusText.value = "检测到停顿，自动提交中...";
  }
  asrStatusLevel.value = "processing";

  let payload = null;
  let sent = false;

  try {
    try {
      payload = await requestWebrtcAsrControl({
        action: "stop",
        mode: REALTIME_ASR_MODE,
      });
    } catch (err) {
      console.error("realtime auto listen stop failed:", err);
      asrStatusText.value = "自动识别失败";
      asrStatusLevel.value = "error";
    }

    // 只使用 stop/final 的结果，避免用 partial 兜底导致误识别自动发送。
    const transcript = normalizeTranscriptText(payload?.transcript || "");

    if (payload) {
      asrStatusText.value = resolveAsrLabel(payload, "自由通话识别完成");
      asrStatusLevel.value = transcript ? "success" : "warning";
    }

    if (isMeaningfulTranscript(transcript)) {
      const isDuplicateRecent =
        transcript === freeTalkRuntime.lastCommittedText &&
        Date.now() - freeTalkRuntime.lastCommittedAt < 1800;

      if (!isDuplicateRecent) {
        const emotionPayload = payload ? extractEmotionPayload(payload) : null;
        sent = await sendHumanMessage(transcript, "voice_webrtc", emotionPayload);
        if (sent) {
          freeTalkRuntime.lastCommittedText = transcript;
          freeTalkRuntime.lastCommittedAt = Date.now();
          freeTalkRuntime.committedTurns += 1;
        }
      }
    }
  } finally {
    // 关键修复：必须先释放提交锁，再重启聆听；
    // 否则 startRealtimeAutoListen 会被 isAutoCommitInFlight 拦截，导致“一句后停住"。
    resetFreeTalkSegmentState();
    isAutoCommitInFlight.value = false;
  }

  if (restart && isRealtimeMode.value && isConnected.value && isAutoListeningEnabled.value) {
    await delay(FREE_TALK_RESTART_DELAY_MS);
    const restarted = await startRealtimeAutoListen({ resetSegment: false });
    if (restarted) {
      asrStatusText.value = sent ? "已自动发送，继续聆听中..." : "继续聆听中，请直接说下一句";
      asrStatusLevel.value = "recording";
    } else {
      asrStatusText.value = "自动续听失败，可点击“开启自由聆听”恢复";
      asrStatusLevel.value = "warning";
    }
  } else if (isRealtimeMode.value) {
    asrStatusText.value = "自由通话已暂停";
    asrStatusLevel.value = "warning";
  }

  syncPublishMediaConfig();
};

const stopRealtimeAutoListen = async ({ flushFinal = false } = {}) => {
  if (isAutoCommitInFlight.value) return;
  if (!isAutoListeningRunning.value) return;

  lastRecordingStopTime = Date.now();

  if (flushFinal) {
    await commitRealtimeTurn({ restart: false, reason: "manual" });
    return;
  }

  try {
    await requestWebrtcAsrControl({
      action: "stop",
      mode: REALTIME_ASR_MODE,
    });
  } catch (err) {
    console.warn("stop realtime auto listen ignored:", err);
  }

  isAutoListeningRunning.value = false;
  resetFreeTalkSegmentState();

  if (isRealtimeMode.value) {
    asrStatusText.value = "自由通话已暂停";
    asrStatusLevel.value = "warning";
  }
  syncPublishMediaConfig();
};

const maybeCommitRealtimeFromPartial = async () => {
  if (!isRealtimeMode.value) return;
  if (!isAutoListeningRunning.value || isAutoCommitInFlight.value) return;
  if (!isMeaningfulTranscript(freeTalkRuntime.partialText)) return;

  const now = Date.now();
  const idleMs = now - freeTalkRuntime.lastPartialAt;
  const segmentMs = now - freeTalkRuntime.segmentStartedAt;
  const hasStrongPunctuation = /[。！？!?]$/.test(freeTalkRuntime.partialText);

  if (segmentMs >= AUTO_COMMIT_MAX_SEGMENT_MS) {
    await commitRealtimeTurn({ restart: true, reason: "max_segment" });
    return;
  }

  if (hasStrongPunctuation && idleMs >= AUTO_COMMIT_PUNCTUATION_IDLE_MS) {
    await commitRealtimeTurn({ restart: true, reason: "punctuation" });
    return;
  }

  if (idleMs >= AUTO_COMMIT_SILENCE_MS) {
    await commitRealtimeTurn({ restart: true, reason: "silence" });
  }
};

const toggleRealtimeAutoListen = async () => {
  if (!isRealtimeMode.value) return;
  if (!isConnected.value) {
    pushSystemMessage("请先建立连接，再开启自由聆听。");
    return;
  }
  if (isAutoCommitInFlight.value) return;

  if (isAutoListeningRunning.value) {
    isAutoListeningEnabled.value = false;
    await stopRealtimeAutoListen({ flushFinal: true });
    return;
  }

  isAutoListeningEnabled.value = true;
  const started = await startRealtimeAutoListen({ resetSegment: true });
  if (!started) {
    isAutoListeningEnabled.value = false;
  }
};

// ===== 上行媒体策略同步 =====
// 设计原则：
// 1) 聊天室模式：始终音频轨可协商，但只在“按住说话"时激活；
// 2) 自由通话模式：默认持续音频上行；摄像头开启时上行音视频；
// 3) 不做自动重协商：连接中改媒体结构时只提示“挂断后重连生效"。
const syncPublishMediaConfig = () => {
  if (isRealtimeMode.value) {
    const useCameraStream = Boolean(isCameraEnabled.value && localCameraStream.value);
    const audioActive = Boolean(
      isConnected.value && isAutoListeningEnabled.value && !isAutoCommitInFlight.value
    );

    if (typeof window.configurePublishMedia === "function") {
      window.configurePublishMedia({
        audio: true,
        video: useCameraStream,
        audioActive,
      });
    }

    if (
      useCameraStream &&
      !isConnected.value &&
      typeof window.setPublishStream === "function"
    ) {
      window.setPublishStream(localCameraStream.value, {
        audio: true,
        video: true,
        audioActive,
      });
    } else if (!isConnected.value && typeof window.setPublishStream === "function") {
      // 在未连接态重置外部流引用，但保留 audio/video 发布意图；
      // 否则 clearPublishStream 会把 publishConfig 清零，导致首连时没有上行音频轨。
      window.setPublishStream(null, {
        audio: true,
        video: false,
        audioActive,
      });
    }
    return;
  }

  if (typeof window.configurePublishMedia === "function") {
    window.configurePublishMedia({
      audio: true,
      video: false,
      audioActive: false,
    });
  }
};

// ===== 摄像头采集控制 =====
const stopCameraCapture = () => {
  if (localCameraStream.value) {
    const stream = localCameraStream.value;
    const keepAudioDuringCall = Boolean(isConnected.value);

    // 通话中关闭摄像头时仅停止视频轨，避免把当前上行麦克风轨一起 stop。
    stream.getVideoTracks().forEach((track) => track.stop());

    if (keepAudioDuringCall) {
      const liveAudioTracks = stream
        .getAudioTracks()
        .filter((track) => track.readyState === "live");

      if (liveAudioTracks.length > 0) {
        const audioOnlyStream = new MediaStream();
        liveAudioTracks.forEach((track) => audioOnlyStream.addTrack(track));
        localCameraStream.value = audioOnlyStream;
      } else {
        stream.getAudioTracks().forEach((track) => track.stop());
        localCameraStream.value = null;
      }
    } else {
      stream.getAudioTracks().forEach((track) => track.stop());
      localCameraStream.value = null;
    }
  }

  isCameraEnabled.value = false;
  captureStatusText.value = "";
  syncPublishMediaConfig();
};

const startCameraCapture = async () => {
  if (!isRealtimeMode.value || isCameraEnabled.value || isCameraStarting.value)
    return;

  isCameraStarting.value = true;
  cameraStatusText.value = "正在开启...";
  cameraStatusLevel.value = "processing";

  try {
    // 已在通话中的情况下，摄像头重开只请求视频，避免重置当前麦克风上行轨。
    const requestAudioWithCamera = !isConnected.value;
    localCameraStream.value = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 960 },
        height: { ideal: 540 },
        facingMode: "user",
      },
      audio: requestAudioWithCamera
        ? {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          }
        : false,
    });

    isCameraEnabled.value = true;
    cameraStatusText.value = "摄像头已开启";
    cameraStatusLevel.value = "success";
    captureStatusText.value = "";
    syncPublishMediaConfig();

    if (isConnected.value) {
      pushSystemMessage("媒体结构已变更，当前连接需挂断后重新唤醒才能完全生效。");
    }
  } catch (err) {
    console.error(err);
    isCameraEnabled.value = false;
    cameraStatusText.value = isConnected.value
      ? "无法访问摄像头"
      : "无法访问摄像头/麦克风";
    cameraStatusLevel.value = "error";
    pushSystemMessage(
      isConnected.value
        ? "无法访问摄像头，请检查浏览器摄像头权限。"
        : "无法访问摄像头或麦克风，请检查浏览器权限。"
    );
  } finally {
    isCameraStarting.value = false;
  }
};

const toggleCameraCapture = () => {
  if (isCameraEnabled.value) {
    stopCameraCapture();
    cameraStatusText.value = "摄像头未开启";
    cameraStatusLevel.value = "idle";
    if (isConnected.value) {
      pushSystemMessage(
        "已关闭摄像头"
      );
    }
  } else {
    startCameraCapture();
  }
};

// ===== 轮询后端媒体状态 =====
const applyChatModeAsrState = (data) => {
  const webrtcAsrText = normalizeTranscriptText(data?.last_asr?.transcript || "");
  if (webrtcAsrText && webrtcAsrText !== latestUplinkAsrText) {
    latestUplinkAsrText = webrtcAsrText;
    asrStatusText.value = `上行语音识别：${webrtcAsrText}`;
    asrStatusLevel.value = "success";
  }
};

const applyRealtimeModeAsrState = async (data) => {
  const lastAsr = data?.last_asr || null;
  if (!lastAsr) return;

  const status = String(lastAsr.status || "");
  const source = String(lastAsr.source || "");
  const transcript = normalizeTranscriptText(lastAsr.transcript || "");

  if (status === "partial") {
    if (transcript && transcript !== freeTalkRuntime.partialText) {
      freeTalkRuntime.partialText = transcript;
      freeTalkRuntime.lastPartialAt = Date.now();
      latestUplinkAsrText = transcript;
      asrStatusText.value = "自由聆听中(已检测到语音)";
      asrStatusLevel.value = "recording";
    }
    await maybeCommitRealtimeFromPartial();
    return;
  }

  if (status === "recording" && isAutoListeningRunning.value) {
    asrStatusText.value = "自由通话聆听中，直接开口即可";
    asrStatusLevel.value = "recording";
    return;
  }

  if (status === "processing") {
    asrStatusText.value = "自由通话识别处理中...";
    asrStatusLevel.value = "processing";
    return;
  }

  if (status === "final" && !transcript) {
    if (source === "webrtc_stream_silence_filtered") {
      asrStatusText.value = "检测到静音片段，已自动忽略";
      asrStatusLevel.value = "warning";
      return;
    }
    if (source === "webrtc_stream_echo_filtered") {
      asrStatusText.value = "检测到数字人回声，已自动过滤";
      asrStatusLevel.value = "warning";
      return;
    }
  }

  if (status === "final" && transcript) {
    asrStatusText.value = `识别完成：${transcript}`;
    asrStatusLevel.value = "success";
  }
};

const fetchWebrtcMediaState = async () => {
  if (mediaStateFetchBusy) return;
  if (Date.now() < mediaStateBackoffUntilMs) return;

  // 🆕 修改后的轮询条件：
  // - realtime 模式：只要连接就持续轮询
  const shouldFetch = isConnected.value && isRealtimeMode.value;

  if (!shouldFetch) return;

  const sid = getCurrentSessionId();
  if (sid <= 0) return;

  mediaStateFetchBusy = true;
  try {
    const response = await fetch(
      buildApiUrl(`/webrtc_media_state?sessionid=${encodeURIComponent(String(sid))}`),
      {
        cache: "no-store",
      }
    );

    if (!response.ok) {
      mediaStateFailCount += 1;
      
      if (mediaStateFailCount >= 3) {
        mediaStateBackoffUntilMs = Date.now() + 5000;
      }
      return;
    }
    
    const payload = await response.json();
    const data = payload?.data || {};
    
    // 重置失败计数和退避时间
    mediaStateFailCount = 0;
    mediaStateBackoffUntilMs = 0;

    if (isRealtimeMode.value && isCameraEnabled.value) {
      const frameCount = Number(data?.video_frame_count || 0);
      const savedCount = Number(data?.video_dump_saved_count || 0);
      captureStatusText.value = `摄像头流已上行(累计帧 ${frameCount}, 已存样本 ${savedCount})`;
    }
    
    // 更新音频情绪
    const lastAsr = data?.last_asr || null;
    if (lastAsr && lastAsr.status === 'final') {
      const asrEmotion = String(lastAsr.emotion_label || '').trim();
      if (asrEmotion && asrEmotion !== audioEmotion.value) {
        audioEmotion.value = asrEmotion;
        audioEmotionTimestamp.value = Date.now();
      }
    }
    
    // 更新面部情绪
    const faceEmotionData = data?.face_emotion || null;
    if (faceEmotionData) {
      const newFaceEmotion = String(faceEmotionData.emotion || '中性/平静').trim();
      const newFaceTimestamp = Number(faceEmotionData.timestamp_ms || 0);
      
      if (newFaceEmotion && newFaceTimestamp > faceEmotionTimestamp.value) {
        faceEmotion.value = newFaceEmotion;
        faceEmotionTimestamp.value = newFaceTimestamp;
      }
    }
    

    if (isRealtimeMode.value) {
      await applyRealtimeModeAsrState(data);
    } else {
      applyChatModeAsrState(data);
    }
  } catch (err) {
    mediaStateFailCount += 1; 
    if (mediaStateFailCount >= 3) {
      mediaStateBackoffUntilMs = Date.now() + 5000;
    }
    
    console.warn("fetch webrtc media state failed:", err);
  } finally {
    mediaStateFetchBusy = false;
  }
};

const startMediaStatePolling = () => {
  if (mediaStatePollTimer) return;
  mediaStatePollTimer = setInterval(fetchWebrtcMediaState, 1050);
};

const stopMediaStatePolling = () => {
  if (!mediaStatePollTimer) return;
  clearInterval(mediaStatePollTimer);
  mediaStatePollTimer = null;
};

// ===== 视频背景同步 =====
const startBgSync = (videoEl) => {
  const canvas = document.getElementById("video-blur-bg");
  const ctx = canvas?.getContext("2d");
  if (!canvas || !ctx) return;

  const drawFrame = () => {
    if (!videoEl || videoEl.paused || videoEl.ended) return;
    if (canvas.width !== videoEl.videoWidth) canvas.width = videoEl.videoWidth;
    if (canvas.height !== videoEl.videoHeight) canvas.height = videoEl.videoHeight;
    ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
    bgSyncReqId = requestAnimationFrame(drawFrame);
  };

  bgSyncReqId = requestAnimationFrame(drawFrame);
};

const stopBgSync = () => {
  if (bgSyncReqId) {
    cancelAnimationFrame(bgSyncReqId);
    bgSyncReqId = null;
  }
};

const waitForSessionAndConnect = (retry = 0) => {
  const sid = getCurrentSessionId();
  if (sid > 0) {
    ensureChatStreamConnected();
  } else if (retry < 80) {
    setTimeout(() => waitForSessionAndConnect(retry + 1), 250);
  }
};

// ===== 呼叫控制 =====
const handleStart = () => {
  if (isConnected.value || isConnecting.value) return;

  isConnecting.value = true;
  hasRemoteVideoFrame.value = false;
  if (isRealtimeMode.value && isAutoListeningEnabled.value) {
    asrStatusText.value = "连接完成后将自动进入自由通话";
    asrStatusLevel.value = "processing";
  }

  syncPublishMediaConfig();

  const startPromise =
    typeof window.start === "function" ? window.start() : Promise.resolve(false);

  Promise.resolve(startPromise)
    .then((ok) => {
      if (ok) return;
      isConnecting.value = false;
      if (connectionCheckTimer) {
        clearInterval(connectionCheckTimer);
        connectionCheckTimer = null;
      }
      asrStatusText.value = "连接失败，请重试";
      asrStatusLevel.value = "error";
    })
    .catch((err) => {
      console.error("window.start rejected:", err);
      isConnecting.value = false;
      if (connectionCheckTimer) {
        clearInterval(connectionCheckTimer);
        connectionCheckTimer = null;
      }
      asrStatusText.value = "连接失败，请重试";
      asrStatusLevel.value = "error";
    });

  waitForSessionAndConnect();

  connectionCheckTimer = setInterval(() => {
    const video = document.getElementById("video");
    if (video && video.readyState >= 3 && video.videoWidth > 0) {
      isConnected.value = true;
      isConnecting.value = false;
      hasRemoteVideoFrame.value = true;
      startBgSync(video);
      clearInterval(connectionCheckTimer);
      connectionCheckTimer = null;
    }
  }, 1000);

  setTimeout(() => {
    if (connectionCheckTimer) {
      clearInterval(connectionCheckTimer);
      connectionCheckTimer = null;
    }
  }, 60000);
};

const handleStop = async () => {
  if (isAutoListeningRunning.value) {
    await stopRealtimeAutoListen({ flushFinal: false });
  }

  if (window.stop) window.stop();

  isConnected.value = false;
  isConnecting.value = false;
  hasRemoteVideoFrame.value = false;
  disconnectChatStream();
  stopMediaStatePolling();
  stopBgSync();
  stopCameraCapture();

  lastRecordingStopTime = 0;
  audioEmotion.value = "";
  audioEmotionTimestamp.value = 0;
  faceEmotion.value = "中性/平静";
  faceEmotionTimestamp.value = 0;

  if (connectionCheckTimer) {
    clearInterval(connectionCheckTimer);
    connectionCheckTimer = null;
  }

  asrStatusText.value = "已结束";
  asrStatusLevel.value = "idle";
  cameraStatusText.value = "摄像头未开启";
  cameraStatusLevel.value = "idle";

  syncPublishMediaConfig();
};

const showQuickActions = ref(false);

const handleClearHistory = () => {
  if (!canClearHistory.value) {
    pushSystemMessage("暂无对话记录可清空");
    return;
  }

  if (window.confirm("确定要清空对话历史吗？此操作不可恢复。")) {
    disconnectChatStream();
    resetConversationHistory("对话历史已清空，请开始新的对话。");

    if (isConnected.value) {
      ensureChatStreamConnected(true);
    }
  }
};

const handleExportChat = () => {
  if (!canExportHistory.value) {
    pushSystemMessage("暂无对话记录可导出");
    return;
  }

  const exportMessages = getExportableMessages().map((msg, index) => ({
    index: index + 1,
    role: msg.type,
    roleLabel: MESSAGE_ROLE_LABELS[msg.type] || msg.type,
    text: msg.text,
    createdAt: msg.createdAt || new Date().toISOString(),
  }));

  const exportPayload = {
    app: "EmoCompanion",
    mode: props.pageMode,
    exportedAt: new Date().toISOString(),
    messageCount: exportMessages.length,
    messages: exportMessages,
  };

  const dataStr = JSON.stringify(exportPayload, null, 2);
  const blob = new Blob([dataStr], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = formatHistoryExportFileName();
  link.click();
  URL.revokeObjectURL(url);

  pushSystemMessage("对话记录已导出到本地文件。");
};

// ===== 聊天窗口控制 =====
const showChatWindow = ref(true);
const chatWindowRef = ref(null);
const isDragging = ref(false);
const chatWindowStyle = ref({
  right: '24px',
  top: '104px',
  width: '410px',
  height: '62vh',
  maxHeight: '620px',
});

const dragOffset = reactive({ x: 0, y: 0 });

const toggleChatWindow = () => {
  showChatWindow.value = !showChatWindow.value;
};

const startDrag = (e) => {
  if (!chatWindowRef.value) return;

  isDragging.value = true;
  const rect = chatWindowRef.value.getBoundingClientRect();
  dragOffset.x = e.clientX - rect.left;
  dragOffset.y = e.clientY - rect.top;

  document.addEventListener('mousemove', onDrag);
  document.addEventListener('mouseup', stopDrag);
};

const onDrag = (e) => {
  if (!isDragging.value) return;

  const x = e.clientX - dragOffset.x;
  const y = e.clientY - dragOffset.y;

  chatWindowStyle.value = {
    ...chatWindowStyle.value,
    right: 'auto',
    left: `${x}px`,
    top: `${y}px`,
  };
};

const stopDrag = () => {
  isDragging.value = false;
  document.removeEventListener('mousemove', onDrag);
  document.removeEventListener('mouseup', stopDrag);
};

// ===== 监听：连接状态变化 =====
watch(
  [isConnected, isRealtimeMode],
  async ([connected, realtime]) => {
    if (connected && realtime && isAutoListeningEnabled.value) {
      await startRealtimeAutoListen({ resetSegment: true });
    }

    if (!connected || !realtime) {
      await stopRealtimeAutoListen({ flushFinal: false });
    }
  },
  { immediate: true }
);

// ===== 监听：轮询开关 =====
watch(
  [isConnected, isRealtimeMode, isCameraEnabled, isAutoListeningRunning],
  ([connected, realtime, camera, autoListening]) => {
    if (connected && realtime && (camera || autoListening)) {
      startMediaStatePolling();
    } else {
      stopMediaStatePolling();
    }
  },
  { immediate: true }
);

watch(
  messages,
  () => {
    schedulePersistConversationHistory();
  },
  { deep: true }
);

onMounted(() => {
  adjustTextareaHeight();
  syncPublishMediaConfig();
  scrollToBottom();

  originalOnWebRTCConnected = window.onWebRTCConnected;
  window.onWebRTCConnected = async () => {
    isConnected.value = true;
    isConnecting.value = false;
    ensureChatStreamConnected();
    syncPublishMediaConfig();

    if (isRealtimeMode.value && isAutoListeningEnabled.value) {
      await startRealtimeAutoListen({ resetSegment: true });
    }

    if (typeof originalOnWebRTCConnected === "function") {
      originalOnWebRTCConnected();
    }
  };

  originalOnWebRTCDisconnected = window.onWebRTCDisconnected;
  window.onWebRTCDisconnected = async () => {
    isConnected.value = false;
    isConnecting.value = false;
    hasRemoteVideoFrame.value = false;
    disconnectChatStream();
    stopMediaStatePolling();
    stopBgSync();
    await stopRealtimeAutoListen({ flushFinal: false });
    
    lastRecordingStopTime = 0;
    audioEmotion.value = "";
    audioEmotionTimestamp.value = 0;
    faceEmotion.value = "中性/平静";
    faceEmotionTimestamp.value = 0;
    
    syncPublishMediaConfig();

    if (typeof originalOnWebRTCDisconnected === "function") {
      originalOnWebRTCDisconnected();
    }
  };
});

onUnmounted(() => {
  flushConversationHistoryPersistence();
  void handleStop();
  stopDrag();
  window.onWebRTCConnected = originalOnWebRTCConnected;
  window.onWebRTCDisconnected = originalOnWebRTCDisconnected;
});
</script>

<style scoped>
/* 全局变量 */
.digital-companion {
  --primary: #8a2be2;
  --primary-deep: #5e1c9e;
  --glass-bg: rgba(22, 24, 33, 0.75);
  --glass-border: rgba(255, 255, 255, 0.12);
  --bg-gradient-start: #0f0c29;
  --bg-gradient-mid: #302b63;
  --bg-gradient-end: #24243e;
  --text-primary: #f1f5f9;
  --text-secondary: #cbd5e1;

  width: 100%;
  height: 100%;
  min-height: 0;
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, var(--bg-gradient-start) 0%, var(--bg-gradient-mid) 50%, var(--bg-gradient-end) 100%);
  transition: background 0.4s ease, color 0.4s ease;
}

/* 日间主题 */
.digital-companion.theme-day {
  --primary: #3b82f6;
  --primary-deep: #2563eb;
  --glass-bg: rgba(255, 255, 255, 0.85);
  --glass-border: rgba(59, 130, 246, 0.2);
  --bg-gradient-start: #f0f9ff;
  --bg-gradient-mid: #e0f2fe;
  --bg-gradient-end: #bae6fd;
  --text-primary: #1e293b;
  --text-secondary: #64748b;
}

/* 全屏视频容器 */
.video-container {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.stage-aura {
  position: absolute;
  inset: -35%;
  z-index: 0;
  background:
    radial-gradient(circle at 20% 30%, rgba(138, 43, 226, 0.35), transparent 45%),
    radial-gradient(circle at 82% 68%, rgba(0, 212, 255, 0.2), transparent 45%);
  filter: blur(50px);
  animation: aura-drift 12s ease-in-out infinite alternate;
}

.theme-day .stage-aura {
  background:
    radial-gradient(circle at 30% 40%, rgba(59, 130, 246, 0.25), transparent 50%),
    radial-gradient(circle at 75% 65%, rgba(14, 165, 233, 0.2), transparent 50%);
  filter: blur(60px);
}

.video-blur-bg {
  position: absolute;
  top: -10%;
  left: -10%;
  width: 120%;
  height: 120%;
  z-index: 1;
  filter: blur(90px) saturate(1.4) brightness(0.8);
  transition: opacity 0.8s ease;
}

video {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

audio {
  display: none;
}

.video-placeholder {
  position: absolute;
  inset: 0;
  z-index: 8;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 24px 24px clamp(112px, 18vh, 168px);
  background: radial-gradient(circle at 55% 15%, #181524 0%, #0c0b11 65%, #050508 100%);
}

.theme-day .video-placeholder {
  background: radial-gradient(circle at 55% 15%, #f8fafc 0%, #f1f5f9 65%, #e2e8f0 100%);
}

.placeholder-logo {
  position: relative;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(138, 43, 226, 0.2), rgba(0, 212, 255, 0.15));
  color: #d8b4fe;
  font-size: 48px;
  margin-bottom: 20px;
  box-shadow: 0 0 0 1px rgba(138, 43, 226, 0.4), 0 0 60px rgba(138, 43, 226, 0.3);
}

.theme-day .placeholder-logo {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(14, 165, 233, 0.15));
  color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.4), 0 0 80px rgba(59, 130, 246, 0.25);
}

.logo-ring {
  position: absolute;
  inset: -20px;
  border-radius: 999px;
  border: 1px solid rgba(138, 43, 226, 0.42);
  opacity: 0;
}

.loading .logo-ring {
  animation: ring-wave 2.6s infinite;
}

.loading .ring-b {
  animation-delay: 0.8s;
}

.loading .ring-c {
  animation-delay: 1.6s;
}

.placeholder-title {
  margin: 0;
  color: #f3e8ff;
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.theme-day .placeholder-title {
  color: var(--text-primary);
}

.placeholder-subtitle {
  margin: 8px 0 0;
  color: rgba(216, 180, 254, 0.8);
  font-size: 0.9rem;
}

.theme-day .placeholder-subtitle {
  color: var(--text-secondary);
}

/* 中间唤醒按钮 */
.center-control {
  position: absolute;
  top: 85%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 20;
}

.btn-wake,
.btn-stop {
  border: none;
  border-radius: 50px;
  padding: 14px 28px;
  font-size: 1rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.btn-wake {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.9), rgba(126, 34, 206, 0.9));
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.theme-day .btn-wake {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.95), rgba(126, 34, 206, 0.95));
  box-shadow: 0 8px 32px rgba(126, 34, 206, 0.3);
}

.btn-wake:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 40px rgba(126, 34, 206, 0.5);
}

.btn-stop {
  background: linear-gradient(135deg, rgba(244, 63, 94, 0.9), rgba(190, 18, 60, 0.9));
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.theme-day .btn-stop {
  background: linear-gradient(135deg, rgba(244, 63, 94, 0.95), rgba(190, 18, 60, 0.95));
  box-shadow: 0 8px 32px rgba(225, 29, 72, 0.3);
}

.btn-stop:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 40px rgba(225, 29, 72, 0.5);
}

.btn-wake i,
.btn-stop i {
  font-size: 1.15rem;
}

/* 悬浮控制按钮组 */
.floating-controls {
  position: absolute;
  bottom: max(18px, env(safe-area-inset-bottom));
  left: 50%;
  transform: translateX(-50%);
  z-index: 30;
  display: flex;
  gap: 10px;
  padding: 8px 12px;
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--glass-border);
  border-radius: 60px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.theme-day .floating-controls {
  box-shadow: 0 8px 32px rgba(59, 130, 246, 0.2);
}

.control-btn {
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: rgba(45, 48, 64, 0.8);
  color: #cbd5e1;
  font-size: 1.1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 2px solid transparent;
}

.theme-day .control-btn {
  background: rgba(255, 255, 255, 0.95);
  color: #64748b;
  border: 2px solid rgba(226, 232, 240, 0.8);
}

.control-btn:hover:not(:disabled) {
  background: rgba(138, 43, 226, 0.3);
  border-color: rgba(138, 43, 226, 0.5);
  color: #d8b4fe;
  transform: translateY(-3px) scale(1.05);
}

.theme-day .control-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.15);
  border-color: rgba(59, 130, 246, 0.4);
  color: var(--primary);
}

.control-btn.active {
  background: linear-gradient(135deg, #10b981, #059669);
  color: #fff;
  border-color: transparent;
  animation: pulse-glow 2s infinite;
}

.control-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 聊天记录悬浮窗 */
.chat-window {
  position: fixed;
  z-index: 40;
  background: rgba(22, 24, 33, 0.95);
  backdrop-filter: blur(30px);
  -webkit-backdrop-filter: blur(30px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  max-width: 90vw;
  max-height: 85vh;
  min-width: 380px;
  min-height: 450px;
}

.chat-window.theme-light {
  background: rgba(255, 255, 255, 0.95);
  border: 2px solid rgba(59, 130, 246, 0.3);
  box-shadow: 0 20px 60px rgba(59, 130, 246, 0.25);
}

.chat-header {
  padding: 16px 20px;
  background: rgba(30, 31, 46, 0.7);
  border-bottom: 1px solid rgba(138, 43, 226, 0.25);
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: move;
  user-select: none;
}

.chat-window.theme-light .chat-header {
  background: rgba(239, 246, 255, 0.9);
  border-bottom: 2px solid rgba(59, 130, 246, 0.2);
}

.chat-title {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #e2e8f0;
  font-size: 1rem;
  font-weight: 700;
}

.chat-window.theme-light .chat-title {
  color: var(--text-primary);
}

.chat-title i {
  font-size: 1.2rem;
  color: #c084fc;
}

.chat-window.theme-light .chat-title i {
  color: var(--primary);
}

.chat-actions {
  display: flex;
  gap: 8px;
}

.header-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 10px;
  background: rgba(45, 48, 64, 0.7);
  color: #cbd5e1;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.chat-window.theme-light .header-btn {
  background: rgba(226, 232, 240, 0.9);
  color: #64748b;
  border: 1px solid rgba(203, 213, 225, 0.5);
}

.header-btn:hover:not(:disabled) {
  background: rgba(138, 43, 226, 0.4);
  color: #d8b4fe;
  transform: scale(1.1);
}

.chat-window.theme-light .header-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.15);
  color: var(--primary);
  border-color: var(--primary);
}

.header-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.chat-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: rgba(15, 15, 20, 0.4);
}

.chat-window.theme-light .chat-body {
  background: rgba(248, 250, 252, 0.6);
}

.call-status {
  position: absolute;
  top: 20px;
  left: 20px;
  right: 20px;
  z-index: 5;
  color: var(--text-secondary);
  font-size: 0.85rem;
  pointer-events: none;
}

.chat-input {
  display: flex;
  flex-shrink: 0;
  gap: 10px;
  padding: 12px;
  border-top: 1px solid rgba(138, 43, 226, 0.25);
}

.chat-input textarea {
  flex: 1;
  min-width: 0;
  max-height: 120px;
  resize: none;
  padding: 10px;
  border: 1px solid rgba(138, 43, 226, 0.35);
  border-radius: 10px;
  background: transparent;
  color: inherit;
}

.chat-input button {
  align-self: flex-end;
  border: 0;
  border-radius: 10px;
  padding: 10px 14px;
  background: var(--primary);
  color: white;
}

.chat-input :disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 动画 */
@keyframes ring-wave {
  0% {
    transform: scale(0.82);
    opacity: 0;
  }
  42% {
    opacity: 1;
  }
  100% {
    transform: scale(1.36);
    opacity: 0;
  }
}

@keyframes aura-drift {
  0% {
    transform: translate3d(-2%, -1%, 0);
  }
  100% {
    transform: translate3d(2%, 2%, 0);
  }
}

@keyframes pulse-glow {
  0%, 100% {
    box-shadow: 0 0 20px rgba(16, 185, 129, 0.4);
  }
  50% {
    box-shadow: 0 0 30px rgba(16, 185, 129, 0.7);
  }
}

/* 响应式 */
@media (max-width: 768px) {
  .btn-wake,
  .btn-stop {
    padding: 13px 24px;
    font-size: 0.95rem;
  }

  .btn-wake i,
  .btn-stop i {
    font-size: 1.05rem;
  }

  .floating-controls {
    bottom: max(12px, env(safe-area-inset-bottom));
    padding: 7px 10px;
    gap: 8px;
  }

  .control-btn {
    width: 40px;
    height: 40px;
    font-size: 1rem;
  }

  .chat-window {
    right: 10px !important;
    left: 10px !important;
    top: 60px !important;
    width: calc(100vw - 20px) !important;
    height: calc(100vh - 140px) !important;
    max-height: none !important;
    min-width: auto;
  }
}

@media (max-width: 480px) {
  .placeholder-logo {
    width: 100px;
    height: 100px;
    font-size: 40px;
  }

  .placeholder-title {
    font-size: 1rem;
  }

  .placeholder-subtitle {
    font-size: 0.85rem;
  }

  .btn-wake,
  .btn-stop {
    padding: 14px 28px;
    font-size: 0.95rem;
  }

  .floating-controls {
    padding: 8px 12px;
    gap: 10px;
  }

  .control-btn {
    width: 44px;
    height: 44px;
    font-size: 1.1rem;
  }
}
</style>
