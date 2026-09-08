#!/usr/bin/env python3
# 雷达新闻 V18 - 中文优先、多源直连 RSS
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG=json.load(open(os.path.join(ROOT,'config/country_tiers.json'),encoding='utf-8'))
OUT=os.path.join(ROOT,'data'); HISTORY=os.path.join(OUT,'history')
os.makedirs(HISTORY,exist_ok=True)
DAILY=os.path.join(OUT,'daily.json')
UA='LeidaNews/18.0 (+https://github.com/franklee24/Rader-News)'
TIMEOUT=18; WORKERS=8; MIN_TOTAL_EVENTS=40; MIN_TIER1_EVENTS=20

# 中文源优先：中央媒体/主流财经媒体；英文源只做补充和交叉验证。
FEEDS=[
 ('中新网-即时','GLOBAL','https://www.chinanews.com.cn/rss/scroll-news.xml','cn'),
 ('中新网-要闻','GLOBAL','https://www.chinanews.com.cn/rss/importnews.xml','cn'),
 ('中新网-国际','GLOBAL','https://www.chinanews.com.cn/rss/world.xml','cn'),
 ('中新网-财经','GLOBAL','https://www.chinanews.com.cn/rss/finance.xml','cn'),
 ('中新网-军事','GLOBAL','https://www.chinanews.com.cn/rss/mil.xml','cn'),
 ('人民网-时政','GLOBAL','http://www.people.com.cn/rss/politics.xml','cn'),
 ('人民网-国际','GLOBAL','http://www.people.com.cn/rss/world.xml','cn'),
 ('人民网-财经','GLOBAL','http://www.people.com.cn/rss/finance.xml','cn'),
 ('人民网-军事','GLOBAL','http://www.people.com.cn/rss/military.xml','cn'),
 ('央视-国内','GLOBAL','http://www.cctv.com/program/rss/02/01/index.xml','cn'),
 ('央视-国际','GLOBAL','http://www.cctv.com/program/rss/02/02/index.xml','cn'),
 ('央视-财经','GLOBAL','http://www.cctv.com/program/rss/02/04/index.xml','cn'),
 ('央视-新闻联播','GLOBAL','http://www.cctv.com/program/rss/02/09/index.xml','cn'),
 ('新华-时政','GLOBAL','http://www.xinhuanet.com/politics/news_politics.xml','cn'),
 ('新华-国际','GLOBAL','http://www.xinhuanet.com/world/news_world.xml','cn'),
 ('新华-军事','GLOBAL','http://www.xinhuanet.com/mil/news_mil.xml','cn'),
 ('新华-金融','GLOBAL','http://www.xinhuanet.com/finance/news_finance.xml','cn'),
 ('新华-科技','GLOBAL','http://www.xinhuanet.com/tech/news_tech.xml','cn'),
 ('第一财经','CN','https://www.yicai.com/rss/','cn'),
 ('新浪财经','CN','https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=50&page=1&r=0.1&callback=','cn'),
 ('BBC中文','GLOBAL','https://feeds.bbci.co.uk/zhongwen/simp/rss.xml','cn'),
 ('联合早报','GLOBAL','https://www.zaobao.com/rss.xml','cn'),
 # English secondary
 ('Reuters World','GLOBAL','https://feeds.reuters.com/reuters/worldNews','en'),
 ('BBC World','GLOBAL','https://feeds.bbci.co.uk/news/world/rss.xml','en'),
 ('AP World','GLOBAL','https://feeds.apnews.com/apnews/worldnews','en'),
 ('NHK','JP','https://www3.nhk.or.jp/rss/news/cat0.xml','en'),
 ('NPR','US','https://feeds.npr.org/1001/rss.xml','en'),
 ('BBC UK','GB','https://feeds.bbci.co.uk/news/uk/rss.xml','en'),
 ('France24','FR','https://www.france24.com/en/rss','en'),
 ('DW','DE','https://rss.dw.com/xml/rss-en-all','en'),
 ('TASS','RU','https://tass.com/rss/v2.xml','en'),
]

