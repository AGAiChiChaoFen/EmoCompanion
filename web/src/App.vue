<template>
  <router-view />
</template>

<script setup>
import { useTheme } from './composables/useTheme';

// 初始化主题系统
useTheme();
</script>

<style>
/* Bootstrap Icons 支持 */
@import url('https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css');

/* 应用级重置 */
html,
body,
#app {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* ========== 主题 CSS 变量（默认值作为后备） ========== */
:root {
  /* 主色调 */
  --theme-primary: #ff6b81;
  --theme-primary-light: #ec4899;
  --theme-primary-dark: #8a2be2;
  
  /* 背景色 */
  --theme-bg-base: #0a0b14;
  --theme-bg-card: rgba(26, 22, 37, 0.85);
  --theme-bg-input: rgba(30, 27, 43, 0.9);
  
  /* 文本色 */
  --theme-text-primary: #e2e8f0;
  --theme-text-secondary: #cbd5e1;
  --theme-text-muted: #94a3b8;
  
  /* 边框和阴影 */
  --theme-border: rgba(255, 107, 129, 0.2);
  --theme-shadow: 0 8px 32px rgba(255, 107, 129, 0.15);
  --theme-shadow-hover: 0 12px 48px rgba(255, 107, 129, 0.25);
  
  /* 渐变背景 */
  --theme-gradient-1: rgba(255, 107, 129, 0.25);
  --theme-gradient-2: rgba(138, 43, 226, 0.2);
  --theme-gradient-3: rgba(99, 102, 241, 0.15);
  --theme-gradient-4: rgba(236, 72, 153, 0.18);
  
  /* 粒子效果 */
  --theme-particle-1: rgba(255, 107, 129, 0.3);
  --theme-particle-2: rgba(138, 43, 226, 0.3);
  --theme-particle-3: rgba(236, 72, 153, 0.3);
  --theme-particle-4: rgba(99, 102, 241, 0.3);
  
  /* 滚动条 */
  --theme-scrollbar-track: rgba(15, 12, 29, 0.5);
  --theme-scrollbar-thumb-start: rgba(255, 107, 129, 0.6);
  --theme-scrollbar-thumb-end: rgba(138, 43, 226, 0.6);
  --theme-scrollbar-thumb-hover-start: rgba(255, 107, 129, 0.9);
  --theme-scrollbar-thumb-hover-end: rgba(138, 43, 226, 0.9);
}

/*
  页面基础视觉：
  使用 CSS 变量实现主题切换
*/
body {
  font-family: 'Manrope', 'Inter', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background-color: var(--theme-bg-base);
  background-image: 
    radial-gradient(ellipse at 15% 25%, var(--theme-gradient-1), transparent 50%),
    radial-gradient(ellipse at 85% 75%, var(--theme-gradient-2), transparent 50%),
    radial-gradient(ellipse at 50% 10%, var(--theme-gradient-3), transparent 45%),
    radial-gradient(ellipse at 30% 90%, var(--theme-gradient-4), transparent 48%),
    linear-gradient(135deg, var(--theme-bg-base) 0%, var(--theme-bg-card) 40%, var(--theme-bg-base) 100%);
  background-attachment: fixed;
  color: var(--theme-text-primary);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  animation: bg-shift 20s ease-in-out infinite alternate;
  
  /* 主题切换过渡动画 */
  transition: background-color 0.4s ease-in-out,
              color 0.4s ease-in-out;
}

@keyframes bg-shift {
  0% {
    background-position: 0% 0%, 100% 100%, 50% 0%, 30% 100%;
  }
  100% {
    background-position: 10% 10%, 90% 90%, 60% 10%, 20% 90%;
  }
}

/* 全局盒模型统一 */
* {
  box-sizing: border-box;
}

/* 全局滚动条样式：使用 CSS 变量 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-track {
  background: var(--theme-scrollbar-track);
  border-radius: 10px;
  transition: background 0.3s ease;
}
::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, var(--theme-scrollbar-thumb-start), var(--theme-scrollbar-thumb-end));
  border-radius: 10px;
  transition: all 0.3s ease;
}
::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, var(--theme-scrollbar-thumb-hover-start), var(--theme-scrollbar-thumb-hover-end));
  box-shadow: 0 0 10px var(--theme-primary);
}

/* 全局主题过渡 */
*,
*::before,
*::after {
  transition-property: background-color, color, border-color, box-shadow, fill, stroke;
  transition-duration: 0.3s;
  transition-timing-function: ease-in-out;
}

</style>
