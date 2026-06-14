from __future__ import annotations

from typing import Any


MAX_MODEL_CONTEXT_MESSAGES = 24
MAX_MODEL_CONTEXT_CHARS = 40_000

# 用于检测复读的相似度阈值：Jaccard 字符重叠比例 >= 此值视为重复。
DUPLICATE_ASSISTANT_SIMILARITY_THRESHOLD = 0.6


def trim_messages_for_model(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """保留最近上下文，并用字符预算兜底限制入模历史体积。

    在裁剪前先做一次末尾 assistant 复读去重：若历史末尾出现多条
    role=assistant 且内容高度相似的消息，只保留最后一条。这是对
    “模型自身重复输出”和“历史已被污染”的双重保险。
    """
    deduped = _drop_trailing_duplicate_assistant_messages(messages)
    recent = list(deduped[-MAX_MODEL_CONTEXT_MESSAGES:])
    while len(recent) > 1 and _estimate_messages_chars(recent) > MAX_MODEL_CONTEXT_CHARS:
        recent.pop(0)
    return recent


def _drop_trailing_duplicate_assistant_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """删除末尾连续出现的高度相似 assistant 消息，只保留最后一条。

    只处理末尾连续的 assistant 段：只要中间夹了 user/system/tool 消息就停止。
    这样不会误删跨轮次的合理重复（比如用户重复问同一问题）。
    """
    if len(messages) < 2:
        return messages

    # 从末尾向前找到最后一条非 assistant 消息的位置。
    last_non_assistant_index = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        if str(messages[index].get("role", "")) != "assistant":
            last_non_assistant_index = index + 1
            break
    else:
        last_non_assistant_index = 0

    tail = messages[last_non_assistant_index:]
    if len(tail) < 2:
        return messages

    kept_tail = _dedupe_similar_assistant_tail(tail)
    if len(kept_tail) == len(tail):
        return messages
    return [*messages[:last_non_assistant_index], *kept_tail]


def _dedupe_similar_assistant_tail(tail: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对末尾连续 assistant 段做相似度去重，保留最后一条。"""
    kept: list[dict[str, Any]] = []
    for message in tail:
        if kept and _is_similar_assistant_message(message, kept[-1]):
            # 与上一条高度相似，替换上一条（保留更新的版本）。
            kept[-1] = message
            continue
        kept.append(message)
    return kept


def _is_similar_assistant_message(a: dict[str, Any], b: dict[str, Any]) -> bool:
    text_a = _normalize_text(a.get("content", ""))
    text_b = _normalize_text(b.get("content", ""))
    if not text_a or not text_b:
        return False
    # 完全相同直接判为重复。
    if text_a == text_b:
        return True
    # 短文本要求严格相等，避免误伤。
    if len(text_a) < 12 or len(text_b) < 12:
        return False
    return _jaccard_similarity(text_a, text_b) >= DUPLICATE_ASSISTANT_SIMILARITY_THRESHOLD


def _normalize_text(value: Any) -> str:
    if isinstance(value, list):
        parts = [
            part.get("text", "")
            for part in value
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        text = " ".join(str(part) for part in parts)
    else:
        text = str(value)
    return " ".join(text.split()).strip()


def _jaccard_similarity(a: str, b: str) -> float:
    """字符级 Jaccard 相似度，适合中日混合短文本。"""
    set_a = set(a)
    set_b = set(b)
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _estimate_messages_chars(messages: list[dict[str, Any]]) -> int:
    return sum(len(str(message.get("content", ""))) for message in messages)
