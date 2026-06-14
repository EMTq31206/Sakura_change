from app.llm.chat_reply import ChatSegment
from app.llm.chinese_text import to_simplified_chinese


def test_traditional_chinese_is_normalized_for_subtitles_only() -> None:
    segment = ChatSegment(
        text="畫面を確認したよ。",
        translation="畫面已經確認，這裡顯示繁體中文。",
    )

    assert segment.text == "畫面を確認したよ。"
    assert segment.translation == "画面已经确认，这里显示繁体中文。"
    assert to_simplified_chinese("繁體與網路") == "繁体与网路"
