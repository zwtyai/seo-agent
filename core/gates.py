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
