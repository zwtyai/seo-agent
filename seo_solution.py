"""
用 Vertex Gemini 的 Google Search Grounding 打捞公开 SEO 复盘。

凭证与 main.py / vertex_llm.py 相同，不另接 SerpAPI 或 Custom Search Key：
  1. GOOGLE_CREDENTIALS_ENC + DOC2DOC_SECRETS_KEY
  2. 或 GOOGLE_APPLICATION_CREDENTIALS
外加 GOOGLE_CLOUD_PROJECT、GOOGLE_CLOUD_LOCATION、GEMINI_MODEL。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from vertex_llm import configure_vertex_env

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("seo_solution")

_DEFAULT_MODEL = "gemini-2.5-flash"
_WAIT_LOG_INTERVAL_SEC = 10


def _search_query(search_target: str) -> tuple[str, str]:
    """返回 (检索式, hl 说明)。检索式沿用原来的站点/文件类型足迹。"""
    if search_target == "saas":
        query = (
            '(site:indiehackers.com OR site:growthhackers.com) '
            '"SEO case study" "Search Console" "traffic"'
        )
        lang = "en"
    elif search_target == "xiaohongshu":
        query = '"小红书 SEO" ("案例拆解" OR "数据复盘" OR "流量暴涨") filetype:pdf'
        lang = "zh-cn"
    else:
        query = '"SEO case study" "organic traffic" "GSC"'
        lang = "en"
    return query, lang


def _model_id() -> str:
    model = (os.getenv("GEMINI_MODEL") or _DEFAULT_MODEL).strip()
    if model.startswith("gemini/"):
        model = model.split("/", 1)[1]
    return model


def _cases_from_grounding(response: Any, limit: int = 10) -> list[dict]:
    """从 Grounding 引用块取标题、链接、摘要。链接只来自检索元数据。"""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        logger.warning("响应里没有 candidate")
        return []
    meta = getattr(candidates[0], "grounding_metadata", None)
    if meta is None:
        logger.warning("响应里没有 grounding_metadata")
        return []

    snippets: dict[int, str] = {}
    for support in getattr(meta, "grounding_supports", None) or []:
        segment = getattr(support, "segment", None)
        text = (getattr(segment, "text", None) or "").strip() if segment else ""
        for idx in getattr(support, "grounding_chunk_indices", None) or []:
            snippets.setdefault(int(idx), text)

    cases: list[dict] = []
    chunks = list(getattr(meta, "grounding_chunks", None) or [])
    for i, chunk in enumerate(chunks):
        web = getattr(chunk, "web", None)
        if web is None:
            continue
        link = (getattr(web, "uri", None) or "").strip()
        title = (getattr(web, "title", None) or "").strip()
        if not link:
            continue
        cases.append(
            {
                "排名": len(cases) + 1,
                "标题": title or link,
                "链接": link,
                "快照摘要": snippets.get(i, ""),
            }
        )
        if len(cases) >= limit:
            break
    logger.info("解析引用：%d 个网页块，保留 %d 条", len(chunks), len(cases))
    return cases


def _log_while_waiting(stop: threading.Event, started: float) -> None:
    while not stop.wait(_WAIT_LOG_INTERVAL_SEC):
        logger.info("仍在等待 Vertex 响应，已 %.0f 秒", time.monotonic() - started)


def fetch_seo_case_studies(search_target: str = "saas") -> list[dict]:
    """
    按足迹检索带 Search Console / 流量数据的公开 SEO 复盘。

    search_target: "saas"（海外独立站）或 "xiaohongshu"（小红书复盘）。
    返回最多 10 条：排名、标题、链接、快照摘要。
    """
    from google import genai
    from google.genai import types

    started = time.monotonic()
    logger.info("开始打捞 | target=%s", search_target)

    query, lang = _search_query(search_target)
    logger.info("检索式已生成（%s）: %s", lang, query)

    logger.info("正在加载 Vertex 凭证")
    project, location, _ = configure_vertex_env()
    model = _model_id()
    logger.info("凭证就绪 | model=%s | location=%s", model, location)

    client = genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=types.HttpOptions(timeout=45_000),
    )
    logger.info("客户端已创建，开始请求 Google Search Grounding（超时 45 秒）")
    prompt = (
        "用 Google 搜索执行下面这条检索式，只依据搜索结果作答，不要编造 URL。\n"
        f"检索式：{query}\n"
        "优先保留带 Search Console、流量趋势或真实数据的复盘。"
        "列出最相关的结果，每条给出标题和它在回答中被引用的原因。"
    )
    stop_wait = threading.Event()
    waiter = threading.Thread(
        target=_log_while_waiting,
        args=(stop_wait, time.monotonic()),
        daemon=True,
    )
    waiter.start()
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.2,
            ),
        )
    except Exception:
        logger.exception("请求失败，耗时 %.1f 秒", time.monotonic() - started)
        return []
    finally:
        stop_wait.set()

    logger.info("收到响应，耗时 %.1f 秒，开始解析引用", time.monotonic() - started)
    raw_cases = _cases_from_grounding(response, limit=10)
    if not raw_cases:
        text = (getattr(response, "text", None) or "").strip()
        logger.warning("没有可用的 Grounding 引用链接")
        if text:
            logger.info("模型正文（前 1200 字）: %s", text[:1200])
        return []

    logger.info("截获 %d 条带来源链接的结果", len(raw_cases))
    for case in raw_cases:
        logger.info(
            "标本 %s | %s | %s",
            case["排名"],
            case["标题"],
            case["链接"],
        )
        if case["快照摘要"]:
            logger.info("摘要: %s", case["快照摘要"])
    logger.info("完成，总耗时 %.1f 秒", time.monotonic() - started)
    return raw_cases


if __name__ == "__main__":
    fetch_seo_case_studies(search_target="saas")
