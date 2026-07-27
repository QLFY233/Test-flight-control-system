/**
 * Show Mock Layer — 完整假数据模拟系统。
 * 模拟 WS/SSE/REST 全部后端通信，展示前端全部功能。
 *
 * 模拟场景：一次完整试飞任务
 *   idle → 起飞 → 机动飞行(8字航线) → 悬停 → 异常告警 → β处置建议 → 降落
 */

// ==========================================================
// Mock Data — 静态假数据
// ==========================================================

// Helper: generate today-based date strings
function _today(hours, minutes) {
    const d = new Date();
    d.setHours(hours || 0, minutes || 0, 0, 0);
    const pad = (n) => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':00';
}
function _yesterday(hours, minutes) {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    d.setHours(hours || 0, minutes || 0, 0, 0);
    const pad = (n) => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':00';
}

const NOW = _today(14, 30);
const TODAY_AM = _today(9, 30);
const YESTERDAY_PM = _yesterday(16, 0);
const YESTERDAY_AM = _yesterday(8, 30);
const NOW_ALERT = _today(14, 30, 40);
const NOW_ENV = _today(14, 30);
const NOW_ANALYTICS = _today(14, 31);

const MOCK_SESSIONS = [
    { id: '20260726143012', name: '8字航线验证', date: NOW, created_at: NOW,
      task_title: '试飞测试 #1 — 8字航线验证', task_summary: '执行8字航线飞行，验证飞控响应能力。包括起飞、机动、悬停、降落完整流程。',
      description: '8字航线试飞验证任务，飞行时间约46秒', status: 'success', environment_id: 1,
      trajectory_type: 'figure8', duration: 46,
      beta_plan: '执行8字航线飞行，验证飞控响应', alpha_actions: 'takeoff → goto → figure8 → land' },
    { id: '20260726093005', name: '矩形巡逻', date: TODAY_AM, created_at: TODAY_AM,
      task_title: '试飞测试 #2 — 矩形巡逻', task_summary: '沿场地边界执行矩形巡逻航线，验证航点切换和路径跟踪精度。',
      description: '矩形巡逻验证，飞行时间约40秒', status: 'success', environment_id: 1,
      trajectory_type: 'square', duration: 40,
      beta_plan: '执行矩形巡逻航线', alpha_actions: 'takeoff → goto → square → land' },
    { id: '20260725160000', name: '之字形扫描', date: YESTERDAY_PM, created_at: YESTERDAY_PM,
      task_title: '试飞测试 #3 — 之字形扫描', task_summary: '之字形扫描航线，用于测试区域覆盖和速度切换。因速度超限触发安全中止。',
      description: '高速扫描测试，因超速告警中止', status: 'error', environment_id: 2,
      trajectory_type: 'zigzag', duration: 35, abort_at: 18,
      beta_plan: '测试高速机动性能', alpha_actions: 'takeoff → zigzag → abort' },
    { id: '20260725083000', name: '螺旋巡航', date: YESTERDAY_AM, created_at: YESTERDAY_AM,
      task_title: '试飞测试 #4 — 螺旋巡航', task_summary: '螺旋展开巡航测试，验证边界约束夹紧效果。靠近边界处自动限速，因边界告警提前返航。',
      description: '螺旋巡航边界约束验证，触发软边界告警后返航', status: 'warning', environment_id: 1,
      trajectory_type: 'spiral', duration: 38, abort_at: 24,
      beta_plan: '测试场地边界约束', alpha_actions: 'takeoff → spiral → return_home → land' },
];

