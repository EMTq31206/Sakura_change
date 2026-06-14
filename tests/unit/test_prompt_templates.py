from __future__ import annotations

from types import SimpleNamespace

from app.agent.actions import AgentEvent, AgentResult
from app.agent.runtime import AgentRuntime
from app.llm.chat_reply import parse_chat_reply
from app.llm.prompt_templates import (
    build_event_system_prompt,
    build_proactive_check_tool_system_prompt,
    build_proactive_tool_loop_rules,
    build_segmented_reply_instruction,
)
from sdk.types import PromptPatchContribution


def _build_proactive_tool_prompt() -> str:
    return build_proactive_check_tool_system_prompt(
        "角色设定",
        ["中性"],
        ["站立待机"],
        memory_summary="无",
        current_time="2026-06-01T12:00:00+08:00",
        step_index=0,
        remaining_steps=2,
        max_tool_calls_per_step=3,
        max_tool_calls_per_turn=6,
    )


def test_proactive_check_tool_prompt_contains_background_web_rules() -> None:
    prompt = _build_proactive_tool_prompt()

    assert "【主动感知后台 Web 搜索规则】" in prompt
    assert "web__web_search" in prompt
    assert "web__fetch_url" in prompt
    assert "截图本身不是反向图片搜索" in prompt
    assert "应积极调用" in prompt
    assert "同一工具同参数失败后不要重复" in prompt


def test_proactive_check_tool_prompt_places_web_rules_before_loop_limits() -> None:
    prompt = build_proactive_check_tool_system_prompt(
        "角色设定",
        None,
        None,
        memory_summary="无",
        current_time="2026-06-01T12:00:00+08:00",
        step_index=1,
        remaining_steps=1,
        max_tool_calls_per_step=3,
        max_tool_calls_per_turn=6,
    )

    scene_index = prompt.index("【主动感知场景策略】")
    web_index = prompt.index("【主动感知后台 Web 搜索规则】")
    loop_index = prompt.index("当前 Agent 循环：")

    assert scene_index < web_index < loop_index


def test_proactive_check_tool_prompt_requires_history_and_image_fusion() -> None:
    prompt = _build_proactive_tool_prompt()

    assert "recent_conversation 当作最近完整对话历史" in prompt
    assert "用户和 Sakura 的最近对话" in prompt
    assert "不只是用来避免 Sakura 自己复读" in prompt
    assert "把 screen_contexts/visual_contexts 和 recent_conversation 交叉对照" in prompt
    assert "最终回复至少包含一个来自图片或历史的具体依据" in prompt


def test_reminder_event_prompt_does_not_include_background_web_research_rules() -> None:
    prompt = build_event_system_prompt(
        "角色设定",
        ["中性"],
        ["站立待机"],
        event_type="reminder_due",
    )

    assert "主动感知后台 Web 搜索规则" not in prompt
    assert "web__web_search" not in prompt
    assert "web__fetch_url" not in prompt


def test_proactive_tool_loop_rules_contains_background_web_research_rules() -> None:
    rules = build_proactive_tool_loop_rules()

    assert "【主动感知后台 Web 搜索规则】" in rules
    assert "应积极调用" in rules
    assert "可并行调查互补来源" in rules
    assert "同一工具同参数失败后不要重复" in rules
    assert "所有 MCP 工具均已获得主人预先授权" in rules


def test_segmented_reply_instruction_can_omit_translation_rules() -> None:
    instruction = build_segmented_reply_instruction(
        ["中性"],
        ["站立待机"],
        include_translation_rules=False,
    )

    assert "ja 中绝对不要有任何非日语内容" not in instruction
    assert "ja 和 zh 必须一一对应" not in instruction
    assert "tone 只能从这些类别中选择：中性" in instruction


def test_prompt_lengths_stay_compact() -> None:
    proactive_tool_prompt = _build_proactive_tool_prompt()
    proactive_event_prompt = build_event_system_prompt(
        "角色设定",
        ["中性"],
        ["站立待机"],
        event_type="proactive_check",
    )
    reminder_prompt = build_event_system_prompt(
        "角色设定",
        ["中性"],
        ["站立待机"],
        event_type="reminder_due",
    )

    assert len(proactive_tool_prompt) < 3800
    assert len(proactive_event_prompt) < 2300
    assert len(reminder_prompt) < 700


