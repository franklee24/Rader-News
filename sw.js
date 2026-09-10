const CACHE="leida-v15";

self.addEventListener("install",e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(["./","./index.html","./manifest.webmanifest","./icon.svg"])));
  self.skipWaiting();
});

self.addEventListener("activate",e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});

async function injectTitleTranslations(response){
  try{
    const html=await response.text();
    const script=`<script>(async()=>{try{const r=await fetch('./data/daily.json?ts='+Date.now(),{cache:'no-store'});const d=await r.json();const m=new Map();const walk=x=>{if(!x||typeof x!=='object')return;if(Array.isArray(x)){x.forEach(walk);return}if(typeof x.title==='string'&&typeof x.title_zh==='string'&&x.title_zh.trim())m.set(x.title.trim(),x.title_zh.trim());Object.values(x).forEach(walk)};walk(d);const add=()=>{document.querySelectorAll('.event h3').forEach(h=>{if(h.dataset.zhDone)return;const zh=m.get(h.textContent.trim());if(!zh)return;h.dataset.zhDone='1';const el=document.createElement('div');el.className='zh-title';el.textContent=zh;h.insertAdjacentElement('afterend',el)});};const s=document.createElement('style');s.textContent='.zh-title{margin:-3px 0 7px;color:#b8c8da;font-size:12px;line-height:1.45;font-weight:500}';document.head.appendChild(s);add();new MutationObserver(add).observe(document.body,{childList:true,subtree:true})}catch(e){console.warn('title translation failed',e)}})();</script>`;
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