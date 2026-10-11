#!/usr/bin/env python3
# 雷达新闻 V20 importance model
# 目标：让同一国家的普通新闻不再全部同分；分数反映事件本身，而不是国家标签。
import json,re,datetime as dt
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; DAILY=ROOT/'data'/'daily.json'
CONFIG=json.loads((ROOT/'config'/'country_tiers.json').read_text(encoding='utf-8'))
TIER_BY_COUNTRY={c['name']:i for i,t in enumerate(['tier1','tier2','tier3','tier4'],1) for c in CONFIG['tiers'].get(t,[])}
SEVERE={'战争':20,'war':20,'入侵':19,'invasion':19,'核打击':20,'nuclear strike':20,'核武':18,'nuclear':16,'大规模袭击':17,'mass attack':17,'恐袭':16,'terrorist attack':16,'导弹':15,'missile':15,'空袭':14,'airstrike':14,'袭击':12,'attack':12,'战斗':11,'battle':11,'冲突':10,'conflict':10,'封锁':12,'blockade':12,'停火':9,'ceasefire':9,'紧急状态':9,'state of emergency':9,'死亡':5,'dead':5,'伤亡':7,'casualties':7,'鼠疫':16,'plague':16,'疫情暴发':15,'outbreak':15,'epidemic':15,'pandemic':17,'传染病':12,'infectious disease':12,'病原体':10,'pathogen':10,'公共卫生紧急状态':15,'public health emergency':15,'撤离':9,'evacuation':9,'大规模停电':10,'blackout':10}
STRATEGIC={'总统':10,'president':10,'总理':9,'prime minister':9,'政府':7,'government':7,'议会':6,'parliament':6,'选举':9,'election':9,'央行':10,'central bank':10,'利率':10,'interest rate':10,'降息':10,'加息':10,'关税':12,'tariff':12,'贸易':8,'trade':8,'制裁':12,'sanction':12,'外交':8,'diplomacy':8,'峰会':8,'summit':8,'条约':11,'treaty':11,'核':13,'nuclear':13,'军队':9,'military':9,'国防':10,'defense':10,'pentagon':10,'能源':7,'energy':7,'石油':9,'oil':9,'天然气':8,'gas':8,'芯片':8,'semiconductor':8,'人工智能':6,'artificial intelligence':6,'公共卫生':10,'public health':10,'疫情':12,'outbreak':12,'鼠疫':12,'plague':12,'疫苗':6,'vaccine':6,'气候':6,'climate':6}
CATEGORY={'国防安全':9,'外交':8,'政治':7,'宏观经济':7,'金融':6,'能源':6,'科技':5,'AI/LLM':8,'产业/商业':4,'灾害':7,'公共卫生/疫情':9,'环境/气候':6,'法律/犯罪':5,'其他/综合':2,'社会':3}
ACTION={'宣布':4,'正式':4,'签署':5,'通过':5,'批准':5,'生效':5,'取消':4,'暂停':4,'启动':3,'升级':4,'降息':5,'加息':5,'禁运':6,'制裁':6,'announced':4,'official':4,'signed':5,'approved':5,'effective':5,'launch':3}
def text(e): return ((e.get('title') or '')+' '+(e.get('description') or '')).lower()
def keyword_match(text, keyword):
    key=keyword.lower()
    if re.search(r'[a-z]',key):
        if ' ' in key:
            parts=key.split()
            phrase=re.escape(' '.join(parts[:-1])+ ' ')+re.escape(parts[-1])+r'(?:es|s|ed|ing)?'
            return bool(re.search(r'(?<![a-z0-9])'+phrase+r'(?![a-z0-9])',text))
        return bool(re.search(r'(?<![a-z0-9])'+re.escape(key)+r'(?:es|s|ed|ing)?(?![a-z0-9])',text))
    return key in text
def hits(t,d): return [k for k in d if keyword_match(t,k)]
def parse_time(s):
    try:return dt.datetime.fromisoformat(s.replace('Z','+00:00'))
    except:return None
def freshness(e):
    p=parse_time(e.get('published_at') or ''); now=dt.datetime.now(dt.timezone.utc)
    if not p:return 0
    h=max(0,(now-p).total_seconds()/3600)
    return 5 if h<=4 else 4 if h<=8 else 3 if h<=14 else 2 if h<=20 else 1
def score(e):
    t=text(e); country=e.get('event_country',''); tier=TIER_BY_COUNTRY.get(country,0); cat=e.get('category','')
    scope={'global':20,0:8,1:17,2:14,3:11,4:8}.get(tier,8)
    sev=max([SEVERE[k] for k in hits(t,SEVERE)] or [0])
    strategic=min(20,CATEGORY.get(cat,3)+min(11,sum(STRATEGIC[k] for k in hits(t,STRATEGIC))//2))
    national={1:12,2:9,3:7,4:5}.get(tier,4)
    horizon={'国防安全':8,'外交':7,'政治':6,'宏观经济':6,'金融':6,'能源':6,'科技':5,'AI/LLM':8,'灾害':6,'公共卫生/疫情':9,'环境/气候':5,'法律/犯罪':4,'其他/综合':2,'产业/商业':4,'社会':3}.get(cat,4)
    ah=hits(t,ACTION)
    if ah:horizon=min(10,horizon+max(ACTION[k] for k in ah)//2)
    source_count=e.get('source_count',len(e.get('sources',[]))); verify=0 if source_count<=1 else 3 if source_count==2 else 5
    authority=e.get('source_authority',55); authority_bonus=min(8,max(0,round((authority-55)/8)))
    total=max(0,min(100,scope+sev+strategic+national+horizon+verify+authority_bonus+freshness(e)))
    level='全球重大' if total>=90 else '国家重大' if total>=80 else '重要事件' if total>=70 else '值得关注' if total>=60 else '一般动态'
    e['importance']=int(total); e['importance_level']=level; e['importance_model']='V21：事件级动态评分；媒体权威度用于交叉验证，不按语言偏置'
    return e
def main():
    d=json.loads(DAILY.read_text(encoding='utf-8'))
    for tier in d.get('tiers',{}).values():
        for c in tier.values():
            c['events']=[score(e) for e in c.get('events',[])]; c['events'].sort(key=lambda e:(e.get('importance',0),e.get('published_at') or ''),reverse=True); c['count']=len(c['events'])
    d['ai_news']=[score(e) for e in d.get('ai_news',[])]; d['ai_news'].sort(key=lambda e:(e.get('importance',0),e.get('published_at') or ''),reverse=True); d['ai_news_count']=len(d['ai_news']); d['ai_news_status']='ready' if len(d['ai_news'])==20 else 'partial'
    d['importance_model']={'version':'V22','principle':'事件本身优先；媒体权威度参与验证，国家权重只作背景修正','levels':{'90-100':'全球重大','80-89':'国家重大','70-79':'重要事件','60-69':'值得关注','0-59':'一般动态'}}; d['version']='V22.0'
    DAILY.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
# V20 hotfix: tolerate undated events during scoring; final workflow still removes them before publication.
