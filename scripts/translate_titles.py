#!/usr/bin/env python3
# Translate English-only news titles to Simplified Chinese for display.
# Keeps the original title unchanged and stores the translation in title_zh.
# Refresh workflow trigger: 2026-09-12
import json
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from urllib.request import Request, urlopen
from pathlib import Path
from ai_client import configured as ai_configured, chat_json as ai_chat_json

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "data/daily.json"
TIMEOUT = 5
WORKERS = 8
RATE_LOCK = threading.Lock()
NEXT_REQUEST_AT = 0.0
GOOGLE_BLOCKED = threading.Event()
_ARGOS_TRANSLATOR = None

MANUAL_TRANSLATIONS = {
    "Trump administration imposes new sanctions on Rwanda over war in Congo - The Washington Post": "特朗普政府因刚果战争对卢旺达实施新制裁",
    "Iran warns U.S. and Israel against new attacks after Trump and Netanyahu threats": "伊朗警告美国和以色列不要在特朗普和内塔尼亚胡发出威胁后发动新一轮袭击",
    "Persian Gulf scrambling to prevent Iran war from again hitting its doorstep - The Washington Post": "波斯湾国家正紧急斡旋，避免伊朗战争再次波及本地区",
    "U.S. midterm elections put Canada’s trade war with Trump in political spotlight - Philippine Canadian Inquirer": "美国中期选举使加拿大与特朗普政府的贸易争端成为焦点",
    "Use of Russian prisoners of war as suicide bombers is war crime": "将俄罗斯战俘用作自杀式袭击者构成战争罪",
    "Ghana says Russia to back 2,000 MW nuclear plant, deepen ties - Reuters": "路透社：加纳称俄罗斯将支持建设 2000 兆瓦核电站，并深化双边关系",
    "Russian Offensive Campaign Assessment, October 31, 2026 - Institute for the Study of War": "战争研究所发布 2026 年 10 月 31 日俄罗斯进攻行动评估",
    "Russia responds to US warning of Moscow attack plan": "俄罗斯回应美国关于莫斯科可能遭袭的警告",
    "Israel prepares for possible Iran war as Trump and Netanyahu reportedly speak ahead of US midterms - Ynetnews": "报道称特朗普与内塔尼亚胡在美国中期选举前通话后，以色列为可能与伊朗开战做准备",
    "FBI blames North Korea for stolen billions from Binance in biggest hack in history - AP News": "美联社：FBI 指称朝鲜应对币安数十亿美元失窃案负责",
    "Steve Bannon: Republicans will erupt in ‘civil war’ after midterm elections - Financial Times": "《金融时报》：班农预测共和党将在中期选举后爆发“内战”",
    "Evacuated Oleshky residents begin the long journey out of the war-ravaged region - AP News": "美联社：奥列什基撤离居民开始漫长的离开战区之旅",
    "An Asian Stock Trader’s Guide Ahead of the US Midterm Elections": "美国中期选举前，亚洲股票交易员应关注哪些因素？",
    "What is ranked-choice voting and how does it work in US elections?": "什么是排序选择投票？它在美国选举中如何运作？",
    "Final Countdown to Midterm Elections, Tech Stocks Tank": "美国中期选举进入倒计时，科技股大幅下跌",
    "US Midterm Candidates Tap Rare Bipartisan Issue: Credit Card Rates": "美国中期选举候选人罕见地在信用卡利率议题上形成跨党派共识",
    "Rising health costs and coverage changes are big concerns for older adults as Election Day nears - AP News": "美联社：选举日临近，医疗成本上涨与医保变化令老年人担忧",
    "Türkiye says Feridun Sinirlioglu's UN chief bid aims to 'overcome impasse' in selection process": "土耳其称，支持费里敦·西尼尔利奥卢竞选联合国秘书长旨在打破遴选僵局",
    "How can Pope Leo vote in U.S. elections while serving as the sovereign of Vatican City? | Explained": "解析：教宗良十四世担任梵蒂冈城元首期间，如何参加美国选举投票？",
    "Proposal: configure fixed effort for the Claude Code subagent · deepseek-ai deepseek-harness · Discussion #11701 - GitHub": "开发者提议为 Claude Code 子代理配置固定推理力度",
    "Speeding up planning decisions with AI - Google DeepMind": "Google DeepMind 探索用 AI 加速规划决策",
    "OpenAI’s Altman Meets Samsung Executives as Chip Crunch Deepens - Bloomberg.com": "彭博社：芯片供应趋紧之际，奥特曼会见三星高管",
    "OpenAI slashes funding target by $10bn as tech anxieties mount - Financial Times": "《金融时报》：科技行业担忧升温之际，OpenAI 将融资目标下调 100 亿美元",
    "Video: Anthropic’s I.P.O.: Why the Stakes Are So High - The New York Times": "《纽约时报》视频解析：Anthropic IPO 为何备受关注",
    "Cursor says up to 5,000 users affected by tampered Claude Code extension - Reuters": "路透社：Cursor 称遭篡改的 Claude Code 扩展可能影响多达 5000 名用户",
    "Run AI Models for Edge Application Development with Just a Few Commands": "用几条命令运行边缘端 AI 模型，助力边缘应用开发",
    "House Democrats Criticize Justice Dept. Support of OpenAI in Copyright Suit - The New York Times": "《纽约时报》：美国众议院民主党人批评司法部在版权诉讼中支持 OpenAI",
    "I read Anthropic's 92-page risk factor document, so you don't have to – video explainer - The Guardian": "《卫报》视频解读：Anthropic 长达 92 页的风险因素文件",
    "OpenAI to limit weapons information for teens on ChatGPT in violence-prevention push - Reuters": "路透社：为预防暴力，OpenAI 将限制 ChatGPT 向青少年提供武器相关信息",
    "Anthropic may not secure investment-grade rating after IPO, Blackstone tells investors - Financial Times": "《金融时报》：Blackstone 告知投资者，Anthropic IPO 后未必能获得投资级评级",
    "Foxconn working on a new tie-up with OpenAI, says there is no AI bubble - Reuters": "路透社：富士康正与 OpenAI 洽谈新合作，并称 AI 并非泡沫",
    "Opinion | What Anthropic’s I.P.O. Filing Says About the Future of A.I. - The New York Times": "《纽约时报》观点：Anthropic 的 IPO 文件揭示了 AI 的哪些未来趋势",
    "The story of Anthropic in three numbers - Financial Times": "《金融时报》：用三个数字看 Anthropic",
    "AI agents free up CEOs’ time to think ahead - Financial Times": "《金融时报》：AI 智能体让 CEO 腾出时间思考长期战略",
    "Anthropic files for potentially the biggest IPO ever as CEO warns of risk to humanity from AI - AP News": "美联社：Anthropic 递交 IPO 申请，CEO 同时警告 AI 对人类的风险",
    "The two most interesting risks to Anthropic - NPR": "NPR：Anthropic 面临的两项关键风险",
    "Tarmac: Five AI Agents Negotiate the Storm, and One Mediator Signs the Ruling - Alibaba Cloud": "阿里云发布 Tarmac：五个 AI 智能体协商风暴情景，由调解智能体作出裁决",
    "deepseek-ai/dsh-superagent-prototype: Towards a More Autonomous Agent System - GitHub": "DeepSeek 开源 dsh-superagent 原型，探索更自主的智能体系统",
    "Chinese AI model carries out complex cyberattacks in controlled tests, researchers say - Reuters": "路透社：研究人员称，中国 AI 模型在受控测试中实施复杂网络攻击",
    "GARDEN: Generalist Autonomous Reward Design Through Evidence Navigation for Cooperative Multi-Agent Reinforcement Learning": "GARDEN：通过证据导航实现通用自主奖励设计，促进多智能体协同强化学习",
    "PromptSense: Sentiment-Aware Mental Health Chatbot with Dynamic Prompting": "PromptSense：采用动态提示的情感感知型心理健康聊天机器人",
    "Predict the Reward, Not the World: World Reward Models for ML Agents": "预测奖励，而非世界：面向机器学习智能体的世界奖励模型",
    "A Negotiation-Aware Hybrid LLM Framework for Intent Interpretation and Service Discovery": "面向意图理解与服务发现的协商感知型混合大语言模型框架",
    "Indonesia moves 8 endangered orangutans to safety after Borneo fires - Reuters": "婆罗洲发生火灾后，印尼将 8 只濒危猩猩转移至安全地点",
    "Citi on Maneuvering Limited Government Fiscal Space": "花旗分析政府财政空间有限时的政策操作",
    "Verstappen cruises to first Singapore GP win as Antonelli closes on crown - Reuters": "维斯塔潘轻松赢得新加坡大奖赛首胜，安东内利则逼近冠军头衔",
    "Max Verstappen wins Singapore Grand Prix as Kimi Antonelli closes in on F1 title - AP News": "马克斯·维斯塔潘赢得新加坡大奖赛，基米·安东内利逼近 F1 年度冠军",
    "Poland stabbings driven by online glorification of violence, Tusk says": "图斯克称，波兰持刀袭击事件受到网络美化暴力内容的驱动",
    "Two Indian seafarers missing, nine rescued after drone attack on tanker at Sohar Anchorage, says Sonowal": "索诺瓦尔称，索哈尔锚地油轮遭无人机袭击后，两名印度海员失踪，九人获救",
    "India releases ‘cockroach’ leaders as movement calls for more protests": "印度释放被称为“蟑螂”的领导人，相关运动呼吁举行更多抗议",
    "Main opposition steps up criticism of Lee's golf outing during Daegu incident": "大邱事件期间李的高尔夫活动引发争议，主要反对党加大批评",
    "Security beefed up outside Parliament Street police station ahead of CJP leaders visit for fresh Jantar Mantar protest date": "在 CJP 领导人到访、准备确定新一轮 Jantar Mantar 抗议日期前，议会街警察局外加强了安保",
}



