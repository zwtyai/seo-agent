"""公开来源 URL 存活检查。系列选题要求最终落到可打开的原文页。"""

from __future__ import annotations

import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_BLOCKED_HOST_SUFFIXES = (
    "vertexaisearch.cloud.google.com",
    "baijiahao.baidu.com",
    "wappass.baidu.com",
    "mbd.baidu.com",
)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; seo-agent-source-check/1.0; +https://github.com/zwtyai/seo-agent)"
)


def host_blocked(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    for suffix in _BLOCKED_HOST_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            return suffix
    return None


def probe_source_url(url: str, *, timeout: float = 12.0) -> tuple[bool, str]:
    """
    跟随跳转后最终状态须为 HTTP 200。
    返回 (是否通过, 说明)。说明里带最终 URL / 状态，方便写进 guardrail。
    """
    text = (url or "").strip()
    if not text.startswith(("http://", "https://")):
        return False, "来源 URL 必须以 http:// 或 https:// 开头。"

    blocked = host_blocked(text)
    if blocked:
        return False, f"不要用 {blocked} 这类跳转/验证码页，换成可直接打开的原文。"

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    # 部分站点拒 HEAD，统一用 GET，但只读少量内容。
    request = Request(text, headers=headers, method="GET")
    context = ssl.create_default_context()
    try:
        with urlopen(request, timeout=timeout, context=context) as response:
            final_url = response.geturl() or text
            status = getattr(response, "status", None) or response.getcode()
            # 读一小段，触发某些站点的真实响应。
            response.read(2048)
    except HTTPError as exc:
        final_url = getattr(exc, "url", None) or text
        return False, f"来源打不开：HTTP {exc.code}（最终 {final_url}）。换一条能打开的原文。"
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        return False, f"来源打不开：{reason}。换一条能打开的原文。"
    except Exception as exc:  # noqa: BLE001 - 网络异常统一回写成选题失败
        return False, f"来源打不开：{type(exc).__name__}: {exc}。换一条能打开的原文。"

    blocked_final = host_blocked(final_url)
    if blocked_final:
        return False, f"来源跳到了 {blocked_final}，不能当原文。换稳定来源。"

    if int(status) != 200:
        return False, f"来源最终状态是 HTTP {status}（{final_url}），必须是 200。"

    # 深链落到站点首页，通常表示原文没了。
    if _looks_like_homepage_fallback(text, final_url):
        return False, f"来源深链已跳回首页（{final_url}），原文可能下线。换一条。"

    return True, f"来源可用：HTTP 200 → {final_url}"


def _looks_like_homepage_fallback(original: str, final: str) -> bool:
    """原文路径较长，最终却只剩域名或 /blog/ 这类列表页。"""
    start = urlparse(original)
    end = urlparse(final)
    start_path = (start.path or "").rstrip("/")
    end_path = (end.path or "").rstrip("/")
    if not start_path or start_path == "/":
        return False
    # 原路径至少两段，最终变成空、/、或单段列表页
    start_parts = [p for p in start_path.split("/") if p]
    end_parts = [p for p in end_path.split("/") if p]
    if len(start_parts) >= 2 and len(end_parts) <= 1:
        if end_parts and end_parts[0].lower() in {"blog", "news", "article", "articles"}:
            return True
        if not end_parts:
            return True
    return False
