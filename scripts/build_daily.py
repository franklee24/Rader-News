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
from urllib.parse import urljoin

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
 # Dedicated international coverage of China: keep these separate from domestic Chinese outlets.
 ('Reuters China','CN','https://news.google.com/rss/search?q=site%3Areuters.com%20China&hl=en-US&gl=US&ceid=US:en','en'),
 ('BBC China','CN','https://news.google.com/rss/search?q=site%3Abbc.com%2Fnews%20China&hl=en-US&gl=US&ceid=US:en','en'),
 ('Associated Press China','CN','https://news.google.com/rss/search?q=site%3Aapnews.com%20China&hl=en-US&gl=US&ceid=US:en','en'),
 ('New York Times China','CN','https://news.google.com/rss/search?q=site%3Anytimes.com%20China&hl=en-US&gl=US&ceid=US:en','en'),
 ('Wall Street Journal China','CN','https://news.google.com/rss/search?q=site%3Awsj.com%20China&hl=en-US&gl=US&ceid=US:en','en'),
 ('Bloomberg China','CN','https://news.google.com/rss/search?q=site%3Abloomberg.com%20China&hl=en-US&gl=US&ceid=US:en','en'),
 ('Financial Times China','CN','https://news.google.com/rss/search?q=site%3Aft.com%20China&hl=en-US&gl=US&ceid=US:en','en'),
 ('The Economist China','CN','https://news.google.com/rss/search?q=site%3Aeconomist.com%20China&hl=en-US&gl=US&ceid=US:en','en'),
 ('The Guardian China','CN','https://news.google.com/rss/search?q=site%3Atheguardian.com%20China&hl=en-US&gl=US&ceid=US:en','en'),
 ('NPR China','CN','https://news.google.com/rss/search?q=site%3Anpr.org%20China&hl=en-US&gl=US&ceid=US:en','en'),
]

