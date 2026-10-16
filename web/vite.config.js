// Vite 配置入口：
// 1. 挂载 Vue 官方插件；
// 2. 指定开发服务器监听地址与端口；
// 3. 通过反向代理把前端请求转发到后端服务，避免浏览器跨域。
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { Agent as HttpAgent } from 'node:http';
import { Agent as HttpsAgent } from 'node:https';
import fs from 'node:fs';
import path from 'node:path';
import {
  DEFAULT_API_BASE,
  DEFAULT_PERSONA_API_BASE,
} from './src/config/apiEndpoints.js';

const projectRoot = path.resolve(__dirname, '..');

function parseLocalEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};

  const env = {};
  for (const line of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const eqIndex = trimmed.indexOf('=');
    if (eqIndex <= 0) continue;

    const key = trimmed.slice(0, eqIndex).trim();
    let value = trimmed.slice(eqIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

function splitTurnUrls(value) {
  return String(value || '')
    .split(/[\s,]+/)
    .map((url) => url.trim())
    .filter(Boolean);
}

function buildLocalRtcConfig() {
  const localEnv = {
    ...parseLocalEnvFile(path.join(projectRoot, 'config.env')),
    ...parseLocalEnvFile(path.join(projectRoot, '.env.local')),
    ...process.env,
  };

  const turnHost = localEnv.TURN_HOST || '101.200.57.208';
  const turnPort = localEnv.TURN_PORT || '3478';
  const turnUrls = splitTurnUrls(localEnv.TURN_URL);
  const urls = turnUrls.length > 0
    ? turnUrls
    : [
        `turn:${turnHost}:${turnPort}?transport=udp`,
        `turn:${turnHost}:${turnPort}?transport=tcp`,
      ];

  if (!localEnv.TURN_USERNAME || !localEnv.TURN_PASSWORD) {
    return null;
  }

  return {
    iceServers: [
      {
        urls: [`stun:${turnHost}:${turnPort}`],
      },
      {
        urls,
        username: localEnv.TURN_USERNAME,
        credential: localEnv.TURN_PASSWORD,
      },
    ],
    iceTransportPolicy: localEnv.ICE_TRANSPORT_POLICY || 'relay',
  };
}

function localRtcConfigPlugin() {
  return {
    name: 'local-rtc-config',
    configureServer(server) {
      server.middlewares.use('/rtc_config', (req, res, next) => {
        if (req.method !== 'GET') {
          next();
          return;
        }

        const rtcConfig = buildLocalRtcConfig();
        if (!rtcConfig) {
          next();
          return;
        }

        res.statusCode = 200;
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.setHeader('Cache-Control', 'no-store');
        res.end(JSON.stringify(rtcConfig));
      });
    },
  };
}

function localLightRagProxyPlugin({ baseUrl, apiKey }) {
  const normalizedBaseUrl = String(baseUrl || '').trim().replace(/\/+$/, '');
  const normalizedApiKey = String(apiKey || '').trim();

  const routeMap = {
    '/graph_labels': '/graph/label/popular',
    '/graph': '/graphs',
    '/documents': '/documents/paginated',
    '/document_counts': '/documents/status_counts',
    '/pipeline_status': '/documents/pipeline_status',
    '/scan': '/documents/scan',
    '/upload': '/documents/upload',
  };

  const readBody = (req) => new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });

  const sendJson = (res, statusCode, payload) => {
    const body = Buffer.from(JSON.stringify(payload), 'utf8');
    res.statusCode = statusCode;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Content-Length', String(body.length));
    res.setHeader('Cache-Control', 'no-store');
    res.end(body);
  };

  const requestLightRag = async (pathname, search, req, body, methodOverride = '') => {
    const headers = {
      Accept: 'application/json',
      'X-API-Key': normalizedApiKey,
    };
    const contentType = String(req.headers['content-type'] || '').trim();
    if (contentType) headers['Content-Type'] = contentType;

    const method = String(methodOverride || req.method || 'GET').toUpperCase();
    const options = {
      method,
      headers,
      signal: AbortSignal.timeout(pathname === '/documents/upload' ? 60000 : 15000),
    };
    if (!['GET', 'HEAD'].includes(method) && body.length) options.body = body;

    const response = await fetch(`${normalizedBaseUrl}${pathname}${search}`, options);
    const text = await response.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { message: text || `LightRAG HTTP ${response.status}` };
    }

    if (!response.ok) {
      const message = data?.detail || data?.message || `LightRAG HTTP ${response.status}`;
      const error = new Error(typeof message === 'string' ? message : JSON.stringify(message));
      error.statusCode = response.status;
      throw error;
    }
    return data;
  };

  return {
    name: 'local-lightrag-proxy',
    configureServer(server) {
      server.middlewares.use('/api/lightrag', async (req, res, next) => {
        if (!normalizedBaseUrl || !normalizedApiKey) {
          next();
          return;
        }

        const remoteAddress = String(req.socket.remoteAddress || '');
        const isLoopback = remoteAddress === '127.0.0.1'
          || remoteAddress === '::1'
          || remoteAddress.startsWith('::ffff:127.');
        if (!isLoopback) {
          sendJson(res, 403, { code: -1, msg: 'LightRAG 开发代理仅允许本机访问' });
          return;
        }

        try {
          const requestUrl = new URL(req.url || '/', 'http://localhost');
          const upstreamPath = routeMap[requestUrl.pathname];
          if (!upstreamPath) {
            next();
            return;
          }

          let body = await readBody(req);
          if (requestUrl.pathname === '/documents' && body.length) {
            try {
              const payload = JSON.parse(body.toString('utf8'));
              if (!String(payload?.status_filter || '').trim()) {
                delete payload.status_filter;
              }
              body = Buffer.from(JSON.stringify(payload), 'utf8');
            } catch {
              // Let LightRAG report malformed JSON using its native validation response.
            }
          }
          let data = await requestLightRag(upstreamPath, requestUrl.search, req, body);

          if (requestUrl.pathname === '/graph_labels') {
            data = { labels: Array.isArray(data) ? data : [] };
          } else if (requestUrl.pathname === '/documents') {
            const statusCounts = await requestLightRag(
              '/documents/status_counts',
              '',
              req,
              Buffer.alloc(0),
              'GET'
            );
            data = { ...data, status_counts: data?.status_counts || statusCounts || {} };
          }

          sendJson(res, 200, { code: 0, msg: 'ok', data });
        } catch (error) {
          console.error(`[vite-lightrag] ${req.method} ${req.url} failed: ${error.message}`);
          sendJson(res, Number(error.statusCode || 502), {
            code: -1,
            msg: `LightRAG 开发代理请求失败：${error.message}`,
          });
        }
      });
    },
  };
}

