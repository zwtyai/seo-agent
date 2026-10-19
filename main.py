import re
from pathlib import Path

from crewai import Agent, Crew, Process, Task
from crewai.tools import tool

from static_publish import (
    CONTENT_TYPES,
    _infer_content_type,
    least_used_content_type,
    list_published_titles,
    list_published_content_types,
    publish_static_page,
)
from claim_gate import validate_article_claims
from keyword_gate import brief_sections, validate_keyword_brief
from vertex_llm import (
    build_gemini_llm,
    configure_vertex_env,
    enable_google_search_grounding,
)

SEED_KEYWORD = "PDF 在线翻译"
RUN_DIR = Path(__file__).resolve().parent / "runs" / "latest"
STEP_FILES = {
    "keyword": "01-keyword.md",
    "write": "02-draft.md",
    "edit": "03-final.md",
}


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
    """返回译比邻已确认的产品能力。正文只能复述这些句子，不能加码，也不能拿来贬低其他工具。"""
    return (
        "【译比邻产品能力（只许复述，不许加码，不许拿来对比贬低）】：\n"
        "1. 版式：按段落处理，尽量保留原文排版。复杂公式、印章、批注、水印不保证与原文一致。\n"
        "2. 双栏：对双栏结构、图表位置和公式附近的文字尽量保留，文字仍可能挤出文本框。\n"
        "3. 扫描件：对不能选字的扫描件，会尝试用 OCR 识别文字再翻译，并尽量重建版式。识别和版式都可能出错。\n"
        "4. 表格：尽量减少译文串列、表头和格子对不上，不能保证表格完整。\n"
        "5. 术语：翻译完成后可在双语对照里修改段落和术语，再下载 PDF。\n"
        "6. 限制：Web 工具，单文件建议 10MB、20 页以内。超出或版式很复杂时，结果需要人工核对。\n"
        "写作时正文主体写问题本身。产品只在文末用一小节复述以上能力，并带上第 6 条限制。"
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
        "借助 Google Search Grounding，为 {seed_keyword} 选出 **1 个问题型长尾词**；"
        "有公开数字时搜索量要在 200-2000、KD 要低于 30，并附来源 URL；"
        "公开结果里没有这两个数就写「未找到公开数据」，禁止编造"
    ),
    backstory="""你是一位数据驱动的 SEO 研究专家，接入了 Gemini 的 Google Search Grounding。

你的职责是先选定一个值得写的长尾词，再为它找证据。选词规则：

1. **问题型长尾**：用「如何 / 为什么 / 怎么」开头，一篇只锁 1 个词。
   不要交「PDF翻译」「PDF 在线翻译」这种大词。场景要具体（扫描件、双栏、公式、表格、水印）。

2. **证据为王**：必须找到至少 3 个真实用户抱怨的 URL（知乎、Reddit、论坛、博客、竞品评论），
   每个 URL 需提取 50-100 字的核心抱怨。优先选择带具体场景和情绪的原话。

3. **量化数据支撑**：尽可能找到数据（用户数量、错误率、时间成本、市场调研等），
   让内容更有说服力。如果找不到现成数据，可以统计用户抱怨的频次。

4. **竞品页面**：只记录对方页面 URL 和用户原话。不要写「竞品很差」这类结论。

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
        "把研究简报里的那一个问题写清楚：它为何发生、表现是什么、证据是什么；"
        "H1 贴近这个痛点，不得与已有标题雷同；产品只在文末按知识库复述一次"
    ),
    backstory="""你是一位经验丰富的内容创作者，擅长多种内容类型：

**深度分析型**：把问题的机制写清楚，引用简报里的数据和 URL。
**对比评测型**：只对比简报里有 URL 的事实，不打分，不宣布谁赢了。
**教程指南型**：步骤写读者能做的核对与处理，产品最多是其中一步。
**FAQ型**：每个答案先回答问题本身。
**案例故事型**：只复述简报里已有 URL 的用户抱怨，不编人物和结局。

