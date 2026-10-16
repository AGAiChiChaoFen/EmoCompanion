// 当前 RTCPeerConnection 实例（全局单例）。
var pc = null;

// 浏览器与连接策略常量：
// - Edge 在部分网络环境下 ICE 需要更宽松的超时
// - FORCE_RELAY_ONLY=true 表示优先强制走 TURN relay
// - 默认不内置 TURN，依赖后端 /rtc_config 下发
const IS_EDGE = typeof navigator !== 'undefined' && /Edg\/\d+/i.test(navigator.userAgent || '');
const FORCE_RELAY_ONLY = true;
const DEFAULT_TURN_SERVERS = [];

// Vue 启动时注入 src/utils/api.js 的统一地址构造器。
const buildApiUrl = (path) => {
    const sharedBuilder = window.__APP_BUILD_API_URL__;
    return typeof sharedBuilder === 'function' ? sharedBuilder(path) : path;
};
const ATTEMPT_TIMEOUT_MS = IS_EDGE ? 60000 : 45000;
const DISCONNECTED_GRACE_MS = 5000;
const MAX_OFFER_ICE_WAIT_MS = IS_EDGE ? 3200 : 1800;
const OFFER_REQUEST_TIMEOUT_MS = IS_EDGE ? 120000 : 90000;
const REMOTE_PLAYOUT_DELAY_HINT_S = 4.0;

// 连接流程与上行媒体状态。
let isConnecting = false;
let hasConnectedOnce = false;
let currentProfileName = '';
let publishStream = null;
let publishStreamOwnedByClient = false;
let disconnectedNotifyTimer = null;
let publishConfig = {
    audio: false,
    video: false,
    audioActive: false,
};

// 检测当前环境是否可用 getUserMedia，并返回可读的错误提示。
function buildGetUserMediaUnavailableMessage() {
    const hasNavigator = typeof navigator !== 'undefined';
    const hasMediaDevices = hasNavigator && !!navigator.mediaDevices;
    const hasGetUserMedia = hasMediaDevices && typeof navigator.mediaDevices.getUserMedia === 'function';

    if (hasGetUserMedia) {
        return '';
    }

    if (typeof window !== 'undefined' && window.isSecureContext === false) {
        return '当前页面不是安全上下文（HTTP），浏览器已禁用麦克风接口。请改用 HTTPS 或 localhost 访问。';
    }

    return '当前浏览器环境不支持 mediaDevices.getUserMedia，请检查浏览器版本或权限策略。';
}

// 清理“断线延迟通知”定时器，防止重复触发断开回调。
function clearDisconnectedNotifyTimer() {
    if (!disconnectedNotifyTimer) {
        return;
    }
    clearTimeout(disconnectedNotifyTimer);
    disconnectedNotifyTimer = null;
}

function applyReceiverPlayoutDelay(receiver, kind) {
    if (!receiver || !('playoutDelayHint' in receiver)) {
        return;
    }

    try {
        receiver.playoutDelayHint = REMOTE_PLAYOUT_DELAY_HINT_S;
        console.log('[webrtc] remote', kind, 'playoutDelayHint=', REMOTE_PLAYOUT_DELAY_HINT_S);
    } catch (e) {
        console.warn('[webrtc] failed to set', kind, 'playoutDelayHint:', e);
    }
}

// 规范化上行媒体配置：统一布尔值并补齐 audioActive 默认值。
function normalizePublishConfig(config) {
    const cfg = config || {};
    return {
        audio: !!cfg.audio,
        video: !!cfg.video,
        audioActive: cfg.audioActive === undefined ? !!cfg.audio : !!cfg.audioActive,
    };
}

// 把 publishConfig 实际下发到本地 MediaStream 的音视频轨 enabled 状态。
function applyPublishTrackState() {
    if (!publishStream) {
        return;
    }

    const enableAudio = !!publishConfig.audio && !!publishConfig.audioActive;
    const enableVideo = !!publishConfig.video;

    for (const track of publishStream.getAudioTracks()) {
        track.enabled = enableAudio;
    }
    for (const track of publishStream.getVideoTracks()) {
        track.enabled = enableVideo;
    }
}

