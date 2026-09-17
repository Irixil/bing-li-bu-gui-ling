const CACHE = 'bingli-beta-shell-v4';
const SHELL = ['/', '/styles.css', '/ios.css', '/splash.css', '/config.js', '/local-store-core.js', '/safety.js', '/local-store.js', '/app.js', '/media.js', '/splash.js', '/assets/brand-mascot.png', '/manifest.webmanifest'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/') || url.pathname === '/runtime-config.js') return;
  event.respondWith(fetch(request).then(response => {
    const copy = response.clone();
    const cacheKey = request.mode === 'navigate' ? '/' : request;
    caches.open(CACHE).then(cache => cache.put(cacheKey, copy));
    return response;
  }).catch(() => request.mode === 'navigate' ? caches.match('/') : caches.match(request)));
});
