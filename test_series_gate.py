"""系列栏目的核对规则。不调用模型。"""

import unittest

from core.config import ProductConfig
from core.gates import (
    QualityGateSystem,
    build_xhs_note_from_card,
    format_xhs_copy_paste,
    stamp_series_issue,
)
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
        # 单元测试不打真网；存活检查见 test_urlcheck / 下方 mock 用例。
        series_require_live_source=False,
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
        self.assertEqual(coldfact.series_batch_size, 3)
        self.assertEqual(coldfact.series_timezone, "Asia/Shanghai")
        self.assertFalse(coldfact.series_require_live_source)
        self.assertIn("原来如此", coldfact.description)
        scenes = coldfact.keyword_scene_hints
        self.assertIn("感官与错觉", scenes)
        self.assertIn("城市出行与通勤", scenes)
        self.assertIn("穿衣鞋帽与体感", scenes)
        self.assertGreaterEqual(len(scenes), 15)
        voice = KnowledgeBaseLoader(coldfact).load()
        self.assertEqual(voice["type"], "series_voice")
        self.assertIn("带走一句", voice["content"])
        self.assertIn("明确不做", voice["content"])
        self.assertIn("厨房", voice["content"])

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
            "## fact\n其实香蕉由子房发育而来，植物学上算浆果。\n"
            "## why\n这完全颠覆了我们的固有印象。\n"
            "## source_name\n百科\n"
            "## source_url\nhttps://www.britannica.com/plant/banana\n"
        )
        self.assertFalse(ok)
        self.assertIn("夸张词", message)
        self.assertIn("带走一句", message)

    def test_brief_accepts_actually_contrast_and_glued_heading(self):
        """线上失败：但实际上未算落差；重试时 This looks good.## title 解析丢标题。"""
        glass = """## title
老教堂玻璃窗底厚顶薄，不是玻璃流淌了几百年

## fact
很多人认为，老建筑的玻璃窗底部比顶部厚，是因为玻璃本质上是一种流动缓慢的液体。但实际上，玻璃是无定形固体，厚度不均来自古代工艺。

## why
下次别再相信玻璃是流动的液体。

## source_name
The American Ceramic Society
## source_url
https://www.ceramics.org/ceramic-tech-today/glass-ceramics/glass-flow-in-medieval-windows-myth-busted
"""
        ok, text = self.gate.validate_series_brief(glass)
        self.assertTrue(ok, text)
        self.assertIn("## title", text)

        glued = (
            "This looks good.## title\n"
            "金属摸起来更冷，不是因为它本身温度低\n\n"
            "## fact\n"
            "很多人以为金属比木头温度低，但实际上同一房间里两者温度相同，只是导热更快。\n\n"
            "## why\n"
            "下次别再以为金属本身更冷。\n\n"
            "## source_name\nAvanza STEM\n"
            "## source_url\nhttps://example.com/metal-cold\n"
        )
        ok, text = self.gate.validate_series_brief(glued)
        self.assertTrue(ok, text)
        self.assertTrue(text.startswith("## title"))
        self.assertIn("金属摸起来更冷", text)
        self.assertNotIn("This looks good", text)

    def test_brief_rejects_chore_reminder_without_aha(self):
        ok, message = self.gate.validate_series_brief(
            "## title\n洗衣机要定期清洗\n"
            "## fact\n记得定期清洗洗衣机，不然会有异味。\n"
            "## why\n下次记得清洗洗衣机。\n"
            "## source_name\n百科\n"
            "## source_url\nhttps://www.britannica.com/plant/banana\n"
        )
        self.assertFalse(ok)
        self.assertIn("说明书", message)

    def test_brief_rejects_household_saturation(self):
        recent = [
            "第 019 期 · 冰箱冷藏室的温度别只看显示屏",
            "第 022 期 · 洗衣机不会自己洗干净",
            "第 023 期 · 闹钟响后按小睡只会让你更不清醒",
            "第 017 期 · 柔顺剂别乱用毛巾和运动服会罢工",
            "第 008 期 · 周末补觉补不回睡眠债",
        ]
        ok, message = self.gate.validate_series_brief(
            "## title\n冰箱门别开太久\n"
            "## fact\n很多人误以为显示屏准，其实冷藏室各层温度不同。\n"
            "## why\n下次别只看冰箱面板温度。\n"
            "## source_name\n百科\n"
            "## source_url\nhttps://www.britannica.com/plant/banana\n",
            existing_titles=recent,
        )
        self.assertFalse(ok)
        self.assertIn("最近", message)

    def test_brief_rejects_unresolvable_grounding_redirect(self):
        from unittest.mock import patch

        grounding = (
            "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
        )
        with patch(
            "core.urlcheck.resolve_grounding_redirect",
            return_value=(None, "grounding 跳转解不开：HTTP 403。请改填原文 URL。"),
        ):
            ok, message = self.gate.validate_series_brief(
                "## title\n香蕉算浆果\n"
                "## fact\n香蕉由子房发育而来，植物学上算浆果。\n"
                "## why\n下次别把超市分类当成植物学结论。\n"
                "## source_name\n搜索结果\n"
                f"## source_url\n{grounding}\n"
            )
        self.assertFalse(ok)
        self.assertIn("跳转", message)

    def test_brief_rewrites_resolved_grounding_url(self):
        from unittest.mock import patch

        grounding = (
            "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
        )
        real = "https://www.britannica.com/plant/banana"
        with patch(
            "core.urlcheck.resolve_grounding_redirect",
            return_value=(real, f"已解开 grounding 跳转 → {real}"),
        ):
            ok, text = self.gate.validate_series_brief(
                "## title\n香蕉算浆果\n"
                "## fact\n很多人以为香蕉不是浆果，其实它由子房发育而来，植物学上算浆果。\n"
                "## why\n下次别把超市分类当成植物学结论。\n"
                "## source_name\n百科\n"
                f"## source_url\n{grounding}\n"
            )
        self.assertTrue(ok, text)
        self.assertIn(real, text)
        self.assertNotIn("vertexaisearch", text)

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
        self.assertIn("日常误判", coldfact.seed_keywords)
        self.assertIn("每日冷知识", coldfact.publishing_xiaohongshu_tags)
        self.assertIn("日常误判", coldfact.publishing_xiaohongshu_tags)
        self.assertNotIn("人体冷知识", coldfact.publishing_xiaohongshu_tags)

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
#每日冷知识 #日常误判 #生活常识 #厨房
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
        self.assertIn("#日常误判", paste)
        self.assertIn("封面大字：香蕉其实算浆果", paste)

    def test_xhs_parser_accepts_inline_headers_and_card_fallback(self):
        coldfact = ProductConfig.load("coldfact")
        inline = """## cover_title: 大脑不是只用了10%
## cover_hook: 别再信还有 90% 潜能
## title: 人只用了10%大脑？这是谣言
## body
那个「人只用了 10% 大脑」的说法，其实站不住。

清醒或睡觉时，大脑几乎所有区域都在工作，没有大片地方闲着。

带走一句：别再信特殊方法能激活大脑剩余部分。
## tags: #每日冷知识 #日常误判 #生活常识 #大脑
## source_note: 来源：科普中国
"""
        ok, revised = self.gate.validate_xhs_note(
            inline,
            required_tags=coldfact.publishing_xiaohongshu_tags,
        )
        self.assertTrue(ok, revised)

        card = """# 第 005 期 · 大脑不是只用了10%，它一直都在忙

那个说人只用了10%大脑的说法，其实是个老谣言了。科学研究发现，我们大脑几乎所有区域都在持续工作。

带走一句：别再相信那些说你有巨大大脑潜能待开发的说法了。

来源：[科普中国-科学辟谣](https://www.kepuchina.cn/article/articleinfo?business_type=100&classify_id=1130&ar_id=391307)
"""
        built = build_xhs_note_from_card(card, coldfact.publishing_xiaohongshu_tags)
        ok, revised = self.gate.validate_xhs_note(
            built,
            required_tags=coldfact.publishing_xiaohongshu_tags,
        )
        self.assertTrue(ok, revised)
        self.assertIn("## cover_title", revised)
        self.assertIn("#每日冷知识", revised)
        self.assertIn("来源：科普中国-科学辟谣", revised)
        self.assertNotIn("https://", QualityGateSystem._parse_sections(revised)["body"])

    def test_xhs_fallback_strips_bare_url_lines(self):
        coldfact = ProductConfig.load("coldfact")
        card = """# 第 006 期 · 生鸡肉下锅前别再用水冲洗了

冲洗生鸡肉会把细菌溅到水槽。

https://www.cdc.gov/foodsafety/chicken.html

带走一句：下次解冻后直接下锅，别先冲一遍。

来源：[CDC](https://www.cdc.gov/foodsafety/chicken.html)
"""
        built = build_xhs_note_from_card(card, coldfact.publishing_xiaohongshu_tags)
        ok, revised = self.gate.validate_xhs_note(
            built,
            required_tags=coldfact.publishing_xiaohongshu_tags,
        )
        self.assertTrue(ok, revised)
        body = QualityGateSystem._parse_sections(revised)["body"]
        self.assertNotIn("https://", body)
        self.assertIn("冲洗生鸡肉", body)

    def test_brief_rejects_dead_source_when_live_required(self):
        from unittest.mock import patch

        gate = QualityGateSystem(
            ProductConfig(
                id="coldfact",
                name="每日冷知识",
                domain="https://example.com/",
                mode="series",
                word_count_min=80,
                word_count_max=520,
                series_require_live_source=True,
            )
        )
        brief = (
            "## title\n香蕉算浆果\n## fact\n香蕉由子房发育而来，植物学上算浆果。\n"
            "## why\n下次别把超市分类当成植物学结论。\n"
            "## source_name\n百科\n"
            "## source_url\nhttps://www.britannica.com/plant/banana\n"
        )
        with patch(
            "core.urlcheck.probe_source_url",
            return_value=(False, "来源打不开：HTTP 404（最终 https://example.invalid）。"),
        ):
            ok, message = gate.validate_series_brief(brief)
        self.assertFalse(ok)
        self.assertIn("404", message)


if __name__ == "__main__":
    unittest.main()
