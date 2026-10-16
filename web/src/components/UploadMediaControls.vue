<template>
  <div
    v-if="hasSource"
    class="upload-media-controls"
    :class="{ compact, collapsed: collapsible && isCollapsed }"
  >
    <div class="media-summary">
      <span class="media-kind">{{ kindLabel }}</span>
      <span class="media-name" :title="displayName">{{ displayName }}</span>
      <span class="media-time">{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span>
      <div class="summary-actions">
        <button
          type="button"
          class="summary-icon-button"
          :disabled="!hasPlayableMedia"
          @click="togglePlayback"
          :aria-label="isPlaying ? '暂停媒体' : '播放媒体'"
        >
          <i :class="['bi', isPlaying ? 'bi-pause-fill' : 'bi-play-fill']"></i>
        </button>
        <button
          v-if="collapsible"
          type="button"
          class="summary-icon-button"
          @click="toggleCollapsed"
          :aria-label="isCollapsed ? '展开媒体控制' : '收起媒体控制'"
        >
          <i :class="['bi', isCollapsed ? 'bi-chevron-up' : 'bi-chevron-down']"></i>
        </button>
      </div>
    </div>

    <Transition name="control-panel-slide">
      <div v-show="!(collapsible && isCollapsed)" class="control-panel">
        <button
          type="button"
          class="progress-track"
          :disabled="!duration"
          @click="seekTo"
          :aria-label="`${kindLabel}播放进度`"
        >
          <span class="progress-fill" :style="{ width: `${progressPercent}%` }"></span>
        </button>

        <div class="control-row">
          <button
            type="button"
            class="control-button primary"
            :disabled="!hasPlayableMedia"
            @click="togglePlayback"
          >
            <i :class="['bi', isPlaying ? 'bi-pause-circle-fill' : 'bi-play-circle-fill']"></i>
            {{ isPlaying ? '暂停' : '播放' }}
          </button>
          <button
            type="button"
            class="control-button"
            :disabled="!canStop"
            @click="stopPlayback"
          >
            <i class="bi bi-stop-circle"></i>
            停止
          </button>
          <span class="control-hint">{{ statusText }}</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch, watchEffect } from 'vue';

const props = defineProps({
  source: {
    type: String,
    default: '',
  },
  fileName: {
    type: String,
    default: '',
  },
  kind: {
    type: String,
    default: 'audio',
  },
  mediaRefs: {
    type: Array,
    default: () => [],
  },
  compact: {
    type: Boolean,
    default: false,
  },
  collapsible: {
    type: Boolean,
    default: true,
  },
  defaultCollapsed: {
    type: Boolean,
    default: false,
  },
});

const isPlaying = ref(false);
const currentTime = ref(0);
const duration = ref(0);
const isCollapsed = ref(Boolean(props.defaultCollapsed));

let detachListeners = [];

const hasSource = computed(() => Boolean(props.source));
const kindLabel = computed(() => (props.kind === 'video' ? '视频' : '音频'));
const displayName = computed(() => props.fileName || `已上传${kindLabel.value}`);
const progressPercent = computed(() => {
  if (!duration.value) return 0;
  return Math.min(100, Math.max(0, (currentTime.value / duration.value) * 100));
});
const statusText = computed(() => {
  if (!hasPlayableMedia.value) return '媒体未就绪';
  if (isPlaying.value) return '播放中';
  if (currentTime.value > 0) return '已暂停';
  return '待播放';
});
const canStop = computed(() => hasPlayableMedia.value && (isPlaying.value || currentTime.value > 0));

const toggleCollapsed = () => {
  if (!props.collapsible) return;
  isCollapsed.value = !isCollapsed.value;
};

const mediaElements = computed(() => (
  Array.isArray(props.mediaRefs) ? props.mediaRefs : []
).map((entry) => {
  if (entry && typeof entry === 'object' && 'value' in entry) {
    return entry.value;
  }
  return entry;
}).filter((element) => element && typeof element.play === 'function'));

const primaryMediaElement = computed(() => mediaElements.value[0] || null);
const hasPlayableMedia = computed(() => hasSource.value && !!primaryMediaElement.value);

const cleanupListeners = () => {
  detachListeners.forEach((dispose) => dispose());
  detachListeners = [];
};

const syncState = () => {
  const media = primaryMediaElement.value;
  if (!media) {
    isPlaying.value = false;
    currentTime.value = 0;
    duration.value = 0;
    return;
  }

  isPlaying.value = !media.paused && !media.ended;
  currentTime.value = Number.isFinite(media.currentTime) ? media.currentTime : 0;
  duration.value = Number.isFinite(media.duration) ? media.duration : 0;
};

const bindListeners = () => {
  cleanupListeners();

  mediaElements.value.forEach((element) => {
    const handler = () => syncState();
    ['loadedmetadata', 'durationchange', 'timeupdate', 'play', 'pause', 'ended', 'emptied'].forEach((eventName) => {
      element.addEventListener(eventName, handler);
      detachListeners.push(() => element.removeEventListener(eventName, handler));
    });
  });

  syncState();
};

const syncTargetsCurrentTime = (timeValue) => {
  mediaElements.value.forEach((element) => {
    try {
      element.currentTime = timeValue;
    } catch (_) {
      // 部分浏览器在 metadata 未加载时会拒绝设置 currentTime，这里静默忽略即可。
    }
  });
};