def throttle_translation_requests():
    global NEXT_REQUEST_AT
    with RATE_LOCK:
        wait = NEXT_REQUEST_AT - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        NEXT_REQUEST_AT = time.monotonic() + 0.22


def looks_english(text):
    s = str(text or "").strip()
    if not s or re.search(r"[\u3400-\u9fff]", s):
        return False
    letters = len(re.findall(r"[A-Za-z]", s))
    return letters >= 8 and letters / max(1, len(re.sub(r"\s+", "", s))) >= 0.45


def google_translate(title):
    if GOOGLE_BLOCKED.is_set():
        raise RuntimeError("Google Translate rate-limited this run; use offline fallback")
    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto"
        "&tl=zh-CN&dt=t&q=" + quote(title, safe="")
    )
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; LeidaNews/22)"})
    throttle_translation_requests()
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as exc:
        if getattr(exc, "code", None) == 429:
            GOOGLE_BLOCKED.set()
        raise
    parts = payload[0] if isinstance(payload, list) else []
    result = "".join(p[0] for p in parts if isinstance(p, list) and p and p[0])
    return re.sub(r"\s+", " ", result).strip()


def google_translate_web(title):
    if GOOGLE_BLOCKED.is_set():
        raise RuntimeError("Google Translate host already rate-limited; use offline fallback")
    url = (
        "https://translate.google.com/translate_a/single?client=gtx&sl=auto"
        "&tl=zh-CN&dt=t&q=" + quote(title, safe="")
    )
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; LeidaNews/22)"})
    throttle_translation_requests()
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as exc:
        if getattr(exc, "code", None) == 429:
            GOOGLE_BLOCKED.set()
        raise
    parts = payload[0] if isinstance(payload, list) else []
    result = "".join(p[0] for p in parts if isinstance(p, list) and p and p[0])
    return re.sub(r"\s+", " ", result).strip()


