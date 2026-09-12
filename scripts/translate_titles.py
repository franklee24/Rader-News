#!/usr/bin/env python3
# Translate English-only news titles to Simplified Chinese for display.
# Keeps the original title unchanged and stores the translation in title_zh.
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from urllib.request import Request, urlopen
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "data/daily.json"
TIMEOUT = 15
WORKERS = 6


def looks_english(text):
    s = str(text or "").strip()
    if not s or re.search(r"[\u3400-\u9fff]", s):
        return False
    letters = len(re.findall(r"[A-Za-z]", s))
    return letters >= 8 and letters / max(1, len(re.sub(r"\s+", "", s))) >= 0.45


def google_translate(title):
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


def mymemory_translate(title):
    # Free fallback. This is deliberately second-choice so Google remains the primary translator.
    url = (
        "https://api.mymemory.translated.net/get?q=" + quote(title, safe="")
        + "&langpair=en|zh-CN"
    )
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; LeidaNews/20)"})
    with urlopen(req, timeout=TIMEOUT) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
    result = ((payload.get("responseData") or {}).get("translatedText") or "").strip()
    # Ignore the service's unchanged English fallback.
    if result and re.search(r"[\u3400-\u9fff]", result):
        return re.sub(r"\s+", " ", result).strip()
    return ""


def translate(title):
    errors = []
    for fn in (google_translate, mymemory_translate):
        try:
            result = fn(title)
            if result:
                return result
        except Exception as exc:
            errors.append(str(exc)[:120])
    raise RuntimeError("; ".join(errors) or "no translation returned")


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
    errors = []
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
                errors.append({"title": e.get("title", "")[:160], "error": str(exc)[:300]})

    for e in events:
        if e.get("title") in cache:
            e["title_zh"] = cache[e["title"]]

    remaining = [e.get("title", "") for e in events if looks_english(e.get("title")) and not e.get("title_zh")]
    d.setdefault("translation", {})
    d["translation"].update({
        "language": "zh-CN",
        "field": "title_zh",
        "translated": ok,
        "failed": failed,
        "remaining_english": len(remaining),
        "note": "仅翻译英文标题；原始 title 保留不变；Google Translate 优先，MyMemory 备用。"
    })
    DAILY.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TITLE TRANSLATION:", ok, "translated;", failed, "failed;", len(remaining), "remaining English")
    if remaining:
        print("UNTRANSLATED:", " | ".join(remaining[:20]))
        raise SystemExit("TRANSLATION QUALITY GATE FAILED")


if __name__ == "__main__":
    main()
