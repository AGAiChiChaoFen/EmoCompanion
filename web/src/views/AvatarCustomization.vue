<template>
  <div class="avatar-customization">
    <!-- 🆕 消息提示组件 -->
    <transition name="message-fade">
      <div v-if="showMessage" class="message-toast" :class="errorMessage ? 'message-error' : 'message-success'">
        <div class="message-content">
          <i :class="['bi', errorMessage ? 'bi-exclamation-circle-fill' : 'bi-check-circle-fill']"></i>
          <span>{{ errorMessage || successMessage }}</span>
        </div>
        <button class="message-close" @click="hideMessage">
          <i class="bi bi-x"></i>
        </button>
      </div>
    </transition>
    
    <div class="content-grid">
      <!-- 左侧：配置面板 -->
      <div class="config-panel">
        <div class="panel-section">
          <h3 class="section-title">
            <i class="bi bi-person-circle"></i>
            选择数字人形象
          </h3>
          
          <!-- 🆕 加载状态 -->
          <div v-if="isLoadingAvatars" class="loading-state">
            <div class="spinner-small"></div>
            <span>加载形象列表中...</span>
          </div>
          
          <!-- 🆕 空状态 -->
          <div v-else-if="avatarOptions.length === 0" class="empty-state">
            <i class="bi bi-exclamation-circle"></i>
            <span>无法加载形象列表</span>
            <button class="btn-retry" @click="loadAvatars">
              <i class="bi bi-arrow-clockwise"></i>
              重试
            </button>
          </div>
          
          <div v-else class="avatar-scroll-container">
            <div class="avatar-grid">
            <!-- 上传照片选项 -->
            <div
              class="avatar-card upload-card"
              :class="{ selected: selectedAvatar === 'custom' || selectedAvatar === customAvatarId, uploading: isUploadingPhoto }"
              @click="triggerPhotoUpload"
            >
              <div class="avatar-preview upload-preview">
                <img v-if="customPhoto" :src="customPhoto" alt="自定义照片" />
                <div v-else class="avatar-fallback">
                  <i :class="['bi', isUploadingPhoto ? 'bi-hourglass-split' : 'bi-cloud-upload']"></i>
                  <span>{{ isUploadingPhoto ? '上传中...' : '上传照片' }}</span>
                </div>
                <div class="avatar-overlay">
                  <i class="bi bi-check-circle-fill"></i>
                </div>
              </div>
              <div class="avatar-info">
                <span class="avatar-name">自定义形象</span>
                <span class="avatar-desc">{{ customAvatarId ? '已绑定上传形象' : '上传您的照片' }}</span>
              </div>
            </div>

            <div
              v-for="avatar in avatarOptions"
              :key="avatar.id"
              class="avatar-card"
              :class="{ selected: selectedAvatar === avatar.id }"
              @click="selectAvatar(avatar.id)"
            >
              <div
                class="avatar-preview"
                :style="{
                  '--avatar-accent': avatar.accent,
                  '--avatar-accent-soft': avatar.accentSoft
                }"
              >
                <img
                  v-if="imageAvailability[avatar.id]"
                  :src="avatar.image"
                  :alt="avatar.name"
                  loading="lazy"
                  @error="handleAvatarImageError(avatar.id)"
                />
                <div v-else class="avatar-fallback">
                  <i :class="avatar.fallbackIcon"></i>
                  <span>{{ avatar.fallbackLabel }}</span>
                </div>
                <div class="avatar-overlay">
                  <i class="bi bi-check-circle-fill"></i>
                </div>
              </div>
              <div class="avatar-info">
                <span class="avatar-name">{{ avatar.name }}</span>
                <span class="avatar-desc">{{ avatar.description }}</span>
              </div>
            </div>
          </div>
          </div>
          <input 
            type="file" 
            ref="photoInput" 
            accept="image/*" 
            style="display:none" 
            @change="handlePhotoUpload"
          />
        </div>

        <div class="panel-section">
          <h3 class="section-title">
            <i class="bi bi-mic"></i>
            选择声音
          </h3>
          
          <!-- 🆕 加载状态 -->
          <div v-if="isLoadingVoices" class="loading-state">
            <div class="spinner-small"></div>
            <span>加载音色列表中...</span>
          </div>
          
          <!-- 🆕 空状态 -->
          <div v-else-if="voiceOptions.length === 0" class="empty-state">
            <i class="bi bi-exclamation-circle"></i>
            <span>无法加载音色列表</span>
            <button class="btn-retry" @click="loadVoices">
              <i class="bi bi-arrow-clockwise"></i>
              重试
            </button>
          </div>
          
          <div v-else class="voice-scroll-container">
            <div class="voice-grid">
            <!-- 🆕 上传音频选项（放在最前面） -->
            <div
              class="voice-card upload-voice"
              :class="{ selected: selectedVoice === 'upload', uploading: isUploadingAudio }"
              @click="triggerAudioUpload"
            >
              <div class="voice-icon">
                <i :class="['bi', isUploadingAudio ? 'bi-hourglass-split' : 'bi-cloud-upload']"></i>
              </div>
              <div class="voice-info">
                <span class="voice-name">{{ isUploadingAudio ? '上传中...' : '上传音频' }}</span>
                <span class="voice-desc">音色克隆</span>
              </div>
              <div class="voice-check">
                <i class="bi bi-check-circle-fill"></i>
              </div>
            </div>
            
            <!-- 🆕 录音选项（放在第二位） -->
            <div
              class="voice-card record-voice"
              :class="{ selected: selectedVoice === 'record', recording: isRecordingVoice }"
              @click="toggleRecordVoice"
            >
              <div class="voice-icon">
                <i :class="['bi', isRecordingVoice ? 'bi-stop-circle-fill' : 'bi-mic-fill']"></i>
              </div>
              <div class="voice-info">
                <span class="voice-name">{{ isRecordingVoice ? '停止录音' : '录制音频' }}</span>
                <span class="voice-desc">{{ isRecordingVoice ? '录音中...' : '实时录音' }}</span>
              </div>
              <div class="voice-check">
                <i class="bi bi-check-circle-fill"></i>
              </div>
            </div>
            
            <!-- 预设音色列表 -->
            <div
              v-for="voice in voiceOptions"
              :key="voice.id"
              class="voice-card"
              :class="{ selected: selectedVoice === voice.id }"
              @click="selectVoice(voice.id)"
            >
              <div class="voice-icon">
                <i :class="voice.icon"></i>
              </div>
              <div class="voice-info">
                <span class="voice-name">{{ voice.name }}</span>
                <span class="voice-desc">{{ voice.description }}</span>
              </div>
              <div v-if="isLoadingVoicePreviews" class="voice-preview-loading" title="示例音频加载中">
                <div class="voice-preview-spinner"></div>
              </div>
              <button
                v-else-if="voice.previewUrl"
                class="voice-preview-btn"
                type="button"
                :title="playingPreviewVoiceId === voice.id ? '停止试听' : '试听示例音频'"
                @click.stop="toggleVoicePreview(voice)"
              >
                <i :class="['bi', playingPreviewVoiceId === voice.id ? 'bi-stop-fill' : 'bi-play-fill']"></i>
              </button>
              <div v-else class="voice-preview-placeholder"></div>
              <div class="voice-check">
                <i class="bi bi-check-circle-fill"></i>
              </div>
            </div>
          </div>
          </div>
          <input 
            type="file" 
            ref="audioInput" 
            accept="audio/*" 
            style="display:none" 
            @change="handleAudioUpload"
          />
        </div>

        <div class="panel-section text-section">
          <h3 class="section-title">
            <i class="bi bi-chat-text"></i>
            输入文本内容
            <span class="text-stats-inline">{{ inputText.length }} 字符</span>
          </h3>
          <div class="text-header">
            <button
              v-if="hasSuggestion"
              class="btn-use-suggestion"
              @click="useSuggestion"
            >
              <i class="bi bi-lightbulb-fill"></i>
              使用分析建议
            </button>
          </div>
          <textarea
            v-model="inputText"
            class="text-input"
            placeholder="请输入数字人要说的内容..."
            rows="4"
          ></textarea>
        </div>

        <div class="panel-section button-section">
          <button
            class="btn-generate"
            :disabled="!canGenerate || isGenerating"
            @click="generateVideo"
          >
            <i :class="['bi', isGenerating ? 'bi-hourglass-split' : 'bi-play-circle-fill']"></i>
            <span>{{ isGenerating ? '生成中...' : '生成数字人视频' }}</span>
          </button>
        </div>
      </div>

      <!-- 右侧：预览区域 -->
      <div class="preview-panel">
        <div class="preview-header">
          <h3 class="section-title">
            <i class="bi bi-camera-video"></i>
            视频预览
          </h3>
          <div class="status-badge" :class="statusClass">
            {{ statusText }}
          </div>
        </div>

        <div class="video-container">
          <div v-if="!videoUrl && !isGenerating" class="placeholder">
            <div class="placeholder-icon">
              <i class="bi bi-camera-video-off"></i>
            </div>
            <p class="placeholder-text">选择形象并输入文本后，点击生成按钮</p>
          </div>

          <div v-if="isGenerating" class="generating-state">
            <div class="spinner"></div>
            <p class="generating-text">正在生成数字人视频...</p>
            <p class="generating-hint">这可能需要几秒钟时间</p>
          </div>

          <div
            v-if="videoUrl && !isGenerating"
            class="video-stage"
            role="button"
            tabindex="0"
            aria-label="点击播放或暂停视频"
            @click="toggleVideoPlayback"
            @keydown.enter.prevent="toggleVideoPlayback"
            @keydown.space.prevent="toggleVideoPlayback"
          >
            <div class="video-backdrop" aria-hidden="true">
              <video
                ref="videoBackdrop"
                :src="videoUrl"
                muted
                playsinline
                tabindex="-1"
              ></video>
            </div>
            <video
              ref="videoPlayer"
              :src="videoUrl"
              class="video-player"
              playsinline
              @play="syncVideoBackdrop"
              @pause="syncVideoBackdrop"
              @timeupdate="syncVideoBackdrop"
              @seeking="syncVideoBackdrop"
              @ended="syncVideoBackdrop"
            ></video>
          </div>
        </div>

        <div v-if="videoUrl" class="video-actions">
          <button class="btn-action" @click="downloadVideo">
            <i class="bi bi-download"></i>
            下载视频
          </button>
          <button class="btn-action btn-secondary" @click="resetGeneration">
            <i class="bi bi-arrow-clockwise"></i>
            重新生成
          </button>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted, watch } from 'vue';
