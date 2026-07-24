// All shared app state lives on window.__app — zero circular import issues.
window.__app = {
    config: null,
    wsManager: null,
    sseManager: null,
    apiManager: null,
    router: null,
    chatPanel: null,
    scene3D: null,
    fieldRenderer: null,
    droneModel: null,
    trajectoryLine: null,
    waypointMarker: null,
};

export function renderTwoColumn(container, leftHtml, rightHtml, leftHeader) {
    container.classList.remove('left-column');
    container.style.display = 'flex';
    container.style.flexDirection = 'row';
    container.style.flex = '1';
    container.style.overflow = 'hidden';
    container.innerHTML = `
        <div class="left-column">
            ${leftHeader ? '<div class="left-column__header">' + leftHeader + '</div>' : ''}
            <div class="left-column__body">${leftHtml}</div>
        </div>
        <div class="right-column">
            <div class="right-column__toolbar" id="right-toolbar"></div>
            <div class="right-column__view-area right-column__view-area--single" id="right-view-area"></div>
        </div>
    `;
}

export const wsManager = { get send(){ return window.__app.wsManager?.send?.bind(window.__app.wsManager) }, get connect(){ return ()=>window.__app.wsManager?.connect() }, get on(){ return (...a)=>window.__app.wsManager?.on(...a) }, get off(){ return (...a)=>window.__app.wsManager?.off(...a) } };
export const apiManager = { get getFieldConfig(){ return ()=>window.__app.apiManager?.getFieldConfig() }, get approveProposal(){ return (id)=>window.__app.apiManager?.approveProposal(id) }, get rejectProposal(){ return (id,r)=>window.__app.apiManager?.rejectProposal(id,r) }, get getSessions(){ return (p)=>window.__app.apiManager?.getSessions(p) }, get getEnvironments(){ return ()=>window.__app.apiManager?.getEnvironments() }, get saveEnvironment(){ return (e)=>window.__app.apiManager?.saveEnvironment(e) }, get createSession(){ return (c)=>window.__app.apiManager?.createSession(c) }, get abortSession(){ return (s)=>window.__app.apiManager?.abortSession(s) }, get getCurrentPose(){ return ()=>window.__app.apiManager?.getCurrentPose() }, get getOverview(){ return ()=>window.__app.apiManager?.getOverview() }, get getTelemetry(){ return ()=>window.__app.apiManager?.getTelemetry() } };
export const sseManager = { get sendMessage(){ return (...a)=>window.__app.sseManager?.sendMessage(...a) } };
export const config = {};
export const router = { get navigate(){ return (h)=>window.__app.router?.navigate(h) }, get init(){ return ()=>window.__app.router?.init() } };
export const chatPanel = {};
export const sharedScene3D = { __p: null, get mount(){ return (c)=>this.__p?.mount(c) }, get unmount(){ return ()=>this.__p?.unmount() }, get isReady(){ return ()=>this.__p?.isReady()||false }, get pause(){ return ()=>this.__p?.pause() }, get resume(){ return ()=>this.__p?.resume() }, get add(){ return (o)=>this.__p?.add(o) }, get remove(){ return (o)=>this.__p?.remove(o) } };
export const sharedFieldRenderer = { get updateFromField(){ return (f)=>window.__app.fieldRenderer?.updateFromField(f) } };
export const sharedDroneModel = { get setTargetPosition(){ return (p)=>window.__app.droneModel?.setTargetPosition(p) } };
export const sharedTrajectoryLine = { get setPlanned(){ return (p)=>window.__app.trajectoryLine?.setPlanned(p) }, get updateFlown(){ return (p)=>window.__app.trajectoryLine?.updateFlown(p) } };
export const sharedWaypointMarker = { get setTarget(){ return (t)=>window.__app.waypointMarker?.setTarget(t) }, get setWaypoints(){ return (w)=>window.__app.waypointMarker?.setWaypoints(w) } };
