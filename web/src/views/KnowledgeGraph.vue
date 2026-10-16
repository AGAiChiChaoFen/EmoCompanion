<template>
  <div class="lightrag-console white-knowledge-console">
    <header class="knowledge-console-header">
      <div class="console-heading">
        <span class="console-mark"><i class="bi bi-diagram-3-fill"></i></span>
        <div>
          <strong>心理知识图谱</strong>
          <span>LightRAG Knowledge Workspace</span>
        </div>
      </div>

      <div class="console-tabs" role="tablist" aria-label="知识库功能">
        <button
          type="button"
          role="tab"
          :aria-selected="activeTab === 'documents'"
          :class="{ active: activeTab === 'documents' }"
          @click="activeTab = 'documents'"
        >
          <i class="bi bi-files"></i>
          文档管理
          <strong>{{ totalDocuments }}</strong>
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="activeTab === 'graph'"
          :class="{ active: activeTab === 'graph' }"
          @click="activeTab = 'graph'"
        >
          <i class="bi bi-share"></i>
          知识图谱
          <strong>{{ formatNumber(graphNodes.length) }}</strong>
        </button>
      </div>

      <div class="service-state" :class="{ online: !errorMessage }">
        <i></i>
        <span>{{ errorMessage ? '连接异常' : '知识服务在线' }}</span>
      </div>
    </header>

    <div v-if="errorMessage" class="console-alert" role="alert">
      <i class="bi bi-exclamation-triangle"></i>
      <span>{{ errorMessage }}</span>
      <button type="button" title="关闭提示" aria-label="关闭提示" @click="errorMessage = ''">
        <i class="bi bi-x-lg"></i>
      </button>
    </div>

    <section v-show="activeTab === 'documents'" class="documents-panel console-panel">
      <div class="panel-toolbar document-toolbar">
        <div>
          <span class="panel-kicker">Knowledge Sources</span>
          <h3>知识文档管理</h3>
          <p>{{ pipelineStatusText }}</p>
        </div>
        <div class="actions">
          <button type="button" :disabled="loadingDocuments" title="刷新文档列表" @click="loadDocuments">
            <i class="bi bi-arrow-clockwise" :class="{ spinning: loadingDocuments }"></i>
            刷新
          </button>
          <button type="button" :disabled="scanning" title="扫描服务器输入目录并重试失败任务" @click="scanDocuments">
            <i class="bi bi-activity"></i>
            扫描 / 重试
          </button>
          <label class="upload-button" title="上传知识文档">
            <input type="file" multiple @change="uploadDocuments" />
            <i class="bi bi-cloud-arrow-up"></i>
            上传文档
          </label>
        </div>
      </div>

      <div v-if="uploadNotice" class="notice">
        <i class="bi bi-info-circle"></i>
        <span>{{ uploadNotice }}</span>
      </div>

      <div class="status-filters" aria-label="文档状态筛选">
        <button
          v-for="filter in statusFilters"
          :key="filter.value || 'all'"
          type="button"
          :class="{ active: statusFilter === filter.value }"
          @click="selectStatus(filter.value)"
        >
          {{ filter.label }}
          <strong>{{ statusCount(filter.value) }}</strong>
        </button>
      </div>

      <div class="document-table-shell">
        <table class="document-table">
          <thead>
            <tr>
              <th>文档</th>
              <th>摘要</th>
              <th>状态</th>
              <th>长度</th>
              <th>知识片段</th>
              <th>创建时间</th>
              <th>更新时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loadingDocuments">
              <td colspan="7" class="empty-row"><i class="bi bi-arrow-repeat spinning"></i> 正在读取文档...</td>
            </tr>
            <tr v-else-if="!documents.length">
              <td colspan="7" class="empty-row">当前筛选条件下暂无文档</td>
            </tr>
            <tr v-for="doc in documents" v-else :key="doc.id">
              <td class="document-title-cell">
                <span class="document-icon"><i class="bi bi-file-earmark-text"></i></span>
                <div>
                  <strong :title="documentName(doc)">{{ documentName(doc) }}</strong>
                  <small class="mono" :title="doc.id">{{ doc.id }}</small>
                </div>
              </td>
              <td class="summary-cell" :title="compactSummary(doc.content_summary)">{{ compactSummary(doc.content_summary) }}</td>
              <td><span class="status-chip" :class="statusClass(doc.status)">{{ statusText(doc.status) }}</span></td>
              <td>{{ formatNumber(doc.content_length) }}</td>
              <td>{{ formatNumber(doc.chunks_count) }}</td>
              <td>{{ formatTime(doc.created_at) }}</td>
              <td>{{ formatTime(doc.updated_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <footer class="pagination-bar">
        <span>共 {{ formatNumber(pagination.total_count || totalDocuments) }} 个文档</span>
        <div>
          <button type="button" :disabled="!pagination.has_prev" title="上一页" @click="changePage(pagination.page - 1)">
            <i class="bi bi-chevron-left"></i>
          </button>
          <strong>{{ pagination.page }} / {{ pagination.total_pages || 1 }}</strong>
          <button type="button" :disabled="!pagination.has_next" title="下一页" @click="changePage(pagination.page + 1)">
            <i class="bi bi-chevron-right"></i>
          </button>
        </div>
      </footer>
    </section>

    <section
      v-show="activeTab === 'graph'"
      ref="graphPanel"
      class="graph-panel console-panel"
      :class="{ 'is-fullscreen': isGraphFullscreen }"
    >
      <div class="graph-toolbar">
        <div class="graph-query-controls">
          <button type="button" :disabled="loadingGraph" title="重新加载当前图谱" @click="loadGraph({ force: true })">
            <i class="bi bi-arrow-clockwise" :class="{ spinning: loadingGraph }"></i>
          </button>
          <div class="custom-select" :class="{ 'is-open': dropdownOpen, 'is-disabled': loadingGraph }" tabindex="0" @blur="dropdownOpen = false">
            <div class="select-trigger" @click="!loadingGraph && (dropdownOpen = !dropdownOpen)">
              <i class="bi bi-diagram-2"></i>
              <span>{{ selectedLabel || '选择知识实体' }}</span>
              <i class="bi bi-chevron-down" :class="{ rotate: dropdownOpen }"></i>
            </div>
            <Transition name="dropdownFade">
              <div v-show="dropdownOpen" class="select-options">
                <div
                  v-for="label in graphLabels"
                  :key="label"
                  class="select-option"
                  :class="{ 'is-selected': label === selectedLabel }"
                  @mousedown.prevent="selectedLabel = label; dropdownOpen = false; loadGraph()"
                >
                  <i class="bi bi-check" :style="{ opacity: label === selectedLabel ? 1 : 0 }"></i>
                  {{ label }}
                </div>
              </div>
            </Transition>
          </div>
          <label class="search-box">
            <i class="bi bi-search"></i>
            <input v-model="graphSearch" type="search" placeholder="搜索当前图谱节点" />
            <button v-if="graphSearch" type="button" title="清除搜索" @click="graphSearch = ''"><i class="bi bi-x"></i></button>
          </label>
        </div>

        <div class="graph-actions">
          <select v-model="graphLabelMode" title="节点标签显示方式">
            <option v-for="option in graphLabelOptions" :key="option.value" :value="option.value">标签：{{ option.label }}</option>
          </select>
          <button type="button" :class="{ active: graphShowEdges }" title="显示或隐藏关系边" @click="graphShowEdges = !graphShowEdges">
            <i class="bi bi-bezier2"></i>
          </button>
          <button type="button" :class="{ active: graphFocusMode }" title="只显示选中节点的关联网络" @click="graphFocusMode = !graphFocusMode">
            <i class="bi bi-bullseye"></i>
          </button>
          <button type="button" title="放大" @click="zoomGraph(1)"><i class="bi bi-zoom-in"></i></button>
          <button type="button" title="缩小" @click="zoomGraph(-1)"><i class="bi bi-zoom-out"></i></button>
          <button type="button" title="重置视图" @click="resetGraphView"><i class="bi bi-crosshair"></i></button>
          <button type="button" title="导出高清图片" @click="exportGraphImage"><i class="bi bi-download"></i></button>
          <button type="button" title="全屏查看" @click="toggleGraphFullscreen"><i class="bi bi-arrows-fullscreen"></i></button>
        </div>
      </div>

      <div class="graph-stats-strip">
        <span v-for="stat in graphStats" :key="stat.label"><small>{{ stat.label }}</small><strong>{{ stat.value }}</strong></span>
      </div>

      <div class="graph-workspace">
        <div class="graph-canvas" role="img" aria-label="心理健康知识图谱">
          <div ref="graphContainer" class="sigma-container"></div>
          <canvas ref="graphFx" class="graph-fx" aria-hidden="true"></canvas>
          <Transition name="graphLoadingFade">
            <div v-if="loadingGraph || isGraphPreparing" class="graph-loading">
              <span class="graph-loading-orb">
                <i></i><i></i><i></i>
              </span>
              <strong>{{ loadingGraph ? '正在加载图谱数据' : '正在计算图谱布局' }}</strong>
              <small>Aurora Knowledge Engine</small>
            </div>
          </Transition>
          <div v-if="!loadingGraph && !isGraphPreparing && !graphNodes.length" class="graph-loading graph-empty">
            <span class="graph-empty-glyph"><i class="bi bi-diagram-3"></i></span>
            <strong>请选择知识实体查看关系网络</strong>
          </div>
          <div class="graph-canvas-hint"><i class="bi bi-mouse"></i> 拖拽节点 · 滚轮缩放 · 点击查看详情</div>
        </div>

        <aside class="node-inspector" :class="{ empty: !selectedNode }">
          <Transition name="inspectorSwap" mode="out-in">
          <div v-if="selectedNode" :key="selectedNode.id" class="node-inspector-body">
            <div class="node-inspector-heading">
              <span class="node-color" :style="{ background: selectedNode.color }"></span>
              <div>
                <small>{{ selectedNode.type }}</small>
                <h3>{{ selectedNode.label }}</h3>
              </div>
              <button type="button" title="关闭详情" @click="selectedNode = null"><i class="bi bi-x-lg"></i></button>
            </div>
            <p>{{ selectedNode.description }}</p>
            <dl>
              <div><dt>关联数量</dt><dd>{{ selectedNode.degree }}</dd></div>
              <div><dt>实体标识</dt><dd class="mono">{{ selectedNode.id }}</dd></div>
            </dl>
            <div class="relations-heading"><strong>直接关联</strong><span>{{ selectedRelations.length }}</span></div>
            <div class="relation-list">
              <button v-for="relation in selectedRelations" :key="relation.id" type="button" @click="selectedNode = relation.node">
                <span><small>{{ relation.label }}</small><strong>{{ relation.node.label }}</strong></span>
                <i class="bi bi-arrow-right"></i>
              </button>
            </div>
          </div>
          <div v-else class="inspector-placeholder">
            <i class="bi bi-cursor"></i>
            <strong>选择一个知识节点</strong>
            <span>节点的类型、说明和直接关联会显示在这里</span>
          </div>
          </Transition>
        </aside>
      </div>
    </section>
  </div>
</template>

<script setup>
import { createEdgeCurveProgram } from '@sigma/edge-curve';
import { NodeBorderProgram } from '@sigma/node-border';
import Graph from 'graphology';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import Sigma from 'sigma';
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { buildApiUrl } from '../utils/api';
import { useAnalysisResult } from '../composables/useAnalysisResult';

const activeTab = ref('graph');
const { analysisResult: latestAnalysisResult } = useAnalysisResult();
const documents = ref([]);
const statusCounts = ref({ all: 0 });
const pagination = ref({ page: 1, page_size: 10, total_count: 0, total_pages: 1, has_next: false, has_prev: false });
const statusFilter = ref('');
const loadingDocuments = ref(false);
const scanning = ref(false);
const uploadNotice = ref('');
const pipeline = ref(null);
const errorMessage = ref('');

const graphLabels = ref([]);
const selectedLabel = ref('');
const graphNodes = ref([]);
const graphEdges = ref([]);
const selectedNode = ref(null);
const focusedNode = ref(null);
const graphSearch = ref('');
const graphLabelMode = ref('all');
const graphShowEdges = ref(true);
const graphFocusMode = ref(false);
const graphShowRelatedLabels = ref(false);
const graphShowEdgeLabels = ref(false);
const loadingGraph = ref(false);
const dropdownOpen = ref(false);
const isGraphPreparing = ref(false);
const graphPanel = ref(null);
const graphContainer = ref(null);
const graphFx = ref(null);
const isGraphFullscreen = ref(false);

// 统计条数字的 count-up 动画值
const animatedNodeCount = ref(0);
const animatedEdgeCount = ref(0);
const animatedLabelCount = ref(0);

let pollTimer = null;
let sigmaInstance = null;
let sigmaGraph = null;
let graphNodeMap = new Map();
let graphEdgeMap = new Map();
let draggedNodeId = null;
let dragStartViewport = null;
let draggedNodeMoved = false;
let suppressNextNodeClick = false;
let originalGraphPositions = new Map();

// ——— 极光叠层动画（FX）状态：仅保留悬停/选中柔光 ———
let fxCtx = null;
let fxRaf = 0;
let fxResizeObserver = null;
let fxWidth = 0;
let fxHeight = 0;
let revealRaf = 0;
let fxRevealing = false;
let fxRevealProgress = 1;
const statTweenRafs = new Map();

// ——— 弹簧物理仿真状态：拖拽 / 选中时让节点与边"弹动" ———
let simRaf = 0;
let simRunning = false;
let simSleepFrames = 0;
let simSettleFrames = 0;
let pinnedNodeId = null;
const nodeVel = new Map();      // 节点速度 {vx, vy}
const simRest = new Map();      // 节点弹簧锚点（静止目标位置）
const edgeRest = new Map();     // 边的自然长度（保持局部结构）
let simAvgRest = 60;            // 平均边长，用于自适应步长/阈值

const REDUCED_MOTION = typeof window !== 'undefined'
  && window.matchMedia
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const FX_GLOW = 'rgba(129, 140, 248, 0.55)';
const FX_PULSE = 'rgba(129, 140, 248, 0.5)';
const FX_REVEAL_MS = 1200;

// 弹簧物理参数
const SIM_K_EDGE = 0.08;    // 边弹簧刚度（按度归一，防止 hub 抖动）
const SIM_K_ANCHOR = 0.03;  // 锚点回弹刚度
const SIM_DAMPING = 0.8;    // 阻尼（越小越快停）
const SIM_MAX_FRAMES = 300; // 释放后最长自动仿真帧数（安全上限）

const GRAPH_CACHE_VERSION = 'hearttalk-lightrag-graph-v3';
const GRAPH_CACHE_TTL_MS = 24 * 60 * 60 * 1000;
const GRAPH_QUERY_DEPTH = 3;
const GRAPH_MAX_NODES = 420;
const graphLabelOptions = [
  { value: 'important', label: '重点' },
  { value: 'all', label: '全部' },
  { value: 'none', label: '隐藏' },
];

const cacheKey = (name) => `${GRAPH_CACHE_VERSION}:${name}`;
const graphDataCacheKey = (label) =>
  cacheKey(`graph:${GRAPH_QUERY_DEPTH}:${GRAPH_MAX_NODES}:${encodeURIComponent(String(label || '*'))}`);

const readCache = (key) => {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const cached = JSON.parse(raw);
    if (!cached || Date.now() - Number(cached.savedAt || 0) > GRAPH_CACHE_TTL_MS) {
      window.localStorage.removeItem(key);
      return null;
    }
    return cached.value;
  } catch {
    return null;
  }
};

const writeCache = (key, value) => {
  try {
    window.localStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), value }));
  } catch {
    // Ignore quota/private-mode cache failures; graph still works from network.
  }
};

