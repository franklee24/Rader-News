#!/usr/bin/env python3
import json, re, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DAILY = ROOT / "data/daily.json"
API = "https://api.gdeltproject.org/api/v2/doc/doc"

AUTH = {
    "reuters.com": 1.0, "apnews.com": .95, "bbc.com": .9, "bbc.co.uk": .9,
    "nytimes.com": .9, "ft.com": .95, "bloomberg.com": .95,
    "theguardian.com": .85, "cnn.com": .8, "npr.org": .8,
    "nhk.or.jp": .9, "yonhapnews.co.kr": .9, "xinhua.net": .9,
    "gov.cn": 1.0, "gov.uk": 1.0, "elysee.fr": 1.0,
    "bundesregierung.de": 1.0, "kremlin.ru": 1.0, "japan.go.jp": 1.0,
}

ALIASES = {
    "美国":["United States","USA","Washington","Trump","White House"],
    "中国":["China","Chinese","Beijing","Shanghai","PBOC"],
    "英国":["United Kingdom","UK","Britain","London","Starmer"],
    "法国":["France","French","Paris","Macron"],
    "德国":["Germany","German","Berlin","Merz"],
    "俄罗斯":["Russia","Russian","Moscow","Kremlin","Putin"],
    "日本":["Japan","Japanese","Tokyo","Nikkei","BOJ"],
    "印度":["India","Indian","New Delhi","Modi"],
    "巴西":["Brazil","Brazilian","Brasilia"],
    "沙特阿拉伯":["Saudi Arabia","Saudi","Riyadh"],
    "韩国":["South Korea","Korea","Seoul","Yonhap"],
    "加拿大":["Canada","Canadian","Ottawa"],
    "澳大利亚":["Australia","Australian","Canberra"],
    "乌克兰":["Ukraine","Ukrainian","Kyiv","Zelensky"],
    "意大利":["Italy","Italian","Rome"],
    "印度尼西亚":["Indonesia","Indonesian","Jakarta"],
    "土耳其":["Turkey","Turkish","Ankara","Istanbul"],
    "阿联酋":["United Arab Emirates","UAE","Dubai","Abu Dhabi"],
    "墨西哥":["Mexico","Mexican","Mexico City"],
    "伊朗":["Iran","Iranian","Tehran"],
    "瑞士":["Switzerland","Swiss","Geneva","Zurich"],
    "新加坡":["Singapore","Singaporean"],
    "南非":["South Africa","South African","Pretoria","Johannesburg"],
    "荷兰":["Netherlands","Dutch","Amsterdam","The Hague"],
    "以色列":["Israel","Israeli","Jerusalem","Tel Aviv"],
    "西班牙":["Spain","Spanish","Madrid"],
    "埃及":["Egypt","Egyptian","Cairo"],
    "尼日利亚":["Nigeria","Nigerian","Abuja","Lagos"],
    "阿根廷":["Argentina","Argentine","Buenos Aires"],
    "波兰":["Poland","Polish","Warsaw"],
    "越南":["Vietnam","Vietnamese","Hanoi","Ho Chi Minh"],
}

TOPICS = [
    '(government OR president OR election OR parliament OR minister OR policy)',
    '(economy OR economic OR inflation OR GDP OR trade OR tariff OR market OR company OR industry)',
    '(military OR defense OR missile OR war OR diplomacy OR summit OR sanction OR energy OR technology OR AI)',
]
HIGH = ['war','sanction','tariff','election','rate','missile','nuclear','crisis','treaty','strike','earthquake','战争','制裁','关税','利率','选举','导弹','核','危机','条约','地震']

def norm(s):
    s = re.sub(r'https?://\S+', ' ', (s or '').lower())
    s = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', ' ', s)
    return ' '.join(s.split())

def sim(a,b):
    aa=set(norm(a).split()); bb=set(norm(b).split())
    return len(aa&bb)/len(aa|bb) if aa and bb else 0

def domain_score(domain):
    d=(domain or '').lower()
    for k,v in AUTH.items():
        if d.endswith(k) or k in d: return v
    return .35

