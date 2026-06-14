from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.debug_log import debug_log

VISUAL_OBSERVATION_RECENT_MINUTES = 10
VISUAL_OBSERVATION_RETENTION_DAYS = 7
VISUAL_OBSERVATION_RETENTION_LIMIT = 200

VISUAL_CONTEXT_KEYWORDS = (
    "刚才",
    "截图",
    "画面",
    "屏幕",
    "台词",
    "文字",
    "看到了什么",
    "看到什么",
    "写了什么",
    "说了什么",
    "那句话",
    "那段话",
)

_SENSITIVE_PATTERNS = (
    re.compile(r"\b(api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=：]\s*\S+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    re.compile(r"\b\d{17}[\dXx]\b"),
    re.compile(r"(密码|口令|密钥|令牌|银行卡|信用卡|身份证)\s*[:：]\s*\S+"),
)


@dataclass(frozen=True)
class VisualObservationRecord:
    """一条可追问的视觉观察记录；不保存原始截图。"""

    id: str
    created_at: str
    source: str
    user_text: str
    screen_name: str
    width: int
    height: int
    summary: str
    visual_context: str = ""
    visible_texts: list[str] = field(default_factory=list)
    uncertain_texts: list[str] = field(default_factory=list)
    notable_elements: list[str] = field(default_factory=list)
    confidence: float = 0.0
    sensitive_redacted: bool = False


@dataclass(frozen=True)
class VisualObservationJob:
    """交给后台 Worker 生成视觉摘要的任务。"""

    id: str
    source: str
    user_text: str
    observation: Any | None = None
    screen_contexts: list[dict[str, Any]] | None = None


class VisualObservationStore:
    """按角色保存短期视觉观察记录。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: VisualObservationRecord) -> None:
        redacted_record, _ = _redact_record_dict(asdict(record))
        records = [*self._load_raw_records(), redacted_record]
        records = self._prune(records)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as file:
            for item in records:
                file.write(json.dumps(item, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 3, since_minutes: int | None = None) -> list[VisualObservationRecord]:
        threshold = None
        if since_minutes is not None:
            threshold = datetime.now().astimezone() - timedelta(minutes=since_minutes)

        records: list[VisualObservationRecord] = []
        for item in reversed(self._load_raw_records()):
            record = _record_from_dict(item)
            if record is None:
                continue
            if threshold is not None:
                created_at = _parse_iso(record.created_at)
                if created_at is None or created_at < threshold:
                    continue
            records.append(record)
            if len(records) >= limit:
                break
        return records

    def search(self, keyword: str, limit: int = 3) -> list[VisualObservationRecord]:
        normalized = keyword.strip().casefold()
        if not normalized:
            return self.recent(limit=limit)

        records: list[VisualObservationRecord] = []
        for item in reversed(self._load_raw_records()):
            record = _record_from_dict(item)
            if record is None:
                continue
            haystack = "\n".join(
                [
                    record.summary,
                    *record.visible_texts,
                    *record.uncertain_texts,
                    *record.notable_elements,
                ]
            ).casefold()
            if normalized not in haystack:
                continue
            records.append(record)
            if len(records) >= limit:
                break
        return records

    def _load_raw_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []

        records: list[dict[str, Any]] = []
        for raw_line in self.path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                records.append(_redact_record_dict(data)[0])
        return records

    def _prune(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        threshold = datetime.now().astimezone() - timedelta(days=VISUAL_OBSERVATION_RETENTION_DAYS)
        kept: list[dict[str, Any]] = []
        for item in records:
            created_at = _parse_iso(str(item.get("created_at", "")))
            if created_at is not None and created_at < threshold:
                continue
            kept.append(item)
        return kept[-VISUAL_OBSERVATION_RETENTION_LIMIT:]


def generate_visual_observation_id() -> str:
    return f"vis_{uuid.uuid4().hex[:10]}"


def summarize_visual_observation(
    api_client: Any,
    job: VisualObservationJob,
) -> VisualObservationRecord:
    """调用视觉模型生成结构化观察；失败时返回可追踪的最小记录。"""
    metadata = _job_metadata(job)
    fallback = _fallback_record(job, metadata, "视觉摘要生成失败。")
    image_parts = _job_image_parts(job)
    if not image_parts:
        return fallback
    if api_client is None:
        return _fallback_record(job, metadata, "视觉摘要生成失败：独立视觉模型未启用。")

    started_at = time.perf_counter()
    try:
        complete_vision = getattr(api_client, "complete_vision_raw", api_client.complete_raw)
        content = complete_vision(
            _build_visual_summary_prompt(),
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": _build_visual_summary_user_text(job, metadata),
                        },
                        *image_parts,
                    ],
                }
            ],
            temperature=0,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        return _fallback_record(job, metadata, f"视觉摘要生成失败：{exc}")

    parsed = _load_json_object(content)
    if parsed is None:
        return _fallback_record(job, metadata, "视觉摘要返回格式无法解析。")

    record, redacted = _record_from_summary(job, metadata, parsed)
    debug_log(
        "Vision",
        "视觉摘要完成",
        {
            "source": job.source,
            "image_count": len(image_parts),
            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        },
    )
    if redacted:
        return VisualObservationRecord(
            **{
                **asdict(record),
                "sensitive_redacted": True,
            }
        )
    return record


def replace_images_with_visual_context(
    messages: list[dict[str, Any]],
    records: list[VisualObservationRecord],
) -> list[dict[str, Any]]:
    """移除原始图片，并把视觉模型的结构化结果作为文本上下文注入。"""
    stripped: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            stripped.append(message)
            continue
        text_parts = [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        stripped.append({**message, "content": "\n".join(text_parts).strip()})
    if not records:
        return stripped
    context = build_visual_context_message("当前请求附带的屏幕图片", records)
    return [context, *stripped] if context is not None else stripped


def summarize_image_data_urls(
    api_client: Any,
    image_urls: list[str],
    *,
    source: str = "tool_screenshot",
) -> str:
    """将工具返回的截图转成可供主模型使用的纯文本观察。"""
    valid_urls = [
        url for url in image_urls
        if isinstance(url, str) and url.startswith("data:image/")
    ][:3]
    if not valid_urls:
        return ""
    job = VisualObservationJob(
        id=generate_visual_observation_id(),
        source=source,
        user_text="工具返回截图",
        screen_contexts=[
            {
                "data_url": url,
                "screen_name": source,
                "width": 0,
                "height": 0,
                "captured_at": _now_iso(),
            }
            for url in valid_urls
        ],
    )
    record = summarize_visual_observation(api_client, job)
    if record.confidence <= 0 or record.summary.startswith("视觉摘要生成失败"):
        return f"截图视觉解析失败：{record.summary}"
    return "\n".join(
        [
            f"截图摘要：{record.summary}",
            f"可见文字：{_format_list(record.visible_texts)}",
            f"关键元素：{_format_list(record.notable_elements)}",
            f"视觉置信度：{record.confidence:.2f}",
        ]
    )


def build_visual_context_message(
    user_text: str,
    records: list[VisualObservationRecord],
) -> dict[str, str] | None:
    if not records:
        return None

    lines = [
        "以下是最近截图/屏幕观察提炼出的短期视觉记忆。它们是纯文本摘要，不包含原图；回答用户关于刚才截图、画面、台词或可见文字的问题时，应优先依据这些记录，不要臆造看不清的内容。",
        f"用户当前问题：{user_text.strip()}",
    ]
    for record in records:
        lines.append(
            "\n".join(
                [
                    f"- visual_id={record.id} source={record.source} time={record.created_at}",
                    f"  屏幕：{record.screen_name}，尺寸：{record.width}x{record.height}，置信度：{record.confidence:.2f}",
                    f"  摘要：{record.summary or '无摘要'}",
                    f"  画面布局：{record.visual_context or '未知'}",
                    f"  可见文字/台词：{_format_list(record.visible_texts)}",
                    f"  不确定文字：{_format_list(record.uncertain_texts)}",
                    f"  关键元素：{_format_list(record.notable_elements)}",
                ]
            )
        )
    return {"role": "system", "content": "\n".join(lines)}


def should_inject_visual_context(user_text: str) -> bool:
    normalized = "".join(user_text.split()).casefold()
    return any(keyword.casefold() in normalized for keyword in VISUAL_CONTEXT_KEYWORDS)


def _build_visual_summary_prompt() -> str:
    return """
你是桌面 Agent 的视觉观察整理器。你把截图转成结构化视觉记忆，只输出 JSON，不要 Markdown，不要解释。

第一步：理解画面全貌（最重要）
- 当前活跃的是什么应用/窗口？（浏览器、代码编辑器、游戏、视频播放器、聊天、终端、文件管理器、桌面等）
- 画面上有哪些可见的窗口层级？各自位置和大致占比？
- 是什么类型的场景？（写代码、调试、看视频、打游戏、刷网页、聊天、读文档等）
- 画面中是否有图片、视频、头像、图标、表情包、游戏画面、UI 控件等**非文字**视觉元素？尽可能描述它们。
- 整体色彩/明暗/氛围如何？（深色模式编辑器、明亮网页、暗色调游戏画面等）

第二步：提取可见文字（辅助）
- 屏幕里明确可见的文字/台词/字幕/聊天气泡/窗口标题/按钮文字/错误信息/代码片段。
- 遇到 API Key、token、密码、身份证、银行卡等敏感内容，打码为 [REDACTED]。

第三步：只返回如下 JSON：
{
  "summary": "用 3-5 句话描述画面：什么应用、什么内容类型、有哪些视觉元素、用户在做什么",
  "visual_context": "画面布局简述：各个窗口/区域的位置、大小、类型",
  "visible_texts": ["明确可见的文字"],
  "uncertain_texts": ["不确定或部分可见的文字"],
  "notable_elements": ["关键窗口、控件、人物、图标、图片、视频、按钮等"],
  "confidence": 0.0,
  "sensitive_redacted": false
}
""".strip()


def _build_visual_summary_user_text(
    job: VisualObservationJob,
    metadata: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "source": job.source,
            "user_text": job.user_text,
            "screen_name": metadata["screen_name"],
            "width": metadata["width"],
            "height": metadata["height"],
            "captured_at": metadata["captured_at"],
            "screen_context_count": len(job.screen_contexts or []) or 1,
        },
        ensure_ascii=False,
        indent=2,
    )


def _job_image_parts(job: VisualObservationJob) -> list[dict[str, Any]]:
    image_urls: list[str] = []
    if job.observation is not None:
        data_url = getattr(job.observation, "data_url", "")
        if isinstance(data_url, str) and data_url.startswith("data:image/"):
            image_urls.append(data_url)
    for context in job.screen_contexts or []:
        data_url = context.get("data_url")
        if isinstance(data_url, str) and data_url.startswith("data:image/"):
            image_urls.append(data_url)

    return [
        {
            "type": "image_url",
            "image_url": {
                "url": image_url,
                "detail": "high",
            },
        }
        for image_url in image_urls[:3]
    ]


def _job_metadata(job: VisualObservationJob) -> dict[str, Any]:
    if job.observation is not None:
        return {
            "width": int(getattr(job.observation, "width", 0) or 0),
            "height": int(getattr(job.observation, "height", 0) or 0),
            "screen_name": str(getattr(job.observation, "screen_name", "") or "unknown"),
            "captured_at": str(getattr(job.observation, "captured_at", "") or _now_iso()),
        }

    contexts = job.screen_contexts or []
    if contexts:
        first = contexts[0]
        last = contexts[-1]
        return {
            "width": _int_value(last.get("width")),
            "height": _int_value(last.get("height")),
            "screen_name": str(last.get("screen_name") or "unknown"),
            "captured_at": str(first.get("captured_at") or _now_iso()),
        }

    return {
        "width": 0,
        "height": 0,
        "screen_name": "unknown",
        "captured_at": _now_iso(),
    }


def _record_from_summary(
    job: VisualObservationJob,
    metadata: dict[str, Any],
    summary: dict[str, Any],
) -> tuple[VisualObservationRecord, bool]:
    summary_text, summary_redacted = _redact_text(_text_value(summary.get("summary")))
    visual_context, visual_redacted = _redact_text(_text_value(summary.get("visual_context")))
    visible_texts, visible_redacted = _redact_text_list(summary.get("visible_texts"))
    uncertain_texts, uncertain_redacted = _redact_text_list(summary.get("uncertain_texts"))
    notable_elements, notable_redacted = _redact_text_list(summary.get("notable_elements"))
    user_text, user_text_redacted = _redact_text(job.user_text)
    return (
        VisualObservationRecord(
            id=job.id,
            created_at=_now_iso(),
            source=job.source,
            user_text=user_text,
            screen_name=metadata["screen_name"],
            width=metadata["width"],
            height=metadata["height"],
            summary=summary_text,
            visual_context=visual_context,
            visible_texts=visible_texts,
            uncertain_texts=uncertain_texts,
            notable_elements=notable_elements,
            confidence=_confidence_value(summary.get("confidence")),
            sensitive_redacted=bool(summary.get("sensitive_redacted", False)),
        ),
        summary_redacted
        or visible_redacted
        or uncertain_redacted
        or notable_redacted
        or user_text_redacted,
    )


def _fallback_record(
    job: VisualObservationJob,
    metadata: dict[str, Any],
    summary: str,
) -> VisualObservationRecord:
    return VisualObservationRecord(
        id=job.id,
        created_at=_now_iso(),
        source=job.source,
        user_text=_redact_text(job.user_text)[0],
        screen_name=metadata["screen_name"],
        width=metadata["width"],
        height=metadata["height"],
        summary=summary,
        visual_context="",
        visible_texts=[],
        uncertain_texts=[],
        notable_elements=[],
        confidence=0.0,
        sensitive_redacted=False,
    )


def _record_from_dict(data: dict[str, Any]) -> VisualObservationRecord | None:
    try:
        redacted_data, sensitive_redacted = _redact_record_dict(data)
        return VisualObservationRecord(
            id=_text_value(redacted_data.get("id")),
            created_at=_text_value(redacted_data.get("created_at")),
            source=_text_value(redacted_data.get("source")),
            user_text=_text_value(redacted_data.get("user_text")),
            screen_name=_text_value(redacted_data.get("screen_name")),
            width=_int_value(redacted_data.get("width")),
            height=_int_value(redacted_data.get("height")),
            summary=_text_value(redacted_data.get("summary")),
            visible_texts=_string_list(redacted_data.get("visible_texts")),
            uncertain_texts=_string_list(redacted_data.get("uncertain_texts")),
            notable_elements=_string_list(redacted_data.get("notable_elements")),
            confidence=_confidence_value(redacted_data.get("confidence")),
            sensitive_redacted=bool(redacted_data.get("sensitive_redacted", False)) or sensitive_redacted,
        )
    except (TypeError, ValueError):
        return None


def _redact_record_dict(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    redacted = dict(data)
    sensitive_redacted = False
    for key in ("user_text", "summary"):
        redacted[key], changed = _redact_text(_text_value(redacted.get(key)))
        sensitive_redacted = sensitive_redacted or changed
    for key in ("visible_texts", "uncertain_texts", "notable_elements"):
        redacted[key], changed = _redact_text_list(redacted.get(key))
        sensitive_redacted = sensitive_redacted or changed
    if sensitive_redacted:
        redacted["sensitive_redacted"] = True
    redacted.pop("data_url", None)
    redacted.pop("image_url", None)
    return redacted, sensitive_redacted


def _redact_text_list(value: Any) -> tuple[list[str], bool]:
    result: list[str] = []
    changed = False
    for item in _string_list(value):
        redacted, item_changed = _redact_text(item)
        if redacted:
            result.append(redacted)
        changed = changed or item_changed
    return result, changed


def _redact_text(text: str) -> tuple[str, bool]:
    redacted = text
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted, redacted != text


def _load_json_object(content: str) -> dict[str, Any] | None:
    text = content.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _format_list(items: list[str]) -> str:
    return "；".join(item for item in items if item.strip()) or "无"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _text_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _int_value(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _confidence_value(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(1.0, number))


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
