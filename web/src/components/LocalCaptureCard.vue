<template>
  <!-- 摄像头未开启时，只显示一个开启按钮 -->
  <button
    v-if="!isCameraEnabled"
    type="button"
    class="camera-toggle-simple"
    :disabled="isCameraStarting"
    @click="$emit('toggle-camera')"
  >
    <i class="bi bi-camera-video"></i>
    <span>{{ isCameraStarting ? '开启中...' : '开启摄像头' }}</span>
  </button>

  <!-- 摄像头已开启时，显示完整的可拖动卡片 -->
  <div
    v-else
    ref="cardRef"
    class="local-camera-card"
    :class="{ collapsed: isCollapsed, dragging: dragState.dragging, resizing: resizeState.resizing }"
    :style="cardStyle"
  >
    <!-- 顶部工具栏 -->
    <div class="local-camera-top" @pointerdown="onDragStart">
      <div class="camera-title-wrap">
        <span class="camera-title">摄像头</span>
      </div>
      <div class="camera-actions">
        <button type="button" class="btn-collapse" @click.stop="toggleCollapsed">
          <i :class="['bi', isCollapsed ? 'bi-arrows-angle-expand' : 'bi-arrows-angle-contract']"></i>
        </button>
        <button
          type="button"
          class="btn-camera-toggle"
          @click.stop="$emit('toggle-camera')"
        >
          <i class="bi bi-camera-video-fill"></i>
          关闭
        </button>
      </div>
    </div>

    <!-- 预览区 -->
    <div class="local-camera-preview" v-show="!isCollapsed">
      <video ref="previewRef" autoplay muted playsinline></video>
    </div>

    <!-- 调整大小手柄 -->
    <div 
      v-show="!isCollapsed" 
      class="resize-handle resize-handle-br"
      @pointerdown="onResizeStart"
    >
      <i class="bi bi-arrows-angle-expand"></i>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch, nextTick, onBeforeUnmount, onMounted } from 'vue';

const props = defineProps({
  isCameraEnabled: {
    type: Boolean,
    required: true,
  },
  isCameraStarting: {
    type: Boolean,
    required: true,
  },
  localStream: {
    type: Object,
    default: null,
  },
  captureStatusText: {
    type: String,
    default: '',
  },
});

defineEmits(['toggle-camera']);

const previewRef = ref(null);
const cardRef = ref(null);

const EDGE_PADDING_PX = 12;
const RIGHT_PADDING_PX = 24;
const TOP_PADDING_PX = 20;
const MIN_WIDTH = 200;
const MAX_WIDTH = 600;
const DEFAULT_PREVIEW_ASPECT_RATIO = 4 / 3;
const FALLBACK_CHROME_HEIGHT = 56;

const isCollapsed = ref(false);
const hasInitializedPosition = ref(false);
const position = ref({ x: EDGE_PADDING_PX, y: TOP_PADDING_PX });
const cardWidth = ref(280);
const previewAspectRatio = ref(DEFAULT_PREVIEW_ASPECT_RATIO);

const dragState = reactive({
  dragging: false,
  pointerStartX: 0,
  pointerStartY: 0,
  originX: EDGE_PADDING_PX,
  originY: TOP_PADDING_PX,
});

const resizeState = reactive({
  resizing: false,
  pointerStartX: 0,
  pointerStartY: 0,
  originWidth: 280,
});

const cardStyle = computed(() => ({
  left: `${position.value.x}px`,
  top: `${position.value.y}px`,
  width: `${cardWidth.value}px`,
  '--preview-aspect-ratio': `${previewAspectRatio.value}`,
}));

const normalizeAspectRatio = (width, height) => {
  if (
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  ) {
    return DEFAULT_PREVIEW_ASPECT_RATIO;
  }

  return width / height;
};

const getParentMetrics = () => {
  const cardEl = cardRef.value;
  if (!cardEl) return null;

  const parentEl = cardEl.offsetParent || cardEl.parentElement;
  if (!parentEl || typeof parentEl.getBoundingClientRect !== 'function') {
    return null;
  }

  return {
    parentEl,
    parentRect: parentEl.getBoundingClientRect(),
  };
};