ALIASES={
'US':['美国','美方','美总统','特朗普','华盛顿','白宫','美国政府','美联储','美国国会','美军','美国经济','United States','Trump','Washington','White House','Federal Reserve'],
'CN':['中国','中方','中国政府','国务院','北京','人民币','央行','中国人民银行','China','Beijing'],
'GB':['英国','英方','英首相','伦敦','英国政府','英国央行','United Kingdom','Britain','London','Starmer','Bank of England'],
'FR':['法国','法方','巴黎','法国政府','法国总统','France','Paris','Macron'],
'DE':['德国','德方','柏林','德国政府','德国央行','Germany','Berlin','Merz'],
'RU':['俄罗斯','俄方','莫斯科','克里姆林宫','俄军','俄罗斯政府','Russia','Moscow','Kremlin','Putin'],
'JP':['日本','日方','东京','日本政府','日本央行','Japan','Tokyo','Nikkei','BOJ'],
'IN':['印度','新德里','印度政府','India','New Delhi','Modi'],
'BR':['巴西','巴西政府','Brasilia','Brazil'],
'SA':['沙特','沙特阿拉伯','利雅得','Saudi Arabia','Riyadh'],
'KR':['韩国','韩方','首尔','韩国政府','South Korea','Seoul'],
'CA':['加拿大','加方','渥太华','Canada','Ottawa','Trudeau'],
'AU':['澳大利亚','澳方','堪培拉','Australia','Canberra'],
'UA':['乌克兰','乌方','基辅','Ukraine','Kyiv','Zelensky'],
'IT':['意大利','罗马','Italy','Rome'],
'ID':['印度尼西亚','印尼','雅加达','Indonesia','Jakarta'],
'TR':['土耳其','安卡拉','Turkey','Ankara'],
'AE':['阿联酋','阿布扎比','迪拜','UAE','Abu Dhabi','Dubai'],
'MX':['墨西哥','墨西哥城','Mexico','Mexico City'],
'IR':['伊朗','伊方','德黑兰','伊朗政府','Iran','Tehran'],
'CH':['瑞士','日内瓦','Swiss','Switzerland','Geneva'],
'SG':['新加坡','Singapore'], 'ZA':['南非','South Africa'], 'NL':['荷兰','Netherlands','Amsterdam'],
'IL':['以色列','以方','特拉维夫','Israel','Tel Aviv'], 'ES':['西班牙','马德里','Spain','Madrid'],
'EG':['埃及','开罗','Egypt','Cairo'], 'NG':['尼日利亚','Nigeria'], 'AR':['阿根廷','布宜诺斯艾利斯','Argentina'],
'PL':['波兰','华沙','Poland','Warsaw'], 'VN':['越南','河内','Vietnam','Hanoi']
}
CODE_TO_COUNTRY={c['code']:c for arr in CONFIG['tiers'].values() for c in arr}
CAT={
'政治':['政治','政府','总统','总理','选举','议会','政党','内阁','election','government','president','prime minister','parliament'],
'宏观经济':['经济','GDP','通胀','通货膨胀','利率','央行','宏观','economic','inflation','interest rate','central bank'],
'金融':['金融','股市','债券','汇率','银行','资本市场','market','stocks','bond','currency','finance','bank'],
'产业/商业':['企业','公司','产业','制造','贸易','商业','供应链','company','industry','trade','manufacturing','business'],
'科技':['科技','人工智能','AI','芯片','半导体','量子','technology','artificial intelligence','chip','semiconductor'],
'能源':['能源','石油','天然气','电力','核能','油价','oil','gas','energy','power','nuclear'],
'国防安全':['军事','国防','导弹','军演','武器','安全','袭击','战争','military','defense','missile','security','attack','war'],
'外交':['外交','峰会','会谈','访问','外长','条约','diplomacy','summit','foreign','minister','treaty'],
'社会':['社会','医疗','教育','抗议','就业','公共卫生','society','health','education','protest'],
'灾害':['地震','洪水','台风','火灾','飓风','灾害','earthquake','flood','storm','fire','disaster']}
HIGH=['战争','袭击','制裁','关税','选举','利率','核','导弹','停火','入侵','冲突','oil','war','attack','sanction','tariff','election','rate','nuclear','missile','ceasefire','invasion']