const clearGraphCache = () => {
  try {
    Object.keys(window.localStorage)
      .filter((key) => key.startsWith(GRAPH_CACHE_VERSION))
      .forEach((key) => window.localStorage.removeItem(key));
  } catch {
    // Best-effort cache cleanup.
  }
};

const stopPolling = () => {
  if (!pollTimer) return;
  window.clearInterval(pollTimer);
  pollTimer = null;
};

const startPolling = () => {
  if (pollTimer) return;
  pollTimer = window.setInterval(async () => {
    const ok = await loadPipelineStatus({ fromPoll: true });
    if (!ok) {
      stopPolling();
      return;
    }
    if (pipeline.value?.busy) loadDocuments({ fromPoll: true });
  }, 8000);
};

const statusFilters = [
  { value: '', label: '全部' },
  { value: 'processed', label: '已完成' },
  { value: 'preprocessed', label: '预处理' },
  { value: 'processing', label: '处理中' },
  { value: 'pending', label: '待处理' },
  { value: 'failed', label: '失败' },
];

const totalDocuments = computed(() => statusCounts.value.all || pagination.value.total_count || documents.value.length);
const processedDocuments = computed(() => statusCounts.value.processed || statusCounts.value.PROCESSED || 0);
const interventionSuggestions = computed(() => {
  const suggestions = latestAnalysisResult.value?.suggestions;
  return Array.isArray(suggestions) ? suggestions.filter(Boolean) : [];
});
const lightragReferences = computed(() => {
  const references = latestAnalysisResult.value?.lightrag?.references;
  if (!Array.isArray(references)) return [];
  return references
    .map((item) => ({
      reference_id: String(item?.reference_id || '').trim(),
      file_path: String(item?.file_path || '').trim(),
    }))
    .filter((item) => item.reference_id || item.file_path)
    .slice(0, 6);
});

const displayedKnowledgeSources = computed(() => (
  lightragReferences.value
));
const lightragStatusText = computed(() => {
  const status = String(latestAnalysisResult.value?.lightrag?.status || '').trim();
  if (!latestAnalysisResult.value?.lightrag) return '已按内置知识规则应用';
  if (!status) return '已参与推理';
  const statusMap = {
    success: '检索成功',
    ok: '检索成功',
    skipped: '未返回具体引用',
    disabled: '知识库未启用',
    failed: '检索异常',
  };
  return statusMap[status.toLowerCase()] || status;
});
const lightragContextText = computed(() => {
  const length = Number(latestAnalysisResult.value?.lightrag?.contextLength || 0);
  return length > 0 ? `${length} 字符` : '未取得检索上下文';
});
const pipelineStatusText = computed(() => {
  if (!pipeline.value) return 'Pipeline 状态未知';
  if (pipeline.value.busy) return pipeline.value.latest_message || pipeline.value.job_name || 'Pipeline 正在运行';
  return 'Pipeline 空闲';
});
const graphStats = computed(() => [
  { label: '当前节点数', value: formatNumber(Math.round(animatedNodeCount.value)) },
  { label: '当前边数', value: formatNumber(Math.round(animatedEdgeCount.value)) },
  { label: '实体标签数', value: formatNumber(Math.round(animatedLabelCount.value)) },
  { label: '查询深度', value: `${GRAPH_QUERY_DEPTH} 层` },
  { label: '加载上限', value: `${formatNumber(GRAPH_MAX_NODES)} 节点` },
]);

// 数字滚动动画：把 ref 从当前值缓动到目标值
const tweenStat = (statRef, target, key) => {
  const existing = statTweenRafs.get(key);
  if (existing) window.cancelAnimationFrame(existing);
  const from = Number(statRef.value) || 0;
  const to = Number(target) || 0;
  if (REDUCED_MOTION || from === to) {
    statRef.value = to;
    return;
  }
  const duration = 700;
  const start = performance.now();
  const step = (now) => {
    const progress = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    statRef.value = from + (to - from) * eased;
    if (progress < 1) {
      statTweenRafs.set(key, window.requestAnimationFrame(step));
    } else {
      statRef.value = to;
      statTweenRafs.delete(key);
    }
  };
  statTweenRafs.set(key, window.requestAnimationFrame(step));
};

const animateGraphStats = () => {
  tweenStat(animatedNodeCount, graphNodes.value.length, 'nodes');
  tweenStat(animatedEdgeCount, graphEdges.value.length, 'edges');
  tweenStat(animatedLabelCount, graphLabels.value.length, 'labels');
};

const selectedRelations = computed(() => {
  if (!selectedNode.value) return [];
  return graphEdges.value
    .filter((edge) => edge.source === selectedNode.value.id || edge.target === selectedNode.value.id)
    .slice(0, 12)
    .map((edge) => {
      const otherId = edge.source === selectedNode.value.id ? edge.target : edge.source;
      return {
        id: edge.id,
        node: graphNodeMap.get(otherId),
        label: firstText(edge.label, edge.type, edge.properties?.keywords, edge.properties?.relation, edge.properties?.description, '关联'),
      };
    })
    .filter((item) => item.node);
});

const apiJson = async (url, options = {}) => {
  // 本地开发时走 Vite 的同源服务端代理，避免把 LightRAG 凭据交给浏览器；
  // 生产构建仍通过统一 API 基址访问 LiveTalking 的 /api/lightrag/* 代理。
  const requestUrl = import.meta.env.DEV ? url : buildApiUrl(url);
  const response = await fetch(requestUrl, options);
  const result = await response.json().catch(() => ({}));
  if (!response.ok || result.code !== 0) {
    throw new Error(result.msg || `HTTP ${response.status}`);
  }
  errorMessage.value = '';
  return result.data;
};

const loadDocuments = async () => {
  loadingDocuments.value = true;
  try {
    const data = await apiJson('/api/lightrag/documents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        page: pagination.value.page,
        page_size: pagination.value.page_size,
        status_filter: statusFilter.value,
        sort_field: 'updated_at',
        sort_direction: 'desc',
      }),
    });
    documents.value = data.documents || [];
    pagination.value = data.pagination || pagination.value;
    statusCounts.value = data.status_counts || statusCounts.value;
    startPolling();
    return true;
  } catch (error) {
    errorMessage.value = error.message;
    return false;
  } finally {
    loadingDocuments.value = false;
  }
};

const loadPipelineStatus = async () => {
  try {
    pipeline.value = await apiJson('/api/lightrag/pipeline_status');
    startPolling();
    return true;
  } catch (error) {
    errorMessage.value = error.message;
    return false;
  }
};

const scanDocuments = async () => {
  scanning.value = true;
  try {
    clearGraphCache();
    const result = await apiJson('/api/lightrag/scan', { method: 'POST' });
    uploadNotice.value = result.message || '已触发 LightRAG 扫描任务';
    await loadPipelineStatus();
    await loadDocuments();
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    scanning.value = false;
  }
};

const uploadDocuments = async (event) => {
  const files = Array.from(event.target.files || []);
  event.target.value = '';
  if (!files.length) return;
  uploadNotice.value = `正在上传 ${files.length} 个文件...`;
  try {
    clearGraphCache();
    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      await apiJson('/api/lightrag/upload', { method: 'POST', body: formData });
    }
    uploadNotice.value = '上传完成，LightRAG 正在后台索引文档';
    await loadPipelineStatus();
    await loadDocuments();
  } catch (error) {
    errorMessage.value = error.message;
    uploadNotice.value = '上传失败，请检查 LightRAG 服务状态和文件类型';
  }
};

const selectStatus = (value) => {
  statusFilter.value = value;
  pagination.value = { ...pagination.value, page: 1 };
  loadDocuments();
};

const changePage = (page) => {
  pagination.value = { ...pagination.value, page: Math.max(1, page) };
  loadDocuments();
};

const loadGraphLabels = async () => {
  const cachedLabels = readCache(cacheKey('labels:popular:80'));
  if (Array.isArray(cachedLabels) && cachedLabels.length) {
    graphLabels.value = cachedLabels;
    if (!selectedLabel.value) selectedLabel.value = cachedLabels[0];
    return;
  }

  const data = await apiJson('/api/lightrag/graph_labels?limit=80');
  graphLabels.value = data.labels || [];
  if (graphLabels.value.length) writeCache(cacheKey('labels:popular:80'), graphLabels.value);
  if (!selectedLabel.value && graphLabels.value.length) {
    selectedLabel.value = graphLabels.value[0];
  }
};

const DEFAULT_NODE_COLOR = '#7c86c9';
const NODE_BORDER_COLOR = '#ffffff';
const NODE_BORDER_SELECTED = '#a855f7';
const EDGE_COLOR_DARK = '#aeb8d8';
const EDGE_HIGHLIGHT_COLOR = '#a855f7';
const NODE_COLOR_DISABLED = '#d7dcec';

const graphThemeValue = (name, fallback) => {
  if (typeof window === 'undefined') return fallback;
  const themeScope = document.querySelector('.lightrag-console') || document.documentElement;
  return getComputedStyle(themeScope).getPropertyValue(name).trim() || fallback;
};

