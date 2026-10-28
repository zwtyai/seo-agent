"""
Agent工厂
根据产品配置动态创建定制化的CrewAI Agent
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from crewai import Agent
from crewai.tools import tool

if TYPE_CHECKING:
    from .config import ProductConfig
    from .knowledge_base import KnowledgeBaseLoader


class AgentFactory:
    """Agent工厂 - 根据产品配置创建定制化Agent"""
    
    def __init__(
        self,
        config: ProductConfig,
        kb_loader: Any,
        researcher_llm: Any,
        writer_llm: Any,
        editor_llm: Any,
    ):
        """
        Args:
            config: 产品配置
            kb_loader: KnowledgeBaseLoader实例
            researcher_llm / writer_llm / editor_llm: 三个岗位各自的模型温度
        """
        self.config = config
        self.kb_loader = kb_loader
        self.researcher_llm = researcher_llm
        self.writer_llm = writer_llm
        self.editor_llm = editor_llm
    
    def create_researcher(self, seed: str | None = None) -> Agent:
        """创建研究员Agent"""
        self._seed = seed or self.config.get_primary_seed_keyword()
        goal = self._generate_researcher_goal()
        backstory = self._generate_researcher_backstory()
        
        role = (
            f"{self.config.name} 选题编辑"
            if self.config.mode == "series"
            else f"{self.config.name} 关键词研究员 (Keyword Researcher)"
        )
        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            llm=self.researcher_llm,
            verbose=True,
        )
    
    def create_writer(self) -> Agent:
        """创建写作Agent"""
        kb = self.kb_loader.load()
        tools = self._create_writer_tools(kb)
        
        goal = self._generate_writer_goal()
        backstory = self._generate_writer_backstory()
        
        role = (
            f"{self.config.name} 栏目作者"
            if self.config.mode == "series"
            else f"{self.config.name} 内容创作者 (Technical Content Writer)"
        )
        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            tools=tools,
            llm=self.writer_llm,
            verbose=True,
        )
    
    def create_editor(self) -> Agent:
        """创建编辑Agent"""
        tools = self._create_editor_tools()
        
        goal = self._generate_editor_goal()
        backstory = self._generate_editor_backstory()
        
        return Agent(
            role=f"{self.config.name} SEO 质量把控总编 (SEO Editor)",
            goal=goal,
            backstory=backstory,
            tools=tools,
            llm=self.editor_llm,
            verbose=True,
        )
    
    # ==================== 研究员 ====================
    
    def _generate_researcher_goal(self) -> str:
        """动态生成研究员goal"""
        if self.config.mode == "series":
            return (
                f"为栏目「{self.config.name}」找 1 条还没发过的冷知识。"
                "必须有可打开的来源 URL。找不到就不要编。"
            )
        seed = getattr(self, "_seed", None) or self.config.get_primary_seed_keyword()
        types_str = "、".join(self.config.keyword_types) if self.config.keyword_types else "长尾"
        
        return (
            f"借助 Google Search Grounding，为 {seed} 选出 **1 个{types_str}关键词**；"
            f"有公开数字时搜索量要在 {self.config.search_volume_min}-{self.config.search_volume_max}、"
            f"KD 要低于 {self.config.keyword_difficulty_max}，并附来源 URL；"
            f"公开结果里没有这两个数就写「未找到公开数据」，禁止编造"
        )
    
    def _generate_researcher_backstory(self) -> str:
        """动态生成研究员backstory"""
        if self.config.mode == "series":
            return f"""你为固定栏目「{self.config.name}」找素材，不写 SEO 长文，也不做竞品分析。

规则：
1. 用 Google Search Grounding 找 1 条具体、可核对的事实。
2. 来源必须是这次搜索里打开过的页面。没有页面就写「未找到」，不要编 URL。
3. 用自己的话概括，不要整段抄原文。
4. 不要写搜索量、KD、用户痛点或产品推荐。
5. 交卷只用这些行首二级标题：title、fact、why、source_name、source_url。"""
        exclusions_str = "、".join(self.config.keyword_exclusions)
        scene = "、".join(self.config.keyword_scene_hints)
        scene_line = f"场景要具体（{scene}）。" if scene else "场景要具体。"
        question_line = (
            "用「如何 / 为什么 / 怎么」开头。"
            if self.config.keyword_gate_require_question_type
            else "写成具体长尾，不要交大词。"
        )
        
        base_backstory = f"""你是一位数据驱动的 SEO 研究专家，接入了 Gemini 的 Google Search Grounding。

你的职责是先选定一个值得写的长尾词，再为它找证据。选词规则：

1. **长尾关键词**：{question_line}围绕「{getattr(self, "_seed", None) or self.config.get_primary_seed_keyword()}」，但避开把这些大词原样交出来：{exclusions_str or '无'}
   一篇只锁 1 个词。{scene_line}

2. **证据为王**：必须找到至少 {self.config.evidence_min_urls} 个真实用户抱怨的 URL（知乎、Reddit、论坛、博客、竞品评论），
   每个 URL 需提取 50-100 字的核心抱怨。优先选择带具体场景和情绪的原话。

