from __future__ import annotations

import sys
from urllib.error import URLError

import pytest

from app.agent.mcp.web_search_server import (
    _search_query_candidates,
    _validate_public_http_url,
    fetch_url,
    handle_message,
    search_web,
)
from app.agent import web_search as web_search_module
from app.agent.web_search import (
    SearchResult,
    _filter_relevant_results,
    parse_bing_rss,
)


def test_bing_rss_parser_extracts_and_dedupes_results() -> None:
    results = parse_bing_rss(
        """
        <rss><channel>
          <item>
            <title>Example</title>
            <link>https://example.com/page</link>
            <description>Example snippet</description>
          </item>
          <item>
            <title>Duplicate</title>
            <link>https://example.com/page</link>
            <description>Duplicate snippet</description>
          </item>
        </channel></rss>
        """
    )

    assert results == [
        SearchResult(
            title="Example",
            url="https://example.com/page",
            snippet="Example snippet",
        )
    ]


def test_bing_search_uses_shared_rss_results(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    def fake_search(query: str, *, max_results: int):  # type: ignore[no-untyped-def]
        captured.update(query=query, max_results=max_results)
        return [SearchResult("First", "https://example.com/page", "First snippet")]

    monkeypatch.setattr(
        "app.agent.mcp.web_search_server.search_bing_rss",
        fake_search,
    )

    result = search_web("二阶堂真红", max_results=5)

    assert captured == {"query": "二阶堂真红", "max_results": 5}
    assert result["source"] == "Bing"
    assert result["results"] == [
        {
            "title": "First",
            "url": "https://example.com/page",
            "snippet": "First snippet",
        }
    ]


def test_bing_search_rejects_empty_query() -> None:
    try:
        search_web("   ")
    except ValueError as exc:
        assert "query" in str(exc)
        return
    raise AssertionError("empty query should fail")


def test_bing_rss_parser_reports_malformed_xml() -> None:
    try:
        parse_bing_rss("<rss><broken>")
    except RuntimeError as exc:
        assert "RSS" in str(exc)
        return
    raise AssertionError("malformed RSS should fail")


def test_bing_search_reports_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        web_search_module,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )

    with pytest.raises(RuntimeError, match="Bing 搜索网络请求失败"):
        web_search_module.search_bing_rss("OpenAI")


def test_bing_search_filters_results_missing_the_core_query_term() -> None:
    results = _filter_relevant_results(
        "二阶堂真红 百科",
        [
            SearchResult("二（汉语汉字）", "https://example.com/two", "二的解释"),
            SearchResult(
                "二阶堂真红角色资料",
                "https://example.com/shinku",
                "二阶堂真红是作品角色。",
            ),
        ],
    )

    assert [item.url for item in results] == ["https://example.com/shinku"]


def test_bing_search_filter_falls_back_when_domain_token_misleads() -> None:
    results = _filter_relevant_results(
        "佛山天气 weather.com.cn",
        [
            SearchResult("佛山天气预报", "https://www.weather.com.cn/weather/101280800.shtml", "佛山天气"),
            SearchResult("Chetan Bhagat", "https://example.com/books", "books"),
        ],
    )

    assert results[0].url == "https://www.weather.com.cn/weather/101280800.shtml"


def test_fetch_url_reports_search_page_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_read(_url: str, *, max_bytes: int) -> tuple[str, str, str]:
        nonlocal called
        called = True
        return "", "", _url

    monkeypatch.setattr("app.agent.mcp.web_search_server._read_url_text_with_metadata", fake_read)

    result = fetch_url("https://www.google.com/search?q=%CE%A9%C3%92", max_chars=1000)

    assert result["status"] == "warning"
    assert "web_search" in result["guidance"]
    assert "编码损坏" in result["guidance"]
    assert called is False


