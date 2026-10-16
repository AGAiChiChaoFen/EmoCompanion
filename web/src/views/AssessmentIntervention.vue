<template>
  <div class="assessment-workbench">
    <div class="workbench-grid">
      <section class="workbench-card documents-card">
        <header class="card-head">
          <div class="title-lockup">
            <span class="title-icon"><i class="bi bi-folder2-open"></i></span>
            <div>
              <small>KNOWLEDGE SOURCES</small>
              <h3>知识文档管理</h3>
            </div>
          </div>
          <div class="card-actions">
            <span class="service-pill" :class="{ offline: knowledgeError }">
              <i></i>{{ knowledgeError ? '知识服务异常' : loadingDocuments ? '正在连接' : pipeline ? '知识库在线' : '待连接' }}
            </span>
            <button type="button" title="刷新文档" :disabled="loadingDocuments" @click="loadDocuments">
              <i class="bi bi-arrow-clockwise" :class="{ spinning: loadingDocuments }"></i>
            </button>
            <label class="icon-upload" title="上传知识文档">
              <input type="file" multiple @change="uploadDocuments" />
              <i class="bi bi-cloud-arrow-up"></i>
            </label>
          </div>
        </header>

        <div class="source-summary">
          <div><strong>{{ totalDocuments }}</strong><span>知识文档</span></div>
          <div><strong>{{ processedDocuments }}</strong><span>已完成索引</span></div>
          <p><i class="bi bi-database-check"></i>{{ pipelineText }}</p>
        </div>

        <div class="document-list">
          <div v-if="loadingDocuments && !documents.length" class="panel-state"><i class="bi bi-arrow-repeat spinning"></i>正在读取知识文档</div>
          <div v-else-if="!documents.length" class="panel-state"><i class="bi bi-file-earmark-plus"></i>暂无可展示文档</div>
          <article v-for="document in visibleDocuments" v-else :key="document.id || documentName(document)" class="document-row">
            <span class="file-glyph"><i class="bi bi-file-earmark-medical"></i></span>
            <div>
              <strong :title="documentName(document)">{{ documentName(document) }}</strong>
              <small>{{ documentMeta(document) }}</small>
            </div>
            <span class="status-tag" :class="`status-${normalizeStatus(document.status)}`">{{ statusText(document.status) }}</span>
          </article>
        </div>
        <p v-if="knowledgeError" class="upload-notice" role="status">{{ knowledgeError }}</p>
        <p v-if="uploadNotice" class="upload-notice"><i class="bi bi-info-circle"></i>{{ uploadNotice }}</p>
      </section>

      <section class="workbench-card assessment-card" :class="`risk-${riskAssessment.severity}`">
        <header class="card-head">
          <div class="title-lockup">
            <span class="title-icon"><i class="bi bi-clipboard2-pulse"></i></span>
            <div>
              <small>ASSESSMENT RESULT</small>
              <h3>心理状态评估结果</h3>
            </div>
          </div>
          <span class="result-source"><i class="bi bi-link-45deg"></i>{{ hasAnalysis ? '多模态分析已同步' : '等待分析输入' }}</span>
        </header>

        <div class="assessment-body">
          <div class="risk-orbit">
            <div class="risk-ring"><strong>{{ riskAssessment.level }}</strong><span>当前风险等级</span></div>
            <div class="risk-scale" aria-label="三级风险刻度">
              <span v-for="step in riskSteps" :key="step.key" :class="{ active: step.key === riskAssessment.severity }">{{ step.label }}</span>
            </div>
          </div>

          <div class="assessment-facts">
            <div class="fact-row">
              <span>心理状态</span>
              <strong>{{ psychologicalStatus }}</strong>
            </div>
            <div class="fact-row emotion-fact">
              <span>关键情绪</span>
              <div>
                <em v-for="item in emotionSignals" :key="item.label"><small>{{ item.label }}</small>{{ item.value }}</em>
              </div>
            </div>
            <div class="fact-row judgment-row">
              <span>综合判断</span>
              <p>{{ overallJudgment }}</p>
            </div>
          </div>
        </div>

        <div class="evidence-strip">
          <span><i class="bi bi-signpost-split"></i>{{ riskAssessment.route }}</span>
          <span v-for="basis in riskAssessment.basis.slice(0, 2)" :key="basis"><i class="bi bi-check2-circle"></i>{{ basis }}</span>
        </div>
      </section>

      <section class="workbench-card graph-card">
        <header class="card-head">
          <div class="title-lockup">
            <span class="title-icon"><i class="bi bi-diagram-3"></i></span>
            <div>
              <small>KNOWLEDGE GRAPH</small>
              <h3>心理知识图谱</h3>
            </div>
          </div>
          <div class="graph-controls">
            <select v-model="selectedLabel" :disabled="loadingGraph || !graphLabels.length" @change="loadGraph">
              <option v-if="!graphLabels.length" value="">暂无实体</option>
              <option v-for="label in graphLabels" :key="label" :value="label">{{ label }}</option>
            </select>
            <button type="button" title="刷新图谱" :disabled="loadingGraph || !selectedLabel" @click="loadGraph">
              <i class="bi bi-arrow-clockwise" :class="{ spinning: loadingGraph }"></i>
            </button>
          </div>
        </header>

        <div class="graph-stage">
          <div ref="graphContainer" class="sigma-container" role="img" aria-label="心理健康知识关系网络"></div>
          <div v-if="loadingGraph || preparingGraph" class="graph-empty graph-loading"><i class="bi bi-arrow-repeat spinning"></i><strong>{{ loadingGraph ? '正在加载图谱数据' : '正在计算图谱布局' }}</strong></div>
          <div v-else-if="!graphNodes.length" class="graph-empty"><i class="bi bi-diagram-2"></i><strong>请选择知识实体查看关系网络</strong></div>
          <div class="graph-legend"><span><i></i>{{ graphNodes.length }} 个实体</span><span><i></i>{{ graphEdges.length }} 条关系</span></div>
          <aside v-if="selectedNode" class="node-popover">
            <button type="button" @click="selectedNode = null"><i class="bi bi-x"></i></button>
            <small>{{ selectedNode.type }}</small>
            <strong>{{ selectedNode.label }}</strong>
            <p>{{ selectedNode.description }}</p>
          </aside>
        </div>
      </section>

      <section class="workbench-card intervention-card">
        <header class="card-head">
          <div class="title-lockup">
            <span class="title-icon"><i class="bi bi-life-preserver"></i></span>
            <div>
              <small>INTERVENTION PLAN</small>
              <h3>分级干预建议</h3>
            </div>
          </div>
          <span class="plan-badge">{{ riskAssessment.route }}</span>
        </header>

        <div class="intervention-list">
          <p v-if="!interventionPlan.length" class="panel-state">完成多模态分析后显示模型建议</p>
          <article v-for="(item, index) in interventionPlan" :key="item.title" :style="{ '--delay': `${index * 70}ms` }">
            <span class="plan-index">0{{ index + 1 }}</span>
            <span class="plan-icon"><i class="bi" :class="item.icon"></i></span>
            <div><small>{{ item.category }}</small><strong>{{ item.title }}</strong><p>{{ item.content }}</p></div>
            <i class="bi bi-arrow-up-right"></i>
          </article>
        </div>

        <footer class="safety-note">
          <i class="bi bi-shield-check"></i>
          <span>系统提供陪护辅助建议，不替代专业诊断；出现明确高危信号时优先联系家属、专业机构或紧急服务。</span>
        </footer>
      </section>
    </div>
  </div>
