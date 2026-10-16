import { ref, computed, watch, onMounted } from 'vue';

const STORAGE_KEY = 'hearttalk-theme';
const VALID_THEMES = ['night', 'day'];
const DEFAULT_THEME = 'night';

// 主题配置
const THEME_CONFIGS = {
    night: {
        id: 'night',
        name: '夜间主题',
        icon: 'bi-moon-stars-fill',
        variables: {
            '--theme-primary': '#ff6b81',
            '--theme-primary-light': '#ec4899',
            '--theme-primary-dark': '#8a2be2',
            '--theme-bg-base': '#0a0b14',
            '--theme-bg-card': 'rgba(26, 22, 37, 0.85)',
            '--theme-bg-input': 'rgba(30, 27, 43, 0.9)',
            '--theme-text-primary': '#e2e8f0',
            '--theme-text-secondary': '#cbd5e1',
            '--theme-text-muted': '#94a3b8',
            '--theme-border': 'rgba(255, 107, 129, 0.2)',
            '--theme-shadow': '0 8px 32px rgba(255, 107, 129, 0.15)',
            '--theme-shadow-hover': '0 12px 48px rgba(255, 107, 129, 0.25)',
            '--theme-gradient-1': 'rgba(255, 107, 129, 0.25)',
            '--theme-gradient-2': 'rgba(138, 43, 226, 0.2)',
            '--theme-gradient-3': 'rgba(99, 102, 241, 0.15)',
            '--theme-gradient-4': 'rgba(236, 72, 153, 0.18)',
            '--theme-particle-1': 'rgba(255, 107, 129, 0.3)',
            '--theme-particle-2': 'rgba(138, 43, 226, 0.3)',
            '--theme-particle-3': 'rgba(236, 72, 153, 0.3)',
            '--theme-particle-4': 'rgba(99, 102, 241, 0.3)',
            '--theme-scrollbar-track': 'rgba(15, 12, 29, 0.5)',
            '--theme-scrollbar-thumb-start': 'rgba(255, 107, 129, 0.6)',
            '--theme-scrollbar-thumb-end': 'rgba(138, 43, 226, 0.6)',
            '--theme-scrollbar-thumb-hover-start': 'rgba(255, 107, 129, 0.9)',
            '--theme-scrollbar-thumb-hover-end': 'rgba(138, 43, 226, 0.9)'
        }
    },
    day: {
        id: 'day',
        name: '日间主题',
        icon: 'bi-sun-fill',
        variables: {
            '--theme-primary': '#3b82f6',
            '--theme-primary-light': '#60a5fa',
            '--theme-primary-dark': '#1e40af',
            '--theme-bg-base': '#f0f4f8',
            '--theme-bg-card': 'rgba(255, 255, 255, 0.85)',
            '--theme-bg-input': 'rgba(241, 245, 249, 0.95)',
            '--theme-text-primary': '#1e293b',
            '--theme-text-secondary': '#475569',
            '--theme-text-muted': '#64748b',
            '--theme-border': 'rgba(59, 130, 246, 0.3)',
            '--theme-shadow': '0 4px 12px rgba(59, 130, 246, 0.2)',
            '--theme-shadow-hover': '0 10px 20px rgba(59, 130, 246, 0.3)',
            '--theme-gradient-1': 'rgba(59, 130, 246, 0.15)',
            '--theme-gradient-2': 'rgba(96, 165, 250, 0.18)',
            '--theme-gradient-3': 'rgba(147, 197, 253, 0.12)',
            '--theme-gradient-4': 'rgba(37, 99, 235, 0.15)',
            '--theme-particle-1': 'rgba(59, 130, 246, 0.35)',
            '--theme-particle-2': 'rgba(96, 165, 250, 0.30)',
            '--theme-particle-3': 'rgba(37, 99, 235, 0.32)',
            '--theme-particle-4': 'rgba(29, 78, 216, 0.28)',
            '--theme-scrollbar-track': 'rgba(226, 232, 240, 0.8)',
            '--theme-scrollbar-thumb-start': 'rgba(59, 130, 246, 0.6)',
            '--theme-scrollbar-thumb-end': 'rgba(30, 64, 175, 0.6)',
            '--theme-scrollbar-thumb-hover-start': 'rgba(59, 130, 246, 0.9)',
            '--theme-scrollbar-thumb-hover-end': 'rgba(30, 64, 175, 0.9)',
            '--theme-accent-purple': '#a855f7',
            '--theme-accent-pink': '#ec4899',
            '--theme-accent-cyan': '#06b6d4',
            '--theme-accent-green': '#10b981',
            '--theme-accent-orange': '#f59e0b'
        }
    }
};

