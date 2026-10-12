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

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "data/daily.json"
TIMEOUT = 5
WORKERS = 8
RATE_LOCK = threading.Lock()
NEXT_REQUEST_AT = 0.0
GOOGLE_BLOCKED = threading.Event()
_ARGOS_TRANSLATOR = None


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
    # Reject obvious fragments returned as if they were complete translations.
    title_words = max(1, len(re.findall(r"\b[A-Za-z0-9]+\b", title)))
    result_words = len(re.findall(r"\b[A-Za-z0-9]+\b", result))
    han_chars = len(re.findall("[一-鿿]", result))
    if title_words >= 8 and result_words < max(2, round(title_words * 0.28)) and han_chars < max(7, round(len(title) * 0.12)):
        return False
    if len(result) < min(8, max(1, round(len(title) * 0.18))):
        return False
    return True


def translate(title):
    errors = []
    # Try multiple providers only when the previous provider fails; keep the full-title sweep within the scheduled runner window.
    for fn in (google_translate, google_translate_web, mymemory_translate, argos_translate):
        try:
            result = fn(title)
            if translation_is_usable(title, result):
                return result
            errors.append(fn.__name__ + ": returned an incomplete Chinese translation")
        except Exception as exc:
            errors.append(fn.__name__ + ": " + str(exc)[:100])
    raise RuntimeError("; ".join(errors[-3:]) or "no translation returned")

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
        if looks_english(title) and not translation_is_usable(title, e.get("title_zh", "")):
            targets_by_title.setdefault(title, e)
    targets = list(targets_by_title.values())
    print("Translation request budget:", len(targets), "unique English headlines; all visible sections included.")
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

    remaining = [e.get("title", "") for e in events if looks_english(e.get("title")) and not translation_is_usable(e.get("title", ""), e.get("title_zh", ""))]
    d.setdefault("translation", {})
    d["translation"].update({
        "language": "zh-CN",
        "field": "title_zh",
        "translated": ok,
        "failed": failed,
        "remaining_english": len(remaining),
        "degraded": bool(remaining),
        "note": "覆盖国家梯队、GLOBAL TOP、全球补充及 AI/LLM；原始 title 保留；全量翻译英文标题，翻译不完整时阻止本次发布。并发与请求间隔已优化，避免长时间占用自动更新任务。"
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
