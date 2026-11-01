#!/usr/bin/env python3
"""Export a compact, auditable news batch for manual ChatGPT review (no API)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "data" / "daily.json"
OUT = ROOT / "data" / "ai_review"
MAX_ITEMS = 120

def clean(value, limit=700):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]

def collect(data):
    rows = []
    for tier_name, tier in (data.get("tiers") or {}).items():
        for country, bucket in (tier or {}).items():
            for e in (bucket or {}).get("events", []):
                rows.append((e, clean(country), clean(tier_name)))
    for section in ("global_top", "supplement", "ai_news"):
        for e in data.get(section, []) or []:
            rows.append((e, clean(e.get("event_country") or e.get("country") or "GLOBAL"), section))
    seen, result = set(), []
    for e, country, section in rows:
        url = clean(e.get("url") or e.get("source_url"))
        title = clean(e.get("title"))
        key = clean(e.get("id") or url or title)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append({
            "id": key, "title": title, "title_zh_existing": clean(e.get("title_zh")),
            "summary": clean(e.get("summary") or e.get("description")),
            "source": clean(e.get("source")), "url": url,
            "published_at": clean(e.get("published_at")), "country": country,
            "section": section, "rule_score": int(e.get("importance") or 0),
        })
    result.sort(key=lambda x: (x["section"] == "ai_news", x["rule_score"]), reverse=True)
    return result[:MAX_ITEMS]

def main():
    if not DAILY.exists():
        raise SystemExit("data/daily.json missing; run the news collection step first.")
    data = json.loads(DAILY.read_text(encoding="utf-8"))
    items = collect(data)
    if not items:
        raise SystemExit("No candidate news items found; refusing to produce an empty review pack.")
    OUT.mkdir(parents=True, exist_ok=True)
    pack = {"schema_version": 1, "instructions": "ChatGPT editorial review; preserve ids exactly; do not invent facts; return JSON only.", "generated_beijing": data.get("generated_beijing") or data.get("generated_at") or "", "items": items}
    (OUT / "chatgpt_review_input.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prompt = """# Radar-News：ChatGPT 新闻编辑审核

请模拟专业新闻编辑逐条审核。只依据输入标题、摘要、来源、时间和链接；信息不足时降低 confidence，不要编造背景。重要性不是标题党程度，也不是媒体热度。

## 评分标准（0–100）
- 90–100：全球系统性影响、战争重大升级、全球宏观/金融冲击、重大政策转折或已证实的突破。
- 80–89：对一个大国、关键产业或大量人口有重大影响。
- 70–79：明确的重要政策、市场、科技或安全事件。
- 60–69：有一定影响，值得持续关注。
- 25–59：一般动态、局部事件或普通研究论文。
- 普通学术论文如无临床/监管验证、规模化部署或强证据突破，通常不应超过55。
- 不要把“涉及/面临审查/可能暴露的资产规模”误写成“已缴税金额/实际损失”。
- 同一事件的多条报道应有相近评分，并赋予相同或高度一致的 event_key。
- 结合影响、证据强度、时效性和独特性评分；避免把国家重要性直接等同于单条新闻的重要性。

## 输出要求
只返回可解析 JSON，不要 Markdown 代码围栏或额外说明：
{"schema_version":1,"items":[{"id":"必须原样保留输入id","title_zh":"准确简体中文标题","score":0,"confidence":0.0,"reason_zh":"不超过45字，解释影响及证据边界","event_key":"简短稳定的事件归类键","decision":"keep|deprioritize","facts_to_verify":["最多2条待核实信息"]}]}

必须为输入中的每个 id 输出一条结果。不要删除或改写 id。标题应忠实保留人物、数字、归因和不确定性。不要将资产规模翻译成税额。证据不足时降低 confidence 并指出待核实事实。

## 待审核新闻 JSON
"""
    prompt += json.dumps(pack, ensure_ascii=False, indent=2)
    (OUT / "chatgpt_review_prompt.md").write_text(prompt + "\n", encoding="utf-8")
    print(f"Prepared {len(items)} review candidates.")
    print(f"Prompt: {OUT / 'chatgpt_review_prompt.md'}")
    print(f"Input JSON: {OUT / 'chatgpt_review_input.json'}")

if __name__ == "__main__":
    main()
