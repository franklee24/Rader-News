import json, re, time, hashlib, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
OUT = ROOT/"data/daily.json"
API = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT sourcecountry operator: outlet country, useful for domestic coverage.
SOURCE_COUNTRY = {
    "美国":"unitedstates","中国":"china","英国":"unitedkingdom","法国":"france",
    "德国":"germany","俄罗斯":"russia","日本":"japan","印度":"india","巴西":"brazil",
    "沙特阿拉伯":"saudiarabia","韩国":"southkorea","加拿大":"canada","澳大利亚":"australia",
    "乌克兰":"ukraine","意大利":"italy","印度尼西亚":"indonesia","土耳其":"turkey",
    "阿联酋":"unitedarabemirates","墨西哥":"mexico","伊朗":"iran","瑞士":"switzerland",
    "新加坡":"singapore","南非":"southafrica","荷兰":"netherlands","以色列":"israel",
    "西班牙":"spain","埃及":"egypt","尼日利亚":"nigeria","阿根廷":"argentina",
    "波兰":"poland","越南":"vietnam"
}
ALIASES={
"美国":["United States","USA","US","Washington","Trump","Federal Reserve","Congress"],
"中国":["China","Chinese","Beijing","Shanghai","PBOC","Xi Jinping"],
"英国":["United Kingdom","UK","Britain","British","London","Starmer","Bank of England"],
"法国":["France","French","Paris","Macron","Elysee"],
"德国":["Germany","German","Berlin","Scholz","Merz","Bundesbank"],
"俄罗斯":["Russia","Russian","Moscow","Kremlin","Putin"],
"日本":["Japan","Japanese","Tokyo","Nikkei","BOJ","Ishiba"],
"印度":["India","Indian","New Delhi","Modi","RBI"],
"巴西":["Brazil","Brazilian","Brasilia","Lula","central bank"],
"沙特阿拉伯":["Saudi Arabia","Saudi","Riyadh","Crown Prince","Aramco"],
"韩国":["South Korea","Korea","Seoul","Yonhap","Bank of Korea"],
"加拿大":["Canada","Canadian","Ottawa","Trudeau","Carney","Bank of Canada"],
"澳大利亚":["Australia","Australian","Canberra","Albanese","RBA"],
"乌克兰":["Ukraine","Ukrainian","Kyiv","Kiev","Zelensky"],
"意大利":["Italy","Italian","Rome","Meloni","Bank of Italy"],
"印度尼西亚":["Indonesia","Indonesian","Jakarta","Prabowo","Bank Indonesia"],
"土耳其":["Turkey","Turkish","Ankara","Istanbul","Erdogan","central bank"],
"阿联酋":["United Arab Emirates","UAE","Dubai","Abu Dhabi"],
"墨西哥":["Mexico","Mexican","Mexico City","Sheinbaum","Banxico"],
"伊朗":["Iran","Iranian","Tehran","Khamenei","central bank"],
"瑞士":["Switzerland","Swiss","Bern","Zurich","SNB"],
"新加坡":["Singapore","Singaporean","Singapore government","MAS"],
"南非":["South Africa","South African","Pretoria","Johannesburg","SARB"],
"荷兰":["Netherlands","Dutch","Amsterdam","The Hague","ECB"],
"以色列":["Israel","Israeli","Jerusalem","Tel Aviv","Netanyahu"],
"西班牙":["Spain","Spanish","Madrid","Sanchez","Bank of Spain"],
"埃及":["Egypt","Egyptian","Cairo","Sisi","central bank"],
"尼日利亚":["Nigeria","Nigerian","Abuja","Lagos","CBN"],
"阿根廷":["Argentina","Argentine","Buenos Aires","Milei","central bank"],
"波兰":["Poland","Polish","Warsaw","Tusk","central bank"],
"越南":["Vietnam","Vietnamese","Hanoi","Ho Chi Minh","State Bank"]
}
CAT={
"政治":["election","government","president","prime minister","parliament","minister","politics","vote","cabinet","law","court","policy","选举","政府","总统","总理","议会","部长","政治","法律"],
"经济":["economy","economic","growth","inflation","GDP","jobs","employment","fiscal","budget","trade","tariff","经济","通胀","增长","就业","财政","预算","贸易","关税"],
"金融":["central bank","interest rate","rate cut","rate hike","bank","bond","currency","stock","market","finance","Fed","ECB","BoJ","央行","利率","降息","加息","银行","债券","汇率","股市","金融"],
"产业":["company","business","investment","factory","manufacturing","automotive","airline","industry","merger","acquisition","企业","投资","工厂","制造","汽车","航空","产业","并购"],
"科技":["AI","artificial intelligence","chip","semiconductor","quantum","software","technology","cyber","data","科技","人工智能","芯片","半导体","量子","软件","网络安全"],
"能源":["oil","gas","energy","electricity","nuclear","OPEC","solar","wind","能源","石油","天然气","电力","核能"],
"国防":["military","defense","defence","missile","army","navy","air force","weapon","NATO","军方","国防","导弹","军队","海军","空军","武器"],
"外交":["diplomatic","diplomacy","summit","foreign","sanction","treaty","embassy","bilateral","外交","峰会","制裁","条约","使馆"],
"社会":["society","health","education","protest","strike","population","crime","social","school","hospital","社会","卫生","教育","抗议","罢工","人口","犯罪","学校","医院"],
"灾害":["earthquake","flood","fire","storm","hurricane","typhoon","disaster","eruption","地震","洪水","火灾","风暴","飓风","台风","灾害","火山"]
}
AUTH={"reuters.com":1.0,"apnews.com":0.95,"bbc.com":0.9,"nytimes.com":0.9,"ft.com":0.95,"bloomberg.com":0.95,
"theguardian.com":0.85,"cnn.com":0.8,"npr.org":0.8,"nhk.or.jp":0.9,"yonhapnews.co.kr":0.9,
"xinhua.net":0.9,"gov.cn":1.0,"gov.uk":1.0,"elysee.fr":1.0,"bundesregierung.de":1.0,
"kremlin.ru":1.0,"japan.go.jp":1.0}

