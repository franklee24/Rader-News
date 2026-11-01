#!/usr/bin/env python3
"""AI editorial rescoring with deterministic fallback to the existing rule score."""
import json
import os
import time
from pathlib import Path
from ai_client import configured, chat_json

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "data" / "daily.json"
BATCH = max(5, min(25, int(os.getenv("AI_BATCH_SIZE", "20"))))
SYSTEM = """You are an evidence-grounded editor for a global news briefing.
Score each supplied news EVENT from 0 to 100 for real-world importance, not sensational wording.
Consider geopolitical/security impact, macroeconomics/markets, policy/law, affected population,
verified scope, technology/AI significance, novelty, and evidence strength. Ordinary academic
papers without demonstrated deployment, clinical/regulatory validation, or substantiated
breakthrough should usually score 25-55; a major validated breakthrough may score higher.
Do not infer facts absent from title/summary. A claim about possible exposure is not confirmed
actual impact. Duplicate coverage of one event should have similar scores. Preserve rule_score as
a prior signal, but change it when evidence warrants. Return JSON exactly as:
{"items":[{"id":"same input id","score":0,"confidence":0.0,"reason_zh":"简体中文、最多45字的可核验理由","event_key":"简短规范化事件键","translation_zh":"准确简体中文标题"}]}
Scores/confidence are numeric; confidence is 0..1. Never invent sources or facts."""
def all_events(d):
    rows=[]
    for tier in d.get("tiers", {}).values():
        for country in tier.values():
            rows.extend(country.get("events", []))
    rows.extend(d.get("global_top", []))
    rows.extend(d.get("supplement", []))
    rows.extend(d.get("ai_news", []))
    # Shared objects can appear in more than one displayed surface; deduplicate by object identity.
    seen=set(); out=[]
    for e in rows:
        if id(e) not in seen:
            seen.add(id(e)); out.append(e)
    return out

def main():
    d=json.loads(DAILY.read_text(encoding="utf-8"))
    events=all_events(d)
    if not configured():
        d["ai_editorial"]={"status":"disabled","provider":"OpenAI-compatible API","reason":"AI_API_KEY/AI_MODEL secrets not configured; deterministic rule scoring and existing translation fallbacks remain active."}
        DAILY.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
        print("AI editorial scoring skipped: API credentials not configured; rules remain active.")
        return
    # Rank only candidates that can affect displayed lists, plus the AI/LLM section.
    # Keep at least the best 100 rule-ranked country/global stories and all AI/LLM entries.
    country=[e for tier in d.get("tiers",{}).values() for c in tier.values() for e in c.get("events",[])]
    supplement=d.get("supplement",[])
    ai=d.get("ai_news",[])
    selected=[]; seen=set()
    for e in sorted(country+supplement,key=lambda x:int(x.get("importance",0)),reverse=True)[:100]+ai:
        key=str(e.get("id") or e.get("url") or e.get("title") or id(e))
        if key not in seen:
            seen.add(key); selected.append(e)
    success=failed=0; errors=[]
    for start in range(0,len(selected),BATCH):
        chunk=selected[start:start+BATCH]
        payload={"items":[{"id":str(e.get("id") or e.get("url") or e.get("title") or i),
            "title":e.get("title",""),"summary":e.get("summary") or e.get("description") or "",
            "category":e.get("category",""),"country":e.get("event_country") or e.get("country") or "",
            "source":e.get("source",""),"published_at":e.get("published_at",""),
            "rule_score":int(e.get("importance",0))} for i,e in enumerate(chunk)]}
        try:
            result=chat_json(SYSTEM,payload,max_tokens=3500)
            returned={str(x.get("id")):x for x in result.get("items",[]) if isinstance(x,dict)}
            for i,e in enumerate(chunk):
                key=str(e.get("id") or e.get("url") or e.get("title") or i)
                x=returned.get(key)
                if not x: continue
                try: score=max(0,min(100,int(round(float(x.get("score"))))))
                except (TypeError,ValueError): continue
                try: confidence=max(0.0,min(1.0,float(x.get("confidence",0))))
                except (TypeError,ValueError): confidence=0.0
                if confidence < 0.55:
                    continue
                e["rule_importance"]=int(e.get("importance",0))
                e["importance"]=score
                e["importance_level"]=("全球重大" if score>=90 else "国家重大" if score>=80 else "重要事件" if score>=70 else "值得关注" if score>=60 else "一般动态")
                e["importance_model"]="AI editorial + V24 rules"
                e["ai_assessment"]={"confidence":round(confidence,2),"reason_zh":str(x.get("reason_zh",""))[:120],"event_key":str(x.get("event_key",""))[:100]}
                zh=str(x.get("translation_zh","")).strip()
                if zh and any("\u3400" <= ch <= "\u9fff" for ch in zh) and len(zh)>=4:
                    e["title_zh_ai"]=zh
                success+=1
        except Exception as exc:
            failed+=1; errors.append(str(exc)[:250])
            print("AI scoring batch fallback:",str(exc)[:250])
        time.sleep(0.15)
    # Resort all lists whose ranking uses importance.
    for tier in d.get("tiers",{}).values():
        for c in tier.values():
            c["events"].sort(key=lambda e:(int(e.get("importance",0)),e.get("published_at") or ""),reverse=True)
    d["ai_news"].sort(key=lambda e:(int(e.get("importance",0)),e.get("published_at") or ""),reverse=True)
    d["ai_editorial"]={"status":"partial" if failed else "active","provider":"OpenAI-compatible API","model":os.environ.get("AI_MODEL"),
        "candidate_count":len(selected),"scored_count":success,"failed_batches":failed,"errors":errors[:3],
        "fallback":"Existing rule score retained for missing, invalid, or low-confidence AI responses."}
    d["importance_model"]={"version":"AI+V24","principle":"AI evidence-grounded editorial judgement constrained by deterministic V24 scoring and confidence gate"}
    DAILY.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
    print("AI editorial scoring:",success,"accepted;",failed,"failed batches;",len(selected),"candidates.")

if __name__=="__main__": main()
