(() => {
  const ENDPOINT = 'https://apbalfbnqsdgsrpqccth.supabase.co/functions/v1/rader-analytics-ingest';
  const KEY = 'rader_session_id';
  const tier = () => document.querySelector('.radar-tier.active')?.dataset?.tier || null;
  let sid = localStorage.getItem(KEY);
  if (!sid) { sid = crypto.randomUUID(); localStorage.setItem(KEY, sid); }
  const ua = navigator.userAgent;
  const browser = /Firefox/i.test(ua) ? 'Firefox' : /Edg/i.test(ua) ? 'Edge' : /Chrome/i.test(ua) ? 'Chrome' : /Safari/i.test(ua) ? 'Safari' : 'Other';
  const os = /iPhone|iPad|iPod/i.test(ua) ? 'iOS' : /Android/i.test(ua) ? 'Android' : /Windows/i.test(ua) ? 'Windows' : /Mac OS X/i.test(ua) ? 'macOS' : /Linux/i.test(ua) ? 'Linux' : 'Other';
  const device = /Mobi|Android|iPhone|iPad/i.test(ua) ? 'mobile' : 'desktop';
  const send = (event_type='pageview', target=null, meta={}) => {
    const body = { session_id:sid, path:location.pathname, event_type, event_target:target, country_tier:tier(), browser, os, device, screen_width:screen.width, screen_height:screen.height, language:navigator.language, timezone:Intl.DateTimeFormat().resolvedOptions().timeZone, referer:document.referrer || null, user_agent:ua, metadata:meta };
    try { fetch(ENDPOINT,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),keepalive:true,mode:'cors'}).catch(()=>{}); } catch(e) {}
  };
  window.RaderAnalytics = { track:(name,target,meta)=>send(name,target,meta) };
  send();
  document.addEventListener('click', e => {
    const el = e.target.closest('[data-tier],[data-news-id],a');
    if (!el) return;
    send(el.dataset.tier ? 'tier_click' : 'news_click', el.dataset.newsId || el.dataset.tier || el.textContent?.trim().slice(0,120) || 'link');
  }, {capture:true, passive:true});
})();
