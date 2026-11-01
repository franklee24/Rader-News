#!/usr/bin/env python3
"""Offline contract tests for no-API ChatGPT review scripts."""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    prep = load_module("scripts/prepare_chatgpt_review.py", "prepare_review")
    sample = {
        "generated_beijing": "2026-11-01T06:00:00+08:00",
        "global_top": [{
            "id": "news-1", "title": "Important policy announcement",
            "url": "https://example.com/news-1", "source": "Example",
            "importance": 72, "summary": "A test summary."
        }],
        "ai_news": [{
            "id": "news-2", "title": "AI research update",
            "url": "https://example.com/news-2", "importance": 50
        }]
    }
    rows = prep.collect(sample)
    assert len(rows) == 2, rows
    assert {x["id"] for x in rows} == {"news-1", "news-2"}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        daily = tmp / "daily.json"
        response = tmp / "response.json"
        daily.write_text(json.dumps({
            "global_top": [{
                "id": "news-1", "title": "Important policy announcement",
                "url": "https://example.com/news-1", "importance": 72
            }],
            "supplement": [{
                "id": "news-1", "title": "Duplicate copy of same story",
                "url": "https://example.com/news-1", "importance": 72
            }],
            "ai_news": []
        }), encoding="utf-8")
        response.write_text(json.dumps({
            "schema_version": 1,
            "items": [
                {"id": "news-1", "title_zh": "重要政策公告", "score": 84,
                 "confidence": 0.9, "reason_zh": "影响范围较大",
                 "event_key": "policy-test", "decision": "keep",
                 "facts_to_verify": []},
                {"id": "unknown", "title_zh": "未知新闻", "score": 99, "confidence": 0.99},
                {"id": "news-1", "title_zh": "低置信度新闻", "score": 90, "confidence": 0.2}
            ]
        }), encoding="utf-8")
        cmd = [sys.executable, str(ROOT / "scripts/apply_chatgpt_review.py"),
               "--daily", str(daily), "--response", str(response), "--dry-run"]
        dry = subprocess.run(cmd, check=True, capture_output=True, text=True)
        assert "1 valid results, 2 skipped" in dry.stdout, dry.stdout
        original = json.loads(daily.read_text(encoding="utf-8"))
        assert original["global_top"][0]["importance"] == 72
        cmd.remove("--dry-run")
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        updated = json.loads(daily.read_text(encoding="utf-8"))
        assert updated["global_top"][0]["importance"] == 84
        assert updated["supplement"][0]["importance"] == 84
        assert updated["global_top"][0]["title_zh"] == "重要政策公告"
        assert updated["global_top"][0]["rule_importance"] == 72
        assert updated["ai_editorial"]["reviewed_count"] == 1
    print("PASS: candidate export, ID validation, confidence gate, dry-run, duplicate surfaces and write-back")

if __name__ == "__main__":
    main()