3. **量化数据支撑**：尽可能找到数据（用户数量、错误率、时间成本、市场调研等），
   让内容更有说服力。如果找不到现成数据，可以统计用户抱怨的频次。

4. **竞品页面**：只记录对方页面 URL 和用户原话。不要写「竞品很差」这类结论。

5. **交卷格式**：简报只用行首的二级标题。标题名必须是 keyword、search_volume、keyword_difficulty、competitor_keyword_gap、user_persona、pain_points、quantitative_data、evidence_urls、suggested_content_type、suggested_h1、unique_angle。
   关键词写在「## keyword」下面的第一行。不要把关键词写成 # 或 ## 标题。不要用 ###。

**禁止**凭空编造数据、URL 或用户评价。如果 Grounding 没有返回足够证据，明确说明，
而不是伪造。宁可推迟生产，也不能输出低质量素材。"""
        
        return base_backstory
    
    # ==================== 写作 ====================
    
    def _generate_writer_goal(self) -> str:
        """动态生成写作goal"""
        word_range = f"{self.config.word_count_min}-{self.config.word_count_max}"
        if self.config.mode == "series":
            return (
                f"把简报里的那一条事实改写成「{self.config.name}」卡片，"
                f"{word_range} 字，保留来源链接，不要展开证明。"
            )
        
        if self.config.product_mention_max == 0:
            # 导航站模式
            return (
                f"把研究简报里的那个主题写清楚：{word_range} 字；"
                "客观中立，不推销特定产品，保持专业性"
            )
        else:
            # 产品模式
            return (
                f"把研究简报里的那一个问题写清楚：它为何发生、表现是什么、证据是什么；"
                f"H1 贴近这个痛点，不得与已有标题雷同；"
                f"「{self.config.name}」全文最多 {self.config.product_mention_max} 次，只放在文末，{word_range} 字"
            )
    
    def _generate_writer_backstory(self) -> str:
        """动态生成写作backstory"""
        if self.config.mode == "series":
            return f"""你写栏目「{self.config.name}」，不是评测，也不是教程。

一张卡片只有四段：标题、事实、为什么值得说、来源。
口气短、好奇，像跟朋友说一件刚刚核对过的事。
不要写「在当今」「综上所述」，不要写据说、网传。
不要加搜索分析、步骤清单或产品推荐。事实和 URL 只能来自简报。"""
        types = self.config.get_content_type_priority()
        types_str = "\n".join(f"- {name}" for name in types) if types else "- 专业文章"
        
        if self.config.product_mention_max == 0:
            # 导航站模式
            return f"""你是一位经验丰富的内容创作者，擅长多种内容类型：

{types_str}

写作原则：
1. 文风专业、客观中立
2. 必须引用研究员报告中的真实数据、URL、用户反馈
3. 禁止 AI 套话（如「在当今时代」「综上所述」「赋能」「助力」）
4. 根据研究员建议的内容类型选择对应模板
5. 不推销任何特定产品，保持中立性"""
        else:
            # 产品模式
            return f"""你是一位经验丰富的内容创作者，擅长多种内容类型：

**深度分析型**：把问题的机制写清楚，引用简报里的数据和 URL。
**对比评测型**：只对比简报里有 URL 的事实，不打分，不宣布谁赢了。
**教程指南型**：步骤写读者能做的核对与处理，产品最多是其中一步。
**FAQ型**：每个答案先回答问题本身。
**案例故事型**：只复述简报里已有 URL 的用户抱怨，不编人物和结局。

可写的类型：
{types_str}