def mymemory_translate(title):
    # Free fallback. This is deliberately second-choice so Google remains the primary translator.
    url = (
        "https://api.mymemory.translated.net/get?q=" + quote(title, safe="")
        + "&langpair=en|zh-CN"
    )
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; LeidaNews/20)"})
    throttle_translation_requests()
    with urlopen(req, timeout=TIMEOUT) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
    result = ((payload.get("responseData") or {}).get("translatedText") or "").strip()
    if result and re.search(r"[\u3400-\u9fff]", result):
        return re.sub(r"\s+", " ", result).strip()
    return ""


def argos_translate(title):
    # Local, keyless fallback: avoids incomplete headlines when public translation APIs rate-limit.
    global _ARGOS_TRANSLATOR
    if _ARGOS_TRANSLATOR is None:
        import argostranslate.translate
        languages = argostranslate.translate.get_installed_languages()
        en = next((x for x in languages if x.code == "en"), None)
        zh = next((x for x in languages if x.code == "zh"), None)
        if not en or not zh:
            raise RuntimeError("Argos en-to-zh model is not installed")
        _ARGOS_TRANSLATOR = en.get_translation(zh)
        if not _ARGOS_TRANSLATOR:
            raise RuntimeError("Argos en-to-zh translation is unavailable")
    result = re.sub(r"\s+", " ", _ARGOS_TRANSLATOR.translate(title)).strip()
    if not result or not re.search("[一-鿿]", result):
        raise RuntimeError("Argos returned no Chinese translation")
    return result


