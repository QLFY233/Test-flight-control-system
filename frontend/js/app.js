/**
 * App — Main Entry Point. Uses window.__app for shared state — zero circular import issues.
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
import { AudioPlayer } from './components/AudioPlayer.js';
import { FloatingBall } from './components/FloatingBall.js';
import { ShortcutEditor } from './components/ShortcutEditor.js';

import { Scene3D } from './scenes/Scene3D.js';
import { FieldRenderer } from './scenes/FieldRenderer.js';
import { DroneModel } from './scenes/DroneModel.js';
import { TrajectoryLine } from './scenes/TrajectoryLine.js';
import { WaypointMarker } from './scenes/WaypointMarker.js';

import { OverviewPage } from './pages/OverviewPage.js';
import { AlphaPage } from './pages/AlphaPage.js';
import { BetaPage } from './pages/BetaPage.js';
import { HistoryPage } from './pages/HistoryPage.js';
import { SettingsPage } from './pages/SettingsPage.js';
import { DashboardPage } from './pages/DashboardPage.js';

initToast();

function renderRootLayout(appEl) {
    appEl.innerHTML = `<div class="app-container">
        <div id="status-bar" class="status-bar"></div>
        <div id="main-content" class="main-content">
            <div id="page-container" style="width:100%;border-right:none;display:flex;flex-direction:row;flex:1;overflow:hidden"></div>
        </div>
        <div id="bottom-bar" class="bottom-bar"></div>
        <nav class="tab-bar">
            <a class="tab-bar__item tab-bar__item--active" href="#/overview"><span class="tab-bar__item-icon">&#9673;</span><span>总览</span></a>
            <a class="tab-bar__item" href="#/beta"><span class="tab-bar__item-icon">&#9881;</span><span>规划</span></a>
            <a class="tab-bar__item" href="#/dashboard"><span class="tab-bar__item-icon">&#9636;</span><span>看板</span></a>
            <a class="tab-bar__item" href="#/alpha"><span class="tab-bar__item-icon">&#9992;</span><span>飞控</span></a>
            <a class="tab-bar__item" href="#/history"><span class="tab-bar__item-icon">&#9638;</span><span>历史</span></a>
            <a class="tab-bar__item" href="#/settings"><span class="tab-bar__item-icon">&#9881;</span><span>设置</span></a>
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

    a.apiManager = new ApiManager(a.config.backend?.base_url || 'http://localhost:8000');
    a.sseManager = new SseManager();
    a.wsManager = new WsManager((a.config.backend?.base_url || 'http://localhost:8000').replace(/^http/, 'ws') + (a.config.backend?.ws_endpoint || '/ws'));
    console.log('managers created');

    renderRootLayout(appEl);
    console.log('layout rendered');

    // 3D Scene
    console.log('creating 3D scene...');
    const s3d = new Scene3D();
    a.scene3D = s3d;
    if (s3d.isReady()) {
        a.fieldRenderer = new FieldRenderer(s3d);
        a.droneModel = new DroneModel(s3d);
        a.trajectoryLine = new TrajectoryLine(s3d);
        a.waypointMarker = new WaypointMarker(s3d);
        console.log('3D scene ok');
    } else {
        console.log('3D not available (no WebGL)');
    }

    // StatusBar
    console.log('mounting StatusBar...');
    new StatusBar(document.getElementById('status-bar')).mount();
    console.log('StatusBar done');

    // BottomBar
    new BottomBar(document.getElementById('bottom-bar')).mount();
    console.log('BottomBar done');

    // ConnectionOverlay
    const co = new ConnectionOverlay(document.getElementById('connection-overlay'));
    store.subscribe('connection', v => v === 'disconnected' ? co.show() : co.hide());
    console.log('ConnectionOverlay done');

    // Chat Dock
    const cc = document.createElement('div'); cc.id = 'chat-dock';
    document.querySelector('.app-container').appendChild(cc);
    a.chatPanel = new ChatPanel(cc);
    console.log('ChatPanel done');

    // Floating Ball
    const fb = document.createElement('div'); fb.id = 'fb';
    document.querySelector('.app-container').appendChild(fb);
    new FloatingBall(fb);
    new ShortcutEditor();
    console.log('FloatingBall done');

    // Router
    console.log('setting up router...');
    a.router = new Router(document.getElementById('page-container'));
    a.router.register('#/overview', new OverviewPage());
    console.log('registering alpha...');
    a.router.register('#/alpha', new AlphaPage());
    console.log('registering beta...');
    a.router.register('#/beta', new BetaPage());
    console.log('registering history...');
    a.router.register('#/history', new HistoryPage());
    a.router.register('#/settings', new SettingsPage());
    console.log('registering dashboard...');
    a.router.register('#/dashboard', new DashboardPage());
    console.log('router init...');
    a.router.init();
    console.log('router done');

    // Subscriptions
    store.subscribe('connection', () => { const sb = document.getElementById('status-bar'); if (sb) new StatusBar(sb).mount(); });
    store.subscribe('drone', () => { const sb = document.getElementById('status-bar'); if (sb) new StatusBar(sb).mount(); });
    store.subscribe('flight', () => {
        const sb = document.getElementById('status-bar'); if (sb) new StatusBar(sb).mount();
        const bb = document.getElementById('bottom-bar'); if (bb) new BottomBar(bb).mount();
    });
    store.subscribe('trajectory', () => { const bb = document.getElementById('bottom-bar'); if (bb) new BottomBar(bb).mount(); });

    // WS
    a.wsManager.connect();
    registerWsHandlers();
    console.log('WS handlers registered');

    // Field config
    a.apiManager.getFieldConfig().then(fd => {
        if (fd) { store.set('field.boundary', fd.boundary || store.get('field.boundary')); store.set('field.obstacles', fd.obstacles || []); store.set('field.home', fd.home || store.get('field.home')); }
    }).catch(() => store.set('field.obstacles', []));

    // Visibility
    document.addEventListener('visibilitychange', () => { const s = a.scene3D; if (s?.isReady()) { document.hidden ? s.pause() : s.resume(); } });

    // Tab bar
    const syncTabs = () => { const h = window.location.hash || '#/overview'; document.querySelectorAll('.tab-bar__item').forEach(x => x.classList.toggle('tab-bar__item--active', x.getAttribute('href') === h)); };
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
    w.on('pose', p => {
        if (!p) return;
        store.batch(() => {
            if (p.position) { store.set('drone.position', p.position); window.__app.droneModel?.setTargetPosition(p.position); window.__app.trajectoryLine?.updateFlown([p.position]); }
            if (p.velocity) store.set('drone.velocity', p.velocity);
            if (p.attitude) store.set('drone.attitude', p.attitude);
            store.set('drone.timestamp', Date.now()); store.set('drone.connected', true);
        });
    });
    w.on('status', p => {
        if (!p) return;
        store.batch(() => {
            if (p.mode != null) store.set('flight.mode', p.mode);
            if (p.status != null) store.set('flight.status', p.status);
            if (p.current_action != null) store.set('flight.currentAction', p.current_action);
            if (p.total_actions != null) store.set('flight.totalActions', p.total_actions);
            if (p.current_action_code != null) store.set('flight.currentActionCode', p.current_action_code);
            if (p.progress != null) store.set('flight.progress', p.progress);
        });
        bus.emit('status-update', p);
    });
    w.on('alert', p => bus.emit('alert', p));
    w.on('reject', p => bus.emit('proposal-rejected', p));
    w.on('alpha_output', p => {
        if (!p) return;
        store.batch(() => {
            if (p.planned) store.set('trajectory.planned', p.planned);
            if (p.action_sequence) store.set('trajectory.actionSequence', p.action_sequence);
            if (p.current_target) store.set('trajectory.currentTarget', p.current_target);
        });
        if (p.planned) window.__app.trajectoryLine?.setPlanned(p.planned);
        if (p.current_target) window.__app.waypointMarker?.setTarget(p.current_target);
        if (p.action_sequence?.length && window.__app.waypointMarker) {
            const ts = p.action_sequence.filter(a => a.params?.target).map(a => a.params.target);
            if (ts.length) window.__app.waypointMarker.setWaypoints(ts);
        }
        bus.emit('alpha-output', p);
    });
    w.on('link_status', p => { if (p) store.batch(() => { if (p.backend_a != null) store.set('connection.backendA', p.backend_a); if (p.backend_b != null) store.set('connection.backendB', p.backend_b); if (p.drone != null) store.set('connection.drone', p.drone); if (p.llm != null) store.set('connection.llm', p.llm); }); });
    w.on('voice_tts', p => { if (p?.audio) AudioPlayer.play(p.audio); });
    w.on('__event:open', () => { store.set('connection.ws', 'connected'); });
    w.on('__event:close', () => { store.set('connection.ws', 'disconnected'); });
    w.on('connection', p => { if (p?.status) store.set('connection.ws', p.status); });
}

// Boot: if DOM already ready, call init immediately; otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