def norm(s):
    s=re.sub(r"https?://\S+"," ",s.lower())
    s=re.sub(r"[^a-z0-9\u4e00-\u9fff]+"," ",s)
    return " ".join(s.split())

def domain_score(domain):
    d=(domain or "").lower()
    for k,v in AUTH.items():
        if d.endswith(k) or k in d: return v
    return 0.35

def category(title):
    low=title.lower()
    scores={c:sum(1 for k in ks if k.lower() in low) for c,ks in CAT.items()}
    return max(scores,key=scores.get) if max(scores.values()) else "政治"

def domestic_score(a,country):
    title=(a.get("title") or "").lower()
    aliases=[x.lower() for x in ALIASES.get(country,[])]
    hit=sum(x in title for x in aliases)
    terms=["government","president","parliament","minister","central bank","budget","election","policy","court",
           "央行","政府","总统","议会","部长","预算","选举","政策","法院"]
    return min(100,35+20*min(hit,2)+8*sum(x in title for x in terms))

def importance(a,country):
    d=domain_score(a.get("domain"))
    high=sum(x.lower() in (a.get("title") or "").lower() for x in
             ["war","sanction","tariff","rate","election","missile","nuclear","crisis","treaty","strike","earthquake",
              "战争","制裁","关税","利率","选举","导弹","核","危机","条约","地震"])
    return round(min(100,35+d*25+high*7+domestic_score(a,country)*0.28),1)

def similarity(a,b):
    sa=set(norm(a).split()); sb=set(norm(b).split())
    if not sa or not sb:return 0
    return len(sa&sb)/len(sa|sb)

