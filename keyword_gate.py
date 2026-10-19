"""选题门槛：长尾词必须带来源的搜索量、难度，以及竞品有、本站没有的缺口。"""

from __future__ import annotations

import re

VOLUME_MIN = 200
VOLUME_MAX = 2000
KD_MAX = 30

_QUESTION = re.compile(r"如何|为什么|怎么|怎样|为何|吗")
_URL = re.compile(r"https?://\S+")
_VOLUME = re.compile(
    r"(?:月搜索量|搜索量)\s*[:：]\s*([0-9][0-9,]*(?:\.\d+)?)\s*([kK千])?"
)
_KD = re.compile(r"(?:KD|难度)\s*[:：]\s*(\d{1,3})", re.IGNORECASE)
_GAP_TERM = re.compile(r"(?:缺口词|关键词)\s*[:：]\s*(.+)")
_MISSING_METRIC = re.compile(r"未找到公开数据|无法提供")


def _norm(text: str) -> str:
    return re.sub(r"[\s\-—_，。、“”\"'？?]+", "", text).lower()


def brief_sections(markdown: str) -> dict[str, str]:
    parts = re.split(r"(?m)^##\s+", markdown or "")
    sections: dict[str, str] = {}
    for part in parts[1:]:
        lines = part.splitlines()
        name = re.sub(r"（.*?）", "", lines[0]).strip().lower()
        sections[name] = "\n".join(lines[1:]).strip()
    return sections


def _plain(text: str) -> str:
    return re.sub(r"[*_`]", "", text)


def _scaled_number(raw: str, suffix: str | None) -> int:
    number = float(raw.replace(",", ""))
    if suffix:
        number *= 1000
    return int(round(number))


def validate_keyword_brief(
    markdown: str,
    seed_keyword: str,
    existing_titles: list[str] | None = None,
    required_content_type: str | None = None,
) -> tuple[bool, str]:
    """检查研究简报里的长尾词是否满足第一步选题条件。"""
    sections = brief_sections(markdown)
    problems: list[str] = []

    keyword = sections.get("keyword", "").strip().splitlines()
    keyword_text = keyword[0].strip() if keyword else ""
    if not keyword_text:
        problems.append("缺少 ## keyword，写一个问题型长尾词。")
    else:
        folded = _norm(keyword_text)
        blocked = {_norm(seed_keyword), "pdf翻译", "pdf在线翻译"}
        if folded in blocked:
            problems.append(f"「{keyword_text}」是大词。改成「如何/为什么/怎么…」这种长尾问句。")
        elif not _QUESTION.search(keyword_text):
            problems.append(f"「{keyword_text}」不是问题型关键词。用如何、为什么、怎么开头。")
        for title in existing_titles or []:
            if folded and len(folded) >= 4 and folded in _norm(title):
                problems.append(f"「{keyword_text}」已经出现在已有标题里：{title}")
                break

    volume_body = sections.get("search_volume", "")
    volume_match = _VOLUME.search(volume_body)
    if not volume_body:
        problems.append("缺少 ## search_volume。写「搜索量: 数字」或「搜索量: 未找到公开数据」。")
    elif volume_match is None:
        if not _MISSING_METRIC.search(volume_body):
            problems.append(
                "## search_volume 里要有「搜索量: 数字」和来源 URL，"
                "或一行「搜索量: 未找到公开数据」。"
            )
    else:
        volume = _scaled_number(volume_match.group(1), volume_match.group(2))
        if not VOLUME_MIN <= volume <= VOLUME_MAX:
            problems.append(
                f"搜索量 {volume} 不在 {VOLUME_MIN}-{VOLUME_MAX}。"
                "换成区间内的词，或改写成「搜索量: 未找到公开数据」。"
            )
        if not _URL.search(volume_body):
            problems.append("写了搜索量数字，就必须附带公开来源 URL。")

    difficulty_body = sections.get("keyword_difficulty", "")
    kd_match = _KD.search(difficulty_body)
    if not difficulty_body:
        problems.append("缺少 ## keyword_difficulty。写「KD: 数字」或「KD: 未找到公开数据」。")
    elif kd_match is None:
        if not _MISSING_METRIC.search(difficulty_body):
            problems.append(
                "## keyword_difficulty 里要有「KD: 数字」和来源 URL，"
                "或一行「KD: 未找到公开数据」。"
            )
    else:
        kd = int(kd_match.group(1))
        if kd >= KD_MAX:
            problems.append(
                f"KD {kd} 不低于 {KD_MAX}。换成更低的词，或改写成「KD: 未找到公开数据」。"
            )
        if not _URL.search(difficulty_body):
            problems.append("写了 KD 数字，就必须附带公开来源 URL。")

    gap_body = sections.get("competitor_keyword_gap", "")
    gap_term = _GAP_TERM.search(_plain(gap_body))
    if not gap_body:
        problems.append("缺少 ## competitor_keyword_gap。写竞品页面、缺口词和来源 URL。")
    elif not _URL.search(gap_body):
        problems.append("竞品缺口必须附带竞品页面 URL。")
    elif gap_term is None or len(gap_term.group(1).strip()) < 4:
        problems.append("竞品缺口要写一行「缺口词: …」，说明对方在排、本站标题没覆盖的词。")

    if required_content_type:
        suggested = sections.get("suggested_content_type", "")
        if required_content_type not in suggested:
            problems.append(
                f"## suggested_content_type 必须写「{required_content_type}」。"
                "这是当前篇数最少的类型，不要改成别的。"
            )

    if problems:
        return False, "选题未通过，请重写研究简报：\n- " + "\n- ".join(problems)
    return True, markdown
