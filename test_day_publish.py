"""系列按天目录与批量落盘。不调用模型。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from static_publish import (
    list_published_titles,
    publish_static_page,
    rebuild_index,
    series_day_key,
)


class DayPublishTest(unittest.TestCase):
    def test_series_day_key_is_iso_date(self):
        day = series_day_key("Asia/Shanghai")
        self.assertRegex(day, r"^\d{4}-\d{2}-\d{2}$")

    def test_publish_three_under_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            day = "2026-10-31"
            paths = []
            for slot, title in enumerate(
                ("舌头没有味觉地图", "洗碗机前刮掉残渣就好", "掰手指不会导致关节炎"),
                start=1,
            ):
                md = (
                    f"# 第 {slot:03d} 期 · {title}\n\n"
                    f"事实段落足够长，用来撑过列表。带走一句：下次注意。\n\n"
                    f"来源：[例](https://example.com/{slot})\n"
                )
                paths.append(
                    publish_static_page(
                        md,
                        seed_keyword=title,
                        site_dir=site,
                        site_origin="https://example.com/series/coldfact",
                        brand_name="每日冷知识",
                        brand_url="https://example.com/series/coldfact/",
                        brand_blurb="每天三条",
                        day=day,
                        slot=slot,
                    )
                )

            rels = [p.relative_to(site).as_posix() for p in paths]
            self.assertTrue(all(r.startswith("2026-10-31/0") for r in rels))
            self.assertEqual(
                [Path(r).name[:3] for r in rels],
                ["01-", "02-", "03-"],
            )
            for p in paths:
                self.assertTrue(p.with_suffix(".md").is_file())

            titles = list_published_titles(site)
            self.assertEqual(len(titles), 3)

            index = rebuild_index(site)
            html = index.read_text(encoding="utf-8")
            self.assertIn("<h2>2026-10-31</h2>", html)
            self.assertIn("2026-10-31/01-", html)
            self.assertIn("2026-10-31/03-", html)

            sitemap = (site / "sitemap.xml").read_text(encoding="utf-8")
            self.assertIn("/2026-10-31/01-", sitemap)


if __name__ == "__main__":
    unittest.main()