// 对外暴露：仅更新发布配置，不替换已有 stream。
window.configurePublishMedia = function configurePublishMedia(config) {
    publishConfig = normalizePublishConfig(config);
    applyPublishTrackState();
    console.log('[webrtc] publishConfig=', publishConfig);
};

function setCallControlVisibility(isCallActive) {
    const startButton = document.getElementById('start');
    const stopButton = document.getElementById('stop');

    if (startButton) {
        startButton.style.display = isCallActive ? 'none' : 'inline-block';
    }
    if (stopButton) {
        stopButton.style.display = isCallActive ? 'inline-block' : 'none';
    }
}

// 对外暴露：设置外部创建的发布流（通常来自 Vue 侧本地采集）。
window.setPublishStream = function setPublishStream(stream, config) {
    publishStream = stream || null;
    publishStreamOwnedByClient = false;
    if (config) {
        publishConfig = normalizePublishConfig(config);
    }
    applyPublishTrackState();
    console.log('[webrtc] setPublishStream=', !!publishStream, publishConfig);
};

// 对外暴露：清理发布流（可选是否同时 stop 轨道）。
window.clearPublishStream = function clearPublishStream(stopTracks) {
    if (stopTracks && publishStream) {
        for (const track of publishStream.getTracks()) {
            track.stop();
        }
    }
    publishStream = null;
    publishStreamOwnedByClient = false;
    publishConfig = {
        audio: false,
        video: false,
        audioActive: false,
    };
    console.log('[webrtc] publish stream cleared');
};

// 释放“由 client.js 自己申请”的发布流，避免在外部注入流场景误关用户轨道。
function releaseManagedPublishStream() {
    if (!publishStreamOwnedByClient || !publishStream) {
        return;
    }
    for (const track of publishStream.getTracks()) {
        track.stop();
    }
    publishStream = null;
    publishStreamOwnedByClient = false;
}

// 如果当前配置需要上行音视频，则把对应轨道 attach 到 PC。
// 当未提供外部 publishStream 时，会在此函数内申请本地设备。
async function attachPublishTracksIfNeeded() {
    const wantAudio = !!publishConfig.audio;
    const wantVideo = !!publishConfig.video;

    if (!wantAudio && !wantVideo) {
        return;
    }

    let stream = publishStream;
    if (!stream) {
        const mediaError = buildGetUserMediaUnavailableMessage();
        if (mediaError) {
            throw new Error(mediaError);
        }

        const audioConstraints = wantAudio
            ? {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                channelCount: 1,
            }
            : false;

        stream = await navigator.mediaDevices.getUserMedia({
            audio: audioConstraints,
            video: wantVideo,
        });
        publishStream = stream;
        publishStreamOwnedByClient = true;
        window.dispatchEvent(new CustomEvent('webrtc-local-publish-created', { detail: { stream } }));
    }

    applyPublishTrackState();

    const tracks = [];
    if (wantAudio) {
        const audioTrack = stream.getAudioTracks()[0];
        if (audioTrack) {
            tracks.push(audioTrack);
        }
    }
    if (wantVideo) {
        const videoTrack = stream.getVideoTracks()[0];
        if (videoTrack) {
            tracks.push(videoTrack);
        }
    }

    for (const track of tracks) {
        pc.addTrack(track, stream);
    }

    applyPublishTrackState();

    console.log('[webrtc] publish tracks attached:', tracks.map((t) => t.kind));
}

async function loadRtcConfig() {
    // 从后端拉取 ICE 配置；失败时退回本地默认策略。
    try {
        const response = await fetch(buildApiUrl('/rtc_config'), { cache: 'no-store' });
        if (!response.ok) {
            throw new Error('rtc_config status=' + response.status);
        }
        const data = await response.json();
        return {
            iceServers: Array.isArray(data.iceServers) ? data.iceServers : DEFAULT_TURN_SERVERS.slice(),
            iceTransportPolicy: data.iceTransportPolicy || (FORCE_RELAY_ONLY ? 'relay' : undefined),
        };
    } catch (e) {
        console.warn('[webrtc] failed to fetch /rtc_config, fallback to local default', e);
        return {
            iceServers: DEFAULT_TURN_SERVERS.slice(),
            iceTransportPolicy: FORCE_RELAY_ONLY ? 'relay' : undefined,
        };
    }
}