import { useRoute } from 'vue-router';
import { buildApiUrl, getApiFetchErrorMessage } from '../utils/api';
import {
  loadPersistentJson,
  loadPersistentValue,
  removePersistentValue,
  savePersistentJson,
  savePersistentValue,
} from '../utils/persistentState';

const route = useRoute();

// 数字人形象选项（从后端动态加载）
const avatarOptions = ref([]);

// 声音选项（从后端动态加载）
const voiceOptions = ref([]);

const selectedAvatar = ref('');
const selectedVoice = ref('');
const inputText = ref('');
const isGenerating = ref(false);
const videoUrl = ref('');
const videoPlayer = ref(null);
const videoBackdrop = ref(null);
const photoInput = ref(null);
const audioInput = ref(null);
const customPhoto = ref('');
const customAvatarId = ref('');
const isRecordingVoice = ref(false);
const imageAvailability = ref({});
const suggestionText = ref('');
const isLoadingVoices = ref(false);
const isLoadingAvatars = ref(false);
const isUploadingAudio = ref(false);
const isUploadingPhoto = ref(false);

const voicePreviewMap = ref({});
const voicePreviewAudio = ref(null);
const playingPreviewVoiceId = ref('');
const isLoadingVoicePreviews = ref(false);
const voicePreviewManifestLoaded = ref(false);

// 🆕 错误和成功消息状态
const errorMessage = ref('');
const successMessage = ref('');
const showMessage = ref(false);

