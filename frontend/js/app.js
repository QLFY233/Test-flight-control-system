/**
 * App — Main Entry Point
 * Initializes the application: config, store, WebSocket, API, router, UI shell.
 */

import store from './state.js';
import { Router } from './router.js';
import { loadConfig } from './config.js';
import { WsManager } from './ws.js';
import { SseManager } from './sse.js';
import { ApiManager } from './api.js';
import bus from './event-bus.js';

// These will be imported after UI components are loaded
import { StatusBar } from './components/StatusBar.js';
import { BottomBar } from './components/BottomBar.js';
import { ConnectionOverlay } from './components/ConnectionOverlay.js';
import { ChatPanel } from './components/ChatPanel.js';
import { ChatMessage } from './components/ChatMessage.js';
import { AudioPlayer } from './components/AudioPlayer.js';
import { VideoPanel } from './components/VideoPanel.js';
import { FlightPlanCard } from './components/FlightPlanCard.js';
import { SessionCard } from './components/SessionCard.js';
import { EmptyState } from './components/EmptyState.js';
import { ViewModeSelector } from './components/ViewModeSelector.js';
import { ViewPanel } from './components/ViewPanel.js';
import { FloatingBall } from './components/FloatingBall.js';
import { ShortcutEditor } from './components/ShortcutEditor.js';
import { TimelineControl } from './components/TimelineControl.js';

import { Scene3D } from './scenes/Scene3D.js';
import { FieldRenderer } from './scenes/FieldRenderer.js';
import { DroneModel } from './scenes/DroneModel.js';
import { TrajectoryLine } from './scenes/TrajectoryLine.js';
import { WaypointMarker } from './scenes/WaypointMarker.js';

import { AltitudeChart } from './charts/AltitudeChart.js';
import { VelocityChart } from './charts/VelocityChart.js';
import { FieldMap2D } from './charts/FieldMap2D.js';
import { HistoryChart } from './charts/HistoryChart.js';

import { OverviewPage } from './pages/OverviewPage.js';
import { AlphaPage } from './pages/AlphaPage.js';
import { BetaPage } from './pages/BetaPage.js';
import { HistoryPage } from './pages/HistoryPage.js';
import { SettingsPage } from './pages/SettingsPage.js';

// ============================================================
// Global instances (for pages/components to access)
// ============================================================
export let config;
export let wsManager;
export let sseManager;
export let apiManager;
export let router;
export let chatPanel;

// Shared 3D scene (used across pages)
export let sharedScene3D;
export let sharedFieldRenderer;
export let sharedDroneModel;
export let sharedTrajectoryLine;
export let sharedWaypointMarker;

// ============================================================
// Render Root Layout
// ============================================================

function renderRootLayout(appEl) {
    appEl.innerHTML = `
        <div class="app-container">
            <!-- Status Bar -->
            <div id="status-bar" class="status-bar"></div>

            <!-- Main Content -->
            <div id="main-content" class="main-content">
                <div id="page-container" class="left-column" style="width: 100%; border-right: none;"></div>
            </div>

            <!-- Bottom Bar -->
            <div id="bottom-bar" class="bottom-bar"></div>

            <!-- Tab Bar (Mobile) -->
            <nav class="tab-bar">
                <a class="tab-bar__item tab-bar__item--active" href="#/overview">
                    <span class="tab-bar__item-icon">&#9673;</span>
                    <span>总览</span>
                </a>
                <a class="tab-bar__item" href="#/beta">
                    <span class="tab-bar__item-icon">&#9881;</span>
                    <span>规划</span>
                </a>
                <a class="tab-bar__item" href="#/alpha">
                    <span class="tab-bar__item-icon">&#9992;</span>
                    <span>飞控</span>
                </a>
                <a class="tab-bar__item" href="#/history">
                    <span class="tab-bar__item-icon">&#9638;</span>
                    <span>历史</span>
                </a>
                <a class="tab-bar__item" href="#/settings">
                    <span class="tab-bar__item-icon">&#9881;</span>
                    <span>设置</span>
                </a>
            </nav>

            <!-- Connection Overlay -->
            <div id="connection-overlay"></div>
        </div>
    `;
}

/**
 * Render the full two-column layout (used by pages like Alpha).
 * @param {HTMLElement} mainContent - the #main-content element
 * @param {string} leftHtml - HTML for the left column body
 * @param {string} rightHtml - HTML for the right column content
 * @param {string} [leftHeader] - optional left column header text
 */