const MOCK_DATA_CATEGORIES = [
    { id: 'data-telemetry', name: '遥测数据包', type: 'telemetry', date: NOW,
      task_title: '遥测数据 — ' + NOW.substring(0, 10) + ' 14:30', task_summary: '10Hz 位姿/速度/IMU 完整遥测记录，共 460 条数据点',
      description: '包含位置(x,y,z)、速度(vx,vy,vz)、姿态(roll,pitch,yaw)、IMU原始数据', status: 'info' },
    { id: 'data-alert', name: '告警记录', type: 'alert', date: _today(14, 30, 40),
      task_title: '告警记录 — SPEED_EXCEED', task_summary: '速度超限告警：1.62m/s 超出预设上限 1.5m/s',
      description: '告警级别 warning，触发 β 处置建议，后续调整速度约束至 1.2m/s', status: 'warning' },
    { id: 'data-env', name: '环境快照', type: 'environment', date: NOW_ENV,
      task_title: '环境条件 — 室内标准', task_summary: '温度 25°C，湿度 60%，无风，气压 1013hPa',
      description: '室内试验场环境快照', status: 'info' },
    { id: 'data-analytics', name: '频谱分析结果', type: 'analytics', date: NOW_ANALYTICS,
      task_title: 'FFT 分析结果', task_summary: '主频 0.05Hz，振幅 0.12，无明显异常频率分量',
      description: '遥测数据 FFT 频谱分析，飞行状态正常', status: 'info' },
];

const MOCK_ENVIRONMENTS = [
    { id: 1, name: '室内标准', data: { temperature: 25, humidity: 60, wind: [0, 0, 0], pressure: 1013, location: '室内试验场' } },
    { id: 2, name: '室外轻风', data: { temperature: 28, humidity: 45, wind: [0.5, -0.2, 0.1], pressure: 1010, location: '外场A区' } },
];

const MOCK_FIELD = {
    boundary: { xMin: 0, xMax: 5, yMin: 0, yMax: 4, zMin: 0, zMax: 3 },
    obstacles: [],
    home: { x: 0, y: 0, z: 0.5 },
};

const MOCK_OVERVIEW = {
    total_sessions: 12, total_flight_time_minutes: 47.5,
    sessions_today: 3, alerts_today: 2, avg_flight_time: 3.96,
    recent_sessions: MOCK_SESSIONS,
};

const MOCK_TELEMETRY_SNAPSHOT = {
    session_id: '20260726143012',
    points: Array.from({ length: 50 }, (_, i) => ({
        t: i * 0.2,
        x: 1.5 + Math.cos(i * 0.3) * 1.5, y: 2 + Math.sin(i * 0.3) * 1.2, z: 1.0 + Math.sin(i * 0.15) * 0.5,
        vx: -Math.sin(i * 0.3) * 0.5, vy: Math.cos(i * 0.3) * 0.4, vz: Math.cos(i * 0.15) * 0.05,
    })),
};

// ==========================================================
// MockWsManager — 模拟 WebSocket 数据推送
// ==========================================================

class MockWsManager {
    constructor(url) {
        this.url = url;
        this.handlers = new Map();
        this._timers = [];
        this._status = 'disconnected';
        this._flightPhase = 'idle';
        this._phaseStartTime = 0;
        this._simTime = 0;
        this._dronePos = { x: 1.5, y: 2.0, z: 0.05 };
        this._droneVel = { vx: 0, vy: 0, vz: 0 };
        this._droneYaw = 0;
        this._actionIndex = 0;
        this._totalActions = 5;
        this._alertFired = false;
        this._figure8Angle = 0;
    }

    connect() {
        this._status = 'connecting';
        setTimeout(() => {
            this._status = 'connected';
            this._dispatch({ type: 'connection', payload: { status: 'connected' } });

            const openHandlers = this.handlers.get('__event:open');
            if (openHandlers) {
                for (const h of openHandlers) { try { h({}); } catch (e) {} }
            }

            // 链路状态 — 显示全部在线
            this._dispatch({ type: 'link_status', payload: {
                backend_a: 'ok', backend_b: 'ok', drone: 'ok', llm: 'ok'
            }});

            // 不自动开始模拟，演示数据仅在历史页回放
        }, 800);
    }

    send(type, payload = {}) {
        console.log('[MockWS] send:', type, payload);
        // 如果是语音帧，模拟 STT 结果
        if (type === 'voice_frame') {
            setTimeout(() => {
                this._dispatch({ type: 'voice_stt_result', payload: { text: '[模拟语音识别] 执行悬停', is_final: true } });
            }, 1000);
        }
        return true;
    }

    on(type, handler) {
        if (!this.handlers.has(type)) this.handlers.set(type, new Set());
        this.handlers.get(type).add(handler);
    }

    off(type, handler) {
        const set = this.handlers.get(type);
        if (set) set.delete(handler);
    }

