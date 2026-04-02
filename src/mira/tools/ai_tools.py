#!/usr/bin/env python3
"""
网络工具 - WebSearchTool / WebFetchTool
搜索引擎：ddgs 库（主）/ Bing 抓取（备）
"""

import re
import html as _html_mod
import urllib.parse
from html.parser import HTMLParser
from typing import Dict, Any, List

from mira.tools.base import Tool

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_DEFAULT_HEADERS = {
    "User-Agent": _DEFAULT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
_TIMEOUT = 12


# ─── HTTP 工具 ────────────────────────────────────────────────────────────────

def _get(url: str, params: dict = None, timeout: int = _TIMEOUT,
         headers: dict = None) -> str:
    """发起 GET 请求，优先 requests，无则 urllib"""
    h = {**_DEFAULT_HEADERS, **(headers or {})}
    try:
        import requests
        resp = requests.get(url, params=params, headers=h,
                            timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except ImportError:
        pass

    import urllib.request
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(full, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        cs = "utf-8"
        ct = r.headers.get("Content-Type", "")
        if "charset=" in ct:
            cs = ct.split("charset=")[-1].strip().split(";")[0]
        return r.read().decode(cs, errors="replace")


# ─── HTML → 纯文本 ────────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "head", "svg",
                 "iframe", "nav", "footer"}

    def __init__(self):
        super().__init__()
        self._skip = 0
        self.parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self._skip += 1
        if tag.lower() in ("br", "p", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS:
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if self._skip == 0:
            text = data.strip()
            if text:
                self.parts.append(text)

    def get_text(self) -> str:
        raw = " ".join(self.parts)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        return raw.strip()


def _html_to_text(html_content: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html_content)
    except Exception:
        pass
    return parser.get_text()


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


# ─── ddgs 搜索（主引擎）─────────────────────────────────────────────────────

def _search_ddgs(query: str, num: int) -> List[Dict[str, str]]:
    """使用 ddgs 库搜索 DuckDuckGo（推荐，最可靠）"""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return []

    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("url", "")),
                    "snippet": r.get("body", r.get("snippet", ""))[:300],
                })
        return results
    except Exception:
        return []


# ─── Bing 搜索（备用引擎）────────────────────────────────────────────────────

def _parse_bing_html(content: str, num: int) -> List[Dict[str, str]]:
    """解析 Bing HTML 搜索结果，多策略兼容不同版本"""
    results: List[Dict[str, str]] = []

    # Bing 结果在 <li class="b_algo"> 或 <div class="b_algo">
    blocks = re.findall(
        r'<(?:li|div)\s+class="b_algo"[^>]*>(.*?)</(?:li|div)>',
        content, re.DOTALL
    )

    # 新版 Bing 可能使用不同 class
    if not blocks:
        blocks = re.findall(
            r'<(?:li|div)[^>]+class="[^"]*(?:b_algo|b_result)[^"]*"[^>]*>(.*?)</(?:li|div)>',
            content, re.DOTALL
        )

    for block in blocks:
        # 提取标题链接（<h2> 内的 <a>）
        url_m = re.search(
            r'<h2[^>]*>.*?<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            block, re.DOTALL
        )
        if not url_m:
            url_m = re.search(
                r'<a[^>]+href="(https?://(?!www\.bing\.com)[^"]+)"[^>]*>(.*?)</a>',
                block, re.DOTALL
            )
        if not url_m:
            continue

        url = url_m.group(1)
        if any(x in url for x in ("bing.com", "microsoft.com", "msn.com")):
            continue

        title = _strip_tags(url_m.group(2))
        if not title:
            continue

        # 提取摘要
        snippet = ""
        for pat in (
            r'<p\s+class="b_lineclamp[^"]*"[^>]*>(.*?)</p>',
            r'<div\s+class="b_caption[^"]*"[^>]*>.*?<p[^>]*>(.*?)</p>',
            r'<p[^>]*>(.*?)</p>',
        ):
            sm = re.search(pat, block, re.DOTALL)
            if sm:
                snippet = _strip_tags(sm.group(1))[:250]
                break

        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= num:
            break

    return results


def _search_bing(query: str, num: int) -> List[Dict[str, str]]:
    """Bing 搜索（备用）"""
    try:
        content = _get(
            "https://www.bing.com/search",
            params={"q": query, "count": num, "setlang": "zh-CN", "mkt": "zh-CN"},
            timeout=_TIMEOUT,
        )
        return _parse_bing_html(content, num)
    except Exception:
        return []


