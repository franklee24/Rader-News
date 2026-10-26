#!/usr/bin/env python3
"""Regression contract for daily AI/LLM news coverage and shared importance scoring."""
import datetime as dt
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
build = runpy.run_path(str(ROOT / "scripts" / "build_daily.py"))
scoring = runpy.run_path(str(ROOT / "scripts" / "score_importance.py"))

feeds = build["AI_FEEDS"]
feed_names = {feed[0] for feed in feeds}
assert len(feeds) >= 25, f"AI/LLM source pool unexpectedly shrank: {len(feeds)}"
for expected in ("OpenAI News", "Google DeepMind", "Anthropic News Watch",
                 "NVIDIA AI Blog", "Alibaba Qwen", "DeepSeek",
                 "Reuters AI", "Financial Times AI", "TechCrunch AI",
                 "arXiv cs.AI", "arXiv cs.CL"):
    assert expected in feed_names, f"AI/LLM source missing: {expected}"

is_ai_related = build["is_ai_related"]
assert is_ai_related({"title": "OpenAI releases a new reasoning model"})
assert is_ai_related({"title": "New large language model benchmark results"})
assert not is_ai_related({"title": "Local football club wins weekend match",
                          "description": "The coach said AI once helped with training"})

now = dt.datetime.now(dt.timezone.utc)
def fixture(title, category, published_at, country="AI / LLM"):
    return {
        "title": title, "description": title, "category": category,
        "event_country": country, "published_at": published_at,
        "source_authority": 80, "source_count": 2,
        "sources": [{"source": "Publisher A"}, {"source": "Publisher B"}],
    }

fresh = fixture("Major AI model release changes enterprise capabilities",
                "AI/LLM", now.isoformat())
stale = fixture("Major AI model release changes enterprise capabilities",
                "AI/LLM", (now - dt.timedelta(days=5)).isoformat())
fresh_score = scoring["score"](dict(fresh))["importance"]
stale_score = scoring["score"](dict(stale))["importance"]
assert fresh_score > stale_score, (
    f"fresh AI news must outrank an otherwise identical stale item: fresh={fresh_score}, stale={stale_score}"
)
assert 0 <= fresh_score <= 100
assert scoring["score"](dict(fresh))["importance_model"] == scoring["score"](
    dict(fixture("Major central bank changes interest-rate policy", "宏观经济", now.isoformat()))
)["importance_model"], "AI and mainstream news must use the same importance model"

print(f"AI/LLM regression tests passed: {len(feeds)} configured feeds; shared scoring and freshness verified.")