// 兼容 urls 既可能是字符串也可能是数组的情况。
function toUrlArray(urls) {
    if (Array.isArray(urls)) {
        return urls.slice();
    }
    if (typeof urls === 'string' && urls) {
        return [urls];
    }
    return [];
}

// 按 transport 过滤 TURN URL：
// - udp: turn:...transport=udp
// - tcp: turn:...transport=tcp 或 turns:
function splitIceServersByTransport(iceServers, targetTransport) {
    const out = [];

    for (const s of iceServers || []) {
        const urls = toUrlArray(s.urls);
        const turnUrls = urls.filter((u) => typeof u === 'string' && (u.startsWith('turn:') || u.startsWith('turns:')));
        const nonTurnUrls = urls.filter((u) => typeof u === 'string' && !(u.startsWith('turn:') || u.startsWith('turns:')));

        if (nonTurnUrls.length > 0) {
            out.push(Object.assign({}, s, { urls: nonTurnUrls.length === 1 ? nonTurnUrls[0] : nonTurnUrls }));
        }

        if (turnUrls.length > 0) {
            const filtered = turnUrls.filter((u) => {
                if (targetTransport === 'udp') {
                    return u.startsWith('turn:') && u.includes('transport=udp');
                }
                if (targetTransport === 'tcp') {
                    return (u.startsWith('turn:') && u.includes('transport=tcp')) || u.startsWith('turns:');
                }
                return true;
            });

            if (filtered.length > 0) {
                out.push(Object.assign({}, s, { urls: filtered.length === 1 ? filtered[0] : filtered }));
            }
        }
    }

    return out;
}

function hasTurnIceServer(iceServers) {
    return (iceServers || []).some((server) =>
        toUrlArray(server && server.urls).some((url) =>
            typeof url === 'string' && (url.startsWith('turn:') || url.startsWith('turns:'))
        )
    );
}

// 去重插入 profile，避免不同分支生成重复配置。
function pushProfileUnique(profiles, profile) {
    const key = JSON.stringify({
        iceTransportPolicy: profile.iceTransportPolicy || '',
        iceServers: profile.iceServers || [],
    });
    if (!profiles.some((p) => p._key === key)) {
        profile._key = key;
        profiles.push(profile);
    }
}

// 生成“候选连接配置列表”：
// primary -> relay-udp-only / relay-tcp-only -> all-fallback。
function buildIceProfiles(rtcConfig) {
    const profiles = [];
    const basePolicy = rtcConfig.iceTransportPolicy || (FORCE_RELAY_ONLY ? 'relay' : undefined);
    const baseServers = Array.isArray(rtcConfig.iceServers) ? rtcConfig.iceServers : [];

    const tcpOnlyServers = splitIceServersByTransport(baseServers, 'tcp');
    const udpOnlyServers = splitIceServersByTransport(baseServers, 'udp');

    // 在 relay 场景优先尝试单一 transport，避免 mixed turn urls 在受限网络中长时间探测。
    if (basePolicy === 'relay') {
        if (IS_EDGE) {
            if (udpOnlyServers.length > 0) {
                pushProfileUnique(profiles, {
                    name: 'relay-udp-only',
                    iceTransportPolicy: 'relay',
                    iceServers: udpOnlyServers,
                });
            }
            if (tcpOnlyServers.length > 0) {
                pushProfileUnique(profiles, {
                    name: 'relay-tcp-only',
                    iceTransportPolicy: 'relay',
                    iceServers: tcpOnlyServers,
                });
            }
        } else {
            if (tcpOnlyServers.length > 0) {
                pushProfileUnique(profiles, {
                    name: 'relay-tcp-only',
                    iceTransportPolicy: 'relay',
                    iceServers: tcpOnlyServers,
                });
            }
            if (udpOnlyServers.length > 0) {
                pushProfileUnique(profiles, {
                    name: 'relay-udp-only',
                    iceTransportPolicy: 'relay',
                    iceServers: udpOnlyServers,
                });
            }
        }
    }

    pushProfileUnique(profiles, {
        name: 'primary',
        iceTransportPolicy: basePolicy,
        iceServers: baseServers,
    });

    if (basePolicy === 'relay') {
        pushProfileUnique(profiles, {
            name: 'all-fallback',
            iceTransportPolicy: 'all',
            iceServers: baseServers,
        });
    }

    return profiles;
}

