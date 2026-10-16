<template>
  <div
    class="demo-layout"
    :class="{
      'sidebar-collapsed': isSidebarCollapsed,
      'sidebar-animating': isSidebarAnimating
    }"
  >
    <!-- 侧边导航栏 -->
    <aside class="sidebar" :class="{ collapsed: isSidebarCollapsed }">
      <!-- Logo区域 -->
      <div class="sidebar-header">
        <div class="logo-container">
          <div class="logo-icon">
            <i class="bi bi-heart-pulse-fill"></i>
          </div>
          <div class="logo-text">
            <h1>EmoCompanion</h1>
            <p>情感关怀系统</p>
          </div>
        </div>
        
        <!-- 折叠按钮 -->
        <button class="collapse-btn" @click="toggleSidebar" :title="isSidebarCollapsed ? '展开侧边栏' : '收起侧边栏'">
          <i class="bi" :class="isSidebarCollapsed ? 'bi-chevron-right' : 'bi-chevron-left'"></i>
        </button>
      </div>

      <!-- 导航菜单 -->
      <nav class="sidebar-nav">
        <router-link
          v-for="route in navRoutes"
          :key="route.path"
          :to="route.path"
          class="nav-item"
          :class="{ active: isActiveRoute(route.path) }"
        >
          <div class="nav-icon">
            <i class="bi" :class="route.meta.icon"></i>
          </div>
          <div class="nav-content">
            <span class="nav-title">{{ route.meta.title }}</span>
            <span class="nav-desc">{{ route.meta.description }}</span>
          </div>
          
          <!-- 激活指示器 -->
          <div class="active-indicator"></div>
        </router-link>
      </nav>

      <!-- 主题切换按钮 -->
      <div class="theme-toggle-wrapper">
        <ThemeToggle />
      </div>

      <!-- 底部信息 -->
      <div class="sidebar-footer">
        <div class="footer-text">
          <p class="footer-title">智能陪伴中枢</p>
          <p class="footer-subtitle">Care Intelligence Hub</p>
        </div>
        <div class="footer-icon">
          <i class="bi bi-shield-check"></i>
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
      <header class="topbar">
        <div class="topbar-title-group">
          <div class="topbar-kicker">
            <i class="bi bi-stars"></i>
            <span>情感陪护虚拟数字人系统</span>
          </div>
          <div class="topbar-title-row">
            <h2>{{ currentMeta.title }}</h2>
            <span class="topbar-desc">{{ currentMeta.description }}</span>
          </div>
        </div>

        <div class="topbar-actions">
          <router-link class="knowledge-entry" to="/knowledge-graph" title="查看心理知识库">
            <i class="bi bi-journal-medical"></i>
            <span>心理知识库</span>
          </router-link>
          <div class="calendar-menu" @click.stop>
            <button class="topbar-date" type="button" @click="toggleCalendar">
              <i class="bi bi-calendar2-week"></i>
              <span>{{ currentDateText }}</span>
            </button>

            <div v-if="isCalendarOpen" class="calendar-popover">
              <div class="calendar-header">
                <button type="button" class="calendar-nav-btn" @click="changeMonth(-1)" title="上个月">
                  <i class="bi bi-chevron-left"></i>
                </button>
                <div>
                  <strong>{{ calendarMonthTitle }}</strong>
                  <span>{{ selectedDateText }}</span>
                </div>
                <button type="button" class="calendar-nav-btn" @click="changeMonth(1)" title="下个月">
                  <i class="bi bi-chevron-right"></i>
                </button>
              </div>

              <div class="calendar-weekdays">
                <span v-for="day in weekDays" :key="day">{{ day }}</span>
              </div>

              <div class="calendar-grid">
                <button
                  v-for="day in calendarDays"
                  :key="day.key"
                  type="button"
                  class="calendar-day"
                  :class="{
                    muted: !day.inCurrentMonth,
                    today: day.isToday,
                    selected: day.isSelected,
                    'has-events': day.events.length
                  }"
                  @click="selectCalendarDate(day.date)"
                >
                  <span>{{ day.date.getDate() }}</span>
                  <i v-if="day.events.length"></i>
                </button>
              </div>

              <div class="calendar-agenda">
                <div class="agenda-title">
                  <span>当天提醒</span>
                  <button type="button" @click="goToday">回到今天</button>
                </div>
                <div class="agenda-list">
                  <div v-for="item in selectedAgenda" :key="`${item.time}-${item.title}`" class="agenda-item">
                    <span>{{ item.time }}</span>
                    <div>
                      <strong>{{ item.title }}</strong>
                      <small>{{ item.note }}</small>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="topbar-theme">
            <ThemeToggle />
          </div>
        </div>
      </header>

      <section class="content-viewport">
        <router-view />
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue';
import { useRoute } from 'vue-router';
import ThemeToggle from '../components/ThemeToggle.vue';