function createProxy(target, routeTag) {
  const resolvedTarget = String(target || '').trim();
  const isHttps = resolvedTarget.startsWith('https://');
  const agent = isHttps
    ? new HttpsAgent({ keepAlive: false })
    : new HttpAgent({ keepAlive: false });

  return {
    target: resolvedTarget,
    changeOrigin: true,
    secure: false,
    agent,
    configure(proxy) {
      proxy.on('error', (err, req, res) => {
        const message = String(err?.message || 'upstream unavailable');
        const reqUrl = String(req?.url || routeTag || 'unknown');
        console.error(`[vite-proxy] ${routeTag} ${reqUrl} -> ${resolvedTarget} failed: ${message}`);

        if (!res || res.headersSent || typeof res.writeHead !== 'function') {
          return;
        }
        res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ code: -1, msg: `proxy ${routeTag} failed: ${message}` }));
      });
    },
  };
}

const localEnv = {
  ...parseLocalEnvFile(path.join(projectRoot, 'config.env')),
  ...parseLocalEnvFile(path.join(projectRoot, '.env.local')),
  ...parseLocalEnvFile(path.join(__dirname, '.env.local')),
  ...process.env,
};

const backendTarget = localEnv.VITE_API_BASE_URL
  || localEnv.VITE_BACKEND_TARGET
  || localEnv.BACKEND_TARGET
  || DEFAULT_API_BASE;
const webrtcTarget = localEnv.VITE_WEBRTC_TARGET || localEnv.WEBRTC_TARGET || backendTarget;
const asrTarget = localEnv.VITE_ASR_TARGET || localEnv.ASR_TARGET || backendTarget;
const personaTarget = localEnv.VITE_PERSONA_API_BASE_URL
  || localEnv.VITE_PERSONA_TARGET
  || localEnv.PERSONA_TARGET
  || DEFAULT_PERSONA_API_BASE;
const lightRagTarget = localEnv.LIGHTRAG_BASE_URL || 'http://101.200.57.208:9622';
const lightRagApiKey = localEnv.LIGHTRAG_API_KEY || '';

export default defineConfig({
    define: {
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(backendTarget),
      'import.meta.env.VITE_PERSONA_API_BASE_URL': JSON.stringify(personaTarget),
    },

    // 启用 Vue 单文件组件编译能力（.vue）。
    plugins: [
      localRtcConfigPlugin(),
      localLightRagProxyPlugin({ baseUrl: lightRagTarget, apiKey: lightRagApiKey }),
      vue(),
    ],

    // 配置路径别名
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src')
      }
    },

    server: {
      // 监听所有网卡，便于局域网/反代环境访问。
      host: '0.0.0.0',

      // 前端开发端口：当前项目固定使用 9010。
      port: 9010,

      // 代理规则说明：
      // 每个接口都映射到同一后端地址，保证前端可用相对路径请求 API。
      proxy: {
        // 数字人配置、音色克隆、语音/视频生成等 REST API
        '/api': createProxy(backendTarget, '/api'),

        // 头像静态资源：后端若开放对应路径，前端可直接同源加载
        '/avatars': createProxy(backendTarget, '/avatars'),
        '/data': createProxy(backendTarget, '/data'),

        // 文本对话与数字人控制
        '/human': createProxy(webrtcTarget, '/human'),
        '/ai_conversation': createProxy(webrtcTarget, '/ai_conversation'),

        // SSE 流式聊天输出
        '/chat_stream': createProxy(webrtcTarget, '/chat_stream'),

        // WebRTC 配置与 SDP 协商
        '/rtc_config': createProxy(webrtcTarget, '/rtc_config'),
        '/offer': createProxy(webrtcTarget, '/offer'),
        '/candidate': createProxy(webrtcTarget, '/candidate'),

        // 语音识别接口（文件上传式）
        '/asr': createProxy(asrTarget, '/asr'),

        // 个性化记忆服务：转到 PersonaVLM API，避免与 LiveTalking 的 /api 混在一起
        '/persona-api': {
          ...createProxy(personaTarget, '/persona-api'),
          rewrite: (requestPath) => requestPath.replace(/^\/persona-api/, '/api'),
        },

        // WebRTC 上行媒体状态查询与流式 ASR 控制
        '/webrtc_media_state': createProxy(webrtcTarget, '/webrtc_media_state'),
        '/webrtc_asr_control': createProxy(webrtcTarget, '/webrtc_asr_control'),

        // 多模态心理状态分析
        '/multimodal_analysis': createProxy(webrtcTarget, '/multimodal_analysis'),

      },
    },
});