</template>

<script setup>
import Graph from 'graphology';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import Sigma from 'sigma';
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { buildApiUrl } from '../utils/api';
import '../assets/assessment-intervention-theme.css';
import { useAnalysisResult } from '../composables/useAnalysisResult';

const { analysisResult } = useAnalysisResult();
const documents = ref([]);
const statusCounts = ref({});
const pagination = ref({ total_count: 0 });
const pipeline = ref(null);
const graphLabels = ref([]);
const selectedLabel = ref('');
const graphNodes = ref([]);
const graphEdges = ref([]);
const selectedNode = ref(null);
const graphContainer = ref(null);
const loadingDocuments = ref(false);
const loadingGraph = ref(false);
const preparingGraph = ref(false);
const resourceErrors = ref({ documents: '', pipeline: '', labels: '', graph: '' });
const knowledgeError = computed(() => [...new Set(Object.values(resourceErrors.value).filter(Boolean))].join('；'));
const uploadNotice = ref('');
let sigmaInstance = null;

const apiJson = async (url, options = {}) => {
  const requestUrl = import.meta.env.DEV ? url : buildApiUrl(url);
  const response = await fetch(requestUrl, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.code !== 0) throw new Error(payload.msg || `HTTP ${response.status}`);
  return payload.data;
};