    disconnect() {
        this._clearTimers();
        this._status = 'disconnected';
    }

    getStatus() { return this._status; }

    // ---- Internal ----

    _startSimulation() {
        // Phase timeline (seconds): idle(0-2) → takeoff(2-8) → maneuver(8-25) → hover(25-28) → alert(28) → maneuver(28-40) → landing(40-46) → completed(46+)
        this._simTime = 0;
        this._dronePos = { x: 1.0, y: 0.5, z: 0.05 };
        this._droneVel = { vx: 0, vy: 0, vz: 0 };
        this._droneYaw = 0;
        this._actionIndex = 0;
        this._totalActions = 5;
        this._alertFired = false;
        this._figure8Angle = 0;

        // 初始状态
        this._pushStatus('idle', '', 1, 5, 0);

        // Reset trajectory for fresh simulation
        this._dispatch({ type: 'trajectory_reset', payload: {} });

        // Push planned trajectory immediately
        this._tickAlphaOutput();

        // 10Hz pose + telemetry 推送
        this._timers.push(setInterval(() => this._tick(), 100));

        // 2s status 更新
        this._timers.push(setInterval(() => this._tickStatus(), 2000));

        // 每 15s alpha_output
        this._timers.push(setInterval(() => this._tickAlphaOutput(), 15000));
    }

    _tick() {
        this._simTime += 0.1;
        this._updateDronePhysics();
        this._pushPose();
    }

    _updateDronePhysics() {
        const t = this._simTime;
        const p = this._dronePos;
        const PI = Math.PI;

        if (t < 2) {
            // idle on ground
            this._droneVel = { vx: 0, vy: 0, vz: 0 };
        } else if (t < 8) {
            // takeoff: ascend to ~1.5m
            const targetZ = 1.5;
            p.z += (targetZ - p.z) * 0.1 + 0.02;
            this._droneVel = { vx: 0, vy: 0, vz: (targetZ - p.z) * 0.5 + 0.3 };
        } else if (t < 25) {
            // figure-8 maneuver
            this._figure8Angle += 0.04;
            const a = this._figure8Angle;
            const sx = 1.5; // scale X (m)
            const sy = 1.0; // scale Y (m)
            const cx = 2.5; // center X
            const cy = 2.0; // center Y
            // Parametric figure-8: x = sin(t), y = sin(t)cos(t)
            const tx = cx + Math.sin(a) * sx;
            const ty = cy + Math.sin(a) * Math.cos(a) * sy;
            const tz = 1.5 + Math.sin(a * 0.3) * 0.3;

            p.x += (tx - p.x) * 0.15;
            p.y += (ty - p.y) * 0.15;
            p.z += (tz - p.z) * 0.1;

            const vx = (tx - p.x) * 1.5;
            const vy = (ty - p.y) * 1.5;
            const vz = (tz - p.z) * 1.0;
            this._droneVel = { vx: Math.round(vx * 100) / 100, vy: Math.round(vy * 100) / 100, vz: Math.round(vz * 100) / 100 };
            this._droneYaw = Math.atan2(vy, vx) * (180 / PI);
        } else if (t < 28) {
            // hover at (3.5, 2.0, 1.5)
            const tx = 3.5, ty = 2.0, tz = 1.5;
            p.x += (tx - p.x) * 0.1;
            p.y += (ty - p.y) * 0.1;
            p.z += (tz - p.z) * 0.1;
            this._droneVel = { vx: 0, vy: 0, vz: 0 };
        } else if (t < 40) {
            // resume figure-8 after alert
            this._figure8Angle += 0.05;
            const a = this._figure8Angle;
            const tx = 2.5 + Math.sin(a) * 2.0;
            const ty = 2.0 + Math.sin(a) * Math.cos(a) * 1.5;
            const tz = 1.5 + Math.sin(a * 0.3) * 0.3;
            p.x += (tx - p.x) * 0.15;
            p.y += (ty - p.y) * 0.15;
            p.z += (tz - p.z) * 0.1;
            const vx = (tx - p.x) * 1.5, vy = (ty - p.y) * 1.5, vz = (tz - p.z) * 1.0;
            this._droneVel = { vx: Math.round(vx * 100) / 100, vy: Math.round(vy * 100) / 100, vz: Math.round(vz * 100) / 100 };
            this._droneYaw = Math.atan2(vy, vx) * (180 / PI);
        } else if (t < 46) {
            // landing
            const tx = 0.0, ty = 0.0, tz = 0.05;
            p.x += (tx - p.x) * 0.12;
            p.y += (ty - p.y) * 0.12;
            p.z += (tz - p.z) * 0.08;
            this._droneVel = { vx: (tx - p.x) * 0.5, vy: (ty - p.y) * 0.5, vz: -Math.max(0.05, p.z * 0.3) };
        } else {
            // completed, stay on ground
            this._droneVel = { vx: 0, vy: 0, vz: 0 };
            p.z = 0.05;
            if (this._flightPhase !== 'completed') {
                this._flightPhase = 'completed';
                this._pushStatus('completed', '', 5, 5, 100);
            }
        }

        // Round positions
        p.x = Math.round(p.x * 100) / 100;
        p.y = Math.round(p.y * 100) / 100;
        p.z = Math.round(p.z * 100) / 100;

        // Clamp within boundary
        p.x = Math.max(0, Math.min(5, p.x));
        p.y = Math.max(0, Math.min(4, p.y));
        p.z = Math.max(0.01, Math.min(3, p.z));
    }

