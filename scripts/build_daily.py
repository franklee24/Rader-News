#!/usr/bin/env python3
import json, os, re, time, random, hashlib, socket
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "daily.json")
CFG = os.path.join(ROOT, "config.json")
API = "https://api.gdeltproject.org/api/v2/doc/doc"
UA = "Radar-News/12.0 (+https://github.com/franklee24/Rader-News)"
REQUEST_TIMEOUT = 25
MAX_RETRIES = 4
MAX_WORKERS = 3
RATE_GATE_SECONDS = 4.0

CATEGORIES = {
    "政治/政府":["government","president","prime minister","parliament","election","cabinet","minister","congress","senate","policy","政","政府","总统","总理","议会","选举","内阁","部长"],
    "宏观经济/金融":["central bank","interest rate","inflation","gdp","economy","economic","bond","currency","market","rate cut","rate hike","央行","利率","通胀","GDP","经济","国债","货币","金融"],
    "产业/商业":["company","corporate","business","industry","merger","acquisition","factory","manufacturing","trade","tariff","企业","商业","产业","制造","贸易","关税"],
    "科技":["technology","tech","AI","artificial intelligence","chip","semiconductor","software","space","robot","科技","人工智能","芯片","半导体","软件","航天","机器人"],
    "能源":["oil","gas","energy","power","electricity","nuclear","renewable","OPEC","石油","天然气","能源","电力","核能","可再生"],
    "国防/安全":["military","defense","defence","missile","weapon","army","navy","air force","security","war","attack","drone","国防","军事","导弹","武器","军队","安全","战争","袭击","无人机"],
    "外交/国际":["diplomatic","diplomacy","foreign","summit","treaty","sanction","NATO","UN","EU","外交","峰会","条约","制裁","北约","联合国","欧盟"],
    "社会/灾害":["society","social","health","hospital","disease","crime","protest","fire","flood","earthquake","storm","disaster","社会","卫生","医院","疾病","犯罪","抗议","火灾","洪水","地震","灾害"]
}
AUTH = {
    "reuters.com":1.0,"apnews.com":1.0,"bbc.com":0.98,"ft.com":0.98,"wsj.com":0.98,
    "nytimes.com":0.96,"bloomberg.com":0.98,"theguardian.com":0.9,"economist.com":0.96,
    "aljazeera.com":0.9,"cnn.com":0.86,"cnbc.com":0.88,"dw.com":0.9,"france24.com":0.9,
    "nikkei.com":0.92,"nhk.or.jp":0.94,"japantimes.co.jp":0.84,"scmp.com":0.84,
    "tass.com":0.78,"rt.com":0.62,"xinhuanet.com":0.94,"english.news.cn":0.94,
    "people.com.cn":0.9,"chinadaily.com.cn":0.88,"globaltimes.cn":0.72,
    "indiatimes.com":0.72,"thehindu.com":0.88,"abc.net.au":0.88,"abcnews.go.com":0.9,
    "cbc.ca":0.9,"theglobeandmail.com":0.86,"arabnews.com":0.82,"spa.gov.sa":0.9,
    "yonhapnews.co.kr":0.92,"koreaherald.com":0.82,"elpais.com":0.88
}
COUNTRY_DATA = json.load(open(CFG, encoding="utf-8"))
TARGETS = COUNTRY_DATA["targets"]

# Thread-safe global request gate. It prevents a burst from the same runner IP.
import threading
_gate_lock = threading.Lock()
_last_request = 0.0

def wait_for_gate():
    global _last_request
    with _gate_lock:
        now = time.monotonic()
        delay = RATE_GATE_SECONDS - (now - _last_request)
        if delay > 0:
            time.sleep(delay)
        _last_request = time.monotonic()