const AVATAR_PAGE_STATE_KEY = 'hearttalk.avatar.page.v1';
const AVATAR_VIDEO_BLOB_KEY = 'hearttalk.avatar.video.blob.v1';

// 🆕 显示消息的辅助函数
const displayMessage = (message, type = 'error') => {
  if (type === 'error') {
    errorMessage.value = message;
    successMessage.value = '';
  } else {
    successMessage.value = message;
    errorMessage.value = '';
  }
  showMessage.value = true;
  
  // 3秒后自动隐藏
  setTimeout(() => {
    showMessage.value = false;
  }, 3000);
};

const hideMessage = () => {
  showMessage.value = false;
};

const revokeObjectUrl = (url) => {
  if (typeof url === 'string' && url.startsWith('blob:')) {
    URL.revokeObjectURL(url);
  }
};

const normalizeStaticMediaPath = (path) => {
  const normalized = String(path || '').trim().replace(/\\/g, '/');
  if (!normalized) {
    return '';
  }
  if (/^(?:https?:)?\/\//i.test(normalized) || normalized.startsWith('data:')) {
    return normalized;
  }

  const dataIndex = normalized.indexOf('/data/');
  if (dataIndex >= 0) {
    return normalized.slice(dataIndex);
  }

  if (normalized.startsWith('data/')) {
    return `/${normalized}`;
  }

  const avatarsIndex = normalized.indexOf('/avatars/');
  if (avatarsIndex >= 0) {
    return normalized.slice(avatarsIndex);
  }

  return normalized.startsWith('/') ? normalized : `/${normalized}`;
};

const resolveUploadedMediaUrl = (path) => {
  const normalized = normalizeStaticMediaPath(path);
  return normalized ? buildApiUrl(normalized) : '';
};

const parseJsonResponse = async (response, fallbackPrefix) => {
  const contentType = String(response.headers.get('content-type') || '').toLowerCase();
  const payload = contentType.includes('application/json')
    ? await response.json()
    : null;

  if (!response.ok) {
    const message = payload?.msg || `${fallbackPrefix}失败: HTTP ${response.status}: ${response.statusText}`;
    throw new Error(message);
  }

  if (!payload) {
    throw new Error(`${fallbackPrefix}失败: 后端没有返回 JSON`);
  }

  return payload;
};

const normalizeWarnings = (warnings) => {
  if (Array.isArray(warnings)) {
    return warnings.filter(Boolean).map((item) => String(item));
  }
  if (typeof warnings === 'string' && warnings.trim()) {
    return [warnings.trim()];
  }
  return [];
};

const loadVoicePreviews = async () => {
  isLoadingVoicePreviews.value = true;
  voicePreviewManifestLoaded.value = false;
  try {
    const response = await fetch(buildApiUrl('/data/demo_voices/manifest.json'), {
      cache: 'no-store'
    });
    if (!response.ok) {
      console.warn('示例音频清单加载失败:', response.status, response.statusText);
      voicePreviewMap.value = {};
      return;
    }
    const manifest = await response.json();
    const items = Array.isArray(manifest?.items) ? manifest.items : [];
    voicePreviewMap.value = Object.fromEntries(
      items
        .filter(item => item?.voice_id && item?.url)
        .map(item => [item.voice_id, buildApiUrl(item.url)])
    );
    voicePreviewManifestLoaded.value = true;
  } catch (error) {
    console.warn('示例音频清单加载失败:', error);
    voicePreviewMap.value = {};
  } finally {
    isLoadingVoicePreviews.value = false;
  }
};

const persistAvatarPageState = () => {
  savePersistentJson(AVATAR_PAGE_STATE_KEY, {
    selectedAvatar: selectedAvatar.value,
    selectedVoice: selectedVoice.value,
    inputText: inputText.value,
    customPhoto: customPhoto.value,
    customAvatarId: customAvatarId.value,
    suggestionText: suggestionText.value,
  });
};

const restoreAvatarPageState = () => {
  const persistedState = loadPersistentJson(AVATAR_PAGE_STATE_KEY, null);
  if (!persistedState || typeof persistedState !== 'object') {
    return;
  }

  selectedAvatar.value = String(persistedState.selectedAvatar || '');
  selectedVoice.value = String(persistedState.selectedVoice || '');
  inputText.value = String(persistedState.inputText || '');
  customPhoto.value = String(persistedState.customPhoto || '');
  customAvatarId.value = String(persistedState.customAvatarId || '');
  suggestionText.value = String(persistedState.suggestionText || '');
};

const restoreGeneratedMedia = async () => {
  const savedVideoBlob = await loadPersistentValue(AVATAR_VIDEO_BLOB_KEY);

  if (savedVideoBlob instanceof Blob) {
    revokeObjectUrl(videoUrl.value);
    videoUrl.value = URL.createObjectURL(savedVideoBlob);
  }

};