export function renderTwoColumn(mainContent, leftHtml, rightHtml, leftHeader) {
    mainContent.innerHTML = `
        <div class="left-column">
            ${leftHeader ? `<div class="left-column__header">${leftHeader}</div>` : ''}
            <div class="left-column__body">${leftHtml}</div>
        </div>
        <div class="right-column">
            <div class="right-column__toolbar" id="right-toolbar"></div>
            <div class="right-column__view-area right-column__view-area--single" id="right-view-area"></div>
        </div>
    `;
}

// ============================================================
// Initialization
// ============================================================

async function init() {
    console.log('[App] initializing...');

    const appEl = document.getElementById('app');
    if (!appEl) {
        console.error('[App] #app element not found');
        return;
    }

    // 1. Load config
    config = await loadConfig();
    console.log('[App] config loaded');

    // 2. Setup API
    apiManager = new ApiManager(config.backend?.base_url || 'http://localhost:8000');

    // 3. Setup SSE
    sseManager = new SseManager();

    // 4. Setup WebSocket
    const wsUrl = (config.backend?.base_url || 'http://localhost:8000').replace(/^http/, 'ws') + (config.backend?.ws_endpoint || '/ws');
    wsManager = new WsManager(wsUrl);

    // 5. Render root layout
    renderRootLayout(appEl);

    // 6. Initialize 3D scene (shared)
    sharedScene3D = new Scene3D();
    sharedFieldRenderer = new FieldRenderer(sharedScene3D);
    sharedDroneModel = new DroneModel(sharedScene3D);
    sharedTrajectoryLine = new TrajectoryLine(sharedScene3D);
    sharedWaypointMarker = new WaypointMarker(sharedScene3D);

    // 7. Initialize StatusBar
    const statusBarEl = document.getElementById('status-bar');
    const statusBar = new StatusBar(statusBarEl);
    statusBar.mount();
    store.subscribe('connection', () => statusBar.mount());
    store.subscribe('drone', () => statusBar.mount());
    store.subscribe('flight', () => statusBar.mount());

    // 8. Initialize BottomBar
    const bottomBarEl = document.getElementById('bottom-bar');
    const bottomBar = new BottomBar(bottomBarEl);
    bottomBar.mount();
    store.subscribe('flight', () => bottomBar.mount());
    store.subscribe('trajectory', () => bottomBar.mount());

    // 9. Initialize ConnectionOverlay
    const overlayEl = document.getElementById('connection-overlay');
    const connectionOverlay = new ConnectionOverlay(overlayEl);
    store.subscribe('connection', (val) => {
        if (val === 'disconnected') {
            connectionOverlay.show();
        } else {
            connectionOverlay.hide();
        }
    });

    // 10. Initialize Chat Dock
    const chatContainer = document.createElement('div');
    chatContainer.id = 'chat-dock-container';
    document.querySelector('.app-container').appendChild(chatContainer);
    chatPanel = new ChatPanel(chatContainer);

    // 11. Initialize Floating Ball
    const floatingBallContainer = document.createElement('div');
    floatingBallContainer.id = 'floating-ball-container';
    document.querySelector('.app-container').appendChild(floatingBallContainer);
    const floatingBall = new FloatingBall(floatingBallContainer);

    // 11b. Initialize ShortcutEditor (modal, shown on demand)
    const shortcutEditor = new ShortcutEditor();

    // 12. Initialize Router
    const pageContainer = document.getElementById('page-container');
    router = new Router(pageContainer);

    // Register pages
    router.register('#/overview', new OverviewPage());
    router.register('#/alpha', new AlphaPage());
    router.register('#/beta', new BetaPage());
    router.register('#/history', new HistoryPage());
    router.register('#/settings', new SettingsPage());

    router.init();

    // 13. Connect WebSocket
    wsManager.connect();

    // Register WS handlers
    _registerWsHandlers();

    // 14. Fetch field config
    try {
        const fieldData = await apiManager.getFieldConfig();
        if (fieldData) {
            store.batch(() => {
                if (fieldData.boundary) store.set('field.boundary', fieldData.boundary);
                if (fieldData.obstacles) store.set('field.obstacles', fieldData.obstacles);
                if (fieldData.home) store.set('field.home', fieldData.home);
            });
            sharedFieldRenderer.updateFromField(store.get('field'));
        }
    } catch (e) {
        console.warn('[App] could not fetch field config, using defaults:', e.message);
        sharedFieldRenderer.updateFromField(store.get('field'));
    }

    // 15. Visibility change handler (pause/resume 3D)
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            sharedScene3D.pause();
        } else {
            sharedScene3D.resume();
        }
    });

    // 16. beforeunload — save config
    window.addEventListener('beforeunload', () => {
        const savedConfig = {};
        if (config?.display?.theme) savedConfig.theme = config.display.theme;
        if (config?.display?.language) savedConfig.language = config.display.language;

        const existing = JSON.parse(localStorage.getItem('flight-control-config') || '{}');
        Object.assign(existing, { display: { ...(existing.display || {}), ...savedConfig } });
        // Don't save backend endpoints — _ prefixed are protected
        localStorage.setItem('flight-control-config', JSON.stringify(existing));
    });

    // 17. Tab bar active state
    _syncTabBar();

    console.log('[App] initialized');
}

