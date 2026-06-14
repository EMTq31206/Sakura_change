from __future__ import annotations

from app.llm.context_trimming import (
    MAX_MODEL_CONTEXT_MESSAGES,
    trim_messages_for_model,
)


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def test_trim_keeps_recent_messages_within_limit() -> None:
    messages = [_msg("user", f"msg {i}") for i in range(40)]
    trimmed = trim_messages_for_model(messages)
    assert len(trimmed) == MAX_MODEL_CONTEXT_MESSAGES
    # 保留最近的，不是最早的。
    assert trimmed[-1]["content"] == "msg 39"


def test_trim_drops_trailing_identical_assistant_messages() -> None:
    """末尾连续相同的 assistant 消息应被去重为一条。"""
    messages = [
        _msg("user", "你好"),
        _msg("assistant", "今天天气不错"),
        _msg("assistant", "今天天气不错"),  # 完全相同
    ]
    trimmed = trim_messages_for_model(messages)
    assert len(trimmed) == 2
    assert trimmed[-1]["content"] == "今天天气不错"


def test_trim_keeps_assistant_messages_separated_by_user() -> None:
    """跨轮次的 assistant 回复不应被误删。"""
    messages = [
        _msg("user", "问题1"),
        _msg("assistant", "回答1"),
        _msg("user", "问题2"),
        _msg("assistant", "回答1"),  # 内容相同但跨了 user，不算复读
    ]
    trimmed = trim_messages_for_model(messages)
    assert len(trimmed) == 4


def test_trim_drops_highly_similar_assistant_messages() -> None:
    """高度相似（Jaccard >= 0.6）的 assistant 消息应去重。"""
    messages = [
        _msg("user", "讲个故事"),
        _msg("assistant", "从前有座山，山里有座庙，庙里有个老和尚在讲故事"),
        _msg("assistant", "从前有座山，山里有座庙，庙里有个老和尚在讲经"),  # 仅末尾几字不同
    ]
    trimmed = trim_messages_for_model(messages)
    assert len(trimmed) == 2


def test_trim_keeps_short_distinct_messages() -> None:
    """短文本要求严格相等，避免误伤。"""
    messages = [
        _msg("user", "你好"),
        _msg("assistant", "你好呀"),
        _msg("assistant", "你也好"),  # 都很短，相似度高但不相同
    ]
    trimmed = trim_messages_for_model(messages)
    # 短文本不触发相似度去重（除非完全相同）。
    assert len(trimmed) == 3


def test_trim_handles_multimodal_content_list() -> None:
    """多模态消息（content 是 list）也能正常去重。"""
    content = [
        {"type": "text", "text": "这是一段很长的描述文字用于测试"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,xxx"}},
    ]
    messages = [
        _msg("user", "看图"),
        {"role": "assistant", "content": content},
        {"role": "assistant", "content": content},
    ]
    trimmed = trim_messages_for_model(messages)
    assert len(trimmed) == 2
