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

import { Scene3D } from './scenes/Scene3D.js';

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
        <div id="main-content" class="main-content">
            <div id="page-container" style="width:100%;border-right:none;display:flex;flex-direction:row;flex:1;overflow:hidden"></div>
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

    a.apiManager = new ApiManager(a.config.backend?.base_url || 'http://localhost:8000');
    a.sseManager = new SseManager();
    a.wsManager = new WsManager((a.config.backend?.base_url || 'http://localhost:8000').replace(/^http/, 'ws') + (a.config.backend?.ws_endpoint || '/ws'));
    console.log('managers created');

    renderRootLayout(appEl);
    console.log('layout rendered');

    // 3D Scene — create eagerly (needed by most pages)
    console.log('creating 3D scene...');
    const s3d = new Scene3D();
    a.scene3D = s3d;
    if (s3d.isReady()) {
        // Defer 3D sub-modules: they're only needed when a page mounts a 3D view
        // Preload them in the background without blocking
        Promise.all([
            import('./scenes/FieldRenderer.js'),
            import('./scenes/DroneModel.js'),
            import('./scenes/TrajectoryLine.js'),
            import('./scenes/WaypointMarker.js'),
        ]).then(([frMod, dmMod, tlMod, wmMod]) => {
            if (a.scene3D?.isReady()) {
                a.fieldRenderer = new frMod.FieldRenderer(a.scene3D);
                a.droneModel = new dmMod.DroneModel(a.scene3D);
                a.trajectoryLine = new tlMod.TrajectoryLine(a.scene3D);
                a.waypointMarker = new wmMod.WaypointMarker(a.scene3D);
                console.log('3D sub-modules loaded');
            }
        }).catch(e => console.warn('3D sub-modules load failed:', e.message));
        console.log('3D scene ok (sub-modules loading in background)');
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

    // Chat Dock — lazy load (only needed when user opens chat)
    const cc = document.createElement('div'); cc.id = 'chat-dock';
    document.querySelector('.app-container').appendChild(cc);
    a._chatPanelContainer = cc;
    import('./components/ChatPanel.js').then(m => {
        a.chatPanel = new m.ChatPanel(cc);
        console.log('ChatPanel loaded');
    }).catch(e => console.warn('ChatPanel load failed:', e.message));

    // Floating Ball — lazy load
    const fb = document.createElement('div'); fb.id = 'fb';
    document.querySelector('.app-container').appendChild(fb);
    import('./components/FloatingBall.js').then(m => {
        new m.FloatingBall(fb);
        console.log('FloatingBall loaded');
    }).catch(e => console.warn('FloatingBall load failed:', e.message));
    import('./components/ShortcutEditor.js').then(m => {
        new m.ShortcutEditor();
    }).catch(() => {});

    // Router — register lazy page factories
    console.log('setting up router...');
    a.router = new Router(document.getElementById('page-container'));
    for (const [hash, factory] of Object.entries(PAGE_REGISTRY)) {
        a.router.register(hash, factory);
    }
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
    w.on('voice_tts', p => {
        if (!p?.audio) return;
        import('./components/AudioPlayer.js').then(m => m.AudioPlayer.play(p.audio)).catch(() => {});
    });
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
