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

function registerWsHandlers() {
    const w = window.__app.wsManager;
    // 后端广播为顶层字段：{type, pos, quat, vel, ...}（无 payload 键），
    // _dispatch 已统一为 payload ?? data，此处 handler 直接收顶层对象。
    w.on('pose', p => {
        if (!p) return;
        store.batch(() => {
            if (Array.isArray(p.pos)) store.set('drone.position', { x: p.pos[0], y: p.pos[1], z: p.pos[2] });
            else if (p.pos) store.set('drone.position', p.pos);
            if (Array.isArray(p.vel)) store.set('drone.velocity', { vx: p.vel[0], vy: p.vel[1], vz: p.vel[2] });
            else if (p.vel) store.set('drone.velocity', p.vel);
            // 后端广播 quat [w,x,y,z] (无 attitude 字段); 暂存原始四元数, 需要欧拉角时再转换
            if (Array.isArray(p.quat)) store.set('drone.attitude', { quat: p.quat });
            store.set('drone.timestamp', Date.now()); store.set('drone.connected', true);
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
        store.batch(() => {
            if (p.action?.code != null) store.set('flight.currentActionCode', p.action.code);
            if (p.action?.params) store.set('flight.currentActionParams', p.action.params);
            if (Array.isArray(p.goal)) store.set('trajectory.currentTarget', { x: p.goal[0], y: p.goal[1], z: p.goal[2] });
            else if (p.goal) store.set('trajectory.currentTarget', p.goal);
            if (Array.isArray(p.remaining_actions)) store.set('trajectory.actionSequence', p.remaining_actions);
            if (Array.isArray(p.planned)) store.set('trajectory.planned', p.planned);
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
    w.on('connection', p => { if (p?.status) store.set('connection.ws', p.status); });
}

// Boot: if DOM already ready, call init immediately; otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