    _pushPose() {
        this._dispatch({ type: 'pose', payload: {
            position: { x: this._dronePos.x, y: this._dronePos.y, z: this._dronePos.z },
            velocity: this._droneVel,
            attitude: { roll: 0, pitch: 0, yaw: this._droneYaw },
            timestamp: Date.now(),
        }});

        // telemetry (not pushed to frontend per spec, but included for completeness)
        this._dispatch({ type: 'telemetry', payload: {
            vel: this._droneVel,
            accel: { ax: 0, ay: 0, az: 0 },
            imu: { ax: 0, ay: 0, az: 9.8, gx: 0, gy: 0, gz: 0 },
            ts: Date.now() / 1000,
        }});
    }

    _pushStatus(flightStatus, mode, currentAction, totalActions, progress) {
        this._dispatch({ type: 'status', payload: {
            status: flightStatus,
            mode: mode,
            current_action: currentAction,
            total_actions: totalActions,
            current_action_code: currentAction > 0 && currentAction <= 5
                ? ['takeoff', 'goto', 'hover', 'figure8', 'land'][currentAction - 1] : '',
            progress: progress,
            taskId: '20260726143012',
            task_id: '20260726143012',
        }});
    }

    _tickStatus() {
        const t = this._simTime;
        let flightStatus = 'idle', mode = 'auto', currentAction = 0;

        if (t < 2) { flightStatus = 'idle'; currentAction = 0; }
        else if (t < 8) { flightStatus = 'executing'; currentAction = 1; mode = 'auto'; }
        else if (t < 25) { flightStatus = 'executing'; currentAction = 2; mode = 'auto'; }
        else if (t < 28) { flightStatus = 'executing'; currentAction = 3; mode = 'auto'; }
        else if (t < 40) { flightStatus = 'executing'; currentAction = 4; mode = 'auto'; }
        else if (t < 46) { flightStatus = 'executing'; currentAction = 5; mode = 'auto'; }
        else { flightStatus = 'completed'; currentAction = 5; }

        this._pushStatus(flightStatus, mode, currentAction, 5, Math.min(100, Math.floor(t / 46 * 100)));

        // Fire alert at t=28s (once)
        if (t >= 28 && !this._alertFired) {
            this._alertFired = true;
            this._dispatch({ type: 'alert', payload: {
                level: 'warning', code: 'SPEED_EXCEED',
                detail: '速度 1.62m/s 超出预设 safe 上限 1.5m/s',
                suggestion: '', ts: Date.now() / 1000,
            }});
        }
    }

