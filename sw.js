const CACHE="leida-v22";

self.addEventListener("install",e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(["./","./index.html","./manifest.webmanifest","./icon.svg"])).catch(()=>{}));
  self.skipWaiting();
});

self.addEventListener("activate",e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});

self.addEventListener("fetch",e=>{
  const url=e.request.url;
  if(url.includes('/data/daily.json')){
    e.respondWith(fetch(e.request,{cache:'no-store'}).catch(()=>caches.match(e.request)));
    return;
  }
  if(e.request.mode==='navigate' || url.endsWith('/index.html')){
    e.respondWith(fetch(e.request,{cache:'no-store'}).then(async r=>{
      if(!r.ok) return r;
      const html=await r.text();
      const credit='<div class="radar-credit" style="margin-left:4px;padding:7px 11px;border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:8px;font-size:11px;font-weight:600;white-space:nowrap;letter-spacing:.1px">designed by Lee, powered by ChatGPT</div>';
      const replaced=html.replace('<button class="btn" onclick="loadData()">↻ 刷新</button>',credit);
      return new Response(replaced,{status:r.status,statusText:r.statusText,headers:r.headers});
    }).catch(()=>caches.match('./index.html')));
    return;
  }
  e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)));
});
