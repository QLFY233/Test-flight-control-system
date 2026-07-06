/**
 * Config Loader — Loads defaults, merges with localStorage overrides.
 * Keys prefixed with "_" are protected and cannot be overridden by user config.
 */

/**
 * Deep merge two objects. source overrides target.
 * Keys starting with "_" in source are skipped (protected).
 * @param {object} target - base config
 * @param {object} source - user config
 * @returns {object} merged result
 */
function deepMerge(target, source) {
    const result = JSON.parse(JSON.stringify(target));

    function mergeInto(resultObj, sourceObj) {
        for (const key of Object.keys(sourceObj)) {
            // Protected keys
            if (key.startsWith('_')) continue;

            const srcVal = sourceObj[key];
            const tgtVal = resultObj[key];

            if (
                srcVal !== null &&
                typeof srcVal === 'object' &&
                !Array.isArray(srcVal) &&
                tgtVal !== null &&
                typeof tgtVal === 'object' &&
                !Array.isArray(tgtVal)
            ) {
                mergeInto(tgtVal, srcVal);
            } else {
                resultObj[key] = srcVal;
            }
        }
    }

    mergeInto(result, source);
    return result;
}

/**
 * Load and merge configuration.
 * @returns {Promise<object>} merged config object
 */
async function loadConfig() {
    try {
        const res = await fetch('config-default.json');
        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }
        const defaults = await res.json();

        let saved;
        try {
            saved = JSON.parse(localStorage.getItem('flight-control-config') || '{}');
        } catch (e) {
            console.warn('[Config] localStorage parse error, using defaults');
            saved = {};
        }

        return deepMerge(defaults, saved);
    } catch (e) {
        console.error('[Config] failed to load config-default.json:', e);
        // Fallback: hardcoded minimal config
        return {
            _format: 'flight-control-config',
            _version: 1,
            backend: {
                base_url: 'http://localhost:8000',
                ws_endpoint: '/ws',
                sse_beta: '/api/chat/beta',
            },
            display: {
                theme: 'dark',
                language: 'zh-CN',
            },
        };
    }
}

export { loadConfig, deepMerge };
