const CACHE="leida-v18";

self.addEventListener("install",e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(["./","./index.html","./manifest.webmanifest","./icon.svg"])).catch(()=>{}));
  self.skipWaiting();
});

self.addEventListener("activate",e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});

async function injectTitleTranslations(response){
  try{
    const html=await response.text();
    const script=`<style>.original-title{margin:-2px 0 7px;color:var(--muted);font-size:11px;line-height:1.35;font-weight:400;word-break:break-word}.original-title::before{content:'原文：';font-weight:600;opacity:.8}</style><script>(async()=>{try{const r=await fetch('./data/daily.json?ts='+Date.now(),{cache:'no-store'});const d=await r.json();const m=new Map();const walk=x=>{if(!x||typeof x!=='object')return;if(Array.isArray(x)){x.forEach(walk);return}if(typeof x.title==='string'&&typeof x.title_zh==='string'&&x.title_zh.trim())m.set(x.title_zh.trim(),x.title.trim());Object.values(x).forEach(walk)};walk(d);const add=()=>{document.querySelectorAll('.event h3,.modalbox h2').forEach(h=>{if(h.dataset.originalDone)return;const zh=h.textContent.trim();const raw=m.get(zh);if(!raw||raw===zh)return;h.dataset.originalDone='1';const o=document.createElement('div');o.className='original-title';o.textContent=raw;h.insertAdjacentElement('afterend',o);});};add();new MutationObserver(add).observe(document.body,{childList:true,subtree:true})}catch(e){console.warn('title translation injection failed',e)}})();</script>`;
    return new Response(html.replace('</body>',script+'</body>'),{status:response.status,statusText:response.statusText,headers:response.headers});
  }catch(e){return response}
}

self.addEventListener("fetch",e=>{
  const url=e.request.url;
  if(url.includes('/data/daily.json')){
    e.respondWith(fetch(e.request,{cache:'no-store'}).catch(()=>caches.match(e.request)));
    return;
  }
  if(e.request.mode==='navigate' || url.endsWith('/index.html')){
    e.respondWith(fetch(e.request,{cache:'no-store'}).then(injectTitleTranslations).catch(()=>caches.match('./index.html')));
    return;
  }
  e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)));
});