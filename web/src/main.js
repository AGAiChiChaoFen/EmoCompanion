import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import { buildApiUrl } from './utils/api'

// public/client.js 是传统脚本，通过同一个构造器访问后端，避免维护第二套地址配置。
window.__APP_BUILD_API_URL__ = buildApiUrl

const app = createApp(App)

app.use(ElementPlus)
app.use(router)

app.mount('#app')
