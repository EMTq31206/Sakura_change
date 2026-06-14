from __future__ import annotations

from app.llm.chat_reply import ChatReply, parse_chat_reply


def _import_marker():
    """延迟导入，避免在无 Qt 环境下 import pet_window 失败。

    _progress_already_spoken_marker 是模块级纯函数，只依赖 ChatReply，
    但它定义在 pet_window.py 中，导入该模块会触发 PySide6 依赖。
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # 仅在 PySide6 可用时运行；CI 可能跳过 UI 相关测试。
    try:
        from app.ui import pet_window  # noqa: F401
    except Exception:  # pragma: no cover - 无 Qt 环境时跳过
        return None
    from app.ui.pet_window import _progress_already_spoken_marker
    return _progress_already_spoken_marker


def test_progress_marker_compresses_multi_segment_reply() -> None:
    marker_fn = _import_marker()
    if marker_fn is None:
        import pytest

        pytest.skip("PySide6 不可用，跳过 UI 单元测试")

    reply = parse_chat_reply(
        '{"segments":['
        '{"ja":"ちょっと調べてくる。","zh":"我去查一下。","tone":"中性","portrait":"站立待机"},'
        '{"ja":"すぐ戻るから。","zh":"马上回来哦。","tone":"请求","portrait":"伸手命令"}'
        "]}"
    )
    marker = marker_fn(reply)

    assert "已经对用户说过" in marker
    # marker 用 segment.text（模型自己输出的日文原文），让模型最容易识别自己说过的话。
    assert "ちょっと調べてくる" in marker
    assert "すぐ戻るから" in marker


def test_progress_marker_truncates_long_snippet() -> None:
    marker_fn = _import_marker()
    if marker_fn is None:
        import pytest

        pytest.skip("PySide6 不可用，跳过 UI 单元测试")

    long_text = "あ" * 100
    reply = ChatReply([__import__("app.llm.chat_reply", fromlist=["ChatSegment"]).ChatSegment(text=long_text)])
    marker = marker_fn(reply)

    assert "已经对用户说过" in marker
    # 单条 snippet 截断到 60 字 + 省略号。
    assert "…" in marker
    assert len(marker) < 200


def test_progress_marker_returns_empty_for_empty_reply() -> None:
    marker_fn = _import_marker()
    if marker_fn is None:
        import pytest

        pytest.skip("PySide6 不可用，跳过 UI 单元测试")

    reply = ChatReply(
        [__import__("app.llm.chat_reply", fromlist=["ChatSegment"]).ChatSegment(text="")]
    )
    marker = marker_fn(reply)
    assert marker == ""