/**
 * Register WebSocket message handlers.
 */
function _registerWsHandlers() {
    // Pose updates
    wsManager.on('pose', (payload) => {
        if (!payload) return;
        store.batch(() => {
            if (payload.position) {
                store.set('drone.position', payload.position);
                sharedDroneModel.setTargetPosition(payload.position);
                sharedTrajectoryLine.updateFlown([payload.position]);
            }
            if (payload.velocity) store.set('drone.velocity', payload.velocity);
            if (payload.attitude) store.set('drone.attitude', payload.attitude);
            if (payload.battery != null) store.set('drone.battery', payload.battery);
            if (payload.gps) store.set('drone.gps', payload.gps);
            if (payload.state) store.set('drone.state', payload.state);
            store.set('drone.timestamp', Date.now());
            store.set('drone.connected', true);
        });
    });

    // Status updates
    wsManager.on('status', (payload) => {
        if (!payload) return;
        store.batch(() => {
            if (payload.mode != null) store.set('flight.mode', payload.mode);
            if (payload.status != null) store.set('flight.status', payload.status);
            if (payload.current_segment != null) store.set('flight.currentSegment', payload.current_segment);
            if (payload.total_segments != null) store.set('flight.totalSegments', payload.total_segments);
            if (payload.current_action != null) store.set('flight.currentAction', payload.current_action);
            if (payload.progress != null) store.set('flight.progress', payload.progress);
        });
        bus.emit('status-update', payload);
    });

    // Alerts
    wsManager.on('alert', (payload) => {
        bus.emit('alert', payload);
    });

    // Rejected proposals
    wsManager.on('reject', (payload) => {
        bus.emit('proposal-rejected', payload);
    });

    // Alpha output (trajectory from alpha backend)
    wsManager.on('alpha_output', (payload) => {
        if (!payload) return;
        store.batch(() => {
            if (payload.planned) store.set('trajectory.planned', payload.planned);
            if (payload.waypoints) store.set('trajectory.waypoints', payload.waypoints);
            if (payload.current_target) store.set('trajectory.currentTarget', payload.current_target);
        });
        if (payload.planned) sharedTrajectoryLine.setPlanned(payload.planned);
        if (payload.waypoints) sharedWaypointMarker.setWaypoints(payload.waypoints);
        if (payload.current_target) sharedWaypointMarker.setTarget(payload.current_target);
        bus.emit('alpha-output', payload);
    });

    // Link status
    wsManager.on('link_status', (payload) => {
        if (!payload) return;
        store.batch(() => {
            if (payload.backend_a != null) store.set('connection.backendA', payload.backend_a);
            if (payload.backend_b != null) store.set('connection.backendB', payload.backend_b);
            if (payload.drone != null) store.set('connection.drone', payload.drone);
            if (payload.llm != null) store.set('connection.llm', payload.llm);
        });
    });

    // Voice TTS
    wsManager.on('voice_tts', (payload) => {
        if (payload && payload.audio) {
            AudioPlayer.play(payload.audio);
        }
    });

    // Connection status from WS manager's own events
    wsManager.on('__event:open', () => {
        store.set('connection.ws', 'connected');
        store.set('connection.retryCount', 0);
    });

    wsManager.on('__event:close', () => {
        store.set('connection.ws', 'disconnected');
    });

    // Handle reconnection retries from ws dispatch
    wsManager.on('connection', (payload) => {
        if (payload && payload.status) {
            store.set('connection.ws', payload.status);
            if (payload.retryCount != null) {
                store.set('connection.retryCount', payload.retryCount);
            }
        }
    });
}

/**
 * Sync the tab bar active state with the current hash.
 */
function _syncTabBar() {
    const updateTabs = () => {
        const hash = window.location.hash || '#/overview';
        document.querySelectorAll('.tab-bar__item').forEach((item) => {
            const href = item.getAttribute('href');
            item.classList.toggle('tab-bar__item--active', href === hash);
        });
    };
    window.addEventListener('hashchange', updateTabs);
    updateTabs();
}

// ============================================================
// Boot
// ============================================================
document.addEventListener('DOMContentLoaded', init);
