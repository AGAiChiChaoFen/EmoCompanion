import { readonly, ref } from 'vue';
import { loadPersistentJson, savePersistentJson } from '../utils/persistentState';

export const personaUserName = String(import.meta.env.VITE_PERSONA_USER_NAME || '王秀兰').trim();
export const analysisStateKey = `hearttalk.multimodal.real.v2:${encodeURIComponent(personaUserName)}`;
const saved = loadPersistentJson(analysisStateKey, null);
const validResult = (result) => result && ['model', 'emollm'].includes(result.reportSource)
  && typeof result.description === 'string' && Array.isArray(result.suggestions);
const result = ref(saved?.userName === personaUserName && validResult(saved?.analysisResult)
  ? saved.analysisResult : null);

// 页面共享同一次真实接口结果；旧版演示缓存不参与恢复。
export const useAnalysisResult = () => ({
  analysisResult: readonly(result),
  setAnalysisResult(value) {
    if (value !== null && !validResult(value)) throw new Error('分析接口未返回有效模型报告');
    result.value = value;
    savePersistentJson(analysisStateKey, { userName: personaUserName, analysisResult: value });
  },
});