def clean(s): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s or ''))).strip()
def dateval(s):
 if not s:return None
 try:
  d=email.utils.parsedate_to_datetime(str(s)); return d.astimezone(dt.timezone.utc) if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
 except Exception:
  try:
   d=dt.datetime.fromisoformat(str(s).replace('Z','+00:00')); return d.astimezone(dt.timezone.utc) if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
  except Exception:return None

def fetch(url):
 try:
  req=Request(url,headers={'User-Agent':UA,'Accept':'application/rss+xml,application/xml,text/xml,*/*;q=0.8'})
  with urlopen(req,timeout=TIMEOUT) as r:return r.read(),None
 except Exception as e:return None,str(e)[:160]

def parse_feed(body,source,feed_country,lang):
 root=ET.fromstring(body); rows=[]
 for item in root.iter():
  if item.tag.split('}')[-1].lower() not in ('item','entry'):continue
  title=''; link=''; pub=''; desc=''
  for x in item:
   n=x.tag.split('}')[-1].lower(); txt=(x.text or '').strip()
   if n=='title':title=clean(txt)
   elif n=='link' and not link:link=(txt or x.attrib.get('href','')).strip()
   elif n in ('pubdate','published','updated','date') and not pub:pub=txt
   elif n in ('description','summary','content') and not desc:desc=txt
  if title and link:
   d=dateval(pub)
   rows.append({'title':title,'link':link,'published_at':d.isoformat() if d else None,'source':source,'source_url':link,'description':clean(desc),'feed_country':feed_country,'language':lang})
 return rows

def fetch_feed(feed):
 source,country,url,lang=feed; body,err=fetch(url)
 if not body:return feed,[],err
 try:return feed,parse_feed(body,source,country,lang),None
 except Exception as e:return feed,[],'XML '+str(e)[:120]

def norm(s):
 s=re.sub(r'https?://\S+',' ',(s or '').lower()); s=re.sub(r'\[[^\]]+\]|\([^)]*\)',' ',s); s=re.sub(r'[^0-9a-z\u4e00-\u9fff]+',' ',s); return ' '.join(s.split())
def similarity(a,b):
 aa=set(norm(a).split());bb=set(norm(b).split());return len(aa&bb)/len(aa|bb) if aa and bb else 0

def infer_country(item):
 if item.get('feed_country') in CODE_TO_COUNTRY:return item['feed_country']
 text=item.get('title','')+' '+item.get('description','')[:300]
 scores=[]
 for code,als in ALIASES.items():
  score=sum(1 for a in als if a.lower() in text.lower())
  if score:scores.append((score,code))
 if scores:return max(scores)[1]
 return 'GLOBAL'

def category(t):
 low=(t or '').lower(); scores={c:sum(1 for k in ks if k.lower() in low) for c,ks in CAT.items()}; return max(scores,key=scores.get) if max(scores.values()) else '政治'

def cluster(items):
 events=[]
 for a in sorted(items,key=lambda x:x.get('published_at') or '',reverse=True):
  m=next((e for e in events if similarity(a['title'],e['title'])>=0.56),None)
  if m:m['sources'].append(a)
  else:events.append({'id':hashlib.sha1(norm(a['title']).encode()).hexdigest()[:16],'title':a['title'],'published_at':a.get('published_at'),'code':a.get('code','GLOBAL'),'event_country':a.get('event_country','国际/全球'),'sources':[a]})
 out=[]
 for e in events:
  uniq={s.get('source'):s for s in e['sources']}; srcs=list(uniq.values())[:8]
  zh=[s for s in srcs if s.get('language')=='cn']; best=(zh or srcs)[0]
  e.update(source=best.get('source',''),url=best.get('link',''),source_url=best.get('source_url',''),sources=srcs,source_count=len(srcs),source_names=[s.get('source','') for s in srcs],category=category(e['title']))
  impact=sum(1 for k in HIGH if k.lower() in e['title'].lower())
  e['domestic_score']=min(100,30+impact*8) if e['code']!='GLOBAL' else 12
  e['importance']=min(100,48+min(20,6*max(0,e['source_count']-1))+min(24,impact*4)+round(e['domestic_score']*.10))
  e['why_important']='涉及'+e['category']+'，在过去24小时具有跟踪价值。'
  e['impact']='关注政策、市场、产业、安全及国际关系的后续影响。'
  e['next_72h']='关注官方声明、政策落地、市场反应及相关方后续行动。'
  out.append(e)
 return sorted(out,key=lambda x:(x['importance'],x.get('published_at') or ''),reverse=True)

