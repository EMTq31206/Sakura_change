from __future__ import annotations

import pytest

from app.agent.web_search import SearchResult
from plugins.playwright_browser import browser


def test_playwright_search_opens_bing_and_respects_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Page:
        def __init__(self) -> None:
            self.visited_url = ""

        def goto(self, url: str, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            self.visited_url = url

    page = Page()
    captured: dict[str, object] = {}

    def fake_search(query: str, *, max_results: int):  # type: ignore[no-untyped-def]
        captured.update(query=query, max_results=max_results)
        return [
            SearchResult("标题 1", "https://example.com/1", "摘要 1"),
            SearchResult("标题 2", "https://example.com/2", "摘要 2"),
        ]

    monkeypatch.setattr(browser, "_use_bg_thread", False)
    monkeypatch.setattr(browser, "_ensure_browser", lambda: page)
    monkeypatch.setattr(browser, "search_bing_rss", fake_search)

    result = browser.search_web("二阶堂真红 百科", limit=2)

    assert page.visited_url.startswith("https://www.bing.com/search?")
    assert "q=%E4%BA%8C%E9%98%B6%E5%A0%82%E7%9C%9F%E7%BA%A2+%E7%99%BE%E7%A7%91" in page.visited_url
    assert "cc=cn" in page.visited_url
    assert "mkt=zh-CN" in page.visited_url
    assert captured == {"query": "二阶堂真红 百科", "max_results": 2}
    assert "标题 1" in result
    assert "摘要 1" in result
    assert "https://example.com/1" in result
    assert "标题 2" in result


def test_playwright_search_reports_empty_bing_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Page:
        def goto(self, _url: str, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

    monkeypatch.setattr(browser, "_use_bg_thread", False)
    monkeypatch.setattr(browser, "_ensure_browser", lambda: Page())
    monkeypatch.setattr(browser, "search_bing_rss", lambda *_args, **_kwargs: [])

    assert browser.search_web("没有结果") == "没有找到可用搜索结果。"