写作原则：
1. 文风硬核、禁止 AI 套话（如「在当今时代」「综上所述」「赋能」「助力」堆砌）
2. 写作前必须调用 product_knowledge_base，产品句子只复述返回的原文
3. 必须引用研究员报告中的真实数据、URL、用户抱怨
4. 根据研究员建议的内容类型选择对应模板
5. 正文主体是问题本身，避免与已有文章雷同""",
    tools=[product_knowledge_base_tool],
    llm=writer_llm,
    verbose=True,
)

seo_editor = Agent(
    role="严苛的 SEO 质量把控总编 (SEO Editor)",
    goal=(
        "把关可读性、独特标题、关键词密度与绝对路径内链，"
        "删掉夸大、贬低竞品和广告腔，让终稿回到问题本身"
    ),
    backstory="""你是总编不是复读机：删套话、补具体细节、校正 H1/H2。
    密度约 1.5%-2.5%；必须调用 seo_link_injector；保留真实抱怨引用。
    若 H1 与「已有标题」过近，改写成更具体、可区分的标题。
    看到「彻底解决」「完美」「终极」「经过测试」或贬低其他工具的句子，改成问题机制和知识库里的原话。
    译比邻全文最多出现 4 次，集中在文末。""",
    tools=[seo_optimization_tool],
    llm=editor_llm,
    verbose=True,
)

# =====================================================================
# 4. Tasks
# =====================================================================

def _required_content_type() -> str:
    return least_used_content_type(list_published_content_types())


def _content_type_in_brief() -> str:
    path = _step_path("keyword")
    if path.is_file():
        suggested = brief_sections(path.read_text(encoding="utf-8")).get(
            "suggested_content_type", ""
        )
        for name in CONTENT_TYPES:
            if name in suggested:
                return name
    return _required_content_type()


def _keyword_guardrail(output) -> tuple[bool, str]:
    text = getattr(output, "raw", None) or str(output)
    return validate_keyword_brief(
        text,
        seed_keyword=SEED_KEYWORD,
        existing_titles=list_published_titles(),
        required_content_type=_required_content_type(),
    )


def _claim_guardrail(output) -> tuple[bool, str]:
    text = getattr(output, "raw", None) or str(output)
    ok, message = validate_article_claims(text)
    if not ok:
        return ok, message
    expected = _content_type_in_brief()
    actual = _infer_content_type(text)
    if actual != expected:
        hint = ""
        if expected == "FAQ型":
            hint = " FAQ 至少写 5 个「## Q: 问题？」标题。"
        return False, f"成稿类型必须是{expected}，当前识别为{actual}。{hint}"
    return True, text


research_task = Task(
    description="""针对种子词 '{seed_keyword}'，使用 Google Search Grounding 深度挖掘高价值内容素材。

    【已有文章标题——禁止重复同一角度】
    {existing_titles}

    【已有内容类型】
    {existing_content_types}

    选词门槛（写进简报；禁止编造数字）：
    1. **问题型长尾词**：## keyword 只写 1 个问句，不能是种子大词「{seed_keyword}」
    2. **搜索量**：找到公开来源就写「搜索量: 数字」和 URL，数字须在 200-2000。
       公开结果里没有，就只写一行「搜索量: 未找到公开数据」，不要为此换掉合适的问句。
    3. **KD**：找到就写「KD: 数字」和 URL，须低于 30。
       没有就只写一行「KD: 未找到公开数据」。
    4. **竞品缺口**：## competitor_keyword_gap 写竞品页面 URL，以及一行「缺口词: …」
       （对方在排、已有标题没覆盖的那个词）

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
    
    5. **内容类型**：本篇必须是 {preferred_content_type}。
       ## suggested_content_type 只写这个类型，不要因为素材像分析就改成别的。
       若是 FAQ型，正文稍后会要求至少 5 个「## Q:」标题。

    【禁止】无联网依据时凭空编造数据和URL。
    
    【输出格式】Markdown 简报：
    ## keyword
    ## search_volume
    ## keyword_difficulty
    ## competitor_keyword_gap
    ## user_persona
    ## pain_points（含量化数据）
    ## quantitative_data（至少1条，标注来源）
    ## evidence_urls（至少3个，每个带摘要）
    ## competitor_gaps（竞品缺陷，可选）
    ## suggested_content_type（推荐内容类型+理由）
    ## suggested_h1（独特标题草案）
    ## unique_angle（本篇独特角度，30字内说明与已有文章的差异）""",
    expected_output=(
        "Markdown 研究简报：1 个问题型长尾词；搜索量和 KD 要么是带来源的合格数字，"
        "要么写明未找到公开数据；内容类型必须是指定的那一种；另有竞品缺口词和至少 3 个证据 URL。"
    ),
    agent=keyword_researcher,
    guardrail=_keyword_guardrail,
    guardrail_max_retries=1,
)