const resolveAvatarImageUrl = (avatar) => {
  const imageUrl = String(avatar?.image_url || '').trim();
  if (imageUrl) {
    return buildApiUrl(imageUrl);
  }

  const imagePath = String(avatar?.image_path || '').trim().replace(/^\.?\//, '');
  if (!imagePath) {
    return '';
  }

  return buildApiUrl(`/${imagePath}`);
};

// 🆕 加载形象列表
const loadAvatars = async () => {
  isLoadingAvatars.value = true;
  try {
    const avatarsUrl = buildApiUrl('/api/avatars');
    console.log(`正在从 ${avatarsUrl} 加载形象列表...`);
    
    const response = await fetch(avatarsUrl);
    
    console.log('响应状态:', response.status, response.statusText);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const result = await response.json();
    console.log('响应数据:', result);
    
    if (result.code !== 0) {
      throw new Error(result.msg || 'Failed to load avatars');
    }
    
    // 从 data.avatars 中获取形象列表
    const avatars = result.data?.avatars || [];
    console.log('解析到的形象列表:', avatars);
    
    if (avatars.length === 0) {
      throw new Error('形象列表为空，请检查后端配置文件');
    }
    
    // 转换后端数据格式为前端需要的格式
    avatarOptions.value = avatars.map(avatar => ({
      id: avatar.avatar_id,
      name: avatar.name,
      description: avatar.description,
      image: resolveAvatarImageUrl(avatar),
      accent: avatar.accent || '#ff6b81',
      accentSoft: avatar.accentSoft || 'rgba(255, 107, 129, 0.24)',
      fallbackIcon: avatar.fallbackIcon || 'bi bi-person-circle',
      fallbackLabel: avatar.fallbackLabel || avatar.name,
      type: avatar.type
    }));
    
    // 初始化图片可用性状态
    imageAvailability.value = Object.fromEntries(
      avatarOptions.value.map(avatar => [avatar.id, Boolean(avatar.image)])
    );

    const validAvatarIds = new Set(avatarOptions.value.map(avatar => avatar.id));
    if (
      selectedAvatar.value &&
      selectedAvatar.value !== 'custom' &&
      selectedAvatar.value !== customAvatarId.value &&
      !validAvatarIds.has(selectedAvatar.value)
    ) {
      selectedAvatar.value = '';
    }
    
    // 设置默认选中第一个形象
    if (avatarOptions.value.length > 0 && !selectedAvatar.value) {
      selectedAvatar.value = validAvatarIds.has('preset_default_avatar')
        ? 'preset_default_avatar'
        : avatarOptions.value[0].id;
    }
    
    console.log('形象列表加载成功:', avatarOptions.value);
  } catch (error) {
    console.error('加载形象列表失败:', error);
    displayMessage(`加载形象列表失败: ${getApiFetchErrorMessage(error)}`, 'error');
    avatarOptions.value = [];
  } finally {
    isLoadingAvatars.value = false;
  }
};

// 🆕 加载音色列表
const loadVoices = async () => {
  isLoadingVoices.value = true;
  try {
    const voicesUrl = buildApiUrl('/api/voices');
    console.log(`正在从 ${voicesUrl} 加载音色列表...`);
    
    const response = await fetch(voicesUrl);
    
    console.log('响应状态:', response.status, response.statusText);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const result = await response.json();
    console.log('响应数据:', result);
    
    if (result.code !== 0) {
      throw new Error(result.msg || 'Failed to load voices');
    }
    
    // 从 data.voices 中获取音色列表
    const voices = result.data?.voices || [];
    console.log('解析到的音色列表:', voices);
    
    if (voices.length === 0) {
      throw new Error('音色列表为空，请检查后端配置文件');
    }
    
    // 转换后端数据格式为前端需要的格式
    voiceOptions.value = voices.map(voice => ({
      id: voice.voice_id,
      name: voice.name,
      description: voice.description,
      icon: getVoiceIcon(voice.type, voice.name),
      type: voice.type,
      previewUrl: voicePreviewMap.value[voice.voice_id] || ''
    }));

    const validVoiceIds = new Set(voiceOptions.value.map(voice => voice.id));
    if (selectedVoice.value && !validVoiceIds.has(selectedVoice.value)) {
      selectedVoice.value = '';
    }
    
    // 设置默认选中第一个音色
    if (voiceOptions.value.length > 0 && !selectedVoice.value) {
      selectedVoice.value = voiceOptions.value[0].id;
    }
    
    console.log('音色列表加载成功:', voiceOptions.value);
  } catch (error) {
    console.error('加载音色列表失败:', error);
    voiceOptions.value = [];
  } finally {
    isLoadingVoices.value = false;
  }
};

// 🆕 根据音色类型和名称获取图标
const getVoiceIcon = (type, name) => {
  // 根据音色类型返回不同图标
  if (type === 'cloned') {
    return 'bi bi-person-badge';
  }
  if (type === 'described') {
    return 'bi bi-chat-quote';
  }
  
  // 预设音色根据名称判断
  const nameLower = name.toLowerCase();
  if (nameLower.includes('女') || nameLower.includes('female')) {
    if (nameLower.includes('温柔') || nameLower.includes('gentle')) {
      return 'bi bi-person-heart';
    }
    if (nameLower.includes('活力') || nameLower.includes('energetic')) {
      return 'bi bi-emoji-smile';
    }
    return 'bi bi-person-heart';
  }
  
  if (nameLower.includes('男') || nameLower.includes('male')) {
    if (nameLower.includes('沉稳') || nameLower.includes('steady')) {
      return 'bi bi-shield-check';
    }
    if (nameLower.includes('磁性') || nameLower.includes('magnetic')) {
      return 'bi bi-soundwave';
    }
    return 'bi bi-shield-check';
  }
  
  return 'bi bi-mic-fill';
};

const hasSuggestion = computed(() => {
  return suggestionText.value.length > 0;
});

const canGenerate = computed(() => {
  return selectedAvatar.value && selectedVoice.value && inputText.value.trim().length > 0;
});

const statusClass = computed(() => {
  if (isGenerating.value) return 'status-generating';
  if (videoUrl.value) return 'status-ready';
  return 'status-idle';
});

const statusText = computed(() => {
  if (isGenerating.value) return '生成中';
  if (videoUrl.value) return '已完成';
  return '待生成';
});

const syncVideoBackdrop = () => {
  const player = videoPlayer.value;
  const backdrop = videoBackdrop.value;
  if (!player || !backdrop) return;

  if (Math.abs(backdrop.currentTime - player.currentTime) > 0.12) {
    backdrop.currentTime = player.currentTime;
  }

  if (player.paused || player.ended) {
    backdrop.pause();
    return;
  }

  backdrop.play().catch(() => {
    // 背景仅用于视觉填充，播放失败不影响主视频。
  });
};

const toggleVideoPlayback = async () => {
  const player = videoPlayer.value;
  if (!player) return;

  if (!player.paused && !player.ended) {
    player.pause();
    return;
  }

  if (player.ended) {
    player.currentTime = 0;
  }

  try {
    await player.play();
  } catch (error) {
    displayMessage(`视频播放失败: ${error.message}`, 'error');
  }
};

const selectAvatar = (avatarId) => {
  selectedAvatar.value = avatarId;
  persistAvatarPageState();
};

const selectVoice = (voiceId) => {
  selectedVoice.value = voiceId;
  persistAvatarPageState();
};

const stopVoicePreview = () => {
  if (voicePreviewAudio.value) {
    voicePreviewAudio.value.pause();
    voicePreviewAudio.value.currentTime = 0;
  }
  playingPreviewVoiceId.value = '';
};

const toggleVoicePreview = (voice) => {
  if (!voice?.previewUrl) return;
  if (playingPreviewVoiceId.value === voice.id) {
    stopVoicePreview();
    return;
  }

  stopVoicePreview();
  const audio = new Audio(voice.previewUrl);
  voicePreviewAudio.value = audio;
  playingPreviewVoiceId.value = voice.id;
  audio.addEventListener('ended', () => {
    if (voicePreviewAudio.value === audio) {
      playingPreviewVoiceId.value = '';
    }
  }, { once: true });
  audio.addEventListener('error', () => {
    if (voicePreviewAudio.value === audio) {
      playingPreviewVoiceId.value = '';
      displayMessage('示例音频播放失败', 'error');
    }
  }, { once: true });
  audio.play().catch((error) => {
    playingPreviewVoiceId.value = '';
    displayMessage(`示例音频播放失败: ${error.message}`, 'error');
  });
};

const useSuggestion = () => {
  inputText.value = suggestionText.value;
  persistAvatarPageState();
};

const triggerPhotoUpload = () => {
  if (isUploadingPhoto.value) {
    displayMessage('正在上传图片，请稍候...', 'error');
    return;
  }
  photoInput.value?.click();
};

const handlePhotoUpload = async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  
  // 验证文件类型
  if (!file.type.startsWith('image/')) {
    displayMessage('请选择图片文件', 'error');
    return;
  }
  
  // 验证文件大小（最大 10MB）
  if (file.size > 10 * 1024 * 1024) {
    displayMessage('图片文件大小不能超过 10MB', 'error');
    return;
  }
  
  isUploadingPhoto.value = true;
  
  try {
    const formData = new FormData();
    formData.append('image', file);
    
    console.log('正在上传图片:', file.name);
    
    const response = await fetch(buildApiUrl('/api/upload/avatar'), {
      method: 'POST',
      body: formData
    });

    const result = await parseJsonResponse(response, '图片上传');
    console.log('上传响应:', result);
    
    if (result.code !== 0) {
      throw new Error(result.msg || '上传失败');
    }
    
    // 显示上传成功的图片
    const uploadedAvatar = result.data?.avatar;
    const uploadedAvatarId = result.data?.avatar_id || uploadedAvatar?.avatar_id;
    const uploadedImageUrl = resolveUploadedMediaUrl(uploadedAvatar?.image_url || uploadedAvatar?.image_path || result.data?.image_path);
    customPhoto.value = uploadedImageUrl || URL.createObjectURL(file);
    customAvatarId.value = uploadedAvatarId || '';
    selectedAvatar.value = uploadedAvatarId || 'custom';
    persistAvatarPageState();
    
    console.log('图片上传成功:', uploadedImageUrl);
    displayMessage('图片上传成功！', 'success');
    
    // 重新加载形象列表（如果后端自动添加到配置）
    await loadAvatars();
    if (uploadedAvatarId) {
      selectedAvatar.value = uploadedAvatarId;
      persistAvatarPageState();
    }
    
  } catch (error) {
    console.error('图片上传失败:', error);
    displayMessage(`图片上传失败: ${error.message}`, 'error');
  } finally {
    isUploadingPhoto.value = false;
    // 清空文件输入，允许重新选择同一文件
    if (photoInput.value) {
      photoInput.value.value = '';
    }
  }
};

