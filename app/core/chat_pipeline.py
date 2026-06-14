from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.agent import AgentEvent, AgentProgress, AgentResult, AgentRuntime, PendingToolAction
from app.agent.character_lore import CharacterLore, get_character_lore
from app.core.debug_log import debug_log, summarize_messages
from app.storage.visual_observation import (
    VisualObservationJob,
    VisualObservationRecord,
    VisualObservationStore,
    replace_images_with_visual_context,
    summarize_visual_observation,
)


ProgressCallback = Callable[[AgentProgress], None]


class ChatPipeline:
    """封装对话运行管线，让 Qt Worker 只保留线程和信号职责。"""

    def __init__(
        self,
        agent_runtime: AgentRuntime,
        visual_observation_store: VisualObservationStore | None = None,
        character_lore: CharacterLore | None = None,
        character_dir: Path | None = None,
    ) -> None:
        self.agent_runtime = agent_runtime
        self.visual_observation_store = visual_observation_store
        self.character_lore = character_lore or (
            get_character_lore(character_dir) if character_dir else None
        )

    def run_user_message(
        self,
        messages: list[dict[str, Any]],
        *,
        visual_observation_jobs: list[VisualObservationJob] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> AgentResult:
        has_screen = bool(visual_observation_jobs)
        vision_client = self.agent_runtime.vision_client

        visual_records = self._record_visual_observations(
            "ChatWorker", visual_observation_jobs or []
        )

        if has_screen and vision_client is not None:
            messages = self._inject_lore(messages)
            api_client = self.agent_runtime.api_client
            self.agent_runtime.api_client = vision_client
            debug_log("ChatPipeline", "屏幕观察→mimo直答", {"images_kept": True})
            try:
                return self.agent_runtime.handle_user_message(
                    messages, progress_callback=progress_callback
                )
            finally:
                self.agent_runtime.api_client = api_client

        if visual_records:
            messages = replace_images_with_visual_context(messages, visual_records)

        messages = self._inject_lore(messages)
        messages = self._inject_visual_system_context(messages, visual_records)

        debug_log(
            "ChatWorker",
            "开始处理用户消息",
            {
                "message_count": len(messages),
                "messages": summarize_messages(messages),
            },
        )
        return self.agent_runtime.handle_user_message(messages, progress_callback=progress_callback)

    def run_confirmed_action(
        self,
        action: PendingToolAction,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> AgentResult:
        debug_log("ChatWorker", "开始处理已确认动作", action.to_dict())
        return self.agent_runtime.handle_confirmed_action(
            action,
            progress_callback=progress_callback,
        )

    def run_cancelled_action(self, action: PendingToolAction) -> AgentResult:
        debug_log("ChatWorker", "开始处理已取消动作", action.to_dict())
        return self.agent_runtime.handle_cancelled_action(action)

    def run_event(
        self,
        event: AgentEvent,
        *,
        visual_observation_jobs: list[VisualObservationJob] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> AgentResult:
        visual_records = self._record_visual_observations("EventWorker", visual_observation_jobs or [])
        if visual_records:
            event = AgentEvent(
                type=event.type,
                payload={
                    **_event_payload_without_images(event.payload),
                    "visual_contexts": [
                        _visual_record_to_event_context(record)
                        for record in visual_records
                    ],
                },
            )
        debug_log(
            "EventWorker",
            "开始处理主动事件",
            {
                "type": event.type,
                "payload": event.payload,
            },
        )
        return self.agent_runtime.handle_event(
            event,
            progress_callback=progress_callback,
        )

    def _record_visual_observations(
        self,
        log_scope: str,
        visual_observation_jobs: list[VisualObservationJob],
    ) -> list[VisualObservationRecord]:
        if self.visual_observation_store is None or not visual_observation_jobs:
            return []
        records: list[VisualObservationRecord] = []
        vision_client = getattr(self.agent_runtime, "vision_client", None)
        for job in visual_observation_jobs:
            record = summarize_visual_observation(vision_client, job)
            records.append(record)
            self.visual_observation_store.append(record)
            debug_log(
                log_scope,
                "视觉观察记录已保存",
                {
                    "visual_id": record.id,
                    "source": record.source,
                    "summary": record.summary,
                    "visible_text_count": len(record.visible_texts),
                    "sensitive_redacted": record.sensitive_redacted,
                },
            )
        return records

    def _inject_lore(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.character_lore is None or not self.character_lore.has_content():
            return messages
        user_text = _extract_last_user_text(messages)
        if not user_text:
            return messages
        # Also search recent conversation context for broader keyword matching
        recent_context = _extract_recent_user_texts(messages, limit=3)
        search_query = recent_context + " " + user_text
        lore_context = self.character_lore.search(search_query, max_sections=5)
        if lore_context:
            messages = list(messages)
            messages.insert(0, {"role": "system", "content": lore_context})
        return messages

    def _inject_visual_system_context(
        self,
        messages: list[dict[str, Any]],
        visual_records: list[VisualObservationRecord],
    ) -> list[dict[str, Any]]:
        if not visual_records:
            return messages
        last = visual_records[-1]
        parts = [
            "【当前屏幕画面】",
            f"摘要：{last.summary}",
        ]
        if last.visual_context:
            parts.append(f"画面布局：{last.visual_context}")
        if last.notable_elements:
            parts.append(f"关键元素：{', '.join(last.notable_elements[:8])}")
        if last.visible_texts:
            parts.append(f"可见文字：{', '.join(last.visible_texts[:5])}")
        context = "\n".join(parts)
        messages = list(messages)
        messages.insert(0, {"role": "system", "content": context})
        return messages


def _extract_last_user_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                return " ".join(texts)
    return ""


def _extract_recent_user_texts(messages: list[dict[str, Any]], limit: int = 3) -> str:
    texts: list[str] = []
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                t = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                texts.append(" ".join(t))
            if len(texts) >= limit:
                break
    return " ".join(reversed(texts))


def _visual_record_to_event_context(record: VisualObservationRecord) -> dict[str, Any]:
    return {
        "visual_id": record.id,
        "source": record.source,
        "created_at": record.created_at,
        "screen_name": record.screen_name,
        "summary": record.summary,
        "visible_texts": record.visible_texts[:12],
        "uncertain_texts": record.uncertain_texts[:6],
        "notable_elements": record.notable_elements[:10],
        "confidence": record.confidence,
        "sensitive_redacted": record.sensitive_redacted,
    }


def _event_payload_without_images(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    screen_context = cleaned.get("screen_context")
    if isinstance(screen_context, dict):
        cleaned["screen_context"] = {
            key: value for key, value in screen_context.items() if key != "data_url"
        }
    screen_contexts = cleaned.get("screen_contexts")
    if isinstance(screen_contexts, list):
        cleaned["screen_contexts"] = [
            {key: value for key, value in item.items() if key != "data_url"}
            if isinstance(item, dict)
            else item
            for item in screen_contexts
        ]
    return cleaned
