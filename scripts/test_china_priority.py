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

# Search results must identify a senior role, not merely mention an investigation.
snippet_only = {
    "title": "某市某局干部李某接受审查调查",
    "description": "李某曾任某省省长，相关调查正在进行",
    "source": "Official China investigations search",
}
assert build["is_major_china_investigation"](snippet_only), "senior role in search snippet was missed"
ordinary_investigation = {
    "title": "某县普通科级干部接受审查调查",
    "description": "有关部门发布调查通报",
    "source": "Official China investigations search",
}
assert not build["is_major_china_investigation"](ordinary_investigation), "ordinary investigation was incorrectly elevated"

# A second senior-official investigation proves the rule is event-based, not name-specific.
generic_headline = "广东省人大常委会党组成员、副主任张硕辅接受中央纪委国家监委纪律审查和监察调查"
generic = {
    "title": generic_headline,
    "source": "Official China investigations search",
    "source_names": ["Official China investigations search"],
    "sources": [{"source": "Official China investigations search"}],
    "source_authority": 97,
    "category": "政治",
    "published_at": "2026-10-08T00:00:00+00:00",
    "event_country": "中国",
}
assert build["is_major_china_investigation"](generic)
generic_score = scoring["score"](dict(generic))["importance"]
assert generic_score < 92, f"generic senior-official investigation was forced into global-top score: {generic_score}"

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
