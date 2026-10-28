"""
多渠道发布器
根据产品配置发布到不同渠道
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import ProductConfig


class MultiPublisher:
    """多渠道发布器"""
    
    def __init__(self, config: ProductConfig):
        self.config = config
    
    def publish(self, markdown: str, metadata: dict | None = None) -> dict[str, str]:
        """
        发布到配置的所有渠道
        
        Args:
            markdown: 文章Markdown内容
            metadata: 元数据（如seed_keyword等）
        
        Returns:
            dict: 各渠道的发布结果 {"html": "path", "wordpress": "url", ...}
        """
        metadata = metadata or {}
        results = {}
        
        # 1. 静态HTML（默认启用）
        if self.config.publishing_github_enabled:
            try:
                html_path = self._publish_static_html(markdown, metadata)
                results["html"] = str(html_path)
            except Exception as e:
                results["html_error"] = str(e)

        # 2. WordPress（可选）
        if self.config.publishing_wordpress_enabled:
            try:
                wp_url = self._publish_wordpress(markdown, metadata)
                results["wordpress"] = wp_url
            except Exception as e:
                results["wordpress_error"] = str(e)

        # 3. 小红书文案（只落盘，不自动发帖）
        xhs_note = (metadata.get("xhs_note") or "").strip()
        if self.config.publishing_xiaohongshu_enabled and xhs_note:
            try:
                xhs_path = self._publish_xhs_note(xhs_note, results.get("html", ""))
                results["xiaohongshu"] = str(xhs_path)
            except Exception as e:
                results["xiaohongshu_error"] = str(e)

        return results
    
    def _publish_static_html(self, markdown: str, metadata: dict) -> Path:
        """
        发布为静态HTML
        
        Args:
            markdown: 文章内容
            metadata: 元数据
        
        Returns:
            Path: 生成的HTML文件路径
        """
        # 动态导入，避免循环依赖
        from static_publish import publish_static_page
        
        output_dir = self.config.get_output_dir()
        seed_keyword = metadata.get("seed_keyword", self.config.get_primary_seed_keyword())
        html_path = publish_static_page(
            markdown,
            seed_keyword=seed_keyword,
            site_dir=output_dir,
            site_origin=self.config.publishing_static_site_origin,
            brand_name=self.config.name,
            brand_url=self.config.domain or self.config.seo_internal_links_target_url,
            brand_blurb=self.config.description or self.config.name,
        )
        
        return html_path
    
    def _publish_xhs_note(self, xhs_markdown: str, html_path: str) -> Path:
        """把小红书结构化文案和可粘贴版写到与静态页同目录。"""
        from core.gates import format_xhs_copy_paste

        if html_path:
            base = Path(html_path).with_suffix("")
        else:
            output_dir = self.config.get_output_dir() / "posts"
            output_dir.mkdir(parents=True, exist_ok=True)
            title = self._extract_title(xhs_markdown) or "xhs-note"
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in title)[:40]
            base = output_dir / (safe or "xhs-note")

        structured = base.with_name(base.name + ".xhs.md")
        copy_paste = base.with_name(base.name + ".xhs.txt")
        structured.write_text(xhs_markdown.strip() + "\n", encoding="utf-8")
        copy_paste.write_text(format_xhs_copy_paste(xhs_markdown), encoding="utf-8")
        return copy_paste

    def _publish_wordpress(self, markdown: str, metadata: dict) -> str:
        """
        发布到WordPress
        
        Args:
            markdown: 文章内容
            metadata: 元数据
        
        Returns:
            str: WordPress文章URL
        """
        # 动态导入
        from publish_and_monitor import publish_to_wordpress
        
        # 从markdown提取标题
        title = self._extract_title(markdown)
        
        wp_url = publish_to_wordpress(
            title=title,
            content_markdown=markdown,
            status="publish"
        )
        
        return wp_url or "WordPress发布失败"
    
    @staticmethod
    def _extract_title(markdown: str) -> str:
        """从Markdown提取H1标题"""
        for line in markdown.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return "未命名文章"
