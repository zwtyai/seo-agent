import os
from typing import List

from crewai import Agent, Crew, LLM, Process, Task
from crewai.tools import tool
from googleapiclient.discovery import build
from pydantic import BaseModel, Field

from vertex_llm import build_gemini_llm, configure_vertex_env

# =====================================================================
# 1. 环境变量与大模型初始化（与 yibelin / doc2doc Vertex Gemini 同一套）
# =====================================================================
# 先落好 GOOGLE_APPLICATION_CREDENTIALS，供 Vertex LLM 与 Custom Search 复用
configure_vertex_env()

# Programmable Search Engine（垂直检索 CX）
os.environ.setdefault("GOOGLE_SEARCH_CX", "71009255757954160")

gemini_llm: LLM = build_gemini_llm(temperature=0.7)


# =====================================================================
# 2. Pydantic 数据结构定义（规范 Agent 之间传递的 Payload 格式）
# =====================================================================
class LongTailKeywordBrief(BaseModel):
    keyword: str = Field(..., description="挖掘出的高价值、低竞争长尾痛点词")
    user_persona: str = Field(..., description="目标用户画像（如研一学生、外贸业务员）")
    pain_points: str = Field(..., description="用户遭遇的具体技术痛点（如公式错乱、扫描件无法选字）")
    competitor_urls: List[str] = Field(
        ..., description="谷歌检索到的真实帖子/竞品页面 URL 列表"
    )
    evidence_snippets: List[str] = Field(
        default_factory=list,
        description="来自 google_official_search 的真实摘要/吐槽摘录",
    )


class KeywordResearcherOutput(BaseModel):
    briefs: List[LongTailKeywordBrief] = Field(..., description="长尾词研究简报列表")
    search_queries_used: List[str] = Field(
        default_factory=list,
        description="实际调用过的谷歌检索 query 列表",
    )


# =====================================================================
# 3. 自定义 SEO / 搜索 / 产品知识库工具集（Tools）
# 注意：Gemini Function Calling 要求工具名为英文+下划线
# =====================================================================