// 立即关闭现有 PC，并释放受管发布流。
function closePeerConnectionNow() {
    clearDisconnectedNotifyTimer();
    if (pc) {
        try {
            pc.close();
        } catch (e) {
            console.warn('[webrtc] close pc failed:', e);
        }
    }
    pc = null;
    releaseManagedPublishStream();
}

// 按 profile 创建并初始化 RTCPeerConnection，注册关键事件监听。
function setupPeerConnection(config, profileName) {
    closePeerConnectionNow();
    currentProfileName = profileName;
    hasConnectedOnce = false;

    pc = new RTCPeerConnection(config);
    const currentPc = pc;
    console.log('[webrtc] profile=', profileName, 'config=', config);

    pc.addEventListener('connectionstatechange', () => {
        console.log('[webrtc] profile=', currentProfileName, 'connectionState=', pc.connectionState);
        if (pc.connectionState === 'connected') {
            clearDisconnectedNotifyTimer();
            if (!hasConnectedOnce) {
                hasConnectedOnce = true;
                if (typeof window.onWebRTCConnected === 'function') {
                    window.onWebRTCConnected();
                }
            }
            return;
        }
        if ((pc.connectionState === 'failed' || pc.connectionState === 'closed')
            && typeof window.onWebRTCDisconnected === 'function') {
            clearDisconnectedNotifyTimer();
            window.onWebRTCDisconnected();
            return;
        }
        if (pc.connectionState === 'disconnected') {
            clearDisconnectedNotifyTimer();
            disconnectedNotifyTimer = setTimeout(() => {
                if (pc !== currentPc || !pc) {
                    return;
                }
                if (pc.connectionState === 'disconnected' && typeof window.onWebRTCDisconnected === 'function') {
                    window.onWebRTCDisconnected();
                }
            }, DISCONNECTED_GRACE_MS);
            return;
        }
        clearDisconnectedNotifyTimer();
    });

    pc.addEventListener('iceconnectionstatechange', () => {
        console.log('[webrtc] profile=', currentProfileName, 'iceConnectionState=', pc.iceConnectionState);
    });

    pc.addEventListener('icegatheringstatechange', () => {
        console.log('[webrtc] profile=', currentProfileName, 'iceGatheringState=', pc.iceGatheringState);
    });

    pc.addEventListener('icecandidate', (evt) => {
        if (!evt.candidate) {
            console.log('[webrtc] profile=', currentProfileName, 'candidate gathering finished');
            return;
        }
        const c = evt.candidate.candidate || '';
        if (c.includes(' typ relay ')) {
            console.log('[webrtc] profile=', currentProfileName, 'relay candidate found:', c);
        } else {
            console.log('[webrtc] profile=', currentProfileName, 'candidate:', c);
        }

        // Send ICE candidate to backend for trickle ICE support
        const sessionEl = document.getElementById('sessionid');
        const sessionid = sessionEl ? sessionEl.value : '';
        if (sessionid && evt.candidate) {
            console.log('[webrtc] sending candidate to backend, sessionid=', sessionid);
            const candidateData = {
                candidate: evt.candidate.candidate,
                sdpMid: evt.candidate.sdpMid,
                sdpMLineIndex: evt.candidate.sdpMLineIndex
            };
            fetch(buildApiUrl('/candidate'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    candidate: candidateData,
                    sessionid: parseInt(sessionid, 10)
                })
            }).then(response => {
                if (response.ok) {
                    console.log('[webrtc] candidate sent successfully');
                } else {
                    console.warn('[webrtc] failed to send candidate to backend, status=', response.status);
                }
            }).catch(err => {
                console.warn('[webrtc] error sending candidate to backend:', err.message);
            });
        } else {
            if (!sessionid) {
                console.warn('[webrtc] cannot send candidate: sessionid not available yet');
            }
        }
    });

    pc.addEventListener('icecandidateerror', (evt) => {
        console.error('[webrtc] profile=', currentProfileName, 'icecandidateerror', {
            url: evt.url,
            errorCode: evt.errorCode,
            errorText: evt.errorText,
            hostCandidate: evt.hostCandidate,
        });
    });

    pc.addEventListener('track', (evt) => {
        applyReceiverPlayoutDelay(evt.receiver, evt.track.kind);

        if (evt.track.kind === 'video') {
            const videoEl = document.getElementById('video');
            if (videoEl) {
                videoEl.srcObject = evt.streams[0];
                const playPromise = videoEl.play();
                if (playPromise && typeof playPromise.catch === 'function') {
                    playPromise.catch((e) => console.warn('[webrtc] video autoplay blocked:', e));
                }
            }
        } else {
            var audioEl = document.getElementById('audio');
            if (audioEl) {
                audioEl.srcObject = evt.streams[0];
                const playPromise = audioEl.play();
                if (playPromise && typeof playPromise.catch === 'function') {
                    playPromise.catch((e) => console.warn('[webrtc] audio autoplay blocked:', e));
                }
            }
        }
    });
}

