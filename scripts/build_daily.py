#!/usr/bin/env python3
# 雷达新闻 V17 - 多源直连 RSS 生产器
# 核心原则：不再把 Google/Bing 当唯一数据源；源失败不等于任务成功；低于质量阈值直接让 Actions 失败。

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = json.load(open(os.path.join(ROOT, "config/country_tiers.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "data")
DAILY = os.path.join(OUT, "daily.json")
HISTORY = os.path.join(OUT, "history")
os.makedirs(HISTORY, exist_ok=True)

UA = "LeidaNews/17.0 (+https://github.com/franklee24/Rader-News)"
TIMEOUT = 15
WORKERS = 8
MIN_TOTAL_EVENTS = 20

# 直连 RSS：优先使用媒体/机构自己的 feed，避免 Google News 429 成为单点故障。
# country 代表该 feed 的主要本土新闻覆盖国；global feed 只进入全球补充池。
FEEDS = [
    # Tier 1
    ("NPR", "US", "https://feeds.npr.org/1001/rss.xml", "tier1"),
    ("NPR Politics", "US", "https://feeds.npr.org/1014/rss.xml", "tier1"),
    ("NYTimes US", "US", "https://rss.nytimes.com/services/xml/rss/nyt/US.xml", "tier1"),
    ("CNN Top Stories", "US", "http://rss.cnn.com/rss/cnn_topstories.rss", "tier1"),
    ("BBC UK", "GB", "https://feeds.bbci.co.uk/news/uk/rss.xml", "tier1"),
    ("Guardian UK", "GB", "https://www.theguardian.com/uk-news/rss", "tier1"),
    ("China Daily China", "CN", "https://www.chinadaily.com.cn/rss/china_rss.xml", "tier1"),
    ("China Daily Business", "CN", "https://www.chinadaily.com.cn/rss/bizchina_rss.xml", "tier1"),
    ("SCMP China", "CN", "https://www.scmp.com/rss/91/feed", "tier1"),
    ("France24", "FR", "https://www.france24.com/en/rss", "tier1"),
    ("France24 France", "FR", "https://www.france24.com/en/france/rss", "tier1"),
    ("DW", "DE", "https://rss.dw.com/xml/rss-en-all", "tier1"),
    ("TASS", "RU", "https://tass.com/rss/v2.xml", "tier1"),
    ("Moscow Times", "RU", "https://www.themoscowtimes.com/rss/news", "tier1"),
    ("NHK", "JP", "https://www3.nhk.or.jp/rss/news/cat0.xml", "tier1"),
    ("Japan Times", "JP", "https://www.japantimes.co.jp/feed/", "tier1"),
    # Tier 2
    ("The Hindu", "IN", "https://www.thehindu.com/feeder/default.rss", "tier2"),
    ("Times of India", "IN", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms", "tier2"),
    ("G1 Brazil", "BR", "https://g1.globo.com/rss/g1/", "tier2"),
    ("Arab News", "SA", "https://www.arabnews.com/rss.xml", "tier2"),
    ("Yonhap", "KR", "https://www.yna.co.kr/rss/news.xml", "tier2"),
    ("Korea Times", "KR", "https://feed.koreatimes.co.kr/k/allnews.xml", "tier2"),
    ("CBC Canada", "CA", "https://www.cbc.ca/webfeed/rss/rss-canada", "tier2"),
    ("CBC Business", "CA", "https://www.cbc.ca/webfeed/rss/rss-business", "tier2"),
    ("SBS Australia", "AU", "https://www.sbs.com.au/news/topic/latest/rss.xml", "tier2"),
    # Tier 3
    ("UNIAN", "UA", "https://rss.unian.net/site/news_eng.rss", "tier3"),
    ("ANSA", "IT", "https://www.ansa.it/sito/ansait_rss.xml", "tier3"),
    ("Repubblica", "IT", "https://www.repubblica.it/rss/homepage/rss2.0.xml", "tier3"),
    ("Merdeka", "ID", "https://www.merdeka.com/feed/", "tier3"),
    ("Republika", "ID", "https://www.republika.co.id/rss/", "tier3"),
    ("TRT World", "TR", "https://www.trtworld.com/rss", "tier3"),
    ("Al Arabiya", "AE", "https://www.alarabiya.net/rss", "tier3"),
    ("El Universal Mexico", "MX", "https://www.eluniversal.com.mx/rss.xml", "tier3"),
    ("Tehran Times", "IR", "https://www.tehrantimes.com/rss", "tier3"),
    ("Swissinfo", "CH", "https://www.swissinfo.ch/eng/rss", "tier3"),
    # Tier 4
    ("CNA Singapore", "SG", "https://www.channelnewsasia.com/rssfeeds/8395986", "tier4"),
    ("Daily Maverick", "ZA", "https://www.dailymaverick.co.za/feed/", "tier4"),
    ("NL Times", "NL", "https://nltimes.nl/rssfeed", "tier4"),
    ("Times of Israel", "IL", "https://www.timesofisrael.com/feed/", "tier4"),
    ("El Pais", "ES", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "tier4"),
    ("Ahram Online", "EG", "https://english.ahram.org.eg/rss/", "tier4"),
    ("Premium Times Nigeria", "NG", "https://www.premiumtimesng.com/feed", "tier4"),
    ("Buenos Aires Herald", "AR", "https://www.buenosairesherald.com/feed", "tier4"),
    ("Notes from Poland", "PL", "https://notesfrompoland.com/feed/", "tier4"),
    ("VnExpress", "VN", "https://e.vnexpress.net/rss/news.rss", "tier4"),
    # Global / institutional supplement
    ("BBC World", "GLOBAL", "https://feeds.bbci.co.uk/news/world/rss.xml", "supplement"),
    ("Guardian World", "GLOBAL", "https://www.theguardian.com/world/rss", "supplement"),
    ("Al Jazeera", "GLOBAL", "https://www.aljazeera.com/xml/rss/all.xml", "supplement"),
    ("Sky World", "GLOBAL", "https://feeds.skynews.com/feeds/rss/world.xml", "supplement"),
    ("France24 Global", "GLOBAL", "https://www.france24.com/en/rss", "supplement"),
]

CAT_TERMS = {
    "政治": ["election","government","president","prime minister","parliament","cabinet","policy","政治","政府","总统","选举","议会"],
    "宏观经济": ["economy","economic","GDP","inflation","interest rate","central bank","宏观","经济","通胀","利率","央行"],
    "金融": ["bank","market","stocks","bond","currency","finance","金融","股市","债券","汇率","银行"],
    "产业/商业": ["company","business","industry","trade","manufacturing","merger","商业","产业","贸易","制造","企业"],
    "科技": ["technology","AI","artificial intelligence","chip","semiconductor","科技","人工智能","芯片","半导体"],
    "能源": ["oil","gas","energy","power","nuclear","能源","石油","天然气","电力","核能"],
    "国防安全": ["military","defense","missile","army","navy","security","国防","军事","导弹","安全"],
    "外交": ["diplomacy","foreign","summit","minister","treaty","外交","峰会","外长","条约"],
    "社会": ["society","health","education","protest","crime","social","社会","医疗","教育","抗议"],
    "灾害": ["earthquake","flood","fire","storm","disaster","wildfire","地震","洪水","火灾","风暴","灾害"],
}
HIGH_IMPACT = ["war","strike","attack","sanction","tariff","election","rate","default","bankruptcy","nuclear","missile","earthquake","flood","ceasefire","invasion","战争","袭击","制裁","关税","选举","利率","核","导弹","地震","洪水","停火","入侵"]

CODE_TO_COUNTRY = {c["code"]: c for tier in CONFIG["tiers"].values() for c in tier}

def parse_date(s):
    if not s: return None
    try:
        if isinstance(s, dt.datetime):
            return s.astimezone(dt.timezone.utc) if s.tzinfo else s.replace(tzinfo=dt.timezone.utc)
        return email.utils.parsedate_to_datetime(str(s)).astimezone(dt.timezone.utc)
    except Exception:
        try:
            d = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
            return d.astimezone(dt.timezone.utc) if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
        except Exception:
            return None

def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()

def fetch(url):
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9,*/*;q=0.5"})
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
            return body, None
    except Exception as e:
        return None, str(e)[:140]

def tag(root, name):
    for x in root.iter():
        if x.tag.split("}")[-1].lower() == name.lower():
            return x
    return None

def parse_feed(body, source, country, tier):
    root = ET.fromstring(body)
    rows = []
    # RSS 2.0 / RSS 1.0
    for item in [x for x in root.iter() if x.tag.split("}")[-1].lower() in ("item", "entry")]:
        title = clean(next((x.text for x in item if x.tag.split("}")[-1].lower() == "title"), ""))
        link = ""
        for x in item:
            if x.tag.split("}")[-1].lower() == "link":
                link = (x.text or x.attrib.get("href", "")).strip()
                if link: break
        pub = next((x.text for x in item if x.tag.split("}")[-1].lower() in ("pubdate","published","updated","date")), None)
        desc = next((x.text for x in item if x.tag.split("}")[-1].lower() in ("description","summary","content")), "")
        if title and link:
            p = parse_date(pub)
            rows.append({"title": title, "link": link, "published_at": p.isoformat() if p else None, "source": source, "source_url": link, "description": clean(desc), "feed_country": country, "feed_tier": tier})
    return rows

def fetch_feed(feed):
    source, country, url, tier = feed
    body, err = fetch(url)
    if not body:
        return feed, [], err
    try:
        return feed, parse_feed(body, source, country, tier), None
    except Exception as e:
        return feed, [], "XML " + str(e)[:120]

def normalize_title(t):
    t = re.sub(r"\[[^\]]+\]|\([^)]*\)", " ", (t or "").lower())
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", t)
    return " ".join(t.split())

def sim(a,b):
    aa, bb = set(normalize_title(a).split()), set(normalize_title(b).split())
    return len(aa & bb) / len(aa | bb) if aa and bb else 0

def category(title):
    low = title.lower()
    scores = {c: sum(1 for k in ks if k.lower() in low) for c, ks in CAT_TERMS.items()}
    return max(scores, key=scores.get) if max(scores.values()) else "政治"

def event_key(title):
    return hashlib.sha1(normalize_title(title).encode()).hexdigest()[:16]

def cluster(items):
    events = []
    for a in sorted(items, key=lambda x: x.get("published_at") or "", reverse=True):
        match = next((e for e in events if sim(a["title"], e["title"]) >= 0.58), None)
        if match:
            match["sources"].append(a)
        else:
            events.append({"id": event_key(a["title"]), "title": a["title"], "published_at": a.get("published_at"), "event_country": a.get("event_country", a.get("feed_country", "")), "event_country_en": a.get("event_country_en", ""), "code": a.get("code", ""), "sources": [a]})
    out=[]
    for e in events:
        uniq={}
        for s in e["sources"]: uniq[s.get("source", "Unknown")]=s
        srcs=list(uniq.values())[:8]
        best=max(srcs, key=lambda x: x.get("published_at") or "")
        e["sources"]=srcs
        e["source_count"]=len(srcs)
        e["source_names"]=[s.get("source","") for s in srcs]
        e["source"]=best.get("source", "")
        e["url"]=best.get("link", "")
        e["source_url"]=best.get("source_url", "")
        e["category"]=category(e["title"])
        impact=sum(2 for k in HIGH_IMPACT if k.lower() in e["title"].lower())
        e["domestic_score"]=min(100, 20 + impact*8) if e["event_country"] not in ("", "国际/全球") else 10
        e["importance"]=min(100, 42 + min(20, 8*max(0,e["source_count"]-1)) + min(30,impact*3) + round(e["domestic_score"]*.12))
        e["why_important"]="涉及"+e["category"]+"，属于过去24小时值得跟踪的独立事件。"
        e["impact"]="关注政策、市场、产业、安全及国际关系的后续影响。"
        e["next_72h"]="关注官方声明、政策落地、市场反应及相关方后续行动。"
        out.append(e)
    return sorted(out,key=lambda x:x["importance"],reverse=True)

def assign_country(item):
    # Country-specific feeds are trusted for domestic coverage; global feeds remain global.
    code=item.get("feed_country", "GLOBAL")
    c=CODE_TO_COUNTRY.get(code)
    if c:
        item.update(event_country=c["name"], event_country_en=c["en"], code=code)
    else:
        item.update(event_country="国际/全球", event_country_en="Global", code="GLOBAL")
    return item

def main():
    print("雷达新闻 V17：开始多源直连 RSS 采集")
    now=dt.datetime.now(dt.timezone.utc)
    cutoff=now-dt.timedelta(hours=25)
    raw_by_country={}
    failures=[]
    source_ok=0
    source_total=len(FEEDS)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures=[ex.submit(fetch_feed,f) for f in FEEDS]
        for fut in as_completed(futures):
            feed,items,err=fut.result()
            source, country, url, tier=feed
            if err:
                failures.append({"source":source,"country":country,"error":err})
                print(f"[FAIL] {source}: {err}")
                continue
            source_ok+=1
            fresh=[]
            for x in items:
                p=parse_date(x.get("published_at"))
                if p and p < cutoff: continue
                fresh.append(assign_country(x))
            if country == "GLOBAL":
                raw_by_country.setdefault("GLOBAL",[]).extend(fresh)
            else:
                raw_by_country.setdefault(country,[]).extend(fresh)
            print(f"[OK] {source}: {len(fresh)} fresh")

    # Google News is now a LAST-RESORT supplement, not the critical path.
    # Only query countries with no direct feed data, keeping requests bounded.
    missing=[]
    for tier, arr in CONFIG["tiers"].items():
        for c in arr:
            if len(raw_by_country.get(c["code"],[])) < 3:
                missing.append(c)
    if missing:
        print(f"[FALLBACK] {len(missing)} countries need search fallback")
        for c in missing[:12]:
            q=f'"{c["en"]}" (government OR economy OR technology OR defense OR business OR energy) when:1d'
            url="https://news.google.com/rss/search?q="+quote_plus(q)+"&hl=en-US&gl=US&ceid=US:en"
            body,err=fetch(url)
            if not body:
                failures.append({"source":"Google News fallback","country":c["name"],"error":err or "empty"})
                continue
            try:
                rows=parse_feed(body,"Google News","GLOBAL","fallback")
                for x in rows:
                    p=parse_date(x.get("published_at"))
                    if p and p < cutoff: continue
                    x["feed_country"]=c["code"]
                    assign_country(x)
                    raw_by_country.setdefault(c["code"],[]).append(x)
            except Exception as e:
                failures.append({"source":"Google News fallback","country":c["name"],"error":str(e)[:120]})

    report={"generated_at":now.isoformat(),"generated_beijing":dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),"window_hours":24,"version":"V17.0","source_mode":"direct-rss-plus-bounded-fallback","source_total":source_total,"source_ok":source_ok,"failures":failures,"tiers":{},"global_top":[],"supplement":[]}
    all_events=[]
    for tier, arr in CONFIG["tiers"].items():
        report["tiers"][tier]={}
        for c in arr:
            events=cluster(raw_by_country.get(c["code"],[]))[:c["max"]]
            report["tiers"][tier][c["name"]]={"country":c["name"],"country_en":c["en"],"code":c["code"],"target_min":c["min"],"target_max":c["max"],"count":len(events),"events":events}
            all_events.extend(events)
    report["supplement"]=cluster(raw_by_country.get("GLOBAL",[]))[:10]
    report["global_top"]=cluster(all_events + report["supplement"])[:20]
    report["stats"]={"countries":sum(len(v) for v in report["tiers"].values()),"events":sum(x["count"] for v in report["tiers"].values() for x in v.values()),"tier1_events":sum(x["count"] for x in report["tiers"]["tier1"].values()),"supplement_events":len(report["supplement"]),"failed_sources":len(failures),"successful_sources":source_ok}

    # 质量闸门：不能再出现“0 条新闻但 Actions 绿色”。
    if report["stats"]["events"] < MIN_TOTAL_EVENTS:
        print("QUALITY GATE FAILED:", report["stats"])
        print("失败源：", failures[:20])
        raise SystemExit(2)

    report["stale_fallback"]=False
    with open(DAILY,"w",encoding="utf-8") as f: json.dump(report,f,ensure_ascii=False,indent=2)
    date=report["generated_beijing"][:10]
    with open(os.path.join(HISTORY,date+".json"),"w",encoding="utf-8") as f: json.dump(report,f,ensure_ascii=False,indent=2)
    print("QUALITY GATE PASSED:", report["stats"])

if __name__ == "__main__":
    main()