write_task = Task(
    description="""只根据下面这份研究简报写正文。不要重新选词，不要再跑一轮关键词研究。
    调用 product_knowledge_base，撰写高质量 Markdown 正文。

    【上一步结果：研究简报】
    {research_brief}

    【已有文章标题——H1 不得雷同或换皮重复】
    {existing_titles}

    【内容类型要求】
    本篇必须使用 {preferred_content_type}。只套这一种模板，不要改成深度分析或其他类型。
    
    **模板A：深度分析型（1200-1800字）**
    结构：问题场景 → 问题为何发生（含量化数据和 URL）→ 表现与影响 →
          读者可以做的核对 → 文末一段产品能力（只复述知识库，并写限制）
    特点：主体是问题机制，不是产品方案
    
    **模板B：对比评测型（1000-1500字）**
    结构：问题场景 → 简报里有 URL 的事实 → 这些事实说明了问题的哪一面 →
          文末一段产品能力（只复述知识库，并写限制）
    特点：没有简报中的实测，就不做评分表，不写「优秀 / 极佳」，不宣布赢家
    
    **模板C：教程指南型（1000-1400字）**
    结构：问题场景 → 为什么困难 → 读者能做的步骤（3-5步）→
          常见核对点 → 文末可把产品作为可选的一步
    特点：步骤针对问题本身
    
    **模板D：FAQ型（800-1200字）**
    结构：引入这个问题 → 至少 5 个 Q&A（每个都是一行 H2：## Q: 问题？，答案先解释问题）→
          文末一段产品能力（只复述知识库，并写限制）
    特点：每个答案独立可读。少于 5 个「## Q:」不会被算成 FAQ。
    
    **模板E：案例故事型（1000-1500字）**
    结构：复述简报中带 URL 的抱怨 → 这个场景里问题如何发生 →
          文末一段产品能力（只复述知识库，并写限制）
    特点：简报里没有的人物、结局、效果，不要编

    【通用写作要求】
    1. **H1标题**：使用研究员的 suggested_h1 或自拟更优标题
       - 必须包含简报 ## keyword 里的那个长尾词
       - 必须独特、包含痛点关键词、激发点击欲
       - 可使用数字、疑问句、对比、情感词
    
    2. **证据引用**（必须）：
       - 至少引用 2 个研究简报中的真实证据
       - 标注来源（"知乎用户XXX表示"/"根据XXX调研"）
       - 必须引用量化数据（如有）
    
    3. **产品**：
       - 调用 product_knowledge_base，只复述返回的句子
       - 「译比邻」全文最多 4 次，放在文末一小节
       - 这一节必须带上知识库第 6 条限制：复杂版式仍需人工核对
    
    4. **内容增强元素**（根据类型选用）：
       - 带数字的小标题（"3个核心原因"），数字来自简报
       - FAQ小节，先回答问题
       - 注意事项/Tips
       - 只引用简报里已有 URL 的用户原话
    
    5. **可信**：
       - 专业性来自把问题机制讲清楚
       - 引用简报中的 URL
       - 简报里没有的测试、样本、评分，不要写
    
    6. **可读性**：
       - 段落不超过 4 行
       - 使用小标题分割（H2/H3）
       - 适当使用加粗、列表
       - 避免AI套话（"在当今"、"综上所述"、"赋能"等）
    
    7. **结尾**：可以用一次「可以打开 yibelin.com 试一份自己的文件」，说明结果仍需核对

    【禁止】
    - 禁止夸大：不用「终极」「彻底解决」「完美」「前所未有」「革命性」「精准还原」「100%」「经过测试」
    - 禁止贬低竞品：不写其他工具「不行 / 只翻文字 / 都做不到」，不打分，不宣布译比邻赢了
    - 禁止过度营销：不用「一站式」「终结焦虑」「数字修复师」；不编用户原话和人物结局
    - 尽量还原问题本身：正文主体写这个问题为何发生、表现是什么
    - 禁止编造简报里没有的数据和 URL
    - 禁止与已有文章换皮重复""",
    expected_output=(
        "800-1800 字 Markdown：先把这一个问题写清楚，证据来自简报；"
        "文末才用不超过 4 次的「译比邻」复述知识库能力，并写明仍需人工核对。"
    ),
    agent=content_writer,
    guardrail=_claim_guardrail,
    guardrail_max_retries=1,
)