const route = useRoute();
const isSidebarCollapsed = ref(true);
const isSidebarAnimating = ref(false);

const SIDEBAR_WIDTH_DURATION_MS = 860;
let sidebarAnimationTimer = null;
const today = new Date();
const isCalendarOpen = ref(false);
const selectedDate = ref(new Date(today));
const visibleMonth = ref(new Date(today.getFullYear(), today.getMonth(), 1));
const weekDays = ['一', '二', '三', '四', '五', '六', '日'];

const navRoutes = [
  {
    path: '/multimodal-analysis',
    meta: {
      title: '多模态数据采集及解析',
      icon: 'bi-activity',
      description: '视频、音频、文本并行采集与情绪解析'
    }
  },
  {
    path: '/assessment-intervention',
    meta: {
      title: '心理评估与干预',
      icon: 'bi-clipboard2-pulse',
      description: '知识支持的风险评估与分级干预'
    }
  },
  {
    path: '/knowledge-graph',
    meta: {
      title: '心理知识库',
      icon: 'bi-journal-medical',
      description: '心理资料构建、图谱可视化与干预建议'
    }
  },
  {
    path: '/avatar-customization',
    meta: {
      title: '数字人形象定制',
      icon: 'bi-person-video3',
      description: '支持形象定制、音色克隆的数字人生成'
    }
  },
  {
    path: '/integrated-system',
    meta: {
      title: '数字人伴侣',
      icon: 'bi-grid-3x3-gap',
      description: '唤醒数字人并开展实时陪护互动'
    }
  },
  {
    path: '/persona-memory',
    meta: {
      title: '长期情感档案',
      icon: 'bi-diagram-3-fill',
      description: '用户画像、长期记忆与陪伴偏好变化'
    }
  }
];

const formatDateKey = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const addDays = (date, days) => {
  const nextDate = new Date(date);
  nextDate.setDate(nextDate.getDate() + days);
  return nextDate;
};

const sameDate = (dateA, dateB) => formatDateKey(dateA) === formatDateKey(dateB);

const agendaByDate = {
  [formatDateKey(today)]: [
    { time: '08:30', title: '晨间心情问候', note: '记录今天的初始状态' },
    { time: '15:30', title: '散步与饮水提醒', note: '适合低强度活动' },
    { time: '19:30', title: '晚间情绪回顾', note: '聊聊今天发生的小事' },
  ],
  [formatDateKey(addDays(today, 1))]: [
    { time: '09:00', title: '早餐后问候', note: '关注睡眠和食欲变化' },
    { time: '20:00', title: '家属视频提醒', note: '建议安排一次轻松通话' },
  ],
  [formatDateKey(addDays(today, 2))]: [
    { time: '10:00', title: '兴趣话题陪聊', note: '从花草和天气自然开始' },
    { time: '21:00', title: '睡前舒缓练习', note: '进行 3 分钟呼吸放松' },
  ],
};

const currentDateText = computed(() => new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  weekday: 'short'
}).format(selectedDate.value));

const selectedDateText = computed(() => new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  weekday: 'long'
}).format(selectedDate.value));

const calendarMonthTitle = computed(() => new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: 'long'
}).format(visibleMonth.value));

const selectedAgenda = computed(() => agendaByDate[formatDateKey(selectedDate.value)] || [
  { time: '09:00', title: '日常陪伴问候', note: '根据用户状态生成温和开场' },
  { time: '19:30', title: '晚间状态回顾', note: '记录一天情绪与睡眠线索' },
]);

