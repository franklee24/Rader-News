
#!/usr/bin/env python3
# 雷达新闻 V14 - 多源 RSS 生产器
# 主源：Google News RSS 聚合（不依赖 GDELT）
# 设计原则：单源失败不阻断；429 不重试；上一份成功快照可回退。

import csv, datetime as dt, email.utils, hashlib, html, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = json.load(open(os.path.join(ROOT,"config/country_tiers.json"),encoding="utf-8"))
OUT = os.path.join(ROOT,"data")
DAILY = os.path.join(OUT,"daily.json")
HISTORY = os.path.join(OUT,"history")
os.makedirs(HISTORY, exist_ok=True)

UA = "LeidaNews/14.0 (+https://github.com/franklee24/Rader-News)"
TIMEOUT = 18
MAX_PER_COUNTRY = 70
WORKERS = 3

CAT_TERMS = {
 "政治":["election","government","president","prime minister","parliament","cabinet","policy","政治","政府","总统","选举","议会"],
 "宏观经济":["economy","economic","GDP","inflation","interest rate","central bank","宏观","经济","通胀","利率","央行"],
 "金融":["bank","market","stocks","bond","currency","finance","金融","股市","债券","汇率","银行"],
 "产业/商业":["company","business","industry","trade","manufacturing","merger","商业","产业","贸易","制造","企业"],
 "科技":["technology","AI","artificial intelligence","chip","semiconductor","科技","人工智能","芯片","半导体"],
 "能源":["oil","gas","energy","power","nuclear","能源","石油","天然气","电力","核能"],
 "国防安全":["military","defense","missile","army","navy","security","国防","军事","导弹","安全"],
 "外交":["diplomacy","foreign","summit","minister","treaty","外交","峰会","外长","条约"],
 "社会":["society","health","education","protest","crime","social","社会","医疗","教育","抗议"],
 "灾害":["earthquake","flood","fire","storm","disaster","wildfire","地震","洪水","火灾","风暴","灾害"],
}
HIGH_IMPACT = ["war","strike","attack","sanction","tariff","election","rate","default","bankruptcy","nuclear","missile","earthquake","flood","ceasefire","invasion",
               "战争","袭击","制裁","关税","选举","利率","核","导弹","地震","洪水","停火","入侵"]

def parse_date(s):
    if not s: return None
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(dt.timezone.utc)
    except Exception:
        return None

def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>"," ",s or ""))
    return re.sub(r"\s+"," ",s).strip()

def fetch(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"application/rss+xml, application/xml, text/xml;q=0.9,*/*;q=0.5"})
    try:
        with urlopen(req,timeout=TIMEOUT) as r:
            status=getattr(r,"status",200)
            body=r.read()
            if status == 429: return None,"429"
            if status >= 500: return None,str(status)
            return body,None
    except Exception as e:
        msg=str(e)
        if "429" in msg: return None,"429"
        return None,msg[:100]

def google_rss(query):
    url="https://news.google.com/rss/search?q="+quote_plus(query)+"&hl=en-US&gl=US&ceid=US:en"
    body,err=fetch(url)
    if not body:
        return [],err
    try:
        root=ET.fromstring(body)
    except Exception as e:
        return [],"XML:"+str(e)[:80]
    items=[]
    for it in root.findall(".//item"):
        title=clean(it.findtext("title"))
        link=(it.findtext("link") or "").strip()
        pub=parse_date(it.findtext("pubDate"))
        desc=clean(it.findtext("description"))
        src_el=it.find("source")
        source=(src_el.text.strip() if src_el is not None and src_el.text else "")
        source_url=(src_el.get("url","") if src_el is not None else "")
        if title and link:
            items.append({"title":title,"link":link,"published_at":pub.isoformat() if pub else None,
                          "source":source or "Google News","source_url":source_url,"description":desc})
    return items,None