const playAll = async () => {
  if (!hasPlayableMedia.value) return;

  const primary = primaryMediaElement.value;
  const baseTime = Number.isFinite(primary?.currentTime) ? primary.currentTime : 0;
  syncTargetsCurrentTime(baseTime);

  await Promise.all(
    mediaElements.value.map((element) => element.play().catch(() => {}))
  );

  syncState();
};

const pauseAll = () => {
  mediaElements.value.forEach((element) => {
    element.pause?.();
  });
  syncState();
};

const stopPlayback = () => {
  pauseAll();
  syncTargetsCurrentTime(0);
  syncState();
};

const togglePlayback = async () => {
  if (isPlaying.value) {
    pauseAll();
    return;
  }

  await playAll();
};

const seekTo = (event) => {
  if (!duration.value) return;

  const rect = event.currentTarget.getBoundingClientRect();
  const offsetX = event.clientX - rect.left;
  const ratio = rect.width > 0 ? offsetX / rect.width : 0;
  const targetTime = Math.min(duration.value, Math.max(0, duration.value * ratio));

  syncTargetsCurrentTime(targetTime);
  currentTime.value = targetTime;
};

const formatTime = (secondsValue) => {
  if (!Number.isFinite(secondsValue) || secondsValue <= 0) {
    return '00:00';
  }

  const totalSeconds = Math.floor(secondsValue);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};

watchEffect((onCleanup) => {
  void props.source;
  void mediaElements.value;
  bindListeners();
  onCleanup(() => cleanupListeners());
});

watch(
  () => props.source,
  () => {
    isCollapsed.value = Boolean(props.defaultCollapsed);
  }
);

onBeforeUnmount(() => {
  cleanupListeners();
});
</script>

<style scoped>
.upload-media-controls {
  margin-top: 10px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(10, 8, 18, 0.56);
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(14px);
}

.upload-media-controls.compact {
  margin-top: 0;
  padding: 10px 12px;
  background: linear-gradient(180deg, rgba(10, 8, 18, 0.42), rgba(10, 8, 18, 0.68));
  border-color: rgba(255, 255, 255, 0.08);
  box-shadow: 0 14px 30px rgba(0, 0, 0, 0.22);
}

.upload-media-controls.collapsed {
  padding-bottom: 10px;
}

.media-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  margin-bottom: 10px;
}

.media-kind {
  flex-shrink: 0;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 107, 129, 0.1);
  color: #f7b5c1;
  font-size: 0.72rem;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 24px;
  line-height: 1;
}

.media-name {
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  min-height: 24px;
  color: #f8fafc;
  font-size: 0.84rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.2;
}

.media-time {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  min-height: 24px;
  color: #94a3b8;
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.summary-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.summary-icon-button {
  width: 28px;
  height: 28px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  color: #dbe5f0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.summary-icon-button:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.14);
}

.summary-icon-button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.control-panel {
  overflow: hidden;
}

/* 🎨 丝滑的折叠/展开过渡动画 */
.control-panel-slide-enter-active,
.control-panel-slide-leave-active {
  transition: all 0.6s cubic-bezier(0.4, 0.0, 0.2, 1);
  transform-origin: top;
}

.control-panel-slide-enter-from,
.control-panel-slide-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(-10px);
  margin-top: 0;
}

.control-panel-slide-enter-to,
.control-panel-slide-leave-from {
  max-height: 200px;
  opacity: 1;
  transform: translateY(0);
}


.progress-track {
  width: 100%;
  height: 8px;
  padding: 0;
  border: none;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.06);
  cursor: pointer;
}

.progress-track:disabled {
  cursor: default;
  opacity: 0.55;
}

.progress-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, rgba(255, 107, 129, 0.9), rgba(168, 85, 247, 0.8));
}

.control-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}

.control-button {
  flex-shrink: 0;
  min-width: 88px;
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: #e2e8f0;
  font-size: 0.83rem;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.2s ease;
}

.control-button:hover:not(:disabled) {
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.08);
}

.control-button:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.control-button.primary {
  border-color: rgba(255, 107, 129, 0.18);
  background: rgba(255, 107, 129, 0.08);
  color: #ffe4ea;
}

.control-hint {
  min-width: 0;
  color: #94a3b8;
  font-size: 0.8rem;
}

.upload-media-controls.compact .media-summary {
  margin-bottom: 8px;
}

.upload-media-controls.compact .media-name {
  font-size: 0.78rem;
}

.upload-media-controls.compact .media-time {
  font-size: 0.74rem;
}

.upload-media-controls.compact .control-row {
  gap: 8px;
  margin-top: 10px;
}

.upload-media-controls.compact .control-button {
  min-width: 70px;
  padding: 6px 10px;
  font-size: 0.78rem;
}

.upload-media-controls.compact .control-hint {
  font-size: 0.75rem;
}

.upload-media-controls.compact .summary-icon-button {
  width: 24px;
  height: 24px;
  font-size: 0.78rem;
}

@media (max-width: 768px) {
  .media-summary,
  .control-row {
    flex-wrap: wrap;
  }

  .summary-actions {
    width: 100%;
    justify-content: flex-end;
    margin-left: 0;
  }

  .control-hint {
    width: 100%;
  }

  .upload-media-controls.compact {
    padding: 8px 10px;
  }
}
</style>
