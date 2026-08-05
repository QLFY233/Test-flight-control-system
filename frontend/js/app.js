/**
 * App — Main Entry Point.
 * Uses window.__app for shared state — zero circular import issues.
 * Pages are lazy-loaded via dynamic import() to minimize initial HTTP requests.
 *
 * Startup module count: ~15 (reduced from ~44)
 */
import store from './state.js';
import { Router } from './router.js';
import { loadConfig } from './config.js';
import { WsManager } from './ws.js';
import { SseManager } from './sse.js';
import { ApiManager } from './api.js';
import bus from './event-bus.js';
import { initToast } from './components/Toast.js';
import { renderTwoColumn } from './shared.js';

import { StatusBar } from './components/StatusBar.js';
import { BottomBar } from './components/BottomBar.js';
import { ConnectionOverlay } from './components/ConnectionOverlay.js';
import { ChatPanel } from './components/ChatPanel.js';
import { ShortcutEditor } from './components/ShortcutEditor.js';


initToast();

// ==========================================================
// Lazy Page Registry — maps hash → dynamic import factory
// ==========================================================
const PAGE_REGISTRY = {
    '#/overview':  () => import('./pages/OverviewPage.js').then(m => new m.OverviewPage()),
    '#/alpha':     () => import('./pages/AlphaPage.js').then(m => new m.AlphaPage()),
    '#/beta':      () => import('./pages/BetaPage.js').then(m => new m.BetaPage()),
    '#/history':   () => import('./pages/HistoryPage.js').then(m => new m.HistoryPage()),
    '#/settings':  () => import('./pages/SettingsPage.js').then(m => new m.SettingsPage()),
    '#/dashboard': () => import('./pages/DashboardPage.js').then(m => new m.DashboardPage()),
};

function renderRootLayout(appEl) {
    appEl.innerHTML = `<div class="app-container">
        <div id="status-bar" class="status-bar"></div>
        <nav class="nav-strip" id="nav-strip">
            <a class="nav-strip__item nav-strip__item--active" href="#/overview"><span class="nav-strip__code">OVR</span> 总览</a>
            <a class="nav-strip__item" href="#/beta"><span class="nav-strip__code">PLN</span> 规划</a>
            <a class="nav-strip__item" href="#/dashboard"><span class="nav-strip__code">DSH</span> 看板</a>
            <a class="nav-strip__item" href="#/alpha"><span class="nav-strip__code">FLT</span> 飞控</a>
            <a class="nav-strip__item" href="#/history"><span class="nav-strip__code">HST</span> 历史</a>
            <a class="nav-strip__item" href="#/settings"><span class="nav-strip__code">CFG</span> 设置</a>
            <span class="nav-strip__sep">///</span>
            <span class="nav-strip__info">REV 2.6 · UNIT D-01</span>
        </nav>
        <div id="main-content" class="main-content">
            <div id="page-container" style="flex:1;display:flex;flex-direction:row;overflow:hidden"></div>
            <div id="chat-sidebar" class="chat-sidebar"></div>
        </div>
        <div id="bottom-bar" class="bottom-bar"></div>
        <nav class="tab-bar">
            <a class="tab-bar__item tab-bar__item--active" href="#/overview"><span class="tab-bar__item-icon">&#9638;</span><span>OVR</span></a>
            <a class="tab-bar__item" href="#/beta"><span class="tab-bar__item-icon">&#9874;</span><span>PLN</span></a>
            <a class="tab-bar__item" href="#/dashboard"><span class="tab-bar__item-icon">&#9643;</span><span>DSH</span></a>
            <a class="tab-bar__item" href="#/alpha"><span class="tab-bar__item-icon">&#9992;</span><span>FLT</span></a>
            <a class="tab-bar__item" href="#/history"><span class="tab-bar__item-icon">&#8986;</span><span>HST</span></a>
            <a class="tab-bar__item" href="#/settings"><span class="tab-bar__item-icon">&#9881;</span><span>CFG</span></a>
        </nav>
        <div id="connection-overlay"></div>
    </div>`;
}

