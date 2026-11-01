#!/usr/bin/env python3
"""Regression tests for high-impact headline translation quality."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import translate_titles as translator


def main():
    cases = {
        "Proposal: configure fixed effort for the Claude Code subagent · deepseek-ai deepseek-harness · Discussion #11701 - GitHub":
            "开发者提议为 Claude Code 子代理配置固定推理力度",
        "AI agents free up CEOs’ time to think ahead - Financial Times":
            "《金融时报》：AI 智能体让 CEO 腾出时间思考长期战略",
        "OpenAI slashes funding target by $10bn as tech anxieties mount - Financial Times":
            "《金融时报》：科技行业担忧升温之际，OpenAI 将融资目标下调 100 亿美元",
        "GARDEN: Generalist Autonomous Reward Design Through Evidence Navigation for Cooperative Multi-Agent Reinforcement Learning":
            "GARDEN：通过证据导航实现通用自主奖励设计，促进多智能体协同强化学习",
    }
    for title, expected in cases.items():
        actual = translator.translate(title)
        assert actual == expected, f"manual translation mismatch for {title!r}: {actual!r}"
        assert translator.translation_is_usable(title, actual), f"manual translation rejected: {title!r}"

    stale = {
        "title": "AI agents free up CEOs’ time to think ahead - Financial Times",
        "title_zh": "AI特工腾出时间让首席执行官提前思考",
    }
    applied = translator.apply_curated_translations([stale])
    assert applied == 1, "curated translation should replace an existing bad translation"
    assert stale["title_zh"] == cases[stale["title"]], "curated override did not replace stale translation"

    assert not translator.translation_is_usable(
        "Proposal: configure fixed effort for the Claude Code subagent",
        "建议为克洛德密码子代理配置固定推理力度",
    ), "Claude Code mistranslation should be rejected"
    assert not translator.translation_is_usable(
        "AI agents free up CEOs’ time to think ahead",
        "AI特工腾出时间让首席执行官提前思考",
    ), "AI agents mistranslation should be rejected"
    assert not translator.translation_is_usable(
        "Anthropic files for an IPO",
        "人类学公司提交 IPO 申请",
    ), "Anthropic mistranslation should be rejected"
    assert not translator.translation_is_usable(
        "OpenAI slashes funding target",
        "开放人工智能下调融资目标",
    ), "OpenAI brand mistranslation should be rejected"
    print(f"translation quality tests passed: {len(cases)} curated titles and 4 mistranslation guards")


if __name__ == "__main__":
    main()
