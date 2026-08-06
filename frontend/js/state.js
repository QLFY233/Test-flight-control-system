/**
 * Global State Management — Publish-Subscribe Store
 * Supports dot-notation path access, batched updates, and path-based subscriptions.
 */

class Store {
    constructor(initial) {
        this._state = JSON.parse(JSON.stringify(initial));
        this._listeners = new Map(); // path -> Set<callback>
        this._batchMode = false;
        this._batchChanges = [];
        this._batchDepth = 0;
    }

    /**
     * Get a value at a dot-notation path.
     * @param {string} path - e.g. "drone.position.x"
     * @returns {any}
     */
    get(path) {
        if (!path) return this._state;
        const keys = path.split('.');
        let current = this._state;
        for (const key of keys) {
            if (current == null || typeof current !== 'object') return undefined;
            current = current[key];
        }
        return current;
    }

    /**
     * Set a value at a dot-notation path. Notifies subscribers.
     * @param {string} path - e.g. "drone.position"
     * @param {any} value
     */
    set(path, value) {
        if (!path) return;
        const keys = path.split('.');
        let current = this._state;
        for (let i = 0; i < keys.length - 1; i++) {
            const key = keys[i];
            if (current[key] == null || typeof current[key] !== 'object') {
                current[key] = {};
            }
            current = current[key];
        }
        const lastKey = keys[keys.length - 1];
        const oldValue = current[lastKey];
        if (oldValue === value) return; // no change

        current[lastKey] = value;

        if (this._batchMode) {
            this._batchChanges.push({ path, value, oldValue });
        } else {
            this._notify(path, value, oldValue);
        }
    }

    /**
     * Execute multiple set() calls inside a function, only notify once at the end.
     * @param {Function} fn
     */
    batch(fn) {
        this._batchDepth++;
        const wasBatching = this._batchMode;
        this._batchMode = true;
        if (wasBatching) {
            // Nested batch: just execute directly, outer batch owns the flush
            try {
                fn();
            } finally {
                this._batchDepth--;
                if (this._batchDepth === 0) {
                    this._batchMode = false;
                    this._flushBatch();
                }
            }
        } else {
            this._batchChanges = [];
            try {
                fn();
            } finally {
                this._batchDepth--;
                this._batchMode = false;
                if (this._batchChanges.length > 0) {
                    this._flushBatch();
                }
            }
        }
    }

    _flushBatch() {
        const notified = new Set();
        for (const change of this._batchChanges) {
            if (!notified.has(change.path)) {
                notified.add(change.path);
                this._notify(change.path, change.value, change.oldValue);
            }
        }
        this._batchChanges = [];
    }

    /**
     * Subscribe to changes at a path or prefix.
     * Returns an unsubscribe function.
     * @param {string} path - dot-path 前缀订阅；通知值可能是前缀路径下的标量/对象值
     *   （如订阅 'drone' 会在 drone.position / drone.velocity 等任意子路径变更时触发），
     *   回调收到 (newValue, oldValue, changedPath)。
     * @param {Function} callback - receives (newValue, oldValue, path)
     * @returns {Function} unsubscribe
     */
    subscribe(path, callback) {
        if (!this._listeners.has(path)) {
            this._listeners.set(path, new Set());
        }
        this._listeners.get(path).add(callback);

        return () => {
            const set = this._listeners.get(path);
            if (set) {
                set.delete(callback);
                if (set.size === 0) {
                    this._listeners.delete(path);
                }
            }
        };
    }

    /**
     * Get the full state tree (shallow clone of root keys).
     * @returns {object}
     */
    getState() {
        return this._state;
    }

    /**
     * Internal: notify all subscribers that match a path.
     */
    _notify(path, value, oldValue) {
        const keys = path.split('.');
        // Walk from most-specific to least-specific
        for (let i = 0; i < keys.length; i++) {
            const prefix = keys.slice(0, keys.length - i).join('.');
            const set = this._listeners.get(prefix);
            if (set) {
                for (const cb of set) {
                    try {
                        cb(value, oldValue, path);
                    } catch (e) {
                        console.error(`[Store] subscriber error for "${prefix}":`, e);
                    }
                }
            }
        }
        // Also notify wildcard subscribers
        const set = this._listeners.get('*');
        if (set) {
            for (const cb of set) {
                try {
                    cb(value, oldValue, path);
                } catch (e) {
                    console.error('[Store] wildcard subscriber error:', e);
                }
            }
        }
    }
}