const calendarDays = computed(() => {
  const year = visibleMonth.value.getFullYear();
  const month = visibleMonth.value.getMonth();
  const firstDay = new Date(year, month, 1);
  const startOffset = (firstDay.getDay() + 6) % 7;
  const startDate = new Date(year, month, 1 - startOffset);

  return Array.from({ length: 42 }, (_, index) => {
    const date = addDays(startDate, index);
    const key = formatDateKey(date);
    return {
      key,
      date,
      inCurrentMonth: date.getMonth() === month,
      isToday: sameDate(date, today),
      isSelected: sameDate(date, selectedDate.value),
      events: agendaByDate[key] || [],
    };
  });
});

const currentMeta = computed(() => ({
  title: route.meta?.title || '长期情感档案',
  description: route.meta?.description || '用户画像、交互历史与干预策略动态迭代',
}));

const clearSidebarAnimationTimer = () => {
  if (sidebarAnimationTimer) {
    clearTimeout(sidebarAnimationTimer);
    sidebarAnimationTimer = null;
  }
};

const toggleCalendar = () => {
  isCalendarOpen.value = !isCalendarOpen.value;
};

const selectCalendarDate = (date) => {
  selectedDate.value = new Date(date);
  visibleMonth.value = new Date(date.getFullYear(), date.getMonth(), 1);
};

const changeMonth = (offset) => {
  visibleMonth.value = new Date(
    visibleMonth.value.getFullYear(),
    visibleMonth.value.getMonth() + offset,
    1
  );
};

const goToday = () => {
  selectedDate.value = new Date(today);
  visibleMonth.value = new Date(today.getFullYear(), today.getMonth(), 1);
};

// 切换侧边栏状态
const toggleSidebar = () => {
  clearSidebarAnimationTimer();
  isSidebarAnimating.value = true;
  isSidebarCollapsed.value = !isSidebarCollapsed.value;
  sidebarAnimationTimer = setTimeout(() => {
    isSidebarAnimating.value = false;
    sidebarAnimationTimer = null;
  }, SIDEBAR_WIDTH_DURATION_MS);
};

// 判断路由是否激活
const isActiveRoute = (path) => {
  return route.path === path;
};

onBeforeUnmount(() => {
  clearSidebarAnimationTimer();
});
</script>

<style scoped>
.demo-layout {
  --sidebar-expanded-width: 320px;
  --sidebar-collapsed-width: 84px;
  --sidebar-width: var(--sidebar-expanded-width);
  --sidebar-motion-duration: 860ms;
  --sidebar-motion-ease: cubic-bezier(0.22, 1, 0.36, 1);
  --content-fade-duration: 360ms;

  display: flex;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background: var(--theme-bg-base);
  transition: background 0.4s ease-in-out;
}

