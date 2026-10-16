<template>
  <div class="chat-messages" ref="containerRef">
    <!--
      消息渲染主循环：
      - system：系统通知（居中展示）
      - user / ai：左右对话气泡
    -->
    <div
      v-for="(msg, index) in messages"
      :key="msg.id || index"
      :class="msg.type === 'system' ? 'message-system' : ('message-row message-' + msg.type)"
    >
      <template v-if="msg.type === 'system'">
        <!-- 系统消息：不显示头像，仅文本提示 -->
        {{ msg.text }}
      </template>
      <template v-else>
        <!-- 普通消息：头像 + 气泡 -->
        <div :class="['avatar', msg.type === 'user' ? 'avatar-user' : 'avatar-ai']">
          <i :class="['bi', msg.type === 'user' ? 'bi-person-fill' : 'bi-stars']"></i>
        </div>
        <div class="bubble" :class="{ 'bubble-thinking': msg.thinking }">
          <template v-if="msg.thinking && !msg.text">
            <!-- 流式响应尚无正文时，展示“思考中”动效 -->
            <span class="thinking-text">正在思考中</span>
            <span class="thinking-dots" aria-hidden="true">
              <i></i><i></i><i></i>
            </span>
          </template>
          <template v-else>
            <!-- 已有正文时展示文本，streaming 状态下附带光标 -->
            <span>{{ msg.text }}</span>
            <span v-if="msg.streaming" class="typing-cursor"></span>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue';

// 输入消息数组由父组件维护，本组件只负责“展示 + 自动滚动”。
const props = defineProps({
  messages: {
    type: Array,
    required: true,
  },
});

// 对应最外层滚动容器，用于程序化滚动到底部。
const containerRef = ref(null);

// 滚动到底部：使用 nextTick 保证 DOM 已更新（尤其是流式 token 追加后）。
const scrollToBottom = () => {
  nextTick(() => {
    if (!containerRef.value) return;
    containerRef.value.scrollTop = containerRef.value.scrollHeight;
  });
};

// 深度监听消息数组，任何文本增量都触发自动滚动。
watch(
  () => props.messages,
  () => {
    scrollToBottom();
  },
  { deep: true }
);

// 向父组件暴露滚动方法，便于在发送消息等时机主动触发。
defineExpose({
  scrollToBottom,
});
</script>

<style scoped>
/*
  消息列表容器：
  1. 竖向流式排布；
  2. 启用平滑滚动；
  3. 使用暗色紫罗兰底色与新主题统一。
*/
.chat-messages {
  flex: 1;
  min-height: 0;
  padding: 20px 22px;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 18px;
  scroll-behavior: smooth;
  background: linear-gradient(180deg, rgba(22, 24, 33, 0.6) 0%, rgba(18, 19, 28, 0.4) 100%);
}

:global([data-theme="day"] .chat-messages) {
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.8) 0%, rgba(241, 245, 249, 0.6) 100%);
}

.chat-messages::-webkit-scrollbar {
  width: 6px;
}

.chat-messages::-webkit-scrollbar-track {
  background: transparent;
}

.chat-messages::-webkit-scrollbar-thumb {
  background-color: rgba(138, 43, 226, 0.24);
  border-radius: 10px;
}

:global([data-theme="day"] .chat-messages::-webkit-scrollbar-thumb) {
  background-color: rgba(59, 130, 246, 0.35);
}

.chat-messages::-webkit-scrollbar-thumb:hover {
  background-color: rgba(138, 43, 226, 0.5);
}

:global([data-theme="day"] .chat-messages::-webkit-scrollbar-thumb:hover) {
  background-color: rgba(59, 130, 246, 0.6);
}

.message-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  max-width: 92%;
  animation: message-slide-in 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.message-user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.message-ai {
  align-self: flex-start;
  flex-direction: row;
  align-items: flex-start;
}

