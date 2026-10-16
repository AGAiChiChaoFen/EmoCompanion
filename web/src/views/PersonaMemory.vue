<template>
  <main class="memory-page">
    <div class="memory-shell">
      <section v-if="isMemoryLoading" class="memory-status-panel">
        <i class="bi bi-arrow-repeat"></i>
        <div>
          <strong>正在读取记忆数据</strong>
          <p>正在连接服务器上的个性化记忆服务。</p>
        </div>
      </section>

      <section v-else-if="memoryLoadError" class="memory-status-panel memory-status-error">
        <i class="bi bi-exclamation-triangle"></i>
        <div>
          <strong>记忆数据读取失败</strong>
          <p>{{ memoryLoadError }}</p>
        </div>
      </section>

      <template v-else>
      <nav class="archive-actions" aria-label="记忆档案入口">
        <button type="button" @click="openDrawer('profile')">
          <i class="bi bi-person-lines-fill"></i>
          <span><strong>当前画像</strong><small>查看最新有效状态</small></span>
          <i class="bi bi-chevron-right"></i>
        </button>
        <button type="button" @click="openDrawer('semantic')">
          <i class="bi bi-bookmark-check"></i>
          <span><strong>重要信息</strong><small>{{ retainedSemanticCount }} 条长期保留</small></span>
          <i class="bi bi-chevron-right"></i>
        </button>
        <button type="button" @click="openDrawer('episodic')">
          <i class="bi bi-journal-text"></i>
          <span><strong>生活主题</strong><small>{{ episodicRecords.length }} 个历史主题</small></span>
          <i class="bi bi-chevron-right"></i>
        </button>
        <button type="button" @click="openDrawer('procedural')">
          <i class="bi bi-check2-square"></i>
          <span><strong>习惯与目标</strong><small>{{ latestProceduralCount }} 项当前状态</small></span>
          <i class="bi bi-chevron-right"></i>
        </button>
      </nav>

      <section class="overview-stats">
        <div class="stat-card">
          <i class="bi bi-chat-dots-fill stat-icon"></i>
          <div class="stat-content">
            <span class="stat-value">{{ interactionCount }}</span>
            <span class="stat-label">对话轮次</span>
          </div>
        </div>
        <div class="stat-card">
          <i class="bi bi-calendar-check-fill stat-icon"></i>
          <div class="stat-content">
            <span class="stat-value">{{ sessions.length }}</span>
            <span class="stat-label">会话次数</span>
          </div>
        </div>
        <div class="stat-card">
          <i class="bi bi-bookmark-star-fill stat-icon"></i>
          <div class="stat-content">
            <span class="stat-value">{{ retainedSemanticCount }}</span>
            <span class="stat-label">保留信息</span>
          </div>
        </div>
        <div class="stat-card">
          <i class="bi bi-collection-fill stat-icon"></i>
          <div class="stat-content">
            <span class="stat-value">{{ episodicRecords.length }}</span>
            <span class="stat-label">生活主题</span>
          </div>
        </div>
      </section>

      <section class="chart-board" aria-label="个性化记忆图表">
        <article class="card insight-card chart-accent-green">
          <div class="insight-heading">
            <div>
              <div class="heading-with-icon">
                <span class="heading-icon heading-icon-green"><i class="bi bi-tags-fill"></i></span>
                <h2>长期关注主题</h2>
              </div>
              <p>来自已保留信息与生活主题的关键词统计</p>
            </div>
            <span class="chip chip-green">高频 {{ topicFrequency.length }} 项</span>
          </div>
          <div ref="topicChartRef" class="insight-chart" role="img" aria-label="长期记忆高频主题图"></div>
        </article>

        <article class="card insight-card chart-accent-purple">
          <div class="insight-heading">
            <div>
              <div class="heading-with-icon">
                <span class="heading-icon heading-icon-purple"><i class="bi bi-person-bounding-box"></i></span>
                <h2>性格分析</h2>
              </div>
              <p>当前大五人格特征</p>
            </div>
            <span class="chip chip-purple">当前状态</span>
          </div>
          <div v-if="hasPersonality" ref="personalityChartRef" class="insight-chart personality-chart" role="img" aria-label="性格数值雷达图，悬浮可查看具体分值"></div>
          <div v-else class="chart-empty-state"><i class="bi bi-person"></i><div><strong>尚未取得完整人格数据</strong><p>完成真实对话并更新记忆后显示有效分数。</p></div></div>
        </article>

        <article class="card insight-card chart-wide chart-accent-amber">
          <div class="insight-heading">
            <div>
              <div class="heading-with-icon">
                <span class="heading-icon heading-icon-amber"><i class="bi bi-graph-up-arrow"></i></span>
                <h2>性格变化趋势</h2>
              </div>
              <p>逐轮记录更新后的大五人格有效分数</p>
            </div>
            <span class="chip chip-amber">{{ personalityHistory.length ? `${personalityHistory.length} 个时间点` : '等待历史数据' }}</span>
          </div>
          <div
            v-if="personalityHistory.length"
            ref="personalityTrendChartRef"
            class="insight-chart personality-trend-chart"
            role="img"
            aria-label="大五人格随对话时间变化趋势图"
          ></div>
          <div v-else class="chart-empty-state">
            <i class="bi bi-clock-history"></i>
            <div><strong>尚未生成人格历史</strong><p>完成真实对话并更新记忆后，这里将展示逐轮变化趋势。</p></div>
          </div>
        </article>
      </section>
      </template>
    </div>

    <Teleport to="body">
      <div v-if="activeDrawer" class="drawer-overlay" @click="closeDrawer">
        <aside class="drawer" :class="{ 'profile-drawer': activeDrawer === 'profile' }" role="dialog" aria-modal="true" :aria-label="drawerTitle" @click.stop>
        <div class="drawer-header">
          <div>
            <small>{{ PERSONA_USER_NAME }} · 更新于 {{ latestProfile['update time'] || '暂无时间' }}</small>
            <h3>{{ drawerTitle }}</h3>
          </div>
          <button class="close-btn" type="button" aria-label="关闭" @click="closeDrawer">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
        <div class="drawer-body">
          <div v-if="activeDrawer === 'profile'" class="profile-content">
            <div class="profile-stat-grid" aria-label="记忆数据概览">
              <div v-for="stat in profileStats" :key="stat.label" class="profile-stat">
                <strong>{{ stat.value }}</strong>
                <span>{{ stat.label }}</span>
              </div>
            </div>

            <div class="profile-detail-layout">
              <section class="profile-fields" aria-label="当前画像内容">
                <div class="drawer-section-heading">
                  <div><h4>当前画像</h4><p>仅展示最新有效版本</p></div>
                  <span>V{{ profileVersions.length }}</span>
                </div>
                <div v-for="entry in displayProfileEntries" :key="entry.key" class="profile-item">
                  <label>{{ profileFieldLabel(entry.key) }}</label>
                  <div class="profile-value">{{ formatValue(entry.value) }}</div>
                </div>
              </section>

              <aside class="profile-version-panel" aria-label="画像版本记录">
                <div class="drawer-section-heading">
                  <div><h4>画像版本</h4><p>历次画像更新时间</p></div>
                  <span>{{ profileVersions.length }}版</span>
                </div>
                <div class="profile-version-list">
                  <div
                    v-for="version in profileVersions"
                    :key="version.id"
                    class="profile-version"
                    :class="{ current: version.isCurrent }"
                  >
                    <strong>V{{ version.number }}</strong>
                    <time>{{ version.label }}</time>
                  </div>
                </div>
              </aside>
            </div>
          </div>

          <div v-else-if="activeDrawer === 'semantic'">
            <div class="record-list">
              <div v-for="record in pagedSemanticRecords" :key="record.id" class="record-card">
                <div class="record-header">
                  <time>{{ record.time }}</time>
                </div>
                <div class="record-body">
                  <p class="content-text">{{ record.content }}</p>
                  <div v-if="record.keywords" class="keywords">
                    <span v-for="keyword in splitKeywords(record.keywords)" :key="keyword" class="keyword">{{ keyword }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="pagination-bar">
              <span class="pagination-info">共 {{ retainedSemanticRecords.length }} 条</span>
              <div class="pagination-controls">
                <button type="button" class="pagination-btn" :disabled="semanticPage <= 1" @click="semanticPage--">
                  <i class="bi bi-chevron-left"></i> 上一页
                </button>
                <span class="pagination-current">{{ semanticPage }} / {{ semanticPageCount }}</span>
                <button type="button" class="pagination-btn" :disabled="semanticPage >= semanticPageCount" @click="semanticPage++">
                  下一页 <i class="bi bi-chevron-right"></i>
                </button>
              </div>
            </div>
          </div>

          <div v-else-if="activeDrawer === 'episodic'">
            <div class="episode-list">
              <div v-for="record in pagedEpisodicRecords" :key="record.id" class="episode-card">
                <div class="episode-header">
                  <span class="episode-number">#{{ record.order }}</span>
                  <time>{{ record.time }}</time>
                </div>
                <p class="episode-summary">{{ record.topicSummary }}</p>
                <div v-if="record.keywords" class="keywords">
                  <span v-for="keyword in splitKeywords(record.keywords)" :key="keyword" class="keyword">{{ keyword }}</span>
                </div>
              </div>
            </div>
            <div class="pagination-bar">
              <span class="pagination-info">共 {{ episodicRecords.length }} 条</span>
              <div class="pagination-controls">
                <button type="button" class="pagination-btn" :disabled="episodicPage <= 1" @click="episodicPage--">
                  <i class="bi bi-chevron-left"></i> 上一页
                </button>
                <span class="pagination-current">{{ episodicPage }} / {{ episodicPageCount }}</span>
                <button type="button" class="pagination-btn" :disabled="episodicPage >= episodicPageCount" @click="episodicPage++">
                  下一页 <i class="bi bi-chevron-right"></i>
                </button>
              </div>
            </div>
          </div>

          <div v-else-if="activeDrawer === 'procedural'">
            <div class="latest-state-note">
              <span>当前有效状态</span>
              <time>更新于 {{ latestProceduralUpdateTime || '暂无时间' }}</time>
            </div>
            <div class="procedure-list">
              <div v-for="entry in latestProceduralEntries" :key="entry.key" class="procedure-card">
                <h3>{{ entry.title }}</h3>
                <p>{{ entry.content }}</p>
              </div>
              <p v-if="latestProceduralCount === 0" class="empty-state">暂无有效的习惯或目标记录</p>
            </div>
          </div>
        </div>
        </aside>
      </div>
    </Teleport>
  </main>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import * as echarts from 'echarts';
import { useTheme } from '../composables/useTheme';
import { buildApiUrl, getApiFetchErrorMessage } from '../utils/api';

import { personaUserName as PERSONA_USER_NAME } from '../composables/useAnalysisResult';
const { isNightTheme } = useTheme();

const SEMANTIC_PAGE_SIZE = 10;
const EPISODIC_PAGE_SIZE = 12;

const memoryData = ref(null);
const isMemoryLoading = ref(true);
const memoryLoadError = ref('');
const activeDrawer = ref(null);
const semanticPage = ref(1);
const episodicPage = ref(1);

const currentMemory = computed(() => memoryData.value || {});
const initialProfile = computed(() => currentMemory.value.init_profile || {});
const sessions = computed(() => Array.isArray(currentMemory.value.sessions) ? currentMemory.value.sessions : []);
const latestProfile = computed(() => sessions.value.at(-1)?.profile || initialProfile.value);

const latestProceduralSession = computed(() => [...sessions.value]
  .reverse()
  .find(session => session.ProceduralMemory && Object.keys(session.ProceduralMemory).length));
const latestProceduralMemory = computed(() => latestProceduralSession.value?.ProceduralMemory || {});
const latestProceduralUpdateTime = computed(() => latestProceduralSession.value?.profile?.['update time'] || '');


const latestProceduralEntries = computed(() => Object.entries(latestProceduralMemory.value).map(([key, value]) => ({
  key,
  title: key,
  content: value
})));
const latestProceduralCount = computed(() => latestProceduralEntries.value.length);

const semanticRecords = computed(() => sessions.value.flatMap((session, sessionIndex) =>
  (session.semantic_memory || []).map((memory, memoryIndex) => ({
    id: `semantic-${sessionIndex}-${memoryIndex}`,
    sessionIndex,
    memoryIndex,
    time: session.interactions?.[memoryIndex]?.[0]?.time || '',
    decision: Boolean(memory.decision),
    content: memory.content,
    keywords: memory.keywords
  }))
));

const episodicRecords = computed(() => sessions.value.flatMap((session, sessionIndex) =>
  (session.EpisodicMemory || []).map((memory, memoryIndex) => {
    const firstSource = memory.source_dialog_indices?.[0] ?? 0;
    return {
      id: `episode-${sessionIndex}-${memoryIndex}`,
      order: 0,
      sessionIndex,
      time: session.interactions?.[firstSource]?.[0]?.time || '',
      topicSummary: memory.topic_summary,
      keywords: memory.keywords,
      sourceIndices: memory.source_dialog_indices || []
    };
  })
).map((record, index) => ({ ...record, order: index + 1 })));

const personalityLabels = {
  openness: '开放性',
  conscientiousness: '尽责性',
  extraversion: '外向性',
  agreeableness: '宜人性',
  neuroticism: '情绪敏感性'
};

const personalityValues = computed(() => Object.entries(currentMemory.value.big_five_personality || {})
  .filter(([key, value]) => key in personalityLabels && value != null && value !== '' && Number.isFinite(Number(value)))
  .map(([key, value]) => ({
  key,
  label: personalityLabels[key] || key,
  value: Number(value)
})));
const hasPersonality = computed(() => personalityValues.value.length === Object.keys(personalityLabels).length);

const retainedSemanticRecords = computed(() => semanticRecords.value.filter(record => record.decision && record.content));
const retainedSemanticCount = computed(() => retainedSemanticRecords.value.length);
const semanticRetentionRate = computed(() => semanticRecords.value.length
  ? Number(((retainedSemanticCount.value / semanticRecords.value.length) * 100).toFixed(1))
  : 0);
const interactionCount = computed(() => sessions.value.reduce((total, session) => total + (session.interactions?.length || 0), 0));
const personalityHistory = computed(() => (Array.isArray(currentMemory.value.personality_history) ? currentMemory.value.personality_history : [])
  .filter(record => record && record.time && record.personality)
  .map((record, index) => ({
    index: index + 1,
    time: record.time,
    personality: Object.fromEntries(
      Object.keys(personalityLabels).map(key => [key, Number(record.personality[key])])
    )
  }))
  .filter(record => Object.values(record.personality).every(Number.isFinite)));
const profileStats = computed(() => [
  { label: '对话轮次', value: interactionCount.value },
  { label: '会话次数', value: sessions.value.length },
  { label: '保留信息', value: retainedSemanticCount.value },
  { label: '生活主题', value: episodicRecords.value.length }
]);
const profileSnapshots = computed(() => sessions.value
  .filter(session => session.profile && Object.keys(session.profile).length)
  .map(session => session.profile));
const profileVersions = computed(() => profileSnapshots.value
  .map((profile, index, records) => ({
    id: `profile-version-${index}`,
    number: index + 1,
    label: index === 0
      ? '初始版本'
      : profile?.['update time'] || '暂无时间',
    isCurrent: index === records.length - 1
  })));

const monthlyMemoryBuckets = computed(() => {
  const buckets = new Map();
  retainedSemanticRecords.value.forEach(record => addMonthlyMemory(buckets, record.time, 'semantic'));
  episodicRecords.value.forEach(record => addMonthlyMemory(buckets, record.time, 'episodic'));
  return buckets;
});

function addMonthlyMemory(buckets, time, type) {
  const month = String(time || '').slice(0, 7);
  if (!/^\d{4}-\d{2}$/.test(month)) return;
  if (!buckets.has(month)) {
    buckets.set(month, { month, semantic: 0, episodic: 0 });
  }
  buckets.get(month)[type] += 1;
}

const memoryTimeline = computed(() => [...monthlyMemoryBuckets.value.values()]
  .sort((left, right) => left.month.localeCompare(right.month)));

const topicCounts = computed(() => {
  const counts = new Map();
  [...retainedSemanticRecords.value, ...episodicRecords.value].forEach(record => {
    splitKeywords(record.keywords).forEach(keyword => {
      counts.set(keyword, (counts.get(keyword) || 0) + 1);
    });
  });
  return counts;
});

const topicFrequency = computed(() => [...topicCounts.value.entries()]
  .map(([name, count]) => ({ name, count }))
  .sort((left, right) => right.count - left.count || left.name.localeCompare(right.name, 'zh-CN'))
  .slice(0, 8));

const episodeScaleCounts = computed(() => {
  const counts = new Map();
  episodicRecords.value.forEach(record => {
    const sourceCount = record.sourceIndices.length;
    counts.set(sourceCount, (counts.get(sourceCount) || 0) + 1);
  });
  return counts;
});
const episodeScaleDistribution = computed(() => [...episodeScaleCounts.value.entries()]
  .map(([sourceCount, topicCount]) => ({ sourceCount, topicCount }))
  .sort((left, right) => left.sourceCount - right.sourceCount));

const topicEvolutionTopics = computed(() => topicFrequency.value.map(item => item.name));
const topicEvolutionCounts = computed(() => {
  const counts = new Map();
  [...retainedSemanticRecords.value, ...episodicRecords.value].forEach(record => {
    const month = String(record.time || '').slice(0, 7);
    if (!/^\d{4}-\d{2}$/.test(month)) return;
    const keywords = new Set(splitKeywords(record.keywords));
    keywords.forEach(keyword => {
      if (!topicEvolutionTopics.value.includes(keyword)) return;
      const id = `${month}|${keyword}`;
      counts.set(id, (counts.get(id) || 0) + 1);
    });
  });
  return counts;
});
const topicEvolutionData = computed(() => memoryTimeline.value.flatMap((item, monthIndex) =>
  topicEvolutionTopics.value.map((topic, topicIndex) => [
    monthIndex,
    topicIndex,
    topicEvolutionCounts.value.get(`${item.month}|${topic}`) || 0
  ])
));

const profileFieldKeys = computed(() => [...new Set(profileSnapshots.value.flatMap(profile => Object.keys(profile)))]
  .filter(key => !['name', 'update time'].includes(key)));
const profileChangeCounts = computed(() => profileSnapshots.value.map((profile, index) => ({
  version: `V${index + 1}`,
  count: index === 0
    ? 0
    : profileFieldKeys.value.filter(key => stableValue(profile[key]) !== stableValue(profileSnapshots.value[index - 1]?.[key])).length
})));
const profileChangeHeatmapData = computed(() => profileSnapshots.value.flatMap((profile, versionIndex) =>
  profileFieldKeys.value.map((field, fieldIndex) => {
    const hasValue = profile[field] !== undefined && profile[field] !== null && profile[field] !== '';
    const changed = versionIndex > 0
      && stableValue(profile[field]) !== stableValue(profileSnapshots.value[versionIndex - 1]?.[field]);
    return [versionIndex, fieldIndex, versionIndex === 0 && hasValue ? 2 : changed ? 1 : 0];
  })
));

const proceduralEvolution = computed(() => sessions.value.map((session, index) => {
  const current = session.ProceduralMemory || {};
  const previous = sessions.value[index - 1]?.ProceduralMemory || {};
  const currentKeys = Object.keys(current);
  const previousKeys = Object.keys(previous);
  return {
    version: `V${index + 1}`,
    added: currentKeys.filter(key => !(key in previous)).length,
    updated: currentKeys.filter(key => key in previous && stableValue(current[key]) !== stableValue(previous[key])).length,
    removed: previousKeys.filter(key => !(key in current)).length,
    active: currentKeys.length
  };
}));

const dailyMemoryCounts = computed(() => {
  const counts = new Map();
  [...retainedSemanticRecords.value, ...episodicRecords.value].forEach(record => {
    const date = String(record.time || '').slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return;
    counts.set(date, (counts.get(date) || 0) + 1);
  });
  return counts;
});
const memoryCalendarData = computed(() => [...dailyMemoryCounts.value.entries()].sort(([left], [right]) => left.localeCompare(right)));
const memoryActiveDays = computed(() => memoryCalendarData.value.length);
const memoryCalendarRange = computed(() => memoryCalendarData.value.length
  ? [memoryCalendarData.value[0][0], memoryCalendarData.value.at(-1)[0]]
  : ['2026-01-01', '2026-12-31']);

const displayProfileEntries = computed(() => {
  const entries = Object.entries(latestProfile.value).map(([key, value]) => ({ key, value }));
  return entries.filter(entry => entry.key !== 'update time');
});

const semanticPageCount = computed(() => Math.max(1, Math.ceil(retainedSemanticRecords.value.length / SEMANTIC_PAGE_SIZE)));
const pagedSemanticRecords = computed(() => paginate(retainedSemanticRecords.value, semanticPage.value, SEMANTIC_PAGE_SIZE));
const episodicPageCount = computed(() => Math.max(1, Math.ceil(episodicRecords.value.length / EPISODIC_PAGE_SIZE)));
const pagedEpisodicRecords = computed(() => paginate(episodicRecords.value, episodicPage.value, EPISODIC_PAGE_SIZE));

const drawerTitles = {
  profile: '当前用户画像',
  semantic: '重要信息',
  episodic: '生活主题',
  procedural: '习惯与目标'
};
const drawerTitle = computed(() => drawerTitles[activeDrawer.value] || '');

const profileLabels = {
  name: '姓名',
  'system context': '使用场景',
  'requirements or expectations': '回应要求',
  'communication preferences': '交流偏好',
  family: '家庭关系',
  social: '社会关系',
  hobbies: '兴趣爱好',
  'update time': '更新时间'
};

function profileFieldLabel(key) {
  return profileLabels[key] || key;
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join('、');
  if (value && typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value ?? '');
}

function stableValue(value) {
  if (Array.isArray(value)) return JSON.stringify(value);
  if (value && typeof value === 'object') {
    return JSON.stringify(Object.keys(value).sort().reduce((result, key) => {
      result[key] = value[key];
      return result;
    }, {}));
  }
  return String(value ?? '');
}

function splitKeywords(value) {
  return String(value || '')
    .split(/[,，、]/)
    .map(item => item.trim())
    .filter(Boolean);
}

function paginate(records, page, pageSize) {
  const start = (page - 1) * pageSize;
  return records.slice(start, start + pageSize);
}

function openDrawer(type) {
  activeDrawer.value = type;
}

function closeDrawer() {
  activeDrawer.value = null;
}

function handleDrawerKeydown(event) {
  if (event.key === 'Escape') closeDrawer();
}

function handleDocumentPointerDown(event) {
  if (!activeDrawer.value) return;
  if (event.target instanceof Element && event.target.closest('.drawer')) return;
  closeDrawer();
}

async function loadMemoryData() {
  isMemoryLoading.value = true;
  memoryLoadError.value = '';
  activeDrawer.value = null;

  try {
    const response = await fetch(
      buildApiUrl(`/persona-api/v1/users/${encodeURIComponent(PERSONA_USER_NAME)}/memory`),
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
      }
    );
    const payload = await response.json().catch(() => null);

    if (!response.ok) {
      throw new Error(payload?.detail || payload?.message || `服务返回 ${response.status}`);
    }
    if (!payload || typeof payload !== 'object' || !payload.data || typeof payload.data !== 'object') {
      throw new Error('记忆服务返回的数据格式不正确。');
    }

    memoryData.value = payload.data;
  } catch (error) {
    memoryData.value = null;
    memoryLoadError.value = getApiFetchErrorMessage(error);
  } finally {
    isMemoryLoading.value = false;
  }
}


