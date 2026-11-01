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
        "Dartmouth provost resigns following accusations he used AI to write his own statement - The New York Times":
            "《纽约时报》：达特茅斯学院教务长因被指使用 AI 撰写自己的声明而辞职",
        "Rubio says U.S. yet to decide on new Iran strikes - Financial Times":
            "《金融时报》：鲁比奥表示，美国尚未决定是否对伊朗发动新一轮打击",
        "Maria Vorontsova, Vladimir Putin's daughter, leads fight against aging - Financial Times":
            "《金融时报》：普京之女玛丽亚·沃龙佐娃参与抗衰老研究",
        "Bond investors sit out ‘most consequential’ US midterm elections in years - Financial Times":
            "《金融时报》：债券投资者对这场被称为多年来最重要的美国中期选举持观望态度",
        "Video: Opinion | What We’re Watching For on Election Night - The New York Times":
            "《纽约时报》视频观点：美国选举之夜有哪些值得关注的看点",
        "Wall Street Journal AI Exclusive | Elizabeth Warren Demands Answers From Anthropic Over “Existential Risk” Responses - WSJ":
            "《华尔街日报》独家：伊丽莎白·沃伦要求 Anthropic 解释其对“生存性风险”问题的回应",
    }
    for title, expected in cases.items():
        actual = translator.translate(title)
        assert actual == expected, f"manual translation mismatch for {title!r}: {actual!r}"
        assert translator.translation_is_usable(title, actual), f"manual translation rejected: {title!r}"
    for title, translated in translator.MANUAL_TRANSLATIONS.items():
        assert translator.translation_is_usable(title, translated), f"curated translation failed quality checks: {title!r}"

    stale = {
        "title": "AI agents free up CEOs’ time to think ahead - Financial Times",
        "title_zh": "AI特工腾出时间让首席执行官提前思考",
    }
    duplicate = dict(stale)
    applied = translator.apply_curated_translations([stale, duplicate])
    assert applied == 1, "translation metadata should count unique titles, not duplicate surfaces"
    assert stale["title_zh"] == cases[stale["title"]], "curated override did not replace stale translation"
    assert duplicate["title_zh"] == cases[duplicate["title"]], "curated override must update duplicate surfaces too"

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