/* 日间主题专用背景 */
[data-theme="day"] .demo-layout {
  background: linear-gradient(135deg, #e0f2fe 0%, #dbeafe 30%, #e0e7ff 60%, #fae8ff 100%);
}

.demo-layout.sidebar-collapsed {
  --sidebar-width: var(--sidebar-collapsed-width);
}

/* ========== 侧边栏样式 ========== */
.sidebar {
  width: var(--sidebar-width);
  height: 100vh;
  background: linear-gradient(180deg, 
    var(--theme-bg-card) 0%, 
    var(--theme-bg-base) 100%
  );
  backdrop-filter: blur(20px);
  border-right: 1px solid var(--theme-border);
  display: flex;
  flex-direction: column;
  transition:
    width var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    box-shadow var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    border-color var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    background 0.4s ease-in-out;
  position: relative;
  z-index: 700;
  box-shadow: 4px 0 24px var(--theme-shadow);
  will-change: width;
}

.sidebar.collapsed {
  width: var(--sidebar-width);
}

/* ========== Logo区域 ========== */
.sidebar-header {
  padding: 24px 20px;
  border-bottom: 1px solid var(--theme-border);
  position: relative;
  transition:
    padding var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    border-color var(--sidebar-motion-duration) var(--sidebar-motion-ease);
}

.logo-container {
  display: flex;
  align-items: center;
  gap: 16px;
  transition: gap var(--sidebar-motion-duration) var(--sidebar-motion-ease);
}

.logo-icon {
  width: 48px;
  height: 48px;
  min-width: 48px;
  background: linear-gradient(135deg, var(--theme-primary) 0%, var(--theme-primary-dark) 100%);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: white;
  box-shadow: 0 4px 16px var(--theme-primary);
  transition:
    transform var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    box-shadow var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    border-radius var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    background 0.4s ease-in-out;
}

.sidebar:not(.collapsed) .logo-icon:hover {
  transform: scale(1.05) rotate(5deg);
  box-shadow: 0 6px 20px var(--theme-primary);
}

.logo-text {
  flex: 1 1 auto;
  min-width: 0;
  max-width: 220px;
  overflow: hidden;
  transform-origin: left center;
  transition:
    max-width var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    opacity var(--content-fade-duration) ease,
    transform var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    filter var(--content-fade-duration) ease;
}

.logo-text h1 {
  font-size: 20px;
  font-weight: 700;
  color: var(--theme-text-primary);
  margin: 0;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  background: linear-gradient(135deg, var(--theme-primary) 0%, var(--theme-primary-dark) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  transition: background 0.4s ease-in-out;
}

.logo-text p {
  font-size: 11px;
  color: var(--theme-text-muted);
  margin: 2px 0 0 0;
  font-weight: 500;
  letter-spacing: 0.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.4s ease-in-out;
}

/* 折叠按钮 */
.collapse-btn {
  position: absolute;
  right: -12px;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  background: linear-gradient(135deg, var(--theme-primary) 0%, var(--theme-primary-dark) 100%);
  border: 2px solid var(--theme-bg-base);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: white;
  font-size: 12px;
  transition:
    transform var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    box-shadow var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    background var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    border-color 0.4s ease-in-out;
  z-index: 20;
  box-shadow: 0 2px 8px var(--theme-primary);
}

.collapse-btn:hover {
  transform: translateY(-50%) scale(1.1);
  box-shadow: 0 4px 12px var(--theme-primary);
}

.collapse-btn i {
  transition: transform var(--sidebar-motion-duration) var(--sidebar-motion-ease);
}

.collapse-btn:hover i {
  transform: scale(1.1);
}

/* ========== 导航菜单 ========== */
.sidebar-nav {
  flex: 1;
  padding: 16px 12px;
  overflow-y: auto;
  overflow-x: hidden;
  transition: padding var(--sidebar-motion-duration) var(--sidebar-motion-ease);
}

.sidebar-nav::-webkit-scrollbar {
  width: 4px;
}

.sidebar-nav::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: var(--theme-primary);
  border-radius: 2px;
  transition: background 0.3s ease;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 13px 12px;
  margin-bottom: 6px;
  border-radius: 12px;
  text-decoration: none;
  color: var(--theme-text-secondary);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
  cursor: pointer;
  transition:
    transform 320ms cubic-bezier(0.22, 1, 0.36, 1),
    color 320ms ease,
    background var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    box-shadow var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    gap var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    padding var(--sidebar-motion-duration) var(--sidebar-motion-ease);
}

.nav-item::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, 
    var(--theme-gradient-1) 0%, 
    var(--theme-gradient-2) 100%
  );
  opacity: 0;
  transition: opacity 0.3s ease, background 0.4s ease-in-out;
}

.nav-item:hover::before {
  opacity: 1;
}

.nav-item:hover {
  color: var(--theme-text-primary);
  transform: translateX(4px);
}

.demo-layout.sidebar-animating .sidebar-nav {
  pointer-events: none;
}

.demo-layout.sidebar-animating .nav-item::before {
  opacity: 0 !important;
}

.demo-layout.sidebar-animating .nav-item:hover,
.demo-layout.sidebar-animating .nav-item:hover .nav-icon,
.demo-layout.sidebar-animating .collapse-btn:hover,
.demo-layout.sidebar-animating .collapse-btn:hover i {
  transform: none;
}

.nav-item.active {
  background: linear-gradient(135deg, 
    var(--theme-gradient-1) 0%, 
    var(--theme-gradient-2) 100%
  );
  color: var(--theme-text-primary);
  box-shadow: 0 4px 16px var(--theme-primary);
  transition: background 0.4s ease-in-out, box-shadow 0.4s ease-in-out;
}