const triggerAudioUpload = () => {
  if (isUploadingAudio.value) {
    displayMessage('正在上传音频，请稍候...', 'error');
    return;
  }
  audioInput.value?.click();
};

const handleAudioUpload = async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  
  // 验证文件类型
  if (!file.type.startsWith('audio/')) {
    displayMessage('请选择音频文件', 'error');
    return;
  }
  
  // 验证文件大小（最大 50MB）
  if (file.size > 50 * 1024 * 1024) {
    displayMessage('音频文件大小不能超过 50MB', 'error');
    return;
  }
  
  isUploadingAudio.value = true;
  
  try {
    const formData = new FormData();
    formData.append('audio', file);
    
    console.log('正在上传音频:', file.name);
    
    const response = await fetch(buildApiUrl('/api/upload/audio'), {
      method: 'POST',
      body: formData
    });

    const result = await parseJsonResponse(response, '音频上传');
    console.log('上传响应:', result);
    
    if (result.code !== 0) {
      // 显示警告信息（如果有）
      const warnings = normalizeWarnings(result.data?.warnings);
      if (warnings.length > 0) {
        console.warn('音频验证警告:', warnings.join('\n'));
      }
      throw new Error(result.msg || '上传失败');
    }
    
    // 显示验证警告（如果有）
    const warnings = normalizeWarnings(result.data?.warnings);
    if (warnings.length > 0) {
      displayMessage(`音频上传成功，建议: ${warnings.join(', ')}`, 'success');
    } else {
      displayMessage('音频上传成功！', 'success');
    }
    
    const audioPath = result.data?.audio_path;
    if (!audioPath) {
      throw new Error('后端未返回 audio_path');
    }
    console.log('音频上传成功，audio_path:', audioPath);
    
    // 自动进行音色克隆
    await cloneVoice(audioPath);
    
  } catch (error) {
    console.error('音频上传失败:', error);
    displayMessage(`音频上传失败: ${error.message}`, 'error');
  } finally {
    isUploadingAudio.value = false;
    // 清空文件输入
    if (audioInput.value) {
      audioInput.value.value = '';
    }
  }
};