    _tickAlphaOutput() {
        if (this._simTime < 2) return;
        const t = this._simTime;
        const actionMap = [
            { code: 'takeoff', value: 1.5, comment: '起飞到 1.5m' },
            { code: 'goto', target: [3.5, 2.0, 1.5], comment: '飞往起航点' },
            { code: 'hover', value: 2.0, comment: '等待稳定' },
            { code: 'figure8', comment: '8字航线' },
            { code: 'land', comment: '返回降落' },
        ];

        let idx = 0;
        if (t < 8) idx = 0;
        else if (t < 25) idx = 1;
        else if (t < 28) idx = 2;
        else if (t < 40) idx = 3;
        else idx = 4;

        // Generate full planned trajectory (same figure-8 as _updateDronePhysics)
        const planned = [];
        const PI = Math.PI;
        const n = 350;
        for (let i = 0; i < n; i++) {
            const a = i * 0.04;
            const ti = i * 0.04;
            let px, py, pz;
            if (ti < 6) {
                // takeoff
                px = 1.0; py = 0.5; pz = 0.1 + (ti / 6) * 1.4;
            } else if (ti < 23) {
                // figure-8
                const b = (ti - 6) * (Math.PI * 2 / 17);
                px = 2.5 + Math.sin(b) * 1.5;
                py = 2.0 + Math.sin(b) * Math.cos(b) * 1.0;
                pz = 1.5 + Math.sin(b * 0.3) * 0.3;
            } else if (ti < 26) {
                // hover
                px = 3.5; py = 2.0; pz = 1.5;
            } else if (ti < 38) {
                // resume figure-8
                const b = (ti - 26) * (Math.PI * 2 / 12);
                px = 2.5 + Math.sin(b) * 2.0;
                py = 2.0 + Math.sin(b) * Math.cos(b) * 1.5;
                pz = 1.5 + Math.sin(b * 0.3) * 0.3;
            } else {
                // landing
                const frac = (ti - 38) / 6;
                px = 2.5 * (1 - frac);
                py = 2.0 * (1 - frac);
                pz = 1.5 * (1 - frac) + 0.05 * frac;
            }
            planned.push({ x: Math.round(px * 100) / 100, y: Math.round(py * 100) / 100, z: Math.round(pz * 100) / 100 });
        }

        this._dispatch({ type: 'alpha_output', payload: {
            planned: planned,
            action_sequence: [actionMap[idx]],
            current_target: { x: this._dronePos.x + 1, y: this._dronePos.y, z: this._dronePos.z },
            remaining_actions: 5 - idx - 1,
        }});
    }

    _clearTimers() {
        this._timers.forEach(clearInterval);
        this._timers = [];
    }

    _dispatch(data) {
        const typeHandlers = this.handlers.get(data.type);
        if (typeHandlers) {
            for (const handler of typeHandlers) {
                try { handler(data.payload, data); } catch (e) { console.error('[MockWS] handler err:', e); }
            }
        }
        const starHandler = this.handlers.get('*');
        if (starHandler) {
            for (const handler of starHandler) {
                try { handler(data.payload, data); } catch (e) { console.error('[MockWS] * err:', e); }
            }
        }
    }
}

// ==========================================================
// MockSseManager — 模拟 β 对话流
// ==========================================================

