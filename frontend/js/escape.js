/**
 * escape.js — 统一 HTML 转义助手（文本上下文 + 属性上下文）。
 * 全仓唯一转义实现，替代散落的 4 套近似实现（ChatMessage._escapeHtml /
 * 历史: FlightPlanCard._esc / SettingsPage._escAttr）。
 */

/**
 * 文本上下文转义：& < > （用于 innerHTML 文本插值）。
 * 基于 DOM 节点转换，天然覆盖所有 HTML 特殊字符。
 * @param {*} text
 * @returns {string}
 */
export function esc(text) {
    const div = document.createElement('div');
    div.textContent = String(text == null ? '' : text);
    return div.innerHTML;
}

/**
 * 属性上下文转义：在 esc 基础上额外转义引号，防止从属性值逃逸。
 * @param {*} text
 * @returns {string}
 */
export function escAttr(text) {
    return String(text == null ? '' : text)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

export default { esc, escAttr };