const TYPE_SYNONYMS = {
  unknown: 'unknown',
  other: 'other',
  concept: 'concept',
  object: 'concept',
  type: 'concept',
  category: 'concept',
  model: 'concept',
  project: 'concept',
  condition: 'concept',
  rule: 'concept',
  regulation: 'concept',
  article: 'concept',
  law: 'concept',
  disease: 'concept',
  method: 'method',
  process: 'method',
  artifact: 'artifact',
  technology: 'artifact',
  tech: 'artifact',
  product: 'artifact',
  equipment: 'artifact',
  device: 'artifact',
  material: 'artifact',
  chemical: 'artifact',
  drug: 'artifact',
  medicine: 'artifact',
  naturalobject: 'naturalobject',
  natural: 'naturalobject',
  phenomena: 'naturalobject',
  substance: 'naturalobject',
  data: 'data',
  figure: 'data',
  value: 'data',
  content: 'content',
  book: 'content',
  organization: 'organization',
  org: 'organization',
  company: 'organization',
  event: 'event',
  activity: 'event',
  person: 'person',
  people: 'person',
  role: 'person',
  location: 'location',
  geography: 'location',
  place: 'location',
  概念: 'concept',
  疾病: 'concept',
  方法: 'method',
  药物: 'artifact',
  数据: 'data',
  内容: 'content',
  组织: 'organization',
  机构: 'organization',
  事件: 'event',
  活动: 'event',
  人物: 'person',
  地点: 'location',
};

const NODE_TYPE_COLORS = {
  person: '#4169E1',
  creature: '#bd7ebe',
  organization: '#00cc00',
  location: '#cf6d17',
  event: '#00bfa0',
  concept: '#e3493b',
  method: '#b71c1c',
  content: '#0f558a',
  data: '#0000ff',
  artifact: '#4421af',
  naturalobject: '#b2e061',
  other: '#f4d371',
  unknown: '#b0b0b0',
};

const EXTENDED_COLORS = [
  '#84a3e1',
  '#5a2c6d',
  '#2F4F4F',
  '#003366',
  '#9b3a31',
  '#00CED1',
  '#b300b3',
  '#0f705d',
  '#ff99cc',
  '#6ef7b3',
  '#cd071e',
];

const typeColorMap = new Map();

const colorForType = (type) => {
  const normalized = String(type || 'unknown').trim().toLowerCase() || 'unknown';
  const mappedType = TYPE_SYNONYMS[normalized] || normalized;
  if (NODE_TYPE_COLORS[mappedType]) {
    return NODE_TYPE_COLORS[mappedType];
  }
  if (!typeColorMap.has(normalized)) {
    typeColorMap.set(normalized, EXTENDED_COLORS[typeColorMap.size % EXTENDED_COLORS.length] || DEFAULT_NODE_COLOR);
  }
  return typeColorMap.get(normalized);
};

const firstText = (...values) => {
  for (const value of values) {
    if (Array.isArray(value) && value.length) return String(value[0] || '').trim();
    if (value !== undefined && value !== null && String(value).trim()) return String(value).trim();
  }
  return '';
};

const normalizeGraphData = (data) => {
  const rawNodes = data?.nodes || data?.entities || [];
  const rawEdges = data?.edges || data?.relations || [];
  const degreeMap = new Map();

  rawEdges.forEach((edge) => {
    const source = String(edge.source || edge.src || edge.src_id || edge.from || '').trim();
    const target = String(edge.target || edge.tgt || edge.tgt_id || edge.to || '').trim();
    if (!source || !target) return;
    degreeMap.set(source, (degreeMap.get(source) || 0) + 1);
    degreeMap.set(target, (degreeMap.get(target) || 0) + 1);
  });

  graphNodes.value = rawNodes.map((node, index) => {
    const properties = node.properties || node.entity_data || {};
    const id = String(node.id || node.entity_name || node.label || node.name || `node-${index}`);
    const label = firstText(node.labels, node.label, node.entity_name, node.name, properties.entity_name, id);
    const type = firstText(properties.entity_type, node.entity_type, node.type, 'ENTITY');
    const degree = degreeMap.get(id) || Number(node.degree || node.size || 1);
    return {
      id,
      label,
      type,
      description: firstText(properties.description, node.description, 'LightRAG 知识图谱实体。'),
      degree,
      lowerLabel: label.toLowerCase(),
      lowerDescription: firstText(properties.description, node.description, '').toLowerCase(),
      size: 4,
      color: colorForType(type),
      properties,
    };
  });

  const degrees = graphNodes.value.map((node) => Number(node.degree || 0));
  const minDegree = Math.min(...degrees, 0);
  const maxDegree = Math.max(...degrees, 0);
  const degreeRange = maxDegree - minDegree;
  graphNodes.value = graphNodes.value.map((node) => ({
    ...node,
    size: degreeRange > 0
      ? Math.round(4 + 16 * Math.pow((node.degree - minDegree) / degreeRange, 0.5))
      : 4,
  }));

  const validIds = new Set(graphNodes.value.map((node) => node.id));
  graphEdges.value = rawEdges
    .map((edge, index) => {
      const source = String(edge.source || edge.src || edge.src_id || edge.from || '');
      const target = String(edge.target || edge.tgt || edge.tgt_id || edge.to || '');
      const properties = edge.properties || {};
      return {
        id: String(edge.id || `${source}-${target}-${index}`),
        source,
        target,
        label: firstText(properties.keywords, edge.type, edge.label),
        weight: Number(properties.weight || edge.weight || 1),
        properties,
      };
    })
    .filter((edge) => validIds.has(edge.source) && validIds.has(edge.target))
    .slice(0, 900);

  graphNodeMap = new Map(graphNodes.value.map((node) => [node.id, node]));
  graphEdgeMap = new Map(graphEdges.value.map((edge) => [edge.id, edge]));

  selectedNode.value = null;
  focusedNode.value = null;
};

const prepareGraphLayout = async () => {
  isGraphPreparing.value = true;
  try {
    await nextTick();
    await new Promise((resolve) => window.requestAnimationFrame(resolve));
    await renderSigmaGraph();
  } finally {
    isGraphPreparing.value = false;
  }
};

const loadGraph = async ({ force = false } = {}) => {
  if (!selectedLabel.value) return;
  const currentCacheKey = graphDataCacheKey(selectedLabel.value);

  if (!force) {
    const cachedGraph = readCache(currentCacheKey);
    if (cachedGraph) {
      normalizeGraphData(cachedGraph);
      await prepareGraphLayout();
      return;
    }
  }

  loadingGraph.value = true;
  try {
    const data = await apiJson(`/api/lightrag/graph?label=${encodeURIComponent(selectedLabel.value)}&max_depth=${GRAPH_QUERY_DEPTH}&max_nodes=${GRAPH_MAX_NODES}`);
    writeCache(currentCacheKey, data || {});
    normalizeGraphData(data || {});
    loadingGraph.value = false;
    await prepareGraphLayout();
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    loadingGraph.value = false;
    isGraphPreparing.value = false;
  }
};

const destroySigma = () => {
  stopFx();
  stopSim();
  if (revealRaf) {
    window.cancelAnimationFrame(revealRaf);
    revealRaf = 0;
  }
  fxRevealing = false;
  fxRevealProgress = 1;
  if (fxResizeObserver) {
    fxResizeObserver.disconnect();
    fxResizeObserver = null;
  }
  if (sigmaInstance) {
    sigmaInstance.kill();
    sigmaInstance = null;
  }
  sigmaGraph = null;
  pinnedNodeId = null;
  nodeVel.clear();
  simRest.clear();
  edgeRest.clear();
  draggedNodeId = null;
  dragStartViewport = null;
  draggedNodeMoved = false;
  suppressNextNodeClick = false;
  originalGraphPositions = new Map();
};

const refreshSigma = () => {
  sigmaInstance?.setSetting('renderEdgeLabels', graphShowEdgeLabels.value);
  sigmaInstance?.refresh({ skipIndexation: true });
};

// ——— 极光叠层动画系统（悬停/选中柔光 + 选中脉冲光环） ———

// 依据摄像机缩放推算屏幕上的辉光半径
const fxScaleFactor = () => {
  const ratio = sigmaInstance?.getCamera().getState().ratio || 1;
  return Math.max(0.4, Math.min(2.4, 1 / ratio));
};

// graph 坐标 → 视口像素坐标
const fxNodeViewport = (nodeId) => {
  if (!sigmaInstance || !sigmaGraph?.hasNode(nodeId)) return null;
  const x = sigmaGraph.getNodeAttribute(nodeId, 'x');
  const y = sigmaGraph.getNodeAttribute(nodeId, 'y');
  if (typeof x !== 'number' || typeof y !== 'number') return null;
  return sigmaInstance.graphToViewport({ x, y });
};

// 绘制柔和径向辉光
const fxDrawHalo = (x, y, radius, color) => {
  if (!fxCtx) return;
  const gradient = fxCtx.createRadialGradient(x, y, 0, x, y, radius);
  gradient.addColorStop(0, color);
  gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
  fxCtx.beginPath();
  fxCtx.fillStyle = gradient;
  fxCtx.arc(x, y, radius, 0, Math.PI * 2);
  fxCtx.fill();
};

const fxTick = () => {
  fxRaf = window.requestAnimationFrame(fxTick);
  if (!fxCtx || !sigmaInstance) return;
  if (document.hidden || activeTab.value !== 'graph') {
    fxCtx.clearRect(0, 0, fxWidth, fxHeight);
    return;
  }
  const now = performance.now();
  const scale = fxScaleFactor();
  fxCtx.clearRect(0, 0, fxWidth, fxHeight);
  fxCtx.globalCompositeOperation = 'lighter';

  // 1) 悬停 / 选中节点柔光
  const activeId = focusedNode.value?.id || selectedNode.value?.id || '';
  if (activeId && sigmaGraph?.hasNode(activeId)) {
    const pos = fxNodeViewport(activeId);
    if (pos) fxDrawHalo(pos.x, pos.y, 34 * scale, FX_GLOW);
  }

  // 2) 选中节点向外扩散的脉冲光环
  const selId = selectedNode.value?.id || '';
  if (selId && sigmaGraph?.hasNode(selId)) {
    const pos = fxNodeViewport(selId);
    if (pos) {
      const pulse = (now % 1800) / 1800;
      const ring = (10 + pulse * 42) * scale;
      fxCtx.beginPath();
      fxCtx.strokeStyle = FX_PULSE;
      fxCtx.globalAlpha = (1 - pulse) * 0.6;
      fxCtx.lineWidth = 2;
      fxCtx.arc(pos.x, pos.y, ring, 0, Math.PI * 2);
      fxCtx.stroke();
      fxCtx.globalAlpha = 1;
    }
  }

  fxCtx.globalCompositeOperation = 'source-over';
};

const startFx = () => {
  if (REDUCED_MOTION || fxRaf) return;
  fxRaf = window.requestAnimationFrame(fxTick);
};

const stopFx = () => {
  if (fxRaf) {
    window.cancelAnimationFrame(fxRaf);
    fxRaf = 0;
  }
  if (fxCtx) fxCtx.clearRect(0, 0, fxWidth, fxHeight);
};

// 让叠层 canvas 与容器保持同尺寸（含高分屏 DPR）
const resizeFx = () => {
  const canvas = graphFx.value;
  const host = graphContainer.value;
  if (!canvas || !host) return;
  const rect = host.getBoundingClientRect();
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  fxWidth = rect.width;
  fxHeight = rect.height;
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  fxCtx = canvas.getContext('2d');
  if (fxCtx) fxCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
};

const setupFx = () => {
  if (!graphFx.value || !graphContainer.value) return;
  resizeFx();
  if (fxResizeObserver) fxResizeObserver.disconnect();
  fxResizeObserver = new ResizeObserver(() => resizeFx());
  fxResizeObserver.observe(graphContainer.value);
  startFx();
};

// ——— 弹簧物理仿真：拖拽 / 选中时让节点与边"弹动" ———

// 记录每个节点的锚点（静止位置）与每条边的自然长度
const buildSimState = () => {
  nodeVel.clear();
  simRest.clear();
  edgeRest.clear();
  pinnedNodeId = null;
  simSleepFrames = 0;
  simSettleFrames = 0;
  if (!sigmaGraph) return;
  sigmaGraph.forEachNode((nodeId) => {
    nodeVel.set(nodeId, { vx: 0, vy: 0 });
    simRest.set(nodeId, {
      x: sigmaGraph.getNodeAttribute(nodeId, 'x'),
      y: sigmaGraph.getNodeAttribute(nodeId, 'y'),
    });
  });
  let total = 0;
  let edgeCount = 0;
  sigmaGraph.forEachEdge((edgeId, _attr, source, target) => {
    const dx = sigmaGraph.getNodeAttribute(target, 'x') - sigmaGraph.getNodeAttribute(source, 'x');
    const dy = sigmaGraph.getNodeAttribute(target, 'y') - sigmaGraph.getNodeAttribute(source, 'y');
    const len = Math.hypot(dx, dy) || 1;
    edgeRest.set(edgeId, len);
    total += len;
    edgeCount += 1;
  });
  simAvgRest = edgeCount > 0 ? total / edgeCount : 60;
};

