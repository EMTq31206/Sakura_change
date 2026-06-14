from __future__ import annotations

import html
import json
import re
import sys
from html.parser import HTMLParser
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.agent.web_search import search_bing_rss


SERVER_NAME = "sakura-web-search"
SERVER_VERSION = "0.1.0"
DEFAULT_TIMEOUT_SECONDS = 12
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)


TOOLS: list[dict[str, Any]] = [
    {
        "name": "web_search",
        "description": "搜索公开网页，并返回标题、链接和简短摘要。适合查询最新信息、资料来源和网页入口；搜索需求必须先用本工具，不要自行拼接搜索 URL。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词。",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最多返回多少条结果，范围 1-10。",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "fetch_url",
        "description": "读取一个明确的公开 http/https 内容页，抽取标题、正文文本和页面链接。不要传 Google/Bing 搜索结果页；搜索需求先用 web_search。返回 status/guidance 用于判断是否为空页、动态页或错误 URL。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要读取的公开网页 URL，仅支持 http 或 https。",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "正文最多返回多少字符，范围 500-20000。建议需要网页详情时使用 12000 或更高。",
                    "minimum": 500,
                    "maximum": 20000,
                    "default": 6000,
                },
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
]


def main() -> int:
    try:
        _run_fastmcp_server()
        return 0
    except ImportError as exc:
        # mcp 库未安装时，fallback 到轻量 JSON-RPC。
        # 但 MCP 客户端默认按 Content-Length 分帧（LSP 风格），
        # 这里的 fallback 按 newline 分帧，协议不匹配会导致大量请求解析失败。
        # 因此打印醒目警告，提醒用户安装 mcp 库；fallback 仍保留以便调试。
        sys.stderr.write(
            "[sakura-web-search] 警告：未安装 mcp 库（ImportError: "
            + str(exc)
            + "），已降级到不兼容的 newline-delimited JSON-RPC fallback。\n"
            "MCP 客户端很可能无法正常通信，Web 搜索/抓取工具会失败。\n"
            "请运行：pip install -r requirements.txt  （需要 mcp>=1.9）\n"
        )
        sys.stderr.flush()

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            response = handle_message(message)
        except Exception as exc:  # MCP Server 不能因为单条坏消息退出。
            response = _error_response(None, -32603, f"内部错误：{exc}")
        if response is not None:
            _write_message(response)
    return 0


