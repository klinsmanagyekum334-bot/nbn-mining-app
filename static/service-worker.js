const CACHE_NAME = 'nbn-mining-v1';
const urlsToCache = [
  '/',
  '/login',
  '/static/manifest.json',
  '/static/mining1.jpeg',
  '/static/mining4.jpg'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});