// 单步物理积分，返回本帧最大位移速度（用于休眠判定）
const stepSim = () => {
  if (!sigmaGraph) return 0;
  const force = new Map();
  sigmaGraph.forEachNode((nodeId) => force.set(nodeId, { fx: 0, fy: 0 }));

  // 边弹簧：偏离自然长度时相互拉/推（按节点度归一，避免 hub 抖动）
  sigmaGraph.forEachEdge((edgeId, _attr, source, target) => {
    const rest = edgeRest.get(edgeId) || simAvgRest;
    const dx = sigmaGraph.getNodeAttribute(target, 'x') - sigmaGraph.getNodeAttribute(source, 'x');
    const dy = sigmaGraph.getNodeAttribute(target, 'y') - sigmaGraph.getNodeAttribute(source, 'y');
    const dist = Math.hypot(dx, dy) || 0.0001;
    const diff = dist - rest;
    const ux = dx / dist;
    const uy = dy / dist;
    const sDeg = Math.max(1, sigmaGraph.degree(source));
    const tDeg = Math.max(1, sigmaGraph.degree(target));
    const fs = force.get(source);
    const ft = force.get(target);
    fs.fx += (SIM_K_EDGE * diff * ux) / sDeg;
    fs.fy += (SIM_K_EDGE * diff * uy) / sDeg;
    ft.fx -= (SIM_K_EDGE * diff * ux) / tDeg;
    ft.fy -= (SIM_K_EDGE * diff * uy) / tDeg;
  });

  // 锚点弹簧：把节点缓缓拉回它的静止位置，保持整体形态、防漂移
  sigmaGraph.forEachNode((nodeId) => {
    const rest = simRest.get(nodeId);
    const f = force.get(nodeId);
    if (!rest || !f) return;
    f.fx += SIM_K_ANCHOR * (rest.x - sigmaGraph.getNodeAttribute(nodeId, 'x'));
    f.fy += SIM_K_ANCHOR * (rest.y - sigmaGraph.getNodeAttribute(nodeId, 'y'));
  });

  // 速度积分 + 阻尼 + 步长钳制
  const maxStep = simAvgRest * 0.5;
  let maxSpeed = 0;
  sigmaGraph.forEachNode((nodeId) => {
    const v = nodeVel.get(nodeId);
    if (!v) return;
    if (nodeId === pinnedNodeId) {
      v.vx = 0;
      v.vy = 0;
      return;
    }
    const f = force.get(nodeId);
    v.vx = (v.vx + f.fx) * SIM_DAMPING;
    v.vy = (v.vy + f.fy) * SIM_DAMPING;
    let sx = v.vx;
    let sy = v.vy;
    const stepLen = Math.hypot(sx, sy);
    if (stepLen > maxStep) {
      sx = (sx / stepLen) * maxStep;
      sy = (sy / stepLen) * maxStep;
    }
    sigmaGraph.setNodeAttribute(nodeId, 'x', sigmaGraph.getNodeAttribute(nodeId, 'x') + sx);
    sigmaGraph.setNodeAttribute(nodeId, 'y', sigmaGraph.getNodeAttribute(nodeId, 'y') + sy);
    const speed = Math.hypot(sx, sy);
    if (speed > maxSpeed) maxSpeed = speed;
  });
  return maxSpeed;
};

const simTick = () => {
  if (!sigmaInstance || !sigmaGraph) {
    simRunning = false;
    simRaf = 0;
    return;
  }
  const maxSpeed = stepSim();
  sigmaInstance.refresh({ skipIndexation: true });

  // 未拖拽且速度足够小 → 判定为已静止；带安全帧上限
  const sleepThreshold = simAvgRest * 0.012;
  if (pinnedNodeId) {
    simSleepFrames = 0;
    simSettleFrames = 0;
  } else {
    simSettleFrames += 1;
    simSleepFrames = maxSpeed < sleepThreshold ? simSleepFrames + 1 : 0;
  }
  if (!pinnedNodeId && (simSleepFrames > 14 || simSettleFrames > SIM_MAX_FRAMES)) {
    simRunning = false;
    simRaf = 0;
    return;
  }
  simRaf = window.requestAnimationFrame(simTick);
};

const startSim = () => {
  if (REDUCED_MOTION || !sigmaGraph || sigmaGraph.order <= 1) return;
  simSleepFrames = 0;
  simSettleFrames = 0;
  if (simRunning) return;
  simRunning = true;
  simRaf = window.requestAnimationFrame(simTick);
};

const stopSim = () => {
  if (simRaf) {
    window.cancelAnimationFrame(simRaf);
    simRaf = 0;
  }
  simRunning = false;
  pinnedNodeId = null;
};

// 给某个节点施加一次冲量（点击选中时的"弹一下"）
const nudgeNode = (nodeId, magnitude) => {
  if (REDUCED_MOTION || !nodeVel.has(nodeId)) return;
  const angle = Math.random() * Math.PI * 2;
  const power = simAvgRest * magnitude;
  const v = nodeVel.get(nodeId);
  v.vx += Math.cos(angle) * power;
  v.vy += Math.sin(angle) * power;
  startSim();
};

// 入场展开动画：节点尺寸从 0 缓动到 1（错峰），完成后显示边
const runRevealAnimation = () => {
  if (revealRaf) {
    window.cancelAnimationFrame(revealRaf);
    revealRaf = 0;
  }
  if (REDUCED_MOTION || !sigmaInstance || (sigmaGraph?.order || 0) <= 1) {
    fxRevealing = false;
    fxRevealProgress = 1;
    sigmaInstance?.refresh({ skipIndexation: true });
    return;
  }
  fxRevealing = true;
  fxRevealProgress = 0;
  const start = performance.now();
  const step = () => {
    const elapsed = performance.now() - start;
    fxRevealProgress = Math.max(0, Math.min(1, elapsed / FX_REVEAL_MS));
    sigmaInstance?.refresh({ skipIndexation: true });
    if (fxRevealProgress < 1) {
      revealRaf = window.requestAnimationFrame(step);
    } else {
      revealRaf = 0;
      fxRevealing = false;
      sigmaInstance?.refresh({ skipIndexation: true });
    }
  };
  revealRaf = window.requestAnimationFrame(step);
};

const drawReadableNodeLabel = (context, data, settings) => {
  if (!data.label) return;

  const label = String(data.label);
  const fontSize = settings.labelSize || 12;
  const font = `${settings.labelWeight || '600'} ${fontSize}px ${settings.labelFont || 'system-ui, sans-serif'}`;
  const labelX = data.x + data.size + 7;
  const labelY = data.y + fontSize / 3;

  context.save();
  context.font = font;
  const textWidth = context.measureText(label).width;
  const paddingX = 7;
  const paddingY = 4;
  const boxX = labelX - paddingX;
  const boxY = labelY - fontSize - paddingY + 1;
  const boxWidth = textWidth + paddingX * 2;
  const boxHeight = fontSize + paddingY * 2;

  context.fillStyle = graphThemeValue('--kb-graph-label-bubble-bg', 'rgba(3, 7, 18, 0.74)');
  context.strokeStyle = graphThemeValue('--kb-graph-label-bubble-border', 'rgba(255, 255, 255, 0.22)');
  context.lineWidth = 1;
  context.beginPath();
  context.roundRect(boxX, boxY, boxWidth, boxHeight, 6);
  context.fill();
  context.stroke();

  context.lineWidth = 3;
  context.strokeStyle = graphThemeValue('--kb-graph-label-bubble-stroke', 'rgba(3, 7, 18, 0.92)');
  context.strokeText(label, labelX, labelY);
  context.fillStyle = graphThemeValue('--kb-graph-label-bubble-text', data.labelColor || settings.labelColor?.color || '#FFFFFF');
  context.fillText(label, labelX, labelY);
  context.restore();
};