def _run_fastmcp_server() -> None:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(SERVER_NAME, log_level="ERROR")

    @mcp.tool(
        name="web_search",
        description="搜索公开网页，并返回标题、链接和简短摘要。适合查询最新信息、资料来源和网页入口；搜索需求必须先用本工具，不要自行拼接搜索 URL。",
        structured_output=True,
    )
    def web_search_tool(query: str, max_results: int = 5) -> dict[str, Any]:
        """搜索公开网页。"""

        return search_web(
            query=query,
            max_results=_clamp_int(max_results, default=5, minimum=1, maximum=10),
        )

    @mcp.tool(
        name="fetch_url",
        description="读取一个明确的公开 http/https 内容页，抽取标题、正文文本和页面链接。不要传 Google/Bing 搜索结果页；搜索需求先用 web_search。返回 status/guidance 用于判断是否为空页、动态页或错误 URL。",
        structured_output=True,
    )
    def fetch_url_tool(url: str, max_chars: int = 6000) -> dict[str, Any]:
        """读取公开网页正文。"""

        return fetch_url(
            url=url,
            max_chars=_clamp_int(max_chars, default=6000, minimum=500, maximum=20000),
        )

    mcp.run("stdio")


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = str(message.get("method") or "")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    if request_id is None:
        return None
    if method == "initialize":
        requested_version = str(params.get("protocolVersion") or "2024-11-05")
        return _result_response(
            request_id,
            {
                "protocolVersion": requested_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "ping":
        return _result_response(request_id, {})
    if method == "tools/list":
        return _result_response(request_id, {"tools": TOOLS})
    if method == "tools/call":
        return _handle_tool_call(request_id, params)
    if method == "resources/list":
        return _result_response(request_id, {"resources": []})
    if method == "prompts/list":
        return _result_response(request_id, {"prompts": []})
    return _error_response(request_id, -32601, f"不支持的方法：{method}")


def _handle_tool_call(request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = str(params.get("name") or "")
    arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
    try:
        if name == "web_search":
            payload = search_web(
                query=_required_string(arguments, "query"),
                max_results=_clamp_int(arguments.get("max_results"), default=5, minimum=1, maximum=10),
            )
        elif name == "fetch_url":
            payload = fetch_url(
                url=_required_string(arguments, "url"),
                max_chars=_clamp_int(arguments.get("max_chars"), default=6000, minimum=500, maximum=20000),
            )
        else:
            return _error_response(request_id, -32602, f"未知工具：{name}")
    except Exception as exc:
        return _result_response(
            request_id,
            {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            },
        )
    return _tool_result_response(request_id, payload)


def search_web(query: str, max_results: int = 5) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise ValueError("query 不能为空。")

    results = _merged_search_results(query, max_results=max_results)
    return {
        "query": query,
        "source": "Bing",
        "results": [
            {"title": item.title, "url": item.url, "snippet": item.snippet}
            for item in results
        ],
    }


def fetch_url(url: str, max_chars: int = 6000) -> dict[str, Any]:
    normalized_url = _validate_public_http_url(url)
    search_page_warning = _search_page_warning(normalized_url)
    mojibake_warning = _mojibake_url_warning(normalized_url)
    if search_page_warning or mojibake_warning:
        return _blocked_fetch_result(normalized_url, search_page_warning, mojibake_warning)
    raw_text, content_type, final_url = _read_url_text_with_metadata(
        normalized_url,
        max_bytes=max(256_000, min(max_chars * 8, 1_500_000)),
    )
    if "html" in content_type.lower():
        parser = PageTextParser()
        parser.feed(raw_text)
        text = _normalize_space(parser.text)
        title = _normalize_space(parser.title)
        links = parser.links[:30]
    else:
        text = _normalize_space(raw_text)
        title = ""
        links = []
    status, guidance = _fetch_status_and_guidance(
        url=final_url,
        title=title,
        text=text,
        content_type=content_type,
        search_page_warning=search_page_warning,
        mojibake_warning=mojibake_warning,
    )
    return {
        "url": final_url,
        "content_type": content_type,
        "title": title,
        "text": text[:max_chars],
        "truncated": len(text) > max_chars,
        "links": links,
        "status": status,
        "guidance": guidance,
    }


def _merged_search_results(query: str, max_results: int) -> list[Any]:
    seen: set[str] = set()
    merged: list[Any] = []
    for candidate in _search_query_candidates(query):
        for item in search_bing_rss(candidate, max_results=max_results):
            key = item.url.rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= max_results:
                return merged
    return merged


def _search_query_candidates(query: str) -> list[str]:
    candidates = [query]
    simplified = re.sub(r"\bsite:\S+", " ", query, flags=re.I)
    simplified = re.sub(r"\b(?:https?://)?(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}\b", " ", simplified, flags=re.I)
    simplified = " ".join(simplified.split())
    if simplified and simplified != query:
        if re.search(r"\bsite:\S+", query, flags=re.I):
            candidates.append(simplified)
        else:
            candidates.insert(0, simplified)
    return candidates


def _blocked_fetch_result(url: str, *warnings: str) -> dict[str, Any]:
    guidance = " ".join(warning for warning in warnings if warning)
    return {
        "url": url,
        "content_type": "",
        "title": "",
        "text": "",
        "truncated": False,
        "links": [],
        "status": "warning",
        "guidance": guidance,
    }


def _search_page_warning(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if host.endswith("google.com") and path.startswith("/search"):
        query = parse_qs(parsed.query).get("q", [""])[0]
        return (
            "这是 Google 搜索结果页，不适合用 fetch_url 读取。"
            f"请改用 web_search，query={query!r}。"
        )
    if host.endswith("bing.com") and path.startswith("/search"):
        query = parse_qs(parsed.query).get("q", [""])[0]
        return (
            "这是 Bing 搜索结果页，不适合用 fetch_url 读取。"
            f"请改用 web_search，query={query!r}。"
        )
    return ""


def _mojibake_url_warning(url: str) -> str:
    parsed = urlparse(url)
    query_text = " ".join(value for values in parse_qs(parsed.query).values() for value in values)
    if _looks_mojibake(query_text):
        return "URL 查询参数疑似编码损坏。不要继续使用这个 URL，请回到原始自然语言问题并调用 web_search。"
    return ""


def _looks_mojibake(text: str) -> bool:
    if not text:
        return False
    markers = {"�", "Ã", "Â", "ƒ", "∆", "Ω", "Í", "Ò", "Ó", "¬", "»", "«"}
    hits = sum(text.count(marker) for marker in markers)
    return hits >= 2 or (hits >= 1 and not any("\u4e00" <= char <= "\u9fff" for char in text))


def _fetch_status_and_guidance(
    *,
    url: str,
    title: str,
    text: str,
    content_type: str,
    search_page_warning: str,
    mojibake_warning: str,
) -> tuple[str, str]:
    warnings = [warning for warning in (search_page_warning, mojibake_warning) if warning]
    if not text.strip():
        warnings.append(
            "页面没有抽取到可读正文。可能是错误 URL、动态渲染页面、反爬页面或空页面；请先用 web_search 找到更可靠的具体页面。"
        )
        return "empty_text", " ".join(warnings)
    if warnings:
        return "warning", " ".join(warnings)
    if len(text) < 300 and "html" in content_type.lower():
        warnings.append(
            "页面正文很短，可能不是目标内容页；请检查 title/url 是否匹配用户问题，必要时重新 web_search。"
        )
        return "limited_text", " ".join(warnings)
    if "github.com/trending" in url and "Trending repositories" in title:
        return "ok", "GitHub trending 是可抓取的静态 HTML；请直接从 text 中提取仓库名、描述和链接，不要改用搜索页。"
    return "ok", "页面正文已抽取；请基于 title/text/links 回答，不要臆造页面外信息。"


class PageTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.links: list[dict[str, str]] = []
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._active_link: str | None = None
        self._active_link_text: list[str] = []

    @property
    def text(self) -> str:
        return "\n".join(self._text_parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = attrs_map.get("href", "")
            if href.startswith(("http://", "https://")):
                self._active_link = href
                self._active_link_text = []
        if tag in {"p", "div", "section", "article", "br", "li", "h1", "h2", "h3"}:
            self._text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
        if self._active_link is not None:
            self._active_link_text.append(data)
        stripped = data.strip()
        if stripped:
            self._text_parts.append(stripped)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
            self.title = "".join(self._title_parts)
        elif tag == "a" and self._active_link is not None:
            text = _normalize_space("".join(self._active_link_text))
            if text:
                self.links.append({"text": text[:120], "url": self._active_link})
            self._active_link = None
            self._active_link_text = []


def _read_url_text(url: str, max_bytes: int) -> str:
    text, _content_type, _final_url = _read_url_text_with_metadata(url, max_bytes)
    return text


def _read_url_text_with_metadata(url: str, max_bytes: int) -> tuple[str, str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json,text/plain"})
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read(max_bytes + 1)
            final_url = response.geturl()
    except HTTPError as exc:
        raise RuntimeError(_friendly_http_error_message(url, exc)) from exc
    except URLError as exc:
        reason = str(exc.reason)
        if "timed out" in reason.lower() or "timeout" in reason.lower():
            raise RuntimeError(
                f"读取超时（{DEFAULT_TIMEOUT_SECONDS}s）：{url}。"
                "该站点响应慢或不可达，建议改用 web_search 获取摘要，不要反复重试同一 URL。"
            ) from exc
        raise RuntimeError(f"网络请求失败：{exc.reason}") from exc

    charset = _charset_from_content_type(content_type)
    if len(body) > max_bytes:
        body = body[:max_bytes]
    try:
        return body.decode(charset, errors="replace"), content_type, final_url
    except LookupError:
        return body.decode("utf-8", errors="replace"), content_type, final_url


def _friendly_http_error_message(url: str, exc: HTTPError) -> str:
    """把 HTTPError 翻译成模型可理解的诊断信息，引导它改用 web_search。"""
    try:
        code = int(exc.code)
    except (TypeError, ValueError):
        code = 0
    host = (urlparse(url).hostname or "").lower()
    reason = str(exc.reason or "")
    if code == 403:
        return (
            f"HTTP 403 被拒绝（{host}）：该站点有反爬/Cloudflare 拦截，无法直接抓取正文。"
            "不要反复重试同一 URL，改用 web_search 获取其他来源的摘要。"
        )
    if code == 429:
        return (
            f"HTTP 429 限流（{host}）：请求过于频繁被暂时拒绝。"
            "等待片刻或改用 web_search 找其他来源。"
        )
    if code in (401, 407):
        return f"HTTP {code} 需要认证（{host}）：该页面需要登录，fetch_url 无法读取，改用 web_search。"
    if 400 <= code < 500:
        return f"HTTP {code} 客户端错误（{host}：{reason}）：URL 可能失效或不公开，改用 web_search。"
    if 500 <= code < 600:
        return f"HTTP {code} 服务端错误（{host}：{reason}）：站点暂时不可用，稍后再试或改用 web_search。"
    return f"HTTP {code}: {reason}"


def _charset_from_content_type(content_type: str) -> str:
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            return part.split("=", 1)[1].strip()
    return "utf-8"


def _validate_public_http_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url 必须是完整的 http 或 https 地址。")
    host = parsed.hostname or ""
    if _is_blocked_host(host):
        raise ValueError("出于安全考虑，不允许读取本机或私有网络地址。")
    return url


def _is_blocked_host(host: str) -> bool:
    normalized = host.strip("[]").lower()
    if normalized in {"localhost"} or normalized.endswith(".localhost"):
        return True
    try:
        address = ip_address(normalized)
    except ValueError:
        return False
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _required_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 必须是非空字符串。")
    return value


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("数值参数必须是整数。")
    if value < minimum or value > maximum:
        raise ValueError(f"数值参数必须在 {minimum}-{maximum} 之间。")
    return value


def _normalize_space(value: str) -> str:
    lines = [" ".join(line.split()) for line in html.unescape(value).splitlines()]
    return "\n".join(line for line in lines if line)


def _tool_result_response(request_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return _result_response(
        request_id,
        {
            "content": [{"type": "text", "text": text}],
            "structuredContent": payload,
            "isError": False,
        },
    )


def _result_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _write_message(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
