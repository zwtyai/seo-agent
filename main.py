import re

from crewai import Agent, Crew, Process, Task
from crewai.tools import tool

from static_publish import (
    list_published_titles,
    list_published_content_types,
    publish_static_page,
)
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
        "借助 Google Search Grounding，为 {seed_keyword} 深度挖掘 **1 个高价值长尾痛点**；"
        "必须提供量化数据、至少 3 个真实 URL、明确的内容类型建议；"
        "角度必须与已有文章明显不同，内容类型需考虑多样性"
    ),
    backstory="""你是一位数据驱动的 SEO 研究专家，接入了 Gemini 的 Google Search Grounding。

你的职责不是简单找关键词，而是挖掘**有深度、有证据、有价值**的内容素材：

1. **具体场景优先**：优先挖掘具体、可感知的痛点（双栏论文、扫描件、公式、表格串列、合同排版等），
   避免泛泛而谈的"PDF翻译不好用"。

2. **证据为王**：必须找到至少 3 个真实用户抱怨的 URL（知乎、Reddit、论坛、博客、竞品评论），
   每个 URL 需提取 50-100 字的核心抱怨。优先选择带具体场景和情绪的原话。

3. **量化数据支撑**：尽可能找到数据（用户数量、错误率、时间成本、市场调研等），
   让内容更有说服力。如果找不到现成数据，可以统计用户抱怨的频次。

4. **竞品分析**：留意其他翻译工具的差评和局限性，这是差异化定位的关键。

5. **内容类型判断**：根据素材特点，建议最适合的内容类型（深度分析、对比评测、教程、FAQ、案例故事），
   考虑已有内容类型的分布，优先推荐较少使用的类型。

**禁止**凭空编造数据、URL 或用户评价。如果 Grounding 没有返回足够证据，明确说明，
而不是伪造。宁可推迟生产，也不能输出低质量素材。""",
    llm=researcher_llm,
    verbose=True,
)
enable_google_search_grounding(keyword_researcher.llm)

content_writer = Agent(
    role="顶尖科技博客主 (Technical Content Writer)",
    goal=(
        "基于研究员的深度简报与译比邻产品能力，创作高质量、差异化的 Markdown 长文；"
        "H1 必须独特、贴近本篇痛点，不得与已有标题雷同；内容类型需与已有文章互补"
    ),
    backstory="""你是一位经验丰富的内容创作者，擅长多种内容类型：

**深度分析型**：善于挖掘问题根源，引用大量数据和证据，层层剖析，给出深度见解。
**对比评测型**：客观公正，通过表格和多维度对比，帮助用户做选择，突出产品优势但不贬低竞品。
**教程指南型**：步骤清晰，注重可操作性，每个步骤都有明确指引，帮助用户解决实际问题。
**FAQ型**：精准解答用户疑问，每个回答简洁有力，覆盖面广，适合快速查阅。
**案例故事型**：叙事流畅，通过真实故事引发共鸣，技术说明融入情节，读起来像在看故事而非广告。

写作原则：
1. 文风硬核、禁止 AI 套话（如「在当今时代」「综上所述」「赋能」「助力」堆砌）
2. 写作前必须调用 product_knowledge_base 核对技术参数，确保准确性
3. 必须引用研究员报告中的真实数据、URL、用户抱怨，避免空泛广告腔
4. 根据研究员建议的内容类型选择对应模板，发挥该类型的特点
5. 内容要有独特价值：新数据、新角度、新案例，避免与已有文章雷同""",
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
    description="""针对种子词 '{seed_keyword}'，使用 Google Search Grounding 深度挖掘高价值内容素材。

    【已有文章标题——禁止重复同一角度】
    {existing_titles}

    【已有内容类型】
    {existing_content_types}

    核心要求：
    1. **长尾痛点挖掘**：找到 1 个与已有文章明显不同的具体场景
       - 优先：双栏/公式/扫描件 OCR/表格串列/合同排版/图表注释/脚注引用/水印处理等
       - 必须是具体、可感知的痛点，非泛泛而谈
    
    2. **量化数据要求**（至少满足一项）：
       - 用户抱怨的频次统计（"知乎上XX问题有XXX个回答"）
       - 错误率/失败率数据（"OCR识别率仅XX%"）
       - 时间成本数据（"手动排版需要X小时"）
       - 市场调研数据（"XX%的用户遇到此问题"）
    
    3. **真实证据链**（必须提供）：
       - 至少 3 个真实 URL（知乎/Reddit/论坛/博客/竞品评论）
       - 每个 URL 附 50-100 字的核心抱怨摘要
       - 优先带具体场景和情绪的用户原话
    
    4. **竞品缺陷分析**（可选但加分）：
       - 找到其他翻译工具的差评或局限性
       - 具体说明它们在哪个环节失败
    
    5. **内容类型建议**：
       根据素材特点，建议最适合的内容类型：
       - 深度分析型（有大量证据和数据）
       - 对比评测型（有多个工具对比）
       - 教程指南型（痛点有明确解决步骤）
       - FAQ型（用户疑问集中）
       - 案例故事型（有生动的用户故事）

    【禁止】无联网依据时凭空编造数据和URL。
    
    【输出格式】Markdown 简报：
    ## keyword
    ## user_persona
    ## pain_points（含量化数据）
    ## quantitative_data（至少1条，标注来源）
    ## evidence_urls（至少3个，每个带摘要）
    ## competitor_gaps（竞品缺陷，可选）
    ## suggested_content_type（推荐内容类型+理由）
    ## suggested_h1（独特标题草案）
    ## unique_angle（本篇独特角度，30字内说明与已有文章的差异）""",
    expected_output=(
        "Markdown 研究简报：包含长尾痛点、量化数据、至少3个真实URL证据、"
        "内容类型建议、独特标题，总字数 500-800 字。"
    ),
    agent=keyword_researcher,
)