async function init() {
    try {
    console.log('[App] init start');
    const a = window.__app;
    const appEl = document.getElementById('app');
    if (!appEl) { console.log('ERROR: no #app element'); return; }

    console.log('loading config...');
    a.config = await loadConfig();
    console.log('config loaded');

    // Restore persisted environment from localStorage
    try {
        const saved = JSON.parse(localStorage.getItem('flight-control-config') || '{}');
        if (saved.environment) {
            store.batch(() => {
                for (const [key, val] of Object.entries(saved.environment)) {
                    if (val != null) store.set(`environment.${key}`, val);
                }
            });
        }
        // Apply display theme if saved
        if (saved.display?.theme === 'light') {
            document.body.classList.add('theme-light');
        }
    } catch(e) { /* ignore parse errors */ }

    // 同源自适应: 页面由 A 服务 StaticFiles 挂载时, base_url 跟随 location.origin
    // (默认 8000 被其他服务占用/改用 BACKEND_A_PORT 时, 无需改配置即可同源访问);
    // 用户显式配置的 base_url (SettingsPage 保存) 优先
    const cfgBase = a.config.backend?.base_url || 'http://localhost:8000';
    const effectiveBase = (cfgBase === 'http://localhost:8000' && location.origin && location.origin !== 'http://localhost:8000')
        ? location.origin : cfgBase;
    a.apiManager = new ApiManager(effectiveBase);
    a.sseManager = new SseManager();
    a.wsManager = new WsManager(effectiveBase.replace(/^http/, 'ws') + (a.config.backend?.ws_endpoint || '/ws'));
    console.log('managers created');

    renderRootLayout(appEl);
    console.log('layout rendered');

    // 状态栏/底栏：实例复用 + rAF 节流，避免每条遥测消息重建 5 次 DOM
    const sb = new StatusBar(document.getElementById('status-bar'));
    sb.mount();
    const bb = new BottomBar(document.getElementById('bottom-bar'));
    bb.mount();

    let sbRaf = null;
    let bbRaf = null;
    const scheduleStatusBar = () => {
        if (sbRaf) return;
        sbRaf = requestAnimationFrame(() => { sbRaf = null; sb.mount(); });
    };
    const scheduleBottomBar = () => {
        if (bbRaf) return;
        bbRaf = requestAnimationFrame(() => { bbRaf = null; bb.mount(); });
    };
    // 订阅一次：connection/drone 变更刷新状态栏，flight/trajectory 刷新底栏
    store.subscribe('connection', scheduleStatusBar);
    store.subscribe('drone', scheduleStatusBar);
    store.subscribe('flight', () => { scheduleStatusBar(); scheduleBottomBar(); });
    store.subscribe('trajectory', scheduleBottomBar);
    console.log('StatusBar done');

    // ConnectionOverlay
    const co = new ConnectionOverlay(document.getElementById('connection-overlay'));
    store.subscribe('connection', v => v === 'disconnected' ? co.show() : co.hide());
    console.log('ConnectionOverlay done');

    // Chat Sidebar — fixed right panel per spec P1/C2
    a.chatPanel = new ChatPanel(document.getElementById('chat-sidebar'));
    a.chatPanel.mount();
    console.log('ChatPanel mounted (right sidebar)');

    // Floating Ball
    const fb = document.createElement('div'); fb.id = 'fb';
    document.querySelector('.app-container').appendChild(fb);
    import('./components/FloatingBall.js').then(m => {
        new m.FloatingBall(fb).mount();
    }).catch(() => {});

    // ShortcutEditor — 常驻监听 open-shortcut-editor 事件（长按悬浮球进入编辑）
    new ShortcutEditor();

    // Router — register lazy page factories
    console.log('setting up router...');
    a.router = new Router(document.getElementById('page-container'));
    for (const [hash, factory] of Object.entries(PAGE_REGISTRY)) {
        a.router.register(hash, factory);
    }
    console.log('router init...');
    a.router.init();
    console.log('router done');

    // WS
    a.wsManager.connect();
    registerWsHandlers();
    // 页面加载即主动拉取一次链路状态（不等 WS 连接事件，apiManager 此时已可用）
    refreshLinkStatus();
    // SSE plan 事件 (β 提议, 待批准) → 待批准航线预览 (黄色)
    // 后端 plan 事件 actions = α 预翻译结果 (可能为空 → 无预览);
    // 批准后 alpha_output 到达时自动清空 (正式计划覆盖预览)
    bus.on('plan-received', (plan) => {
        try {
            const actions = plan?.actions;
            if (Array.isArray(actions) && actions.length > 0) {
                const pose = store.get('drone.position') || { x: 0, y: 0, z: 0 };
                const home = _getHomePos(store.get('field'));
                const { seq, planned } = _normalizePlan(actions, pose, home);
                store.set('trajectory.pending', { seq, planned });
            } else {
                store.set('trajectory.pending', null);
            }
        } catch (e) {
            console.warn('[App] plan-received preview failed:', e);
            store.set('trajectory.pending', null);
        }
    });
    console.log('WS handlers registered');

    // Field config
    a.apiManager.getFieldConfig().then(fd => {
        if (fd) { store.set('field.boundary', fd.boundary || store.get('field.boundary')); store.set('field.obstacles', fd.obstacles || []); store.set('field.home', fd.home || store.get('field.home')); }
    }).catch(() => store.set('field.obstacles', []));

    // 可见性恢复：页面重新可见且 WS 未连接时主动重连
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible') return;
        const wm = a.wsManager;
        if (wm && wm.getStatus() !== 'connected' && wm.getStatus() !== 'connecting') {
            console.log('[App] tab visible — reconnecting WS');
            wm.connect();
        }
    });

    // 设置页修改后端地址后重建 WS 连接（REST 与 WS 保持同一目标）
    bus.on('backend-url-changed', ({ baseUrl, wsEndpoint }) => {
        if (!baseUrl) return;
        a.config.backend = { ...(a.config.backend || {}), base_url: baseUrl, ws_endpoint: wsEndpoint || '/ws' };
        a.apiManager.setBaseUrl(baseUrl);
        const wsUrl = baseUrl.replace(/^http/, 'ws') + (a.config.backend.ws_endpoint || '/ws');
        a.wsManager.disconnect();
        a.wsManager = new WsManager(wsUrl);
        registerWsHandlers();
        a.wsManager.connect();
        bus.emit('toast', { message: '后端地址已更新，连接已重建', level: 'success' });
    });

    // Tab bar + Nav strip (skip button elements)
    const syncTabs = () => { const h = window.location.hash || '#/overview'; document.querySelectorAll('.tab-bar__item[href], .nav-strip__item[href]').forEach(x => { const match = x.getAttribute('href') === h; x.classList.toggle('tab-bar__item--active', match); x.classList.toggle('nav-strip__item--active', match); }); };
    window.addEventListener('hashchange', syncTabs);
    syncTabs();

    // Save config
    window.addEventListener('beforeunload', () => { const c = a.config; const s = { theme: c?.display?.theme, language: c?.display?.language }; const e = JSON.parse(localStorage.getItem('flight-control-config') || '{}'); Object.assign(e, { display: { ...(e.display || {}), ...s } }); localStorage.setItem('flight-control-config', JSON.stringify(e)); });

    console.log('INIT DONE ✅');
    } catch(e) {
        console.log('INIT CRASH: ' + e.message + ' at ' + (e.stack?.split('\n')[1]||'?'));
    }
}