const getDragBounds = () => {
  const metrics = getParentMetrics();
  const cardEl = cardRef.value;
  if (!metrics || !cardEl) return null;

  const { parentRect } = metrics;
  const cardRect = cardEl.getBoundingClientRect();

  const maxX = Math.max(EDGE_PADDING_PX, parentRect.width - cardRect.width - EDGE_PADDING_PX);
  const maxY = Math.max(EDGE_PADDING_PX, parentRect.height - cardRect.height - EDGE_PADDING_PX);
  const rightAlignedX = Math.max(
    EDGE_PADDING_PX,
    parentRect.width - cardRect.width - RIGHT_PADDING_PX
  );

  return {
    maxX,
    maxY,
    rightAlignedX,
    parentWidth: parentRect.width,
    parentHeight: parentRect.height,
  };
};

const clampPosition = (x, y) => {
  const bounds = getDragBounds();
  if (!bounds) {
    return { x, y };
  }

  return {
    x: Math.min(Math.max(EDGE_PADDING_PX, x), bounds.maxX),
    y: Math.min(Math.max(EDGE_PADDING_PX, y), bounds.maxY),
  };
};

const getCardChromeHeight = () => {
  const cardEl = cardRef.value;
  if (!cardEl) return FALLBACK_CHROME_HEIGHT;

  const previewEl = cardEl.querySelector('.local-camera-preview');
  if (previewEl instanceof HTMLElement) {
    const cardHeight = cardEl.getBoundingClientRect().height;
    const previewHeight = previewEl.getBoundingClientRect().height;
    if (cardHeight > previewHeight && previewHeight > 0) {
      return cardHeight - previewHeight;
    }
  }

  const headerEl = cardEl.querySelector('.local-camera-top');
  if (headerEl instanceof HTMLElement) {
    return headerEl.getBoundingClientRect().height;
  }

  return FALLBACK_CHROME_HEIGHT;
};

const getWidthBounds = () => {
  const metrics = getParentMetrics();
  if (!metrics) return null;

  const { parentRect } = metrics;
  const maxWidthFromViewport = parentRect.width - EDGE_PADDING_PX * 2;
  const maxWidthFromPosition = parentRect.width - position.value.x - EDGE_PADDING_PX;
  const maxWidthFromHeight = isCollapsed.value
    ? MAX_WIDTH
    : (parentRect.height -
        position.value.y -
        EDGE_PADDING_PX -
        getCardChromeHeight()) *
      previewAspectRatio.value;

  const maxWidth = Math.max(
    1,
    Math.min(MAX_WIDTH, maxWidthFromViewport, maxWidthFromPosition, maxWidthFromHeight)
  );

  return {
    minWidth: Math.min(MIN_WIDTH, maxWidth),
    maxWidth,
  };
};

const clampWidth = (width) => {
  const bounds = getWidthBounds();
  if (!bounds) {
    return Math.min(Math.max(MIN_WIDTH, width), MAX_WIDTH);
  }

  return Math.min(Math.max(bounds.minWidth, width), bounds.maxWidth);
};

const syncCardWithinBounds = () => {
  cardWidth.value = clampWidth(cardWidth.value);
  nextTick(() => {
    position.value = clampPosition(position.value.x, position.value.y);
  });
};

const resetPositionToTopRight = () => {
  const bounds = getDragBounds();
  if (!bounds) return;
  position.value = clampPosition(bounds.rightAlignedX, TOP_PADDING_PX);
};

const ensureInitialPosition = () => {
  if (hasInitializedPosition.value) return;
  resetPositionToTopRight();
  hasInitializedPosition.value = true;
};

// 拖动逻辑
const onDragMove = (event) => {
  if (!dragState.dragging) return;

  const deltaX = event.clientX - dragState.pointerStartX;
  const deltaY = event.clientY - dragState.pointerStartY;
  const next = clampPosition(dragState.originX + deltaX, dragState.originY + deltaY);
  position.value = next;
};