const lightPalette = ['#8b5cf6', '#06b6d4', '#f59e0b', '#ec4899', '#10b981'];
const nightPalette = ['#a78bfa', '#67e8f9', '#fbbf24', '#f472b6', '#34d399'];
const topicLightPalette = ['#10b981', '#3b82f6', '#f59e0b', '#ec4899', '#8b5cf6', '#06b6d4', '#ef4444', '#6366f1'];
const topicNightPalette = ['#34d399', '#60a5fa', '#fbbf24', '#f472b6', '#a78bfa', '#67e8f9', '#f87171', '#818cf8'];

const personalityPalette = lightPalette;
const topicPalette = topicLightPalette;

const personalityChartRef = ref(null);
const personalityTrendChartRef = ref(null);
const topicChartRef = ref(null);
let personalityChart = null;
let personalityTrendChart = null;
let topicChart = null;
let chartResizeObserver = null;

function personalityOption(night) {
  const text = night ? '#9ca3af' : '#6b7280';
  const grid = night ? 'rgba(75,85,99,.3)' : 'rgba(209,213,219,.5)';
  const colors = night
    ? ['#a78bfa', '#67e8f9', '#fbbf24', '#f472b6', '#34d399']
    : ['#8b5cf6', '#06b6d4', '#f59e0b', '#ec4899', '#10b981'];
  return {
    animationDuration: 600,
    tooltip: {
      trigger: 'item',
      confine: true,
      formatter: () => [
        '<div style="font-weight:600;margin-bottom:7px">当前性格特征</div>',
        ...personalityValues.value.map((item, index) => (
          `<div style="display:flex;justify-content:space-between;gap:28px;line-height:1.8">`+
          `<span style="color:${colors[index]};font-weight:600">${item.label}</span><strong style="color:${colors[index]}">${item.value.toFixed(2)}</strong></div>`
        ))
      ].join('')
    },
    legend: {
      bottom: 0,
      left: 'center',
      data: personalityValues.value.map((item, index) => ({
        name: item.label,
        itemStyle: { color: colors[index] }
      })),
      textStyle: { color: text, fontSize: 11 },
      itemWidth: 10,
      itemHeight: 10,
      icon: 'circle'
    },
    radar: {
      center: ['50%', '46%'],
      radius: '68%',
      splitNumber: 4,
      indicator: personalityValues.value.map((item, index) => ({
        name: item.label,
        max: 5,
        color: colors[index]
      })),
      axisName: {
        color: text,
        fontSize: 14,
        fontWeight: 600
      },
      splitArea: { show: false },
      splitLine: { lineStyle: { color: grid, width: 2 } },
      axisLine: { lineStyle: { color: grid } }
    },
    series: [{
      type: 'radar',
      symbol: 'circle',
      symbolSize: 8,
      data: [{ value: personalityValues.value.map(item => item.value) }],
      lineStyle: { color: colors[0], width: 3 },
      itemStyle: {
        color: '#fff',
        borderColor: colors[0],
        borderWidth: 3
      },
      areaStyle: {
        color: {
          type: 'radial',
          x: 0.5,
          y: 0.5,
          r: 0.5,
          colorStops: [
            { offset: 0, color: night ? 'rgba(167, 139, 250, 0.4)' : 'rgba(139, 92, 246, 0.3)' },
            { offset: 1, color: night ? 'rgba(167, 139, 250, 0.1)' : 'rgba(139, 92, 246, 0.05)' }
          ]
        }
      }
    }]
  };
}