const CHAT_RESPONSES = {
    default: {
        chunks: [
            '收到指令，正在分析...\n\n',
            '根据当前飞行状态，我建议执行以下方案：\n\n',
            '**飞行计划概要**\n',
            '- 起飞至 1.5m 安全高度\n',
            '- 执行巡航机动\n',
            '- 保持边界内飞行\n',
            '- 完成任务后返回降落\n\n',
            '> 预计飞行时间：约 45 秒\n',
            '> 安全约束：速度 ≤1.5m/s，高度 ≤2.5m\n\n',
            '是否批准此计划？',
        ],
        toolCalls: [
            { name: 'get_current_pose', args: {}, result: { x: 1.0, y: 0.5, z: 0.05, yaw: 0 } },
            { name: 'get_field_map', args: {}, result: { boundary: MOCK_FIELD.boundary, home: MOCK_FIELD.home } },
        ],
        plan: {
            task_id: '20260726143012', schema_version: 2,
            actions: [
                { code: 'takeoff', value: 1.5, units: 'm', comment: '起飞' },
                { code: 'goto', target: [3.5, 2.0, 1.5], units: 'm', comment: '飞往起航点' },
                { code: 'hover', value: 2.0, units: 's', comment: '稳定悬停' },
                { code: 'goto', target: [0.5, 1.0, 1.5], units: 'm', comment: '返回' },
                { code: 'land', comment: '降落' },
            ],
            safety_constraints: { speed_max: 1.5, ceiling: 2.5, floor: 0.3, boundary: [[0,0,0],[5,4,3]] },
        },
    },

    '分析': {
        chunks: [
            '正在分析遥测数据...\n\n',
            '**分析结果**\n',
            '- 当前位置：(1.5, 2.0, 1.0) m\n',
            '- 当前速度：0.5 m/s\n',
            '- 飞行状态：正常\n\n',
            'FFT 频谱分析显示无明显异常频率分量。\n',
            '建议继续当前飞行计划。',
        ],
        toolCalls: [
            { name: 'get_current_pose', args: {}, result: { x: 1.5, y: 2.0, z: 1.0 } },
            { name: 'analytics_stats', args: { metric: 'velocity' }, result: { mean: 0.52, std: 0.08, min: 0.3, max: 0.8 } },
            { name: 'analytics_fft', args: {}, result: { dominant_freq: 0.05, amplitude: 0.12 } },
        ],
        plan: null,
    },

    '告警': {
        chunks: [
            '收到告警信息，正在分析...\n\n',
            '**告警分析**\n',
            '- 告警类型：SPEED_EXCEED\n',
            '- 当前速度：1.62 m/s\n',
            '- 阈值上限：1.50 m/s\n\n',
            '**处置建议**\n',
            '1. 建议将速度限制降至 1.2 m/s\n',
            '2. 监控后续 5 秒速度趋势\n',
            '3. 如持续超速，考虑切换到 careful 模式\n\n',
            '是否需要我自动调整速度约束？',
        ],
        toolCalls: [
            { name: 'get_current_pose', args: {}, result: { x: 3.2, y: 2.1, z: 1.5, v: 1.62 } },
            { name: 'get_recent_telemetry', args: { window_sec: 5 }, result: { max_speed: 1.62 } },
        ],
        plan: null,
    },

    '环境': {
        chunks: [
            '当前环境条件：\n\n',
            '- 温度：25°C\n',
            '- 湿度：60%\n',
            '- 风速：(0, 0, 0) m/s\n',
            '- 气压：1013 hPa\n\n',
            '环境条件良好，适合飞行。',
        ],
        toolCalls: [
            { name: 'get_current_environment', args: {}, result: MOCK_ENVIRONMENTS[0].data },
        ],
        plan: null,
    },

    '历史': {
        chunks: [
            '查询历史试飞记录：\n\n',
            '- 共 12 次试飞会话\n',
            '- 今日 3 次：2 次完成，1 次中止\n',
            '- 累计飞行时间：47.5 分钟\n\n',
            '最近一次：2026-07-26 14:30，8字航线验证，已完成。',
        ],
        toolCalls: [
            { name: 'query_sessions', args: {}, result: MOCK_SESSIONS },
        ],
        plan: null,
    },
};

class MockSseManager {
    async sendMessage(endpoint, text, callbacks, signal) {
        const {
            onMessage = () => {}, onToolCall = () => {}, onToolResult = () => {},
            onPlan = () => {}, onComplete = () => {}, onError = () => {},
        } = callbacks;

        // Pick response template based on keywords
        let template = CHAT_RESPONSES.default;
        if (text.includes('分析') || text.includes('数据')) template = CHAT_RESPONSES['分析'];
        else if (text.includes('告警') || text.includes('异常')) template = CHAT_RESPONSES['告警'];
        else if (text.includes('环境') || text.includes('天气')) template = CHAT_RESPONSES['环境'];
        else if (text.includes('历史') || text.includes('记录')) template = CHAT_RESPONSES['历史'];

        try {
            // Simulate tool calls
            for (const tc of template.toolCalls) {
                await this._delay(400, signal);
                if (signal?.aborted) return;
                onToolCall(tc.name, tc.args);
                await this._delay(600, signal);
                if (signal?.aborted) return;
                onToolResult(tc.name, tc.result);
            }

            // Send chat plan if present
            if (template.plan) {
                await this._delay(500, signal);
                if (signal?.aborted) return;
                onPlan(template.plan);
            }

            // Stream text chunks
            for (const chunk of template.chunks) {
                await this._delay(chunk.length * 15 + 100, signal);
                if (signal?.aborted) return;
                onMessage(chunk);
            }

            // Assemble full text
            const fullText = template.chunks.join('');
            onComplete(fullText);
        } catch (e) {
            if (e.name === 'AbortError') { onComplete(''); return; }
            onError(e.message || String(e));
        }
    }