def bing_rss(query):
    url="https://www.bing.com/news/search?q="+quote_plus(query)+"&format=rss"
    body,err=fetch(url)
    if not body: return [],err
    try:
        root=ET.fromstring(body)
    except Exception as e:
        return [],"XML:"+str(e)[:80]
    items=[]
    for it in root.findall(".//item"):
        title=clean(it.findtext("title")); link=(it.findtext("link") or "").strip()
        pub=parse_date(it.findtext("pubDate")); desc=clean(it.findtext("description"))
        src_el=it.find("source"); source=(src_el.text.strip() if src_el is not None and src_el.text else "")
        if title and link:
            items.append({"title":title,"link":link,"published_at":pub.isoformat() if pub else None,
                          "source":source or "Bing News","source_url":"","description":desc})
    return items,None

def normalize_title(t):
    t=t.lower()
    t=re.sub(r"\[[^\]]+\]|\([^)]*\)"," ",t)
    t=re.sub(r"https?://\S+"," ",t)
    t=re.sub(r"[^0-9a-z\u4e00-\u9fff]+"," ",t)
    return " ".join(t.split())

def sim(a,b):
    a=set(normalize_title(a).split()); b=set(normalize_title(b).split())
    if not a or not b:return 0
    return len(a&b)/len(a|b)

def category(t):
    low=t.lower()
    scores={c:sum(1 for x in terms if x.lower() in low) for c,terms in CAT_TERMS.items()}
    return max(scores,key=scores.get) if max(scores.values()) else "政治"

def importance(country, source, title, source_count=1):
    x=42
    if source_count>=3:x+=15
    elif source_count==2:x+=8
    if source and source.lower() not in ("google news",""): x+=8
    low=title.lower()
    x+=min(25,sum(2 for k in HIGH_IMPACT if k.lower() in low))
    return max(0,min(100,x))

def domestic_score(title,country):
    # broad domesticity heuristic: country name + governing/economic/social terms.
    low=title.lower()
    aliases=[country["en"].lower(),country["name"].lower()]
    domestic=["government","president","prime minister","parliament","central bank","economy","company","industry",
              "technology","energy","military","health","education","election","国内","政府","经济","央行","企业","科技","能源","军事","医疗","教育","选举"]
    hit=sum(1 for a in aliases if a in low)
    hit+=min(5,sum(1 for k in domestic if k in low))
    return min(100,20*hit)

def event_key(t):
    return hashlib.sha1(normalize_title(t).encode("utf-8")).hexdigest()[:16]

def collect_country(c):
    # One broad query per country. It is deliberately not retried on 429.
    name,en,code,mi,ma=c
    q=f'"{en}" (government OR economy OR technology OR defense OR diplomacy OR business OR energy OR society) when:1d'
    items,err=google_rss(q)
    if not items:
        print(f"[{name}] Google News unavailable ({err}), fallback -> Bing News")
        items,err2=bing_rss(q)
        if items: err=None
        else: err=err2 or err
    now=dt.datetime.now(dt.timezone.utc)
    cutoff=now-dt.timedelta(hours=25)
    clean_items=[]
    for it in items[:MAX_PER_COUNTRY]:
        p=parse_date(it.get("published_at"))
        if p and p < cutoff: continue
        it.update(event_country=name,event_country_en=en,code=code,tier=None)
        clean_items.append(it)
    return clean_items,err

def collect_supplement():
    q='("world" OR "global" OR "summit" OR "war" OR "market" OR "technology") when:1d'
    return google_rss(q)

def cluster(items):
    events=[]
    for a in sorted(items,key=lambda x:x.get("published_at") or "",reverse=True):
        placed=False
        for e in events:
            if sim(a["title"],e["title"])>=0.58:
                e["sources"].append(a)
                placed=True; break
        if not placed:
            events.append({"id":event_key(a["title"]),"title":a["title"],"published_at":a.get("published_at"),
                           "event_country":a.get("event_country",""),"event_country_en":a.get("event_country_en",""),
                           "code":a.get("code",""),"sources":[a]})
    out=[]
    for e in events:
        srcs=e["sources"]
        uniq={}
        for s in srcs: uniq[s.get("source","Google News")]=s
        best=sorted(srcs,key=lambda x:(x.get("published_at") or "",x.get("source","")),reverse=True)[0]
        e["sources"] = list(uniq.values())[:8]
        e["source_count"]=len(e["sources"])
        e["source_names"]=[x.get("source","") for x in e["sources"]]
        e["url"]=best.get("link")
        e["source_url"]=best.get("source_url","")
        e["source"]=best.get("source","Google News")
        e["category"]=category(e["title"])
        e["domestic_score"]=domestic_score(e["title"],{"name":e["event_country"],"en":e["event_country_en"]})
        e["importance"]=importance(e["event_country"],e["source"],e["title"],e["source_count"])+round(e["domestic_score"]*0.12)
        e["why_important"]="涉及"+e["category"]+"，具有跨市场或政策观察价值。"
        e["impact"]="重点观察政策、市场、产业或安全层面的后续反应。"
        e["next_72h"]="关注官方后续声明、政策落地、市场反应及相关国家/机构行动。"
        out.append(e)
    return sorted(out,key=lambda x:x["importance"],reverse=True)

