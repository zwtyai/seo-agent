"""
知识库加载器
支持多种格式的产品知识库
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ProductConfig


class KnowledgeBaseLoader:
    """知识库加载器 - 支持Markdown和JSON格式"""
    
    def __init__(self, config: ProductConfig):
        self.config = config
        self.kb_path = config.get_knowledge_base_path()
    
    def load(self) -> dict:
        """
        加载知识库
        
        Returns:
            dict: 包含type, content, format等字段的知识库数据
        """
        if not self.kb_path.exists():
            return {
                "type": "placeholder",
                "content": f"【{self.config.name} 知识库占位】\n请在 {self.kb_path} 创建知识库文件",
                "format": "placeholder"
            }
        
        main_file_name = self.config.knowledge_base_main_file
        if not main_file_name:
            # 尝试默认文件
            for default_name in ["capabilities.md", "features.md", "tools_database.json"]:
                if (self.kb_path / default_name).exists():
                    main_file_name = default_name
                    break
        
        if not main_file_name:
            return {
                "type": "placeholder",
                "content": f"【{self.config.name} 知识库占位】\n请在配置中指定 knowledge_base.main_file",
                "format": "placeholder"
            }
        
        main_file = self.kb_path / main_file_name
        
        if not main_file.exists():
            return {
                "type": "placeholder",
                "content": f"【{self.config.name} 知识库占位】\n文件不存在: {main_file}",
                "format": "placeholder"
            }
        
        if main_file.suffix == ".md":
            loaded = self._load_markdown(main_file)
            if self.config.mode == "series":
                loaded["type"] = "series_voice"
            return loaded
        elif main_file.suffix == ".json":
            return self._load_json(main_file)
        else:
            return {
                "type": "unknown",
                "content": f"不支持的文件格式: {main_file.suffix}",
                "format": "unknown"
            }
    
    def _load_markdown(self, path: Path) -> dict:
        """加载Markdown格式的知识库（产品能力描述）"""
        content = path.read_text(encoding="utf-8")
        return {
            "type": "product_capabilities",
            "content": content,
            "format": "markdown",
            "source_file": str(path)
        }
    
    def _load_json(self, path: Path) -> dict:
        """加载JSON格式的知识库（如工具数据库）"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "type": "tool_database",
                "tools": data.get("tools", []),
                "categories": data.get("categories", []),
                "format": "json",
                "source_file": str(path),
                "raw_data": data
            }
        except json.JSONDecodeError as e:
            return {
                "type": "error",
                "content": f"JSON解析失败: {e}",
                "format": "json"
            }
    
    def get_tool_by_name(self, name: str) -> dict | None:
        """获取特定工具信息（导航站专用）"""
        kb = self.load()
        if kb.get("type") != "tool_database":
            return None
        
        name_lower = name.lower()
        for tool in kb.get("tools", []):
            if tool.get("name", "").lower() == name_lower:
                return tool
        
        return None
    
    def search_tools(self, query: str, limit: int = 5) -> list[dict]:
        """搜索工具（导航站专用）"""
        kb = self.load()
        if kb.get("type") != "tool_database":
            return []
        
        query_lower = query.lower()
        results = []
        
        for tool in kb.get("tools", []):
            name = tool.get("name", "").lower()
            desc = tool.get("description", "").lower()
            category = tool.get("category", "").lower()
            
            if query_lower in name or query_lower in desc or query_lower in category:
                results.append(tool)
                if len(results) >= limit:
                    break
        
        return results
