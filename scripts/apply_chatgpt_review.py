#!/usr/bin/env python3
"""Apply manually returned ChatGPT JSON to a daily news JSON, with strict validation."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAILY = ROOT / "data" / "daily.json"
DEFAULT_RESPONSE = ROOT / "data" / "ai_review" / "chatgpt_response.json"

def usable_zh(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return len(value) >= 4 and bool(re.search(r"[\u3400-\u9fff]", value))

def all_events(data):
    rows = []
    for tier in (data.get("tiers") or {}).values():
        for bucket in (tier or {}).values():
            rows.extend((bucket or {}).get("events", []))
    for section in ("global_top", "supplement", "ai_news"):
        rows.extend(data.get(section, []) or [])
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily", type=Path, default=DEFAULT_DAILY)
    parser.add_argument("--response", type=Path, default=DEFAULT_RESPONSE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.daily.exists(): raise SystemExit(f"Daily data not found: {args.daily}")
    if not args.response.exists(): raise SystemExit(f"ChatGPT response not found: {args.response}")
    data = json.loads(args.daily.read_text(encoding="utf-8"))
    response = json.loads(args.response.read_text(encoding="utf-8"))
    if response.get("schema_version") != 1 or not isinstance(response.get("items"), list):
        raise SystemExit("Invalid response: expected schema_version=1 and an items array.")
    lookup = {}
    for row in all_events(data):
        key = str(row.get("id") or row.get("url") or row.get("source_url") or row.get("title") or "")
        if key: lookup[key] = row
    accepted = skipped = 0
    for item in response["items"]:
        if not isinstance(item, dict): skipped += 1; continue
        key = str(item.get("id") or "")
        target = lookup.get(key)
        if target is None:
            skipped += 1
            print(f"Skipped unknown id: {key[:100]}")
            continue
        try:
            score = int(round(float(item.get("score"))))
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0))))
        except (TypeError, ValueError):
            skipped += 1; continue
        if not 0 <= score <= 100 or confidence < 0.55:
            skipped += 1; continue
        title_zh = str(item.get("title_zh") or "").strip()
        if title_zh and not usable_zh(title_zh):
            skipped += 1; continue
        if not args.dry_run:
            target["rule_importance"] = int(target.get("importance") or 0)
            target["importance"] = score
            target["importance_level"] = ("全球重大" if score >= 90 else "国家重大" if score >= 80 else "重要事件" if score >= 70 else "值得关注" if score >= 60 else "一般动态")
            target["importance_model"] = "ChatGPT manual editorial review"
            target["ai_assessment"] = {
                "confidence": round(confidence, 2), "reason_zh": str(item.get("reason_zh") or "")[:120],
                "event_key": str(item.get("event_key") or "")[:100],
                "decision": item.get("decision") if item.get("decision") in ("keep", "deprioritize") else "keep",
                "facts_to_verify": [str(x)[:160] for x in (item.get("facts_to_verify") or [])[:2]],
            }
            if usable_zh(title_zh): target["title_zh"] = title_zh
        accepted += 1
    if args.dry_run:
        print(f"DRY RUN: {accepted} valid results, {skipped} skipped; no files changed.")
        return
    for tier in (data.get("tiers") or {}).values():
        for bucket in (tier or {}).values():
            if isinstance(bucket, dict) and isinstance(bucket.get("events"), list):
                bucket["events"].sort(key=lambda e: (int(e.get("importance") or 0), e.get("published_at") or ""), reverse=True)
    for section in ("global_top", "supplement", "ai_news"):
        if isinstance(data.get(section), list):
            data[section].sort(key=lambda e: (int(e.get("importance") or 0), e.get("published_at") or ""), reverse=True)
    data["ai_editorial"] = {"status": "manual_chatgpt_review", "provider": "ChatGPT conversation (manual handoff; no API)", "reviewed_count": accepted, "skipped_count": skipped, "confidence_threshold": 0.55}
    args.daily.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Applied {accepted} review results; skipped {skipped} invalid/unknown/low-confidence results.")

if __name__ == "__main__":
    main()