.nav-icon {
  width: 40px;
  height: 40px;
  min-width: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  background: var(--theme-bg-input);
  border-radius: 10px;
  transition:
    transform 380ms cubic-bezier(0.22, 1, 0.36, 1),
    background var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    box-shadow var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    border-radius var(--sidebar-motion-duration) var(--sidebar-motion-ease);
  position: relative;
  z-index: 1;
}

.nav-icon i {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  line-height: 1;
}

.nav-item:hover .nav-icon {
  background: var(--theme-gradient-1);
  transform: scale(1.1) rotate(5deg);
}

.nav-item.active .nav-icon {
  background: linear-gradient(135deg, var(--theme-primary) 0%, var(--theme-primary-dark) 100%);
  box-shadow: 0 4px 12px var(--theme-primary);
  transition: background 0.4s ease-in-out, box-shadow 0.4s ease-in-out;
}

.nav-content {
  flex: 1;
  min-width: 0;
  max-width: 240px;
  overflow: hidden;
  position: relative;
  z-index: 1;
  transform-origin: left center;
  transition:
    max-width var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    opacity var(--content-fade-duration) ease,
    transform var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    filter var(--content-fade-duration) ease;
}

.nav-title {
  display: block;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-desc {
  display: block;
  font-size: 11px;
  opacity: 0.6;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 激活指示器 */
.active-indicator {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 0;
  background: linear-gradient(180deg, var(--theme-primary) 0%, var(--theme-primary-dark) 100%);
  border-radius: 0 2px 2px 0;
  transition: height 420ms cubic-bezier(0.22, 1, 0.36, 1), background 0.4s ease-in-out;
}

.nav-item.active .active-indicator {
  height: 60%;
}

/* ========== 主题切换按钮容器 ========== */
.theme-toggle-wrapper {
  padding: 12px 20px;
  border-top: 1px solid var(--theme-border);
  transition:
    padding var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    border-color var(--sidebar-motion-duration) var(--sidebar-motion-ease);
}

.demo-layout.sidebar-collapsed .theme-toggle-wrapper {
  padding-left: 14px;
  padding-right: 14px;
}

/* 收起状态下的导航项 */
.sidebar.collapsed .nav-item {
  padding: 16px 12px;
  gap: 0;
}

.sidebar.collapsed .nav-icon {
  margin: 0;
  border-radius: 12px;
}

.demo-layout.sidebar-collapsed .logo-text,
.demo-layout.sidebar-collapsed .nav-content,
.demo-layout.sidebar-collapsed .footer-text {
  max-width: 0;
  opacity: 0;
  transform: translateX(-10px) scale(0.98);
  filter: blur(4px);
}

/* ========== 底部信息 ========== */
.sidebar-footer {
  padding: 20px;
  border-top: 1px solid var(--theme-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  transition:
    padding var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    gap var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    border-color var(--sidebar-motion-duration) var(--sidebar-motion-ease);
}

.footer-text {
  flex: 1;
  min-width: 0;
  max-width: 180px;
  overflow: hidden;
  transform-origin: left center;
  transition:
    max-width var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    opacity var(--content-fade-duration) ease,
    transform var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    filter var(--content-fade-duration) ease;
}

.footer-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--theme-text-secondary);
  margin: 0 0 2px 0;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.4s ease-in-out;
}

.footer-subtitle {
  font-size: 11px;
  color: var(--theme-text-muted);
  margin: 0;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.4s ease-in-out;
}

.footer-icon {
  width: 36px;
  height: 36px;
  min-width: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #ffd700;
  background: rgba(255, 215, 0, 0.1);
  border-radius: 8px;
  animation: pulse-gold 2s ease-in-out infinite;
  flex-shrink: 0;
  transition:
    transform var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    border-radius var(--sidebar-motion-duration) var(--sidebar-motion-ease);
}

@keyframes pulse-gold {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(255, 215, 0, 0.4);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(255, 215, 0, 0);
  }
}

.sidebar.collapsed .sidebar-footer {
  justify-content: center;
}

.sidebar:not(.collapsed) .sidebar-footer {
  justify-content: space-between;
}

