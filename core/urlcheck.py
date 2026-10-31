"""公开来源 URL：解 grounding 跳转、可选存活检查。"""

from __future__ import annotations

import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
    urlopen,
)

_BLOCKED_HOST_SUFFIXES = (
    "baijiahao.baidu.com",
    "wappass.baidu.com",
    "mbd.baidu.com",
)

_GROUNDING_HOST = "vertexaisearch.cloud.google.com"

_USER_AGENT = (
    "Mozilla/5.0 (compatible; seo-agent-source-check/1.0; +https://github.com/zwtyai/seo-agent)"
)


def host_blocked(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if host == _GROUNDING_HOST or host.endswith("." + _GROUNDING_HOST):
        return _GROUNDING_HOST
    for suffix in _BLOCKED_HOST_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            return suffix
    return None


def is_grounding_redirect(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == _GROUNDING_HOST or host.endswith("." + _GROUNDING_HOST)


class _NoFollowRedirect(HTTPRedirectHandler):
    """不自动跟随，把 Location 留给调用方读取。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def resolve_grounding_redirect(url: str, *, timeout: float = 12.0) -> tuple[str | None, str]:
    """
    把 vertexaisearch grounding 跳转链解成真实原文 URL。
    只读第一跳 Location，不要求目标页此时一定 200。
    """
    text = (url or "").strip()
    if not is_grounding_redirect(text):
        return text, ""

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    opener = build_opener(
        _NoFollowRedirect,
        HTTPSHandler(context=ssl.create_default_context()),
    )
    # 部分环境对 HEAD 不友好，失败再试 GET。
    for method in ("HEAD", "GET"):
        request = Request(text, headers=headers, method=method)
        try:
            with opener.open(request, timeout=timeout) as response:
                location = response.headers.get("Location") or response.headers.get("location")
                if location:
                    final = urljoin(text, location.strip())
                    if final.startswith(("http://", "https://")) and not is_grounding_redirect(final):
                        return final, f"已解开 grounding 跳转 → {final}"
                # 若服务端直接 200 且 geturl 已变（少数实现），也收下。
                final_url = response.geturl() or text
                if final_url != text and not is_grounding_redirect(final_url):
                    return final_url, f"已解开 grounding 跳转 → {final_url}"
        except HTTPError as exc:
            location = None
            if exc.headers:
                location = exc.headers.get("Location") or exc.headers.get("location")
            if location:
                final = urljoin(text, location.strip())
                if final.startswith(("http://", "https://")) and not is_grounding_redirect(final):
                    return final, f"已解开 grounding 跳转 → {final}"
            if method == "GET":
                return None, f"grounding 跳转解不开：HTTP {exc.code}。请改填原文 URL。"
        except URLError as exc:
            if method == "GET":
                reason = getattr(exc, "reason", exc)
                return None, f"grounding 跳转解不开：{reason}。请改填原文 URL。"
        except Exception as exc:  # noqa: BLE001
            if method == "GET":
                return None, f"grounding 跳转解不开：{type(exc).__name__}: {exc}。"

    return None, "grounding 跳转没有 Location。请改填百科/媒体原文 URL。"


def canonicalize_source_url(
    url: str,
    *,
    require_live: bool = False,
    timeout: float = 12.0,
) -> tuple[str | None, str]:
    """
    规范化来源 URL。
    返回 (可用 URL 或 None, 空字符串表示成功 / 否则是失败原因)。
    grounding 跳转会先解开；百度验证码页仍拒绝；require_live 时再测最终 200。
    """
    text = (url or "").strip()
    if not text.startswith(("http://", "https://")):
        return None, "来源 URL 必须以 http:// 或 https:// 开头。"

    if is_grounding_redirect(text):
        resolved, note = resolve_grounding_redirect(text, timeout=timeout)
        if not resolved:
            return None, note
        text = resolved

    blocked = host_blocked(text)
    if blocked:
        return None, f"来源不要用 {blocked} 这类跳转/验证码页，换成可直接打开的原文。"

    if require_live:
        ok, reason = probe_source_url(text, timeout=timeout)
        if not ok:
            return None, reason

    return text, ""


def probe_source_url(url: str, *, timeout: float = 12.0) -> tuple[bool, str]:
    """
    跟随跳转后最终状态须为 HTTP 200。
    返回 (是否通过, 说明)。说明里带最终 URL / 状态，方便写进 guardrail。
    """
    text = (url or "").strip()
    if not text.startswith(("http://", "https://")):
        return False, "来源 URL 必须以 http:// 或 https:// 开头。"

    if is_grounding_redirect(text):
        resolved, note = resolve_grounding_redirect(text, timeout=timeout)
        if not resolved:
            return False, note
        text = resolved

    blocked = host_blocked(text)
    if blocked:
        return False, f"不要用 {blocked} 这类跳转/验证码页，换成可直接打开的原文。"

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    request = Request(text, headers=headers, method="GET")
    context = ssl.create_default_context()
    try:
        with urlopen(request, timeout=timeout, context=context) as response:
            final_url = response.geturl() or text
            status = getattr(response, "status", None) or response.getcode()
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
    start_parts = [p for p in start_path.split("/") if p]
    end_parts = [p for p in end_path.split("/") if p]
    if len(start_parts) >= 2 and len(end_parts) <= 1:
        if end_parts and end_parts[0].lower() in {"blog", "news", "article", "articles"}:
            return True
        if not end_parts:
            return True
    return False