const loadDocuments = async () => {
  loadingDocuments.value = true;
  try {
    const data = await apiJson('/api/lightrag/documents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page: 1, page_size: 10, status_filter: '', sort_field: 'updated_at', sort_direction: 'desc' }),
    });
    documents.value = data?.documents || [];
    statusCounts.value = data?.status_counts || {};
    pagination.value = data?.pagination || pagination.value;
    resourceErrors.value.documents = '';
  } catch (error) {
    resourceErrors.value.documents = error.message;
    documents.value = [];
    statusCounts.value = {};
    pagination.value = { total_count: 0 };
  } finally {
    loadingDocuments.value = false;
  }
};

const loadPipeline = async () => {
  try { pipeline.value = await apiJson('/api/lightrag/pipeline_status'); resourceErrors.value.pipeline = ''; } catch (error) { pipeline.value = null; resourceErrors.value.pipeline = error.message; }
};

const uploadDocuments = async (event) => {
  const files = Array.from(event.target.files || []);
  event.target.value = '';
  if (!files.length) return;
  uploadNotice.value = `正在上传 ${files.length} 份文档…`;
  try {
    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      await apiJson('/api/lightrag/upload', { method: 'POST', body: formData });
    }
    uploadNotice.value = '上传完成，知识索引正在后台更新';
    await Promise.all([loadDocuments(), loadPipeline()]);
  } catch (error) {
    resourceErrors.value.documents = error.message;
    uploadNotice.value = '上传失败，请检查知识服务连接';
  }
};

const firstText = (...values) => {
  for (const value of values) {
    if (Array.isArray(value) && value.length) return String(value[0] || '').trim();
    if (value !== undefined && value !== null && String(value).trim()) return String(value).trim();
  }
  return '';
};
const nodeColors = ['#4977ff', '#7858d7', '#05a7b5', '#f08b45', '#bd5fe8', '#1ba772'];

const normalizeGraph = (data) => {
  const rawNodes = data?.nodes || data?.entities || [];
  const rawEdges = data?.edges || data?.relations || [];
  const degrees = new Map();
  rawEdges.forEach((edge) => {
    const source = String(edge.source || edge.src || edge.src_id || edge.from || '');
    const target = String(edge.target || edge.tgt || edge.tgt_id || edge.to || '');
    if (source) degrees.set(source, (degrees.get(source) || 0) + 1);
    if (target) degrees.set(target, (degrees.get(target) || 0) + 1);
  });
  graphNodes.value = rawNodes.slice(0, 34).map((node, index) => {
    const properties = node.properties || node.entity_data || {};
    const id = String(node.id || node.entity_name || node.label || node.name || `node-${index}`).trim();
    const type = firstText(properties.entity_type, node.entity_type, node.type, '知识实体');
    const label = firstText(node.labels, node.label, node.entity_name, node.name, properties.entity_name, id);
    return { id, label, type, description: firstText(properties.description, node.description, 'LightRAG 知识图谱实体。'), degree: degrees.get(id) || Number(node.degree || node.size || 1), color: nodeColors[index % nodeColors.length] };
  });
  const validIds = new Set(graphNodes.value.map((node) => node.id));
  graphEdges.value = rawEdges.map((edge, index) => {
    const properties = edge.properties || {};
    const source = String(edge.source || edge.src || edge.src_id || edge.from || '').trim();
    const target = String(edge.target || edge.tgt || edge.tgt_id || edge.to || '').trim();
    return { id: String(edge.id || `${source}-${target}-${index}`), source, target, label: firstText(properties.keywords, edge.type, edge.label), weight: Number(properties.weight || edge.weight || 1) };
  }).filter((edge) => validIds.has(edge.source) && validIds.has(edge.target)).slice(0, 900);
  selectedNode.value = null;
};

const destroyGraph = () => {
  sigmaInstance?.kill();
  sigmaInstance = null;
};