function personalityTrendOption(night) {
  const text = night ? '#9ca3af' : '#64748b';
  const grid = night ? 'rgba(75,85,99,.26)' : 'rgba(226,232,240,.9)';
  const colors = night
    ? ['#a78bfa', '#67e8f9', '#fbbf24', '#f472b6', '#34d399']
    : ['#8b5cf6', '#06b6d4', '#f59e0b', '#ec4899', '#10b981'];
  const visibleStart = personalityHistory.value.length > 40
    ? Math.max(0, 100 - (40 / personalityHistory.value.length) * 100)
    : 0;
  return {
    animationDuration: 650,
    color: colors,
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: params => {
        const time = params[0]?.axisValue || '';
        const rows = params.map(p =>
          `<div style="display:flex;justify-content:space-between;gap:24px;line-height:1.9">` +
          `<span style="display:flex;align-items:center;gap:6px">` +
          `<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${p.color}"></span>` +
          `${p.seriesName}</span>` +
          `<strong style="color:${p.color}">${Number(p.value).toFixed(2)}</strong></div>`
        ).join('');
        return `<div style="font-size:11px;margin-bottom:6px;color:#9ca3af">${time}</div>${rows}`;
      }
    },
    legend: {
      top: 0,
      right: 4,
      textStyle: { color: text, fontSize: 12, fontWeight: 600 },
      itemWidth: 20,
      itemHeight: 4,
      itemStyle: { borderRadius: 2 }
    },
    grid: { top: 44, right: 22, bottom: 52, left: 42 },
    dataZoom: [
      { type: 'inside', start: visibleStart, end: 100 },
      {
        type: 'slider',
        start: visibleStart,
        end: 100,
        height: 16,
        bottom: 4,
        borderColor: 'transparent',
        fillerColor: night ? 'rgba(167, 139, 250, .2)' : 'rgba(139, 92, 246, .15)',
        handleStyle: {
          color: night ? '#a78bfa' : '#8b5cf6'
        }
      }
    ],
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: personalityHistory.value.map(record => record.time),
      axisLine: { lineStyle: { color: grid } },
      axisTick: { show: false },
      axisLabel: {
        color: text,
        fontSize: 10,
        formatter: value => String(value).slice(5, 16),
        hideOverlap: true
      }
    },
    yAxis: {
      type: 'value',
      min: 1,
      max: 5,
      interval: 1,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: text, fontSize: 11 },
      splitLine: { lineStyle: { color: grid } }
    },
    series: Object.entries(personalityLabels).map(([key, label], index) => ({
      name: label,
      type: 'line',
      smooth: 0.3,
      showSymbol: personalityHistory.value.length <= 40,
      symbolSize: 6,
      lineStyle: { width: 3 },
      itemStyle: {
        color: colors[index],
        borderColor: '#fff',
        borderWidth: 2
      },
      emphasis: {
        itemStyle: {
          borderWidth: 3,
          shadowBlur: 10,
          shadowColor: colors[index]
        }
      },
      data: personalityHistory.value.map(record => record.personality[key])
    }))
  };
}

