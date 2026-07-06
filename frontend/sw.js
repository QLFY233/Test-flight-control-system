/**
 * Service Worker — Cache static resources, offline fallback.
 */

const CACHE_NAME = 'flight-control-v1';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/css/reset.css',
    '/css/variables.css',
    '/css/layout.css',
    '/css/components.css',
    '/css/pages.css',
    '/config-default.json',
    '/manifest.json',
];

// Install: cache static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS).catch((err) => {
                console.warn('[SW] cache addAll partial failure:', err);
            });
        })
    );
    self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});

// Fetch: cache-first for static, network-first for API
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Skip non-GET requests
    if (event.request.method !== 'GET') return;

    // Skip chrome-extension and other non-http(s) requests
    if (!url.protocol.startsWith('http')) return;

    // API requests: network-first
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws')) {
        event.respondWith(networkFirst(event.request));
        return;
    }

    // CDN scripts: network-first with fallback
    if (url.hostname.includes('cdn.jsdelivr.net')) {
        event.respondWith(networkFirst(event.request));
        return;
    }

    // Static assets: cache-first
    event.respondWith(cacheFirst(event.request));
});

/**
 * Cache-first strategy: try cache, fall back to network.
 */
async function cacheFirst(request) {
    const cached = await caches.match(request);
    if (cached) return cached;

    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone());
        }
        return response;
    } catch (e) {
        // Offline fallback for page navigations
        if (request.mode === 'navigate') {
            const cachedPage = await caches.match('/index.html');
            if (cachedPage) return cachedPage;
        }
        return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
    }
}

/**
 * Network-first strategy: try network, fall back to cache.
 */
async function networkFirst(request) {
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone());
        }
        return response;
    } catch (e) {
        const cached = await caches.match(request);
        if (cached) return cached;
        return new Response('Network error', { status: 503, statusText: 'Service Unavailable' });
    }
}
