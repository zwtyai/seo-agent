"""系列栏目的核对规则。不调用模型。"""

import unittest

from core.config import ProductConfig
from core.gates import QualityGateSystem, format_xhs_copy_paste, stamp_series_issue
from core.knowledge_base import KnowledgeBaseLoader


def _config() -> ProductConfig:
    return ProductConfig(
        id="coldfact",
        name="每日冷知识",
        domain="https://example.com/series/coldfact/",
        mode="series",
        word_count_min=80,
        word_count_max=520,
        knowledge_base_source="knowledge_base/coldfact/",
        knowledge_base_main_file="voice.md",
    )


def _card(
    title: str = "香蕉在植物学里算浆果",
    takeaway: str = "下次别把超市分类当成植物学结论。",
    source: str = "https://www.britannica.com/plant/banana",
) -> str:
    return f"""# {title}

植物学里，香蕉由一朵花的子房发育而来，因此被算作浆果。草莓的可食部分主要来自花托，不算浆果。

带走一句：{takeaway}

来源：[不列颠百科]({source})
"""


class SeriesGateTest(unittest.TestCase):
    def setUp(self):
        self.gate = QualityGateSystem(_config())

    def test_loaded_products_keep_their_mode(self):
        coldfact = ProductConfig.load("coldfact")
        yibelin = ProductConfig.load("yibelin")
        self.assertEqual(coldfact.mode, "series")
        self.assertEqual(yibelin.mode, "seo")
        self.assertEqual(coldfact.publishing_output_dir, "docs/series/coldfact/")
        voice = KnowledgeBaseLoader(coldfact).load()
        self.assertEqual(voice["type"], "series_voice")
        self.assertIn("带走一句", voice["content"])

    def test_brief_requires_a_real_url(self):
        ok, message = self.gate.validate_series_brief(
            "## title\n香蕉算浆果\n## fact\n香蕉由子房发育而来，植物学上算浆果。\n"
            "## why\n下次别把超市分类当成植物学结论。\n"
            "## source_name\n百科\n## source_url\n未找到\n"
        )
        self.assertFalse(ok)
        self.assertIn("source_url", message)

    def test_brief_rejects_empty_takeaway_and_hype_title(self):
        ok, message = self.gate.validate_series_brief(
            "## title\n香蕉灵敏万亿倍\n"
            "## fact\n香蕉由子房发育而来，植物学上算浆果。\n"
            "## why\n这完全颠覆了我们的固有印象。\n"
            "## source_name\n百科\n"
            "## source_url\nhttps://www.britannica.com/plant/banana\n"
        )
        self.assertFalse(ok)
        self.assertIn("夸张词", message)
        self.assertIn("带走一句", message)

    def test_brief_rejects_grounding_redirect(self):
        ok, message = self.gate.validate_series_brief(
            "## title\n香蕉算浆果\n"
            "## fact\n香蕉由子房发育而来，植物学上算浆果。\n"
            "## why\n下次别把超市分类当成植物学结论。\n"
            "## source_name\n搜索结果\n"
            "## source_url\nhttps://vertexaisearch.cloud.google.com/grounding-api-redirect/abc\n"
        )
        self.assertFalse(ok)
        self.assertIn("跳转", message)

    def test_brief_rejects_a_fact_already_published(self):
        fact = "香蕉由子房发育而来，植物学上算浆果。"
        ok, message = self.gate.validate_series_brief(
            f"## title\n香蕉算浆果\n## fact\n{fact}\n"
            "## why\n下次别把超市分类当成植物学结论。\n"
            "## source_name\n百科\n## source_url\nhttps://www.britannica.com/plant/banana\n",
            existing_docs=[f"# 旧文\n\n{fact}\n"],
        )
        self.assertFalse(ok)
        self.assertIn("已经发过", message)

    def test_card_rejects_hearsay_and_missing_source(self):
        ok, message = self.gate.validate_series_card(
            _card(takeaway="据说下次草莓不是水果。")
        )
        self.assertFalse(ok)
        self.assertIn("据说", message)

        thin = "# 太短\n\n没有链接。\n"
        ok, message = self.gate.validate_series_card(thin, source_url="https://example.com/a")
        self.assertFalse(ok)
        self.assertIn("来源", message)

    def test_card_rejects_empty_takeaway(self):
        ok, message = self.gate.validate_series_card(
            _card(takeaway="这完全颠覆了我们的固有印象。")
        )
        self.assertFalse(ok)
        self.assertIn("带走一句", message)

    def test_card_passes_and_issue_number_is_stamped(self):
        source = "https://www.britannica.com/plant/banana"
        ok, revised = self.gate.validate_series_card(_card(), source_url=source)
        self.assertTrue(ok, revised)
        stamped = stamp_series_issue(revised, 3)
        self.assertTrue(stamped.startswith("# 第 003 期 · 香蕉在植物学里算浆果"))
        again = stamp_series_issue("# 第 9 期 · 香蕉在植物学里算浆果\n\n正文\n", 3)
        self.assertTrue(again.startswith("# 第 003 期 · 香蕉在植物学里算浆果"))

        duplicate, message = self.gate.validate_series_card(
            _card(),
            existing_titles=["第 001 期 · 香蕉在植物学里算浆果"],
            source_url=source,
        )
        self.assertFalse(duplicate)
        self.assertIn("重复", message)

    def test_xhs_note_requires_cover_takeaway_and_tags(self):
        coldfact = ProductConfig.load("coldfact")
        self.assertTrue(coldfact.publishing_xiaohongshu_enabled)
        self.assertIn("每日冷知识", coldfact.publishing_xiaohongshu_tags)

        bad = """## cover_title
震惊万亿倍香蕉
## cover_hook
你绝对想不到
## title
香蕉冷知识
## body
香蕉很好吃 https://example.com
## tags
#水果
## source_note
来源：https://www.britannica.com/plant/banana
"""
        ok, message = self.gate.validate_xhs_note(
            bad,
            required_tags=coldfact.publishing_xiaohongshu_tags,
        )
        self.assertFalse(ok)
        self.assertIn("夸张词", message)
        self.assertIn("外链", message)
        self.assertIn("#每日冷知识", message)
        self.assertIn("source_note", message)

        good = """## cover_title
香蕉其实算浆果
## cover_hook
草莓反而不是
## title
香蕉算浆果，草莓不算
## body
超市里的水果分类，和植物学不是一套标准。

香蕉由一朵花的子房发育而来，植物学上算浆果；草莓的可食部分主要来自花托。

带走一句：下次别把超市分类当成植物学结论。
## tags
#每日冷知识 #人体冷知识 #冷知识分享 #植物冷知识
## source_note
来源：不列颠百科
"""
        ok, revised = self.gate.validate_xhs_note(
            good,
            required_tags=coldfact.publishing_xiaohongshu_tags,
        )
        self.assertTrue(ok, revised)
        paste = format_xhs_copy_paste(revised)
        self.assertIn("香蕉算浆果，草莓不算", paste)
        self.assertIn("#每日冷知识", paste)
        self.assertIn("封面大字：香蕉其实算浆果", paste)


if __name__ == "__main__":
    unittest.main()
