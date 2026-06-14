from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


BING_SEARCH_URL = "https://www.bing.com/search"
BING_MARKET_PARAMS = {"cc": "cn", "mkt": "zh-CN"}
DEFAULT_SEARCH_TIMEOUT_SECONDS = 12
SEARCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


def build_bing_search_url(query: str) -> str:
    return BING_SEARCH_URL + "?" + urlencode({"q": query, **BING_MARKET_PARAMS})


def build_bing_rss_url(query: str) -> str:
    return BING_SEARCH_URL + "?" + urlencode(
        {"format": "rss", "q": query, **BING_MARKET_PARAMS}
    )


def search_bing_rss(
    query: str,
    *,
    max_results: int = 5,
    timeout_seconds: int = DEFAULT_SEARCH_TIMEOUT_SECONDS,
) -> list[SearchResult]:
    query = query.strip()
    if not query:
        raise ValueError("query 不能为空。")
    request = Request(
        build_bing_rss_url(query),
        headers={
            "User-Agent": SEARCH_USER_AGENT,
            "Accept": "application/rss+xml,application/xml,text/xml",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(1_000_001)
    except HTTPError as exc:
        raise RuntimeError(f"Bing 搜索 HTTP {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"Bing 搜索网络请求失败：{exc.reason}") from exc
    if len(body) > 1_000_000:
        body = body[:1_000_000]
    results = _filter_relevant_results(query, parse_bing_rss(body))
    return results[: max(1, max_results)]


def parse_bing_rss(payload: bytes | str) -> list[SearchResult]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise RuntimeError("Bing 搜索返回了无法解析的 RSS。") from exc

    results: list[SearchResult] = []
    for item in root.findall(".//item"):
        title = _element_text(item, "title")
        url = _element_text(item, "link")
        snippet = _element_text(item, "description")
        if title and url:
            results.append(SearchResult(title=title, url=url, snippet=snippet))
    return _dedupe_results(results)


def _element_text(element: ElementTree.Element, name: str) -> str:
    child = element.find(name)
    if child is None:
        return ""
    return " ".join("".join(child.itertext()).split())


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    deduped: list[SearchResult] = []
    for item in results:
        key = item.url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _filter_relevant_results(
    query: str,
    results: list[SearchResult],
) -> list[SearchResult]:
    """按查询相关性过滤搜索结果。

    对 CJK 查询使用字符级 Jaccard 重叠，避免整 token 子串匹配把
    Bing 返回的相关性较低但仍包含部分关键词的结果全部过滤掉。
    """
    anchors = _query_anchor_tokens(query)
    if not anchors:
        return results

    # CJK 查询走字符级重叠：只要结果与 query 共享足够多的汉字就保留。
    if _query_has_cjk(query):
        return _filter_by_char_overlap(query, results, anchors)

    # 拉丁文查询保留原 token 子串匹配。
    filtered = [
        item
        for item in results
        if any(
            anchor in f"{item.title}\n{item.snippet}\n{item.url}".casefold()
            for anchor in anchors
        )
    ]
    return filtered or results


def _query_has_cjk(query: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in query)


def _filter_by_char_overlap(
    query: str,
    results: list[SearchResult],
    anchors: list[str],
) -> list[SearchResult]:
    """CJK 查询的字符级相关性过滤。

    策略：从 query 抽取的 CJK token 集合为锚点。对每条结果，统计它的
    title+snippet 中出现了多少个锚点字符。命中比例 >= 阈值则保留。
    """
    anchor_chars = _cjk_char_set("".join(anchors))
    if not anchor_chars:
        return results

    threshold = _cjk_relevance_threshold(len(anchor_chars))
    scored: list[tuple[float, SearchResult]] = []
    for item in results:
        haystack = f"{item.title}\n{item.snippet}"
        haystack_chars = _cjk_char_set(haystack)
        if not haystack_chars:
            continue
        hit = len(anchor_chars & haystack_chars)
        ratio = hit / len(anchor_chars)
        if ratio >= threshold:
            scored.append((ratio, item))

    if scored:
        # 按相关性降序排列，让最相关的结果排在前面。
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _ratio, item in scored]
    # 全部不达标时回退原结果，避免返回空列表。
    return results


def _cjk_char_set(text: str) -> set[str]:
    return {char for char in text if "\u3400" <= char <= "\u9fff"}


def _cjk_relevance_threshold(anchor_count: int) -> float:
    """锚点字符越多，要求越宽松；越少（短查询），要求越严格。"""
    if anchor_count <= 2:
        return 0.999  # 短查询要求几乎全命中。
    if anchor_count <= 4:
        return 0.6
    return 0.4


def _query_anchor_tokens(query: str) -> list[str]:
    tokens = [
        token.casefold()
        for token in re.findall(r"[\w\u3400-\u9fff]+", query)
        if len(token) >= 2 and token.casefold() not in _QUERY_STOP_TOKENS
    ]
    cjk_tokens = [token for token in tokens if re.search(r"[\u3400-\u9fff]", token)]
    if cjk_tokens:
        return sorted(cjk_tokens, key=len, reverse=True)
    return sorted(tokens, key=len, reverse=True)


_QUERY_STOP_TOKENS = {
    "site",
    "www",
    "http",
    "https",
    "com",
    "cn",
    "org",
    "net",
    "百科",
    "最新",
    "消息",
}
