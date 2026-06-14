from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.llm.chinese_text import to_simplified_chinese

DEFAULT_TONE = "中性"
SAFE_PARSE_FAILURE_TEXT = "返答の形が少し崩れたみたい。もう一度整理するね。"
SAFE_PARSE_FAILURE_TRANSLATION = "回复格式有点乱，我重新整理一下。"
SAFE_LANGUAGE_FALLBACK_TEXT = "うまく日本語にできなかったみたい。もう一度言い直すね。"


@dataclass(frozen=True, init=False)
class ChatSegment:
    text: str
    tone: str = DEFAULT_TONE
    translation: str = ""
    portrait: str = ""

    def __init__(
        self,
        text: str = "",
        tone: str = DEFAULT_TONE,
        translation: str = "",
        portrait: str = "",
        *,
        ja: str | None = None,
        zh: str | None = None,
    ) -> None:
        """兼容旧测试/调用点中的 ja、zh 命名参数。"""
        if ja is not None and not text:
            text = ja
        if zh is not None and not translation:
            translation = zh
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "tone", tone)
        object.__setattr__(self, "translation", to_simplified_chinese(translation))
        object.__setattr__(self, "portrait", portrait)

    def display_text(self, subtitle_language: str) -> str:
        """按字幕语言返回气泡显示文本；缺少译文时回退日文原文。"""
        if subtitle_language == "zh" and self.translation.strip():
            return self.translation.strip()
        return self.text


@dataclass(frozen=True)
class ChatReply:
    segments: list[ChatSegment]

    @property
    def text(self) -> str:
        return "\n".join(segment.text for segment in self.segments if segment.text.strip()).strip()

    @property
    def translation(self) -> str:
        return "\n".join(
            segment.display_text("zh")
            for segment in self.segments
            if segment.display_text("zh").strip()
        ).strip()

    def display_text(self, subtitle_language: str) -> str:
        if subtitle_language == "zh":
            return self.translation or self.text
        return self.text

    @property
    def tone(self) -> str:
        for segment in self.segments:
            if segment.text.strip() and segment.tone.strip():
                return segment.tone.strip()
        return DEFAULT_TONE


@dataclass(frozen=True)
class ChatReplyParseResult:
    reply: ChatReply
    ok: bool
    needs_retry: bool = False
    repaired: bool = False
    reason: str = ""


def parse_chat_reply(content: str) -> ChatReply:
    """解析模型返回；坏结构化回复会降级成安全提示，避免原文泄到 UI。"""
    return parse_chat_reply_result(content).reply


def parse_chat_reply_result(content: str) -> ChatReplyParseResult:
    """解析模型返回并附带诊断，供 AgentRuntime 决定是否重试。"""
    content = content.strip()
    if not content:
        return ChatReplyParseResult(ChatReply([ChatSegment("", DEFAULT_TONE)]), ok=False, needs_retry=True, reason="empty")

    data, repaired = _try_load_json(content)
    if data is None:
        if _looks_structured_reply(content):
            return ChatReplyParseResult(
                _build_safe_parse_failure_reply(),
                ok=False,
                needs_retry=True,
                reason="invalid_json",
            )
        return ChatReplyParseResult(ChatReply([ChatSegment(content, DEFAULT_TONE)]), ok=True)

    if isinstance(data, dict):
        segments, has_language_issue = _parse_segments(data)
        if segments:
            return ChatReplyParseResult(
                ChatReply(segments),
                ok=not has_language_issue,
                needs_retry=has_language_issue,
                repaired=repaired,
                reason="language_issue" if has_language_issue else "",
            )

    return ChatReplyParseResult(
        _build_safe_parse_failure_reply(),
        ok=False,
        needs_retry=True,
        repaired=repaired,
        reason="missing_segments",
    )


def _parse_segments(data: dict[str, Any]) -> tuple[list[ChatSegment], bool]:
    raw_segments = data.get("segments")
    if isinstance(raw_segments, list):
        parsed = [_parse_segment(item) for item in raw_segments]
        segments = [segment for segment, _issue in parsed if segment is not None]
        has_language_issue = any(issue for _segment, issue in parsed)
        return segments, has_language_issue

    text = _clean_first_text(data, "ja", "japanese", "reply", "text")
    if text:
        tone = data.get("tone")
        translation = _clean_first_text(data, "zh", "chinese", "translation")
        segment, has_language_issue = _build_segment(text, tone, translation, data.get("portrait"))
        return [segment], has_language_issue

    return [], False


def _parse_segment(item: Any) -> tuple[ChatSegment | None, bool]:
    if isinstance(item, str):
        text = item.strip()
        return (ChatSegment(text, DEFAULT_TONE), False) if text else (None, False)
    if not isinstance(item, dict):
        return None, False

    text = _clean_first_text(item, "ja", "japanese", "text")
    translation = _clean_first_text(item, "zh", "chinese", "translation")
    if not text and not translation:
        return None, False
    if not text:
        # 叙述段：ja 为空、zh 有内容，仅显示不朗读
        # 防御：若 zh 假名占比 > 50%，说明模型误将日文写入了叙述段
        if _kana_ratio(translation) > 0.5:
            return (ChatSegment("", item.get("tone"), "", item.get("portrait")), False)
        return ChatSegment("", item.get("tone"), translation, item.get("portrait")), False
    return _build_segment(text, item.get("tone"), translation, item.get("portrait"))