.sidebar:not(.collapsed) .footer-icon {
  margin-left: auto;
}

.demo-layout.sidebar-collapsed .footer-icon {
  margin: 0 auto;
}

/* ========== 主内容区 ========== */
.main-content {
  flex: 1;
  width: calc(100% - var(--sidebar-width));
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-width: 0;
  transition:
    width var(--sidebar-motion-duration) var(--sidebar-motion-ease),
    transform var(--sidebar-motion-duration) var(--sidebar-motion-ease);
  will-change: width;
}

.topbar {
  position: relative;
  z-index: 500;
  height: 82px;
  min-height: 82px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 0 28px 0 44px;
  border-bottom: 1px solid var(--theme-border);
  background: linear-gradient(135deg, var(--theme-bg-card), var(--theme-bg-input));
  backdrop-filter: blur(18px);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.08);
  transition: background 0.4s ease-in-out, border-color 0.4s ease-in-out;
}

.topbar-title-group {
  min-width: 0;
}

.topbar-kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  color: var(--theme-primary);
  font-size: 0.78rem;
  font-weight: 700;
}

.topbar-title-row {
  display: flex;
  align-items: baseline;
  gap: 14px;
  min-width: 0;
}

.topbar-title-row h2 {
  margin: 0;
  color: var(--theme-text-primary);
  font-size: 1.25rem;
  line-height: 1.2;
  white-space: nowrap;
}

.topbar-desc {
  color: var(--theme-text-muted);
  font-size: 0.88rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.knowledge-entry,
.topbar-date {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 13px;
  border: 1px solid var(--theme-border);
  border-radius: 999px;
  background: var(--theme-bg-card);
  color: var(--theme-text-secondary);
  font-size: 0.82rem;
  text-decoration: none;
  white-space: nowrap;
}

.topbar-date {
  cursor: pointer;
  font: inherit;
}

.calendar-menu {
  position: relative;
  z-index: 520;
}

.calendar-popover {
  position: absolute;
  top: calc(100% + 12px);
  right: 0;
  z-index: 999;
  width: 360px;
  padding: 16px;
  border: 1px solid var(--theme-border);
  border-radius: 18px;
  background: #141827;
  color: var(--theme-text-primary);
  box-shadow: var(--theme-shadow-hover);
  backdrop-filter: blur(22px);
}

.calendar-popover::before {
  content: '';
  position: absolute;
  top: -7px;
  right: 48px;
  width: 12px;
  height: 12px;
  transform: rotate(45deg);
  border-left: 1px solid var(--theme-border);
  border-top: 1px solid var(--theme-border);
  background: #141827;
}

.calendar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.calendar-header strong,
.calendar-header span {
  display: block;
  text-align: center;
}

.calendar-header strong {
  font-size: 1rem;
}

.calendar-header span {
  margin-top: 3px;
  color: var(--theme-text-muted);
  font-size: 0.78rem;
}

.calendar-nav-btn {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 1px solid var(--theme-border);
  border-radius: 12px;
  background: #1f2537;
  color: var(--theme-text-secondary);
  cursor: pointer;
}

.calendar-nav-btn:hover {
  color: var(--theme-primary);
  border-color: var(--theme-primary);
}

.calendar-weekdays,
.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
}

.calendar-weekdays {
  margin-bottom: 8px;
}

.calendar-weekdays span {
  color: var(--theme-text-muted);
  font-size: 0.74rem;
  font-weight: 800;
  text-align: center;
}

.calendar-day {
  position: relative;
  height: 38px;
  display: grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: var(--theme-text-secondary);
  cursor: pointer;
}

.calendar-day:hover {
  border-color: var(--theme-border);
  background: var(--theme-gradient-1);
  color: var(--theme-primary);
}

.calendar-day.muted {
  opacity: 0.36;
}

.calendar-day.today {
  border-color: var(--theme-primary);
}

.calendar-day.selected {
  background: linear-gradient(135deg, var(--theme-primary), var(--theme-primary-light));
  color: white;
  box-shadow: var(--theme-shadow);
}

.calendar-day span {
  font-size: 0.88rem;
  font-weight: 800;
}

.calendar-day i {
  position: absolute;
  bottom: 5px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}

