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