写作原则：
1. 文风硬核、禁止 AI 套话（如「在当今时代」「综上所述」「赋能」「助力」堆砌）
2. 写作前必须调用知识库工具，产品句子只复述返回的原文
3. 必须引用研究员报告中的真实数据、URL、用户抱怨
4. 只套本篇指定的那一种模板
5. 正文主体是问题本身，避免与已有文章雷同
6. {self.config.name} 全文最多 {self.config.product_mention_max} 次，只放在文末一小节"""
    
    def _create_writer_tools(self, kb: dict) -> list:
        """创建写作工具"""
        if self.config.mode == "series":
            return [self._make_voice_tool(kb)]

        kb_type = kb.get("type", "placeholder")
        
        if kb_type == "product_capabilities":
            return [self._make_product_kb_tool(kb)]
        elif kb_type == "tool_database":
            return [self._make_tool_db_tool(kb)]
        elif kb_type == "placeholder":
            return [self._make_placeholder_tool(kb)]
        else:
            return []
    
    def _make_voice_tool(self, kb: dict):
        """栏目语气。系列卡片照这个口气写，不复述成产品能力。"""
        config = self.config
        voice = kb.get("content", "")

        @tool(f"{config.id}_voice")
        def series_voice_tool(query: str) -> str:
            """返回栏目语气和卡片格式。写作时照这个口气，不要写成产品介绍。"""
            return f"【{config.name} 栏目语气】\n{voice}"

        return series_voice_tool

    def _make_product_kb_tool(self, kb: dict):
        """创建产品知识库工具"""
        config = self.config
        kb_content = kb.get("content", "")
        
        @tool(f"{config.id}_knowledge_base")
        def product_knowledge_base_tool(query: str) -> str:
            """返回已确认的产品能力。正文只能复述这些句子，不能加码，也不能拿来贬低其他工具。"""
            mandatory = "\n".join(f"- {m}" for m in config.knowledge_base_mandatory_mentions)
            return (
                f"【{config.name}产品能力（只许复述，不许加码，不许拿来对比贬低）】：\n"
                f"{kb_content}\n\n"
                f"【必须提及的点】：\n{mandatory if mandatory else '（无特殊要求）'}"
            )
        
        return product_knowledge_base_tool
    
    def _make_tool_db_tool(self, kb: dict):
        """创建工具数据库工具（导航站）"""
        @tool("tool_database")
        def tool_database_tool(query: str) -> str:
            """查询工具数据库，返回工具的客观信息。"""
            query_lower = query.lower()
            results = []
            
            for tool_info in kb.get("tools", [])[:10]:
                name = tool_info.get("name", "")
                if query_lower in name.lower():
                    features = tool_info.get("features", [])
                    features_str = "、".join(features[:5]) if features else "无"
                    results.append(
                        f"- **{name}**: {tool_info.get('description', '')}\n"
                        f"  功能: {features_str}\n"
                        f"  价格: {tool_info.get('pricing', 'N/A')}"
                    )
                if len(results) >= 5:
                    break
            
            if not results:
                return f"未找到匹配「{query}」的工具。请尝试其他关键词。"
            
            return f"【工具数据库查询结果】：\n\n" + "\n\n".join(results)
        
        return tool_database_tool
    
    def _make_placeholder_tool(self, kb: dict):
        """创建占位工具"""
        config = self.config
        placeholder_msg = kb.get("content", "知识库未配置")
        
        @tool(f"{config.id}_placeholder")
        def placeholder_tool(query: str) -> str:
            """返回尚未填写的产品知识库占位内容。"""
            return placeholder_msg
        
        return placeholder_tool
    
    # ==================== 编辑 ====================
    
    def _generate_editor_goal(self) -> str:
        """动态生成编辑goal"""
        return (
            "把关可读性、独特标题、关键词密度与绝对路径内链，"
            "删掉夸大、贬低竞品和广告腔，让终稿回到问题本身"
        )
    
    def _generate_editor_backstory(self) -> str:
        """动态生成编辑backstory"""
        density_range = f"{self.config.seo_keyword_density_min*100:.1f}%-{self.config.seo_keyword_density_max*100:.1f}%"
        
        if self.config.product_mention_max == 0:
            mention_rule = "不要写本站自己的产品名。"
        elif self.config.product_mention_position == "ending":
            mention_rule = (
                f"{self.config.name} 全文最多出现 {self.config.product_mention_max} 次，集中在文末。"
            )
        else:
            mention_rule = (
                f"{self.config.name} 全文最多出现 {self.config.product_mention_max} 次。"
            )
        return f"""你是总编不是复读机：删套话、补具体细节、校正 H1/H2。
密度约 {density_range}；必须调用 seo_link_injector；保留真实抱怨引用。
若 H1 与「已有标题」过近，改写成更具体、可区分的标题。
看到夸大、贬低其他工具、广告腔的句子，改成问题机制和知识库里的原话。
{mention_rule}产品名超过这个次数就删到上限以内，不要整段改写成夸大。"""
    
    def _create_editor_tools(self) -> list:
        """创建编辑工具"""
        if not self.config.seo_internal_links_enabled:
            return []
        
        config = self.config
        anchor = config.seo_internal_links_anchor_text or config.name
        target = config.seo_internal_links_target_url or config.domain
        
        @tool("seo_link_injector")
        def seo_optimization_tool(markdown_content: str) -> str:
            """自动化发布前质检：在正文自然处注入绝对路径锚文本（不改 H1）。"""
            target_anchor = f"[{anchor}]({target})"
            keywords_to_replace = [
                anchor,
                anchor.replace(" ", ""),
                anchor.lower(),
                anchor.lower().replace(" ", ""),
            ]
            
            lines = markdown_content.splitlines(keepends=True)
            h1_idx = next(
                (i for i, ln in enumerate(lines) if ln.lstrip().startswith("# ")),
                None,
            )
            
            body_start = 0 if h1_idx is None else h1_idx + 1
            head = "".join(lines[:body_start])
            body = "".join(lines[body_start:])
            
            replaced = False
            for kw in keywords_to_replace:
                if kw in body:
                    body = body.replace(kw, target_anchor, 1)
                    replaced = True
                    break
            
            if not replaced and target_anchor not in body and target_anchor not in head:
                body = (
                    f"在处理相关任务时，拥有一款好用的 {target_anchor} 工具往往能事半功倍。\n\n"
                ) + body
            
            return head + body
        
        return [seo_optimization_tool]
