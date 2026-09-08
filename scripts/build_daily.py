
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
def load_config():
    """Load country configuration from the current repo layout, with backward compatibility."""
    candidates = [
        os.path.join(ROOT, "config.json"),
        os.path.join(ROOT, "config", "country_tiers.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            # Current repository format:
            # {"countries": {"tier1": [...], ...}}
            if isinstance(raw, dict) and isinstance(raw.get("countries"), dict):
                return {"tiers": raw["countries"]}
            # Original V14 package format:
            # {"tiers": {"tier1": [...], ...}}
            if isinstance(raw, dict) and isinstance(raw.get("tiers"), dict):
                return raw
            raise ValueError(f"Unsupported config schema: {path}")
    raise FileNotFoundError(
        "No country configuration found. Expected config.json or config/country_tiers.json"
    )

CONFIG = load_config()
# Fail fast with a clear message before any network requests.
_REQUIRED_TIERS = ("tier1", "tier2", "tier3", "tier4")
for _tier in _REQUIRED_TIERS:
    if _tier not in CONFIG["tiers"] or not isinstance(CONFIG["tiers"][_tier], list):
        raise ValueError(f"Invalid country configuration: missing list for {_tier}")
print(
    "Config OK:",
    ", ".join(f"{k}={len(CONFIG['tiers'][k])}" for k in _REQUIRED_TIERS)
)

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
    if not s:
        return None
    s = str(s).strip()
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(dt.timezone.utc)
    except Exception:
        pass
    # Atom / ISO-8601 timestamps used by several first-party feeds.
    try:
        x=s.replace("Z","+00:00")
        return dt.datetime.fromisoformat(x).astimezone(dt.timezone.utc)
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
            if status >= 400: return None,str(status)
            return body,None
    except Exception as e:
        msg=str(e)
        if "429" in msg: return None,"429"
        return None,msg[:140]

def parse_rss(body, fallback_source="RSS"):
    try:
        root=ET.fromstring(body)
    except Exception as e:
        return [],"XML:"+str(e)[:100]
    items=[]
    # RSS 2.0, RDF/RSS and Atom are all handled.
    nodes=root.findall(".//item")
    if not nodes:
        nodes=root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for it in nodes:
        title=clean(it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title"))
        link=(it.findtext("link") or "").strip()
        if not link:
            for le in it.findall("{http://www.w3.org/2005/Atom}link"):
                href=le.get("href")
                if href:
                    link=href.strip(); break
        pub=(it.findtext("pubDate") or it.findtext("published") or it.findtext("updated") or
             it.findtext("{http://www.w3.org/2005/Atom}published") or
             it.findtext("{http://www.w3.org/2005/Atom}updated"))
        desc=(it.findtext("description") or it.findtext("summary") or
              it.findtext("{http://www.w3.org/2005/Atom}summary") or "")
        src_el=it.find("source")
        source=(src_el.text.strip() if src_el is not None and src_el.text else "")
        source_url=(src_el.get("url","") if src_el is not None else "")
        # Dublin Core creator is useful for some feeds.
        if not source:
            creator=it.findtext("{http://purl.org/dc/elements/1.1/}creator")
            source=clean(creator) if creator else fallback_source
        p=parse_date(pub)
        if title and link:
            items.append({"title":title,"link":link,"published_at":p.isoformat() if p else None,
                          "source":source or fallback_source,"source_url":source_url,"description":clean(desc)})
    return items,None

def rss_feed(url, source):
    body,err=fetch(url)
    if not body:
        return [],err
    return parse_rss(body, source)

def google_rss(query):
    url="https://news.google.com/rss/search?q="+quote_plus(query)+"&hl=en-US&gl=US&ceid=US:en"
    return rss_feed(url,"Google News")

def bing_rss(query):
    url="https://www.bing.com/news/search?q="+quote_plus(query)+"&format=rss"
    return rss_feed(url,"Bing News")

# First-party / major publisher feeds are the primary fallback.  They are deliberately
# redundant: one dead feed must never make a country empty.
GLOBAL_FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("BBC UK", "https://feeds.bbci.co.uk/news/uk/rss.xml"),
    ("DW", "https://rss.dw.com/rdf/rss-en-all"),
    ("The Guardian World", "https://www.theguardian.com/world/rss"),
    ("The Guardian Business", "https://www.theguardian.com/business/rss"),
    ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
]
COUNTRY_FEEDS = {
    "美国": [
        ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
        ("NPR Business", "https://feeds.npr.org/1006/rss.xml"),
        ("NPR Technology", "https://feeds.npr.org/1019/rss.xml"),
        ("BBC US", "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"),
    ],
    "中国": [
        ("SCMP China", "https://www.scmp.com/rss/91/feed"),
        ("BBC China", "https://feeds.bbci.co.uk/news/world/asia/china/rss.xml"),
        ("The Guardian China", "https://www.theguardian.com/world/china/rss"),
    ],
    "英国": [
        ("BBC UK", "https://feeds.bbci.co.uk/news/uk/rss.xml"),
        ("The Guardian UK", "https://www.theguardian.com/uk/rss"),
    ],
    "法国": [
        ("France24 France", "https://www.france24.com/en/france/rss"),
        ("The Guardian France", "https://www.theguardian.com/world/france/rss"),
    ],
    "德国": [
        ("DW Germany", "https://rss.dw.com/rdf/rss-en-ger"),
        ("The Guardian Germany", "https://www.theguardian.com/world/germany/rss"),
    ],
    "俄罗斯": [
        ("TASS", "https://tass.com/rss/v2.xml"),
        ("The Guardian Russia", "https://www.theguardian.com/world/russia/rss"),
    ],
    "日本": [
        ("NHK", "https://www3.nhk.or.jp/rss/news/cat0.xml"),
        ("The Guardian Japan", "https://www.theguardian.com/world/japan/rss"),
        ("BBC Japan", "https://feeds.bbci.co.uk/news/world/asia/rss.xml"),
    ],
    "印度": [("The Hindu National", "https://www.thehindu.com/news/national/feeder/default.rss")],
    "加拿大": [("CBC World", "https://www.cbc.ca/cmlink/rss-world")],
    "澳大利亚": [("ABC Australia", "https://www.abc.net.au/news/feed/2942460/rss.xml")],
    "意大利": [("The Guardian Italy", "https://www.theguardian.com/world/italy/rss")],
    "西班牙": [("The Guardian Spain", "https://www.theguardian.com/world/spain/rss")],
    "以色列": [("The Guardian Israel", "https://www.theguardian.com/world/israel/rss")],
    "乌克兰": [("The Guardian Ukraine", "https://www.theguardian.com/world/ukraine/rss")],
}

FEED_CACHE={}

def get_feed(url, source):
    key=(url,source)
    if key not in FEED_CACHE:
        FEED_CACHE[key]=rss_feed(url,source)
    return FEED_CACHE[key]

COUNTRY_ALIASES={
    "美国":["united states","u.s.","u.s","america","washington"],
    "中国":["china","chinese","beijing"],
    "英国":["united kingdom","u.k.","uk","britain","london"],
    "法国":["france","french","paris"],
    "德国":["germany","german","berlin"],
    "俄罗斯":["russia","russian","moscow"],
    "日本":["japan","japanese","tokyo"],
    "印度":["india","indian","new delhi"],
    "巴西":["brazil","brazilian","brasilia"],
    "沙特阿拉伯":["saudi","saudi arabia","riyadh"],
    "韩国":["south korea","korea","seoul"],
    "加拿大":["canada","canadian","ottawa"],
    "澳大利亚":["australia","australian","canberra"],
    "乌克兰":["ukraine","ukrainian","kyiv","kiev"],
    "意大利":["italy","italian","rome"],
    "印度尼西亚":["indonesia","indonesian","jakarta"],
    "土耳其":["turkey","turkish","ankara","istanbul"],
    "阿联酋":["united arab emirates","uae","dubai","abu dhabi"],
    "墨西哥":["mexico","mexican","mexico city"],
    "伊朗":["iran","iranian","tehran"],
    "瑞士":["switzerland","swiss","bern","geneva"],
    "新加坡":["singapore","singaporean"],
    "南非":["south africa","south african","pretoria","johannesburg"],
    "荷兰":["netherlands","dutch","amsterdam"],
    "以色列":["israel","israeli","jerusalem","tel aviv"],
    "西班牙":["spain","spanish","madrid"],
    "埃及":["egypt","egyptian","cairo"],
    "尼日利亚":["nigeria","nigerian","abuja"],
    "阿根廷":["argentina","argentine","buenos aires"],
    "波兰":["poland","polish","warsaw"],
    "越南":["vietnam","vietnamese","hanoi","ho chi minh"],
}

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

def normalize_country(c):
    """Normalize current dict config and legacy list config to one dict shape."""
    if isinstance(c, dict):
        return {
            "name": c.get("name") or c.get("country") or c.get("zh") or c.get("en"),
            "en": c.get("en") or c.get("english") or c.get("name"),
            "code": c.get("code") or c.get("iso") or "",
            "min": int(c.get("min", 1)),
            "max": int(c.get("max", 20)),
        }
    if isinstance(c, (list, tuple)) and len(c) >= 5:
        return {
            "name": c[0], "en": c[1], "code": c[2],
            "min": int(c[3]), "max": int(c[4])
        }
    raise TypeError(f"Unsupported country config entry: {c!r}")

def recent_items(items, hours=26):
    cutoff=dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=hours)
    out=[]
    for it in items:
        p=parse_date(it.get("published_at"))
        if p is not None and p < cutoff:
            continue
        # If a feed omits the date, keep it for the later ranking rather than silently deleting it.
        if p is None:
            it["date_unknown"]=True
        out.append(it)
    return out

def title_matches_country(title, country):
    low=(title or "").lower()
    aliases=COUNTRY_ALIASES.get(country,[])
    return any(a in low for a in aliases)

def dedupe_articles(items):
    seen=set(); out=[]
    for x in sorted(items,key=lambda z:z.get("published_at") or "",reverse=True):
        key=normalize_title(x.get("title",""))
        if not key or key in seen: continue
        seen.add(key); out.append(x)
    return out

def collect_country(c):
    c=normalize_country(c)
    name,en,code,mi,ma=c["name"],c["en"],c["code"],c["min"],c["max"]
    pool=[]; diagnostics=[]

    # 1) Country-specific first-party/major publisher feeds.
    feeds=COUNTRY_FEEDS.get(name,[])
    for source,url in feeds:
        items,err=get_feed(url,source)
        diagnostics.append(f"{source}:{len(items)}" + (f"({err})" if err else ""))
        for x in items:
            x["source_kind"]="publisher"
            x["feed_country"]=name
            pool.append(x)

    # 2) Global feeds: only retain items that clearly mention the country.
    for source,url in GLOBAL_FEEDS:
        items,err=get_feed(url,source)
        diagnostics.append(f"{source}:{len(items)}" + (f"({err})" if err else ""))
        for x in items:
            if title_matches_country(x.get("title","")+" "+x.get("description","") ,name):
                x=x.copy(); x["source_kind"]="publisher"; x["feed_country"]=name; pool.append(x)

    # 3) Search aggregators are supplementary only, and the query is deliberately broad.
    queries=[f'"{en}" when:1d', f'{en} news when:1d']
    for q in queries:
        items,err=google_rss(q)
        diagnostics.append(f"Google:{len(items)}" + (f"({err})" if err else ""))
        for x in items:
            x=x.copy(); x["source_kind"]="aggregator"; pool.append(x)
        if len(pool)>=max(50,mi*2): break
    if len(pool)<max(10,mi):
        q=f'{en} news when:1d'
        items,err=bing_rss(q)
        diagnostics.append(f"Bing:{len(items)}" + (f"({err})" if err else ""))
        for x in items:
            x=x.copy(); x["source_kind"]="aggregator"; pool.append(x)

    pool=recent_items(dedupe_articles(pool),26)
    # For country-specific feeds, the feed itself is evidence of event-country relevance.
    for it in pool:
        it.update(event_country=name,event_country_en=en,code=code,tier=None)
    print(f"[{name}] sources="+" | ".join(diagnostics[:12])+f" | pool24h={len(pool)}")
    return pool[:MAX_PER_COUNTRY],None if pool else "; ".join(diagnostics[:6])

def collect_supplement():
    pool=[]
    for source,url in GLOBAL_FEEDS:
        items,err=get_feed(url,source)
        for x in items:
            x=x.copy(); x["source_kind"]="publisher"; x["event_country"]="国际/全球"; x["event_country_en"]="Global"; x["code"]="GLOBAL"; pool.append(x)
    items,err=google_rss('world global major news when:1d')
    pool.extend(items)
    pool=recent_items(dedupe_articles(pool),26)
    return pool[:60],None if pool else (err or "no supplement items" )

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
        for s in srcs:
            key=s.get("link") or s.get("source","Google News")
            uniq[key]=s
        best=sorted(srcs,key=lambda x:(x.get("source_kind")!="publisher", x.get("published_at") or "", x.get("source","")),reverse=False)[0]
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

def validate_country_config():
    for tier in ("tier1", "tier2", "tier3", "tier4"):
        arr = CONFIG["tiers"].get(tier)
        if not isinstance(arr, list) or not arr:
            raise ValueError(f"Invalid config: {tier} must be a non-empty list")
        for idx, item in enumerate(arr):
            c = normalize_country(item)
            if not c["name"] or not c["en"] or not c["code"]:
                raise ValueError(f"Invalid config: {tier}[{idx}] missing name/en/code")
            if c["min"] < 0 or c["max"] < 1 or c["min"] > c["max"]:
                raise ValueError(f"Invalid config limits: {tier}[{idx}]")
    print("Country config structure OK")

def main():
    validate_country_config()
    print("雷达新闻 V15.0：多源真实新闻生产模式（聚合源仅作补充）")
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
            c = normalize_country(c)
            name = c["name"]
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
            "window_hours":24,"version":"V15.0","source_mode":"multi-rss",
            "source_policy":"GDELT removed from critical path; 429 never blocks publication.",
            "failures":failures,"tiers":{},"global_top":[],"supplement":[]}
    all_events=[]
    for tier,arr in CONFIG["tiers"].items():
        report["tiers"][tier]={}
        for c in arr:
            c = normalize_country(c)
            name = c["name"]
            ev=cluster(results.get(name,[]))
            # target minimum only for tier1; others use available, capped.
            ev=ev[:c["max"]]
            report["tiers"][tier][name]={"country":name,"country_en":c["en"],"code":c["code"],
                                         "target_min":c["min"],"target_max":c["max"],
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
    # Never publish a blank snapshot. If this is the first run and no source produced data,
    # fail loudly so the workflow is red instead of pretending the daily product succeeded.
    if report["stats"]["events"] == 0:
        if os.path.exists(DAILY):
            old=json.load(open(DAILY,encoding="utf-8"))
            old["stale_fallback"]=True
            old["current_run_failures"]=failures
            json.dump(old,open(DAILY,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        raise RuntimeError("NO_NEWS_DATA: all configured feeds/searches returned no usable 24h events")
    if report["stats"]["tier1_events"] == 0:
        raise RuntimeError("NO_TIER1_DATA: Tier1 produced zero events; refusing to publish a false-success snapshot")
    report["stale_fallback"]=False
    json.dump(report,open(DAILY,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    date=report["generated_beijing"][:10]
    json.dump(report,open(os.path.join(HISTORY,date+".json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print("完成：",report["stats"])
    if failures: print("部分源失败（不阻断）：",failures[:10])

if __name__=="__main__":
    main()