// 🆕 音色克隆功能（自动使用默认名称）
const cloneVoice = async (audioPath) => {
  try {
    // 使用时间戳生成默认名称
    const timestamp = new Date().toLocaleString('zh-CN', { 
      month: '2-digit', 
      day: '2-digit', 
      hour: '2-digit', 
      minute: '2-digit' 
    }).replace(/\//g, '-').replace(/:/g, '-').replace(/\s/g, '_');
    const voiceName = `克隆音色_${timestamp}`;
    
    console.log('正在克隆音色:', audioPath, '名称:', voiceName);
    
    const response = await fetch(buildApiUrl('/api/voices/clone'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        audio_path: audioPath,
        voice_name: voiceName,
        voice_description: '用户上传的克隆音色'
      })
    });

    const result = await parseJsonResponse(response, '音色克隆');
    console.log('克隆响应:', result);
    
    if (result.code !== 0) {
      throw new Error(result.msg || '克隆失败');
    }
    
    displayMessage('音色克隆成功！', 'success');
    
    // 重新加载音色列表
    await loadVoices();
    
    // 自动选中新克隆的音色
    const newVoiceId = result.data?.voice?.voice_id || result.data?.voice_id;
    if (newVoiceId) {
      selectedVoice.value = newVoiceId;
    }
    persistAvatarPageState();
    
  } catch (error) {
    console.error('音色克隆失败:', error);
    displayMessage(`音色克隆失败: ${error.message}`, 'error');
  }
};

const toggleRecordVoice = async () => {
  if (isRecordingVoice.value) {
    // 停止录音
    isRecordingVoice.value = false;
    console.log('录音已停止');
  } else {
    // 开始录音
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      isRecordingVoice.value = true;
      selectedVoice.value = 'record';
      persistAvatarPageState();
      console.log('开始录音');
      // 这里可以添加录音处理逻辑
      // 简化流程：3秒后自动停止
      setTimeout(() => {
        if (isRecordingVoice.value) {
          isRecordingVoice.value = false;
          stream.getTracks().forEach(track => track.stop());
        }
      }, 3000);
    } catch (error) {
      console.error('无法访问麦克风:', error);
      displayMessage('无法访问麦克风，请检查权限设置', 'error');
    }
  }
};

const handleAvatarImageError = (avatarId) => {
  imageAvailability.value = {
    ...imageAvailability.value,
    [avatarId]: false,
  };
};

const generateVideo = async () => {
  if (!canGenerate.value || isGenerating.value) return;

  isGenerating.value = true;
  revokeObjectUrl(videoUrl.value);
  videoUrl.value = '';
  await removePersistentValue(AVATAR_VIDEO_BLOB_KEY);

  try {
    const response = await fetch(buildApiUrl('/api/generate/video'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        avatar_id: selectedAvatar.value,
        voice_id: selectedVoice.value,
        text: inputText.value.trim()
      })
    });

    const contentType = String(response.headers.get('content-type') || '').toLowerCase();

    if (!response.ok) {
      if (contentType.includes('application/json')) {
        const errorPayload = await response.json();
        throw new Error(errorPayload.msg || `HTTP ${response.status}: ${response.statusText}`);
      }
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    if (contentType.includes('video/')) {
      const blob = await response.blob();
      videoUrl.value = URL.createObjectURL(blob);
      await savePersistentValue(AVATAR_VIDEO_BLOB_KEY, blob);
      persistAvatarPageState();
      displayMessage('数字人视频生成成功！', 'success');
      return;
    }

    if (contentType.includes('application/json')) {
      const payload = await response.json();
      const backendMessage =
        payload?.data?.note ||
        payload?.msg ||
        '后端暂未返回可播放的视频文件。';
      throw new Error(backendMessage);
    }

    throw new Error(`后端返回了无法识别的内容类型: ${contentType || 'unknown'}`);
  } catch (error) {
    console.error('生成数字人视频失败:', error);
    displayMessage(`生成失败: ${getApiFetchErrorMessage(error)}`, 'error');
  } finally {
    isGenerating.value = false;
  }
};

const downloadVideo = () => {
  if (!videoUrl.value) return;
  
  const link = document.createElement('a');
  link.href = videoUrl.value;
  link.download = `avatar-video-${Date.now()}.mp4`;
  link.click();
};

const resetGeneration = () => {
  revokeObjectUrl(videoUrl.value);
  videoUrl.value = '';
  inputText.value = '';
  void removePersistentValue(AVATAR_VIDEO_BLOB_KEY);
  persistAvatarPageState();
};

watch(
  [selectedAvatar, selectedVoice, inputText, customPhoto, customAvatarId, suggestionText],
  () => {
    persistAvatarPageState();
  }
);

onMounted(async () => {
  restoreAvatarPageState();

  // 从路由参数或 localStorage 获取建议文本
  const suggestion = route.query.suggestion || localStorage.getItem('avatarSuggestion') || '';
  if (suggestion) {
    suggestionText.value = suggestion;
    localStorage.removeItem('avatarSuggestion'); // 清除已使用的建议
    persistAvatarPageState();
  }
  
  // 🆕 加载形象和音色列表
  await loadVoicePreviews();
  await Promise.all([loadAvatars(), loadVoices(), restoreGeneratedMedia()]);
});

onUnmounted(() => {
  stopVoicePreview();
  revokeObjectUrl(videoUrl.value);
});
</script>

<style scoped>
@import '../assets/avatar-theme.css';

.avatar-customization {
  width: 100%;
  height: 100%;
  padding: 16px;
  overflow: hidden;
  position: relative;
  background: transparent;
}

/* 🆕 消息提示样式 */
.message-toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  min-width: 320px;
  max-width: 500px;
  padding: 14px 18px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(10px);
  animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}

.message-fade-enter-active,
.message-fade-leave-active {
  transition: all 0.3s ease;
}

.message-fade-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(-20px);
}

.message-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-20px);
}

.message-error {
  background: rgba(239, 68, 68, 0.95);
  border: 1px solid rgba(239, 68, 68, 0.5);
}

.message-success {
  background: rgba(34, 197, 94, 0.95);
  border: 1px solid rgba(34, 197, 94, 0.5);
}

