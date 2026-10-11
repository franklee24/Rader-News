#!/usr/bin/env python3
# 雷达新闻 V21 - 多源事件聚合；不预设中文媒体优先
# 质量策略：领域覆盖 + 事件影响力排序，压低纯猎奇/人物故事
# 来源校验：Japan Times / NYT Japan / WHO News 均已通过 RSS 可用性测试
# 分类规则兼容英文复数词组，如 data breaches / fighter jets / tax cuts
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

# 多源直连 RSS：中文媒体与国际媒体一视同仁，由事件覆盖度、媒体权威度和时效共同决定主来源。
FEEDS=[
 ('中新网-即时','CN','https://www.chinanews.com.cn/rss/scroll-news.xml','cn'),
 ('人民网-时政','CN','http://www.people.com.cn/rss/politics.xml','cn'),
 ('新华-时政','CN','http://www.xinhuanet.com/politics/news_politics.xml','cn'),
 ('新华-国际','CN','http://www.xinhuanet.com/world/news_world.xml','cn'),
 ('BBC中文','GLOBAL','https://feeds.bbci.co.uk/zhongwen/simp/rss.xml','cn'),
 ('纽约时报','GLOBAL','https://rss.nytimes.com/services/xml/rss/nyt/World.xml','en'),
 ('纽约时报-日本','JP','https://www.nytimes.com/svc/collections/v1/publish/http://www.nytimes.com/topic/destination/japan/rss.xml','en'),
 ('彭博社','GLOBAL','https://feeds.bloomberg.com/markets/news.rss','en'),
 ('华尔街日报','GLOBAL','https://feeds.a.dj.com/rss/RSSWorldNews.xml','en'),
 ('联合早报','GLOBAL','https://plink.anyfeeder.com/zaobao/realtime/world','cn'),
 ('卫报','GLOBAL','https://www.theguardian.com/world/rss','en'),
 ('BBC World','GLOBAL','https://feeds.bbci.co.uk/news/world/rss.xml','en'),
 ('NHK World','JP','https://www3.nhk.or.jp/rss/news/cat0.xml','en'),
 ('Japan Times','JP','https://www.japantimes.co.jp/feed/','en'),
 ('WHO News','GLOBAL','https://www.who.int/rss-feeds/news-english.xml','en'),
 ('金融时报','GLOBAL','https://www.ft.com/rss/home','en'),
 ('经济学人','GLOBAL','https://www.economist.com/the-world-this-week/rss.xml','en'),
 ('NPR','US','https://feeds.npr.org/1001/rss.xml','en'),
 ('BBC UK','GB','https://feeds.bbci.co.uk/news/uk/rss.xml','en'),
 ('France24','FR','https://www.france24.com/en/rss','en'),
 ('DW','DE','https://rss.dw.com/xml/rss-en-all','en'),
 ('TASS','RU','https://tass.com/rss/v2.xml','en'),
 ('华盛顿邮报','GLOBAL','https://feeds.washingtonpost.com/rss/world','en'),
 ('半岛电视台','GLOBAL','https://www.aljazeera.com/xml/rss/all.xml','en'),
 # Reuters/AP are collected via Google News site-specific RSS because legacy publisher RSS endpoints are not dependable.
 ('Reuters','GLOBAL','https://news.google.com/rss/search?q=site%3Areuters.com&hl=en-US&gl=US&ceid=US:en','en'),
 ('Associated Press','GLOBAL','https://news.google.com/rss/search?q=site%3Aapnews.com&hl=en-US&gl=US&ceid=US:en','en'),
 ('Yonhap','KR','https://en.yna.co.kr/RSS/news.xml','en'),
 ('The Hindu National','IN','https://www.thehindu.com/news/national/feeder/default.rss','en'),
 ('The Hindu International','GLOBAL','https://www.thehindu.com/news/international/feeder/default.rss','en'),
 ('CBC World','CA','https://www.cbc.ca/webfeed/rss/rss-world','en'),
 ('ABC Australia','AU','https://www.abc.net.au/news/feed/51120/rss.xml','en'),
 ('Le Monde English','FR','https://www.lemonde.fr/en/rss/une.xml','en'),
 ('Anadolu World','GLOBAL','https://www.aa.com.tr/en/rss/default?cat=world','en'),
 ('South China Morning Post','GLOBAL','https://www.scmp.com/rss/91/feed','en'),
]

