<template>
  <button
    class="theme-toggle-btn"
    :aria-label="ariaLabel"
    :title="ariaLabel"
    @click="toggleTheme"
  >
    <i :class="iconClass"></i>
  </button>
</template>

<script setup>
import { computed } from 'vue';
import { useTheme } from '../composables/useTheme';

const { currentTheme, toggleTheme } = useTheme();

const iconClass = computed(() => {
  return currentTheme.value === 'night' ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
});

const ariaLabel = computed(() => {
  return currentTheme.value === 'night' ? '切换到日间主题' : '切换到夜间主题';
});
</script>

<style scoped>
.theme-toggle-btn {
  width: 100%;
  height: 48px;
  border-radius: 12px;
  border: 1px solid var(--theme-border, rgba(255, 107, 129, 0.2));
  background: var(--theme-bg-card, rgba(26, 22, 37, 0.85));
  color: var(--theme-primary, #ff6b81);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 18px;
  transition: all 0.3s ease;
  box-shadow: var(--theme-shadow, 0 8px 32px rgba(255, 107, 129, 0.15));
  backdrop-filter: blur(10px);
  position: relative;
  overflow: hidden;
}

.theme-toggle-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, 
    rgba(255, 107, 129, 0.1) 0%, 
    rgba(138, 43, 226, 0.1) 100%
  );
  opacity: 0;
  transition: opacity 0.3s ease;
}

.theme-toggle-btn:hover::before {
  opacity: 1;
}

.theme-toggle-btn:hover {
  transform: translateY(-2px);
  box-shadow: var(--theme-shadow-hover, 0 12px 48px rgba(255, 107, 129, 0.25));
  border-color: var(--theme-primary, #ff6b81);
}

.theme-toggle-btn:focus {
  outline: 2px solid var(--theme-primary, #ff6b81);
  outline-offset: 2px;
}

.theme-toggle-btn:active {
  transform: translateY(0);
}

/* 点击涟漪效果 */
.theme-toggle-btn::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 12px;
  background: var(--theme-primary, #ff6b81);
  opacity: 0;
  transform: scale(0);
  transition: transform 0.6s ease, opacity 0.6s ease;
}

.theme-toggle-btn:active::after {
  transform: scale(1);
  opacity: 0.3;
}

.theme-toggle-btn i {
  position: relative;
  z-index: 1;
}
</style>