const stopDragging = () => {
  if (!dragState.dragging) return;

  dragState.dragging = false;
  window.removeEventListener('pointermove', onDragMove);
  window.removeEventListener('pointerup', stopDragging);
  window.removeEventListener('pointercancel', stopDragging);
};

const onDragStart = (event) => {
  if (typeof event.button === 'number' && event.button !== 0) {
    return;
  }
  if (event.target instanceof Element && event.target.closest('button')) {
    return;
  }

  ensureInitialPosition();

  dragState.dragging = true;
  dragState.pointerStartX = event.clientX;
  dragState.pointerStartY = event.clientY;
  dragState.originX = position.value.x;
  dragState.originY = position.value.y;

  window.addEventListener('pointermove', onDragMove);
  window.addEventListener('pointerup', stopDragging);
  window.addEventListener('pointercancel', stopDragging);

  event.preventDefault();
};

// 调整大小逻辑
const onResizeMove = (event) => {
  if (!resizeState.resizing) return;

  const deltaX = event.clientX - resizeState.pointerStartX;
  const deltaY = event.clientY - resizeState.pointerStartY;

  const widthFromHorizontal = resizeState.originWidth + deltaX;
  const widthFromVertical =
    resizeState.originWidth + deltaY * previewAspectRatio.value;
  const widthDelta =
    Math.abs(deltaX) >= Math.abs(deltaY * previewAspectRatio.value)
      ? widthFromHorizontal
      : widthFromVertical;

  cardWidth.value = clampWidth(widthDelta);
};

const stopResizing = () => {
  if (!resizeState.resizing) return;

  resizeState.resizing = false;
  window.removeEventListener('pointermove', onResizeMove);
  window.removeEventListener('pointerup', stopResizing);
  window.removeEventListener('pointercancel', stopResizing);
  nextTick(() => {
    position.value = clampPosition(position.value.x, position.value.y);
  });
};

const onResizeStart = (event) => {
  if (typeof event.button === 'number' && event.button !== 0) {
    return;
  }

  resizeState.resizing = true;
  resizeState.pointerStartX = event.clientX;
  resizeState.pointerStartY = event.clientY;
  resizeState.originWidth = cardWidth.value;

  window.addEventListener('pointermove', onResizeMove);
  window.addEventListener('pointerup', stopResizing);
  window.addEventListener('pointercancel', stopResizing);

  event.preventDefault();
  event.stopPropagation();
};

const toggleCollapsed = () => {
  isCollapsed.value = !isCollapsed.value;
  nextTick(() => {
    cardWidth.value = clampWidth(cardWidth.value);
    position.value = clampPosition(position.value.x, position.value.y);
  });
};

const handleWindowResize = () => {
  if (!hasInitializedPosition.value) {
    ensureInitialPosition();
    return;
  }
  syncCardWithinBounds();
};

const syncPreviewMetrics = () => {
  const videoEl = previewRef.value;
  if (!videoEl) return;

  previewAspectRatio.value = normalizeAspectRatio(
    videoEl.videoWidth,
    videoEl.videoHeight
  );
  syncCardWithinBounds();
};

const unbindPreviewEvents = () => {
  const videoEl = previewRef.value;
  if (!videoEl) return;

  videoEl.removeEventListener('loadedmetadata', syncPreviewMetrics);
  videoEl.removeEventListener('resize', syncPreviewMetrics);
};

const bindPreviewStream = () => {
  nextTick(() => {
    const videoEl = previewRef.value;
    if (!videoEl) return;

    unbindPreviewEvents();
    videoEl.srcObject = props.localStream || null;

    if (props.localStream) {
      videoEl.addEventListener('loadedmetadata', syncPreviewMetrics);
      videoEl.addEventListener('resize', syncPreviewMetrics);

      if (videoEl.readyState >= 1) {
        syncPreviewMetrics();
      }

      videoEl.play().catch(() => {});
    }
  });
};

watch(
  () => props.localStream,
  () => {
    bindPreviewStream();
  },
  { immediate: true }
);