def main():
 now=dt.datetime.now(dt.timezone.utc); cutoff=now-dt.timedelta(hours=25)
 raw={c['code']:[] for arr in CONFIG['tiers'].values() for c in arr}; global_rows=[]; failures=[]; ok=0
 print('雷达新闻 V18：中文优先多源 RSS')
 with ThreadPoolExecutor(max_workers=WORKERS) as ex:
  fs=[ex.submit(fetch_feed,f) for f in FEEDS]
  for fut in as_completed(fs):
   feed,rows,err=fut.result(); source,fc,_,lang=feed
   if err:failures.append({'source':source,'country':fc,'error':err});print('[FAIL]',source,err);continue
   ok+=1; fresh=[]
   for x in rows:
    p=dateval(x.get('published_at'))
    if p and p<cutoff:continue
    code=infer_country(x); x['code']=code
    c=CODE_TO_COUNTRY.get(code)
    x['event_country']=c['name'] if c else '国际/全球'; x['event_country_en']=c['en'] if c else 'Global'
    fresh.append(x)
   if fc=='GLOBAL':global_rows.extend(fresh)
   elif fc in raw:raw[fc].extend(fresh)
   else:global_rows.extend(fresh)
   print('[OK]',source,len(fresh))
 for x in global_rows:
  if x.get('code') in raw:raw[x['code']].append(x)
 all_events=[]; report={'generated_at':now.isoformat(),'generated_beijing':dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M'),'window_hours':24,'version':'V18.0','source_mode':'chinese-first-direct-rss','source_total':len(FEEDS),'source_ok':ok,'failures':failures,'tiers':{},'global_top':[],'supplement':[]}
 for tier,arr in CONFIG['tiers'].items():
  report['tiers'][tier]={}
  for c in arr:
   pool=raw.get(c['code'],[])
   # 中文优先：当一个国家有足够中文报道时，英文事件最多占该国展示量约20%。
   cn_items=[x for x in pool if x.get('language')=='cn']
   en_items=[x for x in pool if x.get('language')!='cn']
   if len(cn_items)>=5 and en_items:
    en_cap=max(2,int(c['max']*0.20))
    pool=cn_items+sorted(en_items,key=lambda x:x.get('published_at') or '',reverse=True)[:en_cap]
   ev=cluster(pool)[:c['max']]
   report['tiers'][tier][c['name']]={'country':c['name'],'country_en':c['en'],'code':c['code'],'target_min':c['min'],'target_max':c['max'],'count':len(ev),'events':ev}
   all_events.extend(ev)
 report['supplement']=cluster(global_rows)[:10]
 report['global_top']=cluster(all_events+report['supplement'])[:20]
 report['stats']={'countries':sum(len(v) for v in report['tiers'].values()),'events':sum(x['count'] for v in report['tiers'].values() for x in v.values()),'tier1_events':sum(x['count'] for x in report['tiers']['tier1'].values()),'supplement_events':len(report['supplement']),'failed_sources':len(failures),'successful_sources':ok,'chinese_sources':sum(1 for f in FEEDS if f[3]=='cn')}
 print('STATS',report['stats'])
 if report['stats']['events']<MIN_TOTAL_EVENTS or report['stats']['tier1_events']<MIN_TIER1_EVENTS:
  print('QUALITY GATE FAILED'); raise SystemExit(2)
 report['stale_fallback']=False
 with open(DAILY,'w',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
 date=report['generated_beijing'][:10]
 with open(os.path.join(HISTORY,date+'.json'),'w',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
 print('QUALITY GATE PASSED')

if __name__=='__main__':main()