write_task = Task(
    description="""消费研究员简报，调用 product_knowledge_base，撰写高质量 Markdown 正文。

    【已有文章标题——H1 不得雷同或换皮重复】
    {existing_titles}

    【内容类型要求】
    根据研究员建议的 suggested_content_type，选择对应模板：
    
    **模板A：深度分析型（1200-1800字）**
    结构：引入痛点场景 → 问题深度剖析（含量化数据）→ 行业现状/竞品分析 → 
          解决方案详解（分点说明）→ 实施建议 → CTA
    特点：大量引用研究数据、用户证据、对比分析
    
    **模板B：对比评测型（1000-1500字）**
    结构：痛点场景 → 评测维度说明 → 3-5个工具对比（含表格）→ 
          译比邻优势详解 → 选择建议 → CTA
    特点：必须有 Markdown 对比表格、客观评价竞品
    
    **模板C：教程指南型（1000-1400字）**
    结构：痛点场景 → 为什么困难 → 分步骤解决方案（3-5步，每步有小标题）→ 
          注意事项/常见错误 → CTA
    特点：步骤清晰、可操作、带"如何"/"怎么办"关键词
    
    **模板D：FAQ型（800-1200字）**
    结构：引入 → 10-15个 Q&A（H2 格式：## Q: 问题？）→ 
          总结（译比邻如何一站式解决）→ CTA
    特点：每个问题独立可读、答案简洁有力
    
    **模板E：案例故事型（1000-1500字）**
    结构：用户故事开头（具体人物+场景）→ 遇到的困境 → 尝试的方法和失败 → 
          使用译比邻的转折 → 效果与感受 → 技术原理解释 → CTA
    特点：叙事性强、代入感强、情感共鸣

    【通用写作要求】
    1. **H1标题**：使用研究员的 suggested_h1 或自拟更优标题
       - 必须独特、包含痛点关键词、激发点击欲
       - 可使用数字、疑问句、对比、情感词
    
    2. **证据引用**（必须）：
       - 至少引用 2 个研究简报中的真实证据
       - 标注来源（"知乎用户XXX表示"/"根据XXX调研"）
       - 必须引用量化数据（如有）
    
    3. **产品能力描述**：
       - 调用 product_knowledge_base 获取准确参数
       - 具体说明功能，避免泛泛而谈
       - 每个卖点配合痛点，不要堆砌
    
    4. **内容增强元素**（根据类型选用）：
       - 对比表格（Markdown table）
       - 带数字的小标题（"3个核心原因"）
       - FAQ小节
       - 注意事项/Tips
       - 用户评价引用
    
    5. **E-E-A-T 信号**：
       - 体现第一手经验（"经过测试"）
       - 引用权威来源
       - 展示专业性（技术术语准确）
    
    6. **可读性**：
       - 段落不超过 4 行
       - 使用小标题分割（H2/H3）
       - 适当使用加粗、列表
       - 避免AI套话（"在当今"、"综上所述"、"赋能"等）
    
    7. **CTA**：结尾自然引导，包含明确行动（"立即访问"、"开始翻译"）

    【禁止】
    - 凭空编造数据或用户评价
    - 与已有文章结构和论点雷同
    - 过度营销或夸大宣传
    - 忽略研究简报中的核心证据""",
    expected_output=(
        "根据内容类型模板撰写的 800-1800 字 Markdown 文章，含独特 H1、"
        "清晰结构、真实证据引用、量化数据、产品能力详解、明确 CTA。"
    ),
    agent=content_writer,
)