edit_task = Task(
    description="""只审下面这份草稿，输出可上线 Markdown。不要重新选题，不要重写一份新题目。

    【上一步结果：待审草稿】
    {draft_markdown}

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
       - 对于对比型，只保留简报里有 URL 的事实，不补评分表
       - 结尾最多一次试用引导，并说明结果仍需核对
    
    6. **问题本身**：
       - 主体是否在解释这个问题为何发生、表现是什么？
       - 「译比邻」是否只在文末出现，且全文不超过 4 次？
       - 产品句子是否只复述知识库，并写了复杂版式仍需人工核对？
       - 内容类型是否仍是简报指定的那一种？FAQ 要保留至少 5 个「## Q:」标题。
    
    【改写动作】
    - 夸大句改成问题机制，或改成知识库原话
    - 贬低竞品的句子删掉，只保留简报里有 URL 的事实
    - 广告腔、没有来源的「经过测试」和用户原话删掉
    - 若缺少证据支撑，补充研究简报中的引用
    - 若关键词密度不足，在小标题和段落中自然增加
    - 若结构混乱，把问题解释放到前面，产品放到文末
    
    【不要】
    - 不要为了凑字数而注水
    - 不要删掉研究简报中的真实数据和引用
    - 不要把长文压缩成短文
    - 不要为了「更有说服力」把「尽量保留」写成「彻底解决」

    最终输出：问题写清楚、没有夸大和贬低的 Markdown 终稿。""",
    expected_output=(
        "可上线 Markdown 终稿：问题本身写清楚，证据来自简报，"
        "无夸大、无贬低竞品、无广告腔，产品只在文末按知识库复述。"
    ),
    agent=seo_editor,
    guardrail=_claim_guardrail,
    guardrail_max_retries=1,
)

print("✅ 第二步：Agent / Task 组装完成（研究员已启用 Google Search Grounding）")


def _factory_inputs() -> dict:
    existing = list_published_titles()
    existing_types = list_published_content_types()
    type_stats: dict[str, int] = {}
    for content_type in existing_types:
        type_stats[content_type] = type_stats.get(content_type, 0) + 1
    print(f"📚 已有文章 {len(existing)} 篇（用于选题/标题去重）")
    print(f"📊 内容类型分布：{type_stats}")
    preferred = least_used_content_type(existing_types)
    print(f"📎 本篇指定类型：{preferred}")
    return {
        "seed_keyword": SEED_KEYWORD,
        "preferred_content_type": preferred,
        "existing_titles": (
            "\n".join(f"- {title}" for title in existing)
            if existing
            else "- （暂无已发布文章）"
        ),
        "existing_content_types": (
            "\n".join(f"- {name}: {count}篇" for name, count in sorted(type_stats.items()))
            if type_stats
            else "- （暂无统计）"
        ),
    }