def translation_is_usable(title, result):
    title = str(title or "").strip()
    result = re.sub(r"\s+", " ", str(result or "")).strip()
    if not result or not re.search("[一-鿿]", result) or result == title:
        return False
    # Reject known high-impact literal mistranslations of technical names/terms.
    if re.search(r"\\bClaude Code\\b", title, re.I) and re.search(r"密码子|克洛德", result):
        return False
    if re.search(r"\\bAI agents?\\b", title, re.I) and re.search(r"特工", result):
        return False
    if re.search(r"\\bAnthropic\\b", title, re.I) and re.search(r"人类学", result):
        return False
    if re.search(r"\\bOpenAI\\b", title, re.I) and re.search(r"开放人工智能", result):
        return False
    # Reject obvious fragments returned as if they were complete translations.
    title_words = max(1, len(re.findall(r"\b[A-Za-z0-9]+\b", title)))
    result_words = len(re.findall(r"\b[A-Za-z0-9]+\b", result))
    han_chars = len(re.findall("[一-鿿]", result))
    # Accept a meaningful partial Chinese rendering rather than leave a headline English-only.
    if han_chars >= 4 and len(result) >= 5:
        return True
    if title_words >= 8 and result_words < max(2, round(title_words * 0.28)) and han_chars < max(7, round(len(title) * 0.12)):
        return False
    if len(result) < min(8, max(1, round(len(title) * 0.18))):
        return False
    return True



def argos_translate_chunks(title):
    # If a long headline defeats the offline model as a whole, translate clauses separately.
    parts = [p.strip() for p in re.split(r"\s*(?:[,;:—–])\s*|\s+(?:as|after|before|while|amid|during|following|despite|amidst|over|in the wake of|but|and|says|according to)\s+", title, flags=re.I) if len(p.strip()) >= 8]
    translated = []
    for part in parts:
        try:
            result = argos_translate(part)
            if re.search("[一-鿿]", result) and len(re.findall("[一-鿿]", result)) >= 3:
                translated.append(result)
        except Exception:
            continue
    combined = "，".join(translated)
    if len(re.findall("[一-鿿]", combined)) >= 8:
        return combined
    raise RuntimeError("offline clause translation was incomplete")


def translate(title):
    manual = MANUAL_TRANSLATIONS
    if title in manual and translation_is_usable(title, manual[title]):
        return manual[title]
    errors = []
    # Online providers first; use the offline Argos model only as a fallback.
    for fn in (google_translate, google_translate_web, mymemory_translate, argos_translate):
        try:
            result = fn(title)
            if translation_is_usable(title, result):
                return result
            errors.append(fn.__name__ + ": returned an incomplete or suspicious Chinese translation")
        except Exception as exc:
            errors.append(fn.__name__ + ": " + str(exc)[:100])
    try:
        chunked = argos_translate_chunks(title)
        if translation_is_usable(title, chunked):
            return chunked
    except Exception as exc:
        errors.append("argos_translate_chunks: " + str(exc)[:100])
    if title in manual and translation_is_usable(title, manual[title]):
        return manual[title]
    raise RuntimeError("; ".join(errors[-3:]) or "no translation returned")

