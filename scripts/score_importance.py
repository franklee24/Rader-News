#!/usr/bin/env python3
# 雷达新闻 V19 importance model
# 事件重要性：影响范围25 + 严重性20 + 战略/政策影响20 + 国家战略地位15 + 72小时影响10 + 多源验证5 + 时效性5
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DAILY=ROOT/'data'/'daily.json'
CONFIG=json.loads((ROOT/'config'/'country_tiers.json').read_text(encoding='utf-8'))
TIER_BY_COUNTRY={c['name']:i for i,tier in enumerate(['tier1','tier2','tier3','tier4'],1) for c in CONFIG['tiers'].get(tier,[])}

SEVERE={
    '战争':10,'war':10,'入侵':10,'invasion':10,'核武':10,'核打击':10,'nuclear strike':10,
    '导弹':8,'missile':8,'大规模袭击':9,'mass attack':9,'恐袭':9,'terrorist attack':9,
    '空袭':8,'airstrike':8,'袭击':7,'attack':7,'战斗':7,'battle':7,'冲突':6,'conflict':6,
    '停火':6,'ceasefire':6,'制裁':5,'sanction':5,'关税':5,'tariff':5,'封锁':7,'blockade':7,
    '紧急状态':6,'state of emergency':6,'死亡':3,'dead':3,'伤亡':4,'casualties':4,
}
STRATEGIC={
    '总统':7,'president':7,'总理':6,'prime minister':6,'政府':5,'government':5,'议会':4,'parliament':4,
    '选举':6,'election':6,'央行':7,'central bank':7,'利率':7,'interest rate':7,'降息':7,'加息':7,
    '关税':8,'tariff':8,'贸易':5,'trade':5,'制裁':8,'sanction':8,'外交':5,'diplomacy':5,
    '峰会':5,'summit':5,'条约':7,'treaty':7,'核':9,'nuclear':9,'军队':6,'military':6,
    '国防':7,'defense':7,'pentagon':7,'能源':5,'energy':5,'石油':6,'oil':6,'天然气':5,'gas':5,
    '芯片':5,'semiconductor':5,'人工智能':4,'artificial intelligence':4,
}

CATEGORY_BASE={'国防安全':18,'外交':17,'政治':16,'宏观经济':16,'金融':14,'能源':14,'科技':13,'产业/商业':11,'社会':9,'灾害':12}

def text(e):
    return ((e.get('title') or '')+' '+(e.get('description') or '')).lower()

def hits(t, table):
    return [k for k in table if k.lower() in t]

def tier_score(country):
    n=TIER_BY_COUNTRY.get(country,5)
    return {1:15,2:12,3:9,4:6}.get(n,4)

def score(e):
    t=text(e)
    category=e.get('category','政治')
    # 1) 影响范围 25：全球事件/核心国家/其他国家
    country=e.get('event_country','')
    scope=25 if e.get('code')=='GLOBAL' or country in ('国际/全球','全球') else 22 if TIER_BY_COUNTRY.get(country)==1 else 18 if TIER_BY_COUNTRY.get(country)==2 else 14
    # 2) 严重性 20：最高命中项封顶20，避免关键词堆叠刷分
    sev_hits=hits(t,SEVERE)
    severity=min(20, max([SEVERE[k] for k in sev_hits], default=0)+min(8,max(0,len(sev_hits)-1)*2))
    # 3) 战略/政策影响 20
    strategic_hits=hits(t,STRATEGIC)
    strategic=min(20, CATEGORY_BASE.get(category,10)+min(8, sum(STRATEGIC[k] for k in strategic_hits)//4))
    # 4) 国家战略地位 15
    national=tier_score(country)
    # 5) 未来72小时影响 10：政策、军事、金融、外交天然具有连续影响
    horizon=8 if category in ('国防安全','外交','政治','宏观经济','金融') else 6 if category in ('能源','科技','灾害') else 4
    if any(k.lower() in t for k in ('宣布','announced','effective','立即','immediate','deadline','正式','official')):
        horizon=min(10,horizon+2)
    # 6) 多源验证 5：只奖励独立来源，不让媒体数量主导评分
    source_count=e.get('source_count',len(e.get('sources',[])))
    verification=min(5,max(0,source_count-1)*2)
    # 7) 时效性 5：日报窗口内越新越高；无时间不给分
    freshness=5 if e.get('published_at') else 0
    total=max(0,min(100,scope+severity+strategic+national+horizon+verification+freshness))
    if total>=90: level='全球重大'
    elif total>=80: level='国家重大'
    elif total>=70: level='重要事件'
    elif total>=60: level='值得关注'
    else: level='一般动态'
    e['importance']=total
    e['importance_level']=level
    e['importance_model']='V19：影响范围25/严重性20/战略政策20/国家战略15/72小时影响10/多源验证5/时效5'
    return e

def main():
    d=json.loads(DAILY.read_text(encoding='utf-8'))
    for tier in d.get('tiers',{}).values():
        for country in tier.values():
            country['events']=[score(e) for e in country.get('events',[])]
            country['events'].sort(key=lambda e:(e.get('importance',0),e.get('published_at','')),reverse=True)
            country['count']=len(country['events'])
    # 兼容页面可能读取的 global_top / top_events 字段
    for key in ('global_top','top_events'):
        if isinstance(d.get(key),list):
            d[key]=[score(e) for e in d[key]]
            d[key].sort(key=lambda e:(e.get('importance',0),e.get('published_at','')),reverse=True)
    d['importance_model']={'version':'V19','dimensions':{'影响范围':25,'严重性':20,'战略政策影响':20,'国家战略地位':15,'未来72小时影响':10,'多源验证':5,'时效性':5},'levels':{'90-100':'全球重大','80-89':'国家重大','70-79':'重要事件','60-69':'值得关注','0-59':'一般动态'}}
    d['version']='V19.0'
    DAILY.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Importance scoring upgraded to V19.')

if __name__=='__main__': main()
