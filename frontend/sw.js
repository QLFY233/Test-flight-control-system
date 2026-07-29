// Service Worker — PWA 离线缓存 (先导阶段 L)
// 缓存策略: 首次访问缓存静态资源, 后续优先从缓存取 (Cache First)

const CACHE_NAME = 'flight-control-v1';
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

// 请求拦截 — Cache First (静态), Network First (API)
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API/WebSocket 请求 — 走网络
  if (url.pathname.startsWith('/api/') || url.pathname === '/ws') {
    return; // 不拦截
  }

  // 静态资源 — Cache First
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return cached || fetch(event.request).then((response) => {
        // 缓存成功的网络请求
        if (response.ok && response.type === 'basic') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, clone);
          });
        }
        return response;
      });
    })
  );
});