function waitForConnectionResult(timeoutMs) {
    // 监听 connectionState / iceConnectionState，直到成功、失败或超时。
    return new Promise((resolve, reject) => {
        let done = false;
        let disconnectedTimer = null;

        const clearDisconnectedTimer = () => {
            if (!disconnectedTimer) {
                return;
            }
            clearTimeout(disconnectedTimer);
            disconnectedTimer = null;
        };

        const finish = (ok, reason) => {
            if (done) {
                return;
            }
            done = true;
            clearTimeout(timer);
            clearDisconnectedTimer();
            if (pc) {
                pc.removeEventListener('connectionstatechange', onState);
                pc.removeEventListener('iceconnectionstatechange', onState);
            }
            if (ok) {
                resolve(reason);
            } else {
                reject(new Error(reason));
            }
        };

        const onState = () => {
            if (!pc) {
                finish(false, 'pc_closed');
                return;
            }
            const connectionState = pc.connectionState;
            const iceState = pc.iceConnectionState;

            if (connectionState === 'connected' || iceState === 'connected' || iceState === 'completed') {
                clearDisconnectedTimer();
                finish(true, connectionState === 'connected' ? 'connected' : `ice_${iceState}`);
                return;
            }

            if (
                connectionState === 'failed'
                || connectionState === 'closed'
                || iceState === 'failed'
                || iceState === 'closed'
            ) {
                clearDisconnectedTimer();
                finish(false, connectionState === 'failed' || connectionState === 'closed' ? connectionState : `ice_${iceState}`);
                return;
            }

            if (connectionState === 'disconnected' || iceState === 'disconnected') {
                if (!disconnectedTimer) {
                    disconnectedTimer = setTimeout(() => {
                        if (!pc) {
                            return;
                        }
                        if (pc.connectionState === 'disconnected' || pc.iceConnectionState === 'disconnected') {
                            finish(false, 'disconnected_timeout');
                        }
                    }, DISCONNECTED_GRACE_MS);
                }
                return;
            }

            clearDisconnectedTimer();
        };

        const timer = setTimeout(() => {
            finish(false, 'connect_timeout');
        }, timeoutMs);

        if (!pc) {
            finish(false, 'pc_null');
            return;
        }
        pc.addEventListener('connectionstatechange', onState);
        pc.addEventListener('iceconnectionstatechange', onState);
        onState();
    });
}

// 判断本地 SDP 是否已经出现候选，作为提前发送 offer 的依据。
function hasLocalCandidatesInDescription() {
    if (!pc || !pc.localDescription || !pc.localDescription.sdp) {
        return false;
    }
    return pc.localDescription.sdp.includes('a=candidate:');
}