watch(
  () => props.isCameraEnabled,
  (enabled) => {
    if (!enabled) {
      stopDragging();
      stopResizing();
      return;
    }

    nextTick(() => {
      ensureInitialPosition();
      bindPreviewStream();
      syncCardWithinBounds();
    });
  }
);

watch(
  () => isCollapsed.value,
  () => {
    nextTick(() => {
      cardWidth.value = clampWidth(cardWidth.value);
      position.value = clampPosition(position.value.x, position.value.y);
    });
  }
);

onMounted(() => {
  nextTick(() => {
    if (props.isCameraEnabled) {
      ensureInitialPosition();
      syncCardWithinBounds();
    }
  });
  window.addEventListener('resize', handleWindowResize);
});

onBeforeUnmount(() => {
  stopDragging();
  stopResizing();
  unbindPreviewEvents();
  window.removeEventListener('resize', handleWindowResize);
  if (previewRef.value) {
    previewRef.value.srcObject = null;
  }
});
</script>

<style scoped>
/* 简单的开启按钮 */
.camera-toggle-simple {
  position: absolute;
  top: 20px;
  right: 20px;
  z-index: 22;
  border: none;
  border-radius: 10px;
  padding: 6px 14px;
  font-size: 0.72rem;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #ff6b81 0%, #ec4899 100%);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  box-shadow: 0 3px 10px rgba(255, 107, 129, 0.4);
  display: flex;
  align-items: center;
  gap: 6px;
}

:global([data-theme="day"] .camera-toggle-simple) {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  box-shadow: 0 3px 10px rgba(59, 130, 246, 0.4);
}

.camera-toggle-simple:hover:not(:disabled) {
  transform: translateY(-1px) scale(1.02);
  box-shadow: 0 6px 16px rgba(255, 107, 129, 0.6);
}

:global([data-theme="day"] .camera-toggle-simple:hover:not(:disabled)) {
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.6);
}

.camera-toggle-simple:disabled {
  cursor: not-allowed;
  opacity: 0.5;
  background: #64748b;
  box-shadow: none;
  transform: none;
}

.camera-toggle-simple i {
  font-size: 0.9rem;
}

/* 完整的摄像头卡片 */
.local-camera-card {
  position: absolute;
  z-index: 22;
  background: rgba(18, 14, 30, 0.85);
  backdrop-filter: blur(30px);
  -webkit-backdrop-filter: blur(30px);
  border: 1px solid rgba(255, 107, 129, 0.3);
  border-radius: 16px;
  box-shadow:
    0 20px 40px -10px rgba(0, 0, 0, 0.7),
    0 0 20px rgba(255, 107, 129, 0.15);
  color: #f1f5f9;
  overflow: hidden;
  transition: box-shadow 0.3s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
}

:global([data-theme="day"] .local-camera-card) {
  background: rgba(255, 255, 255, 0.95);
  border: 2px solid rgba(59, 130, 246, 0.3);
  box-shadow:
    0 20px 40px -10px rgba(59, 130, 246, 0.25),
    0 0 20px rgba(59, 130, 246, 0.15);
  color: #1e293b;
}

.local-camera-card:not(.dragging):not(.resizing):hover {
  box-shadow:
    0 25px 50px -12px rgba(0, 0, 0, 0.8),
    0 0 30px rgba(255, 107, 129, 0.25);
  border-color: rgba(255, 107, 129, 0.5);
}

:global([data-theme="day"] .local-camera-card:not(.dragging):not(.resizing):hover) {
  box-shadow:
    0 25px 50px -12px rgba(59, 130, 246, 0.3),
    0 0 30px rgba(59, 130, 246, 0.25);
  border-color: rgba(59, 130, 246, 0.5);
}

.local-camera-card.dragging,
.local-camera-card.resizing {
  transition: none !important;
  user-select: none;
  border: 3px solid #ff6b81 !important;
}

:global([data-theme="day"] .local-camera-card.dragging),
:global([data-theme="day"] .local-camera-card.resizing) {
  border: 3px solid #3b82f6 !important;
}

.local-camera-card.dragging *,
.local-camera-card.resizing * {
  transition: none !important;
}