function topicOption(night) {
  const text = night ? '#d1d5db' : '#4b5563';
  const grid = night ? 'rgba(75,85,99,.26)' : 'rgba(226,232,240,.9)';
  const colors = night
    ? ['#a78bfa', '#67e8f9', '#fbbf24', '#f472b6', '#34d399', '#60a5fa', '#f87171', '#818cf8']
    : ['#8b5cf6', '#06b6d4', '#f59e0b', '#ec4899', '#10b981', '#3b82f6', '#ef4444', '#6366f1'];
  const sortedTopics = [...topicFrequency.value].reverse();
  return {
    animationDuration: 650,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: params => {
        const item = params[0];
        const color = colors[(sortedTopics.length - 1 - item.dataIndex) % colors.length];
        return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">` +
          `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color}"></span>` +
          `<strong style="color:${color}">${item.name}</strong></div>` +
          `<div style="padding-left:18px;color:${text}">出现频次：<strong>${item.value}</strong> 次</div>`;
      }
    },
    legend: {
      top: 0,
      left: 'center',
      type: 'scroll',
      data: sortedTopics.map((item, index) => ({
        name: item.name,
        itemStyle: { color: colors[(sortedTopics.length - 1 - index) % colors.length] }
      })),
      textStyle: { color: text, fontSize: 11 },
      itemWidth: 10,
      itemHeight: 10,
      icon: 'circle',
      pageIconColor: text,
      pageTextStyle: { color: text }
    },
    grid: { top: 36, right: 56, bottom: 8, left: 90 },
    xAxis: {
      type: 'value',
      minInterval: 1,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: text, fontSize: 11 },
      splitLine: { lineStyle: { color: grid } }
    },
    yAxis: {
      type: 'category',
      data: sortedTopics.map(item => item.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: text,
        fontSize: 12,
        formatter: value => value.length > 7 ? `${value.slice(0, 7)}…` : value
      }
    },
    series: [{
      type: 'bar',
      data: sortedTopics.map((item, index) => ({
        value: item.count,
        itemStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [
              { offset: 0, color: colors[index % colors.length] },
              { offset: 1, color: colors[index % colors.length] + 'bb' }
            ]
          },
          borderRadius: [0, 8, 8, 0]
        }
      })),
      barWidth: 14,
      label: {
        show: true,
        position: 'right',
        color: text,
        fontSize: 11,
        fontWeight: 600,
        formatter: params => `${params.value}次`
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 2,
          shadowColor: 'rgba(0,0,0,0.2)'
        }
      }
    }]
  };
}