const renderSigmaGraph = async () => {
  await nextTick();
  if (!graphContainer.value || activeTab.value !== 'graph') return;
  destroySigma();

  const graph = new Graph({ type: 'undirected', multi: false });
  const count = Math.max(1, graphNodes.value.length);
  graphNodes.value.forEach((node, index) => {
    const angle = index * 2.399963;
    const radius = Math.sqrt((index + 1) / count);
    graph.addNode(node.id, {
      label: node.label,
      color: node.color,
      labelColor: graphThemeValue('--kb-graph-label', '#FFFFFF'),
      size: node.size,
      originalSize: node.size,
      degree: node.degree,
      type: 'default',
      borderColor: NODE_BORDER_COLOR,
      borderSize: 0.2,
      zIndex: node.degree,
      // 入场动画的错峰延迟（0~0.55），越靠后越晚出现
      revealDelay: count > 1 ? (index / count) * 0.55 : 0,
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
    });
  });

  graphEdges.value.forEach((edge) => {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) return;
    if (graph.hasEdge(edge.source, edge.target)) return;
    graph.addEdgeWithKey(edge.id, edge.source, edge.target, {
      label: edge.label,
      size: Math.max(0.35, Math.min(2.6, Math.sqrt(edge.weight || 1) * 0.7)),
      originalWeight: edge.weight || 1,
      color: EDGE_COLOR_DARK,
      type: 'curvedNoArrow',
      zIndex: 0,
    });
  });

  if (graph.order > 1) {
    forceAtlas2.assign(graph, {
      iterations: graph.order > 300 ? 32 : 54,
      settings: {
        ...forceAtlas2.inferSettings(graph),
        gravity: 0.08,
        scalingRatio: 8,
        slowDown: 10,
      },
    });
  }

  sigmaGraph = graph;
  originalGraphPositions = new Map(
    graph.nodes().map((nodeId) => [
      nodeId,
      {
        x: graph.getNodeAttribute(nodeId, 'x'),
        y: graph.getNodeAttribute(nodeId, 'y'),
      },
    ]),
  );

  // 构建弹簧仿真状态（锚点、边自然长度、初始速度）
  buildSimState();

  // 开启入场动画：首帧即为"收缩态"，随后逐个浮现
  fxRevealing = !REDUCED_MOTION && graph.order > 1;
  fxRevealProgress = fxRevealing ? 0 : 1;

  sigmaInstance = new Sigma(graph, graphContainer.value, {
    allowInvalidContainer: true,
    autoCenter: true,
    autoRescale: true,
    defaultEdgeType: 'curvedNoArrow',
    defaultNodeColor: DEFAULT_NODE_COLOR,
    defaultNodeType: 'default',
    edgeProgramClasses: {
      curvedNoArrow: createEdgeCurveProgram(),
    },
    nodeProgramClasses: {
      default: NodeBorderProgram,
    },
    defaultDrawNodeHover: () => {},
    defaultDrawNodeLabel: drawReadableNodeLabel,
    enableEdgeEvents: false,
    hideEdgesOnMove: true,
    hideLabelsOnMove: true,
    labelColor: { color: graphThemeValue('--kb-graph-label', '#FFFFFF'), attribute: 'labelColor' },
    labelDensity: 0.04,
    labelGridCellSize: 60,
    labelRenderedSizeThreshold: 7,
    labelSize: 12,
    labelWeight: '600',
    minCameraRatio: 0.08,
    maxCameraRatio: 8,
    edgeLabelColor: { color: graphThemeValue('--kb-graph-label', '#FFFFFF') },
    edgeLabelSize: 11,
    renderEdgeLabels: graphShowEdgeLabels.value,
    renderLabels: true,
    zIndex: true,
    nodeReducer: (nodeId, data) => {
      const keyword = graphSearch.value.trim().toLowerCase();
      const current = graphNodeMap.get(nodeId);
      const focusedId = focusedNode.value?.id || selectedNode.value?.id || '';
      const selectedFocusId = selectedNode.value?.id || '';
      const selected = selectedNode.value?.id === nodeId;
      const focused = focusedNode.value?.id === nodeId;
      const related = !focusedId || nodeId === focusedId || graph.hasEdge(nodeId, focusedId);
      const selectedRelated = !selectedFocusId || nodeId === selectedFocusId || graph.hasEdge(nodeId, selectedFocusId);
      const matches = Boolean(keyword) && Boolean(current?.lowerLabel.includes(keyword) || current?.lowerDescription.includes(keyword));
      const showLabel = graphLabelMode.value === 'all'
        || (graphLabelMode.value !== 'none' && (
          selected
          || focused
          || matches
          || (graphShowRelatedLabels.value && Boolean(selectedFocusId) && selectedRelated)
          || (!keyword && Number(data.degree || 0) >= 6 && graph.order <= 220)
        ));
      // 入场时按错峰进度缩放节点尺寸（0→1），形成"逐个浮现"效果
      let revealScale = 1;
      if (fxRevealing) {
        const delay = Number(data.revealDelay || 0);
        const local = Math.max(0, Math.min(1, (fxRevealProgress - delay) / Math.max(0.001, 1 - delay)));
        revealScale = local * local * (3 - 2 * local); // smoothstep
      }
      const baseSize = selected ? data.originalSize + 3 : focused || matches ? data.originalSize + 1.5 : data.originalSize;
      return {
        ...data,
        hidden: (graphFocusMode.value && Boolean(selectedFocusId) && !selectedRelated) || (fxRevealing && revealScale <= 0.02),
        borderColor: selected ? NODE_BORDER_SELECTED : NODE_BORDER_COLOR,
        color: focusedId && !related
          ? graphThemeValue('--kb-node-disabled', NODE_COLOR_DISABLED)
          : keyword && !matches && !selected
            ? graphThemeValue('--kb-node-disabled', NODE_COLOR_DISABLED)
            : data.color,
        label: showLabel ? data.label : '',
        labelColor: graphThemeValue('--kb-graph-label', '#FFFFFF'),
        forceLabel: showLabel && (selected || focused || matches || (graphShowRelatedLabels.value && Boolean(selectedFocusId) && selectedRelated)),
        size: baseSize * revealScale,
        zIndex: selected ? 9999 : focused || matches ? 8000 : Number(data.degree || 0),
      };
    },
    edgeReducer: (edgeId, data) => {
      const edge = graphEdgeMap.get(edgeId);
      const focusedId = focusedNode.value?.id || selectedNode.value?.id || '';
      const selectedFocusId = selectedNode.value?.id || '';
      const active = !focusedId || edge?.source === focusedId || edge?.target === focusedId;
      const selectedActive = !selectedFocusId || edge?.source === selectedFocusId || edge?.target === selectedFocusId;
      const searching = Boolean(graphSearch.value.trim());
      const showEdgeLabel = graphShowEdgeLabels.value && (active || !focusedId);
      return {
        ...data,
        color: focusedId && active ? EDGE_HIGHLIGHT_COLOR : EDGE_COLOR_DARK,
        hidden: fxRevealing || !graphShowEdges.value || (graphFocusMode.value && Boolean(selectedFocusId) && !selectedActive) || (searching && !active),
        label: showEdgeLabel ? data.label : '',
        forceLabel: showEdgeLabel,
        size: active ? data.size : Math.max(0.2, data.size * 0.5),
        zIndex: active ? 2 : 0,
      };
    },
  });

  sigmaInstance.on('enterNode', ({ node, event }) => {
    if (event.original?.buttons) return;
    focusedNode.value = graphNodeMap.get(node) || null;
  });

  sigmaInstance.on('leaveNode', ({ event }) => {
    if (event.original?.buttons) return;
    focusedNode.value = null;
  });

  sigmaInstance.on('clickNode', ({ node }) => {
    if (suppressNextNodeClick) {
      suppressNextNodeClick = false;
      return;
    }
    selectedNode.value = graphNodes.value.find((item) => item.id === node) || selectedNode.value;
    // 选中时给该节点一个轻微冲量，让它和邻居"弹一下"
    nudgeNode(node, 0.16);
  });

  sigmaInstance.on('downNode', ({ node, event }) => {
    draggedNodeId = node;
    dragStartViewport = { x: event.x, y: event.y };
    draggedNodeMoved = false;
    event.preventSigmaDefault();
    sigmaInstance?.setSetting('enableCameraPanning', false);
    graphContainer.value?.classList.add('is-dragging-node');
    // 按住即固定该节点并启动弹簧仿真，邻居随之联动
    pinnedNodeId = node;
    startSim();
  });

  sigmaInstance.on('clickStage', () => {
    if (graphFocusMode.value) return;
    selectedNode.value = null;
    focusedNode.value = null;
  });

  const releaseDraggedNode = () => {
    if (!draggedNodeId) return;
    suppressNextNodeClick = draggedNodeMoved;
    // 松手后把锚点更新到落点，让邻居弹性收敛到新的平衡态而非弹回原位
    if (sigmaGraph?.hasNode(draggedNodeId) && simRest.has(draggedNodeId)) {
      simRest.set(draggedNodeId, {
        x: sigmaGraph.getNodeAttribute(draggedNodeId, 'x'),
        y: sigmaGraph.getNodeAttribute(draggedNodeId, 'y'),
      });
    }
    pinnedNodeId = null;
    draggedNodeId = null;
    dragStartViewport = null;
    draggedNodeMoved = false;
    sigmaInstance?.setSetting('enableCameraPanning', true);
    graphContainer.value?.classList.remove('is-dragging-node');
    startSim(); // 继续跑仿真直到自动收敛静止
  };

  const mouseCaptor = sigmaInstance.getMouseCaptor();
  mouseCaptor.on('mousemovebody', (event) => {
    if (!draggedNodeId || !sigmaGraph?.hasNode(draggedNodeId)) return;
    event.preventSigmaDefault();
    const dx = event.x - (dragStartViewport?.x || event.x);
    const dy = event.y - (dragStartViewport?.y || event.y);
    if (!draggedNodeMoved && Math.hypot(dx, dy) < 4) return;
    draggedNodeMoved = true;
    const position = sigmaInstance.viewportToGraph({ x: event.x, y: event.y });
    sigmaGraph.setNodeAttribute(draggedNodeId, 'x', position.x);
    sigmaGraph.setNodeAttribute(draggedNodeId, 'y', position.y);
    // 仿真在跑时由 simTick 统一刷新；否则（如减弱动画）自行刷新保证拖拽可用
    if (!simRunning) sigmaInstance.refresh({ skipIndexation: true });
  });
  mouseCaptor.on('mouseup', releaseDraggedNode);
  mouseCaptor.on('mouseleave', releaseDraggedNode);

  // 启动极光叠层动画与入场展开动画
  setupFx();
  runRevealAnimation();
};

const zoomGraph = (delta) => {
  const camera = sigmaInstance?.getCamera();
  if (!camera) return;
  const ratio = camera.getState().ratio;
  camera.animate({ ratio: Math.max(0.08, Math.min(8, ratio * (delta > 0 ? 0.78 : 1.28))) }, { duration: 180 });
};

const resetGraphView = () => {
  stopSim();
  if (sigmaGraph && originalGraphPositions.size) {
    originalGraphPositions.forEach((position, nodeId) => {
      if (!sigmaGraph.hasNode(nodeId)) return;
      sigmaGraph.setNodeAttribute(nodeId, 'x', position.x);
      sigmaGraph.setNodeAttribute(nodeId, 'y', position.y);
      // 同步复位弹簧锚点与速度，让重置后图谱真正静止在原始布局
      if (simRest.has(nodeId)) simRest.set(nodeId, { x: position.x, y: position.y });
      if (nodeVel.has(nodeId)) nodeVel.set(nodeId, { vx: 0, vy: 0 });
    });
    sigmaInstance?.refresh({ skipIndexation: true });
  }
  sigmaInstance?.getCamera().animatedReset({ duration: 220 });
};

const safeFilePart = (value) =>
  String(value || 'all')
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '-')
    .slice(0, 60) || 'all';

const exportGraphImage = () => {
  if (!graphContainer.value || !graphNodes.value.length) return;

  sigmaInstance?.refresh();
  const rect = graphContainer.value.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const pixelRatio = 6;
  const output = document.createElement('canvas');
  output.width = Math.round(width * pixelRatio);
  output.height = Math.round(height * pixelRatio);

  const context = output.getContext('2d');
  if (!context) return;

  const canvasBg = graphThemeValue('--kb-canvas', '#dcebf7');
  context.fillStyle = canvasBg;
  context.fillRect(0, 0, output.width, output.height);

  const layers = Array.from(graphContainer.value.querySelectorAll('canvas'));
  layers.forEach((layer) => {
    const layerRect = layer.getBoundingClientRect();
    const dx = Math.round((layerRect.left - rect.left) * pixelRatio);
    const dy = Math.round((layerRect.top - rect.top) * pixelRatio);
    const dw = Math.round(layerRect.width * pixelRatio);
    const dh = Math.round(layerRect.height * pixelRatio);
    if (dw > 0 && dh > 0) context.drawImage(layer, dx, dy, dw, dh);
  });

  const link = document.createElement('a');
  const date = new Date().toISOString().slice(0, 10);
  link.download = `knowledge-graph-${safeFilePart(selectedLabel.value)}-${date}.png`;
  link.href = output.toDataURL('image/png');
  link.click();
};

const toggleGraphFullscreen = async () => {
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
      return;
    }
    await graphPanel.value?.requestFullscreen?.();
  } catch (error) {
    errorMessage.value = error.message || '无法进入全屏模式';
  }
};

const handleFullscreenChange = () => {
  isGraphFullscreen.value = document.fullscreenElement === graphPanel.value;
  window.setTimeout(() => {
    sigmaInstance?.resize();
    sigmaInstance?.refresh();
    resizeFx();
  }, 80);
};

const compactSummary = (value) => String(value || '').replace(/\s+/g, ' ').trim() || '-';
const documentName = (doc) => {
  const summary = String(doc?.content_summary || '').replace(/\r\n/g, '\n');
  const ocrTitle = summary.match(/#\s*OCR text for\s+(.+?)(?:\n|$)/i)?.[1]?.trim();
  const raw = String(ocrTitle || doc?.file_path || doc?.id || '知识文档').trim();
  const name = raw.split(/[\\/]/).filter(Boolean).pop() || raw;
  return name
    .replace(/\s*\(z-library[^)]*\)/i, '')
    .replace(/\s*-\s*=+\s*Page\s+\d+.*$/i, '')
    .replace(/\s+/g, ' ')
    .trim();
};
const documentMeta = (doc) => {
  const chunks = Number(doc?.chunks_count || 0);
  const length = Number(doc?.content_length || 0);
  const parts = [];
  if (chunks > 0) parts.push(`${formatNumber(chunks)} 个知识片段`);
  if (length > 0) parts.push(`${formatNumber(length)} 字符`);
  return parts.join(' · ') || compactSummary(doc?.content_summary);
};
const formatNumber = (value) => Number(value || 0).toLocaleString();
const formatTime = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
};
const statusText = (status) => ({ processed: '已完成', processing: '处理中', preprocessed: '预处理', pending: '待处理', failed: '失败' }[String(status).toLowerCase()] || status || '-');
const statusClass = (status) => `is-${String(status || '').toLowerCase()}`;
const statusCount = (value) => {
  if (!value) return statusCounts.value.all || 0;
  return statusCounts.value[value] || statusCounts.value[value.toUpperCase()] || 0;
};
const formatReference = (reference, index) => {
  const raw = String(reference?.file_path || reference?.reference_id || `引用 ${index + 1}`).trim();
  const name = raw.split(/[\\/]/).filter(Boolean).pop() || raw;
  return name.length > 34 ? `${name.slice(0, 32)}...` : name;
};

onMounted(async () => {
  document.addEventListener('fullscreenchange', handleFullscreenChange);
  const [documentsOk, pipelineOk] = await Promise.all([loadDocuments(), loadPipelineStatus()]);
  if (!documentsOk && !pipelineOk) return;

  try {
    await loadGraphLabels();
    await loadGraph();
  } catch (error) {
    errorMessage.value = error.message;
  }
});

onBeforeUnmount(() => {
  stopPolling();
  document.removeEventListener('fullscreenchange', handleFullscreenChange);
  statTweenRafs.forEach((raf) => window.cancelAnimationFrame(raf));
  statTweenRafs.clear();
  destroySigma();
});

watch(activeTab, (tab) => {
  if (tab === 'graph') {
    renderSigmaGraph();
  } else {
    stopFx();
    stopSim();
  }
});

// 图谱数据变化时，触发统计数字的滚动动画
watch([graphNodes, graphEdges, graphLabels], () => {
  animateGraphStats();
}, { immediate: true });

watch([graphSearch, selectedNode, focusedNode, graphLabelMode, graphShowEdges, graphFocusMode, graphShowRelatedLabels, graphShowEdgeLabels], () => {
  refreshSigma();
});
</script>

