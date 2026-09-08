const CACHE='leida-news-v1';
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(clients.claim()));
self.addEventListener('fetch',e=>{
  if(e.request.url.includes('/data/daily.json')) return;
  e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
});