def main():
    print("雷达新闻 V14：多源稳定模式（GDELT 已移出主链）")
    print("目标：Tier1 20-30 / Tier2 ≤20 / Tier3 ≤15 / Tier4 ≤10 / Supplement 10")
    results={}
    all_items=[]
    failures=[]
    countries_flat=[]
    for tier, arr in CONFIG["tiers"].items():
        for c in arr:
            countries_flat.append((tier,c))
    def worker(tier,c):
        items,err=collect_country(c)
        return tier,c,items,err
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs=[ex.submit(worker,tier,c) for tier,c in countries_flat]
        for fut in as_completed(futs):
            tier,c,items,err=fut.result()
            name=c[0]
            if err: failures.append({"country":name,"error":err})
            for x in items:
                x["tier"]=tier
            results[name]=items
            print(f"[{tier}] {name}: {len(items)} candidates" + (f" | {err}" if err else ""))

    supplement,serr=collect_supplement()
    if not supplement:
        supplement,serr2=bing_rss('global world major news when:1d')
        if supplement: serr=None
        else: serr=serr2 or serr
    if serr: failures.append({"country":"Supplement","error":serr})
    for x in supplement:
        x.update(tier="supplement",event_country="国际/全球",event_country_en="Global",code="GLOBAL")
    # Build per-country event sets
    report={"generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),
            "generated_beijing":dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
            "window_hours":24,"version":"V14.0","source_mode":"multi-rss",
            "source_policy":"GDELT removed from critical path; 429 never blocks publication.",
            "failures":failures,"tiers":{},"global_top":[],"supplement":[]}
    all_events=[]
    for tier,arr in CONFIG["tiers"].items():
        report["tiers"][tier]={}
        for c in arr:
            name=c[0]; ev=cluster(results.get(name,[]))
            # target minimum only for tier1; others use available, capped.
            ev=ev[:c[4]]
            report["tiers"][tier][name]={"country":name,"country_en":c[1],"code":c[2],
                                         "target_min":c[3],"target_max":c[4],
                                         "count":len(ev),"events":ev}
            all_events += ev
    sup=cluster(supplement)[:10]
    report["supplement"]=sup
    # Global top is cross-country unique by event id/title similarity
    top=cluster(all_events)[:20]
    report["global_top"]=top
    report["stats"]={
        "countries":sum(len(v) for v in report["tiers"].values()),
        "events":sum(x["count"] for v in report["tiers"].values() for x in v.values()),
        "tier1_events":sum(x["count"] for x in report["tiers"]["tier1"].values()),
        "supplement_events":len(sup),
        "failed_sources":len(failures)
    }
    # If live collection returned nothing, preserve last good snapshot rather than publishing a blank page.
    if report["stats"]["events"] == 0 and os.path.exists(DAILY):
        old=json.load(open(DAILY,encoding="utf-8"))
        old["generated_at"]=report["generated_at"]; old["stale_fallback"]=True
        old["current_run_failures"]=failures
        report=old
        print("本轮没有取得有效新闻，已保留上一份成功快照，不发布空数据。")
    else:
        report["stale_fallback"]=False
        json.dump(report,open(DAILY,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        date=report["generated_beijing"][:10]
        json.dump(report,open(os.path.join(HISTORY,date+".json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print("完成：",report["stats"])
    if failures: print("部分源失败（不阻断）：",failures[:10])

if __name__=="__main__":
    main()