// ============================================================
// Initial State
// ============================================================

const initial = {
    // Connection status
    connection: {
        ws: 'disconnected',    // 'connected' | 'connecting' | 'disconnected'
        backendA: 'unknown',   // 'ok' | 'error' | 'unknown'
        backendB: 'unknown',
        drone: 'unknown',
        llm: 'unknown',
        retryCount: 0,
    },

    // Drone real-time pose
    drone: {
        connected: false,
        position: { x: 0, y: 0, z: 0 },
        velocity: { vx: 0, vy: 0, vz: 0 },
        accel: { ax: 0, ay: 0, az: 0 },
        angularVelocity: { wx: 0, wy: 0, wz: 0 },
        attitude: { roll: 0, pitch: 0, yaw: 0 },
        battery: 100,
        gps: { lat: 0, lon: 0, alt: 0, fix: 0 },
        state: 'idle', // 'idle' | 'armed' | 'flying' | 'rtl' | 'landing' | 'error'
        timestamp: null,
    },

    // Flight session state
    flight: {
        sessionId: null,
        status: 'idle',         // 冻结枚举（shared/protocol.py schema_version=2）: 'idle' | 'hovering' | 'planned' | 'executing' | 'completed' | 'aborted'
        taskTitle: '',
        taskDescription: '',
        currentAction: 0,       // current action index in actionSequence
        totalActions: 0,        // total actions in plan
        currentActionCode: '',  // current ActionCommand code (e.g. "MOVE_TO", "HOVER")
        currentActionParams: null, // current ActionCommand params (target, speed...)
        progress: 0,            // 0-100
        mode: '',               // current flight mode string
        startTime: null,
        environmentId: null,
    },

    // Trajectory data (schema_version=2: ActionCommand 格式, 废弃 segments/waypoints)
    trajectory: {
        flown: [],              // [{x, y, z, t}, ...]
        planned: [],            // [{x, y, z}, ...]
        actionSequence: [],     // ActionCommand entries: [{code, params: {target, speed, ...}}]
        currentTarget: null,    // {x, y, z}
    },

    // Beta (planning) state
    beta: {
        currentPlan: null,       // flight plan object or null
        proposals: [],           // list of plan proposals
        pendingApproval: false,
        fieldOverlay: false,
    },

    // Chat history
    chatHistory: [],

    // History
    history: {
        sessions: [],
        selectedSession: null,
        playbackState: 'stopped', // 'playing' | 'paused' | 'stopped'
        playbackSpeed: 1,
        playbackTime: 0,
        // 2026-08-06: 会话回放数据集 (独立路径, 不污染实时 trajectory.flown)
        playback: {
            dataset: null,   // {sessionId, points:[{t,x,y,z,vx,vy,vz,ax,ay,az,wx,wy,wz}], tStart, tEnd, duration, taskInfo, planned}
            index: 0,        // 当前回放帧索引
        },
    },

    // Field (schema_version=2: obstacles 预编废弃, 阶段2/4 由雷达在线感知替代)
    field: {
        boundary: { xMin: -50, xMax: 50, yMin: -50, yMax: 50, zMin: 0, zMax: 30 },
        obstacles: [],           // [DEPRECATED 2026-07-07] 雷达在线感知替代; 保留空数组向前兼容
        home: { x: 0, y: 0, z: 0 },
    },

    // Environment
    environment: {
        id: null,
        temperature: 25,
        humidity: 60,
        windSpeed: 0,
        windDirection: 0,
        pressure: 1013,
        location: '',
        description: '',
    },

    // UI
    ui: {
        viewMode: 1,            // 1, 2, or 3 panels
        viewSources: ['chart'],    // e.g. ['3d', 'chart', 'video']
        chatOpen: true,
        chatCollapsed: false,
        theme: 'dark',
        language: 'zh-CN',
    },
};

const store = new Store(initial);
export default store;