def test_fetch_url_reports_empty_text_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_read(_url: str, *, max_bytes: int) -> tuple[str, str, str]:
        return "<html><title></title><body><script>app()</script></body></html>", "text/html", _url

    monkeypatch.setattr("app.agent.mcp.web_search_server._read_url_text_with_metadata", fake_read)

    result = fetch_url("https://example.com/dynamic", max_chars=1000)

    assert result["status"] == "empty_text"
    assert "没有抽取到可读正文" in result["guidance"]


def test_search_query_candidates_simplify_domain_noise() -> None:
    assert _search_query_candidates("佛山天气 weather.com.cn") == [
        "佛山天气",
        "佛山天气 weather.com.cn",
    ]
    assert _search_query_candidates("site:weather.com.cn 佛山 天气") == [
        "site:weather.com.cn 佛山 天气",
        "佛山 天气",
    ]


def test_fetch_url_blocks_local_network_addresses() -> None:
    for url in [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://192.168.1.1",
        "file:///C:/Users/test.txt",
    ]:
        try:
            _validate_public_http_url(url)
        except ValueError:
            continue
        raise AssertionError(f"should reject {url}")


def test_tools_list_response_contains_web_search_tools() -> None:
    response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response is not None
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert names == {"web_search", "fetch_url"}


def test_cjk_filter_keeps_partial_overlap_results_sorted_by_relevance() -> None:
    """CJK 查询字符级重叠过滤：保留部分命中结果，按相关性降序。"""
    results = [
        SearchResult("Python教程", "https://example.com/python", "编程语言入门"),
        SearchResult("夜乃桜角色介绍", "https://example.com/sakura", "水晶社游戏女主角"),
        SearchResult("水晶社新作公告", "https://example.com/news", "夜乃桜是女主角"),
    ]
    filtered = _filter_relevant_results("夜乃桜 水晶社 角色 设定", results)

    urls = [item.url for item in filtered]
    # Python 教程应该被过滤掉。
    assert "https://example.com/python" not in urls
    # 两个相关结果都应保留。
    assert "https://example.com/sakura" in urls
    assert "https://example.com/news" in urls


def test_cjk_filter_falls_back_when_nothing_matches() -> None:
    """全部不达标时回退原结果，避免返回空列表。"""
    results = [
        SearchResult("完全无关的内容", "https://example.com/a", "无关"),
        SearchResult("另一条无关结果", "https://example.com/b", "无关"),
    ]
    filtered = _filter_relevant_results("夜乃桜 水晶社", results)
    # 回退到原结果。
    assert len(filtered) == 2


def test_friendly_http_error_guides_to_web_search_on_403() -> None:
    """403 错误应给出改用 web_search 的明确指引。"""
    from urllib.error import HTTPError

    from app.agent.mcp.web_search_server import _friendly_http_error_message

    exc = HTTPError("https://blocked.example.com/x", 403, "Forbidden", {}, None)
    message = _friendly_http_error_message("https://blocked.example.com/x", exc)

    assert "403" in message
    assert "web_search" in message
    assert "不要反复重试" in message


def test_friendly_http_error_handles_non_int_code() -> None:
    """exc.code 不是 int 时不应崩溃。"""
    from urllib.error import HTTPError

    from app.agent.mcp.web_search_server import _friendly_http_error_message

    exc = HTTPError("https://example.com/x", None, "Weird", {}, None)  # type: ignore[arg-type]
    message = _friendly_http_error_message("https://example.com/x", exc)
    assert isinstance(message, str)
    assert len(message) > 0


def test_main_warns_when_mcp_library_missing(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """mcp 库缺失时 main() 应打印醒目 stderr 警告。"""
    import builtins
    import io as _io

    from app.agent.mcp import web_search_server

    original_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name.startswith("mcp"):
            raise ImportError(f"No module named '{name}'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # 空输入让 fallback 循环立即结束。
    monkeypatch.setattr(sys, "stdin", _io.StringIO(""))

    exit_code = web_search_server.main()

    err = capsys.readouterr().err
    assert exit_code == 0
    assert "[sakura-web-search]" in err
    assert "mcp" in err
    assert "pip install" in err