// ============================================================
// trajectory 数据归一化 — 飞行计划 → 前端展示数据
// (ActionCommand schema_version=2: target 为顶层数组 [x,y,z],
//  视图组件按 {x,y,z} 对象读取; goal 链式推导对齐 B 侧 stub.py 语义)
// ============================================================

function _toXYZ(v) {
    if (Array.isArray(v) && v.length >= 3 && v.slice(0, 3).every(n => typeof n === 'number' && Number.isFinite(n))) {
        return { x: v[0], y: v[1], z: v[2] };
    }
    if (v && typeof v === 'object' && typeof v.x === 'number' && typeof v.y === 'number' && typeof v.z === 'number') {
        return { x: v.x, y: v.y, z: v.z };
    }
    return null;
}

// home 兼容解析: field.home.position (数组/对象) 或 field.home 直接为 {x,y,z}
function _getHomePos(field) {
    const raw = field?.home;
    if (!raw) return { x: 0, y: 0, z: 0.5 };
    return _toXYZ(raw.position) || _toXYZ(raw) || { x: 0, y: 0, z: 0.5 };
}

/**
 * 归一化动作序列 + 链式推导每个动作的目标点 (goal)。
 * 推导语义对齐 backend-B/small_model/stub.py (40-135 行)。
 * @param {Array} actions 原始 ActionCommand.actions
 * @param {{x,y,z}} pose 当前无人机位置
 * @param {{x,y,z}} home 返航点
 * @returns {{seq: Array, planned: Array}}
 */