/* 日间主题下的消息样式 */
[data-theme="day"] .message-error {
  background: rgba(239, 68, 68, 0.98);
  border: 2px solid rgba(239, 68, 68, 0.6);
  box-shadow: 0 8px 24px rgba(239, 68, 68, 0.3);
}

[data-theme="day"] .message-success {
  background: rgba(34, 197, 94, 0.98);
  border: 2px solid rgba(34, 197, 94, 0.6);
  box-shadow: 0 8px 24px rgba(34, 197, 94, 0.3);
}

.message-content {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  color: #fff;
}

.message-content i {
  font-size: 1.2rem;
  flex-shrink: 0;
}

.message-content span {
  font-size: 0.9rem;
  font-weight: 500;
  line-height: 1.4;
}

.message-close {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  border-radius: 6px;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.message-close:hover {
  background: rgba(255, 255, 255, 0.3);
}

.message-close i {
  color: #fff;
  font-size: 1rem;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

/* 配置面板 */
.config-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 0;
  overflow-y: hidden;
  overflow-x: hidden;
}

.panel-section {
  background: rgba(18, 14, 30, 0.6);
  border: 1px solid rgba(255, 107, 129, 0.2);
  border-radius: 12px;
  padding: 12px;
  backdrop-filter: blur(10px);
  flex-shrink: 0;
}

/* 🆕 为形象和音色面板设置固定高度 */
.panel-section:nth-child(1) {
  height: 230px;
  display: flex;
  flex-direction: column;
}

.panel-section:nth-child(2) {
  height: 240px;
  display: flex;
  flex-direction: column;
}

.panel-section:nth-child(1) > *:not(.section-title),
.panel-section:nth-child(2) > *:not(.section-title) {
  flex: 1;
  min-height: 0;
}

.section-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #f1f5f9;
  margin: 0 0 10px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.section-title i {
  color: #ff6b81;
  font-size: 0.9rem;
}

.text-stats-inline {
  margin-left: auto;
  font-size: 0.75rem;
  color: #94a3b8;
  font-weight: 400;
}

/* 🆕 横向滚动容器 */
.avatar-scroll-container {
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 8px;
  flex: 1;
  min-height: 0;
}

/* 音色容器改为两行网格布局 */
.voice-scroll-container {
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
  flex: 1;
  min-height: 0;
}

/* 美化滚动条 - 横向和纵向 */
.avatar-scroll-container::-webkit-scrollbar {
  height: 6px;
  width: 6px;
}

.voice-scroll-container::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.avatar-scroll-container::-webkit-scrollbar-track,
.voice-scroll-container::-webkit-scrollbar-track {
  background: var(--theme-scrollbar-track);
  border-radius: 10px;
  margin: 4px;
  transition: background 0.3s ease;
}

.avatar-scroll-container::-webkit-scrollbar-thumb,
.voice-scroll-container::-webkit-scrollbar-thumb {
  background: linear-gradient(135deg, var(--theme-scrollbar-thumb-start), var(--theme-scrollbar-thumb-end));
  border-radius: 10px;
  transition: all 0.3s ease;
}

.avatar-scroll-container::-webkit-scrollbar-thumb:hover,
.voice-scroll-container::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(135deg, var(--theme-scrollbar-thumb-hover-start), var(--theme-scrollbar-thumb-hover-end));
  box-shadow: 0 0 6px var(--theme-primary);
}

.avatar-grid {
  display: flex;
  gap: 10px;
  min-width: min-content;
}

.avatar-card {
  flex: 0 0 auto;
  width: 120px;
  background: rgba(255, 255, 255, 0.02);
  border: 2px solid rgba(255, 107, 129, 0.2);
  border-radius: 10px;
  padding: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.upload-card {
  border-style: dashed;
}

.upload-preview {
  background: var(--theme-gradient-1) !important;
  transition: background 0.3s ease;
}

.upload-preview .avatar-fallback i {
  font-size: 2rem;
  color: var(--theme-primary);
  transition: color 0.3s ease;
}

.upload-preview .avatar-fallback span {
  font-size: 0.8rem;
  color: var(--theme-primary);
  transition: color 0.3s ease;
}

.avatar-card:hover {
  border-color: rgba(255, 107, 129, 0.4);
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(255, 107, 129, 0.2);
}

.avatar-card.selected {
  border-color: #ff6b81;
  background: rgba(255, 107, 129, 0.1);
  box-shadow: 0 6px 20px rgba(255, 107, 129, 0.3);
}

.avatar-preview {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 6px;
  background:
    radial-gradient(circle at 20% 18%, var(--avatar-accent-soft), transparent 52%),
    linear-gradient(160deg, rgba(15, 12, 26, 0.92), rgba(34, 18, 32, 0.88));
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.avatar-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #f8fafc;
  text-align: center;
  padding: 20px;
}

.avatar-fallback i {
  font-size: 1.8rem;
  color: var(--avatar-accent);
  text-shadow: 0 0 20px var(--avatar-accent-soft);
}

.avatar-fallback span {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.avatar-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.avatar-card.selected .avatar-overlay {
  opacity: 1;
}

.avatar-overlay i {
  font-size: 32px;
  color: #ff6b81;
}

.avatar-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.avatar-name {
  font-size: 0.8rem;
  font-weight: 600;
  color: #f1f5f9;
}

.avatar-desc {
  font-size: 0.7rem;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.voice-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.voice-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.02);
  border: 2px solid rgba(255, 107, 129, 0.2);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
}

.upload-voice,
.record-voice {
  border-style: dashed;
}

.record-voice.recording {
  animation: pulse-recording 1.5s ease-in-out infinite;
  border-color: var(--theme-primary);
}

@keyframes pulse-recording {
  0%, 100% {
    box-shadow: 0 0 0 0 var(--theme-primary);
  }
  50% {
    box-shadow: 0 0 0 10px transparent;
  }
}

.voice-card:hover {
  border-color: rgba(255, 107, 129, 0.4);
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(255, 107, 129, 0.2);
}

.voice-card.selected {
  border-color: #ff6b81;
  background: rgba(255, 107, 129, 0.1);
  box-shadow: 0 6px 20px rgba(255, 107, 129, 0.3);
}

.voice-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(255, 107, 129, 0.2), rgba(236, 72, 153, 0.2));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.voice-icon i {
  font-size: 16px;
  color: #ff6b81;
}