function resizeCharts() {
  personalityChart?.resize();
  personalityTrendChart?.resize();
  topicChart?.resize();
}

function updateCharts() {
  if (!memoryData.value) return;
  personalityChart?.setOption(personalityOption(isNightTheme.value), true);
  if (personalityTrendChart) {
    personalityTrendChart.setOption(personalityTrendOption(isNightTheme.value), true);
  }
  topicChart?.setOption(topicOption(isNightTheme.value), true);
}

function initCharts() {
  if (!memoryData.value) return;
  if (personalityChartRef.value && !personalityChart) {
    personalityChart = echarts.init(personalityChartRef.value);
  }
  if (personalityTrendChartRef.value && !personalityTrendChart) {
    personalityTrendChart = echarts.init(personalityTrendChartRef.value);
  }
  if (topicChartRef.value && !topicChart) {
    topicChart = echarts.init(topicChartRef.value);
  }
  updateCharts();

  if (typeof ResizeObserver !== 'undefined' && !chartResizeObserver) {
    chartResizeObserver = new ResizeObserver(resizeCharts);
    [
      personalityChartRef.value,
      personalityTrendChartRef.value,
      topicChartRef.value
    ]
      .filter(Boolean)
      .forEach(element => chartResizeObserver.observe(element));
  }
}

watch(isNightTheme, () => nextTick(updateCharts));

onMounted(async () => {
  window.addEventListener('resize', resizeCharts);
  window.addEventListener('keydown', handleDrawerKeydown);
  document.addEventListener('pointerdown', handleDocumentPointerDown, true);
  await loadMemoryData();
  await nextTick();
  initCharts();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts);
  window.removeEventListener('keydown', handleDrawerKeydown);
  document.removeEventListener('pointerdown', handleDocumentPointerDown, true);
  chartResizeObserver?.disconnect();
  personalityChart?.dispose();
  personalityTrendChart?.dispose();
  topicChart?.dispose();
  personalityChart = null;
  personalityTrendChart = null;
  topicChart = null;
});
</script>

<style scoped>
.memory-page {
  --bg-primary: #f9fafb;
  --bg-secondary: #ffffff;
  --text-primary: #111827;
  --text-secondary: #6b7280;
  --text-tertiary: #9ca3af;
  --border-color: #e5e7eb;
  --border-light: #f3f4f6;
  --primary: #3b82f6;
  --primary-light: #dbeafe;
  --success: #10b981;
  --success-light: #d1fae5;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  background: linear-gradient(150deg, #f0ebff 0%, #e8f4ff 30%, #f5fdf7 65%, #fff5f0 100%);
  color: var(--text-primary);
}