function _normalizePlan(actions, pose, home) {
    const seq = [];
    const planned = [];
    let cursor = { x: pose?.x ?? 0, y: pose?.y ?? 0, z: pose?.z ?? 0 };
    planned.push({ ...cursor }); // 起点 = 当前无人机位置

    for (const a of (Array.isArray(actions) ? actions : [])) {
        const code = a?.code || '';
        let goal = null;

        switch (code) {
            case 'takeoff':
                goal = { x: home.x, y: home.y, z: typeof a.value === 'number' ? a.value : 1 };
                break;
            case 'goto':
                goal = _toXYZ(a.target) || { ...cursor };
                break;
            case 'move': {
                const value = typeof a.value === 'number' ? a.value : 1;
                const dir = _toXYZ(a.target) || { x: 1, y: 0, z: 0 }; // 无方向时简化 +x (前端无 yaw 数据)
                const mag = Math.hypot(dir.x, dir.y, dir.z) || 1;
                goal = {
                    x: cursor.x + (dir.x / mag) * value,
                    y: cursor.y + (dir.y / mag) * value,
                    z: cursor.z + (dir.z / mag) * value,
                };
                break;
            }
            case 'climb':
                goal = { x: cursor.x, y: cursor.y, z: cursor.z + (typeof a.value === 'number' ? a.value : 0.5) };
                break;
            case 'descend':
                goal = { x: cursor.x, y: cursor.y, z: cursor.z - (typeof a.value === 'number' ? a.value : 0.5) };
                break;
            case 'yaw':
            case 'hover':
                goal = null; // 位置不动
                break;
            case 'return_home':
                goal = { ...home };
                break;
            case 'land':
                goal = { ...home }; // 前端简化 (stub 用 floor 高度, 前端无 floor 数据)
                break;
            default:
                goal = null; // 未知编码不抛错
        }

        if (goal) {
            cursor = { ...goal };
            const last = planned[planned.length - 1];
            if (!last || Math.abs(goal.x - last.x) > 0.001 || Math.abs(goal.y - last.y) > 0.001 || Math.abs(goal.z - last.z) > 0.001) {
                planned.push({ ...goal });
            }
        }

        seq.push({
            code,
            target: _toXYZ(a.target),   // 归一化: 数组 [x,y,z] → {x,y,z}
            value: a.value,
            units: a.units,
            comment: a.comment,
            goal,                        // 链式推导目标点 (可能 null)
        });
    }

    return { seq, planned };
}