const renderGraph = async () => {
  preparingGraph.value = true;
  try {
    await nextTick();
    await new Promise((resolve) => window.requestAnimationFrame(resolve));
    destroyGraph();
    if (!graphContainer.value || !graphNodes.value.length) return;

    const graph = new Graph({ type: 'undirected', multi: false });
    const count = Math.max(1, graphNodes.value.length);
    graphNodes.value.forEach((node, index) => {
      const angle = index * 2.399963;
      const radius = Math.sqrt((index + 1) / count);
      graph.addNode(node.id, {
        label: node.label,
        color: node.color,
        size: Math.max(5, Math.min(18, 5 + Math.sqrt(node.degree || 1) * 2.2)),
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
      });
    });
    graphEdges.value.forEach((edge) => {
      if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target) || graph.hasEdge(edge.source, edge.target)) return;
      graph.addEdgeWithKey(edge.id, edge.source, edge.target, {
        label: edge.label,
        size: Math.max(.35, Math.min(2.2, Math.sqrt(edge.weight || 1) * .7)),
        color: 'rgba(103, 119, 205, .34)',
      });
    });
    if (graph.order > 1) {
      forceAtlas2.assign(graph, {
        iterations: graph.order > 250 ? 32 : 54,
        settings: { ...forceAtlas2.inferSettings(graph), gravity: .08, scalingRatio: 8, slowDown: 10 },
      });
    }
    sigmaInstance = new Sigma(graph, graphContainer.value, {
      allowInvalidContainer: true,
      autoCenter: true,
      autoRescale: true,
      hideEdgesOnMove: true,
      hideLabelsOnMove: true,
      labelColor: { color: '#536078' },
      labelDensity: .08,
      labelGridCellSize: 50,
      labelRenderedSizeThreshold: 7,
      labelSize: 11,
      labelWeight: '700',
      renderLabels: true,
      minCameraRatio: .12,
      maxCameraRatio: 5,
    });
    sigmaInstance.on('clickNode', ({ node }) => {
      selectedNode.value = graphNodes.value.find((item) => item.id === node) || null;
    });
    sigmaInstance.on('clickStage', () => { selectedNode.value = null; });
  } finally {
    preparingGraph.value = false;
  }
};

const loadGraphLabels = async () => {
  try {
    const data = await apiJson('/api/lightrag/graph_labels?limit=40');
    graphLabels.value = data?.labels || [];
    resourceErrors.value.labels = '';
    if (!graphLabels.value.includes(selectedLabel.value)) selectedLabel.value = graphLabels.value[0] || '';
  } catch (error) {
    resourceErrors.value.labels = error.message;
    graphLabels.value = [];
    selectedLabel.value = '';
    normalizeGraph({});
    destroyGraph();
  }
};

const loadGraph = async () => {
  if (!selectedLabel.value) {
    normalizeGraph({});
    destroyGraph();
    return;
  }
  loadingGraph.value = true;
  try {
    const data = await apiJson(`/api/lightrag/graph?label=${encodeURIComponent(selectedLabel.value)}&max_depth=2&max_nodes=60`);
    normalizeGraph(data || {});
    resourceErrors.value.graph = '';
    loadingGraph.value = false;
    await renderGraph();
  } catch (error) {
    resourceErrors.value.graph = error.message;
    normalizeGraph({});
    loadingGraph.value = false;
    await renderGraph();
  } finally { loadingGraph.value = false; }
};

const visibleDocuments = computed(() => documents.value.slice(0, 4));
const totalDocuments = computed(() => Number(statusCounts.value.all || pagination.value.total_count || documents.value.length));
const processedDocuments = computed(() => Number(statusCounts.value.processed || statusCounts.value.PROCESSED || documents.value.filter((item) => normalizeStatus(item.status) === 'processed').length));
const pipelineText = computed(() => !pipeline.value ? '尚未取得索引状态' : pipeline.value.busy ? '知识抽取任务运行中' : '知识服务空闲');
const hasAnalysis = computed(() => Boolean(analysisResult.value));

