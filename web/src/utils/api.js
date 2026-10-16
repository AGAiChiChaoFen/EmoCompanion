import {
  DEFAULT_API_BASE,
  DEFAULT_PERSONA_API_BASE,
} from '../config/apiEndpoints';

const ABSOLUTE_URL_PATTERN = /^(?:https?:)?\/\//i;

const normalizeBaseUrl = (value) => String(value || '').trim().replace(/\/+$/, '');

const API_BASES = Object.freeze({
  default: normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE),
  persona: normalizeBaseUrl(
    import.meta.env.VITE_PERSONA_API_BASE_URL || DEFAULT_PERSONA_API_BASE
  ),
});

export const getApiBase = (service = 'default') => API_BASES[service] || API_BASES.default;

export const buildApiUrl = (path) => {
  const rawPath = String(path || '').trim();
  if (!rawPath) return '';
  if (ABSOLUTE_URL_PATTERN.test(rawPath) || rawPath.startsWith('data:')) {
    return rawPath;
  }

  let normalizedPath = rawPath.startsWith('/')
    ? rawPath
    : `/${rawPath}`;

  // 开发代理使用 /persona-api 区分 PersonaVLM；直连时映射回它真实的 /api 路径。
  const isPersonaRequest = normalizedPath === '/persona-api'
    || normalizedPath.startsWith('/persona-api/');
  if (isPersonaRequest) {
    // 开发环境必须保留 /persona-api 前缀，让 Vite 反向代理到 PersonaVLM。
    // 这样即使前端临时改用 9011 等端口，也不会由浏览器跨域直连 9001。
    if (import.meta.env.DEV) return normalizedPath;
    normalizedPath = normalizedPath.replace(/^\/persona-api(?=\/|$)/, '/api');
  }

  const base = getApiBase(isPersonaRequest ? 'persona' : 'default');
  return base ? `${base}${normalizedPath}` : normalizedPath;
};

export const getApiFetchErrorMessage = (error) => {
  const message = String(error?.message || error || '');

  if (message.includes('Failed to fetch')) {
    return '无法连接到后端服务，请确认服务地址、服务状态和跨域配置。';
  }

  return message || '请求失败';
};