def _build_segment(text: str, tone: Any, translation: str, portrait: Any) -> tuple[ChatSegment, bool]:
    text = text.strip()
    translation = translation.strip()
    # 只在 ja 明显是中文、zh 明显是日文时交换，避免误判“ 大丈夫 ”这类日语汉字句。
    if text and translation and _looks_chinese(text) and _looks_japanese(translation):
        text, translation = translation, text
        return ChatSegment(text, _clean_tone(tone), translation, _clean_portrait(portrait)), False

    if text and _has_obvious_chinese(text):
        fallback_translation = translation or text
        return (
            ChatSegment(
                SAFE_LANGUAGE_FALLBACK_TEXT,
                _clean_tone(tone),
                fallback_translation,
                _clean_portrait(portrait),
            ),
            True,
        )

    # 台词段（ja 非空）必须有非空简体中文 zh 译文。
    # 亲昵/情感强烈场景下模型常只写 ja 不写 zh，导致中文字幕回退显示日语。
    # 这里把"台词段 zh 缺失或只含日文假名"标记为语言问题，触发一次模型修复重试；
    # 即便修复失败，display_text 也会用中文兜底而非显示日语。
    if text and not _has_valid_chinese_translation(translation):
        return (
            ChatSegment(
                text,
                _clean_tone(tone),
                translation or _chinese_fallback_for_japanese(text),
                _clean_portrait(portrait),
            ),
            True,
        )

    return ChatSegment(text, _clean_tone(tone), translation, _clean_portrait(portrait)), False


def _has_valid_chinese_translation(translation: str) -> bool:
    """判断 zh 译文是否是合格的简体中文（非空、且不全是日文假名/汉字）。"""
    if not translation.strip():
        return False
    # 假名占比过高说明模型把日文写进了 zh。
    if _kana_ratio(translation) > 0.3:
        return False
    return True


def _chinese_fallback_for_japanese(japanese_text: str) -> str:
    """台词段 zh 缺失时的中文兜底，避免字幕显示日语。

    不做真实翻译（翻译是模型的职责，这里已触发重试），只给一句明确提示，
    让用户知道这条台词缺少中文译文，而不是看到看不懂的日语。
    """
    _ = japanese_text  # 仅占位，不展开翻译。
    return "（此句台词缺少中文译文，请稍候）"


def _clean_tone(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return DEFAULT_TONE


def _clean_portrait(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _clean_first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _looks_japanese(value: str) -> bool:
    return any(
        "\u3040" <= char <= "\u30ff" or "\uff66" <= char <= "\uff9f"
        for char in value
    )


def _looks_chinese(value: str) -> bool:
    return _has_obvious_chinese(value) and not _looks_japanese(value)


def _has_obvious_chinese(value: str) -> bool:
    if _looks_japanese(value):
        return False
    chinese_markers = (
        "这个", "那个", "如果", "因为", "所以", "应该", "节点", "换行", "字符串",
        "看看", "可以", "需要", "无法", "错误", "原因", "里面", "直接",
        "我看", "你可以", "是什么", "为什么", "怎么样",
    )
    chinese_punctuation = "，。？！；：、"
    common_chinese_chars = set("我你的是了在有和不这那们把里吗吧呢")
    simplified_only_chars = set("语错该节显这们为会览")
    return any(marker in value for marker in chinese_markers) or any(
        char in chinese_punctuation for char in value
    ) or sum(1 for char in value if char in common_chinese_chars) >= 2 or any(
        char in simplified_only_chars for char in value
    )


def _kana_ratio(value: str) -> float:
    """假名占文本总字符的比例。"""
    total = len(value)
    if total == 0:
        return 0.0
    kana = sum(1 for char in value if "\u3040" <= char <= "\u30ff" or "\uff66" <= char <= "\uff9f")
    return kana / total


def _try_load_json(content: str) -> tuple[Any | None, bool]:
    candidates = [_strip_code_fence(content)]
    extracted = _extract_json_object(candidates[0])
    if extracted and extracted not in candidates:
        candidates.append(extracted)

    for candidate in candidates:
        try:
            return json.loads(candidate), candidate != content
        except json.JSONDecodeError:
            repaired = _escape_unescaped_string_quotes(candidate)
            if repaired != candidate:
                try:
                    return json.loads(repaired), True
                except json.JSONDecodeError:
                    pass
    return None, False


def _strip_code_fence(content: str) -> str:
    lines = content.strip().splitlines()
    if len(lines) >= 3 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return content


def _extract_json_object(content: str) -> str | None:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end <= start:
        return None
    return content[start : end + 1].strip()


def _escape_unescaped_string_quotes(content: str) -> str:
    """修复值字符串中偶发的裸双引号，例如中文说明里的 `""`。"""
    result: list[str] = []
    in_string = False
    escaped = False
    for index, char in enumerate(content):
        if not in_string:
            if char == '"':
                in_string = True
            result.append(char)
            continue

        if escaped:
            escaped = False
            result.append(char)
            continue
        if char == "\\":
            escaped = True
            result.append(char)
            continue
        if char == '"':
            next_non_space = _next_non_space(content, index + 1)
            if next_non_space in {":", ",", "}", "]", ""}:
                in_string = False
                result.append(char)
            else:
                result.append('\\"')
            continue
        result.append(char)
    return "".join(result)


def _next_non_space(content: str, start: int) -> str:
    for char in content[start:]:
        if not char.isspace():
            return char
    return ""


def _looks_structured_reply(content: str) -> bool:
    stripped = _strip_code_fence(content).strip()
    return stripped.startswith("{") or '"segments"' in stripped or "'segments'" in stripped


def _build_safe_parse_failure_reply() -> ChatReply:
    return ChatReply(
        [
            ChatSegment(
                SAFE_PARSE_FAILURE_TEXT,
                DEFAULT_TONE,
                SAFE_PARSE_FAILURE_TRANSLATION,
            )
        ]
    )