.local-camera-card.collapsed {
  width: auto !important;
  height: auto !important;
}

.local-camera-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  font-size: 0.85rem;
  font-weight: 600;
  background: linear-gradient(180deg, rgba(255, 107, 129, 0.12), rgba(0, 0, 0, 0.3));
  border-bottom: 1px solid rgba(255, 107, 129, 0.2);
  cursor: grab;
  user-select: none;
  touch-action: none;
}

:global([data-theme="day"] .local-camera-top) {
  background: linear-gradient(180deg, rgba(59, 130, 246, 0.08), rgba(241, 245, 249, 0.6));
  border-bottom: 1px solid rgba(59, 130, 246, 0.2);
}

.local-camera-card.dragging .local-camera-top {
  cursor: grabbing;
}

.camera-title-wrap {
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
}

.camera-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #ffb3c1;
  font-weight: 700;
  font-size: 0.88rem;
}

:global([data-theme="day"] .camera-title) {
  color: #2563eb;
}

.camera-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-collapse {
  border: 1px solid rgba(255, 107, 129, 0.3);
  border-radius: 8px;
  padding: 5px 8px;
  font-size: 0.85rem;
  color: #ffb3c1;
  background: rgba(255, 107, 129, 0.1);
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

:global([data-theme="day"] .btn-collapse) {
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: #3b82f6;
  background: rgba(59, 130, 246, 0.1);
}

.btn-collapse:hover {
  border-color: rgba(255, 107, 129, 0.6);
  background: rgba(255, 107, 129, 0.2);
  transform: scale(1.05);
}

:global([data-theme="day"] .btn-collapse:hover) {
  border-color: rgba(59, 130, 246, 0.6);
  background: rgba(59, 130, 246, 0.2);
}

.btn-camera-toggle {
  border: none;
  border-radius: 10px;
  padding: 6px 12px;
  font-size: 0.75rem;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #ff6b81 0%, #ec4899 100%);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(255, 107, 129, 0.4);
  white-space: nowrap;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 5px;
}

:global([data-theme="day"] .btn-camera-toggle) {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
}

.btn-camera-toggle:hover {
  transform: translateY(-1px) scale(1.02);
  box-shadow: 0 6px 16px rgba(255, 107, 129, 0.6);
}

:global([data-theme="day"] .btn-camera-toggle:hover) {
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.6);
}

.btn-camera-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.5;
  background: #64748b;
  box-shadow: none;
  transform: none;
}

.local-camera-preview {
  position: relative;
  width: 100%;
  aspect-ratio: var(--preview-aspect-ratio, 4 / 3);
  min-height: 0;
  background: #000;
  overflow: hidden;
}

.local-camera-preview video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  transform: scaleX(-1);
}

.resize-handle {
  position: absolute;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 107, 129, 0.5);
  cursor: nwse-resize;
  transition: all 0.2s ease;
  z-index: 10;
  touch-action: none;
}

.resize-handle-br {
  right: 0;
  bottom: 0;
  border-top-left-radius: 16px;
  background: linear-gradient(135deg, transparent 50%, rgba(255, 107, 129, 0.12) 50%);
}

:global([data-theme="day"] .resize-handle) {
  color: rgba(59, 130, 246, 0.5);
}

:global([data-theme="day"] .resize-handle-br) {
  background: linear-gradient(135deg, transparent 50%, rgba(59, 130, 246, 0.12) 50%);
}

.resize-handle:hover {
  color: rgba(255, 107, 129, 1);
  background: linear-gradient(135deg, transparent 50%, rgba(255, 107, 129, 0.25) 50%);
}

:global([data-theme="day"] .resize-handle:hover) {
  color: rgba(59, 130, 246, 1);
  background: linear-gradient(135deg, transparent 50%, rgba(59, 130, 246, 0.25) 50%);
}

.resize-handle i {
  font-size: 0.85rem;
  transform: rotate(-90deg);
}

@media (max-width: 1024px) {
  .local-camera-card {
    backdrop-filter: blur(20px);
  }
}
</style>