:global([data-theme='night']) .memory-page {
  --bg-primary: #111827;
  --bg-secondary: #1f2937;
  --text-primary: #f9fafb;
  --text-secondary: #9ca3af;
  --text-tertiary: #6b7280;
  --border-color: #374151;
  --border-light: #2d3748;
  --primary: #60a5fa;
  --primary-light: #1e3a8a;
  --success: #34d399;
  --success-light: #064e3b;
  background: linear-gradient(150deg, #120e22 0%, #111827 45%, #0c1a14 100%);
}

* { box-sizing: border-box; }
button, select { font: inherit; }
h1, h2, h3, p { margin: 0; }


.memory-shell {
  width: 100%;
  max-width: 1500px;
  margin: 0 auto;
  padding: 20px 24px 40px;
}

.memory-status-panel {
  min-height: 420px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 18px;
  box-shadow: 0 18px 48px rgba(59, 130, 246, 0.08);
}

.memory-status-panel i {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  color: #3b82f6;
  font-size: 22px;
  background: rgba(59, 130, 246, 0.12);
  border-radius: 14px;
}

.memory-status-panel strong {
  display: block;
  margin-bottom: 6px;
  color: var(--text-primary);
  font-size: 17px;
}

.memory-status-panel p {
  max-width: 520px;
  line-height: 1.7;
}

.memory-status-error i {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.12);
}

.overview-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  transition: transform .2s ease, box-shadow .2s ease;
  position: relative;
  overflow: hidden;
}

.stat-card::before {
  display: none;
}

.stat-card:nth-child(1) {
  --stat-color-1: #8b5cf6;
  --stat-color-2: #a78bfa;
  background: linear-gradient(135deg, #faf7ff 0%, rgba(139, 92, 246, 0.07) 100%);
  border-color: rgba(139, 92, 246, 0.18);
}

.stat-card:nth-child(2) {
  --stat-color-1: #06b6d4;
  --stat-color-2: #67e8f9;
  background: linear-gradient(135deg, #f0fdff 0%, rgba(6, 182, 212, 0.07) 100%);
  border-color: rgba(6, 182, 212, 0.18);
}

.stat-card:nth-child(3) {
  --stat-color-1: #f59e0b;
  --stat-color-2: #fbbf24;
  background: linear-gradient(135deg, #fffdf0 0%, rgba(245, 158, 11, 0.07) 100%);
  border-color: rgba(245, 158, 11, 0.18);
}

.stat-card:nth-child(4) {
  --stat-color-1: #ec4899;
  --stat-color-2: #f472b6;
  background: linear-gradient(135deg, #fff0f7 0%, rgba(236, 72, 153, 0.07) 100%);
  border-color: rgba(236, 72, 153, 0.18);
}

:global([data-theme='night']) .stat-card:nth-child(1) {
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.1) 0%, rgba(167, 139, 250, 0.04) 100%);
  border-color: rgba(167, 139, 250, 0.22);
}

:global([data-theme='night']) .stat-card:nth-child(2) {
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.1) 0%, rgba(103, 232, 249, 0.04) 100%);
  border-color: rgba(103, 232, 249, 0.22);
}

:global([data-theme='night']) .stat-card:nth-child(3) {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(251, 191, 36, 0.04) 100%);
  border-color: rgba(251, 191, 36, 0.22);
}

:global([data-theme='night']) .stat-card:nth-child(4) {
  background: linear-gradient(135deg, rgba(236, 72, 153, 0.1) 0%, rgba(244, 114, 182, 0.04) 100%);
  border-color: rgba(244, 114, 182, 0.22);
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 28px rgba(15, 23, 42, .12);
}

.stat-icon {
  flex-shrink: 0;
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  font-size: 28px;
  position: relative;
}

.stat-card:nth-child(1) .stat-icon {
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(167, 139, 250, 0.15));
  color: #8b5cf6;
}

.stat-card:nth-child(2) .stat-icon {
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.1), rgba(103, 232, 249, 0.15));
  color: #06b6d4;
}

.stat-card:nth-child(3) .stat-icon {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.1), rgba(251, 191, 36, 0.15));
  color: #f59e0b;
}

.stat-card:nth-child(4) .stat-icon {
  background: linear-gradient(135deg, rgba(236, 72, 153, 0.1), rgba(244, 114, 182, 0.15));
  color: #ec4899;
}

:global([data-theme='night']) .stat-card:nth-child(1) .stat-icon {
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(167, 139, 250, 0.2));
  color: #a78bfa;
}

:global([data-theme='night']) .stat-card:nth-child(2) .stat-icon {
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.15), rgba(103, 232, 249, 0.2));
  color: #67e8f9;
}

:global([data-theme='night']) .stat-card:nth-child(3) .stat-icon {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(251, 191, 36, 0.2));
  color: #fbbf24;
}

:global([data-theme='night']) .stat-card:nth-child(4) .stat-icon {
  background: linear-gradient(135deg, rgba(236, 72, 153, 0.15), rgba(244, 114, 182, 0.2));
  color: #f472b6;
}

