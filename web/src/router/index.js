import { createRouter, createWebHistory } from 'vue-router';
import DemoLayout from '../views/DemoLayout.vue';
import MultimodalAnalysis from '../views/MultimodalAnalysis.vue';
import AssessmentIntervention from '../views/AssessmentIntervention.vue';
import AvatarCustomization from '../views/AvatarCustomization.vue';
import IntegratedSystem from '../views/IntegratedSystem.vue';
import KnowledgeGraph from '../views/KnowledgeGraph.vue';
import PersonaMemory from '../views/PersonaMemory.vue';

const routes = [
  {
    path: '/chat',
    redirect: {
      name: 'integrated-system',
      query: {
        mode: 'chat'
      }
    }
  },
  {
    path: '/realtime',
    redirect: {
      name: 'integrated-system'
    }
  },
  {
    path: '/',
    component: DemoLayout,
    children: [
      {
        path: '',
        redirect: { name: 'persona-memory' }
      },
      {
        // 功能1：多模态数据采集及解析
        path: '/multimodal-analysis',
        name: 'multimodal-analysis',
        component: MultimodalAnalysis,
        meta: {
          title: '多模态数据采集及解析',
          icon: 'bi-activity',
          description: '视频、音频、文本并行采集与情绪解析'
        }
      },
      {
        path: '/assessment-intervention',
        name: 'assessment-intervention',
        component: AssessmentIntervention,
        meta: {
          title: '心理评估与干预',
          icon: 'bi-clipboard2-pulse',
          description: '知识图谱支持的风险评估与分级干预'
        }
      },
      {
        path: '/knowledge-graph',
        name: 'knowledge-graph',
        component: KnowledgeGraph,
        meta: {
          title: '心理知识库',
          icon: 'bi-journal-medical',
          description: '心理资料构建、图谱可视化与干预建议'
        }
      },
      {
        // 功能2：数字人形象定制
        path: '/avatar-customization',
        name: 'avatar-customization',
        component: AvatarCustomization,
        meta: {
          title: '数字人形象定制',
          icon: 'bi-person-video3',
          description: '支持形象定制、音色克隆的数字人生成'
        }
      },
      {
        // 功能4：数字人伴侣
        path: '/integrated-system',
        name: 'integrated-system',
        component: IntegratedSystem,
        meta: {
          title: '数字人伴侣',
          icon: 'bi-grid-3x3-gap',
          description: '唤醒数字人并开展实时陪护互动'
        }
      },
      {
        // 长期情感档案：用户画像、长期记忆与偏好演化
        path: '/persona-memory',
        name: 'persona-memory',
        component: PersonaMemory,
        meta: {
          title: '长期情感档案',
          icon: 'bi-diagram-3-fill',
          description: '用户画像、长期记忆与陪伴偏好变化'
        }
      }
    ]
  }
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
