import re
from typing import List

from crewai import Agent, Crew, Process, Task
from crewai.tools import tool
from pydantic import BaseModel, Field

from static_publish import publish_static_page
from vertex_llm import (
    build_gemini_llm,
    configure_vertex_env,
    enable_google_search_grounding,
)


def _redact_secrets(text: str) -> str:
    """Strip API keys from error strings."""
    if not text:
        return text
    return re.sub(
        r"(key=)([A-Za-z0-9_\-]{8})[A-Za-z0-9_\-]*",
        r"\1\2…",
        text,
        flags=re.IGNORECASE,
    )


# =====================================================================
# 1. Vertex Gemini（与 yibelin 同凭证）
# =====================================================================
configure_vertex_env()

# 各岗位独立实例，避免 Grounding 补丁串到写手/总编
researcher_llm = build_gemini_llm(temperature=0.7)
writer_llm = build_gemini_llm(temperature=0.7)
editor_llm = build_gemini_llm(temperature=0.7)


# =====================================================================
# 2. Pydantic 数据结构
# =====================================================================
class LongTailKeywordBrief(BaseModel):
    keyword: str = Field(..., description="挖掘出的高价值、低竞争长尾痛点词")
    user_persona: str = Field(..., description="目标用户画像（如研一学生、外贸业务员）")
    pain_points: str = Field(..., description="用户遭遇的具体技术痛点（如公式错乱、扫描件无法选字）")
    competitor_urls: List[str] = Field(
        ..., description="Google Search Grounding 检索到的真实帖子/竞品页面 URL"
    )
    evidence_snippets: List[str] = Field(
        default_factory=list,
        description="联网检索到的真实摘要/吐槽摘录",
    )


class KeywordResearcherOutput(BaseModel):
    briefs: List[LongTailKeywordBrief] = Field(..., description="长尾词研究简报列表")
    search_queries_used: List[str] = Field(
        default_factory=list,
        description="实际用于联网检索的 query 列表（若模型有披露）",
    )


# =====================================================================
# 3. 本地工具（写手 / 总编；研究员靠 Grounding，不挂 Custom Search）
# =====================================================================

@tool("product_knowledge_base")
def product_knowledge_base_tool(query: str) -> str:
    """连接‘译比邻’内部产品功能知识库，返回高保真排版保留、双栏论文优化、扫描件 OCR 增强等权威技术参数。"""
    return (
        "【译比邻产品核心技术参数与卖点】：\n"
        "1. 专注版式保留：普通工具只翻文字导致格式错乱，译比邻按段落处理，精准还原原文排版。\n"
        "2. 论文 PDF 双栏优化：基于机器学习对双栏结构、图表位置和公式附近的文字进行尽量保留，避免文字挤出文本框。\n"
        "3. 扫描件 PDF 增强版：针对‘只能看、不能选字’的扫描件图片，自动启用增强版 OCR 识别文字再翻译并重建版式。\n"
        "4. 表格与段落切分优化：默认增强版已包含表格优化，防止译文串列、表头和格子对不上。\n"
        "5. 在线术语编辑：翻译完成后，用户可在双语对照视图中在线修改段落和术语，确认无误后再一键下载导出 PDF。\n"
        "6. 使用限制与规格：Web工具免安装，单文件建议在 10MB、20 页以内，支持英语、中文、日语等多语种。"
    )


@tool("seo_link_injector")
def seo_optimization_tool(markdown_content: str) -> str:
    """自动化发布前质检：在文章自然处注入 yibelin.com 绝对路径锚文本。"""
    target_anchor = "[PDF 在线翻译](https://yibelin.com)"
    keywords_to_replace = ["PDF在线翻译", "pdf在线翻译", "PDF 在线翻译", "pdf 在线翻译"]

    optimized_content = markdown_content
    replaced = False
    for kw in keywords_to_replace:
        if kw in optimized_content:
            optimized_content = optimized_content.replace(kw, target_anchor, 1)
            replaced = True
            break

    if not replaced and target_anchor not in optimized_content:
        intro_text = (
            f"在日常进行科研论文阅读或商务合同处理时，拥有一款好用的 "
            f"{target_anchor} 工具往往能让我们事半功倍。\n\n"
        )
        optimized_content = intro_text + optimized_content
    return optimized_content


print("✅ 第一步：Vertex LLM / 本地工具就绪")


# =====================================================================
# 4. Agents
# =====================================================================