def fetch(query,maxrecords=160):
    """Rate-limited GDELT request with 429/empty/invalid-response protection."""
    params={
        "query":query,
        "mode":"ArtList",
        "format":"json",
        "maxrecords":str(maxrecords),
        "timespan":"24h",
        "sort":"DateDesc"
    }
    url=API+"?"+urlencode(params)
    retries=int(CFG["collection"].get("retries",3))
    backoffs=CFG["collection"].get("backoff_seconds",[30,60,120])

    for attempt in range(retries+1):
        try:
            req=Request(url,headers={
                "User-Agent":"LeidaNews/Final-Daily-Radar (+https://github.com/franklee24/Rader-News)",
                "Accept":"application/json"
            })
            with urlopen(req,timeout=75) as r:
                body=r.read().decode("utf-8","replace").strip()
                if not body:
                    raise RuntimeError("GDELT returned an empty response")
                if not body.startswith("{"):
                    raise RuntimeError(f"GDELT returned non-JSON content: {body[:180]!r}")
                data=json.loads(body)
                if not isinstance(data,dict):
                    raise RuntimeError("GDELT JSON root is not an object")
                return data

        except HTTPError as e:
            retry_after=e.headers.get("Retry-After")
            if e.code == 429 and attempt < retries:
                wait=backoffs[min(attempt,len(backoffs)-1)]
                if retry_after and retry_after.isdigit():
                    wait=max(wait,int(retry_after))
                print(f"429 rate limited; waiting {wait}s ({attempt+1}/{retries})",flush=True)
                time.sleep(wait)
                continue
            raise

        except (URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            if attempt < retries:
                wait=backoffs[min(attempt,len(backoffs)-1)]
                print(f"retryable GDELT error: {e}; waiting {wait}s ({attempt+1}/{retries})",flush=True)
                time.sleep(wait)
                continue
            raise

def eventize(articles,country):
    events=[]
    for a in articles:
        title=(a.get("title") or "").strip()
        url=a.get("url") or a.get("url_mobile") or ""
        if len(title)<12 or not url: continue
        item={"title":title,"url":url,"domain":a.get("domain") or "unknown",
              "published_at":a.get("seendate") or "","source_country":a.get("sourcecountry") or ""}
        placed=None
        for e in events:
            if similarity(title,e["title"])>=0.42:
                placed=e; break
        if placed:
            if all(s["url"]!=url for s in placed["sources"]):
                placed["sources"].append({"name":item["domain"],"url":url})
            if importance(a,country)>placed["importance"]:
                placed["title"]=title
        else:
            events.append({
                "title":title,"url":url,"event_country":country,"category":category(title),
                "importance":importance(a,country),"domestic_score":domestic_score(a,country),
                "published_at":item["published_at"],
                "sources":[{"name":item["domain"],"url":url}],
                "why_important":"该事件在过去24小时内形成具有实际政策、经济、安全、产业或社会影响的新闻信号。",
                "impact":"可能影响相关国家的政策预期、市场情绪、产业链或地区局势，具体影响取决于后续官方措施。",
                "next_72h":"重点观察后续官方公告、议会/央行行动、市场反应以及其他权威媒体的独立确认。"
            })
    for e in events:
        e["source_names"]=" / ".join(x["name"] for x in e["sources"][:4])
        e["id"]=hashlib.sha1((country+"|"+norm(e["title"])).encode()).hexdigest()[:16]
    return events

def main():
    all_events=[]; errors=[]
    country_success=0
    country_failed=0
    country_total=sum(len(v) for v in CFG["tiers"].values())
    gap=float(CFG["collection"].get("request_gap_seconds",10))

    for tier,countries in CFG["tiers"].items():
        for country in countries:
            slug=SOURCE_COUNTRY[country]
            terms=["government","economy","finance","business","technology","energy","military","diplomacy",
                   "health","education","disaster","election","central bank","policy"]
            query=f"sourcecountry:{slug} ("+" OR ".join(terms)+")"

            try:
                raw=fetch(query,CFG["collection"].get("per_country_maxrecords",160))
                arts=raw.get("articles",[]) if isinstance(raw,dict) else []
                ev=eventize(arts,country)
                target=30 if tier=="Tier 1" else 20 if tier=="Tier 2" else 15 if tier=="Tier 3" else 10
                ev=sorted(ev,key=lambda x:(x["importance"],x["domestic_score"]),reverse=True)[:target]
                all_events.extend(ev)
                country_success += 1
                print(f"{tier}/{country}: {len(arts)} articles -> {len(ev)} events",flush=True)
            except Exception as ex:
                country_failed += 1
                errors.append(f"{tier}/{country}: {type(ex).__name__}: {ex}")
                print(f"ERROR {tier}/{country}: {ex}",flush=True)

            # Spread requests evenly; GDELT explicitly rate-limits its hosted APIs.
            time.sleep(gap)

    # Global supplement: one additional broad request only.
    try:
        raw=fetch('(war OR election OR "central bank" OR tariff OR "interest rate" OR AI OR earthquake)',250)
        sup=eventize(raw.get("articles",[]),"全球补充")
        for e in sup: e["event_country"]="全球补充"
        all_events.extend(sorted(sup,key=lambda x:x["importance"],reverse=True)[:10])
    except Exception as ex:
        errors.append(f"supplement: {type(ex).__name__}: {ex}")

    # Cross-country duplicate protection: same title similarity only when same country.
    final=[]
    for e in sorted(all_events,key=lambda x:x["importance"],reverse=True):
        dup=False
        for f in final:
            if e["event_country"]==f["event_country"] and similarity(e["title"],f["title"])>=0.55:
                for s in e["sources"]:
                    if s["url"] and all(x["url"]!=s["url"] for x in f["sources"]):
                        f["sources"].append(s)
                f["source_names"]=" / ".join(x["name"] for x in f["sources"][:4])
                dup=True; break
        if not dup: final.append(e)

    now=datetime.now(timezone.utc).astimezone()
    report={
      "report_date":now.strftime("%Y-%m-%d"),
      "updated_at":now.strftime("%Y-%m-%d %H:%M %Z"),
      "window":"过去24小时",
      "events":final,
      "global_top":[e["id"] for e in final[:10]],
      "quality":{
        "event_count":len(final),
        "errors":errors,
        "summary":f"已生成 {len(final)} 个独立事件；31个国家采集成功 {country_success} 个、失败 {country_failed} 个；数据来自 GDELT 过去24小时 ArticleList。"+
                  (f" 有 {len(errors)} 个采集错误。" if errors else " 本次采集全部成功。")
      }
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("WROTE",OUT,len(final),flush=True)

if __name__=="__main__": main()