.stat-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  color: var(--text-primary);
  font-size: 32px;
  font-weight: 800;
  line-height: 1.2;
  background: linear-gradient(135deg, var(--stat-color-1), var(--stat-color-2));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.stat-label {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.archive-actions {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.archive-actions button {
  min-width: 0;
  min-height: 76px;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 16px;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border: 2px solid var(--border-color);
  border-radius: 12px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  transition: all .25s ease;
  position: relative;
  overflow: hidden;
}

.archive-actions button::before { display: none; }

.archive-actions button:hover {
  border-color: var(--primary);
  box-shadow: 0 6px 20px rgba(15, 23, 42, .08);
  transform: translateX(2px);
}

.archive-actions button > i:first-child {
  font-size: 22px;
  text-align: center;
  transition: transform .25s ease;
}

.archive-actions button:nth-child(1) {
  background: linear-gradient(135deg, #faf7ff 0%, rgba(139, 92, 246, 0.05) 100%);
  border-color: rgba(139, 92, 246, 0.15);
}

.archive-actions button:nth-child(2) {
  background: linear-gradient(135deg, #f0fdff 0%, rgba(6, 182, 212, 0.05) 100%);
  border-color: rgba(6, 182, 212, 0.15);
}

.archive-actions button:nth-child(3) {
  background: linear-gradient(135deg, #fffdf0 0%, rgba(245, 158, 11, 0.05) 100%);
  border-color: rgba(245, 158, 11, 0.15);
}

.archive-actions button:nth-child(4) {
  background: linear-gradient(135deg, #fff0f7 0%, rgba(236, 72, 153, 0.05) 100%);
  border-color: rgba(236, 72, 153, 0.15);
}

:global([data-theme='night']) .archive-actions button:nth-child(1) {
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.08) 0%, rgba(167, 139, 250, 0.03) 100%);
  border-color: rgba(167, 139, 250, 0.2);
}

:global([data-theme='night']) .archive-actions button:nth-child(2) {
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.08) 0%, rgba(103, 232, 249, 0.03) 100%);
  border-color: rgba(103, 232, 249, 0.2);
}

:global([data-theme='night']) .archive-actions button:nth-child(3) {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, rgba(251, 191, 36, 0.03) 100%);
  border-color: rgba(251, 191, 36, 0.2);
}

:global([data-theme='night']) .archive-actions button:nth-child(4) {
  background: linear-gradient(135deg, rgba(236, 72, 153, 0.08) 0%, rgba(244, 114, 182, 0.03) 100%);
  border-color: rgba(244, 114, 182, 0.2);
}

.archive-actions button:nth-child(1) > i:first-child {
  color: #8b5cf6;
}

.archive-actions button:nth-child(2) > i:first-child {
  color: #06b6d4;
}

.archive-actions button:nth-child(3) > i:first-child {
  color: #f59e0b;
}

.archive-actions button:nth-child(4) > i:first-child {
  color: #ec4899;
}

:global([data-theme='night']) .archive-actions button:nth-child(1) > i:first-child {
  color: #a78bfa;
}

:global([data-theme='night']) .archive-actions button:nth-child(2) > i:first-child {
  color: #67e8f9;
}

:global([data-theme='night']) .archive-actions button:nth-child(3) > i:first-child {
  color: #fbbf24;
}

:global([data-theme='night']) .archive-actions button:nth-child(4) > i:first-child {
  color: #f472b6;
}

.archive-actions button:hover > i:first-child {
  transform: scale(1.1);
}

.archive-actions button > i:last-child {
  color: var(--text-tertiary);
  font-size: 12px;
  transition: transform .25s ease;
}

.archive-actions button:hover > i:last-child {
  transform: translateX(3px);
}

.archive-actions span { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.archive-actions strong { font-size: 14px; font-weight: 600; }
.archive-actions small { color: var(--text-tertiary); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.chart-board {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.chart-wide { grid-column: 1 / -1; }

.insight-card {
  min-width: 0;
  padding: 20px 22px 14px;
  position: relative;
  overflow: hidden;
}

.insight-card::before {
  display: none;
}

.insight-card:nth-child(1) {
  --card-accent-1: #10b981;
  --card-accent-2: #34d399;
}

.insight-card:nth-child(2) {
  --card-accent-1: #8b5cf6;
  --card-accent-2: #a78bfa;
}

.insight-card:nth-child(3) {
  --card-accent-1: #f59e0b;
  --card-accent-2: #fbbf24;
}

.insight-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
}

.insight-heading h2 {
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 600;
}

.insight-heading p {
  margin-top: 5px;
  color: var(--text-tertiary);
  font-size: 12px;
}

.insight-heading > span:not(.chip) {
  flex-shrink: 0;
  padding: 4px 9px;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  color: var(--text-secondary);
  font-size: 11px;
}

.insight-heading > .warning-chip {
  border-color: rgba(225, 29, 72, .18);
  background: rgba(225, 29, 72, .08);
  color: #be123c;
}

:global([data-theme='night']) .insight-heading > .warning-chip { color: #fb7185; }

.heading-with-icon {
  display: flex;
  align-items: center;
  gap: 10px;
}

.heading-icon {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  font-size: 16px;
}

.heading-icon-green {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
}

.heading-icon-purple {
  background: rgba(139, 92, 246, 0.12);
  color: #8b5cf6;
}

.heading-icon-amber {
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
}

:global([data-theme='night']) .heading-icon-green {
  background: rgba(52, 211, 153, 0.15);
  color: #34d399;
}

:global([data-theme='night']) .heading-icon-purple {
  background: rgba(167, 139, 250, 0.15);
  color: #a78bfa;
}

:global([data-theme='night']) .heading-icon-amber {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}

.chip {
  flex-shrink: 0;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid;
}

.chip-green {
  background: rgba(16, 185, 129, 0.08);
  color: #059669;
  border-color: rgba(16, 185, 129, 0.25);
}

.chip-purple {
  background: rgba(139, 92, 246, 0.08);
  color: #7c3aed;
  border-color: rgba(139, 92, 246, 0.25);
}

.chip-amber {
  background: rgba(245, 158, 11, 0.08);
  color: #d97706;
  border-color: rgba(245, 158, 11, 0.25);
}

:global([data-theme='night']) .chip-green {
  background: rgba(52, 211, 153, 0.1);
  color: #34d399;
  border-color: rgba(52, 211, 153, 0.3);
}

:global([data-theme='night']) .chip-purple {
  background: rgba(167, 139, 250, 0.1);
  color: #a78bfa;
  border-color: rgba(167, 139, 250, 0.3);
}

:global([data-theme='night']) .chip-amber {
  background: rgba(251, 191, 36, 0.1);
  color: #fbbf24;
  border-color: rgba(251, 191, 36, 0.3);
}

.chart-accent-green {
  border-top: 3px solid #10b981;
  background: linear-gradient(170deg, rgba(16, 185, 129, 0.05) 0%, var(--bg-secondary) 45%);
}

.chart-accent-purple {
  border-top: 3px solid #8b5cf6;
  background: linear-gradient(170deg, rgba(139, 92, 246, 0.05) 0%, var(--bg-secondary) 45%);
}

.chart-accent-amber {
  border-top: 3px solid #f59e0b;
  background: linear-gradient(170deg, rgba(245, 158, 11, 0.05) 0%, var(--bg-secondary) 45%);
}

:global([data-theme='night']) .chart-accent-green {
  border-top-color: #34d399;
  background: linear-gradient(170deg, rgba(52, 211, 153, 0.07) 0%, var(--bg-secondary) 45%);
}

:global([data-theme='night']) .chart-accent-purple {
  border-top-color: #a78bfa;
  background: linear-gradient(170deg, rgba(167, 139, 250, 0.07) 0%, var(--bg-secondary) 45%);
}

:global([data-theme='night']) .chart-accent-amber {
  border-top-color: #fbbf24;
  background: linear-gradient(170deg, rgba(251, 191, 36, 0.07) 0%, var(--bg-secondary) 45%);
}

.insight-chart {
  width: 100%;
  height: 260px;
}

.personality-chart { height: 300px; }
.personality-trend-chart { height: 300px; }
.heatmap-chart { height: 320px; }
.profile-heatmap-chart { height: 280px; }
.calendar-chart { height: 250px; }

.chart-empty-state {
  min-height: 230px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  border: 1px dashed var(--border-color);
  border-radius: 9px;
  background: var(--bg-primary);
  color: var(--text-secondary);
}

.chart-empty-state > i { color: var(--primary); font-size: 25px; }
.chart-empty-state strong { display: block; margin-bottom: 5px; color: var(--text-primary); font-size: 14px; }
.chart-empty-state p { color: var(--text-tertiary); font-size: 12px; }

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 24px;
}

.latest-state-note span {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--success-light);
  color: var(--success);
  font-size: 12px;
  font-weight: 600;
}

.profile-item {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-light);
}

.profile-content { min-width: 0; }

.profile-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 20px;
  padding: 14px 8px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-primary);
}

.profile-stat {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-right: 1px solid var(--border-color);
}

.profile-stat:last-child { border-right: none; }
.profile-stat strong { color: var(--primary); font-size: 24px; line-height: 1.1; font-weight: 700; }
.profile-stat span { color: var(--text-secondary); font-size: 12px; }

.profile-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 350px;
  gap: 20px;
  align-items: start;
}

.profile-fields,
.profile-version-panel {
  min-width: 0;
  padding: 16px 18px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
}

.drawer-section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.drawer-section-heading h4 { margin: 0; color: var(--text-primary); font-size: 15px; }
.drawer-section-heading p { margin-top: 4px; color: var(--text-tertiary); font-size: 11px; }
.drawer-section-heading > span {
  padding: 3px 8px;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  color: var(--text-secondary);
  font-size: 11px;
}