keyword_researcher = Agent(
    role="资深 SEO 关键词研究员 (Keyword Researcher)",
    goal=(
        "借助 Google Search Grounding 快速验证联网挖词；联调阶段只产出 "
        "1 个与 {seed_keyword} 相关的高价值长尾痛点即可"
    ),
    backstory="""你接入了 Gemini 的 Google Search Grounding。
    【联调铁律】少搜、快结：只挖 1 个痛点，带真实 URL/摘要就收工。
    【禁止】纯靠训练数据臆造抱怨。""",
    llm=researcher_llm,
    verbose=True,
)
# Agent 解析完底层 GeminiCompletion 后再打补丁，确保 Grounding 不会丢
enable_google_search_grounding(keyword_researcher.llm)

content_writer = Agent(
    role="顶尖科技博客主 (Technical Content Writer)",
    goal=(
        "基于研究员联网挖到的真实抱怨，结合译比邻技术优势，"
        "撰写约 200 字 Markdown 短文（联调阶段，稳定后再加长）"
    ),
    backstory="""文风硬核、禁止 AI 套话。必须引用研究员报告中的真实抱怨，
    再用译比邻高保真版式 / OCR / 公式表格能力做对比。
    写作前调用 product_knowledge_base 核对参数。""",
    tools=[product_knowledge_base_tool],
    llm=writer_llm,
    verbose=True,
)

seo_editor = Agent(
    role="严苛的 SEO 质量把控总编 (SEO Editor)",
    goal="关键词密度、标题结构与绝对路径内链质检，符合 {seed_keyword} 生产规范",
    backstory="""死盯密度约 1.5%-2.5%、H1/H2 结构；必须调用 seo_link_injector 注入内链。""",
    tools=[seo_optimization_tool],
    llm=editor_llm,
    verbose=True,
)

# =====================================================================
# 5. Tasks
# =====================================================================

research_task = Task(
    description="""针对种子词 '{seed_keyword}'，使用 Google Search Grounding 做**极简联调检索**。
    只查 1 个核心意图即可（优先：格式错乱 / layout broken，或扫描件 OCR 失败，二选一）。
    只输出 **1 个**长尾痛点 brief（不要 3-5 个），附用户画像、痛点、1-2 个真实 URL 与短摘要。
    控制检索轮次：能得出 1 条可用证据就结束，勿扩大范围。
    【禁止】在没有任何联网依据时凭空编造。""",
    expected_output=(
        "结构化 JSON：briefs 仅含 1 条；含 keyword/persona/pain_points/"
        "competitor_urls/evidence_snippets 与 search_queries_used。"
    ),
    output_json=KeywordResearcherOutput,
    agent=keyword_researcher,
)

write_task = Task(
    description="""消费研究员联网报告，调用 product_knowledge_base，写约 200 字短文（联调勿写长）。
    要求：标题含痛点词；引用真实抱怨；点到 yibelin.com 优势；含 H1+至少一个 H2；一句 CTA。""",
    expected_output="约 200 字 Markdown 短文草稿。",
    agent=content_writer,
)

edit_task = Task(
    description="""质检草稿：密度约 1.5%-2.5%；核对标题结构；必须调用 seo_link_injector；保留真实抱怨引用。""",
    expected_output="可上线的 Markdown（含绝对路径内链）。",
    agent=seo_editor,
)

print("✅ 第二步：Agent / Task 组装完成（研究员已启用 Google Search Grounding）")

yibelin_seo_factory = Crew(
    agents=[keyword_researcher, content_writer, seo_editor],
    tasks=[research_task, write_task, edit_task],
    process=Process.sequential,
    verbose=True,
)

if __name__ == "__main__":
    print("🚀 SEO 工厂启动（Vertex Gemini + Google Search Grounding）...")
    seed_keyword = "PDF 在线翻译"
    try:
        result = yibelin_seo_factory.kickoff(
            inputs={"seed_keyword": seed_keyword}
        )
        print("\n=================== ✨ 成品 ===================\n")
        print(result)
        print("\n================================================\n")

        html_path = publish_static_page(result, seed_keyword=seed_keyword)
        print(f"✅ 静态页已写入: {html_path}")
        print("✅ 流程：Grounding 挖词 → 短文 → SEO 质检 → docs/ 静态页（GitHub Pages）")
    except Exception as e:
        print(
            f"❌ 运行异常。请检查 Vertex 凭证 / GOOGLE_CLOUD_PROJECT，"
            f"以及项目是否已开通 Vertex AI 与 Grounding。"
            f"错误: {_redact_secrets(str(e))}"
        )
