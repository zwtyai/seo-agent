import re

from crewai import Agent, Crew, Process, Task
from crewai.tools import tool

from static_publish import list_published_titles, publish_static_page
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
writer_llm = build_gemini_llm(temperature=0.75)
editor_llm = build_gemini_llm(temperature=0.4)


# =====================================================================
# 2. 本地工具（写手 / 总编；研究员靠 Grounding，不挂 Custom Search）
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
    """自动化发布前质检：在正文自然处注入 yibelin.com 绝对路径锚文本（不改 H1）。"""
    target_anchor = "[PDF 在线翻译](https://yibelin.com)"
    keywords_to_replace = ["PDF在线翻译", "pdf在线翻译", "PDF 在线翻译", "pdf 在线翻译"]

    lines = markdown_content.splitlines(keepends=True)
    h1_idx = next(
        (i for i, ln in enumerate(lines) if ln.lstrip().startswith("# ")),
        None,
    )
    # 只在 H1 之外替换，避免标题变成 [PDF 在线翻译](url)…
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
            f"在日常进行科研论文阅读或商务合同处理时，拥有一款好用的 "
            f"{target_anchor} 工具往往能让我们事半功倍。\n\n"
        ) + body
    return head + body


print("✅ 第一步：Vertex LLM / 本地工具就绪")


# =====================================================================
# 3. Agents
# =====================================================================

keyword_researcher = Agent(
    role="资深 SEO 关键词研究员 (Keyword Researcher)",
    goal=(
        "借助 Google Search Grounding，为 {seed_keyword} 挖到 **1 个尚未写过的** "
        "高价值长尾痛点；角度必须与已有文章标题明显不同"
    ),
    backstory="""你接入了 Gemini 的 Google Search Grounding。
    优先找具体场景（双栏论文、扫描件、公式、表格串列、合同排版等），
    带真实 URL/摘要。禁止凭空编造；禁止重复已有标题覆盖过的同一角度。""",
    llm=researcher_llm,
    verbose=True,
)
enable_google_search_grounding(keyword_researcher.llm)

content_writer = Agent(
    role="顶尖科技博客主 (Technical Content Writer)",
    goal=(
        "基于研究员真实抱怨与译比邻能力，写一篇可读、可检索的 Markdown 长文；"
        "H1 必须独特、贴近本篇痛点，不得与已有标题雷同"
    ),
    backstory="""文风硬核、禁止 AI 套话（如「在当今时代」「综上所述」「赋能」堆砌）。
    写作前调用 product_knowledge_base 核对参数。
    结构清晰：痛点场景 → 证据/吐槽 → 为什么普通工具翻车 → 译比邻怎么解 → CTA。
    必须引用研究员报告里的真实抱怨或 URL 语境，避免空泛广告腔。""",
    tools=[product_knowledge_base_tool],
    llm=writer_llm,
    verbose=True,
)

seo_editor = Agent(
    role="严苛的 SEO 质量把控总编 (SEO Editor)",
    goal=(
        "把关可读性、独特标题、关键词密度与绝对路径内链，"
        "输出可直接上线的终稿（符合 {seed_keyword} 规范）"
    ),
    backstory="""你是总编不是复读机：删套话、补具体细节、校正 H1/H2。
    密度约 1.5%-2.5%；必须调用 seo_link_injector；保留真实抱怨引用。
    若 H1 与「已有标题」过近，改写成更具体、可区分的标题。""",
    tools=[seo_optimization_tool],
    llm=editor_llm,
    verbose=True,
)

# =====================================================================
# 4. Tasks
# =====================================================================

research_task = Task(
    description="""针对种子词 '{seed_keyword}'，使用 Google Search Grounding 检索真实用户抱怨。

    【已有文章标题——禁止重复同一角度】
    {existing_titles}

    要求：
    - 只产出 **1 个**长尾痛点 brief（与上表角度明显不同）
    - 优先具体场景：双栏/公式/扫描件 OCR/表格串列/合同排版等（选一个深挖）
    - 附用户画像、痛点、1-2 个真实 URL 与短摘要
    - 能得出 1 条可用证据就结束，勿盲目扩大检索
    【禁止】无联网依据时凭空编造。
    【格式】Markdown 小节：
    ## keyword / ## user_persona / ## pain_points / ## competitor_urls / ## evidence_snippets / ## suggested_h1
    （suggested_h1：给写手的独特标题草案，须不同于已有标题）""",
    expected_output=(
        "Markdown 简报：1 条新痛点 + suggested_h1；含真实 URL 与证据摘要。"
    ),
    agent=keyword_researcher,
)

write_task = Task(
    description="""消费研究员简报，调用 product_knowledge_base，撰写 Markdown 正文。

    【已有文章标题——H1 不得雷同或换皮重复】
    {existing_titles}

    写作要求：
    1. 使用研究员的 suggested_h1 或自拟更优 H1（独特、含痛点词、可读）
    2. 正文约 **800–1200 汉字**（可含必要英文术语）；至少 1 个 H1 + 2 个 H2
    3. 开篇用具体场景；引用简报中的真实抱怨/证据（可改写但勿伪造来源）
    4. 对比「普通工具翻车点」vs「译比邻对应能力」，参数以知识库为准
    5. 结尾一句自然 CTA，指向 yibelin.com
    6. 禁止空洞套话与重复已有文章结构的换皮文""",
    expected_output="800–1200 字 Markdown 草稿，含独特 H1 与清晰小标题。",
    agent=content_writer,
)

edit_task = Task(
    description="""终审草稿并输出可上线 Markdown。

    【已有文章标题】
    {existing_titles}

    检查清单：
    - H1 贴近本篇内容，且与已有标题明显区分；过近则改写
    - 删 AI 套话；保留真实抱怨引用与具体产品能力
    - 关键词密度约 1.5%–2.5%；H1/H2 结构完整
    - 必须调用 seo_link_injector 注入绝对路径内链
    - 不要把正文压回联调短文长度；保持实质信息量""",
    expected_output="可上线 Markdown 终稿（独特标题 + 内链 + 可读长文）。",
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
    existing = list_published_titles()
    existing_block = (
        "\n".join(f"- {t}" for t in existing)
        if existing
        else "- （暂无已发布文章）"
    )
    print(f"📚 已有文章 {len(existing)} 篇（用于选题/标题去重）")
    try:
        result = yibelin_seo_factory.kickoff(
            inputs={
                "seed_keyword": seed_keyword,
                "existing_titles": existing_block,
            }
        )
        print("\n=================== ✨ 成品 ===================\n")
        print(result)
        print("\n================================================\n")

        html_path = publish_static_page(result, seed_keyword=seed_keyword)
        print(f"✅ 静态页已写入: {html_path}")
        print("✅ 流程：Grounding 挖词 → 长文 → SEO 质检 → docs/（标题去重）")
    except Exception as e:
        print(
            f"❌ 运行异常。请检查 Vertex 凭证 / GOOGLE_CLOUD_PROJECT，"
            f"以及项目是否已开通 Vertex AI 与 Grounding。"
            f"错误: {_redact_secrets(str(e))}"
        )
