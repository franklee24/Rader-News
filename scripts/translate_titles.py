#!/usr/bin/env python3
# Translate English-only news titles to Simplified Chinese for display.
# Keeps the original title unchanged and stores the translation in title_zh.
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from urllib.request import Request, urlopen
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "data/daily.json"
TIMEOUT = 12
WORKERS = 6


def looks_english(text):
    s = str(text or "").strip()
    if not s or re.search(r"[\u3400-\u9fff]", s):
        return False
    letters = len(re.findall(r"[A-Za-z]", s))
    return letters >= 8 and letters / max(1, len(re.sub(r"\s+", "", s))) >= 0.45


def translate(title):
    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto"
        "&tl=zh-CN&dt=t&q=" + quote(title, safe="")
    )
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; LeidaNews/20)"})
    with urlopen(req, timeout=TIMEOUT) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
    parts = payload[0] if isinstance(payload, list) else []
    result = "".join(p[0] for p in parts if isinstance(p, list) and p and p[0])
    return re.sub(r"\s+", " ", result).strip()


def main():
    d = json.loads(DAILY.read_text(encoding="utf-8"))
    events = []
    for tier in d.get("tiers", {}).values():
        for country in tier.values():
            events.extend(country.get("events", []))
    events.extend(d.get("supplement", []))

    targets = [e for e in events if looks_english(e.get("title")) and not e.get("title_zh")]
    ok = failed = 0
    cache = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(translate, e["title"]): e for e in targets}
        for fut in as_completed(futures):
            e = futures[fut]
            try:
                zh = fut.result()
                if zh:
                    cache[e["title"]] = zh
                    ok += 1
            except Exception as exc:
                failed += 1
                print("TRANSLATE FAILED:", e.get("title", "")[:100], str(exc)[:120])

    for e in events:
        if e.get("title") in cache:
            e["title_zh"] = cache[e["title"]]

    d.setdefault("translation", {})
    d["translation"].update({
        "language": "zh-CN",
        "field": "title_zh",
        "translated": ok,
        "failed": failed,
        "note": "仅翻译英文标题；原始 title 保留不变。"
    })
    DAILY.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TITLE TRANSLATION:", ok, "translated;", failed, "failed")


if __name__ == "__main__":
    main()