# 独立 AI/LLM 新闻池：官方一手发布 + 权威科技媒体交叉报道
AI_FEEDS=[
 ('OpenAI News','GLOBAL','https://openai.com/news/rss.xml','en'),
 ('Google AI Blog','GLOBAL','https://blog.google/technology/ai/rss/','en'),
 ('Google DeepMind','GLOBAL','https://deepmind.google/blog/rss.xml','en'),
 ('Anthropic News Watch','GLOBAL','https://news.google.com/rss/search?q=site%3Aanthropic.com%2Fnews&hl=en-US&gl=US&ceid=US:en','en'),
 ('NVIDIA AI Blog','GLOBAL','https://blogs.nvidia.com/feed/','en'),
 ('Microsoft AI Blog','GLOBAL','https://www.microsoft.com/en-us/microsoft-cloud/blog/feed//','en'),
 ('Hugging Face Blog','GLOBAL','https://huggingface.co/blog/feed.xml','en'),
 ('TechCrunch AI','GLOBAL','https://techcrunch.com/category/artificial-intelligence/feed/','en'),
 ('Apple ML Research','GLOBAL','https://machinelearning.apple.com/rss.xml','en'),
 ('MIT Technology Review AI','GLOBAL','https://www.technologyreview.com/topic/artificial-intelligence/feed/','en'),
 ('The Verge AI','GLOBAL','https://www.theverge.com/rss/ai-artificial-intelligence/index.xml','en'),
 ('AWS ML Blog','GLOBAL','https://aws.amazon.com/blogs/machine-learning/feed/','en'),
 ('Meta AI Research','GLOBAL','https://ai.meta.com/blog/rss/','en'),
 ('Google Research','GLOBAL','https://research.google/blog/rss/','en'),
 ('arXiv cs.AI','GLOBAL','https://rss.arxiv.org/rss/cs.AI','en'),
]