def fetch(query,start,end,maxrecords=160):
    params={
        'query':query, 'mode':'ArtList', 'format':'json',
        'maxrecords':str(maxrecords), 'sort':'DateDesc',
        'startdatetime':start.strftime('%Y%m%d%H%M%S'),
        'enddatetime':end.strftime('%Y%m%d%H%M%S')
    }
    req=Request(API+'?'+urlencode(params),headers={'User-Agent':'Leida-News-Coverage/1.0'})
    with urlopen(req,timeout=35) as r:
        return json.loads(r.read().decode('utf-8','replace')).get('articles',[])

def main():
    data=json.loads(DAILY.read_text(encoding='utf-8'))
    bj=timezone(timedelta(hours=8)); now=datetime.now(timezone.utc).astimezone(bj)
    anchor=now.replace(hour=8,minute=0,second=0,microsecond=0)
    if now < anchor: anchor -= timedelta(days=1)
    start=anchor-timedelta(days=1); end=anchor

    tier_targets={'tier1':10,'tier2':8,'tier3':8,'tier4':8}
    added=0

    for tier,countries in CFG['countries'].items():
        bucket=data.get('tiers',{}).get(tier,{})
        for c in countries:
            name=c['name']; current=bucket.get(name,{})
            events=current.get('events',[])
            target=min(c.get('max',10),tier_targets.get(tier,8))
            if len(events) >= target:
                continue

            aliases=ALIASES.get(name,[c.get('en',name),name])
            alias_q=' OR '.join('"'+x+'"' for x in aliases)
            candidates={}
            queries=[f'({alias_q})'] + [f'({alias_q}) AND {t}' for t in TOPICS]
            for q in queries:
                try:
                    for a in fetch(q,start,end):
                        url=a.get('url') or a.get('url_mobile') or ''
                        title=(a.get('title') or '').strip()
                        if not url or len(title)<12: continue
                        candidates[url]=a
                except Exception as ex:
                    print('coverage query error',name,ex)

            ranked=[]
            for a in candidates.values():
                title=a.get('title','')
                domain=a.get('domain','unknown')
                high=sum(x.lower() in title.lower() for x in HIGH)
                score=35+domain_score(domain)*25+high*7
                ranked.append((score,a))
            ranked.sort(key=lambda x:(x[0],x[1].get('seendate','')),reverse=True)

            for score,a in ranked:
                if len(events)>=target: break
                title=a.get('title','').strip()
                if any(sim(title,e.get('title',''))>=0.55 for e in events):
                    continue
                domain=a.get('domain') or 'unknown'
                url=a.get('url') or a.get('url_mobile') or ''
                lang=(a.get('language') or '').lower()
                published=a.get('seendate') or ''
                high=sum(x.lower() in title.lower() for x in HIGH)
                importance=round(min(100,35+domain_score(domain)*25+high*7),1)
                eid=hashlib.sha1((c['code']+'|'+norm(title)).encode()).hexdigest()[:16]
                event={
                    'id':eid,'title':title,'published_at':published,
                    'code':c['code'],'event_country':name,
                    'sources':[{'title':title,'link':url,'published_at':published,'source':domain,'source_url':url,'language':lang}],
                    'source':domain,'url':url,'source_url':url,'source_count':1,'source_names':[domain],
                    'category':'政治','domestic_score':35,'importance':importance,
                    'why_important':'该事件在过去24小时内形成具有实际政策、经济、安全、产业或社会影响的新闻信号。',
                    'impact':'关注相关政策、市场、产业链、安全局势及国际关系的后续影响。',
                    'next_72h':'关注官方公告、市场反应及其他权威媒体的独立确认。',
                    'importance_level':'值得关注' if importance>=60 else '一般动态',
                    'importance_model':'V20：事件级动态评分；覆盖扩展补充'
                }
                events.append(event); added+=1
            current['events']=events
            current['count']=len(events)
            bucket[name]=current
        data.setdefault('tiers',{}).setdefault(tier,bucket)

    if 'stats' in data:
        all_events=sum(len(c.get('events',[])) for t in data.get('tiers',{}).values() for c in t.values())
        data['stats']['events']=all_events
        data['stats']['tier1_events']=sum(len(c.get('events',[])) for c in data.get('tiers',{}).get('tier1',{}).values())

    data['coverage_expand']={'target_tier1':10,'target_other_tiers':8,'added':added,'window_start':start.isoformat(),'window_end':end.isoformat()}
    DAILY.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print('coverage expansion added',added,'events')

if __name__=='__main__': main()
