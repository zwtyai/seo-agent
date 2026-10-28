"""
产品配置加载器
从YAML文件加载产品的SEO策略配置
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ProductConfig:
    """产品SEO配置"""
    
    # 基础信息
    id: str
    name: str
    domain: str
    description: str = ""
    # seo：挖词写长文。series：固定栏目，一条来源一张卡片。
    mode: str = "seo"
    
    # 关键词策略
    seed_keywords: list[str] = field(default_factory=list)
    keyword_types: list[str] = field(default_factory=list)
    search_volume_min: int = 200
    search_volume_max: int = 2000
    keyword_difficulty_max: int = 30
    keyword_exclusions: list[str] = field(default_factory=list)
    keyword_scene_hints: list[str] = field(default_factory=list)
    
    # 内容策略
    content_types: list[dict] = field(default_factory=list)
    word_count_min: int = 800
    word_count_max: int = 1800
    evidence_min_urls: int = 3
    evidence_min_data_points: int = 1
    product_mention_max: int = 4
    product_mention_position: str = "ending"
    
    # 知识库
    knowledge_base_source: str = ""
    knowledge_base_main_file: str = ""
    knowledge_base_mandatory_mentions: list[str] = field(default_factory=list)
    
    # 质量门槛
    keyword_gate_enabled: bool = True
    keyword_gate_require_question_type: bool = True
    keyword_gate_check_existing_titles: bool = True
    
    claim_gate_enabled: bool = True
    claim_gate_forbidden_hype: list[str] = field(default_factory=list)
    claim_gate_forbidden_disparage: list[str] = field(default_factory=list)
    claim_gate_forbidden_marketing: list[str] = field(default_factory=list)
    claim_gate_max_product_mentions: int = 4
    
    # SEO配置
    seo_keyword_density_min: float = 0.015
    seo_keyword_density_max: float = 0.025
    seo_internal_links_enabled: bool = True
    seo_internal_links_anchor_text: str = ""
    seo_internal_links_target_url: str = ""
    
    # 发布配置
    publishing_output_dir: str = ""
    publishing_static_site_origin: str = ""
    publishing_github_enabled: bool = True
    publishing_github_repo: str = ""
    publishing_wordpress_enabled: bool = False
    # 只生成小红书文案，不自动发帖。
    publishing_xiaohongshu_enabled: bool = False
    publishing_xiaohongshu_tags: list[str] = field(default_factory=list)
    
    # 监控配置
    monitoring_gsc_enabled: bool = False
    monitoring_gsc_site_url: str = ""
    monitoring_gsc_lookback_days: int = 7
    
    # Agent配置
    agent_researcher_temperature: float = 0.7
    agent_researcher_use_grounding: bool = True
    agent_writer_temperature: float = 0.75
    agent_writer_style: str = "professional"
    agent_editor_temperature: float = 0.4
    agent_editor_strictness: str = "high"
    
    # 原始配置（保留完整YAML数据）
    _raw_config: dict = field(default_factory=dict, repr=False)
    
    @classmethod
    def load(cls, product_id: str) -> ProductConfig:
        """
        从YAML配置文件加载产品配置
        
        Args:
            product_id: 产品ID，如 "yibelin", "tranzify", "toolnav"
        
        Returns:
            ProductConfig实例
        """
        config_file = _REPO_ROOT / "configs" / f"{product_id}.yaml"
        
        if not config_file.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {config_file}\n"
                f"请创建 configs/{product_id}.yaml"
            )
        
        with open(config_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        return cls._from_dict(product_id, data)
    
    @classmethod
    def _from_dict(cls, product_id: str, data: dict) -> ProductConfig:
        """从字典创建ProductConfig"""
        product = data.get("product", {})
        keyword_strategy = data.get("keyword_strategy", {})
        content_strategy = data.get("content_strategy", {})
        knowledge_base = data.get("knowledge_base", {})
        quality_gates = data.get("quality_gates", {})
        keyword_gate = quality_gates.get("keyword_gate", {})
        claim_gate = quality_gates.get("claim_gate", {})
        seo = data.get("seo", {})
        keyword_density = seo.get("keyword_density", {})
        internal_links = seo.get("internal_links", {})
        publishing = data.get("publishing", {})
        github = publishing.get("github", {})
        wordpress = publishing.get("wordpress", {})
        monitoring = data.get("monitoring", {})
        gsc = monitoring.get("gsc", {})
        agents = data.get("agents", {})
        researcher = agents.get("researcher", {})
        writer = agents.get("writer", {})
        editor = agents.get("editor", {})
        
        search_volume = keyword_strategy.get("search_volume", {})
        keyword_difficulty = keyword_strategy.get("keyword_difficulty", {})
        word_count = content_strategy.get("word_count", {})
        evidence_req = content_strategy.get("evidence_requirements", {})
        product_mention = content_strategy.get("product_mention", {})
        
        return cls(
            # 基础信息
            id=product_id,
            name=product.get("name", product_id),
            domain=product.get("domain", ""),
            description=product.get("description", ""),
            mode=str(product.get("mode") or "seo").strip().lower(),
            
            # 关键词策略
            seed_keywords=keyword_strategy.get("seed_keywords", []),
            keyword_types=keyword_strategy.get("keyword_types", []),
            search_volume_min=search_volume.get("min", 200),
            search_volume_max=search_volume.get("max", 2000),
            keyword_difficulty_max=keyword_difficulty.get("max", 30),
            keyword_exclusions=keyword_strategy.get("exclusions", []),
            keyword_scene_hints=keyword_strategy.get("scene_hints", []),
            
            # 内容策略
            content_types=content_strategy.get("types", []),
            word_count_min=word_count.get("min", 800),
            word_count_max=word_count.get("max", 1800),
            evidence_min_urls=evidence_req.get("min_urls", 3),
            evidence_min_data_points=evidence_req.get("min_data_points", 1),
            product_mention_max=product_mention.get("max_count", 4),
            product_mention_position=product_mention.get("position", "ending"),
            
            # 知识库
            knowledge_base_source=knowledge_base.get("source", ""),
            knowledge_base_main_file=knowledge_base.get("main_file", ""),
            knowledge_base_mandatory_mentions=knowledge_base.get("mandatory_mentions", []),
            
            # 质量门槛
            keyword_gate_enabled=keyword_gate.get("enabled", True),
            keyword_gate_require_question_type=keyword_gate.get("require_question_type", True),
            keyword_gate_check_existing_titles=keyword_gate.get("check_existing_titles", True),
            
            claim_gate_enabled=claim_gate.get("enabled", True),
            claim_gate_forbidden_hype=claim_gate.get("forbidden_hype", []),
            claim_gate_forbidden_disparage=claim_gate.get("forbidden_disparage", []),
            claim_gate_forbidden_marketing=claim_gate.get("forbidden_marketing", []),
            claim_gate_max_product_mentions=claim_gate.get("max_product_mentions", 4),
            
            # SEO配置
            seo_keyword_density_min=keyword_density.get("min", 0.015),
            seo_keyword_density_max=keyword_density.get("max", 0.025),
            seo_internal_links_enabled=internal_links.get("enabled", True),
            seo_internal_links_anchor_text=internal_links.get("anchor_text", ""),
            seo_internal_links_target_url=internal_links.get("target_url", ""),
            
            # 发布配置
            publishing_output_dir=publishing.get("output_dir", f"outputs/{product_id}/docs/"),
            publishing_static_site_origin=publishing.get("static_site_origin", ""),
            publishing_github_enabled=github.get("enabled", True),
            publishing_github_repo=github.get("repo", ""),
            publishing_wordpress_enabled=wordpress.get("enabled", False),
            publishing_xiaohongshu_enabled=publishing.get("xiaohongshu", {}).get("enabled", False),
            publishing_xiaohongshu_tags=list(
                publishing.get("xiaohongshu", {}).get("tags") or []
            ),
            
            # 监控配置
            monitoring_gsc_enabled=gsc.get("enabled", False),
            monitoring_gsc_site_url=gsc.get("site_url", ""),
            monitoring_gsc_lookback_days=gsc.get("lookback_days", 7),
            
            # Agent配置
            agent_researcher_temperature=researcher.get("temperature", 0.7),
            agent_researcher_use_grounding=researcher.get("use_grounding", True),
            agent_writer_temperature=writer.get("temperature", 0.75),
            agent_writer_style=writer.get("style", "professional"),
            agent_editor_temperature=editor.get("temperature", 0.4),
            agent_editor_strictness=editor.get("strictness", "high"),
            
            # 保留原始配置
            _raw_config=data,
        )
    
    def get_primary_seed_keyword(self) -> str:
        """获取主种子关键词"""
        if self.seed_keywords:
            return self.seed_keywords[0]
        return self.name

    def choose_seed_keyword(self, documents: list[str]) -> str:
        """按已发布篇数轮换种子词。没有文章时用配置里的第一个。"""
        seeds = [seed for seed in self.seed_keywords if seed] or [self.name]
        return seeds[len(documents) % len(seeds)]
    
    def get_content_type_priority(self) -> list[str]:
        """按优先级排序的内容类型名称"""
        if not self.content_types:
            return []
        sorted_types = sorted(self.content_types, key=lambda x: x.get("priority", 99))
        return [t.get("name", "") for t in sorted_types]
    
    def get_knowledge_base_path(self) -> Path:
        """获取知识库目录路径"""
        if self.knowledge_base_source:
            return _REPO_ROOT / self.knowledge_base_source
        return _REPO_ROOT / "knowledge_base" / self.id
    
    def get_output_dir(self) -> Path:
        """获取输出目录路径"""
        return _REPO_ROOT / self.publishing_output_dir
    
    def get_run_dir(self) -> Path:
        """获取运行中间文件目录"""
        return _REPO_ROOT / "runs" / self.id / "latest"
    
    def get_raw_config(self, key: str, default: Any = None) -> Any:
        """获取原始配置中的任意键值"""
        keys = key.split(".")
        value = self._raw_config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value if value is not None else default


def list_available_products() -> list[str]:
    """列出所有可用的产品配置"""
    configs_dir = _REPO_ROOT / "configs"
    if not configs_dir.exists():
        return []
    
    products = []
    for config_file in configs_dir.glob("*.yaml"):
        if config_file.name not in ["product_template.yaml"]:
            products.append(config_file.stem)
    
    return sorted(products)