// 等待 ICE 收集到候选（或达到超时）再发 /offer，提升弱网下首连成功率。
async function waitForIceBeforeOffer(timeoutMs) {
    if (!pc) {
        throw new Error('pc is null');
    }

    if (pc.iceGatheringState === 'complete' || hasLocalCandidatesInDescription()) {
        return;
    }

    const startedAt = performance.now();

    await new Promise((resolve) => {
        let settled = false;

        const finish = (reason) => {
            if (settled) {
                return;
            }
            settled = true;
            clearTimeout(timer);
            if (pc) {
                pc.removeEventListener('icegatheringstatechange', onGatheringState);
                pc.removeEventListener('icecandidate', onCandidate);
            }
            const waitedMs = Math.round(performance.now() - startedAt);
            console.log('[webrtc] profile=', currentProfileName, 'wait ice done:', reason, 'waited=', waitedMs, 'ms');
            resolve();
        };

        const onGatheringState = () => {
            if (!pc) {
                finish('pc_closed');
                return;
            }
            if (pc.iceGatheringState === 'complete') {
                finish('gather_complete');
                return;
            }
            if (hasLocalCandidatesInDescription()) {
                finish('candidate_ready');
            }
        };

        const onCandidate = (evt) => {
            if (!evt.candidate) {
                finish('candidate_end');
                return;
            }
            finish('candidate_event');
        };

        const timer = setTimeout(() => {
            finish('timeout');
        }, timeoutMs);

        if (pc) {
            pc.addEventListener('icegatheringstatechange', onGatheringState);
            pc.addEventListener('icecandidate', onCandidate);
        }

        onGatheringState();
    });
}

// 执行一次完整协商：
// 1) 声明 recvonly transceiver
// 2) 挂载本地发布轨
// 3) createOffer + setLocalDescription
// 4) POST /offer 并设置远端 answer
async function negotiate() {
    if (!pc) {
        throw new Error('pc is null');
    }

    pc.addTransceiver('video', { direction: 'recvonly' });
    pc.addTransceiver('audio', { direction: 'recvonly' });
    await attachPublishTracksIfNeeded();

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    await waitForIceBeforeOffer(MAX_OFFER_ICE_WAIT_MS);

    const local = pc.localDescription;
    const offerRequestStartedAt = performance.now();
    console.log('[webrtc] profile=', currentProfileName, 'send /offer, sdpLen=', local?.sdp?.length || 0);
    const sessionEl = document.getElementById('sessionid');
    const previousSessionId = parseInt((sessionEl && sessionEl.value) || '0', 10);
    const offerPayload = {
        sdp: local.sdp,
        type: local.type,
    };
    if (previousSessionId > 0) {
        offerPayload.sessionid = previousSessionId;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
        controller.abort();
    }, OFFER_REQUEST_TIMEOUT_MS);

    let response = null;
    try {
        response = await fetch(buildApiUrl('/offer'), {
            body: JSON.stringify(offerPayload),
            headers: {
                'Content-Type': 'application/json'
            },
            method: 'POST',
            signal: controller.signal,
        });
    } catch (err) {
        if (controller.signal.aborted) {
            const timeoutErr = new Error(`/offer timeout after ${OFFER_REQUEST_TIMEOUT_MS}ms`);
            timeoutErr.isOfferTimeout = true;
            throw timeoutErr;
        }
        throw err;
    } finally {
        clearTimeout(timeoutId);
    }

    console.log('[webrtc] profile=', currentProfileName, '/offer status=', response.status,
        'elapsed=', Math.round(performance.now() - offerRequestStartedAt), 'ms');

    if (!response.ok) {
        let detail = '';
        try {
            detail = (await response.text()) || '';
        } catch (e) {
            detail = '';
        }

        const message = detail
            ? `/offer status=${response.status} body=${detail.slice(0, 320)}`
            : `/offer status=${response.status}`;
        const offerErr = new Error(message);
        offerErr.offerStatus = response.status;
        throw offerErr;
    }

    const answer = await response.json();
    if (sessionEl && answer && answer.sessionid) {
        sessionEl.value = answer.sessionid;
    }
    console.log('[webrtc] offer response sessionid=', answer?.sessionid, 'reused=', !!answer?.reused);
    await pc.setRemoteDescription(answer);
}