<style scoped>
/* ============================================================
   极光玻璃（Aurora Glass）主题 —— 知识图谱页面
   柔雾极光渐变 + 磨砂玻璃面板 + 柔光节点 + 丰富动画
   ============================================================ */

.lightrag-console.white-knowledge-console {
  /* —— 极光调色板 —— */
  --kb-aurora-1: #6366f1;   /* 靛蓝 */
  --kb-aurora-2: #a855f7;   /* 紫 */
  --kb-aurora-3: #ec4899;   /* 粉 */
  --kb-aurora-4: #38bdf8;   /* 天蓝 */
  --kb-aurora-5: #22d3ee;   /* 青 */

  --kb-bg: #eef1fb;
  --kb-panel: rgba(255, 255, 255, 0.62);
  --kb-panel-strong: rgba(255, 255, 255, 0.78);
  --kb-panel-muted: rgba(255, 255, 255, 0.45);
  --kb-glass-border: rgba(255, 255, 255, 0.7);
  --kb-input: rgba(255, 255, 255, 0.66);
  --kb-table-head: rgba(255, 255, 255, 0.66);
  --kb-canvas: #f3f5ff;
  --kb-grid: rgba(99, 102, 241, 0.08);
  --kb-text: #24304d;
  --kb-text-soft: #4a577a;
  --kb-text-muted: #8492b4;
  --kb-border: rgba(148, 163, 220, 0.32);
  --kb-border-soft: rgba(148, 163, 220, 0.2);
  --kb-accent: #7c3aed;
  --kb-accent-strong: #6d28d9;
  --kb-accent-text: #ffffff;
  --kb-cyan: #0ea5e9;
  --kb-danger: #ef4476;
  --kb-success: #10b981;
  --kb-info: #3b82f6;
  --kb-link: #6d28d9;
  --kb-shadow: 0 20px 50px rgba(80, 70, 160, 0.14), 0 6px 18px rgba(80, 70, 160, 0.08);
  --kb-shadow-hover: 0 26px 60px rgba(96, 74, 180, 0.22);
  --kb-glow: 0 0 0 1px rgba(255, 255, 255, 0.55) inset;

  /* 图谱画布用变量（JS graphThemeValue 会读取） */
  --kb-edge: rgba(120, 132, 180, 0.45);
  --kb-node-stroke: #ffffff;
  --kb-node-disabled: #d7dcec;
  --kb-graph-label: #2a3559;
  --kb-graph-label-bubble-bg: rgba(255, 255, 255, 0.9);
  --kb-graph-label-bubble-border: rgba(124, 58, 237, 0.28);
  --kb-graph-label-bubble-text: #26314f;
  --kb-graph-label-bubble-stroke: rgba(255, 255, 255, 0.95);
  --kb-canvas-glow: rgba(124, 58, 237, 0.1);
  --kb-canvas-line: rgba(120, 132, 190, 0.12);

  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 16px 20px 20px;
  overflow: hidden;
  color: var(--kb-text);
  background:
    radial-gradient(1200px 800px at 8% -10%, rgba(99, 102, 241, 0.22), transparent 55%),
    radial-gradient(1000px 700px at 100% 0%, rgba(236, 72, 153, 0.18), transparent 52%),
    radial-gradient(1100px 900px at 50% 120%, rgba(56, 189, 248, 0.2), transparent 55%),
    var(--kb-bg);
  position: relative;
  isolation: isolate;
}

/* —— 极光漂移背景层 —— */
.white-knowledge-console::before,
.white-knowledge-console::after {
  content: '';
  position: absolute;
  z-index: -1;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.55;
  pointer-events: none;
}

.white-knowledge-console::before {
  width: 46vw;
  height: 46vw;
  top: -16vw;
  left: -10vw;
  background: conic-gradient(from 90deg, var(--kb-aurora-1), var(--kb-aurora-2), var(--kb-aurora-4), var(--kb-aurora-1));
  animation: aurora-drift-a 22s ease-in-out infinite alternate;
}

.white-knowledge-console::after {
  width: 40vw;
  height: 40vw;
  right: -12vw;
  bottom: -18vw;
  background: conic-gradient(from 210deg, var(--kb-aurora-3), var(--kb-aurora-5), var(--kb-aurora-2), var(--kb-aurora-3));
  animation: aurora-drift-b 26s ease-in-out infinite alternate;
}

@keyframes aurora-drift-a {
  0%   { transform: translate(0, 0) rotate(0deg) scale(1); }
  100% { transform: translate(8vw, 6vw) rotate(120deg) scale(1.15); }
}

@keyframes aurora-drift-b {
  0%   { transform: translate(0, 0) rotate(0deg) scale(1.05); }
  100% { transform: translate(-7vw, -5vw) rotate(-100deg) scale(1.2); }
}

/* ============ 通用玻璃与按钮 ============ */
.white-knowledge-console button,
.white-knowledge-console .upload-button,
.white-knowledge-console select,
.white-knowledge-console input {
  border: 1px solid var(--kb-border);
  border-radius: 12px;
  color: var(--kb-text-soft);
  background: var(--kb-input);
  font-weight: 600;
  transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1),
              box-shadow 0.28s ease, border-color 0.28s ease,
              background 0.28s ease, color 0.28s ease;
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.white-knowledge-console button,
.white-knowledge-console .upload-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 38px;
  padding: 7px 14px;
  font-size: 12.5px;
  cursor: pointer;
}

.white-knowledge-console button:not(:disabled):hover,
.white-knowledge-console .upload-button:hover,
.white-knowledge-console select:hover,
.white-knowledge-console input:hover {
  border-color: color-mix(in srgb, var(--kb-accent) 55%, transparent);
  box-shadow: 0 6px 18px color-mix(in srgb, var(--kb-accent) 18%, transparent);
  color: var(--kb-accent-strong);
}

.white-knowledge-console button:not(:disabled):active,
.white-knowledge-console .upload-button:active {
  transform: scale(0.95);
}

.white-knowledge-console button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.white-knowledge-console .upload-button {
  position: relative;
  overflow: hidden;
  color: #fff;
  border-color: transparent;
  background: linear-gradient(120deg, var(--kb-aurora-1), var(--kb-aurora-2) 55%, var(--kb-aurora-3));
  background-size: 200% 100%;
  box-shadow: 0 8px 22px rgba(124, 58, 237, 0.32);
  animation: gradient-pan 6s linear infinite;
}

.white-knowledge-console .upload-button:hover {
  color: #fff;
  transform: translateY(-2px);
  box-shadow: 0 12px 30px rgba(124, 58, 237, 0.4);
}

.white-knowledge-console .upload-button input {
  display: none;
}

@keyframes gradient-pan {
  0% { background-position: 0% 0%; }
  100% { background-position: 200% 0%; }
}

.white-knowledge-console .spinning {
  animation: kb-spin 800ms linear infinite;
}

@keyframes kb-spin {
  to { transform: rotate(360deg); }
}

/* ============ 顶部标题栏 ============ */
.white-knowledge-console .knowledge-console-header {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: minmax(240px, 1fr) auto minmax(180px, 1fr);
  align-items: center;
  gap: 18px;
  min-height: 62px;
  padding: 10px 18px;
  border: 1px solid var(--kb-glass-border);
  border-radius: 18px;
  background: var(--kb-panel-strong);
  box-shadow: var(--kb-shadow), var(--kb-glow);
  backdrop-filter: blur(22px) saturate(1.2);
  -webkit-backdrop-filter: blur(22px) saturate(1.2);
  animation: panel-enter 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;
}

.white-knowledge-console .console-heading {
  display: flex;
  align-items: center;
  gap: 13px;
  min-width: 0;
}

.white-knowledge-console .console-mark {
  display: grid;
  flex: 0 0 42px;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 13px;
  color: #fff;
  background: linear-gradient(135deg, var(--kb-aurora-1), var(--kb-aurora-2) 55%, var(--kb-aurora-3));
  background-size: 180% 180%;
  font-size: 20px;
  box-shadow: 0 8px 20px rgba(124, 58, 237, 0.35);
  animation: gradient-pan 7s linear infinite, mark-float 4s ease-in-out infinite;
}

@keyframes mark-float {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  50% { transform: translateY(-3px) rotate(-4deg); }
}

.white-knowledge-console .console-heading strong,
.white-knowledge-console .console-heading span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.white-knowledge-console .console-heading strong {
  font-size: 16px;
  font-weight: 800;
  letter-spacing: 0.01em;
  background: linear-gradient(100deg, var(--kb-aurora-1), var(--kb-aurora-2) 50%, var(--kb-aurora-3));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.white-knowledge-console .console-heading div > span {
  margin-top: 2px;
  color: var(--kb-text-muted);
  font-size: 11px;
  letter-spacing: 0.04em;
}

/* —— 标签页 —— */
.white-knowledge-console .console-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--kb-glass-border);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.5);
  box-shadow: var(--kb-glow);
  backdrop-filter: blur(10px);
}

.white-knowledge-console .console-tabs button {
  min-height: 38px;
  padding: 6px 18px;
  border: 0;
  border-radius: 11px;
  color: var(--kb-text-muted);
  background: transparent;
  font-size: 13px;
  font-weight: 700;
}

.white-knowledge-console .console-tabs button:hover {
  color: var(--kb-accent-strong);
  background: rgba(124, 58, 237, 0.08);
  box-shadow: none;
  transform: none;
}

.white-knowledge-console .console-tabs button.active {
  color: #fff;
  background: linear-gradient(120deg, var(--kb-aurora-1), var(--kb-aurora-2) 60%, var(--kb-aurora-3));
  background-size: 180% 100%;
  box-shadow: 0 8px 20px rgba(124, 58, 237, 0.35);
  animation: gradient-pan 6s linear infinite;
}

.white-knowledge-console .console-tabs button strong {
  min-width: 20px;
  padding: 2px 7px;
  border-radius: 999px;
  color: inherit;
  background: rgba(255, 255, 255, 0.28);
  font-size: 10px;
}

.white-knowledge-console .console-tabs button:not(.active) strong {
  background: rgba(124, 58, 237, 0.12);
  color: var(--kb-accent-strong);
}

/* —— 服务状态 —— */
.white-knowledge-console .service-state {
  display: inline-flex;
  justify-self: end;
  align-items: center;
  gap: 9px;
  padding: 7px 14px;
  border-radius: 999px;
  border: 1px solid var(--kb-border);
  background: rgba(255, 255, 255, 0.5);
  color: var(--kb-danger);
  font-size: 12px;
  font-weight: 700;
  backdrop-filter: blur(8px);
}

.white-knowledge-console .service-state i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 0 currentColor;
  animation: status-pulse 2s ease-out infinite;
}

.white-knowledge-console .service-state.online {
  color: var(--kb-success);
}

@keyframes status-pulse {
  0% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 55%, transparent); }
  70% { box-shadow: 0 0 0 8px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
}

/* ============ 告警条 ============ */
.white-knowledge-console .console-alert {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 9px 14px;
  border: 1px solid color-mix(in srgb, var(--kb-danger) 35%, transparent);
  border-radius: 14px;
  color: #b02a54;
  background: color-mix(in srgb, var(--kb-danger) 12%, rgba(255, 255, 255, 0.7));
  font-size: 13px;
  backdrop-filter: blur(12px);
  box-shadow: var(--kb-shadow);
  animation: alert-in 0.45s cubic-bezier(0.16, 1, 0.3, 1) both;
}

.white-knowledge-console .console-alert span { flex: 1; }

.white-knowledge-console .console-alert button {
  width: 30px;
  min-width: 30px;
  min-height: 30px;
  padding: 0;
  border: 0;
  background: transparent;
}

@keyframes alert-in {
  from { opacity: 0; transform: translateY(-10px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

/* ============ 面板 ============ */
.white-knowledge-console .console-panel,
.white-knowledge-console .documents-panel,
.white-knowledge-console .graph-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  border: 1px solid var(--kb-glass-border);
  border-radius: 20px;
  background: var(--kb-panel);
  box-shadow: var(--kb-shadow), var(--kb-glow);
  overflow: hidden;
  backdrop-filter: blur(24px) saturate(1.25);
  -webkit-backdrop-filter: blur(24px) saturate(1.25);
  animation: panel-enter 0.65s cubic-bezier(0.16, 1, 0.3, 1) both;
  animation-delay: 0.08s;
}

@keyframes panel-enter {
  from { opacity: 0; transform: translateY(16px) scale(0.99); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

/* —— 工具栏 —— */
.white-knowledge-console .panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 78px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--kb-border-soft);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.55), rgba(255, 255, 255, 0.15));
}

