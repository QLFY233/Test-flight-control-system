// All shared app state lives on window.__app — zero circular import issues.
window.__app = {
    config: null,
    wsManager: null,
    sseManager: null,
    apiManager: null,
    router: null,
    chatPanel: null,
};

// 左栏宽度 (px) — 模块级会话状态: 页面间导航保留, 刷新即重置 (仅本次会话有效)
let _leftWidth = null;
const _LEFT_MIN_RATIO = 0.15;
const _LEFT_MAX_RATIO = 0.75;

export function renderTwoColumn(container, leftHtml, rightHtml, leftHeader) {
    container.classList.remove('left-column');
    container.style.display = 'flex';
    container.style.flexDirection = 'row';
    container.style.flex = '1';
    container.style.overflow = 'hidden';
    const leftWidthStyle = _leftWidth ? ` style="width:${_leftWidth}px;"` : '';
    container.innerHTML = `
        <div class="left-column"${leftWidthStyle}>
            ${leftHeader ? '<div class="left-column__header">' + leftHeader + '</div>' : ''}
            <div class="left-column__body">${leftHtml}</div>
        </div>
        <div class="layout-splitter" title="拖动调整左右占比"></div>
        <div class="right-column">
            <div class="right-column__toolbar" id="right-toolbar"></div>
            <div class="right-column__view-area right-column__view-area--single" id="right-view-area"></div>
        </div>
    `;
    bindLayoutSplitter(container);
}

/**
 * 左栏 ↔ 右栏 竖向拖动分界条。
 * - 拖动实时改左栏宽度 (px), 右栏 flex:1 自动补齐
 * - 钳制在容器 15%~75%; 宽度存模块级 _leftWidth (导航保留, 刷新重置)
 * - 移动端 (<768px) 纵向堆叠布局不启用
 */
function bindLayoutSplitter(container) {
    const splitter = container.querySelector('.layout-splitter');
    const left = container.querySelector('.left-column');
    if (!splitter || !left) return;
    if (window.innerWidth < 768) return;

    const getX = (ev) => (ev.touches && ev.touches.length) ? ev.touches[0].clientX : ev.clientX;

    const onStart = (e) => {
        e.preventDefault();
        const startX = getX(e);
        const startWidth = left.getBoundingClientRect().width;
        const cw = container.getBoundingClientRect().width;
        const minW = cw * _LEFT_MIN_RATIO;
        const maxW = cw * _LEFT_MAX_RATIO;
        splitter.classList.add('layout-splitter--active');
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'col-resize';

        const onMove = (ev) => {
            const w = Math.min(maxW, Math.max(minW, startWidth + (getX(ev) - startX)));
            left.style.width = w + 'px';
            _leftWidth = w;
        };
        const onEnd = () => {
            splitter.classList.remove('layout-splitter--active');
            document.body.style.userSelect = '';
            document.body.style.cursor = '';
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onEnd);
            document.removeEventListener('touchmove', onMove);
            document.removeEventListener('touchend', onEnd);
            window.removeEventListener('blur', onEnd);
        };
        // 窗口外松开鼠标/触摸 (blur) → 兜底结束拖拽, 防 col-resize 光标卡死
        window.addEventListener('blur', onEnd);
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onEnd);
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('touchend', onEnd);
    };

    splitter.addEventListener('mousedown', onStart);
    splitter.addEventListener('touchstart', onStart, { passive: false });
}

export const wsManager = { get send(){ return window.__app.wsManager?.send?.bind(window.__app.wsManager) }, get connect(){ return ()=>window.__app.wsManager?.connect() }, get on(){ return (...a)=>window.__app.wsManager?.on(...a) }, get off(){ return (...a)=>window.__app.wsManager?.off(...a) } };
export const apiManager = { get getFieldConfig(){ return ()=>window.__app.apiManager?.getFieldConfig() }, get approveProposal(){ return (id)=>window.__app.apiManager?.approveProposal(id) }, get rejectProposal(){ return (id,r)=>window.__app.apiManager?.rejectProposal(id,r) }, get getSessions(){ return (p)=>window.__app.apiManager?.getSessions(p) }, get getSessionDetail(){ return (id)=>window.__app.apiManager?.getSessionDetail(id) }, get getProposals(){ return ()=>window.__app.apiManager?.getProposals() }, get getEnvironments(){ return ()=>window.__app.apiManager?.getEnvironments() }, get saveEnvironment(){ return (e)=>window.__app.apiManager?.saveEnvironment(e) }, get createSession(){ return (c)=>window.__app.apiManager?.createSession(c) }, get abortSession(){ return (s)=>window.__app.apiManager?.abortSession(s) }, get getCurrentPose(){ return ()=>window.__app.apiManager?.getCurrentPose() }, get getOverview(){ return ()=>window.__app.apiManager?.getOverview() }, get getTelemetry(){ return ()=>window.__app.apiManager?.getTelemetry() } , get getTaskList(){ return (l)=>window.__app.apiManager?.getTaskList(l) }, get createTask(){ return (c)=>window.__app.apiManager?.createTask(c) }, get renameTask(){ return (id,n)=>window.__app.apiManager?.renameTask(id,n) }, get deleteTask(){ return (id)=>window.__app.apiManager?.deleteTask(id) }, get activateTask(){ return (id)=>window.__app.apiManager?.activateTask(id) } };
export const sseManager = { get sendMessage(){ return (...a)=>window.__app.sseManager?.sendMessage(...a) } };
export const config = {};
export const router = { get navigate(){ return (h)=>window.__app.router?.navigate(h) }, get init(){ return ()=>window.__app.router?.init() } };