# ─── 统一搜索入口 ─────────────────────────────────────────────────────────────

def _search(query: str, num: int = 5, engine: str = "auto") -> List[Dict[str, str]]:
    """
    统一搜索接口。
    engine: "auto"（自动）| "ddg"（DuckDuckGo）| "bing"（必应）
    auto 模式：ddgs 优先，结果不足时 Bing 补充。
    """
    if engine == "bing":
        return _search_bing(query, num)

    if engine == "ddg":
        return _search_ddgs(query, num)

    # auto：ddgs 优先
    results = _search_ddgs(query, num)
    if len(results) < 2:
        bing = _search_bing(query, num)
        if len(bing) > len(results):
            results = bing

    return results


# ─── Tools ───────────────────────────────────────────────────────────────────

class WebSearchTool(Tool):
    """搜索互联网（DuckDuckGo + Bing 双引擎，无需 API Key）"""

    @property
    def name(self) -> str:
        return "WebSearchTool"

    @property
    def description(self) -> str:
        return (
            "搜索互联网，返回相关页面的标题、URL 和摘要。"
            "优先使用 DuckDuckGo（ddgs 库），自动切换 Bing 作备用，无需 API Key。"
            "参数 num 控制结果数量（默认 5，最多 10）。"
            "参数 engine 可指定搜索引擎：auto | ddg | bing。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "num": {
                    "type": "integer",
                    "description": "返回结果数量，默认 5，最多 10",
                },
                "engine": {
                    "type": "string",
                    "enum": ["auto", "ddg", "bing"],
                    "description": "搜索引擎：auto（自动）| ddg（DuckDuckGo）| bing（必应）",
                },
            },
            "required": ["query"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        query = args.get("query", "").strip()
        num = min(int(args.get("num", 5)), 10)
        engine = args.get("engine", "auto")

        if not query:
            return "错误：query 参数不能为空"

        results = _search(query, num, engine)

        if not results:
            return (
                f"未找到关于 '{query}' 的结果。\n"
                "建议：检查网络连接，或尝试指定 engine='bing'。"
            )

        used_engine = "DuckDuckGo" if engine in ("ddg", "auto") else "Bing"
        lines = [f"搜索: {query}  (共 {len(results)} 条结果)\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r.get('title', '（无标题）')}")
            url = r.get("url", "")
            if url:
                lines.append(f"    URL: {url}")
            snippet = r.get("snippet", "")
            if snippet:
                lines.append(f"    摘要: {snippet}")
            lines.append("")
        return "\n".join(lines).strip()


class WebFetchTool(Tool):
    """抓取网页内容并转换为可读文本"""

    @property
    def name(self) -> str:
        return "WebFetchTool"

    @property
    def description(self) -> str:
        return (
            "抓取指定 URL 的网页内容，自动去除 HTML 标签返回纯文本。"
            "可用 max_length 限制返回长度（默认 8000 字符）。"
            "支持 raw=true 返回原始 HTML（调试用）。"
        )

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "网页 URL"},
                "max_length": {
                    "type": "integer",
                    "description": "最大返回字符数，默认 8000",
                },
                "raw": {
                    "type": "boolean",
                    "description": "返回原始 HTML（默认 false）",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数，默认 12",
                },
            },
            "required": ["url"],
        }

    def execute(self, args: Dict[str, Any]) -> str:
        url = args.get("url", "").strip()
        max_length = int(args.get("max_length", 8000))
        raw = args.get("raw", False)
        timeout = int(args.get("timeout", _TIMEOUT))

        if not url:
            return "错误：url 参数不能为空"
        if not url.startswith(("http://", "https://")):
            return "错误：URL 必须以 http:// 或 https:// 开头"

        try:
            content = _get(url, timeout=timeout)
        except Exception as e:
            return f"错误：无法获取页面 - {e}"

        if raw:
            return content[:max_length]

        text = _html_to_text(content)

        title_m = re.search(
            r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL
        )
        title = _html_mod.unescape(title_m.group(1).strip()) if title_m else ""

        header = f"URL: {url}\n"
        if title:
            header += f"标题: {title}\n"
        header += "─" * 40 + "\n"

        result = header + text
        if len(result) > max_length:
            result = (result[:max_length]
                      + f"\n\n... [已截断，原文共 {len(text)} 字符]")
        return result