.message-system {
  align-self: center;
  max-width: 86%;
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 0.78rem;
  color: #c084fc;
  background: rgba(138, 43, 226, 0.15);
  border: 1px solid rgba(138, 43, 226, 0.3);
  backdrop-filter: blur(4px);
}

:global([data-theme="day"] .message-system) {
  color: #2563eb;
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 15px;
  flex-shrink: 0;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}

.avatar-user {
  background: linear-gradient(140deg, #9333ea 0%, #6b21a8 100%);
}

:global([data-theme="day"] .avatar-user) {
  background: linear-gradient(140deg, #3b82f6 0%, #2563eb 100%);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.avatar-ai {
  background: linear-gradient(140deg, #ec4899 0%, #be185d 100%);
  border-radius: 50%;
}

:global([data-theme="day"] .avatar-ai) {
  background: linear-gradient(140deg, #0ea5e9 0%, #0284c7 100%);
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
}

.bubble {
  min-height: 40px;
  padding: 11px 16px;
  font-size: 0.9rem;
  line-height: 1.56;
  word-wrap: break-word;
  white-space: pre-wrap;
  border: 1px solid transparent;
  box-shadow: 0 6px 14px rgba(0, 0, 0, 0.15);
  transition: transform 0.2s ease;
}

.bubble:empty {
  min-width: 26px;
}

.message-user .bubble {
  color: #fff;
  background: linear-gradient(140deg, #8b5cf6 0%, #6d28d9 100%);
  border-radius: 16px 16px 4px 16px;
  box-shadow: 0 6px 16px rgba(109, 40, 217, 0.3);
}

:global([data-theme="day"] .message-user .bubble) {
  background: linear-gradient(140deg, #3b82f6 0%, #2563eb 100%);
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.35);
}

.message-ai .bubble {
  color: #e2e8f0;
  background: rgba(30, 31, 46, 0.85);
  border-radius: 16px 16px 16px 4px;
  border-color: rgba(138, 43, 226, 0.3);
  backdrop-filter: blur(10px);
}

:global([data-theme="day"] .message-ai .bubble) {
  color: #1e293b;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(226, 232, 240, 0.8);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.bubble-thinking {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.thinking-text {
  color: #c084fc;
  font-size: 0.86rem;
  font-weight: 600;
}

:global([data-theme="day"] .thinking-text) {
  color: #3b82f6;
}

.thinking-dots {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.thinking-dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #6b21a8;
  display: inline-block;
  animation: thinking-dot 1.4s infinite ease-in-out both;
}

:global([data-theme="day"] .thinking-dots i) {
  background: #3b82f6;
}

.thinking-dots i:nth-child(1) {
  animation-delay: -0.32s;
}

.thinking-dots i:nth-child(2) {
  animation-delay: -0.16s;
}

.typing-cursor {
  display: inline-block;
  width: 7px;
  height: 14px;
  margin-left: 5px;
  vertical-align: -2px;
  border-radius: 2px;
  background: #c084fc;
  animation: cursor-blink 0.9s infinite step-end;
}

:global([data-theme="day"] .typing-cursor) {
  background: #3b82f6;
}

@keyframes message-slide-in {
  from {
    opacity: 0;
    transform: translateY(15px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes cursor-blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}

@keyframes thinking-dot {
  0%,
  80%,
  100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1.2);
    opacity: 1;
    background: #e879f9;
    box-shadow: 0 0 8px #e879f9;
  }
}

:global([data-theme="day"] .thinking-dots i) {
  animation: thinking-dot-light 1.4s infinite ease-in-out both;
}

@keyframes thinking-dot-light {
  0%,
  80%,
  100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1.2);
    opacity: 1;
    background: #60a5fa;
    box-shadow: 0 0 8px #60a5fa;
  }
}

@media (max-width: 640px) {
  .chat-messages {
    padding: 14px;
    gap: 14px;
  }

  .bubble {
    font-size: 0.86rem;
  }
}
</style>