def norm(s):
    s = (s or "").lower()
    s = re.sub(r"https?://"," ",s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def tokens(s):
    n = norm(s)
    en = {x for x in n.split() if len(x) > 2}
    zh = {n[i:i+2] for i in range(max(0,len(n)-1)) if "\u4e00" <= n[i] <= "\u9fff"}
    return en | zh

def sim(a,b):
    A,B=tokens(a),tokens(b)
    return len(A&B)/max(1,len(A|B))

def domain_score(domain):
    d=(domain or "").lower().split(":")[0]
    for k,v in AUTH.items():
        if d==k or d.endswith("."+k):
            return v
    return 0.45

def classify(title):
    t=norm(title)
    scores={c:sum(1 for w in words if norm(w) in t) for c,words in CATEGORIES.items()}
    return max(scores,key=scores.get) if max(scores.values()) else "其他"

def fetch(query, label=""):
    params={"query":f"({query})","mode":"artlist","maxrecords":"250","timespan":"24h","sort":"datedesc","format":"json"}
    url=API+"?"+urlencode(params)
    last=None
    for attempt in range(1, MAX_RETRIES+1):
        wait_for_gate()
        started=time.monotonic()
        try:
            print(f"  [{label}] request {attempt}/{MAX_RETRIES}", flush=True)
            req=Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
            with urlopen(req,timeout=REQUEST_TIMEOUT) as r:
                raw=r.read()
                status=getattr(r,"status",200)
            elapsed=time.monotonic()-started
            if not raw:
                raise ValueError("empty response")
            data=json.loads(raw)
            print(f"  [{label}] HTTP {status}, {len(data.get('articles',[])) if isinstance(data,dict) else 0} articles, {elapsed:.1f}s", flush=True)
            return data
        except HTTPError as e:
            last=f"HTTP {e.code}"
            retry_after=e.headers.get("Retry-After")
            if e.code == 429:
                base=float(retry_after) if retry_after and retry_after.isdigit() else min(30*(2**(attempt-1)),180)
            elif e.code in (408,425,500,502,503,504):
                base=min(8*(2**(attempt-1)),90)
            else:
                raise
            jitter=random.uniform(1,4)
            print(f"  [{label}] {last}; retry in {base+jitter:.1f}s", flush=True)
            time.sleep(base+jitter)
        except (URLError, TimeoutError, socket.timeout, ValueError, json.JSONDecodeError) as e:
            last=f"{type(e).__name__}: {e}"
            base=min(6*(2**(attempt-1)),60)
            print(f"  [{label}] {last}; retry in {base:.1f}s", flush=True)
            time.sleep(base+random.uniform(0.5,2))
    raise RuntimeError(last or "fetch failed")

def article_time(a):
    s=a.get("seendate") or ""
    try:
        return datetime.strptime(s,"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)

def make_events(articles,country):
    raw=[]
    for a in articles:
        title=(a.get("title") or "").strip()
        url=(a.get("url") or "").strip()
        if not title or not url: continue
        raw.append({"title":title,"url":url,"domain":a.get("domain",""),
                    "source_country":a.get("sourcecountry",""),
                    "published_at":article_time(a).isoformat(),
                    "category":classify(title)})
    raw.sort(key=lambda x:(domain_score(x["domain"]),x["published_at"]),reverse=True)
    groups=[]
    for a in raw:
        hit=None
        # Keep the clustering window bounded for predictable runtime.
        for g in groups[:220]:
            if sim(a["title"],g["title"]) >= 0.55:
                hit=g; break
        if hit: hit["sources"].append(a)
        else: groups.append({"title":a["title"],"sources":[a],"category":a["category"]})
    events=[]
    for g in groups:
        ss=g["sources"]
        ss.sort(key=lambda x:(domain_score(x["domain"]),x["published_at"]),reverse=True)
        primary=ss[0]
        cats=[x["category"] for x in ss]
        cat=max(set(cats),key=cats.count)
        domains=list(dict.fromkeys(x["domain"] for x in ss if x["domain"]))
        domestic=sum(1 for x in ss if x["source_country"]==country["code"])/max(1,len(ss))
        novelty=min(1.0,0.35+0.12*len(ss))
        authority=domain_score(primary["domain"])
        diversity=min(1.0,len(domains)/4)
        impact_terms=["war","attack","sanction","rate","election","earthquake","missile","tariff","核","战争","袭击","制裁","利率","选举","地震","导弹"]
        impact=min(1.0,sum(1 for w in impact_terms if norm(w) in norm(primary["title"]))/3)
        score=round(100*(0.20*authority+0.20*diversity+0.25*novelty+0.20*domestic+0.15*impact))
        events.append({
            "id":hashlib.sha1((country["name"]+"|"+norm(primary["title"])).encode()).hexdigest()[:12],
            "event_country":country["name"],"country_code":country["code"],
            "title":primary["title"],"category":cat,"domestic_score":round(domestic,2),
            "importance":score,"published_at":primary["published_at"],
            "source":primary["domain"],"url":primary["url"],
            "sources":[{"domain":x["domain"],"url":x["url"],"title":x["title"]} for x in ss[:6]]
        })
    events.sort(key=lambda x:(x["importance"],x["published_at"]),reverse=True)
    return events

def load_old():
    try: return json.load(open(DATA,encoding="utf-8"))
    except Exception: return None

def process_country(tier,c):
    label=f"{tier}/{c['name']}"
    print(f"\n▶ {label} 开始",flush=True)
    try:
        data=fetch(c["query"],label)
        arts=data.get("articles",[]) if isinstance(data,dict) else []
        ev=make_events(arts,c)[:TARGETS[tier]["max"]]
        print(f"✓ {label} 完成：{len(ev)} 个独立事件",flush=True)
        return {"tier":tier,"country":c["name"],"code":c["code"],"count":len(ev),
                "target_max":TARGETS[tier]["max"],"events":ev,"status":"fresh","error":None}
    except Exception as e:
        print(f"✗ {label} 失败：{e}",flush=True)
        return {"tier":tier,"country":c["name"],"code":c["code"],
                "count":0,"target_max":TARGETS[tier]["max"],"events":[],
                "status":"failed","error":str(e)}

def main():
    old=load_old()
    all_countries=[]
    # Submit only 3 at a time; the request gate still spaces calls.
    jobs=[(tier,c) for tier,items in COUNTRY_DATA["countries"].items() for c in items]
    print(f"雷达新闻 V12：{len(jobs)} 个国家/地区，最多并发 {MAX_WORKERS}，单请求超时 {REQUEST_TIMEOUT}s",flush=True)

    results={}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures={ex.submit(process_country,tier,c):(tier,c) for tier,c in jobs}
        for fut in as_completed(futures):
            tier,c=futures[fut]
            results[(tier,c["code"])]=fut.result()

    for tier,c in jobs:
        result=results[(tier,c["code"])]
        if result["status"]=="failed":
            oldc=next((x for x in (old or {}).get("countries",[]) if x.get("country")==c["name"]),None)
            fallback=oldc.get("events",[]) if oldc else []
            if fallback:
                result["events"]=fallback[:TARGETS[tier]["max"]]
                result["count"]=len(result["events"])
                result["status"]="stale_fallback"
                print(f"↩ {tier}/{c['name']} 使用上一份成功快照：{len(result['events'])} 个事件",flush=True)
        all_countries.append(result)

    # Supplement is intentionally one extra request and is isolated from country failures.
    supplement={"count":0,"events":[],"status":"failed"}
    try:
        print("\n▶ supplement/全球补充 开始",flush=True)
        q='"United Nations" OR "NATO" OR "European Union" OR "IMF" OR "World Bank" OR "G7" OR "global economy" OR "international security"'
        data=fetch(q,"supplement")
        fake={"name":"国际组织/全球","english":"Global","code":"GLOBAL"}
        sup=make_events(data.get("articles",[]) if isinstance(data,dict) else [],fake)[:TARGETS["supplement"]["max"]]
        supplement={"count":len(sup),"events":sup,"status":"fresh"}
        print(f"✓ supplement 完成：{len(sup)} 个独立事件",flush=True)
    except Exception as e:
        oldsup=(old or {}).get("supplement",{})
        fallback=oldsup.get("events",[]) if oldsup else []
        supplement={"count":len(fallback),"events":fallback,"status":"stale_fallback" if fallback else "failed","error":str(e)}
        print(f"✗ supplement 失败：{e}",flush=True)

    all_events=[]
    for c in all_countries: all_events.extend(c["events"])
    all_events.extend(supplement["events"])
    uniq={e["id"]:e for e in all_events}
    top=sorted(uniq.values(),key=lambda x:(x.get("importance",0),x.get("domestic_score",0)),reverse=True)[:30]

    now=datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    fresh=sum(1 for c in all_countries if c["status"]=="fresh")
    stale=sum(1 for c in all_countries if c["status"]=="stale_fallback")
    failed=sum(1 for c in all_countries if c["status"]=="failed")
    errors=[f"{c['tier']}/{c['country']}: {c.get('error')}" for c in all_countries if c.get("error")]
    if supplement.get("error"): errors.append(f"supplement: {supplement['error']}")

    out={
      "version":"12.0","generated_at":now.isoformat(),"window":"past_24h",
      "source":"GDELT DOC 2.0",
      "quality":{"country_count":len(all_countries),"fresh_country_count":fresh,
                 "stale_fallback_count":stale,"failed_country_count":failed,
                 "event_count":len(uniq),"errors":errors[:100]},
      "global_top":top,"countries":all_countries,"supplement":supplement,
      "summary":f"北京时间 {now:%Y-%m-%d %H:%M} 生成；最近24小时；成功 {fresh} 国，回退 {stale} 国，失败 {failed} 国；共 {len(uniq)} 个独立事件。"
    }
    os.makedirs(os.path.dirname(DATA),exist_ok=True)
    tmp=DATA+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=2)
    os.replace(tmp,DATA)
    history=os.path.join(ROOT,"data","history"); os.makedirs(history,exist_ok=True)
    with open(os.path.join(history,now.strftime("%Y-%m-%d")+".json"),"w",encoding="utf-8") as f:
        json.dump(out,f,ensure_ascii=False)
    print("\n=== 完成 ===",flush=True)
    print(json.dumps(out["quality"],ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