.white-knowledge-console .panel-toolbar h3 {
  margin: 3px 0;
  color: var(--kb-text);
  font-size: 18px;
  font-weight: 800;
  line-height: 1.25;
}

.white-knowledge-console .panel-toolbar p {
  margin: 0;
  color: var(--kb-text-muted);
  font-size: 12px;
}

.white-knowledge-console .panel-kicker {
  color: var(--kb-accent);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.white-knowledge-console .actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

/* —— 通知 —— */
.white-knowledge-console .notice {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 20px 0;
  padding: 10px 14px;
  border: 1px solid color-mix(in srgb, var(--kb-info) 30%, transparent);
  border-radius: 12px;
  color: var(--kb-info);
  background: color-mix(in srgb, var(--kb-info) 10%, rgba(255, 255, 255, 0.6));
  font-size: 12.5px;
  backdrop-filter: blur(8px);
  animation: alert-in 0.4s ease-out both;
}

/* —— 状态筛选 —— */
.white-knowledge-console .status-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--kb-border-soft);
}

.white-knowledge-console .status-filters button {
  min-height: 34px;
  padding: 6px 14px;
  border-radius: 999px;
  color: var(--kb-text-muted);
  background: rgba(255, 255, 255, 0.5);
}

.white-knowledge-console .status-filters button.active {
  color: #fff;
  border-color: transparent;
  background: linear-gradient(120deg, var(--kb-aurora-1), var(--kb-aurora-2));
  box-shadow: 0 6px 16px rgba(124, 58, 237, 0.3);
}

.white-knowledge-console .status-filters button strong {
  margin-left: 5px;
  padding: 1px 7px;
  border-radius: 999px;
  color: inherit;
  background: color-mix(in srgb, var(--kb-accent) 14%, transparent);
  font-size: 11px;
}

.white-knowledge-console .status-filters button.active strong {
  background: rgba(255, 255, 255, 0.28);
}

/* ============ 文档表格 ============ */
.white-knowledge-console .document-table-shell {
  flex: 1;
  margin: 0;
  overflow: auto;
  background: transparent;
}

.white-knowledge-console .document-table {
  width: 100%;
  min-width: 1080px;
  border-collapse: collapse;
}

.white-knowledge-console .document-table th,
.white-knowledge-console .document-table td {
  padding: 13px 16px;
  border-bottom: 1px solid var(--kb-border-soft);
  text-align: left;
  vertical-align: middle;
  color: var(--kb-text-soft);
  font-size: 12.5px;
}

.white-knowledge-console .document-table th {
  position: sticky;
  top: 0;
  z-index: 2;
  color: var(--kb-text-muted);
  font-weight: 800;
  font-size: 11px;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(10px);
}

.white-knowledge-console .document-table tbody tr {
  transition: background 0.25s ease, transform 0.25s ease;
  animation: row-in 0.5s cubic-bezier(0.16, 1, 0.3, 1) both;
}

/* 行错峰入场 */
.white-knowledge-console .document-table tbody tr:nth-child(1) { animation-delay: 0.02s; }
.white-knowledge-console .document-table tbody tr:nth-child(2) { animation-delay: 0.06s; }
.white-knowledge-console .document-table tbody tr:nth-child(3) { animation-delay: 0.1s; }
.white-knowledge-console .document-table tbody tr:nth-child(4) { animation-delay: 0.14s; }
.white-knowledge-console .document-table tbody tr:nth-child(5) { animation-delay: 0.18s; }
.white-knowledge-console .document-table tbody tr:nth-child(6) { animation-delay: 0.22s; }
.white-knowledge-console .document-table tbody tr:nth-child(7) { animation-delay: 0.26s; }
.white-knowledge-console .document-table tbody tr:nth-child(8) { animation-delay: 0.3s; }
.white-knowledge-console .document-table tbody tr:nth-child(9) { animation-delay: 0.34s; }
.white-knowledge-console .document-table tbody tr:nth-child(10) { animation-delay: 0.38s; }

@keyframes row-in {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}

.white-knowledge-console .document-table tbody tr:hover {
  background: linear-gradient(90deg, color-mix(in srgb, var(--kb-accent) 8%, transparent), transparent);
}

.white-knowledge-console .document-title-cell {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 290px;
}

.white-knowledge-console .document-title-cell > div { min-width: 0; }

.white-knowledge-console .document-title-cell strong,
.white-knowledge-console .document-title-cell small {
  display: block;
  max-width: 250px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.white-knowledge-console .document-title-cell strong {
  margin-bottom: 3px;
  color: var(--kb-text);
  font-size: 12.5px;
  font-weight: 700;
}

.white-knowledge-console .document-title-cell small { color: var(--kb-text-muted); font-size: 10px; }

.white-knowledge-console .document-icon {
  display: grid;
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 11px;
  color: var(--kb-accent);
  background: color-mix(in srgb, var(--kb-accent) 12%, rgba(255, 255, 255, 0.6));
  font-size: 16px;
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.white-knowledge-console .document-table tbody tr:hover .document-icon {
  transform: scale(1.12) rotate(-6deg);
}

.white-knowledge-console .summary-cell {
  max-width: 350px;
  overflow: hidden;
  color: var(--kb-text-soft);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.white-knowledge-console .mono {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
  color: var(--kb-text-muted);
}

.white-knowledge-console .status-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 25px;
  padding: 3px 10px;
  border-radius: 999px;
  color: var(--kb-text-muted);
  background: rgba(148, 163, 220, 0.16);
  font-size: 10.5px;
  font-weight: 800;
}

.white-knowledge-console .status-chip::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.white-knowledge-console .status-chip.is-processed { color: var(--kb-success); background: color-mix(in srgb, var(--kb-success) 14%, transparent); }
.white-knowledge-console .status-chip.is-processing,
.white-knowledge-console .status-chip.is-preprocessed { color: var(--kb-info); background: color-mix(in srgb, var(--kb-info) 14%, transparent); }
.white-knowledge-console .status-chip.is-processing::before { animation: status-pulse 1.5s ease-out infinite; }
.white-knowledge-console .status-chip.is-failed { color: var(--kb-danger); background: color-mix(in srgb, var(--kb-danger) 14%, transparent); }

.white-knowledge-console .empty-row {
  height: 320px;
  color: var(--kb-text-muted);
  text-align: center !important;
  font-size: 13px;
}

/* —— 分页 —— */
.white-knowledge-console .pagination-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  min-height: 52px;
  padding: 8px 16px;
  border-top: 1px solid var(--kb-border-soft);
  color: var(--kb-text-muted);
  font-size: 12px;
  font-weight: 600;
}

.white-knowledge-console .pagination-bar div {
  display: flex;
  align-items: center;
  gap: 10px;
}

.white-knowledge-console .pagination-bar button {
  width: 34px;
  min-width: 34px;
  min-height: 34px;
  padding: 0;
  border-radius: 50%;
}

/* ============ 图谱工具栏 ============ */
.white-knowledge-console .graph-toolbar {
  position: relative;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  min-height: 58px;
  padding: 11px 16px;
  border-bottom: 1px solid var(--kb-border-soft);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.55), rgba(255, 255, 255, 0.12));
  overflow: visible;
}

.white-knowledge-console .graph-query-controls,
.white-knowledge-console .graph-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.white-knowledge-console .graph-query-controls > button,
.white-knowledge-console .graph-actions button {
  width: 38px;
  min-width: 38px;
  min-height: 38px;
  padding: 0;
}

.white-knowledge-console .graph-actions button.active {
  color: #fff;
  border-color: transparent;
  background: linear-gradient(135deg, var(--kb-aurora-1), var(--kb-aurora-2));
  box-shadow: 0 6px 16px rgba(124, 58, 237, 0.32);
}

.white-knowledge-console .graph-actions select {
  width: 116px;
  height: 38px;
  padding: 0 10px;
  font-size: 11.5px;
}

/* —— 自定义下拉 —— */
.white-knowledge-console .custom-select {
  position: relative;
  flex: 0 0 250px;
  min-width: 190px;
  outline: none;
}

.white-knowledge-console .select-trigger {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 38px;
  padding: 0 14px;
  border: 1px solid var(--kb-border);
  border-radius: 12px;
  color: var(--kb-text-soft);
  background: var(--kb-input);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition: border-color 0.25s ease, box-shadow 0.25s ease, background 0.25s ease;
}

.white-knowledge-console .custom-select.is-disabled .select-trigger { opacity: 0.6; cursor: not-allowed; }

.white-knowledge-console .custom-select:not(.is-disabled) .select-trigger:hover {
  border-color: color-mix(in srgb, var(--kb-accent) 55%, transparent);
  box-shadow: 0 6px 18px color-mix(in srgb, var(--kb-accent) 16%, transparent);
}

.white-knowledge-console .custom-select.is-open .select-trigger {
  border-color: var(--kb-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--kb-accent) 18%, transparent);
}

.white-knowledge-console .select-trigger > span {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.white-knowledge-console .select-trigger i:first-child { color: var(--kb-accent); }

.white-knowledge-console .select-trigger i.rotate { transform: rotate(180deg); }
.white-knowledge-console .select-trigger i:last-child {
  color: var(--kb-text-muted);
  transition: transform 0.3s ease;
}

.white-knowledge-console .select-options {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  z-index: 10000;
  max-height: 320px;
  overflow-y: auto;
  padding: 6px;
  border: 1px solid var(--kb-glass-border);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.85);
  box-shadow: 0 20px 46px rgba(80, 70, 160, 0.22);
  backdrop-filter: blur(22px) saturate(1.3);
  -webkit-backdrop-filter: blur(22px) saturate(1.3);
}

.white-knowledge-console .select-options::-webkit-scrollbar { width: 6px; }
.white-knowledge-console .select-options::-webkit-scrollbar-thumb { background: var(--kb-border); border-radius: 10px; }

.white-knowledge-console .select-option {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 7px 10px;
  border-radius: 10px;
  color: var(--kb-text-soft);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.white-knowledge-console .select-option i {
  color: var(--kb-accent);
  font-size: 15px;
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.white-knowledge-console .select-option:hover {
  color: var(--kb-accent-strong);
  background: color-mix(in srgb, var(--kb-accent) 10%, transparent);
  transform: translateX(4px);
}

.white-knowledge-console .select-option.is-selected {
  color: var(--kb-accent-strong);
  background: color-mix(in srgb, var(--kb-accent) 14%, transparent);
  font-weight: 800;
}

/* —— 搜索框 —— */
.white-knowledge-console .search-box {
  display: flex;
  flex: 0 1 280px;
  align-items: center;
  gap: 9px;
  min-width: 180px;
  height: 38px;
  padding: 0 13px;
  border: 1px solid var(--kb-border);
  border-radius: 12px;
  background: var(--kb-input);
  backdrop-filter: blur(8px);
  transition: border-color 0.25s ease, box-shadow 0.25s ease;
}

.white-knowledge-console .search-box:focus-within {
  border-color: var(--kb-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--kb-accent) 18%, transparent);
}

.white-knowledge-console .search-box i { color: var(--kb-text-muted); }
.white-knowledge-console .search-box:focus-within i { color: var(--kb-accent); }

.white-knowledge-console .search-box input {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0;
  border: 0;
  outline: none;
  background: transparent;
  font-size: 12px;
  font-weight: 600;
}

.white-knowledge-console .search-box input:hover { box-shadow: none; }

.white-knowledge-console .search-box button {
  width: 24px;
  min-width: 24px;
  min-height: 24px;
  padding: 0;
  border: 0;
  background: transparent;
}

/* ============ 统计条 ============ */
.white-knowledge-console .graph-stats-strip {
  display: flex;
  flex: 0 0 auto;
  align-items: stretch;
  gap: 10px;
  min-height: 52px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--kb-border-soft);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.35), transparent);
  overflow-x: auto;
}

.white-knowledge-console .graph-stats-strip span {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
  padding: 4px 16px 4px 0;
  border-right: 1px solid var(--kb-border-soft);
  white-space: nowrap;
  transition: transform 0.3s ease;
}

.white-knowledge-console .graph-stats-strip span:hover { transform: translateY(-2px); }
.white-knowledge-console .graph-stats-strip span:last-child { border-right: 0; }

