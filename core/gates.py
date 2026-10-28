"""
质量门槛系统
根据产品配置动态验证选题和成稿质量
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ProductConfig


class QualityGateSystem:
    """动态质量门槛系统"""
    
    def __init__(self, config: ProductConfig):
        self.config = config
    
    def validate_keyword_brief(
        self,
        markdown: str,
        existing_titles: list[str] | None = None,
        required_content_type: str | None = None,
    ) -> tuple[bool, str]:
        """
        验证关键词研究简报
        
        Args:
            markdown: 研究简报Markdown
            existing_titles: 已有文章标题列表
        
        Returns:
            (是否通过, 消息)
        """
        if not self.config.keyword_gate_enabled:
            return True, markdown
        
        problems: list[str] = []
        sections = self._parse_sections(markdown)
        
        # 检查关键词
        keyword = sections.get("keyword", "").strip().splitlines()
        keyword_text = keyword[0].strip() if keyword else ""
        
        if not keyword_text:
            problems.append("缺少 ## keyword，写一个长尾关键词。")
        else:
            # 检查是否是问题型（如果配置要求）
            if self.config.keyword_gate_require_question_type:
                if not re.search(r"如何|为什么|怎么|怎样|为何|吗", keyword_text):
                    problems.append(
                        f"「{keyword_text}」不是问题型关键词。"
                        "用如何、为什么、怎么开头。"
                    )
            
            # 整词等于种子词或排除词才拒绝。长尾问句里可以出现这些词。
            folded = self._normalize_text(keyword_text)
            blocked = {self._normalize_text(seed) for seed in self.config.seed_keywords}
            blocked.update(self._normalize_text(item) for item in self.config.keyword_exclusions)
            blocked.discard("")
            if folded in blocked:
                problems.append(
                    f"「{keyword_text}」是大词。改成更具体的长尾词。"
                )
            
            # 检查与已有标题重复
            if self.config.keyword_gate_check_existing_titles and existing_titles:
                for title in existing_titles:
                    if folded and len(folded) >= 4 and folded in self._normalize_text(title):
                        problems.append(f"「{keyword_text}」已经出现在已有标题里：{title}")
                        break
        
        # 检查搜索量
        volume_body = sections.get("search_volume", "")
        if not volume_body:
            problems.append("缺少 ## search_volume。写「搜索量: 数字」或「搜索量: 未找到公开数据」。")
        else:
            volume_match = re.search(
                r"(?:月搜索量|搜索量)\s*[:：]\s*([0-9][0-9,]*(?:\.\d+)?)\s*([kK千])?",
                volume_body
            )
            if volume_match:
                volume = self._scaled_number(volume_match.group(1), volume_match.group(2))
                if not (self.config.search_volume_min <= volume <= self.config.search_volume_max):
                    problems.append(
                        f"搜索量 {volume} 不在 "
                        f"{self.config.search_volume_min}-{self.config.search_volume_max}。"
                        "换成区间内的词，或改写成「搜索量: 未找到公开数据」。"
                    )
                if not re.search(r"https?://\S+", volume_body):
                    problems.append("写了搜索量数字，就必须附带公开来源 URL。")
            elif not re.search(r"未找到公开数据|无法提供", volume_body):
                problems.append(
                    "## search_volume 里要有「搜索量: 数字」和来源 URL，"
                    "或一行「搜索量: 未找到公开数据」。"
                )
        
        # 检查难度
        difficulty_body = sections.get("keyword_difficulty", "")
        if not difficulty_body:
            problems.append("缺少 ## keyword_difficulty。写「KD: 数字」或「KD: 未找到公开数据」。")
        else:
            kd_match = re.search(r"(?:KD|难度)\s*[:：]\s*(\d{1,3})", difficulty_body, re.IGNORECASE)
            if kd_match:
                kd = int(kd_match.group(1))
                if kd >= self.config.keyword_difficulty_max:
                    problems.append(
                        f"KD {kd} 不低于 {self.config.keyword_difficulty_max}。"
                        "换成更低的词，或改写成「KD: 未找到公开数据」。"
                    )
                if not re.search(r"https?://\S+", difficulty_body):
                    problems.append("写了 KD 数字，就必须附带公开来源 URL。")
            elif not re.search(r"未找到公开数据|无法提供", difficulty_body):
                problems.append(
                    "## keyword_difficulty 里要有「KD: 数字」和来源 URL，"
                    "或一行「KD: 未找到公开数据」。"
                )
        
        # 检查竞品缺口
        gap_body = sections.get("competitor_keyword_gap", "")
        if not gap_body:
            problems.append("缺少 ## competitor_keyword_gap。写竞品页面、缺口词和来源 URL。")
        elif not re.search(r"https?://\S+", gap_body):
            problems.append("竞品缺口必须附带竞品页面 URL。")
        else:
            plain_gap = re.sub(r"[*_`]", "", gap_body)
            gap_term = re.search(r"(?:缺口词|关键词)\s*[:：]\s*(.+)", plain_gap)
            if gap_term is None or len(gap_term.group(1).strip()) < 2:
                problems.append("竞品缺口要写一行「缺口词: …」，说明对方在排、本站标题没覆盖的词。")

        suggested = sections.get("suggested_content_type", "")
        if required_content_type and required_content_type not in suggested:
            problems.append(
                f"## suggested_content_type 必须写「{required_content_type}」。"
                "这是当前篇数最少的类型，不要改成别的。"
            )
        
        if problems:
            hint = ""
            if not sections.get("keyword"):
                hint = (
                    "\n每个小节必须是行首单独一行的二级标题，例如「## keyword」。"
                    "关键词写在这个标题下面，不要把关键词当成标题，不要用 ###。"
                )
            return False, "选题未通过，请重写研究简报：\n- " + "\n- ".join(problems) + hint
        
        return True, markdown
    
    def validate_article_claims(self, markdown: str) -> tuple[bool, str]:
        """
        验证文章内容质量
        
        Args:
            markdown: 文章Markdown
        
        Returns:
            (是否通过, 消息)
        """
        if not self.config.claim_gate_enabled:
            return True, ""
        
        problems: list[str] = []
        text = markdown or ""
        
        # 检查禁用词
        forbidden_patterns = [
            ("禁止夸大", self.config.claim_gate_forbidden_hype),
            ("禁止贬低竞品", self.config.claim_gate_forbidden_disparage),
            ("禁止过度营销", self.config.claim_gate_forbidden_marketing),
        ]
        
        for label, patterns in forbidden_patterns:
            if not patterns:
                continue
            
            pattern_str = "|".join(re.escape(p) for p in patterns)
            found = re.findall(pattern_str, text)
            if found:
                unique_found = list(dict.fromkeys(found))  # 去重保持顺序
                problems.append(f"{label}：删掉这些说法：{'、'.join(unique_found[:8])}")
        
        max_mentions = self.config.claim_gate_max_product_mentions
        if max_mentions > 0 and self.config.name:
            mentions = text.count(self.config.name)
            if mentions > max_mentions:
                where = "放在文末一小节" if self.config.product_mention_position == "ending" else "不要再增加"
                problems.append(
                    f"{self.config.name} 出现了 {mentions} 次，全文最多 {max_mentions} 次，{where}。"
                )
        
        if not problems:
            return True, text
        
        return False, (
            "成稿未通过，请改写：\n- "
            + "\n- ".join(problems)
            + "\n产品只复述知识库里的能力。"
            "不要给竞品打分，不要编测试和用户原话。"
        )

    def validate_content_type(self, markdown: str, expected: str) -> tuple[bool, str]:
        """成稿体裁必须是本篇指定的类型。FAQ 至少 5 个问句标题。"""
        if not expected:
            return True, markdown
        from static_publish import _infer_content_type

        actual = _infer_content_type(markdown)
        if actual == expected:
            return True, markdown
        hint = ""
        if expected == "FAQ型":
            hint = " FAQ 至少写 5 个「## Q: 问题？」标题。"
        return False, f"成稿类型必须是{expected}，当前识别为{actual}。{hint}"

    def validate_series_brief(
        self,
        markdown: str,
        existing_titles: list[str] | None = None,
        existing_docs: list[str] | None = None,
    ) -> tuple[bool, str]:
        """系列选题：一条事实、带走一句、一个可打开的原文来源。"""
        problems: list[str] = []
        text = _strip_fence(markdown)
        sections = self._parse_sections(text)

        title = _first_line(sections.get("title", ""))
        fact = _first_line(sections.get("fact", ""))
        why = _first_line(sections.get("why", ""))
        source_url = _first_url(sections.get("source_url", ""))

        if len(title) < 4:
            problems.append("缺少 ## title，用一句话写出这条冷知识的标题。")
        else:
            problems.extend(self._series_title_problems(title))
        if len(fact) < 8:
            problems.append("缺少 ## fact，用自己的话写清这条事实。")
        if len(why) < 4:
            problems.append("缺少 ## why，写一句可带走的小判断。")
        else:
            problems.extend(self._series_takeaway_problems(why))
        if not source_url:
            problems.append("缺少 ## source_url。写一个 http 开头的原文页，找不到就不要交这条。")
        else:
            problems.extend(self._series_source_problems(source_url))

        folded_title = self._strip_issue_prefix(self._normalize_text(title))
        if folded_title and existing_titles:
            for old in existing_titles:
                old_key = self._strip_issue_prefix(self._normalize_text(old))
                if old_key and folded_title == old_key:
                    problems.append(f"标题和已发内容重复：{old}")
                    break

        folded_fact = self._normalize_text(fact)
        if len(folded_fact) >= 8 and existing_docs:
            for doc in existing_docs:
                if folded_fact in self._normalize_text(doc):
                    problems.append("这条事实已经发过，换一条。")
                    break

        if problems:
            return False, "选题未通过，请重找一条：\n- " + "\n- ".join(problems)
        return True, text

    def validate_series_card(
        self,
        markdown: str,
        existing_titles: list[str] | None = None,
        source_url: str = "",
    ) -> tuple[bool, str]:
        """系列成稿：短卡片、带走一句、原文来源、不重复、不吓人。"""
        problems: list[str] = []
        text = _strip_fence(markdown)
        title = ""
        for line in text.splitlines():
            if line.strip().startswith("# "):
                title = line.strip()[2:].strip()
                break
        if not title:
            problems.append("第一行写成 # 标题。")
        else:
            problems.extend(self._series_title_problems(title))

        url = source_url or _first_url(text)
        if not url or url not in text:
            problems.append("正文要保留简报里的来源 URL，写成「来源：[站点名](URL)」。")
        elif url:
            problems.extend(self._series_source_problems(url))

        takeaway = self._series_takeaway_from_card(text)
        if not takeaway:
            problems.append(
                "加一行「带走一句：…」，写下次怎么看或别再信什么。"
                "不要只写「颠覆了固有印象」。"
            )
        else:
            problems.extend(self._series_takeaway_problems(takeaway))

        hearsay = re.findall(r"据说|网传|听说|据传|坊间", text)
        if hearsay:
            problems.append("删掉没有来源的说法：" + "、".join(dict.fromkeys(hearsay)))

        body_len = len(re.sub(r"\s+", "", text))
        if body_len < self.config.word_count_min:
            problems.append(
                f"正文大约 {body_len} 字，少于 {self.config.word_count_min}。把事实写完整，不要只留标题。"
            )
        if body_len > self.config.word_count_max:
            problems.append(
                f"正文大约 {body_len} 字，超过 {self.config.word_count_max}。删到一张卡片，不要写成分析文。"
            )

        folded_title = self._strip_issue_prefix(self._normalize_text(title))
        if folded_title and existing_titles:
            for old in existing_titles:
                old_key = self._strip_issue_prefix(self._normalize_text(old))
                if old_key and folded_title == old_key:
                    problems.append(f"标题和已发内容重复：{old}")
                    break

        if problems:
            return False, "卡片未通过，请改写：\n- " + "\n- ".join(problems)
        return True, text

    def _series_title_problems(self, title: str) -> list[str]:
        hits = re.findall(
            r"震惊|绝了|万亿倍|竟然|太可怕|秒懂|刷屏|你绝对不知道|颠覆认知",
            title or "",
        )
        if hits:
            return ["标题删掉这些夸张词：" + "、".join(dict.fromkeys(hits))]
        return []

    def _series_takeaway_problems(self, takeaway: str) -> list[str]:
        text = (takeaway or "").strip()
        if re.search(
            r"颠覆了?(我们)?(的)?固有印象|完全颠覆|简直颠覆|颠覆了我们从小|反常识感叹",
            text,
        ):
            return [
                "「带走一句」不要只感叹颠覆印象。"
                "改成下次怎么看、别再信什么，例如「别再按舌尖分区教味觉」。"
            ]
        if not re.search(
            r"下次|别再|不要再|可以|其实|不必|不用|别把|别信|留意|注意|改成|当成",
            text,
        ):
            return [
                "「带走一句」要具体到日常判断。"
                "用「下次 / 别再 / 可以」这类说法，不要空赞叹。"
            ]
        return []

    def _series_source_problems(self, url: str) -> list[str]:
        if "vertexaisearch.cloud.google.com/grounding-api-redirect" in (url or ""):
            return ["来源不要用 grounding 跳转链。换成百科、论文或媒体的原文 URL。"]
        return []

    @staticmethod
    def _series_takeaway_from_card(markdown: str) -> str:
        """从卡片正文取出「带走一句」或旧版「为什么值得说」。"""
        for line in (markdown or "").splitlines():
            stripped = line.strip()
            for prefix in ("带走一句：", "带走一句:", "为什么值得说：", "为什么值得说:"):
                if stripped.startswith(prefix):
                    return stripped[len(prefix):].strip()
        return ""

    @staticmethod
    def _strip_issue_prefix(text: str) -> str:
        return re.sub(r"^第\d+期[·•:：\-]*", "", text or "")

    @staticmethod
    def _parse_sections(markdown: str) -> dict[str, str]:
        """解析Markdown sections"""
        parts = re.split(r"(?m)^##\s+", markdown or "")
        sections: dict[str, str] = {}
        for part in parts[1:]:
            lines = part.splitlines()
            if not lines:
                continue
            name = re.sub(r"（.*?）|\(.*?\)", "", lines[0]).strip().lower()
            sections[name] = "\n".join(lines[1:]).strip()
        return sections
    
    @staticmethod
    def _normalize_text(text: str) -> str:
        """规范化文本用于比较"""
        return re.sub(r"[\s\-—_，。、""\"'？?]+", "", text).lower()
    
    @staticmethod
    def _scaled_number(raw: str, suffix: str | None) -> int:
        """转换带单位的数字"""
        number = float(raw.replace(",", ""))
        if suffix:
            number *= 1000
        return int(round(number))


_FENCE_RE = re.compile(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", re.DOTALL)
_ISSUE_PREFIX_RE = re.compile(r"^第\s*\d+\s*期\s*[·•:：\-]\s*")


def _strip_fence(text: str) -> str:
    stripped = (text or "").strip()
    match = _FENCE_RE.match(stripped)
    return match.group(1).strip() if match else stripped


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        cleaned = line.strip().strip("*").strip()
        if cleaned:
            return cleaned
    return ""


def _first_url(text: str) -> str:
    match = re.search(r"https?://[^\s)>\]]+", text or "")
    if not match:
        return ""
    return match.group(0).rstrip(".,，。")


def stamp_series_issue(markdown: str, issue: int) -> str:
    """把期号写进 H1。模型写错编号时，以已发布篇数算出的期号为准。"""
    text = _strip_fence(markdown)
    lines = text.splitlines()
    label = f"第 {issue:03d} 期"
    for index, line in enumerate(lines):
        if not line.strip().startswith("# "):
            continue
        title = _ISSUE_PREFIX_RE.sub("", line.strip()[2:].strip()).strip()
        lines[index] = f"# {label} · {title}" if title else f"# {label}"
        return "\n".join(lines).strip() + "\n"
    return f"# {label}\n\n{text}\n"
