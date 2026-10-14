#!/usr/bin/env python3
"""Regression tests for high-priority Chinese political-investigation coverage."""
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
build = runpy.run_path(str(ROOT / "scripts" / "build_daily.py"))
scoring = runpy.run_path(str(ROOT / "scripts" / "score_importance.py"))

headline = "重庆市委原副书记、市政府原市长黄奇帆接受中央纪委国家监委纪律审查和监察调查"
fixture = (
    '<html><li><a href="/scdcn/zggb/zjsc/202610/t20261013_516561.html">'
    + headline
    + '</a><span>2026-10-13</span></li></html>'
).encode("utf-8")
items = build["parse_ccdi_listing"](fixture, "CCDI Official investigations")
assert len(items) == 1, f"CCDI listing parser failed: {items!r}"
assert items[0]["title"] == headline
assert items[0]["published_at"].startswith("2026-10-13")
assert build["is_china_related"]({"title": headline})
assert build["is_major_china_investigation"](items[0])

event = {
    "id": "regression-huang-qifan",
    "title": headline,
    "title_zh": headline,
    "source": "CCDI Official investigations",
    "source_names": ["CCDI Official investigations"],
    "sources": [{"source": "CCDI Official investigations", "link": items[0]["link"]}],
    "source_count": 1,
    "source_authority": 99,
    "event_country": "中国",
    "category": "政治",
    "published_at": "2026-10-13T00:00:00+00:00",
    "importance": 96,
}
scored = scoring["score"](dict(event))
assert scored["importance"] >= 92, f"priority score too low: {scored['importance']}"
assert scored["importance_level"] == "国家重大"
ordinary = [
    {"id": f"ordinary-{i}", "title": f"普通中国新闻 {i}", "source_authority": 95,
     "importance": 80-i, "published_at": f"2026-10-14T0{i%9}:00:00+00:00"}
    for i in range(12)
]
ranked = build["rank_china_events"](ordinary + [event], target_max=20)
assert ranked and ranked[0]["id"] == event["id"], "priority investigation did not rank first"
assert any(e["id"] == event["id"] for e in ranked), "priority investigation was dropped from China section"
print("China investigation regression tests passed: discovery, classification, scoring, and ranking.")