def _step_path(step: str) -> Path:
    return RUN_DIR / STEP_FILES[step]


def _save_step(step: str, text: str) -> Path:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    path = _step_path(step)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def _load_step(step: str) -> str:
    path = _step_path(step)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def _show_step(step: str, path: Path, text: str) -> None:
    print(f"\n=================== {step} 结果 ===================")
    print(f"文件: {path}")
    if step == "keyword":
        sections = brief_sections(text)

        def first_line(name: str) -> str:
            body = sections.get(name, "").strip()
            return body.splitlines()[0] if body else "（无）"

        print(f"关键词: {first_line('keyword')}")
        print(f"搜索量: {first_line('search_volume')}")
        print(f"难度: {first_line('keyword_difficulty')}")
        print(f"缺口: {first_line('competitor_keyword_gap')}")
    print(text.strip())
    print("================================================\n")


def _kickoff(agents: list, tasks: list, inputs: dict) -> str:
    crew = Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )
    return str(crew.kickoff(inputs=inputs)).strip()


def run_keyword() -> str:
    print("只跑关键词提取：种子词 → 长尾词简报。不写正文、不发布。")
    text = _kickoff([keyword_researcher], [research_task], _factory_inputs())
    path = _save_step("keyword", text)
    _show_step("keyword", path, text)
    print("下一步只读这个文件：python main.py --step write")
    return text


def run_write() -> str:
    brief = _load_step("keyword")
    print(f"只跑写作。输入只有: {_step_path('keyword')}")
    text = _kickoff(
        [content_writer],
        [write_task],
        {**_factory_inputs(), "research_brief": brief},
    )
    path = _save_step("write", text)
    _show_step("write", path, text)
    print("下一步只读这个文件：python main.py --step edit")
    return text


def run_edit() -> str:
    draft = _load_step("write")
    print(f"只跑编辑。输入只有: {_step_path('write')}")
    text = _kickoff(
        [seo_editor],
        [edit_task],
        {**_factory_inputs(), "draft_markdown": draft},
    )
    path = _save_step("edit", text)
    _show_step("edit", path, text)
    print("下一步只读这个文件：python main.py --step publish")
    return text


def run_publish() -> str:
    final = _load_step("edit")
    print(f"只发布。输入只有: {_step_path('edit')}")
    html_path = publish_static_page(final, seed_keyword=SEED_KEYWORD)
    print(f"静态页: {html_path}")
    return str(html_path)


def run_all() -> str:
    print("按步跑完整流水线：挖词 → 写作 → 编辑 → 发布。每步结果写入 runs/latest/。")
    run_keyword()
    run_write()
    run_edit()
    return run_publish()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="译比邻 SEO 工厂")
    parser.add_argument(
        "--step",
        choices=("keyword", "write", "edit", "publish", "all"),
        default="all",
        help=(
            "keyword 只挖词；write 只根据上一次挖词结果写草稿；"
            "edit 只审上一次草稿；publish 只发布上一次终稿；all 按这个顺序全跑"
        ),
    )
    args = parser.parse_args()
    runners = {
        "keyword": run_keyword,
        "write": run_write,
        "edit": run_edit,
        "publish": run_publish,
        "all": run_all,
    }

    print("🚀 SEO 工厂启动（Vertex Gemini + Google Search Grounding）...")
    try:
        runners[args.step]()
    except FileNotFoundError as e:
        print(f"❌ 缺少上一步结果：{e}")
        print("先跑：python main.py --step keyword")
        print("然后：python main.py --step write")
        print("然后：python main.py --step edit")
        print("然后：python main.py --step publish")
    except Exception as e:
        print(
            f"❌ 运行异常。请检查 Vertex 凭证 / GOOGLE_CLOUD_PROJECT，"
            f"以及项目是否已开通 Vertex AI 与 Grounding。"
            f"错误: {_redact_secrets(str(e))}"
        )