.voice-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.voice-name {
  font-size: 0.8rem;
  font-weight: 600;
  color: #f1f5f9;
}

.voice-desc {
  font-size: 0.7rem;
  color: #94a3b8;
}

.voice-check {
  opacity: 0;
  transition: opacity 0.3s ease;
}

.voice-preview-btn {
  width: 28px;
  height: 28px;
  border: 1px solid rgba(255, 107, 129, 0.28);
  border-radius: 8px;
  background: rgba(255, 107, 129, 0.1);
  color: #ff6b81;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.voice-preview-btn:hover {
  background: rgba(255, 107, 129, 0.2);
  border-color: rgba(255, 107, 129, 0.55);
  transform: translateY(-1px);
}

.voice-preview-btn i {
  font-size: 16px;
}

.voice-preview-loading,
.voice-preview-placeholder {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}

.voice-preview-loading {
  border: 1px solid rgba(255, 107, 129, 0.18);
  border-radius: 8px;
  background: rgba(255, 107, 129, 0.06);
  display: flex;
  align-items: center;
  justify-content: center;
}

.voice-preview-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 107, 129, 0.18);
  border-top-color: #ff6b81;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.voice-card.selected .voice-check {
  opacity: 1;
}

.voice-check i {
  font-size: 16px;
  color: #ff6b81;
}

.text-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.btn-use-suggestion {
  padding: 6px 12px;
  background: rgba(255, 107, 129, 0.15);
  border: 1px solid rgba(255, 107, 129, 0.3);
  border-radius: 8px;
  color: #ff6b81;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.3s ease;
}

.btn-use-suggestion:hover {
  background: rgba(255, 107, 129, 0.25);
  border-color: #ff6b81;
  transform: translateY(-1px);
}

.btn-use-suggestion i {
  font-size: 14px;
}

.text-input {
  width: 100%;
  padding: 10px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 107, 129, 0.2);
  border-radius: 8px;
  color: #e2e8f0;
  font-size: 0.85rem;
  line-height: 1.5;
  resize: none;
  font-family: inherit;
}

.text-input:focus {
  outline: none;
  border-color: #ff6b81;
  box-shadow: 0 0 0 3px rgba(255, 107, 129, 0.1);
}

.text-section {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}

.text-section .text-input {
  flex-grow: 1;
  min-height: 60px;
}

.button-section {
  padding: 10px 12px;
}

.btn-generate {
  width: 100%;
  padding: 12px;
  background: linear-gradient(135deg, #ff6b81 0%, #ec4899 100%);
  border: none;
  border-radius: 10px;
  color: #fff;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.3s ease;
  box-shadow: 0 4px 16px rgba(255, 107, 129, 0.3);
}

.btn-generate:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(255, 107, 129, 0.5);
}

.btn-generate:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

/* 预览面板 */
.preview-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.status-badge {
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}

.status-idle {
  background: rgba(148, 163, 184, 0.2);
  color: #94a3b8;
}

.status-generating {
  background: rgba(255, 107, 129, 0.2);
  color: #ff6b81;
  animation: pulse 2s ease-in-out infinite;
}

.status-ready {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
}

.video-container {
  flex: 1;
  width: 100%;
  min-width: 0;
  min-height: 0;
  max-height: 100%;
  background: var(--theme-bg-input);
  border: 1px solid var(--theme-border);
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
  position: relative;
  transition: background 0.3s ease, border-color 0.3s ease;
}

.placeholder {
  text-align: center;
  padding: 40px;
}

.placeholder-icon {
  font-size: 64px;
  color: rgba(255, 107, 129, 0.3);
  margin-bottom: 16px;
}

.placeholder-text {
  font-size: 0.9rem;
  color: #94a3b8;
}

.generating-state {
  text-align: center;
  padding: 40px;
}

.spinner {
  width: 48px;
  height: 48px;
  margin: 0 auto 16px;
  border: 4px solid rgba(255, 107, 129, 0.2);
  border-top-color: #ff6b81;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.spinner-small {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255, 107, 129, 0.2);
  border-top-color: #ff6b81;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  display: inline-block;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  color: #94a3b8;
  font-size: 0.85rem;
  height: 100%;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 20px;
  color: #94a3b8;
  font-size: 0.85rem;
  height: 100%;
}

.empty-state i {
  font-size: 2rem;
  color: rgba(255, 107, 129, 0.5);
}

.btn-retry {
  margin-top: 8px;
  padding: 6px 12px;
  background: rgba(255, 107, 129, 0.15);
  border: 1px solid rgba(255, 107, 129, 0.3);
  border-radius: 8px;
  color: #ff6b81;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.3s ease;
}

.btn-retry:hover {
  background: rgba(255, 107, 129, 0.25);
  border-color: #ff6b81;
}

.generating-text {
  font-size: 1rem;
  font-weight: 600;
  color: #f1f5f9;
  margin: 0 0 8px 0;
}

.generating-hint {
  font-size: 0.85rem;
  color: #94a3b8;
  margin: 0;
}

.video-stage {
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  cursor: pointer;
  background: #0f172a;
  outline: none;
  touch-action: manipulation;
}

.video-stage:focus-visible {
  box-shadow: inset 0 0 0 3px var(--theme-primary);
}

.video-player {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  display: block;
  background: transparent;
}

.video-actions {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
}

.btn-action {
  flex: 1;
  padding: 12px;
  background: linear-gradient(135deg, #ff6b81 0%, #ec4899 100%);
  border: none;
  border-radius: 10px;
  color: #fff;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.3s ease;
}

.btn-action:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(255, 107, 129, 0.4);
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 107, 129, 0.3);
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.15);
}

@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }

  .preview-panel {
    min-height: 420px;
  }
  
  .avatar-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .voice-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