edit_task = Task(
    description="""终审草稿并输出可上线 Markdown，确保内容质量达到 SEO 和用户价值标准。

    【已有文章标题】
    {existing_titles}

    【质量检查清单】
    
    1. **标题与差异化**：
       - H1 贴近本篇内容，与已有标题明显区分（若过近则改写）
       - 标题包含核心关键词，有吸引力
    
    2. **内容深度与证据**：
       - 是否引用了研究简报中的真实证据和 URL？
       - 是否包含量化数据支撑？
       - 是否有独特观点或新鲜角度？
       - 避免与已有文章论点重复
    
    3. **SEO 优化**：
       - 关键词密度约 1.5%-2.5%（自然出现，不堆砌）
       - H1/H2/H3 结构完整清晰
       - 必须调用 seo_link_injector 注入绝对路径内链
       - 小标题包含相关关键词
    
    4. **可读性**：
       - 删除 AI 套话（"在当今时代"、"综上所述"、"赋能"、"助力"等）
       - 段落长度适中（不超过 4-5 行）
       - 语言自然流畅，避免生硬翻译腔
       - 保留真实抱怨引用与具体产品能力描述
    
    5. **内容完整性**：
       - 对于深度型文章，确保 1200+ 字
       - 对于教程型，确保步骤清晰可执行
       - 对于对比型，确保有表格或结构化对比
       - CTA 明确且自然
    
    6. **E-E-A-T 信号检查**：
       - 是否体现专业性（术语准确）？
       - 是否有经验展示（测试结果、实际使用）？
       - 是否引用权威来源？
       - 是否可信（有具体数据，非夸大）？
    
    【优化动作】
    - 若发现套话或空洞内容，替换为具体描述
    - 若缺少证据支撑，补充研究简报中的引用
    - 若关键词密度不足，在小标题和段落中自然增加
    - 若结构混乱，重新组织段落逻辑
    - 若与已有文章相似度高，突出本篇独特角度
    
    【不要】
    - 不要为了凑字数而注水
    - 不要过度删减导致信息不完整
    - 不要改变研究简报中的真实数据和引用
    - 不要把长文压缩成短文

    最终输出：经过质量把关的可上线 Markdown 终稿。""",
    expected_output=(
        "可上线 Markdown 终稿：独特标题、内链已注入、关键词密度合理、"
        "结构完整、证据充分、可读性强、符合 E-E-A-T 标准。"
    ),
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
    existing_types = list_published_content_types()
    
    existing_block = (
        "\n".join(f"- {t}" for t in existing)
        if existing
        else "- （暂无已发布文章）"
    )
    
    # 内容类型统计
    type_stats = {}
    for ct in existing_types:
        type_stats[ct] = type_stats.get(ct, 0) + 1
    types_block = (
        "\n".join(f"- {t}: {count}篇" for t, count in sorted(type_stats.items()))
        if type_stats
        else "- （暂无统计）"
    )
    
    print(f"📚 已有文章 {len(existing)} 篇（用于选题/标题去重）")
    print(f"📊 内容类型分布：{type_stats}")
    
    try:
        result = yibelin_seo_factory.kickoff(
            inputs={
                "seed_keyword": seed_keyword,
                "existing_titles": existing_block,
                "existing_content_types": types_block,
            }
        )
        print("\n=================== ✨ 成品 ===================\n")
        print(result)
        print("\n================================================\n")

        html_path = publish_static_page(result, seed_keyword=seed_keyword)
        print(f"✅ 静态页已写入: {html_path}")
        print("✅ 流程：Grounding 深度挖词 → 多模板写作 → SEO 质检 → docs/（标题去重）")
    except Exception as e:
        print(
            f"❌ 运行异常。请检查 Vertex 凭证 / GOOGLE_CLOUD_PROJECT，"
            f"以及项目是否已开通 Vertex AI 与 Grounding。"
            f"错误: {_redact_secrets(str(e))}"
        )
