// Service Worker — PWA 离线缓存 (先导阶段 L)
// 缓存策略: 静态资源 Stale-While-Revalidate（先用缓存即时响应，后台回源更新），
// 避免 Cache First 导致的「代码更新后永不清缓存」。
// 版本号变更（发布新版本时更新 BUILD_ID）会自动废弃旧缓存。

const BUILD_ID = '2026-08-05-feat-layout-splitter';
const CACHE_NAME = 'flight-control-v1-' + BUILD_ID;
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/css/reset.css',
  '/css/variables.css',
  '/css/layout.css',
  '/css/components.css',
  '/css/pages.css',
  '/js/app.js',
  '/js/state.js',
  '/js/router.js',
  '/js/config.js',
  '/js/api.js',
  '/js/ws.js',
  '/js/sse.js',
  '/js/event-bus.js',
  '/js/shared.js',
  '/js/escape.js',
  '/config-default.json',
  '/manifest.json',
];

// 安装 — 预缓存静态资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[sw] cache preload partial:', err);
      });
    })
  );
  self.skipWaiting();
});

// 激活 — 清理旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) => {
      return Promise.all(
        names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))
      );
    })
  );
  self.clients.claim();
});

// 请求拦截 — Stale-While-Revalidate (静态), Network First (API)
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API/WebSocket 请求 — 走网络
  if (url.pathname.startsWith('/api/') || url.pathname === '/ws') {
    return; // 不拦截
  }

  // 静态资源 — Stale-While-Revalidate: 先用缓存即时响应，后台回源更新缓存
  // 硬刷新 (Ctrl+Shift+R / request.cache=reload) 绕过缓存直接回源 — 保证拿到最新代码
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const bypass = event.request.cache === 'reload'
        || (event.request.headers.get('cache-control') || '').includes('no-cache');
      if (bypass) {
        return fetch(event.request).then((response) => {
          if (response.ok && response.type === 'basic') {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, clone);
            });
          }
          return response;
        }).catch(() => cached);
      }
      const networkFetch = fetch(event.request).then((response) => {
        if (response.ok && response.type === 'basic') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, clone);
          });
        }
        return response;
      }).catch(() => cached);

      return cached || networkFetch;
    })
  );
});