ALIASES={
'US':['美国','美方','美总统','特朗普','华盛顿','白宫','美国政府','美联储','美国国会','美军','美国经济','United States','Trump','Washington','White House','Federal Reserve'],
'CN':['中国','中方','中国政府','国务院','北京','人民币','央行','中国人民银行','China','Beijing'],
'GB':['英国','英方','英首相','伦敦','英国政府','英国央行','United Kingdom','Britain','London','Starmer','Bank of England'],
'FR':['法国','法方','巴黎','法国政府','法国总统','France','Paris','Macron'],
'DE':['德国','德方','柏林','德国政府','德国央行','Germany','Berlin','Merz'],
'RU':['俄罗斯','俄方','莫斯科','克里姆林宫','俄军','俄罗斯政府','Russia','Moscow','Kremlin','Putin'],
'JP':['日本','日方','东京','日本政府','日本央行','Japan','Japanese','Tokyo','Nikkei','BOJ','Bank of Japan','Takaichi','Koizumi','Okinawa','Osaka','Kyoto','Yen','Japanese firms','LDP','food consumption tax'],
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
'政治':['政治','政府','总统','总理','选举','议会','政党','内阁','election','president','prime minister','parliament','legislation','bill','cabinet','minister','policy'],
'宏观经济':['经济','GDP','通胀','通货膨胀','利率','央行','宏观','财政','预算','税收','减税','国债','经济增长','消费税','economic','inflation','interest rate','central bank','fiscal','budget','tax cut','tax reduction','consumption tax','public debt','economic growth','wages'],
'金融':['金融','股市','债券','汇率','银行','资本市场','market','stocks','bond','currency','finance','bank'],
'产业/商业':['企业','公司','产业','制造','贸易','商业','供应链','company','industry','trade','manufacturing','business'],
'AI/LLM':['人工智能','生成式 AI','大语言模型','大型语言模型','AI 模型','AI agent','AI agents','LLM','GPT-','OpenAI','Anthropic','Gemini','Claude','DeepMind','machine learning','generative AI','large language model','AI model','AI assistant','artificial intelligence'],
 '科技':['科技','人工智能','AI','芯片','半导体','量子','网络安全','数据泄露','网络攻击','technology','artificial intelligence','chip','semiconductor','cybersecurity','data breach','data leak','cyberattack'],
'能源':['能源','石油','天然气','电力','核能','油价','oil','gas','energy','power','nuclear'],
'国防安全':['军事','国防','导弹','军演','武器','安全','袭击','战争','战斗机','国防部','军费','军事开支','military','defense','missile','security','attack','war','fighter jet','defense ministry','military spending','armed forces'],
'外交':['外交','峰会','会谈','访问','外长','条约','双边','合作','国际刑事法院','diplomacy','summit','foreign minister','treaty','bilateral','cooperation','ICC','alliance'],
'公共卫生/疫情':['公共卫生','疫情','传染病','鼠疫','疫情暴发','疫情爆发','病毒','病原体','疫苗','感染','卫生组织','疾病暴发','plague','outbreak','epidemic','pandemic','virus','pathogen','vaccine','infection','infectious disease','disease outbreak','public health','who warns'],
'社会':['社会','医疗','教育','抗议','就业','society','healthcare','education','protest'],
'环境/气候':['气候','污染','排放','环保','森林砍伐','climate','pollution','emissions','environment','wildfire'],
'法律/犯罪':['法院','判决','起诉','调查','腐败','犯罪','凶杀','court','verdict','prosecutor','charged','corruption','crime','murder'],
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

SOURCE_AUTHORITY={
 '纽约时报':96,'纽约时报-日本':96,'华尔街日报':96,'彭博社':96,'金融时报':96,'WHO News':98,'Japan Times':91,'Kyodo News':89,'BBC World':94,'卫报':92,'华盛顿邮报':94,'OpenAI News':95,'Google AI Blog':95,'Google DeepMind':96,'Anthropic News Watch':92,'NVIDIA AI Blog':94,'Microsoft AI Blog':93,'Hugging Face Blog':88,'TechCrunch AI':88,'Apple ML Research':93,'AWS ML Blog':92,'Meta AI Research':94,'Google Research':94,'arXiv cs.AI':90,'MIT Technology Review AI':93,'The Verge AI':88,
 'Reuters':98,'Associated Press':97,'Yonhap':88,'The Hindu National':87,'The Hindu International':87,'CBC World':88,'ABC Australia':88,'Le Monde English':90,'Anadolu World':85,'South China Morning Post':86,
 '半岛电视台':90,'NPR':90,'NHK World':90,'NHK':90,'经济学人':92,'DW':89,'France24':88,'BBC UK':94,
 'TASS':82,'联合早报':78,'BBC中文':82,'中新网-即时':62,'人民网-时政':62,'新华-时政':62,'新华-国际':62
}
def source_group(name):
 if name.startswith('中新网'): return '中新网'
 if name.startswith('人民网'): return '人民网'
 if name.startswith('新华'): return '新华社'
 if name.startswith('纽约时报'): return '纽约时报'
 if name in {'NHK','NHK World'}: return 'NHK'
 if name in {'BBC World','BBC UK','BBC中文'}: return 'BBC'
 return name
def source_rank(s):
 return SOURCE_AUTHORITY.get(s.get('source',''),55)

def norm(s):
 s=re.sub(r'https?://\S+',' ',(s or '').lower()); s=re.sub(r'\[[^\]]+\]|\([^)]*\)',' ',s); s=re.sub(r'[^0-9a-z\u4e00-\u9fff]+',' ',s); return ' '.join(s.split())
def similarity(a,b):
 aa=set(norm(a).split());bb=set(norm(b).split());return len(aa&bb)/len(aa|bb) if aa and bb else 0

def infer_country(item):
 text=item.get('title','')+' '+item.get('description','')[:300]
 scores=[]
 for code,als in ALIASES.items():
  score=sum(1 for a in als if a.lower() in text.lower())
  if score:scores.append((score,code))
 if scores:return max(scores)[1]
 # Feed-country is a fallback only; it must not override an explicitly mentioned event country.
 if item.get('feed_country') in CODE_TO_COUNTRY:return item['feed_country']
 return 'GLOBAL'

def keyword_match(text, keyword):
 low=(text or '').lower(); key=keyword.lower()
 # English abbreviations/words must match token boundaries (e.g. AI must not match "raises").
 if re.fullmatch(r'[a-z0-9][a-z0-9 .+/-]*',key):
  if ' ' in key:
   parts=key.split()
   phrase=re.escape(' '.join(parts[:-1]))+r'\s+'+re.escape(parts[-1])+r'(?:es|s|ed|ing)?'
   return bool(re.search(r'(?<![a-z0-9])'+phrase+r'(?![a-z0-9])',low))
  if len(key.strip())<=3 or any(ch in key for ch in '+/-'):
   return bool(re.search(r'(?<![a-z0-9])'+re.escape(key)+r'(?![a-z0-9])',low))
  return key in low
 return key in low

def category(t):
 text=t or ''
 scores={c:sum(1 for k in ks if keyword_match(text,k)) for c,ks in CAT.items()}
 best=max(scores,key=scores.get)
 return best if scores[best] else '其他/综合'

def cluster(items):
 events=[]
 for a in sorted(items,key=lambda x:x.get('published_at') or '',reverse=True):
  m=next((e for e in events if similarity(a['title'],e['title'])>=0.56),None)
  if m:m['sources'].append(a)
  else:events.append({'id':hashlib.sha1(norm(a['title']).encode()).hexdigest()[:16],'title':a['title'],'published_at':a.get('published_at'),'code':a.get('code','GLOBAL'),'event_country':a.get('event_country','国际/全球'),'sources':[a]})
 out=[]
 for e in events:
  # 同一媒体的不同栏目不重复计数，避免中新网等单一机构因多个 RSS 被人为放大。
  grouped={}
  for s in e['sources']:
   g=source_group(s.get('source',''))
   old=grouped.get(g)
   if old is None or source_rank(s)>source_rank(old) or (source_rank(s)==source_rank(old) and (s.get('published_at') or '')>(old.get('published_at') or '')):
    grouped[g]=s
  srcs=sorted(grouped.values(),key=lambda s:(source_rank(s),s.get('published_at') or ''),reverse=True)[:8]
  best=srcs[0] if srcs else e['sources'][0]
  summary=clean(best.get('description',''))
  e.update(
   source=best.get('source',''),url=best.get('link',''),source_url=best.get('source_url',''),
   sources=srcs,source_count=len(srcs),source_names=[s.get('source','') for s in srcs],
   source_authority=source_rank(best),summary=summary[:500],description=summary[:500],
   category=category(e['title']+' '+summary)
  )
  impact=sum(1 for k in HIGH if k.lower() in e['title'].lower())
  authority_bonus=min(12,round(e['source_authority']/12))
  cross_bonus=min(20,5*max(0,e['source_count']-1))
  e['domestic_score']=min(100,30+impact*8) if e['code']!='GLOBAL' else 12
  category_bonus={'国防安全':16,'公共卫生/疫情':16,'政治':14,'宏观经济':14,'金融':13,'外交':13,'科技':12,'AI/LLM':15,'能源':11,'灾害':12,'环境/气候':9,'法律/犯罪':8,'产业/商业':7,'社会':2,'其他/综合':0}.get(e.get('category',''),0)
  e['importance']=min(100,42+cross_bonus+authority_bonus+min(24,impact*4)+round(e['domestic_score']*.08)+category_bonus)
  e['why_important']='涉及'+e['category']+'，结合多源报道与时效性评估后值得关注。'
  e['impact']='关注政策、市场、产业、安全及国际关系的后续影响。'
  e['next_72h']='关注官方声明、政策落地、市场反应及相关方后续行动。'
  out.append(e)
 return sorted(out,key=lambda x:(x['importance'],x.get('published_at') or ''),reverse=True)

AI_TERMS=['artificial intelligence','generative AI','large language model','language model','LLM','OpenAI','ChatGPT','GPT-','Anthropic','Claude','Google DeepMind','Gemini','AI agent','AI agents','AI model','AI models','machine learning','neural network','Hugging Face','NVIDIA NIM','Copilot','Mistral AI','DeepSeek','Qwen','Llama model','智能体','大语言模型','人工智能','生成式 AI','生成式人工智能','AI 模型','AI芯片','AI 芯片','推理模型','多模态模型','文生视频','AI安全','AI 安全']
def is_ai_related(item):
 text=(item.get('title','')+' '+(item.get('description') or '')[:800])
 return any(keyword_match(text,k) for k in AI_TERMS)

def is_low_signal_human_interest(item):
 title=item.get('title','')
 low=title.lower()
 combined=title+' '+(item.get('description') or '')
 hard=['政治','选举','政府','总理','总统','议会','经济','通胀','央行','利率','贸易','科技','芯片','人工智能','军事','国防','导弹','战争','制裁','外交','疫情','鼠疫','公共卫生','地震','灾害','制裁','能源','金融','税收','半导体','网络安全','疫情','疫苗','传染病',
       'election','government','prime minister','president','parliament','economy','inflation','central bank','interest rate','trade','technology','semiconductor','military','defense','missile','war','sanction','diplomacy','outbreak','plague','public health','earthquake','disaster','energy','finance','tax','cybersecurity','vaccine','infectious disease']
 # Always retain articles with clear public-interest or strategic-policy signals.
 if any(keyword_match(combined,k) for k in hard): return False
 patterns=[
  r'heartwarming',r'viral sensation',r'bizarre hobby',r'oddly enough',
  r'world.?s oldest',r'why this man',r'why this woman',
  r'丈夫.{0,30}妻子',r'妻子.{0,30}丈夫',r'潜水.{0,30}妻子',r'寻妻',r'寻找失踪妻子',
  r'感人故事',r'暖心故事',r'奇闻',r'猎奇',
  r'celebrity',r'horoscope',r'astrology',r'reality tv',r'fashion trend',
  r'名人八卦',r'星座运势',r'综艺明星',r'时尚穿搭'
 ]
 return any(re.search(p,low if p.isascii() else combined,re.I) for p in patterns)

def main():
 now=dt.datetime.now(dt.timezone.utc); cutoff=now-dt.timedelta(hours=25); ai_cutoff=now-dt.timedelta(days=30)
 raw={c['code']:[] for arr in CONFIG['tiers'].values() for c in arr}; global_rows=[]; ai_rows=[]; failures=[]; ok=0
 print('雷达新闻 V22：多源事件聚合 + 独立 AI/LLM 新闻池，不预设媒体优先')
 with ThreadPoolExecutor(max_workers=WORKERS) as ex:
  fs=[ex.submit(fetch_feed,f) for f in (FEEDS+AI_FEEDS)]
  for fut in as_completed(fs):
   feed,rows,err=fut.result(); source,fc,_,lang=feed
   if err:failures.append({'source':source,'country':fc,'error':err});print('[FAIL]',source,err);continue
   ok+=1; fresh=[]
   for x in rows:
    p=dateval(x.get('published_at'))
    if is_ai_related(x) and (not p or p>=ai_cutoff):
     ai_item=x.copy(); ai_item['code']='GLOBAL'; ai_item['event_country']='AI / LLM'; ai_item['event_country_en']='AI / LLM'; ai_rows.append(ai_item)
    if p and p<cutoff:continue
    if is_low_signal_human_interest(x):
     print('[FILTER-LOW-SIGNAL]',source,x.get('title','')[:120]); continue
    code=infer_country(x); x['code']=code
    c=CODE_TO_COUNTRY.get(code)
    x['event_country']=c['name'] if c else '国际/全球'; x['event_country_en']=c['en'] if c else 'Global'
    fresh.append(x)
   for item in fresh:
    code=item.get('code','GLOBAL')
    if code in raw:raw[code].append(item)
    else:global_rows.append(item)
   print('[OK]',source,len(fresh))
 for x in global_rows:
  if x.get('code') in raw:raw[x['code']].append(x)
 all_events=[]; report={'generated_at':now.isoformat(),'generated_beijing':dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M'),'window_hours':24,'version':'V22.0','source_mode':'multi-source-event-first-direct-rss','source_total':len(FEEDS)+len(AI_FEEDS),'source_ok':ok,'ai_news_target':20,'ai_news_window_days':30,'failures':failures,'tiers':{},'global_top':[],'supplement':[]}
 for tier,arr in CONFIG['tiers'].items():
  report['tiers'][tier]={}
  for c in arr:
   pool=raw.get(c['code'],[])
   # 不再按语言限制事件；国家页只负责地理组织，主来源由事件聚合模型选择。
   ev=cluster(pool)[:c['max']*3]
   report['tiers'][tier][c['name']]={'country':c['name'],'country_en':c['en'],'code':c['code'],'target_min':c['min'],'target_max':c['max'],'count':len(ev),'events':ev}
   all_events.extend(ev)
 report['supplement']=cluster(global_rows)[:10]
 report['global_top']=cluster(all_events+report['supplement'])[:20]
 ai_events=cluster(ai_rows)
 # Prefer high-impact AI developments; use a 30-day backfill pool to keep the module populated.
 ai_events.sort(key=lambda e:(e.get('importance',0),e.get('published_at') or ''),reverse=True)
 report['ai_news']=ai_events[:20]
 report['ai_news_count']=len(report['ai_news'])
 report['ai_news_status']='ready' if len(report['ai_news'])==20 else 'partial'
 report['stats']={'countries':sum(len(v) for v in report['tiers'].values()),'events':sum(x['count'] for v in report['tiers'].values() for x in v.values()),'tier1_events':sum(x['count'] for x in report['tiers']['tier1'].values()),'supplement_events':len(report['supplement']),'failed_sources':len(failures),'successful_sources':ok,'chinese_sources':sum(1 for f in FEEDS if f[3]=='cn'),'ai_feed_total':len(AI_FEEDS)}
 print('STATS',report['stats'])
 if report['stats']['events']<MIN_TOTAL_EVENTS or report['stats']['tier1_events']<MIN_TIER1_EVENTS:
  print('QUALITY GATE FAILED'); raise SystemExit(2)
 report['stale_fallback']=False
 with open(DAILY,'w',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
 date=report['generated_beijing'][:10]
 with open(os.path.join(HISTORY,date+'.json'),'w',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
 print('QUALITY GATE PASSED')

if __name__=='__main__':main()