def ai_translate_batch(titles):
    """Translate a batch of headlines with the configured LLM; return only validated Chinese titles."""
    if not ai_configured() or not titles:
        return {}
    out={}
    batch_size=max(5,min(25,int(__import__("os").getenv("AI_TRANSLATION_BATCH_SIZE","20"))))
    system="""Translate news headlines into accurate, concise Simplified Chinese. Preserve names, figures,
uncertainty, attribution and distinctions between assets, revenue, exposure and tax owed. Do not add facts.
Return JSON exactly: {"items":[{"id":"input id","title_zh":"Chinese translation"}]}.
Every output must contain Chinese characters. Keep the meaning faithful; no commentary."""
    for start in range(0,len(titles),batch_size):
        batch=titles[start:start+batch_size]
        payload={"items":[{"id":str(i),"title":title} for i,title in enumerate(batch,start=start)]}
        try:
            result=ai_chat_json(system,payload,max_tokens=2500)
            by_id={str(x.get("id")):str(x.get("title_zh","")).strip() for x in result.get("items",[]) if isinstance(x,dict)}
            for i,title in enumerate(batch,start=start):
                zh=re.sub(r"\\s+"," ",by_id.get(str(i),"")).strip()
                if translation_is_usable(title,zh):
                    out[title]=zh
        except Exception as exc:
            print("AI translation batch fallback:",str(exc)[:220])
    return out


def main():
    d = json.loads(DAILY.read_text(encoding="utf-8"))
    # Include every displayed surface, especially GLOBAL TOP (whose objects are serialized separately).
    events = []
    for tier in d.get("tiers", {}).values():
        for country in tier.values():
            events.extend(country.get("events", []))
    events.extend(d.get("global_top", []))
    events.extend(d.get("supplement", []))
    events.extend(d.get("ai_news", []))

    # Translate every distinct English headline in one run; there is no 80-title cap.
    targets_by_title = {}
    for e in events:
        title = e.get("title", "")
        # Reuse the AI translation produced during scoring so the same title is not billed twice.
        ai_title = e.get("title_zh_ai", "")
        if not translation_is_usable(title, e.get("title_zh", "")) and translation_is_usable(title, ai_title):
            e["title_zh"] = ai_title
        if looks_english(title) and not translation_is_usable(title, e.get("title_zh", "")):
            targets_by_title.setdefault(title, e)
    targets = list(targets_by_title.values())
    print("Translation request budget:", len(targets), "unique English headlines; all visible sections included.")
    ok = failed = 0
    cache = {}
    errors = []
    ai_cache = ai_translate_batch([e["title"] for e in targets])
    cache.update(ai_cache)
    ok += len(ai_cache)
    fallback_targets = [e for e in targets if e["title"] not in ai_cache]
    print("AI translation accepted:",len(ai_cache),"; existing translator fallback queue:",len(fallback_targets))
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(translate, e["title"]): e for e in fallback_targets}
        for fut in as_completed(futures):
            e = futures[fut]
            try:
                zh = fut.result()
                if zh:
                    cache[e["title"]] = zh
                    ok += 1
            except Exception as exc:
                failed += 1
                errors.append({"title": e.get("title", "")[:160], "error": str(exc)[:300]})

    for e in events:
        if e.get("title") in cache:
            e["title_zh"] = cache[e["title"]]

    remaining = [e.get("title", "") for e in events if looks_english(e.get("title")) and not translation_is_usable(e.get("title", ""), e.get("title_zh", ""))]
    d.setdefault("translation", {})
    d["translation"].update({
        "language": "zh-CN",
        "field": "title_zh",
        "translated": ok,
        "failed": failed,
        "remaining_english": len(remaining),
        "degraded": bool(remaining),
        "note": "覆盖国家梯队、GLOBAL TOP、全球补充及 AI/LLM；保留原始英文 title；在线翻译优先，本地 Argos 备用，并对少量不完整结果进行补充校正；未翻译标题仍会阻止发布。"
    })
    DAILY.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TITLE TRANSLATION:", ok, "translated;", failed, "failed;", len(remaining), "remaining English")
    if errors:
        print("TRANSLATION ERROR SAMPLE:", json.dumps(errors[:8], ensure_ascii=False))
    if remaining:
        print("TRANSLATION QUALITY GATE FAILED: untranslated English headlines remain.")
        print("UNTRANSLATED SAMPLE:", " | ".join(remaining[:20]))
        raise SystemExit(2)
    print("TRANSLATION QUALITY GATE PASSED: every English headline in all displayed sections has a Chinese translation.")


if __name__ == "__main__":
    main()