const riskAssessment = computed(() => {
  const backend = analysisResult.value?.riskAssessment;
  if (backend && ['low', 'attention', 'high'].includes(backend.severity)) {
    return { severity: backend.severity, level: String(backend.level || '待评估'), route: String(backend.route || '待确定'), description: String(backend.description || ''), basis: Array.isArray(backend.basis) ? backend.basis.filter(Boolean) : [] };
  }
  return { severity: 'pending', level: '待评估', route: '等待有效风险评估', description: '请先完成多模态分析。', basis: [] };
});

const riskSteps = [{ key: 'low', label: '低风险' }, { key: 'attention', label: '中风险' }, { key: 'high', label: '高风险' }];
const cleanEmotion = (value) => String(value || '未检测').trim() || '未检测';
const emotionSignals = computed(() => [{ label: '面部', value: cleanEmotion(analysisResult.value?.faceEmotion) }, { label: '语音', value: cleanEmotion(analysisResult.value?.audioEmotion) }, { label: '文本', value: cleanEmotion(analysisResult.value?.textEmotion) }]);
const psychologicalStatus = computed(() => firstText(analysisResult.value?.overallStatusText, analysisResult.value?.dominantEmotion, analysisResult.value?.textEmotion, '待完成分析'));
const overallJudgment = computed(() => firstText(analysisResult.value?.description, riskAssessment.value.description, '请先完成多模态数据采集与解析。'));

const interventionPlan = computed(() => {
  const suggestions = Array.isArray(analysisResult.value?.suggestions) ? analysisResult.value.suggestions.filter(Boolean) : [];
  return suggestions.map((content, index) => ({ category: '模型分析建议', title: `建议 ${index + 1}`, content: String(content), icon: 'bi-chat-heart' }));
});

const normalizeStatus = (status) => String(status || '').toLowerCase();
const statusText = (status) => ({ processed: '已完成', processing: '处理中', pending: '待处理', failed: '失败' }[normalizeStatus(status)] || status || '未知');
const documentName = (document) => {
  const summary = String(document?.content_summary || '').replace(/\r\n/g, '\n');
  const ocrTitle = summary.match(/#\s*OCR text for\s+(.+?)(?:\n|$)/i)?.[1]?.trim();
  const raw = String(ocrTitle || document?.file_name || document?.filename || document?.name || document?.file_path || document?.id || '知识文档').trim();
  const name = raw.split(/[\\/]/).filter(Boolean).pop() || raw;
  return name
    .replace(/\s*\(z-library[^)]*\)/i, '')
    .replace(/\s*-\s*=+\s*Page\s+\d+.*$/i, '')
    .replace(/\s+/g, ' ')
    .trim();
};
const documentMeta = (document) => `${Number(document?.chunks_count || 0)} 个知识片段 · ${Number(document?.content_length || 0).toLocaleString()} 字符`;
onMounted(async () => {
  await Promise.all([loadDocuments(), loadPipeline(), loadGraphLabels()]);
  await loadGraph();
});

onBeforeUnmount(destroyGraph);
</script>