function registerWsHandlers() {
    const w = window.__app.wsManager;
    // 后端广播为顶层字段：{type, pos, quat, vel, ...}（无 payload 键），
    // _dispatch 已统一为 payload ?? data，此处 handler 直接收顶层对象。
    w.on('pose', p => {
        if (!p) return;
        store.batch(() => {
            let pos = null;
            if (Array.isArray(p.pos) && p.pos.length >= 3) pos = { x: p.pos[0], y: p.pos[1], z: p.pos[2] };
            else if (p.pos) pos = p.pos;
            if (pos) {
                store.set('drone.position', pos);
                // 已飞轨迹追加 (10Hz; 连续同点跳过, 上限 600)
                const flown = store.get('trajectory.flown') || [];
                const last = flown[flown.length - 1];
                if (!last || Math.hypot(pos.x - last.x, pos.y - last.y, pos.z - last.z) >= 0.01) {
                    const next = flown.length >= 600 ? flown.slice(flown.length - 599) : flown.slice();
                    next.push({ x: pos.x, y: pos.y, z: pos.z });
                    store.set('trajectory.flown', next);
                }
            }
            if (Array.isArray(p.vel)) store.set('drone.velocity', { vx: p.vel[0], vy: p.vel[1], vz: p.vel[2] });
            else if (p.vel) store.set('drone.velocity', p.vel);
            // 后端广播 quat [w,x,y,z] (无 attitude 字段); 暂存原始四元数, 需要欧拉角时再转换
            if (Array.isArray(p.quat)) store.set('drone.attitude', { quat: p.quat });
            store.set('drone.timestamp', Date.now()); store.set('drone.connected', true);
            // drone 在线状态由 pose 数据流推断（link_status 冻结枚举无 drone 链路）
            store.set('connection.drone', 'connected');
        });
    });
    w.on('status', p => {
        if (!p) return;
        store.batch(() => {
            if (p.mode != null) store.set('flight.mode', p.mode);
            if (p.flightStatus != null) store.set('flight.status', p.flightStatus);
            if (p.currentAction != null) store.set('flight.currentAction', p.currentAction);
            if (p.totalActions != null) store.set('flight.totalActions', p.totalActions);
            if (p.progress != null) store.set('flight.progress', p.progress);
        });
        bus.emit('status-update', p);
    });
    w.on('alert', p => bus.emit('alert', p));
    w.on('reject', p => {
        bus.emit('proposal-rejected', p);
        // 应急可见性: reject 直接 toast 提示 (reason/actionIndex 后端已广播)
        if (p?.reason) {
            bus.emit('toast', {
                message: 'α 动作被拒绝: ' + p.reason + (p.actionIndex != null ? ' (动作 #' + p.actionIndex + ')' : ''),
                level: 'warning',
            });
        }
    });
    w.on('alpha_output', p => {
        if (!p) return;
        // 正式计划已下达 → 清除待批准预览 (黄色 → 青色覆盖)
        store.set('trajectory.pending', null);
        // 动作源: WS remaining_actions 优先, 兼容 action.actions (后端广播格式) 兑底
        const rawActions = Array.isArray(p.remaining_actions) ? p.remaining_actions
            : (Array.isArray(p.action?.actions) ? p.action.actions : []);
        const pose = store.get('drone.position') || { x: 0, y: 0, z: 0 };
        const home = _getHomePos(store.get('field'));
        const { seq, planned } = _normalizePlan(rawActions, pose, home);

        store.batch(() => {
            // currentActionCode: 从归一化序列按当前动作索引取 (ActionCommand 无顶层 code 字段)
            const curIdx = (store.get('flight.currentAction') || 1) - 1;
            const curAct = seq[curIdx] || seq[0] || null;
            store.set('flight.currentActionCode', curAct?.code ?? '');
            if (curAct) {
                const params = {};
                if (curAct.value != null) params.value = curAct.value;
                if (curAct.units != null) params.units = curAct.units;
                if (curAct.target) params.target = curAct.target;
                store.set('flight.currentActionParams', Object.keys(params).length ? params : null);
            } else {
                store.set('flight.currentActionParams', null);
            }
            // 目标点: 后端广播的 goal (带 target 的动作) 优先, 否则用推导的第一个 goal
            if (Array.isArray(p.goal) && p.goal.length >= 3) store.set('trajectory.currentTarget', { x: p.goal[0], y: p.goal[1], z: p.goal[2] });
            else if (p.goal) store.set('trajectory.currentTarget', p.goal);
            else store.set('trajectory.currentTarget', seq.find(a => a.goal)?.goal ?? null);
            store.set('trajectory.actionSequence', seq);
            // planned: 后端权威 planned (若将来广播) 优先, 否则用链式推导 [起点 + 各目标点]
            if (Array.isArray(p.planned) && p.planned.length > 1) {
                store.set('trajectory.planned', p.planned);
            } else {
                store.set('trajectory.planned', planned);
            }
        });
        bus.emit('alpha-output', p);
    });
    w.on('link_status', p => {
        if (!p || !p.link) return;
        const state = p.state || 'unknown';
        store.batch(() => {
            if (p.link === 'A-B') {
                store.set('connection.backendA', state);
                store.set('connection.backendB', state);
            } else if (p.link === 'llm') {
                store.set('connection.llm', state);
            }
        });
    });
    w.on('voice_tts', p => {
        if (!p?.audio) return;
        import('./components/AudioPlayer.js').then(m => m.AudioPlayer.play(p.audio)).catch(() => {});
    });
    // 连接状态单一数据源：ws.js 内部 _dispatch({type:'connection', payload:{status}})，
    // 不再经 __event:open/close 重复写 connection.ws
    w.on('connection', p => {
        if (!p?.status) return;
        store.set('connection.ws', p.status);
        // WS (重)连接成功后主动刷新链路状态（后端仅在状态变化时推送 link_status）
        if (p.status === 'connected') refreshLinkStatus();
    });
}

// 主动刷新链路状态：后端 /api/link-status 仅在状态变化时经 WS 推送 link_status，
// 页面加载 / WS 重连后需主动拉取一次，避免总览 [系统状态] 面板恒显 UNK。
function refreshLinkStatus() {
    const a = window.__app;
    if (!a?.apiManager) return;
    a.apiManager.get('/api/link-status')
        .then(d => {
            if (!d) return;
            store.batch(() => {
                if (d.ipc != null) {
                    store.set('connection.backendA', d.ipc);
                    store.set('connection.backendB', d.ipc);
                }
                if (d.llm != null) store.set('connection.llm', d.llm);
                // flight_status 仅在当前值缺失时顺带填充（status WS 消息优先，避免覆盖实时值）
                const cur = store.get('flight.status');
                if (d.flight_status != null && (!cur || cur === 'unknown')) {
                    store.set('flight.status', d.flight_status);
                }
            });
        })
        .catch(() => { /* 拉取失败静默：WS link_status 推送仍是兜底更新源 */ });
}

// Boot: if DOM already ready, call init immediately; otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
