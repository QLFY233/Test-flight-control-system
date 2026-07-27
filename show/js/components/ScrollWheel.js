// ScrollWheel component — center-snap scroller
function genScrollWheel(values, initial, itemHeight, onChange) {
    const vh = itemHeight * 3;
    const container = document.createElement('div');
    container.style.cssText = `
        width: 100%;
        height: ${vh}px;
        overflow: hidden;
        background: var(--color-surface-overlay);
        border: var(--border-hair);
        user-select: none;
    `;

    const scroller = document.createElement('div');
    scroller.style.cssText = `
        width: 100%;
        height: 100%;
        overflow-y: auto;
        scroll-snap-type: y mandatory;
    `;
    container.appendChild(scroller);

    for (const v of values) {
        const el = document.createElement('div');
        el.style.cssText = `
            height: ${itemHeight}px;
            display: flex;
            align-items: center;
            justify-content: center;
            scroll-snap-align: center;
            font-family: var(--font-mono);
            font-size: var(--text-sm);
            color: var(--color-text-disabled);
            letter-spacing: var(--track-wide);
            font-variant-numeric: tabular-nums;
        `;
        el.textContent = Number.isInteger(v) ? String(v) : v.toFixed(1);
        scroller.appendChild(el);
    }

    // Highlight bar at center
    const hl = document.createElement('div');
    hl.style.cssText = `
        position: absolute;
        left: 0; right: 0;
        top: 50%;
        transform: translateY(-50%);
        height: ${itemHeight}px;
        pointer-events: none;
        border-top: 1px solid var(--color-red);
        border-bottom: 1px solid var(--color-red);
        background: transparent;
    `;
    container.appendChild(hl);

    // Center offset: item center - viewport center
    const ch = container.clientHeight || 96;
    const centeringOffset = Math.round(itemHeight / 2 - ch / 2);

    let idx = values.findIndex(v => Math.abs(v - initial) < 0.01);
    if (idx < 0) idx = 0;

    requestAnimationFrame(() => {
        scroller.scrollTop = Math.max(0, idx * itemHeight + centeringOffset);
    });

    let snapTimer = null;
    scroller.addEventListener('scroll', () => {
        if (snapTimer) clearTimeout(snapTimer);
        snapTimer = setTimeout(() => {
            const raw = scroller.scrollTop;
            const off = Math.round(itemHeight / 2 - scroller.clientHeight / 2);
            const i = Math.max(0, Math.min(Math.round((raw - off) / itemHeight), values.length - 1));
            const sy = i * itemHeight + off;
            if (Math.abs(raw - sy) > 2) scroller.scrollTo({ top: sy, behavior: 'smooth' });
            if (values[i] != null) onChange(values[i]);
        }, 150);
    });

    return { container, scroller, topPad: 0, itemHeight, values, centeringOffset };
}

export { genScrollWheel };