    _delay(ms, signal) {
        return new Promise((resolve, reject) => {
            const timer = setTimeout(resolve, ms);
            if (signal) {
                signal.addEventListener('abort', () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); }, { once: true });
            }
        });
    }
}

// ==========================================================
// MockApiManager — 模拟 REST API
// ==========================================================

class MockApiManager {
    constructor(baseUrl) { this.baseUrl = baseUrl; }

    async getOverview() { return MOCK_OVERVIEW; }
    async getSessions(params) {
        if (params?.type === 'data') return MOCK_DATA_CATEGORIES;
        let sessions = MOCK_SESSIONS;
        if (params?.status) sessions = sessions.filter(s => s.status === params.status);
        if (params?.keyword) {
            const kw = params.keyword.toLowerCase();
            sessions = sessions.filter(s => (s.task_title || s.name || '').toLowerCase().includes(kw) || (s.task_summary || '').toLowerCase().includes(kw));
        }
        return sessions;
    }
    async getTelemetry(sessionId) {
        return { session_id: sessionId || '20260726143012', points: MOCK_TELEMETRY_SNAPSHOT.points };
    }
    async getConversations(sessionId) {
        return [
            { agent: 'beta', role: 'human', content: '执行一次试飞测试', created_at: '2026-07-26T14:30:15' },
            { agent: 'beta', role: 'agent', content: '收到。正在规划飞行方案...', created_at: '2026-07-26T14:30:18' },
            { agent: 'beta', role: 'human', content: '批准', created_at: '2026-07-26T14:30:25' },
        ];
    }
    async getEnvironments() { return MOCK_ENVIRONMENTS; }
    async saveEnvironment(env) { return { id: 3, ...env }; }
    async getCurrentPose() {
        return { position: { x: 1.5, y: 2.0, z: 1.0 }, velocity: { vx: 0.3, vy: 0.2, vz: 0 }, attitude: { roll: 0, pitch: 0, yaw: 45 }, timestamp: Date.now() };
    }
    async createSession(config) { return { id: '20260726' + String(Math.floor(Math.random() * 900000 + 100000)), status: 'planned', ...config }; }
    async abortSession(sessionId) { return { id: sessionId, status: 'aborted' }; }
    async getProposals(sessionId) {
        return [{ id: 'prop-001', status: 'pending', intent: '8字航线', actions: CHAT_RESPONSES.default.plan.actions }];
    }
    async approveProposal(proposalId) { return { id: proposalId, status: 'approved' }; }
    async rejectProposal(proposalId, reason) { return { id: proposalId, status: 'rejected', reason }; }
    async getFieldConfig() { return MOCK_FIELD; }

    // Generic HTTP methods (for any un-mocked calls)
    async get(path, params) {
        if (path.includes('/api/overview')) return this.getOverview();
        if (path.includes('/api/sessions')) return this.getSessions(params);
        if (path.includes('/api/telemetry')) return this.getTelemetry();
        if (path.includes('/api/pose')) return this.getCurrentPose();
        if (path.includes('/api/field')) return this.getFieldConfig();
        if (path.includes('/api/environments')) return this.getEnvironments();
        if (path.includes('/api/conversations')) return this.getConversations();
        if (path.includes('/api/proposals')) return this.getProposals();
        return {};
    }
    async post(path, body) {
        if (path.includes('/api/sessions')) return this.createSession(body);
        if (path.includes('/api/environments')) return this.saveEnvironment(body);
        if (path.includes('/api/proposals') && path.includes('approve')) return this.approveProposal(path.split('/')[3]);
        if (path.includes('/api/proposals') && path.includes('reject')) return this.rejectProposal(path.split('/')[3]);
        if (path.includes('/api/abort')) return this.abortSession(path.split('/')[3]);
        return {};
    }
    async patch(path, body) { return {}; }
    async delete(path) { return {}; }
}

export { MockWsManager, MockSseManager, MockApiManager };
