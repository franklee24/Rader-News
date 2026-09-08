#!/usr/bin/env python3
import json, os, re, time, random, hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA=os.path.join(ROOT,"data","daily.json")
CFG=os.path.join(ROOT,"config.json")
API="https://api.gdeltproject.org/api/v2/doc/doc"

CATEGORIES={
"政治/政府":["government","president","prime minister","parliament","election","cabinet","minister","congress","senate","policy","政","政府","总统","总理","议会","选举","内阁","部长"],
"宏观经济/金融":["central bank","interest rate","inflation","gdp","economy","economic","bond","currency","market","rate cut","rate hike","央行","利率","通胀","GDP","经济","国债","货币","金融"],
"产业/商业":["company","corporate","business","industry","merger","acquisition","factory","manufacturing","trade","tariff","企业","商业","产业","制造","贸易","关税"],
"科技":["technology","tech","AI","artificial intelligence","chip","semiconductor","software","space","robot","科技","人工智能","芯片","半导体","软件","航天","机器人"],
"能源":["oil","gas","energy","power","electricity","nuclear","renewable","OPEC","石油","天然气","能源","电力","核能","可再生"],
"国防/安全":["military","defense","defence","missile","weapon","army","navy","air force","security","war","attack","drone","国防","军事","导弹","武器","军队","安全","战争","袭击","无人机"],
"外交/国际":["diplomatic","diplomacy","foreign","summit","treaty","sanction","NATO","UN","EU","外交","峰会","条约","制裁","北约","联合国","欧盟"],
"社会/灾害":["society","social","health","hospital","disease","crime","protest","fire","flood","earthquake","storm","disaster","社会","卫生","医院","疾病","犯罪","抗议","火灾","洪水","地震","灾害"]
}
DOMESTIC={
"政治/政府":1.0,"宏观经济/金融":1.0,"产业/商业":0.9,"科技":0.85,"能源":0.85,
"国防/安全":0.9,"外交/国际":0.65,"社会/灾害":0.9
}
AUTH={
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
COUNTRY_DATA=json.load(open(CFG,encoding="utf-8"))
TARGETS=COUNTRY_DATA["targets"]

def norm(s):
    s=(s or "").lower()
    s=re.sub(r"https?://"," ",s)
    s=re.sub(r"[^a-z0-9\u4e00-\u9fff ]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def tokens(s):
    n=norm(s)
    en=set(x for x in n.split() if len(x)>2)
    zh=set(n[i:i+2] for i in range(max(0,len(n)-1)) if "\u4e00"<=n[i]<="\u9fff")
    return en|zh

def sim(a,b):
    A=tokens(a); B=tokens(b)
    return len(A&B)/max(1,len(A|B))

def domain_score(domain):
    d=(domain or "").lower().split(":")[0]
    for k,v in AUTH.items():
        if d==k or d.endswith("."+k): return v
    return 0.45

def classify(title):
    t=norm(title)
    scores={}
    for c,words in CATEGORIES.items():
        scores[c]=sum(1 for w in words if norm(w) in t)
    return max(scores,key=scores.get) if max(scores.values()) else "其他"

def fetch(query, retries=5):
    params={"query":f"({query})","mode":"artlist","maxrecords":"250","timespan":"24h","sort":"datedesc","format":"json"}
    url=API+"?"+urlencode(params)
    last=None
    for attempt in range(retries):
        try:
            req=Request(url,headers={"User-Agent":"Radar-News/11.0 (news research)"})
            with urlopen(req,timeout=45) as r:
                raw=r.read()
            if not raw: raise ValueError("empty response")
            return json.loads(raw)
        except HTTPError as e:
            last=f"HTTP {e.code}"
            if e.code==429:
                wait=20*(2**attempt)+random.uniform(1,6)
            elif e.code in (500,502,503,504):
                wait=8*(2**attempt)+random.uniform(1,4)
            else: raise
            time.sleep(min(wait,120))
        except (URLError,TimeoutError,ValueError,json.JSONDecodeError) as e:
            last=str(e)
            time.sleep(min(8*(2**attempt)+random.uniform(1,3),90))
    raise RuntimeError(last or "fetch failed")

def article_time(a):
    s=a.get("seendate") or ""
    try:
        return datetime.strptime(s,"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except: return datetime.now(timezone.utc)

def make_events(articles,country):
    raw=[]
    for a in articles:
        title=(a.get("title") or "").strip()
        url=(a.get("url") or "").strip()
        if not title or not url: continue
        raw.append({
            "title":title,"url":url,"domain":a.get("domain",""),
            "source_country":a.get("sourcecountry",""),
            "published_at":article_time(a).isoformat(),
            "category":classify(title)
        })
    raw.sort(key=lambda x:(domain_score(x["domain"]),x["published_at"]),reverse=True)
    groups=[]
    for a in raw:
        hit=None
        for g in groups[:180]:
            if sim(a["title"],g["title"])>=0.55:
                hit=g; break
        if hit: hit["sources"].append(a)
        else:
            groups.append({"title":a["title"],"sources":[a],"category":a["category"]})
    events=[]
    for g in groups:
        ss=g["sources"]
        ss.sort(key=lambda x:(domain_score(x["domain"]),x["published_at"]),reverse=True)
        primary=ss[0]
        cats=[x["category"] for x in ss]
        cat=max(set(cats),key=cats.count)
        source_domains=list(dict.fromkeys(x["domain"] for x in ss if x["domain"]))
        domestic=sum(1 for x in ss if x["source_country"]==country["code"])/max(1,len(ss))
        title=primary["title"]
        novelty=min(1.0,0.35+0.12*len(ss))
        authority=domain_score(primary["domain"])
        diversity=min(1.0,len(source_domains)/4)
        impact_terms=["war","attack","sanction","rate","election","earthquake","missile","tariff","核","战争","袭击","制裁","利率","选举","地震","导弹"]
        impact=min(1.0,sum(1 for w in impact_terms if norm(w) in norm(title))/3)
        score=round(100*(0.20*authority+0.20*diversity+0.25*novelty+0.20*domestic+0.15*impact))
        events.append({
            "id":hashlib.sha1((country["name"]+"|"+norm(title)).encode()).hexdigest()[:12],
            "event_country":country["name"],
            "country_code":country["code"],
            "title":title,
            "category":cat,
            "domestic_score":round(domestic,2),
            "importance":score,
            "published_at":primary["published_at"],
            "source":primary["domain"],
            "url":primary["url"],
            "sources":[{"domain":x["domain"],"url":x["url"],"title":x["title"]} for x in ss[:6]]
        })
    events.sort(key=lambda x:(x["importance"],x["published_at"]),reverse=True)
    return events

def supplement_events():
    # One broad global pass; only used if it succeeds.
    data=fetch('"United Nations" OR "NATO" OR "European Union" OR "IMF" OR "World Bank" OR "G7" OR "global economy" OR "international security"')
    arts=data.get("articles",[]) if isinstance(data,dict) else []
    fake={"name":"国际组织/全球","english":"Global","code":"GLOBAL"}
    return make_events(arts,fake)

def load_old():
    try:return json.load(open(DATA,encoding="utf-8"))
    except:return None

def main():
    old=load_old()
    all_events=[]; countries_out=[]; errors=[]
    # 6 sec between calls materially reduces burst rate-limit pressure.
    for tier,items in COUNTRY_DATA["countries"].items():
        maxn=TARGETS[tier]["max"]
        for idx,c in enumerate(items):
            if idx>0 or tier!="tier1": time.sleep(6)
            try:
                data=fetch(c["query"])
                arts=data.get("articles",[]) if isinstance(data,dict) else []
                ev=make_events(arts,c)
                ev=ev[:maxn]
                countries_out.append({"tier":tier,"country":c["name"],"code":c["code"],"count":len(ev),"target_max":maxn,"events":ev,"status":"fresh"})
                all_events.extend(ev)
            except Exception as e:
                errors.append(f"{tier}/{c['name']}: {e}")
                oldc=next((x for x in (old or {}).get("countries",[]) if x.get("country")==c["name"]),None)
                fallback=oldc.get("events",[]) if oldc else []
                countries_out.append({"tier":tier,"country":c["name"],"code":c["code"],"count":len(fallback),"target_max":maxn,"events":fallback,"status":"stale_fallback" if fallback else "failed"})
                all_events.extend(fallback)
    try:
        time.sleep(6)
        sup=supplement_events()[:TARGETS["supplement"]["max"]]
        supplement={"count":len(sup),"events":sup,"status":"fresh"}
        all_events.extend(sup)
    except Exception as e:
        errors.append(f"supplement: {e}")
        oldsup=(old or {}).get("supplement",{})
        supplement={"count":len(oldsup.get("events",[])),"events":oldsup.get("events",[]),"status":"stale_fallback" if oldsup.get("events") else "failed"}

    # Global TOP is event-level, not article-level.
    uniq={}
    for e in all_events:
        uniq[e["id"]]=e
    top=sorted(uniq.values(),key=lambda x:(x.get("importance",0),x.get("domestic_score",0)),reverse=True)[:30]
    now=datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    fresh=sum(1 for c in countries_out if c["status"]=="fresh")
    out={
      "version":"11.0",
      "generated_at":now.isoformat(),
      "window":"past_24h",
      "source":"GDELT DOC 2.0",
      "quality":{"country_count":len(countries_out),"fresh_country_count":fresh,"failed_or_stale":len(countries_out)-fresh,"errors":errors[:80]},
      "global_top":top,
      "countries":countries_out,
      "supplement":supplement,
      "summary":f"北京时间 {now:%Y-%m-%d %H:%M} 生成；最近24小时；Tier1优先20–30条/国，其余按上限输出。"
    }
    tmp=DATA+".tmp"
    os.makedirs(os.path.dirname(DATA),exist_ok=True)
    with open(tmp,"w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=2)
    os.replace(tmp,DATA)
    history=os.path.join(ROOT,"data","history")
    os.makedirs(history,exist_ok=True)
    with open(os.path.join(history,now.strftime("%Y-%m-%d")+".json"),"w",encoding="utf-8") as f:
        json.dump(out,f,ensure_ascii=False)
    print(json.dumps(out["quality"],ensure_ascii=False))

if __name__=="__main__": main()