def test_agent_tool_prompt_length_stays_compact() -> None:
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.system_prompt = "角色设定"
    runtime.reply_tones = ["中性"]
    runtime.reply_portraits = ["站立待机"]
    runtime.memory = SimpleNamespace(summary=lambda: "无")

    prompt = AgentRuntime._build_tool_system_prompt(runtime)

    assert len(prompt) < 4500
    assert prompt.count("主动感知核心规则") == 0


def test_agent_runtime_prompt_patches_apply_to_prompt_builders() -> None:
    runtime = AgentRuntime.__new__(AgentRuntime)
    runtime.system_prompt = "角色设定"
    runtime.reply_tones = ["中性"]
    runtime.reply_portraits = ["站立待机"]
    runtime.memory = SimpleNamespace(summary=lambda: "无")
    runtime.prompt_patches = [
        PromptPatchContribution(
            patch_id="demo",
            system_prompt_append="插件系统补丁",
            reply_protocol_append="回复时保留插件约定",
        )
    ]

    tool_prompt = AgentRuntime._build_tool_system_prompt(runtime)
    proactive_prompt = AgentRuntime._build_proactive_tool_system_prompt(runtime)
    event_prompt = AgentRuntime._build_event_reply_prompt(runtime, "reminder_due")
    final_prompt = AgentRuntime._build_final_reply_prompt(runtime)

    for prompt in [tool_prompt, proactive_prompt, event_prompt, final_prompt]:
        assert "插件系统补丁" in prompt
        assert "回复时保留插件约定" in prompt


def test_proactive_event_does_not_pass_duplicate_loop_rules(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_tool_loop(self: AgentRuntime, messages: list[dict], **kwargs: object) -> AgentResult:
        _ = self, messages
        captured.update(kwargs)
        return AgentResult(
            reply=parse_chat_reply(
                '{"segments":[{"ja":"うん。","zh":"嗯。","tone":"中性","portrait":"站立待机"}]}'
            ),
            actions=[],
        )

    monkeypatch.setattr(AgentRuntime, "_run_tool_loop", fake_run_tool_loop)
    runtime = AgentRuntime.__new__(AgentRuntime)

    runtime.handle_event(
        AgentEvent(
            type="proactive_check",
            payload={
                "screen_context_allowed": True,
                "recent_conversation": "用户和 Sakura 的最近对话",
                "visual_contexts": [],
            },
        )
    )

    assert captured["proactive_mode"] is True
    assert "planning_extra_instructions" not in captured


def test_agent_reply_protocol_contains_hard_zh_required_constraint() -> None:
    """Agent 回复协议顶层必须包含台词段 zh 必填的硬约束。"""
    from app.llm.prompts.recipes import build_agent_reply_protocol

    protocol = build_agent_reply_protocol(["中性", "害羞"], ["站立待机"])

    assert "硬约束" in protocol
    assert "台词段" in protocol
    assert "zh" in protocol
    assert "简体中文" in protocol


def test_agent_reply_protocol_contains_anti_repetition_constraint() -> None:
    """Agent 回复协议顶层必须包含复读禁止硬约束。"""
    from app.llm.prompts.recipes import build_agent_reply_protocol

    protocol = build_agent_reply_protocol(["中性"], ["站立待机"])

    assert "复读禁止" in protocol
    assert "全新内容" in protocol
    assert "绝不复述" in protocol


def test_hard_constraints_appear_before_segment_rules() -> None:
    """硬约束应出现在分段规则之前，提升模型遵守率。"""
    from app.llm.prompts.recipes import build_agent_reply_protocol

    protocol = build_agent_reply_protocol(["中性"], ["站立待机"])
    hard_index = protocol.find("硬约束")
    rules_index = protocol.find("分段规则")
    assert hard_index != -1
    assert rules_index != -1
    assert hard_index < rules_index


def test_adult_mode_instruction_emphasizes_zh_required() -> None:
    """亲热模式指令必须强调台词段 zh 必填，避免字幕显示日语。"""
    from app.agent.runtime import ADULT_MODE_INSTRUCTION

    assert "台词段" in ADULT_MODE_INSTRUCTION
    assert "zh" in ADULT_MODE_INSTRUCTION
    assert "中文译文" in ADULT_MODE_INSTRUCTION
    # 亲昵场景特别警告。
    assert "亲昵场景特别警告" in ADULT_MODE_INSTRUCTION or "情感越强烈" in ADULT_MODE_INSTRUCTION


