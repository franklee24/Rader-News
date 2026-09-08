#!/usr/bin/env python3
import json, urllib.parse, urllib.request, re, hashlib, time
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
OUT=ROOT/"data/daily.json"
COUNTRY_EN={"美国":"United States","中国":"China","英国":"United Kingdom","法国":"France","德国":"Germany","俄罗斯":"Russia","日本":"Japan","印度":"India","巴西":"Brazil","沙特阿拉伯":"Saudi Arabia","韩国":"South Korea","加拿大":"Canada","澳大利亚":"Australia","乌克兰":"Ukraine","意大利":"Italy","印度尼西亚":"Indonesia","土耳其":"Turkey","阿联酋":"United Arab Emirates","墨西哥":"Mexico","伊朗":"Iran","瑞士":"Switzerland","新加坡":"Singapore","南非":"South Africa","荷兰":"Netherlands","以色列":"Israel","西班牙":"Spain","埃及":"Egypt","尼日利亚":"Nigeria","阿根廷":"Argentina","波兰":"Poland","越南":"Vietnam"}
TERMS={"政治":"government OR president OR parliament OR election OR minister OR policy","宏观经济":"economy OR inflation OR GDP OR interest rate OR central bank OR monetary","金融":"markets OR stocks OR bonds OR currency OR bank OR investment","产业/商业":"company OR business OR industry OR trade OR merger OR earnings","科技":"technology OR AI OR semiconductor OR chip OR cybersecurity OR space","能源":"energy OR oil OR gas OR nuclear OR electricity","国防安全":"military OR defense OR security OR missile OR NATO OR armed forces","外交":"diplomacy OR summit OR talks OR sanctions OR treaty OR foreign minister","社会":"society OR protest OR labor OR health OR education OR migration","灾害":"earthquake OR flood OR wildfire OR storm OR disaster OR accident"}
STOP=set("the a an and or of to in on for with from by as at is are was were be been this that it its into after before over under about new says said".split())
def fetch(q):
    p={"query":f"({q})","mode":"artlist","maxrecords":"250","timespan":"24h","sort":"datedesc","format":"json"}
    u="https://api.gdeltproject.org/api/v2/doc/doc?"+urllib.parse.urlencode(p)
    r=urllib.request.Request(u,headers={"User-Agent":"LeidaNews/1.0"})
    with urllib.request.urlopen(r,timeout=35) as x:return json.load(x).get("articles",[])
def toks(s):return set(x for x in re.findall(r"[A-Za-z]{3,}",s.lower()) if x not in STOP)
def sim(a,b):
    A=toks(a);B=toks(b);return len(A&B)/max(1,len(A|B))
def key(s):
    s=re.sub(r"[^a-z0-9\u4e00-\u9fff ]"," ",s.lower())
    return hashlib.sha1(" ".join(sorted(toks(s)))[:400].encode()).hexdigest()[:16]
def main():
    rows=[]
    for tier,countries in CFG["tiers"].items():
        for c in countries:
            for cat,term in TERMS.items():
                try: arts=fetch(f'"{COUNTRY_EN[c]}" ({term})')
                except Exception as e:
                    print("WARN",c,cat,e); continue
                for a in arts:
                    title=a.get("title","").strip(); url=a.get("url","")
                    if title and url: rows.append({"title":title,"url":url,"source":a.get("domain",""),"published_at":a.get("seendate",""),"event_country":c,"category":cat})
                time.sleep(.1)
    seen=set(); articles=[]
    for a in rows:
        if a["url"] in seen: continue
        seen.add(a["url"]); articles.append(a)
    events=[]
    for a in articles:
        m=None
        for e in events[-600:]:
            if e["event_country"]==a["event_country"] and e["category"]==a["category"] and (sim(e["title"],a["title"])>=.48 or key(e["title"])==key(a["title"])):
                m=e;break
        if m:
            m["sources"].append({"source":a["source"],"url":a["url"],"published_at":a["published_at"]})
            m["source_count"]=len({s["url"] for s in m["sources"]})
        else:
            events.append({"id":key(a["title"]+a["url"]),"title":a["title"],"event_country":a["event_country"],"category":a["category"],"sources":[{"source":a["source"],"url":a["url"],"published_at":a["published_at"]}],"source_count":1})
    hi=["war","attack","sanction","election","rate","inflation","tariff","nuclear","missile","earthquake","resign","president","summit","ai","chip","oil"]
    for e in events:
        base=20 if e["event_country"] in CFG["tiers"]["tier1"] else 14 if e["event_country"] in CFG["tiers"]["tier2"] else 10
        e["importance"]=round(min(100,base+20*min(1,e["source_count"]/3)+25*min(1,e["source_count"]/4)+15*min(1,sum(w in e["title"].lower() for w in hi)/2)),1)
    limits={"tier1":30,"tier2":20,"tier3":15,"tier4":10}; selected=[]
    for tier,countries in CFG["tiers"].items():
        for c in countries:
            ce=sorted([e for e in events if e["event_country"]==c],key=lambda x:(x["importance"],x["source_count"]),reverse=True)
            selected += ce[:limits[tier]]
    selected.sort(key=lambda x:x["importance"],reverse=True)
    out={"product":"雷达新闻","generated_at":datetime.now(timezone.utc).isoformat(),"timezone":"Asia/Shanghai","window":"past 24 hours","events":selected,"global_top":selected[:20],"counts":{"events":len(selected),"countries":31},"note":"不足目标数量时宁缺毋滥。"}
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("events",len(selected))
if __name__=="__main__":main()