.profile-version-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.profile-version {
  min-width: 0;
  min-height: 54px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 7px 5px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--bg-secondary);
}

.profile-version strong { color: var(--text-primary); font-size: 12px; }
.profile-version time {
  width: 100%;
  overflow: hidden;
  color: var(--text-tertiary);
  font-size: 9px;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-version.current {
  border-color: var(--primary);
  background: var(--primary-light);
}

.profile-version.current strong,
.profile-version.current time { color: var(--primary); }

.profile-item label {
  font-size: 12px;
  color: var(--text-tertiary);
  padding-top: 2px;
}

.profile-value {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.record-list { display: flex; flex-direction: column; gap: 12px; }

.record-card {
  border: 2px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
  transition: all .25s ease;
}

.record-card:hover {
  border-color: #8b5cf6;
  box-shadow: 0 6px 20px rgba(139, 92, 246, 0.1);
  transform: translateY(-2px);
}

.record-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.05), rgba(167, 139, 250, 0.08));
  border-bottom: 1px solid var(--border-light);
}

:global([data-theme='night']) .record-header {
  background: linear-gradient(135deg, rgba(167, 139, 250, 0.08), rgba(167, 139, 250, 0.12));
}

.record-header time {
  font-size: 12px;
  color: var(--text-tertiary);
}

.record-body { padding: 12px 14px; }

.content-text {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
  line-height: 1.6;
}

.keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.keyword {
  padding: 4px 12px;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(167, 139, 250, 0.15));
  color: #8b5cf6;
  border: 1px solid rgba(139, 92, 246, 0.2);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  transition: all .2s ease;
}

.keyword:hover {
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(167, 139, 250, 0.2));
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(139, 92, 246, 0.2);
}

:global([data-theme='night']) .keyword {
  background: linear-gradient(135deg, rgba(167, 139, 250, 0.15), rgba(167, 139, 250, 0.2));
  color: #a78bfa;
  border-color: rgba(167, 139, 250, 0.3);
}

:global([data-theme='night']) .keyword:hover {
  background: linear-gradient(135deg, rgba(167, 139, 250, 0.2), rgba(167, 139, 250, 0.25));
  box-shadow: 0 2px 8px rgba(167, 139, 250, 0.3);
}

.episode-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.episode-card {
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.episode-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.episode-number {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
}

.episode-header time {
  font-size: 11px;
  color: var(--text-tertiary);
}

.episode-summary {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
  margin-bottom: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.procedure-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.latest-state-note {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.latest-state-note time {
  color: var(--text-tertiary);
  font-size: 12px;
}

.procedure-card {
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.procedure-card h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.procedure-card p {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.65;
}

.empty-state {
  grid-column: 1 / -1;
  padding: 40px 16px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  color: var(--text-tertiary);
  font-size: 13px;
  text-align: center;
}

.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 20px;
  padding: 14px 16px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-primary);
  border-radius: 0 0 10px 10px;
}

.pagination-info {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pagination-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 16px;
  border: 1.5px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all .2s ease;
  user-select: none;
}

.pagination-btn:disabled {
  opacity: .35;
  cursor: default;
  transform: none !important;
}

.pagination-btn:not(:disabled):hover {
  border-color: #8b5cf6;
  color: #8b5cf6;
  background: rgba(139, 92, 246, 0.06);
  transform: translateY(-1px);
  box-shadow: 0 3px 10px rgba(139, 92, 246, 0.15);
}

.pagination-btn:not(:disabled):active {
  transform: translateY(0);
  box-shadow: none;
}

:global([data-theme='night']) .pagination-btn:not(:disabled):hover {
  border-color: #a78bfa;
  color: #a78bfa;
  background: rgba(167, 139, 250, 0.08);
  box-shadow: 0 3px 10px rgba(167, 139, 250, 0.2);
}

.pagination-current {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 600;
  padding: 7px 12px;
  border: 1.5px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  min-width: 64px;
  text-align: center;
}

/* Drawer (right-side panel) */
.drawer-overlay {
  --bg-primary: #f9fafb;
  --bg-secondary: #ffffff;
  --text-primary: #111827;
  --text-secondary: #6b7280;
  --text-tertiary: #9ca3af;
  --border-color: #e5e7eb;
  --border-light: #f3f4f6;
  --primary: #3b82f6;
  --primary-light: #dbeafe;
  --success: #10b981;
  --success-light: #d1fae5;
  position: fixed;
  inset: 0;
  z-index: 1000;
  pointer-events: auto;
  background: rgba(15, 23, 42, 0.08);
}

:global([data-theme='night']) .drawer-overlay {
  --bg-primary: #111827;
  --bg-secondary: #1f2937;
  --text-primary: #f9fafb;
  --text-secondary: #9ca3af;
  --text-tertiary: #6b7280;
  --border-color: #374151;
  --border-light: #2d3748;
  --primary: #60a5fa;
  --primary-light: #1e3a8a;
  --success: #34d399;
  --success-light: #064e3b;
}

.drawer {
  position: fixed;
  top: 0;
  right: 0;
  height: 100vh;
  width: 720px;
  max-width: 92vw;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-color);
  box-shadow: -4px 0 24px rgba(0,0,0,.12);
  display: flex;
  flex-direction: column;
  z-index: 1001;
  pointer-events: auto;
  animation: drawer-in 220ms ease both;
}

.drawer.profile-drawer { width: 1040px; }

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.drawer-header h3 {
  margin-top: 3px;
  font-size: 17px;
  font-weight: 600;
}

.drawer-header small { color: var(--text-tertiary); font-size: 11px; }

.drawer-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.close-btn {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: var(--bg-primary);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  flex-shrink: 0;
}

.close-btn:hover { background: var(--border-color); }

@keyframes drawer-in {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

@media (max-width: 1100px) {
  .archive-actions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .overview-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 768px) {
  .memory-shell { padding: 12px; }
  .chart-board { grid-template-columns: 1fr; }
  .chart-wide { grid-column: auto; }
  .overview-stats { grid-template-columns: 1fr; }
  .episode-list { grid-template-columns: 1fr; }
  .procedure-list { grid-template-columns: 1fr; }
  .profile-item { grid-template-columns: 80px 1fr; }
  .profile-detail-layout { grid-template-columns: 1fr; }
  .profile-stat strong { font-size: 20px; }
  .insight-chart { height: 240px; }
  .personality-chart { height: 280px; }
  .heatmap-chart { height: 300px; }
  .profile-heatmap-chart { height: 280px; }
  .calendar-chart { height: 240px; }
  .drawer { width: 100%; max-width: 100%; }
}

@media (max-width: 480px) {
  .archive-actions { grid-template-columns: 1fr; }
  .overview-stats { grid-template-columns: 1fr; }
  .profile-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .profile-stat:nth-child(2) { border-right: none; }
  .profile-stat:nth-child(-n + 2) { padding-bottom: 12px; border-bottom: 1px solid var(--border-color); }
  .profile-stat:nth-child(n + 3) { padding-top: 12px; }
  .profile-version-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (prefers-reduced-motion: reduce) {
  .drawer { animation: none; }
  .archive-actions button { transition: none; }
}
</style>