<style scoped>
.assessment-workbench {
  --blue: #527dff;
  --violet: #855ce6;
  --orange: #f28a45;
  --ink: var(--theme-text-primary);
  height: 100%;
  box-sizing: border-box;
  padding: 16px 18px 18px;
  overflow: auto;
  color: var(--ink);
  background:
    radial-gradient(circle at 20% 20%, rgba(82, 125, 255, .12), transparent 30%),
    radial-gradient(circle at 86% 82%, rgba(242, 138, 69, .1), transparent 28%),
    var(--theme-bg-base);
}
.workbench-grid { height: 100%; min-height: 0; display: grid; grid-template-columns: minmax(0, 1.02fr) minmax(0, .98fr); grid-template-rows: minmax(0, .9fr) minmax(0, 1.1fr); gap: 14px; }
.workbench-card { position: relative; min-width: 0; overflow: hidden; border: 1px solid var(--theme-border); border-radius: 20px; background: color-mix(in srgb, var(--theme-bg-card) 94%, transparent); box-shadow: 0 16px 42px rgba(15, 23, 42, .09); }
.workbench-card::before { content: ''; position: absolute; inset: 0 0 auto; height: 3px; background: linear-gradient(90deg, var(--blue), var(--violet), transparent 85%); }
.intervention-card::before { background: linear-gradient(90deg, var(--orange), #f1b052, transparent 85%); }
.card-head { height: 68px; padding: 0 17px; display: flex; align-items: center; justify-content: space-between; gap: 14px; border-bottom: 1px solid var(--theme-border); }
.title-lockup { min-width: 0; display: flex; align-items: center; gap: 11px; }
.title-icon { width: 38px; height: 38px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 12px; color: var(--blue); background: rgba(82, 125, 255, .12); font-size: 1.08rem; }
.intervention-card .title-icon { color: var(--orange); background: rgba(242, 138, 69, .13); }
.title-lockup small { display: block; color: var(--theme-text-muted); font-size: .68rem; font-weight: 900; letter-spacing: .14em; }
.title-lockup h3 { margin: 3px 0 0; font-family: "Microsoft YaHei UI", "Noto Sans SC", sans-serif; font-size: 1.06rem; letter-spacing: .02em; }
.card-actions, .graph-controls { display: flex; align-items: center; gap: 7px; }
.card-actions button, .icon-upload, .graph-controls button { width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid var(--theme-border); border-radius: 10px; background: var(--theme-bg-input); color: var(--theme-text-secondary); cursor: pointer; }
.icon-upload input { display: none; }
.service-pill, .result-source, .plan-badge { display: inline-flex; align-items: center; gap: 6px; height: 29px; padding: 0 10px; border-radius: 999px; background: rgba(35, 177, 117, .1); color: #25a978; font-size: .72rem; font-weight: 800; white-space: nowrap; }
.service-pill i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 4px rgba(35, 177, 117, .12); }
.service-pill.offline { color: #e06666; background: rgba(224, 102, 102, .1); }
.source-summary { margin: 10px 16px 7px; display: grid; grid-template-columns: 90px 110px 1fr; gap: 8px; }
.source-summary > div, .source-summary > p { margin: 0; min-width: 0; height: 46px; padding: 6px 11px; display: flex; flex-direction: column; justify-content: center; border: 1px solid var(--theme-border); border-radius: 12px; background: var(--theme-bg-input); }
.source-summary strong { color: var(--blue); font-size: 1.25rem; line-height: 1; }
.source-summary span { margin-top: 5px; color: var(--theme-text-muted); font-size: .7rem; }
.source-summary > p { flex-direction: row; align-items: center; gap: 8px; color: var(--theme-text-secondary); font-size: .74rem; }
.source-summary > p i { color: #25a978; font-size: 1rem; }
.document-list { padding: 0 16px 7px; display: grid; gap: 4px; }
.document-row { min-width: 0; height: 38px; box-sizing: border-box; overflow: hidden; padding: 3px 9px; display: grid; grid-template-columns: 30px minmax(0, 1fr) auto; align-items: center; gap: 8px; border: 1px solid transparent; border-radius: 10px; background: color-mix(in srgb, var(--theme-bg-input) 75%, transparent); line-height: 1.2; transition: .2s ease; }
.document-row:hover { transform: translateX(3px); border-color: rgba(82, 125, 255, .28); }
.file-glyph { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 9px; color: var(--violet); background: rgba(133, 92, 230, .11); }
.document-row div { min-width: 0; }
.document-row strong, .document-row small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.document-row strong { font-size: .79rem; }
.document-row small { margin-top: 3px; color: var(--theme-text-muted); font-size: .66rem; }
.status-tag { padding: 4px 7px; border-radius: 999px; color: #25a978; background: rgba(35, 177, 117, .1); font-size: .65rem; font-weight: 900; }
.status-processing, .status-pending { color: #d8842f; background: rgba(242, 138, 69, .12); }
.status-failed { color: #dc5f67; background: rgba(220, 95, 103, .12); }
.panel-state { height: 98px; display: grid; place-items: center; align-content: center; gap: 8px; color: var(--theme-text-muted); font-size: .8rem; }
.panel-state i { font-size: 1.4rem; }
.upload-notice { position: absolute; right: 15px; bottom: 8px; margin: 0; color: var(--theme-text-muted); font-size: .68rem; }
.upload-notice i { margin-right: 5px; color: var(--blue); }
.assessment-card { --risk: #25a978; display: flex; flex-direction: column; }
.assessment-card .card-head { flex-shrink: 0; }
.assessment-card.risk-attention { --risk: #ee933c; }
.assessment-card.risk-high { --risk: #e2535e; }
.result-source { color: var(--blue); background: rgba(82, 125, 255, .1); }
.assessment-body { flex: 1; min-height: 0; box-sizing: border-box; padding: 11px 16px 42px; display: grid; grid-template-columns: 132px minmax(0, 1fr); gap: 13px; overflow: hidden; }
.risk-orbit { display: flex; flex-direction: column; align-items: center; justify-content: center; }
.risk-ring { width: 108px; height: 108px; display: grid; place-items: center; align-content: center; border-radius: 50%; border: 1px solid color-mix(in srgb, var(--risk) 40%, transparent); background: radial-gradient(circle, color-mix(in srgb, var(--risk) 15%, transparent), transparent 68%); box-shadow: inset 0 0 0 7px color-mix(in srgb, var(--risk) 5%, transparent), 0 0 26px color-mix(in srgb, var(--risk) 14%, transparent); }
.risk-ring strong { color: var(--risk); font-size: 1.5rem; }
.risk-ring span { margin-top: 5px; color: var(--theme-text-muted); font-size: .74rem; }
.risk-scale { width: 126px; margin-top: 9px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 3px; }
.risk-scale span { padding-top: 7px; border-top: 3px solid var(--theme-border); color: var(--theme-text-muted); font-size: .68rem; text-align: center; }
.risk-scale span.active { color: var(--risk); border-color: var(--risk); font-weight: 900; }
.assessment-facts { display: grid; align-content: center; gap: 8px; }
.fact-row { min-width: 0; padding: 8px 13px; border-left: 3px solid rgba(82, 125, 255, .45); border-radius: 0 10px 10px 0; background: var(--theme-bg-input); }
.fact-row > span { display: block; color: var(--theme-text-muted); font-size: .75rem; font-weight: 800; letter-spacing: .04em; }
.fact-row > strong { display: block; margin-top: 5px; color: var(--ink); font-size: 1rem; }
.emotion-fact > div { margin-top: 5px; display: flex; gap: 6px; flex-wrap: wrap; }
.emotion-fact em { padding: 4px 9px; border-radius: 7px; background: rgba(82, 125, 255, .1); color: var(--blue); font-size: .78rem; font-style: normal; font-weight: 800; }
.emotion-fact em small { margin-right: 5px; opacity: .62; }
.judgment-row p { margin: 4px 0 0; display: -webkit-box; overflow: hidden; color: var(--theme-text-secondary); font-size: .82rem; line-height: 1.55; -webkit-line-clamp: 3; -webkit-box-orient: vertical; }
.evidence-strip { position: absolute; inset: auto 16px 10px; display: flex; gap: 7px; overflow: hidden; }
.evidence-strip span { min-width: 0; padding: 5px 9px; overflow: hidden; border: 1px solid var(--theme-border); border-radius: 8px; color: var(--theme-text-muted); background: var(--theme-bg-card); font-size: .7rem; text-overflow: ellipsis; white-space: nowrap; }
.evidence-strip i { margin-right: 5px; color: var(--risk); }
.graph-controls select { max-width: 155px; height: 34px; border: 1px solid var(--theme-border); border-radius: 10px; padding: 0 9px; background: var(--theme-bg-input); color: var(--theme-text-secondary); font-size: .72rem; }
.graph-stage { position: relative; height: calc(100% - 68px); min-height: 290px; overflow: hidden; background: radial-gradient(circle at 50% 45%, rgba(82, 125, 255, .11), transparent 35%), linear-gradient(rgba(82, 125, 255, .035) 1px, transparent 1px), linear-gradient(90deg, rgba(82, 125, 255, .035) 1px, transparent 1px); background-size: auto, 28px 28px, 28px 28px; }
.sigma-container { position: absolute; inset: 0; }
.graph-empty { height: 100%; display: grid; place-items: center; align-content: center; gap: 10px; color: var(--theme-text-muted); }
.graph-loading { position: absolute; inset: 0; z-index: 3; background: color-mix(in srgb, var(--theme-bg-card) 82%, transparent); backdrop-filter: blur(3px); }
.graph-empty i { font-size: 2rem; color: var(--blue); }
.graph-empty strong { font-size: .82rem; }
.graph-legend { position: absolute; left: 12px; bottom: 10px; display: flex; gap: 8px; }
.graph-legend span { padding: 5px 8px; border: 1px solid var(--theme-border); border-radius: 999px; background: color-mix(in srgb, var(--theme-bg-card) 88%, transparent); color: var(--theme-text-muted); font-size: .64rem; backdrop-filter: blur(8px); }
.graph-legend i { display: inline-block; width: 6px; height: 6px; margin-right: 5px; border-radius: 50%; background: var(--blue); }
.node-popover { position: absolute; top: 12px; right: 12px; width: min(230px, 44%); padding: 13px; border: 1px solid rgba(82, 125, 255, .25); border-radius: 14px; background: color-mix(in srgb, var(--theme-bg-card) 92%, transparent); box-shadow: 0 14px 34px rgba(15,23,42,.16); backdrop-filter: blur(14px); }
.node-popover button { position: absolute; top: 7px; right: 7px; border: 0; background: transparent; color: var(--theme-text-muted); cursor: pointer; }
.node-popover small, .node-popover strong { display: block; }
.node-popover small { color: var(--blue); font-size: .62rem; font-weight: 900; }
.node-popover strong { margin-top: 4px; font-size: .82rem; }
.node-popover p { margin: 7px 0 0; max-height: 70px; overflow: hidden; color: var(--theme-text-muted); font-size: .68rem; line-height: 1.55; }
.plan-badge { color: var(--orange); background: rgba(242, 138, 69, .11); }
.intervention-card { display: flex; flex-direction: column; }
.intervention-card .card-head { flex-shrink: 0; }
.intervention-list { flex: 1; min-height: 0; padding: 9px 16px 6px; display: grid; align-content: start; gap: 7px; overflow-y: auto; }
.intervention-list article { min-width: 0; min-height: 64px; height: auto; box-sizing: border-box; overflow: visible; padding: 10px 13px; display: grid; grid-template-columns: 22px 36px minmax(0, 1fr) 16px; align-items: start; gap: 9px; border: 1px solid var(--theme-border); border-radius: 12px; background: color-mix(in srgb, var(--theme-bg-input) 78%, transparent); line-height: 1.35; animation: plan-in .45s ease both; animation-delay: var(--delay); }
.plan-index { align-self: start; padding-top: 3px; color: rgba(242, 138, 69, .62); font-size: .68rem; font-weight: 900; }
.plan-icon { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 10px; color: var(--orange); background: rgba(242, 138, 69, .12); }
.intervention-list article > div { min-width: 0; }
.intervention-list small, .intervention-list strong { display: block; }
.intervention-list small { color: var(--orange); font-size: .7rem; font-weight: 900; letter-spacing: .06em; }
.intervention-list strong { margin-top: 3px; font-size: .92rem; }
.intervention-list p { margin: 5px 0 0; display: -webkit-box; overflow: hidden; color: var(--theme-text-secondary); font-size: .79rem; line-height: 1.55; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.intervention-list article > .bi-arrow-up-right { padding-top: 3px; color: var(--theme-text-muted); }
.safety-note { margin: 0 16px 8px; padding: 8px 11px; display: flex; gap: 8px; align-items: flex-start; border-radius: 10px; color: #c06e2c; background: rgba(242, 138, 69, .09); font-size: .73rem; line-height: 1.45; }
.safety-note i { flex: 0 0 auto; font-size: 1rem; margin-top: 1px; }
.spinning { animation: spin .85s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes plan-in { from { opacity: 0; transform: translateY(7px); } }

@media (max-width: 1180px) {
  .workbench-grid { grid-template-columns: 1fr; grid-template-rows: repeat(4, minmax(340px, auto)); }
  .assessment-workbench { overflow: auto; }
}
@media (max-width: 720px) {
  .assessment-workbench { padding: 10px; }
  .workbench-grid { gap: 10px; }
  .service-pill, .result-source { display: none; }
  .source-summary { grid-template-columns: repeat(2, 1fr); }
  .source-summary > p { grid-column: 1 / -1; }
  .assessment-body { grid-template-columns: 1fr; }
  .risk-orbit { display: grid; grid-template-columns: 126px 142px; gap: 12px; }
  .risk-scale { margin: 0; }
}
</style>