.calendar-agenda {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--theme-border);
}

.agenda-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.agenda-title span {
  color: var(--theme-text-primary);
  font-weight: 900;
}

.agenda-title button {
  border: 1px solid var(--theme-border);
  border-radius: 999px;
  background: var(--theme-gradient-1);
  color: var(--theme-primary);
  font-size: 0.76rem;
  font-weight: 800;
  padding: 5px 9px;
  cursor: pointer;
}

.agenda-list {
  display: grid;
  gap: 8px;
}

.agenda-item {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--theme-border);
  border-radius: 14px;
  background: #1f2537;
}

[data-theme="day"] .calendar-popover,
[data-theme="day"] .calendar-popover::before {
  background: #ffffff;
}

[data-theme="day"] .calendar-nav-btn,
[data-theme="day"] .agenda-item {
  background: #f3f7fd;
}

.agenda-item > span {
  color: var(--theme-primary);
  font-weight: 900;
  font-size: 0.8rem;
}

.agenda-item strong,
.agenda-item small {
  display: block;
}

.agenda-item strong {
  color: var(--theme-text-primary);
  font-size: 0.88rem;
}

.agenda-item small {
  margin-top: 3px;
  color: var(--theme-text-muted);
  line-height: 1.4;
}

.knowledge-entry {
  color: var(--theme-primary);
  font-weight: 700;
  background:
    linear-gradient(135deg, var(--theme-gradient-1), var(--theme-gradient-2)),
    var(--theme-bg-card);
  box-shadow: var(--theme-shadow);
  transition: transform 0.28s ease, box-shadow 0.28s ease, border-color 0.28s ease;
}

.knowledge-entry:hover,
.knowledge-entry.router-link-active {
  border-color: var(--theme-primary);
  color: var(--theme-primary);
  transform: translateY(-1px);
  box-shadow: var(--theme-shadow-hover);
}

.knowledge-entry i {
  font-size: 1rem;
}

.topbar-theme {
  width: 44px;
  height: 44px;
}

.topbar-theme :deep(.theme-toggle-btn) {
  width: 44px;
  height: 44px;
  border-radius: 12px;
}

.content-viewport {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.demo-layout.sidebar-collapsed .sidebar-header {
  padding-left: 14px;
  padding-right: 14px;
}

.demo-layout.sidebar-collapsed .logo-container {
  gap: 0;
}

.demo-layout.sidebar-collapsed .sidebar-nav {
  padding-left: 10px;
  padding-right: 10px;
}

.demo-layout.sidebar-collapsed .sidebar-footer {
  justify-content: center;
  gap: 0;
  padding-left: 14px;
  padding-right: 14px;
}

.demo-layout.sidebar-collapsed .footer-icon {
  transform: scale(1);
}

/* ========== 响应式 ========== */
@media (max-width: 768px) {
  .demo-layout {
    --sidebar-expanded-width: 280px;
    --sidebar-collapsed-width: 72px;
    --sidebar-motion-duration: 800ms;
  }

  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    width: var(--sidebar-expanded-width);
    transform: translateX(0);
    transition:
      transform var(--sidebar-motion-duration) var(--sidebar-motion-ease),
      box-shadow var(--sidebar-motion-duration) var(--sidebar-motion-ease),
      border-color var(--sidebar-motion-duration) var(--sidebar-motion-ease),
      background 0.4s ease-in-out;
  }
  
  .sidebar.collapsed {
    width: var(--sidebar-expanded-width);
    transform: translateX(calc(-1 * (var(--sidebar-expanded-width) - var(--sidebar-collapsed-width))));
  }

  .main-content {
    width: 100%;
  }

  .demo-layout.sidebar-collapsed .main-content {
    width: calc(100% - var(--sidebar-collapsed-width));
    margin-left: var(--sidebar-collapsed-width);
  }

  .topbar {
    height: auto;
    min-height: 92px;
    align-items: flex-start;
    flex-direction: column;
    padding: 14px 18px;
  }

  .topbar-title-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .topbar-actions {
    width: 100%;
    justify-content: space-between;
    gap: 8px;
  }

  .topbar-date {
    flex: 1;
    justify-content: center;
  }
}
</style>
