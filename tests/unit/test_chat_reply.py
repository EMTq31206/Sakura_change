from __future__ import annotations

from app.llm.chat_reply import (
    DEFAULT_TONE,
    ChatSegment,
    parse_chat_reply,
    parse_chat_reply_result,
)


def test_parse_segments_normal_ja_zh_pair_passes() -> None:
    """正常的台词段（ja 有日文、zh 有中文）应通过，不触发重试。"""
    result = parse_chat_reply_result(
        '{"segments":[{"ja":"好きだ","zh":"我喜欢你","tone":"害羞","portrait":"害羞脸红"}]}'
    )
    assert result.ok is True
    assert result.needs_retry is False
    segment = result.reply.segments[0]
    assert segment.text == "好きだ"
    assert segment.translation == "我喜欢你"


def test_parse_segments_narration_only_zh_passes() -> None:
    """叙述段（ja 为空、zh 有中文）应通过。"""
    result = parse_chat_reply_result(
        '{"segments":[{"ja":"","zh":"她轻轻靠近，脸颊泛起红晕。","tone":"中性","portrait":"害羞脸红"}]}'
    )
    assert result.ok is True
    assert result.needs_retry is False
    segment = result.reply.segments[0]
    assert segment.text == ""
    assert "她轻轻靠近" in segment.translation


def test_parse_segments_ja_only_without_zh_triggers_retry() -> None:
    """亲昵场景的典型 bug：台词段只写 ja、zh 为空。

    必须触发 needs_retry，且 zh 使用中文兜底而非显示日语。
    """
    result = parse_chat_reply_result(
        '{"segments":[{"ja":"ダメ、もう我慢できない…","zh":"","tone":"害羞","portrait":"害羞脸红"}]}'
    )
    assert result.ok is False
    assert result.needs_retry is True
    assert result.reason == "language_issue"
    segment = result.reply.segments[0]
    # zh 必须是非空中文兜底，避免字幕回退显示日语。
    assert segment.translation.strip() != ""
    assert segment.translation != segment.text


def test_parse_segments_zh_full_of_kana_triggers_retry() -> None:
    """zh 字段全是日文假名时也应触发重试。"""
    result = parse_chat_reply_result(
        '{"segments":[{"ja":"好きだ","zh":"すきだよ","tone":"害羞","portrait":"害羞脸红"}]}'
    )
    assert result.ok is False
    assert result.needs_retry is True


def test_chat_segment_display_text_zh_falls_back_to_text_only_when_translation_empty() -> None:
    """zh 字幕为空时 display_text 应回退到 text（日文），这是触发重试的根本原因。"""
    segment = ChatSegment(text="日本語のセリフ", translation="")
    # 这正是我们要避免的场景：用户看到日语。
    assert segment.display_text("zh") == "日本語のセリフ"


def test_chat_segment_display_text_zh_uses_translation_when_present() -> None:
    segment = ChatSegment(text="日本語のセリフ", translation="日语台词")
    assert segment.display_text("zh") == "日语台词"