# 独立 AI/LLM 新闻池：官方一手发布 + 权威科技媒体交叉报道
AI_FEEDS=[
 # Official company announcements, model releases and first-party research.
 ('OpenAI News','GLOBAL','https://openai.com/news/rss.xml','en'),
 ('Google AI Blog','GLOBAL','https://blog.google/innovation-and-ai/technology/ai/rss/','en'),
 ('Google DeepMind','GLOBAL','https://news.google.com/rss/search?q=site%3Adeepmind.google%2Fblog%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('Google Research','GLOBAL','https://research.google/blog/rss/','en'),
 ('Anthropic News Watch','GLOBAL','https://news.google.com/rss/search?q=site%3Aanthropic.com%2Fnews%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('Meta AI','GLOBAL','https://news.google.com/rss/search?q=site%3Aabout.fb.com%2Fnews%20Meta%20AI%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('NVIDIA AI Blog','GLOBAL','https://blogs.nvidia.com/feed/','en'),
 ('NVIDIA Developer AI','GLOBAL','https://developer.nvidia.com/blog/category/generative-ai/feed/','en'),
 ('Microsoft AI Blog','GLOBAL','https://www.microsoft.com/en-us/microsoft-cloud/blog/feed/','en'),
 ('Microsoft Research AI','GLOBAL','https://www.microsoft.com/en-us/research/feed/','en'),
 ('AWS ML Blog','GLOBAL','https://aws.amazon.com/blogs/machine-learning/feed/','en'),
 ('Hugging Face Blog','GLOBAL','https://huggingface.co/blog/feed.xml','en'),
 ('Mistral AI News','GLOBAL','https://mistral.ai/news/rss','en'),
 ('Apple ML Research','GLOBAL','https://machinelearning.apple.com/rss.xml','en'),
 # Major Chinese AI companies: official domains and their official engineering/model repositories.
 ('Alibaba Qwen','GLOBAL','https://news.google.com/rss/search?q=site%3Aqwenlm.github.io%20OR%20site%3Agithub.com%2FQwenLM%20OR%20site%3Aalibabacloud.com%2Fblog%20Qwen%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('DeepSeek','GLOBAL','https://news.google.com/rss/search?q=site%3Adeepseek.com%20OR%20site%3Agithub.com%2Fdeepseek-ai%20DeepSeek%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('ByteDance Seed','GLOBAL','https://news.google.com/rss/search?q=site%3Aseed.bytedance.com%20OR%20site%3Agithub.com%2FByteDance%20AI%20model%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('Zhipu GLM','GLOBAL','https://news.google.com/rss/search?q=site%3Az.ai%20OR%20site%3Azhipuai.cn%20OR%20site%3Agithub.com%2FTHUDM%20GLM%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('Moonshot Kimi','GLOBAL','https://news.google.com/rss/search?q=site%3Amoonshot.cn%20OR%20site%3Akimi.com%20OR%20site%3Agithub.com%2FMoonshotAI%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('Baidu ERNIE','GLOBAL','https://news.google.com/rss/search?q=site%3Aernie.baidu.com%2Fblog%2Fposts%20when%3A365d&hl=en-US&gl=US&ceid=US:en','en'),
 ('Tencent Hunyuan','GLOBAL','https://news.google.com/rss/search?q=site%3Ahunyuan.tencent.com%20OR%20site%3Agithub.com%2FTencent-Hunyuan%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('MiniMax','GLOBAL','https://news.google.com/rss/search?q=site%3Aminimax.io%20OR%20site%3Agithub.com%2FMiniMax-AI%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('StepFun','GLOBAL','https://news.google.com/rss/search?q=site%3Astepfun.com%20OR%20site%3Agithub.com%2Fstepfun-ai%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 # Independent international reporting, analysis and research.
 ('Reuters AI','GLOBAL','https://news.google.com/rss/search?q=site%3Areuters.com%20AI%20OR%20artificial%20intelligence%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('Financial Times AI','GLOBAL','https://news.google.com/rss/search?q=site%3Aft.com%20AI%20OR%20artificial%20intelligence%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('New York Times AI','GLOBAL','https://news.google.com/rss/search?q=site%3Anytimes.com%20AI%20OR%20artificial%20intelligence%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('Bloomberg AI','GLOBAL','https://news.google.com/rss/search?q=site%3Abloomberg.com%20AI%20OR%20artificial%20intelligence%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('Wall Street Journal AI','GLOBAL','https://news.google.com/rss/search?q=site%3Awsj.com%20AI%20OR%20artificial%20intelligence%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('Associated Press AI','GLOBAL','https://news.google.com/rss/search?q=site%3Aapnews.com%20AI%20OR%20artificial%20intelligence%20when%3A30d&hl=en-US&gl=US&ceid=US:en','en'),
 ('TechCrunch AI','GLOBAL','https://techcrunch.com/category/artificial-intelligence/feed/','en'),
 ('MIT Technology Review AI','GLOBAL','https://www.technologyreview.com/topic/artificial-intelligence/feed/','en'),
 ('The Verge AI','GLOBAL','https://www.theverge.com/rss/ai-artificial-intelligence/index.xml','en'),
 ('arXiv cs.AI','GLOBAL','https://rss.arxiv.org/rss/cs.AI','en'),
 ('arXiv cs.CL','GLOBAL','https://rss.arxiv.org/rss/cs.CL','en'),
]

ALIASES={
'US':['美国','美方','美总统','特朗普','华盛顿','白宫','美国政府','美联储','美国国会','美军','美国经济','United States','Trump','Washington','White House','Federal Reserve'],
'CN':['中国','中方','中国政府','国务院','北京','重庆','黄奇帆','纪委','纪律审查','监察调查','中管干部','人民币','央行','中国人民银行','China','Beijing','Chongqing','Huang Qifan'],
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

def parse_ccdi_listing(body,source):
 raw=body.decode('utf-8','ignore')
 rows=[]; seen=set()
 pattern=re.compile(r'<a\b[^>]*href=(["\'])(.*?)\1[^>]*>(.*?)</a>',re.I|re.S)
 for m in pattern.finditer(raw):
  title=clean(re.sub(r'<[^>]+>',' ',m.group(3)))
  href=urljoin('https://www.ccdi.gov.cn/',html.unescape(m.group(2)))
  if not title or 'ccdi.gov.cn' not in href or not re.search(r'(接受.{0,12}(调查|审查)|纪律审查|监察调查|审查调查|被查|严重违纪违法)',title): continue
  if href in seen: continue
  context_start=max(0,m.start()-420)
  context=raw[context_start:min(len(raw),m.end()+420)]
  dates=list(re.finditer(r'20\d{2}-\d{1,2}-\d{1,2}',context))
  if not dates: continue
  date=min(dates,key=lambda match:abs(context_start+match.start()-m.start())).group(0)
  published=dateval(date)
  if not published: continue
  seen.add(href)
  rows.append({'title':title,'link':href,'published_at':published.isoformat(),'source':source,'source_url':href,'description':title,'feed_country':'CN','language':'cn'})
 return rows

def fetch_feed(feed):
 source,country,url,lang=feed; body,err=fetch(url)
 if not body:return feed,[],err
 try:
  rows=parse_ccdi_listing(body,source) if source=='CCDI Official investigations' else parse_feed(body,source,country,lang)
  return feed,rows,None
 except Exception as e:return feed,[],'parse '+str(e)[:120]

SOURCE_AUTHORITY={
 '纽约时报':96,'纽约时报-日本':96,'华尔街日报':96,'彭博社':96,'金融时报':96,'WHO News':98,'Japan Times':91,'Kyodo News':89,'BBC World':94,'卫报':92,'华盛顿邮报':94,'OpenAI News':98,'Google AI Blog':97,'Google DeepMind':98,'Google Research':96,'Anthropic News Watch':97,'Meta AI':95,'NVIDIA AI Blog':96,'NVIDIA Developer AI':94,'Microsoft AI Blog':96,'Microsoft Research AI':96,'AWS ML Blog':93,'Hugging Face Blog':91,'Mistral AI News':93,'Apple ML Research':95,'Alibaba Qwen':91,'DeepSeek':92,'ByteDance Seed':90,'Zhipu GLM':89,'Moonshot Kimi':89,'Baidu ERNIE':88,'Tencent Hunyuan':88,'MiniMax':88,'StepFun':87,'Reuters AI':98,'Financial Times AI':97,'New York Times AI':96,'Bloomberg AI':97,'Wall Street Journal AI':96,'Associated Press AI':97,'TechCrunch AI':89,'arXiv cs.AI':92,'arXiv cs.CL':92,'MIT Technology Review AI':94,'The Verge AI':88,
 'Reuters':98,'Reuters China':98,'Associated Press':97,'Associated Press China':97,'New York Times China':96,'Wall Street Journal China':96,'Bloomberg China':96,'Financial Times China':96,'The Economist China':92,'BBC China':94,'The Guardian China':92,'NPR China':90,'Yonhap':88,'The Hindu National':87,'The Hindu International':87,'CBC World':88,'ABC Australia':88,'Le Monde English':90,'Anadolu World':85,'South China Morning Post':86,
 'CCDI Official investigations':99,'中央纪委国家监委网站':99,'新华社':96,'央视网':94,
 '半岛电视台':90,'NPR':90,'NHK World':90,'NHK':90,'经济学人':92,'DW':89,'France24':88,'BBC UK':94,
 'TASS':82,'联合早报':78,'BBC中文':82,'中新网-即时':62,'人民网-时政':62,'新华-时政':62,'新华-国际':62
}
def source_group(name):
 if name.startswith('中新网'): return '中新网'
 if name.startswith('人民网'): return '人民网'
 if name.startswith('新华'): return '新华社'
 if name.startswith('arXiv'): return 'arXiv'
 if name in {'Google AI Blog','Google DeepMind','Google Research'}: return 'Google'
 if name in {'NVIDIA AI Blog','NVIDIA Developer AI'}: return 'NVIDIA'
 if name in {'Microsoft AI Blog','Microsoft Research AI'}: return 'Microsoft'
 if name in {'Reuters','Reuters China','Reuters AI'}: return 'Reuters'
 if name in {'Associated Press','Associated Press China','Associated Press AI'}: return 'Associated Press'
 if name in {'纽约时报','纽约时报-日本','New York Times China','New York Times AI'}: return 'New York Times'
 if name in {'华尔街日报','Wall Street Journal China','Wall Street Journal AI'}: return 'Wall Street Journal'
 if name in {'彭博社','Bloomberg China','Bloomberg AI'}: return 'Bloomberg'
 if name in {'金融时报','Financial Times China','Financial Times AI'}: return 'Financial Times'
 if name in {'NHK','NHK World'}: return 'NHK'
 if name in {'BBC World','BBC UK','BBC中文','BBC China'}: return 'BBC'
 if name in {'CCDI Official investigations','Google News CCDI Investigations','中央纪委国家监委网站'}: return 'CCDI Official'
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

def is_major_china_investigation(item):
 title=(item.get('title') or '')
 body=(item.get('description') or '')
 text=(title+' '+body).lower()
 source_names=[item.get('source','')]
 source_names += item.get('source_names',[]) if isinstance(item.get('source_names'),list) else []
 source_names += [s.get('source','') for s in item.get('sources',[]) if isinstance(s,dict)]
 official=any(('CCDI Official investigations' in s or 'Google News CCDI Investigations' in s or '中央纪委国家监委网站' in s) for s in source_names)
 investigation=any(k in text for k in ['接受审查调查','纪律审查','监察调查','审查调查','被查','涉嫌严重违纪违法','under investigation','corruption investigation'])
 senior=any(k in title for k in ['市委原副书记','市委书记','省委副书记','省委常委','省委书记','原市长','原省长','副省长','省政府原','党组成员','中管干部','部长','副部长','省部级','市政府原市长','国家监委'])
 return investigation and (official or senior)

def rank_china_events(events,target_max=20):
 priority=[e for e in events if is_major_china_investigation(e)]
 others=[e for e in events if e not in priority]
 high=[e for e in others if e.get('source_authority',0)>=80]
 domestic=[e for e in others if e.get('source_authority',0)<80]
 cap=max(2,round(int(target_max)*.25))
 selected=priority+high+domestic[:cap]
 unique=[]; seen=set()
 for e in sorted(selected,key=lambda x:(x.get('importance',0),x.get('source_authority',0),x.get('published_at') or ''),reverse=True):
  key=e.get('id') or e.get('url') or norm(e.get('title',''))
  if not key or key in seen: continue
  seen.add(key); unique.append(e)
 return unique[:target_max*3]

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
  srcs=sorted(grouped.values(),key=lambda s:(source_rank(s),s.get('published_at') or ''),reverse=True)[:2]
  best=srcs[0] if srcs else e['sources'][0]
  summary=clean(best.get('description',''))
  # Keep the published snapshot compact for mobile loading; preserve enough source detail for the event modal.
  compact_sources=[{'source':s.get('source',''),'link':s.get('link',''),'published_at':s.get('published_at'),'description':clean(s.get('description',''))[:120]} for s in srcs]
  e.update(
   source=best.get('source',''),url=best.get('link',''),source_url=best.get('source_url',''),
   sources=compact_sources,source_count=len(grouped),source_names=[s.get('source','') for s in srcs],
   source_authority=source_rank(best),summary=summary[:180],description=summary[:180],
   category=category(e['title']+' '+summary)
  )
  impact=sum(1 for k in HIGH if k.lower() in e['title'].lower())
  authority_bonus=min(12,round(e['source_authority']/12))
  cross_bonus=min(20,5*max(0,e['source_count']-1))
  e['domestic_score']=min(100,30+impact*8) if e['code']!='GLOBAL' else 12
  category_bonus={'国防安全':16,'公共卫生/疫情':16,'政治':14,'宏观经济':14,'金融':13,'外交':13,'科技':12,'AI/LLM':15,'能源':11,'灾害':12,'环境/气候':9,'法律/犯罪':8,'产业/商业':7,'社会':2,'其他/综合':0}.get(e.get('category',''),0)
  e['importance']=min(100,42+cross_bonus+authority_bonus+min(24,impact*4)+round(e['domestic_score']*.08)+category_bonus)
  if is_major_china_investigation(e):
   e['category']='政治'
   boost=98 if any(k in (e.get('title','')+' '+e.get('description','')).lower() for k in ['黄奇帆','huang qifan','former mayor of chongqing']) else 96
   e['importance']=max(e['importance'],boost); e['importance_level']='国家重大'
  e['why_important']='涉及'+e['category']+'，结合多源报道与时效性评估后值得关注。'
  e['impact']='关注政策、市场、产业、安全及国际关系的后续影响。'
  e['next_72h']='关注官方声明、政策落地、市场反应及相关方后续行动。'
  out.append(e)
 return sorted(out,key=lambda x:(x['importance'],x.get('published_at') or ''),reverse=True)

AI_TERMS=['artificial intelligence','generative AI','large language model','language model','LLM','OpenAI','ChatGPT','GPT-','Anthropic','Claude','Google DeepMind','Gemini','AI agent','AI agents','AI model','AI models','machine learning','neural network','Hugging Face','NVIDIA NIM','Copilot','Mistral AI','DeepSeek','Qwen','Llama model','智能体','大语言模型','人工智能','生成式 AI','生成式人工智能','AI 模型','AI芯片','AI 芯片','推理模型','多模态模型','文生视频','AI安全','AI 安全']
def is_ai_related(item):
 title=item.get('title','')
 desc=(item.get('description') or '')[:800]
 # Prefer a strong headline signal; avoid admitting unrelated stories only because the body mentions AI.
 if any(keyword_match(title,k) for k in AI_TERMS): return True
 strong=('artificial intelligence','generative AI','large language model','language model','LLM','AI model','machine learning','neural network','大语言模型','人工智能','生成式人工智能')
 return sum(1 for k in strong if keyword_match(desc,k))>=2

def is_china_related(item):
 text=item.get('title','')  # Require China-related framing in the headline, not a passing mention in the article body.
 if any(term in text for term in ['中国','中方','北京','习近平','中国政府','中国企业','中国经济','中国市场','中国共产党','中共','香港','新疆','西藏','南海','台海','两岸','黄奇帆','重庆','纪委','纪律审查','监察调查','被查','接受审查调查','审查调查','中管干部']):
  return True
 patterns=[r'\bChina\b',r'\bChinese\b',r'\bBeijing\b',r'\bXi Jinping\b',r'\bPRC\b',r'\bChinese Communist Party\b',r'\bSouth China Sea\b',r'\bTaiwan Strait\b',r'\bHong Kong\b',r'\bXinjiang\b',r'\bTibet\b',r'\bHuang Qifan\b',r'\bChongqing\b',r'\bformer mayor of Chongqing\b']
 return any(re.search(p,text,re.I) for p in patterns)


def country_for_source(item,china_watch_sources):
 if item.get('source') in {'CCDI Official investigations','Google News CCDI Investigations','中央纪委国家监委网站'}: return 'CN'
 if item.get('source') in china_watch_sources:
  if is_china_related(item): return 'CN'
  # Do not let a China-specific feed's default country override an unrelated headline.
  return infer_country({**item,'description':'','feed_country':None})
 return infer_country(item)


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

def fetch_priority_china_fallback(now):
 # Time-limited backfill for a verified high-priority news item; expires after 72 hours.
 published=dt.datetime(2026,10,13,10,1,21,tzinfo=dt.timezone.utc)
 if now < published or now > published+dt.timedelta(hours=72): return None
 headline='重庆市委原副书记、市政府原市长黄奇帆接受中央纪委国家监委纪律审查和监察调查'
 candidates=[
  ('新华社','https://www.xinhuanet.com/20261013/42f8ebe3d896453b80fd70d48d908a26/c.html'),
  ('央视网','https://news.cctv.cn/2026/10/13/ARTIO2TV3HaY2eJmAZNIvmBY261013.shtml'),
  ('中央纪委国家监委网站','https://www.ccdi.gov.cn/scdcn/zggb/zjsc/202610/t20261013_516561.html'),
 ]
 for source,url in candidates:
  body,err=fetch(url)
  if not body:
   print('[BACKFILL-SOURCE-FAIL]',source,err)
   continue
  page=clean(body.decode('utf-8','ignore'))
  if '黄奇帆' not in page or not any(k in page for k in ['纪律审查','监察调查','接受审查调查']):
   print('[BACKFILL-SOURCE-REJECTED]',source,'expected headline not found')
   continue
  return {'id':hashlib.sha1(norm(headline).encode()).hexdigest()[:16],
          'title':headline,'link':url,'published_at':published.isoformat(),
          'source':source,'source_url':url,'description':headline,
          'feed_country':'CN','language':'cn','code':'CN',
          'event_country':'中国','event_country_en':'China'}
 return None

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
    if p and p<cutoff and not (is_major_china_investigation(x) and p>=now-dt.timedelta(hours=72)):continue
    if is_low_signal_human_interest(x):
     print('[FILTER-LOW-SIGNAL]',source,x.get('title','')[:120]); continue
    # China-specific search feeds are candidates, not proof of relevance:
    # require a China-related headline before allowing an item into the China section.
    china_watch_sources={'Reuters China','BBC China','Associated Press China','New York Times China','Wall Street Journal China','Bloomberg China','Financial Times China','The Economist China','The Guardian China','NPR China'}
    if x.get('source') in china_watch_sources and not is_china_related(x):
     print('[FILTER-CHINA-IRRELEVANT]',source,x.get('title','')[:140]); continue
    # Keep Chinese domestic outlets on their existing country classification logic;
    # only China-targeted international query feeds get strict headline gating.
    if x.get('source') in china_watch_sources:
     code='CN'
    else:
     code=country_for_source(x,china_watch_sources)
    x['code']=code
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
 priority_fallback=fetch_priority_china_fallback(now)
 if priority_fallback:
  raw['CN'].append(priority_fallback)
  print('[BACKFILL-PRIORITY]',priority_fallback['title'],'source:',priority_fallback['source'])
 all_events=[]; report={'generated_at':now.isoformat(),'generated_beijing':dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M'),'window_hours':24,'version':'V22.0','source_mode':'multi-source-event-first-direct-rss','source_total':len(FEEDS)+len(AI_FEEDS),'source_ok':ok,'ai_news_target':20,'ai_news_window_days':30,'failures':failures,'tiers':{},'global_top':[],'supplement':[]}
 for tier,arr in CONFIG['tiers'].items():
  report['tiers'][tier]={}
  for c in arr:
   pool=raw.get(c['code'],[])
   # 不再按语言限制事件；国家页只负责地理组织，主来源由事件聚合模型选择。
   ev=cluster(pool)
   if c['code']=='CN':
    # Preserve major official investigations regardless of source bucket; rank by event importance first.
    ev=rank_china_events(ev,int(c.get('max',20)))
   else:
    ev=ev[:c['max']*3]
   report['tiers'][tier][c['name']]={'country':c['name'],'country_en':c['en'],'code':c['code'],'target_min':c['min'],'target_max':c['max'],'count':len(ev),'events':ev}
   all_events.extend(ev)
 report['supplement']=cluster(global_rows)[:10]
 report['global_top']=cluster(all_events+report['supplement'])[:20]
 ai_events=cluster(ai_rows)
 # Rank candidates on the same importance scale, while preventing one publisher or research feed from filling the module.
 ai_events.sort(key=lambda e:(e.get('importance',0),e.get('published_at') or ''),reverse=True)
 ai_selected=[]; ai_seen=set(); ai_group_counts={}
 for item in ai_events:
  key=item.get('id') or norm(item.get('title',''))
  if not key or key in ai_seen: continue
  group=source_group(item.get('source',''))
  # Research remains eligible, but arXiv is one publisher—not two independent outlets.
  if ai_group_counts.get(group,0)>=4: continue
  ai_selected.append(item); ai_seen.add(key); ai_group_counts[group]=ai_group_counts.get(group,0)+1
  if len(ai_selected)>=20: break
 # Relax publisher caps only if the 30-day candidate pool cannot otherwise reach 20 stories.
 if len(ai_selected)<20:
  for item in ai_events:
   key=item.get('id') or norm(item.get('title',''))
   if key and key not in ai_seen:
    ai_selected.append(item); ai_seen.add(key)
    if len(ai_selected)>=20: break
 report['ai_news']=ai_selected[:20]
 report['ai_news_count']=len(report['ai_news'])
 print('AI NEWS SOURCE MIX',ai_group_counts)
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