// 全局状态（单例模式）
let currentTheme = null;

export function useTheme() {
    // 初始化全局状态
    if (!currentTheme) {
        currentTheme = ref(DEFAULT_THEME);
    }

    // 计算属性
    const isNightTheme = computed(() => currentTheme.value === 'night');
    const isDayTheme = computed(() => currentTheme.value === 'day');

    // 验证主题标识符
    const isValidTheme = (theme) => VALID_THEMES.includes(theme);

    // 应用 CSS 变量到 DOM
    const applyCSSVariables = (theme) => {
        const config = THEME_CONFIGS[theme];
        if (!config) return;

        const root = document.documentElement;
        Object.entries(config.variables).forEach(([key, value]) => {
            root.style.setProperty(key, value);
        });
    };

    // 更新 DOM 属性
    const updateDOMAttribute = (theme) => {
        document.documentElement.setAttribute('data-theme', theme);
    };

    // 保存到 LocalStorage
    const saveToStorage = (theme) => {
        try {
            const data = {
                theme,
                timestamp: Date.now(),
                version: '1.0'
            };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (error) {
            console.warn('Failed to save theme to localStorage:', error);
        }
    };

    // 从 LocalStorage 读取
    const loadFromStorage = () => {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return null;

            const data = JSON.parse(raw);
            return isValidTheme(data.theme) ? data.theme : null;
        } catch (error) {
            console.warn('Failed to load theme from localStorage:', error);
            return null;
        }
    };

    // 检测系统主题偏好
    const detectSystemTheme = () => {
        if (typeof window === 'undefined' || !window.matchMedia) {
            return null;
        }

        try {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            return prefersDark ? 'night' : 'day';
        } catch (error) {
            console.warn('Failed to detect system theme:', error);
            return null;
        }
    };

    // 应用主题
    const applyTheme = (theme) => {
        if (!isValidTheme(theme)) {
            console.warn(`Invalid theme: ${theme}, falling back to ${DEFAULT_THEME}`);
            theme = DEFAULT_THEME;
        }

        currentTheme.value = theme;
        updateDOMAttribute(theme);
        applyCSSVariables(theme);
    };

    // 设置主题
    const setTheme = (theme) => {
        applyTheme(theme);
        saveToStorage(currentTheme.value);
    };

    // 切换主题
    const toggleTheme = () => {
        const newTheme = currentTheme.value === 'night' ? 'day' : 'night';
        setTheme(newTheme);
    };

    // 初始化主题
    const initializeTheme = () => {
        // 优先级: LocalStorage > 系统偏好 > 默认主题
        const savedTheme = loadFromStorage();
        if (savedTheme) {
            applyTheme(savedTheme);
            return;
        }

        const systemTheme = detectSystemTheme();
        if (systemTheme) {
            applyTheme(systemTheme);
            saveToStorage(systemTheme);
            return;
        }

        applyTheme(DEFAULT_THEME);
    };

    // 组件挂载时初始化
    onMounted(() => {
        initializeTheme();
    });

    return {
        currentTheme,
        isNightTheme,
        isDayTheme,
        setTheme,
        toggleTheme
    };
}