// 使用某个 ICE profile 尝试连接。
async function tryProfile(profile) {
    const config = {
        sdpSemantics: 'unified-plan',
        iceCandidatePoolSize: IS_EDGE ? 0 : 2,
        iceServers: profile.iceServers,
    };
    if (profile.iceTransportPolicy) {
        config.iceTransportPolicy = profile.iceTransportPolicy;
    }

    setupPeerConnection(config, profile.name);
    await negotiate();
    await waitForConnectionResult(ATTEMPT_TIMEOUT_MS);
}

// 对外入口：按 profile 顺序尝试连接，直到成功或全部失败。
async function start() {
    if (isConnecting) {
        console.warn('[webrtc] start ignored, still connecting');
        return false;
    }

    isConnecting = true;
    setCallControlVisibility(true);

    // 新一轮 start 主动清空 sessionid；
    // 之后若本轮 profile 失败重试，会由 negotiate() 自动带回本轮第一个会话 ID 复用。
    const sessionEl = document.getElementById('sessionid');
    if (sessionEl) {
        sessionEl.value = '';
    }

    try {
        const rtcConfigStartedAt = performance.now();
        const rtcConfig = await loadRtcConfig();
        console.log('[webrtc] /rtc_config elapsed=', Math.round(performance.now() - rtcConfigStartedAt), 'ms');
        if ((rtcConfig.iceTransportPolicy || '') === 'relay' && !hasTurnIceServer(rtcConfig.iceServers)) {
            throw new Error('/rtc_config 缺少 TURN relay 配置：请确认后端启动时已设置 TURN_USERNAME 和 TURN_PASSWORD');
        }
        const profiles = buildIceProfiles(rtcConfig);
        console.log('[webrtc] profiles=', profiles.map((p) => p.name));

        let lastError = null;
        for (const profile of profiles) {
            try {
                await tryProfile(profile);
                console.log('[webrtc] connected with profile=', profile.name);

                // 有些网络下 connectionState 迟迟不从 connecting 切到 connected，
                // 但 ICE 已可用。这里在首个成功 profile 后主动通知 UI，避免长期“连接中”假象。
                if (!hasConnectedOnce && typeof window.onWebRTCConnected === 'function') {
                    hasConnectedOnce = true;
                    window.onWebRTCConnected();
                }
                return true;
            } catch (e) {
                lastError = e;
                console.warn('[webrtc] profile failed:', profile.name, e.message);

                // /offer 返回明确服务端错误时，切 profile 也无法恢复，直接结束本轮重试。
                // /offer 超时通常表示后端仍在构建数字人会话；继续切 profile 会制造更多后端并发。
                if (e?.isOfferTimeout || (typeof e?.offerStatus === 'number' && e.offerStatus >= 400)) {
                    throw e;
                }

                closePeerConnectionNow();
            }
        }

        throw lastError || new Error('all profiles failed');
    } catch (e) {
        console.error('[webrtc] start failed:', e);
        alert('WebRTC连接失败：' + e.message + '\n建议检查浏览器控制台中的 icecandidateerror 详情。');
        setCallControlVisibility(false);
        closePeerConnectionNow();
        if (sessionEl) {
            sessionEl.value = '';
        }
        return false;
    } finally {
        isConnecting = false;
    }
}

// 对外停止入口：恢复按钮状态并延迟关闭 PC，给 UI 一点缓冲时间。
function stop() {
    setCallControlVisibility(false);
    const sessionEl = document.getElementById('sessionid');
    if (sessionEl) {
        sessionEl.value = '';
    }

    setTimeout(() => {
        closePeerConnectionNow();
    }, 200);
}

// 页面关闭时兜底清理连接资源。
window.onunload = function (event) {
    setTimeout(() => {
        closePeerConnectionNow();
    }, 200);
};

// 刷新/关闭前的最后清理与浏览器关闭提示。
window.onbeforeunload = function (e) {
    setTimeout(() => {
        closePeerConnectionNow();
    }, 200);
    e = e || window.event;
    if (e) {
        e.returnValue = '关闭提示';
    }
    return '关闭提示';
};