.white-knowledge-console .graph-stats-strip small {
  color: var(--kb-text-muted);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.white-knowledge-console .graph-stats-strip strong {
  font-size: 17px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  background: linear-gradient(120deg, var(--kb-aurora-1), var(--kb-aurora-2) 60%, var(--kb-aurora-3));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

/* ============ 图谱工作区 ============ */
.white-knowledge-console .graph-workspace {
  display: grid;
  flex: 1;
  grid-template-columns: minmax(0, 1fr) 320px;
  min-height: 0;
  overflow: hidden;
}

.white-knowledge-console .graph-canvas {
  position: relative;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  border-right: 1px solid var(--kb-border-soft);
  background-color: var(--kb-canvas);
  background-image:
    radial-gradient(circle at 22% 18%, var(--kb-canvas-glow), transparent 30%),
    radial-gradient(circle at 80% 82%, rgba(56, 189, 248, 0.1), transparent 32%),
    radial-gradient(circle, var(--kb-canvas-line) 1px, transparent 1px);
  background-size: auto, auto, 24px 24px;
}

.white-knowledge-console .sigma-container {
  position: absolute;
  inset: 0;
  cursor: grab;
  z-index: 1;
}

.white-knowledge-console .sigma-container.is-dragging-node { cursor: grabbing; }

/* 叠层动画 canvas */
.white-knowledge-console .graph-fx {
  position: absolute;
  inset: 0;
  z-index: 3;
  pointer-events: none;
}

/* —— 加载态 —— */
.white-knowledge-console .graph-loading {
  position: absolute;
  inset: 0;
  z-index: 15;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  pointer-events: none;
  color: var(--kb-text-soft);
  background: color-mix(in srgb, var(--kb-canvas) 78%, transparent);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.white-knowledge-console .graph-loading strong { font-size: 14px; font-weight: 800; color: var(--kb-text); }
.white-knowledge-console .graph-loading small { color: var(--kb-accent); font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; }

.white-knowledge-console .graph-loading-orb {
  position: relative;
  display: inline-flex;
  gap: 8px;
}

.white-knowledge-console .graph-loading-orb i {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--kb-aurora-1), var(--kb-aurora-3));
  animation: orb-bounce 1.2s ease-in-out infinite;
}

.white-knowledge-console .graph-loading-orb i:nth-child(2) { animation-delay: 0.15s; background: linear-gradient(135deg, var(--kb-aurora-2), var(--kb-aurora-4)); }
.white-knowledge-console .graph-loading-orb i:nth-child(3) { animation-delay: 0.3s; background: linear-gradient(135deg, var(--kb-aurora-4), var(--kb-aurora-5)); }

@keyframes orb-bounce {
  0%, 100% { transform: translateY(0) scale(0.9); opacity: 0.6; }
  50% { transform: translateY(-12px) scale(1.15); opacity: 1; }
}

.white-knowledge-console .graph-empty { background: transparent; backdrop-filter: none; }

.white-knowledge-console .graph-empty-glyph {
  display: grid;
  width: 64px;
  height: 64px;
  place-items: center;
  border-radius: 20px;
  color: var(--kb-accent);
  background: color-mix(in srgb, var(--kb-accent) 10%, rgba(255, 255, 255, 0.5));
  font-size: 28px;
  animation: mark-float 4s ease-in-out infinite;
}

.white-knowledge-console .graph-canvas-hint {
  position: absolute;
  left: 14px;
  bottom: 14px;
  z-index: 10;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid var(--kb-glass-border);
  border-radius: 999px;
  color: var(--kb-text-muted);
  background: rgba(255, 255, 255, 0.7);
  font-size: 10.5px;
  font-weight: 600;
  pointer-events: none;
  backdrop-filter: blur(10px);
  box-shadow: 0 6px 16px rgba(80, 70, 160, 0.1);
}

/* ============ 节点详情面板 ============ */
.white-knowledge-console .node-inspector {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 18px;
  overflow: auto;
  color: var(--kb-text-soft);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.6), rgba(255, 255, 255, 0.28));
  backdrop-filter: blur(16px);
}

.white-knowledge-console .node-inspector-body { display: block; }

.white-knowledge-console .node-inspector-heading {
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr) 30px;
  align-items: start;
  gap: 10px;
}

.white-knowledge-console .node-color {
  width: 12px;
  height: 12px;
  margin-top: 6px;
  border-radius: 50%;
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--kb-accent) 12%, transparent);
}

.white-knowledge-console .node-inspector-heading small {
  display: block;
  margin-bottom: 4px;
  color: var(--kb-accent);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.white-knowledge-console .node-inspector-heading h3 {
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--kb-text);
  font-size: 17px;
  font-weight: 800;
  line-height: 1.35;
}

.white-knowledge-console .node-inspector-heading button {
  width: 30px;
  min-width: 30px;
  min-height: 30px;
  padding: 0;
  border-radius: 10px;
}

.white-knowledge-console .node-inspector > .node-inspector-body > p {
  margin: 14px 0;
  color: var(--kb-text-soft);
  font-size: 12.5px;
  line-height: 1.7;
}

.white-knowledge-console .node-inspector dl {
  display: grid;
  gap: 8px;
  margin: 0 0 8px;
  padding: 14px;
  border: 1px solid var(--kb-border-soft);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.55);
  position: relative;
  overflow: hidden;
}

.white-knowledge-console .node-inspector dl::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--kb-aurora-1), var(--kb-aurora-2), var(--kb-aurora-3));
}

.white-knowledge-console .node-inspector dl div {
  display: grid;
  grid-template-columns: 80px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
}

.white-knowledge-console .node-inspector dt {
  color: var(--kb-text-muted);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.white-knowledge-console .node-inspector dd {
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--kb-accent-strong);
  font-size: 12px;
  font-weight: 700;
}

.white-knowledge-console .relations-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 18px 0 10px;
  font-size: 13px;
}

.white-knowledge-console .relations-heading strong {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--kb-text);
  font-weight: 800;
}

.white-knowledge-console .relations-heading strong::before {
  content: '';
  width: 4px;
  height: 15px;
  border-radius: 3px;
  background: linear-gradient(180deg, var(--kb-aurora-1), var(--kb-aurora-3));
}

.white-knowledge-console .relations-heading span {
  padding: 2px 9px;
  border-radius: 999px;
  color: var(--kb-accent-strong);
  background: color-mix(in srgb, var(--kb-accent) 12%, transparent);
  font-size: 11px;
  font-weight: 700;
}

.white-knowledge-console .relation-list {
  display: grid;
  gap: 8px;
}

.white-knowledge-console .relation-list button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 50px;
  padding: 9px 12px;
  border: 1px solid var(--kb-border-soft);
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.5);
  text-align: left;
  position: relative;
  overflow: hidden;
  transition: transform 0.32s cubic-bezier(0.34, 1.56, 0.64, 1),
              border-color 0.3s ease, box-shadow 0.3s ease, background 0.3s ease;
  animation: relation-in 0.45s cubic-bezier(0.16, 1, 0.3, 1) both;
}

.white-knowledge-console .relation-list button:nth-child(1) { animation-delay: 0.04s; }
.white-knowledge-console .relation-list button:nth-child(2) { animation-delay: 0.08s; }
.white-knowledge-console .relation-list button:nth-child(3) { animation-delay: 0.12s; }
.white-knowledge-console .relation-list button:nth-child(4) { animation-delay: 0.16s; }
.white-knowledge-console .relation-list button:nth-child(5) { animation-delay: 0.2s; }
.white-knowledge-console .relation-list button:nth-child(6) { animation-delay: 0.24s; }
.white-knowledge-console .relation-list button:nth-child(n+7) { animation-delay: 0.28s; }

@keyframes relation-in {
  from { opacity: 0; transform: translateX(14px); }
  to { opacity: 1; transform: translateX(0); }
}

.white-knowledge-console .relation-list button::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent, color-mix(in srgb, var(--kb-accent) 12%, transparent), transparent);
  transform: translateX(-100%);
  transition: transform 0.6s ease;
}

.white-knowledge-console .relation-list button:hover {
  transform: translateX(6px);
  border-color: color-mix(in srgb, var(--kb-accent) 50%, transparent);
  box-shadow: 0 8px 20px color-mix(in srgb, var(--kb-accent) 16%, transparent);
  background: rgba(255, 255, 255, 0.85);
}

.white-knowledge-console .relation-list button:hover::after { transform: translateX(100%); }

.white-knowledge-console .relation-list button span { min-width: 0; }

.white-knowledge-console .relation-list small,
.white-knowledge-console .relation-list strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.white-knowledge-console .relation-list small {
  margin-bottom: 3px;
  color: var(--kb-accent);
  font-size: 10px;
  font-weight: 700;
}

.white-knowledge-console .relation-list strong { color: var(--kb-text); font-size: 12.5px; font-weight: 700; }

.white-knowledge-console .relation-list button i {
  color: var(--kb-accent);
  font-size: 15px;
  transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.white-knowledge-console .relation-list button:hover i { transform: translateX(5px) scale(1.2); }

/* —— 占位 —— */
.white-knowledge-console .inspector-placeholder {
  display: grid;
  flex: 1;
  place-content: center;
  justify-items: center;
  gap: 10px;
  color: var(--kb-text-muted);
  text-align: center;
}

.white-knowledge-console .inspector-placeholder i {
  display: grid;
  width: 52px;
  height: 52px;
  place-items: center;
  border-radius: 50%;
  color: var(--kb-accent);
  background: color-mix(in srgb, var(--kb-accent) 10%, rgba(255, 255, 255, 0.5));
  font-size: 20px;
  animation: placeholder-float 3.5s ease-in-out infinite;
}

@keyframes placeholder-float {
  0%, 100% { transform: translateY(0); box-shadow: 0 0 0 0 color-mix(in srgb, var(--kb-accent) 30%, transparent); }
  50% { transform: translateY(-6px); box-shadow: 0 0 0 10px transparent; }
}

.white-knowledge-console .inspector-placeholder strong { color: var(--kb-text-soft); font-size: 13px; font-weight: 700; }
.white-knowledge-console .inspector-placeholder span { max-width: 220px; font-size: 11px; line-height: 1.6; }

/* ============ 全屏 ============ */
.white-knowledge-console .graph-panel:fullscreen,
.white-knowledge-console .graph-panel.is-fullscreen {
  width: 100vw;
  height: 100vh;
  min-height: 100vh;
  border: 0;
  border-radius: 0;
  background: var(--kb-canvas);
}

/* ============ Vue Transition ============ */
.dropdownFade-enter-active,
.dropdownFade-leave-active {
  transition: opacity 0.28s ease, transform 0.28s ease;
  transform-origin: top center;
}
.dropdownFade-enter-from,
.dropdownFade-leave-to { opacity: 0; transform: scaleY(0.9) translateY(-8px); }

.graphLoadingFade-enter-active,
.graphLoadingFade-leave-active { transition: opacity 0.4s ease; }
.graphLoadingFade-enter-from,
.graphLoadingFade-leave-to { opacity: 0; }

.inspectorSwap-enter-active { transition: opacity 0.4s ease, transform 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.inspectorSwap-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.inspectorSwap-enter-from { opacity: 0; transform: translateX(20px); }
.inspectorSwap-leave-to { opacity: 0; transform: translateX(-12px); }

/* ============ 响应式 ============ */
@media (max-width: 1180px) {
  .white-knowledge-console .knowledge-console-header { grid-template-columns: minmax(200px, 1fr) auto; }
  .white-knowledge-console .service-state { display: none; }
}

@media (max-width: 900px) {
  .white-knowledge-console .graph-workspace {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(420px, 1fr) auto;
  }
  .white-knowledge-console .graph-canvas {
    border-right: 0;
    border-bottom: 1px solid var(--kb-border-soft);
  }
  .white-knowledge-console .node-inspector { min-height: 220px; }
}

@media (max-width: 820px) {
  .lightrag-console.white-knowledge-console { padding: 12px; overflow: auto; }
  .white-knowledge-console .knowledge-console-header { grid-template-columns: 1fr; }
  .white-knowledge-console .console-tabs { width: 100%; }
  .white-knowledge-console .console-tabs button { flex: 1; }
  .white-knowledge-console .console-panel { min-height: 640px; }
  .white-knowledge-console .graph-toolbar { align-items: stretch; flex-direction: column; }
  .white-knowledge-console .custom-select,
  .white-knowledge-console .search-box { flex-basis: auto; width: 100%; min-width: 0; }
  .white-knowledge-console .graph-actions { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .white-knowledge-console .graph-actions select { grid-column: 1 / -1; width: 100%; }
  .white-knowledge-console .graph-actions button { width: 100%; }
}

/* ============ 减弱动画偏好 ============ */
@media (prefers-reduced-motion: reduce) {
  .white-knowledge-console,
  .white-knowledge-console *,
  .white-knowledge-console *::before,
  .white-knowledge-console *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.08s !important;
  }
}
</style>