@tool("google_official_search")
def google_official_search_tool(query: str) -> str:
    """Search Google Custom Search (configured CX vertical pools) for real user complaints and competitor pages."""
    cx_id = (os.environ.get("GOOGLE_SEARCH_CX") or "").strip()
    if not cx_id:
        return "❌ 未配置 GOOGLE_SEARCH_CX，无法调用谷歌垂直检索。"

    # Custom Search JSON API 通常需要 API Key；也尝试复用 ADC/服务账号
    api_key = (
        os.environ.get("GOOGLE_CSE_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    ).strip()

    try:
        if api_key:
            service = build("customsearch", "v1", developerKey=api_key, cache_discovery=False)
            request = service.cse().list(q=query, cx=cx_id, num=5)
        else:
            # 无独立 CSE Key 时，尝试用当前 Vertex 服务账号凭证
            import google.auth

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cse"]
            )
            service = build(
                "customsearch",
                "v1",
                credentials=credentials,
                cache_discovery=False,
            )
            request = service.cse().list(q=query, cx=cx_id, num=5)

        res = request.execute()
        search_items = res.get("items", [])
        if not search_items:
            return (
                f"查询「{query}」在指定垂直检索池中无结果。"
                "请换一组更贴近社区抱怨的 query 再试。"
            )

        results_text = []
        for item in search_items:
            title = item.get("title", "")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            results_text.append(f"标题: {title}\n链接: {link}\n摘要: {snippet}\n---")
        return "\n".join(results_text)

    except Exception as e:
        return (
            f"❌ 调用谷歌 Custom Search 失败: {e}。"
            "请确认已启用 Custom Search API，并配置 GOOGLE_CSE_API_KEY"
            "（或 GOOGLE_API_KEY）与 GOOGLE_SEARCH_CX。"
        )


@tool("product_knowledge_base")
def product_knowledge_base_tool(query: str) -> str:
    """连接‘译比邻’内部产品功能知识库，返回高保真排版保留、双栏论文优化、扫描件 OCR 增强等权威技术参数。"""
    knowledge = (
        "【译比邻产品核心技术参数与卖点】：\n"
        "1. 专注版式保留：普通工具只翻文字导致格式错乱，译比邻按段落处理，精准还原原文排版。\n"
        "2. 论文 PDF 双栏优化：基于机器学习对双栏结构、图表位置和公式附近的文字进行尽量保留，避免文字挤出文本框。\n"
        "3. 扫描件 PDF 增强版：针对‘只能看、不能选字’的扫描件图片，自动启用增强版 OCR 识别文字再翻译并重建版式。\n"
        "4. 表格与段落切分优化：默认增强版已包含表格优化，防止译文串列、表头和格子对不上。\n"
        "5. 在线术语编辑：翻译完成后，用户可在双语对照视图中在线修改段落和术语，确认无误后再一键下载导出 PDF。\n"
        "6. 使用限制与规格：Web工具免安装，单文件建议在 10MB、20 页以内，支持英语、中文、日语等多语种。"
    )
    return knowledge


@tool("seo_link_injector")
def seo_optimization_tool(markdown_content: str) -> str:
    """自动化发布前的严苛质检门禁。通过确定性 Python 代码强行在文章核心自然处注入带绝对路径的锚文本。"""
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


print("✅ 第一步：环境配置与核心 SEO 工具集构建成功！")


# =====================================================================
# 4. 创建虚拟 Agent 岗位（Vertex Gemini 2.5 Flash）
# =====================================================================

keyword_researcher = Agent(
    role="资深 SEO 关键词研究员 (Keyword Researcher)",
    goal=(
        "利用 google_official_search 在垂直检索池中找真实用户抱怨，"
        "挖掘大厂在 {seed_keyword} 领域的防御漏洞与低竞争长尾痛点词"
    ),
    backstory="""你负责调用 google_official_search，在已配置的高权重社区池
    （如 Reddit、V2EX、知乎、StackExchange 等）检索网民对 PDF 翻译工具的真实吐槽。
    【铁律】：禁止仅凭模型臆测编造痛点；每一条结论都必须能回溯到工具返回的标题/链接/摘要。
    重点搜集：双栏排版错乱、扫描件无法选字、公式变乱码、表格串列等具体案例。""",
    tools=[google_official_search_tool],
    llm=gemini_llm,
    verbose=True,
)

content_writer = Agent(
    role="顶尖科技博客主 (Technical Content Writer)",
    goal=(
        "基于研究员从谷歌抓到的真实抱怨，结合译比邻技术优势，"
        "撰写约 200 字、直击痛点的商业级 Markdown 短文（联调阶段，稳定后再加长）"
    ),
    backstory="""你是一位文风生动扎实、逻辑极其严谨的科技意见领袖（KOL）。
    【铁律】：你极度厌恶 AI 废话。绝对禁止‘总而言之’、‘值得注意的是’、‘如前所述’、
    ‘显而易见’、‘综上所述’等空洞排比。必须引用研究员报告中的真实社区抱怨（可点名平台/摘要），
    再用译比邻的高保真版式、OCR、公式/表格能力做降维打击。
    写作前先调用 product_knowledge_base 核对产品参数。""",
    tools=[product_knowledge_base_tool],
    llm=gemini_llm,
    verbose=True,
)

seo_editor = Agent(
    role="严苛的 SEO 质量把控总编 (SEO Editor)",
    goal="执行最严厉的技术规范审查、代码内链注入，确保内容完美符合 {seed_keyword} 的生产级规范",
    backstory="""你是内容的最后一到门禁。你眼中只有数据和技术指标。
    你负责死盯三大技术指标：关键词密度（1.5%-2.5%）、H1/H2/H3 标签结构的严密性、
    以及主站首页绝对路径锚文本的强行注入。必须调用 seo_link_injector 完成内链注入。""",
    tools=[seo_optimization_tool],
    llm=gemini_llm,
    verbose=True,
)

# =====================================================================
# 5. 定义全自动化执行任务
# =====================================================================

research_task = Task(
    description="""针对种子词 '{seed_keyword}'，必须多次调用 google_official_search 做真实检索。
    建议至少覆盖这些 query（可按结果再追加）：
    1) '{seed_keyword} 格式错乱' / '{seed_keyword} layout broken'
    2) '{seed_keyword} 扫描件' / 'scanned PDF OCR translation fail'
    3) '{seed_keyword} 公式乱码' / 'PDF translate formulas broken'
    4) 'Smallpdf OR DeepL PDF translate site:reddit.com OR site:v2ex.com OR site:zhihu.com'
    从检索结果中提炼 3-5 个高价值长尾痛点词，并记录用户画像、痛点、真实 URL 与摘要证据。
    【禁止】在没有任何工具返回结果的情况下凭空编造抱怨。""",
    expected_output=(
        "结构化漏洞分析报告（JSON）：含 briefs（keyword/persona/pain_points/"
        "competitor_urls/evidence_snippets）与 search_queries_used。"
    ),
    output_json=KeywordResearcherOutput,
    agent=keyword_researcher,
)

write_task = Task(
    description="""消费上一阶段基于谷歌检索的长尾词简报（含真实 URL 与摘要）。
    先调用 product_knowledge_base，再撰写一篇约 200 字的短评测/实操文（当前为流程联调，勿写长文）。
    要求：
    1. 标题包含长尾痛点词，有点击欲。
    2. 正文引用研究员发现的真实社区抱怨（可写平台+摘要，勿伪造未出现的引文）。
    3. 点到译比邻 (yibelin.com) 在高保真排版、扫描件 OCR、公式/表格上的优势即可。
    4. 结构清晰（含 H1 与至少 1 个 H2），Markdown 输出；严禁 AI 套话。
    5. 结尾有一句 CTA，引导去 yibelin.com 体验。""",
    expected_output="一篇未加工的、直击技术痛点的、字数约 200 字的 Markdown 短文草稿。",
    agent=content_writer,
)

edit_task = Task(
    description="""对创作者提交的 Markdown 草稿进行严苛的 SEO 审查和重构：
    1. 将 '{seed_keyword}' 相关关键词密度调整到约 1.5% - 2.5%。
    2. 核对 H1/H2/H3 结构与 Meta 描述。
    3. 必须调用 seo_link_injector，在最自然处注入带绝对路径的锚文本。
    4. 保留文中对真实抱怨的引用，勿删证据感。""",
    expected_output=(
        "审核完全合格、技术指标拉满、包含绝对路径内链代码、可直接上线的商业级生产 Markdown 文本。"
    ),
    agent=seo_editor,
)

print("✅ 第二步：Agent 岗位与动态 Task 任务构建成功！")

# =====================================================================
# 6. 组装 Crew 团队
# =====================================================================

yibelin_seo_factory = Crew(
    agents=[keyword_researcher, content_writer, seo_editor],
    tasks=[research_task, write_task, edit_task],
    process=Process.sequential,
    verbose=True,
)

# =====================================================================
# 7. 本地闭环运行入口
# =====================================================================
if __name__ == "__main__":
    print("🚀 yibelin.com SEO 工厂启动（Vertex Gemini + Google Custom Search）...")

    dynamic_inputs = {
        "seed_keyword": "PDF 在线翻译",
    }

    try:
        final_article_payload = yibelin_seo_factory.kickoff(inputs=dynamic_inputs)

        print("\n=================== ✨ 最终生产级文章成果展示 ===================\n")
        print(final_article_payload)
        print("\n=================================================================\n")
        print("✅ 流水线跑通：谷歌检索挖词 → 写稿 → SEO 质检")

    except Exception as e:
        print(
            f"❌ 运行异常。请检查 Vertex 凭证、GOOGLE_SEARCH_CX、"
            f"以及 Custom Search API / GOOGLE_CSE_API_KEY。错误: {e}"
        )
