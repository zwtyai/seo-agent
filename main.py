"""
SEO Agent 多产品自动化工厂
统一入口：支持多个产品的SEO内容生产

用法:
  python main.py --product yibelin --step all
  python main.py --product tranzify --step keyword
  python main.py --product toolnav --step write
"""

import argparse
import re
from pathlib import Path

from crewai import Crew, Process, Task

from core import (
    AgentFactory,
    KnowledgeBaseLoader,
    MultiPublisher,
    ProductConfig,
    QualityGateSystem,
)
from core.gates import _first_url, stamp_series_issue
from publish_and_monitor import gsc_research_notes
from static_publish import (
    least_used_content_type,
    list_published_content_types,
    list_published_markdown,
    list_published_titles,
)
from vertex_llm import (
    build_gemini_llm,
    configure_vertex_env,
    enable_google_search_grounding,
)

# 运行步骤文件名
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


def _step_path(config: ProductConfig, step: str) -> Path:
    """获取运行步骤文件路径"""
    run_dir = config.get_run_dir()
    return run_dir / STEP_FILES[step]


def _save_step(config: ProductConfig, step: str, text: str) -> Path:
    """保存步骤结果"""
    run_dir = config.get_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    path = _step_path(config, step)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def _load_step(config: ProductConfig, step: str) -> str:
    """加载步骤结果"""
    path = _step_path(config, step)
    if not path.is_file():
        raise FileNotFoundError(
            f"步骤 {step} 的结果文件不存在: {path}\n"
            f"请先运行: python main.py --product {config.id} --step {step}"
        )
    return path.read_text(encoding="utf-8")


def _show_step(step: str, path: Path, text: str) -> None:
    """显示步骤结果摘要"""
    print(f"\n=================== {step} 结果 ===================")
    print(f"文件: {path}")
    
    if step == "keyword":
        # 显示关键词摘要
        lines = text.strip().split("\n")
        for line in lines[:15]:  # 只显示前15行
            print(line)
        if len(lines) > 15:
            print(f"... (共 {len(lines)} 行)")
    else:
        # 显示字数统计
        word_count = len(text)
        print(f"字数: {word_count}")
        print(text[:300] + "..." if len(text) > 300 else text)
    
    print("================================================\n")


def _kickoff(agents: list, tasks: list, inputs: dict) -> str:
    """执行CrewAI流程"""
    crew = Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )
    return str(crew.kickoff(inputs=inputs)).strip()


def create_research_task(
    researcher,
    config: ProductConfig,
    gate_system: QualityGateSystem,
    existing_titles: list[str],
    gsc_notes: str,
) -> Task:
    """创建研究任务"""
    seed = _choose_seed(config)
    preferred_type = _get_preferred_content_type(config)
    keyword_shape = "问题型长尾词" if config.keyword_gate_require_question_type else "长尾词"
    
    faq_note = (
        "若是 FAQ型，正文稍后会要求至少 5 个「## Q:」标题。"
        if preferred_type == "FAQ型"
        else ""
    )
    scene_note = ""
    if config.keyword_scene_hints:
        scene_note = "优先这些具体场景：" + "、".join(config.keyword_scene_hints) + "。"
    description = f"""针对种子词 '{seed}'，使用 Google Search Grounding 深度挖掘高价值内容素材。

【已有文章标题——禁止重复同一角度】
{_format_existing_titles(existing_titles)}

【已有内容类型】
{_format_content_types(config)}

【GSC 近况】
{gsc_notes}

上面若列出了可优先写的查询，本篇问句优先贴近其中一条，并且避开已有标题。
上面若写的是没有数据，就按种子词继续挖一个新的{keyword_shape}。两种情况都要交出简报，不要等待 GSC。

选词门槛（写进简报；禁止编造数字）：
1. **{keyword_shape}**：## keyword 下面只写 1 个词，不能是种子大词「{seed}」
2. **搜索量**：找到公开来源就写「搜索量: 数字」和 URL，数字须在 {config.search_volume_min}-{config.search_volume_max}。
   公开结果里没有，就只写一行「搜索量: 未找到公开数据」，不要为此换掉合适的词。
3. **KD**：找到就写「KD: 数字」和 URL，须低于 {config.keyword_difficulty_max}。
   没有就只写一行「KD: 未找到公开数据」。
4. **竞品缺口**：## competitor_keyword_gap 写竞品页面 URL，以及一行「缺口词: …」
   （对方在排、已有标题没覆盖的那个词）

核心要求：
1. **长尾痛点**：找到 1 个与已有文章明显不同的具体场景。必须可感知，不要泛泛而谈。{scene_note}
2. **量化数据**（至少 {config.evidence_min_data_points} 条，标注来源；没有就写「未找到公开数据」）：
   - 用户抱怨的频次（「知乎上某问题有多少个回答」）
   - 错误率或失败率
   - 时间成本（「手动处理需要多久」）
   - 调研数字（「多少比例的用户遇到此问题」）
3. **真实证据**：至少 {config.evidence_min_urls} 个真实 URL（知乎、Reddit、论坛、博客、竞品页面）。每个 URL 附 50-100 字抱怨摘要。优先带具体场景和情绪的原话。
4. **竞品页面**：只记录 URL 和页面里有依据的原话。不要写「竞品很差」。可选写对方在哪个环节做不到，但必须有 URL。
5. **内容类型**：本篇必须是 {preferred_type}。
   ## suggested_content_type 只写这个类型，不要因为素材像别的类型就改掉。
   {faq_note}

【禁止】无联网依据时凭空编造数据和 URL。不要把关键词写成文章标题。不要使用 ###。

【输出格式】每个小节都是单独一行、行首的二级标题，名字必须如下。关键词写在 ## keyword 的下一行。

## keyword
（这里写 1 个{keyword_shape}）
## search_volume
（搜索量: 数字 加来源 URL，或一行「搜索量: 未找到公开数据」）
## keyword_difficulty
（KD: 数字 加来源 URL，或一行「KD: 未找到公开数据」）
## competitor_keyword_gap
（竞品页面 URL，以及一行「缺口词: …」）
## user_persona
## pain_points
（含量化数据）
## quantitative_data
（至少 {config.evidence_min_data_points} 条，标注来源）
## evidence_urls
（至少 {config.evidence_min_urls} 个，每个带摘要）
## suggested_content_type
{preferred_type}
## suggested_h1
（独特标题草案）
## unique_angle
（30 字内，说明与已有文章的差异）
## competitor_gaps
（可选。竞品局限，必须来自上面的 URL）
"""
    
    expected_output = (
        f"Markdown 研究简报：1 个{keyword_shape}；"
        f"搜索量和 KD 要么是带来源的合格数字，要么写明未找到公开数据；"
        f"内容类型必须是 {preferred_type}；另有竞品缺口词和至少 {config.evidence_min_urls} 个证据 URL。"
    )
    
    def keyword_guardrail(output) -> tuple[bool, str]:
        text = getattr(output, "raw", None) or str(output)
        return gate_system.validate_keyword_brief(
            text,
            existing_titles,
            required_content_type=preferred_type,
        )
    
    return Task(
        description=description,
        expected_output=expected_output,
        agent=researcher,
        guardrail=keyword_guardrail,
        guardrail_max_retries=1,
    )


def create_write_task(
    writer,
    config: ProductConfig,
    gate_system: QualityGateSystem,
    research_brief: str,
    existing_titles: list[str],
) -> Task:
    """创建写作任务"""
    preferred_type = _get_preferred_content_type(config)
    
    description = f"""只根据下面这份研究简报写正文。不要重新选词，不要再跑一轮关键词研究。

【上一步结果：研究简报】
{research_brief}

【已有文章标题——H1 不得雷同或换皮重复】
{_format_existing_titles(existing_titles)}

【内容类型要求】
本篇必须使用 {preferred_type}。只套这一种模板，不要改成其他类型。

{_writing_guide(config)}
"""
    
    if config.product_mention_max == 0:
        expected_output = (
            f"{config.word_count_min}-{config.word_count_max} 字 Markdown：先把问题写清楚，证据来自简报；"
            f"体裁是 {preferred_type}；不要写本站自己的产品名。"
        )
    else:
        mandatory = "、".join(config.knowledge_base_mandatory_mentions) or "知识库里的限制"
        expected_output = (
            f"{config.word_count_min}-{config.word_count_max} 字 Markdown：先把这一个问题写清楚，证据来自简报；"
            f"体裁是 {preferred_type}；"
            f"文末才用不超过 {config.product_mention_max} 次的「{config.name}」复述知识库能力，并写明{mandatory}。"
        )
    
    def claim_guardrail(output) -> tuple[bool, str]:
        text = getattr(output, "raw", None) or str(output)
        ok, revised = gate_system.validate_article_claims(text)
        if not ok:
            return ok, revised
        return gate_system.validate_content_type(revised, preferred_type)
    
    return Task(
        description=description,
        expected_output=expected_output,
        agent=writer,
        guardrail=claim_guardrail,
        guardrail_max_retries=1,
    )


def create_edit_task(
    editor,
    config: ProductConfig,
    gate_system: QualityGateSystem,
    draft_markdown: str,
    existing_titles: list[str],
) -> Task:
    """创建编辑任务"""
    preferred_type = _get_preferred_content_type(config)
    description = f"""只审下面这份草稿，输出可上线 Markdown。不要重新选题，不要重写一份新题目。

【上一步结果：待审草稿】
{draft_markdown}

【已有文章标题】
{_format_existing_titles(existing_titles)}

【质量检查清单】
1. **标题与差异化**：H1 贴近本篇内容，与已有标题明显区分。标题包含核心关键词。
2. **内容深度与证据**：是否引用了研究简报中的真实证据和 URL？是否有量化数据？避免与已有文章论点重复。
3. **SEO 优化**：关键词密度约 {config.seo_keyword_density_min*100:.1f}%-{config.seo_keyword_density_max*100:.1f}%，自然出现，不堆砌。H1/H2/H3 清楚。必须调用 seo_link_injector。
4. **可读性**：删除「在当今时代」「综上所述」「赋能」「助力」。段落不超过 4 行。保留真实抱怨引用。
5. **内容完整性**：字数保持在 {config.word_count_min}-{config.word_count_max}。教程步骤要能执行。对比只保留简报里有 URL 的事实，不补评分表。结尾最多一次试用引导，并说明结果仍需核对。
6. **问题本身**：主体是否在解释这个问题为何发生、表现是什么？
   {_product_rule(config)}
   内容类型必须仍是 {preferred_type}。FAQ 要保留至少 5 个「## Q:」标题。
7. {_forbidden_lines(config)}

【改写动作】
- 夸大句改成问题机制，或改成知识库原话
- 贬低竞品的句子删掉，只保留简报里有 URL 的事实
- 广告腔、没有来源的测试和用户原话删掉
- 若缺少证据，补充研究简报中的引用
- 若结构混乱，把问题解释放到前面，产品放到文末

【不要】
- 不要为了凑字数而注水
- 不要删掉研究简报中的真实数据和引用
- 不要把长文压缩成短文
- 不要把「尽量保留」写成夸大说法

最终输出：问题写清楚、没有夸大和贬低的 Markdown 终稿。
"""
    
    expected_output = (
        "可上线 Markdown 终稿：问题本身写清楚，证据来自简报，"
        "无夸大、无贬低竞品、无广告腔，产品只在文末按知识库复述。"
    )
    
    def claim_guardrail(output) -> tuple[bool, str]:
        text = getattr(output, "raw", None) or str(output)
        ok, revised = gate_system.validate_article_claims(text)
        if not ok:
            return ok, revised
        return gate_system.validate_content_type(revised, preferred_type)
    
    return Task(
        description=description,
        expected_output=expected_output,
        agent=editor,
        guardrail=claim_guardrail,
        guardrail_max_retries=1,
    )


def _site_dir(config: ProductConfig) -> Path:
    return config.get_output_dir()


def _choose_seed(config: ProductConfig) -> str:
    """本篇种子词：已发布文章里出现最少的那个。"""
    return config.choose_seed_keyword(list_published_markdown(_site_dir(config)))


def _get_preferred_content_type(config: ProductConfig) -> str:
    """本篇体裁：该产品已发布文章里篇数最少的类型。"""
    published = list_published_content_types(_site_dir(config))
    order = config.get_content_type_priority()
    if order:
        return least_used_content_type(published, order)
    return least_used_content_type(published)


def _forbidden_lines(config: ProductConfig) -> str:
    """写进提示的禁词，与成稿质检用的是同一份配置。"""
    groups = (
        ("禁止夸大", config.claim_gate_forbidden_hype),
        ("禁止贬低竞品", config.claim_gate_forbidden_disparage),
        ("禁止过度营销", config.claim_gate_forbidden_marketing),
    )
    lines = [
        f"{label}：不用「{'」「'.join(words)}」"
        for label, words in groups
        if words
    ]
    return "\n".join(lines) or "禁止夸大、禁止贬低竞品、禁止过度营销"


def _product_rule(config: ProductConfig) -> str:
    if config.product_mention_max == 0:
        return "不要写本站自己的产品名，只写简报里的事实。"
    mandatory = "、".join(config.knowledge_base_mandatory_mentions) or "知识库里的限制"
    where = "放在文末一小节" if config.product_mention_position == "ending" else "可以分散出现"
    site = config.domain or config.seo_internal_links_target_url or "产品站点"
    return (
        f"调用知识库工具，只复述返回的句子。"
        f"「{config.name}」全文最多 {config.product_mention_max} 次，{where}。"
        f"必须写上：{mandatory}。"
        f"结尾最多一次打开 {site}，并说明结果仍需核对。"
    )


def _writing_guide(config: ProductConfig) -> str:
    if config.product_mention_max == 0:
        ending = "不要写自己的产品。"
        tutorial_ending = "不要写自己的产品。"
        product_block = "不要写本站自己的产品名，只写简报里的事实。"
        close_line = "结尾不要加本站产品试用引导。"
    else:
        ending = "文末一段产品能力（只复述知识库，并写限制）"
        tutorial_ending = "文末可把产品作为可选的一步"
        product_block = _product_rule(config)
        site = config.domain or config.seo_internal_links_target_url or "产品站点"
        close_line = f"结尾可以用一次「可以打开 {site} 试一份自己的文件」，说明结果仍需核对。"
    return f"""
**模板A：深度分析型**
结构：问题场景 → 问题为何发生（含量化数据和 URL）→ 表现与影响 →
      读者可以做的核对 → {ending}
特点：主体是问题机制，不是产品方案

**模板B：对比评测型**
结构：问题场景 → 简报里有 URL 的事实 → 这些事实说明了问题的哪一面 →
      {ending}
特点：没有简报中的实测，就不做评分表，不写「优秀 / 极佳」，不宣布赢家

**模板C：教程指南型**
结构：问题场景 → 为什么困难 → 读者能做的步骤（3-5步）→
      常见核对点 → {tutorial_ending}
特点：步骤针对问题本身

**模板D：FAQ型**
结构：引入这个问题 → 至少 5 个 Q&A（每个都是一行 H2：## Q: 问题？，答案先解释问题）→
      {ending}
特点：每个答案独立可读。少于 5 个「## Q:」不会被算成 FAQ。

**模板E：案例故事型**
结构：复述简报中带 URL 的抱怨 → 这个场景里问题如何发生 →
      {ending}
特点：简报里没有的人物、结局、效果，不要编

【通用写作要求】
1. **H1标题**：使用研究员的 suggested_h1 或自拟更优标题
   - 必须包含简报 ## keyword 里的那个长尾词
   - 必须独特，并与已有标题区分
   - 可使用数字、疑问句、对比
2. **证据引用**：至少引用 2 个研究简报中的真实证据，并标注来源。有量化数据就引用。
3. **产品**：{product_block}
4. **内容增强**：带数字的小标题，数字必须来自简报。只引用简报里已有 URL 的用户原话。
5. **可信**：专业性来自把问题机制讲清楚。简报里没有的测试、样本、评分，不要写。
6. **可读性**：段落不超过 4 行。使用 H2/H3。避免「在当今」「综上所述」「赋能」。
7. **字数**：{config.word_count_min}-{config.word_count_max} 字。
8. **结尾**：{close_line}

【禁止】
- {_forbidden_lines(config)}
- 不打分，不宣布本产品赢了
- 不编用户原话和人物结局
- 正文主体写这个问题为何发生、表现是什么
- 禁止编造简报里没有的数据和 URL
- 禁止与已有文章换皮重复
"""


def _format_existing_titles(titles: list[str]) -> str:
    """格式化已有标题列表"""
    if not titles:
        return "- （暂无已发布文章）"
    return "\n".join(f"- {title}" for title in titles[:20])


def _format_content_types(config: ProductConfig) -> str:
    """格式化内容类型分布"""
    published = list_published_content_types(_site_dir(config))
    counts: dict[str, int] = {}
    for name in published:
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        return "- （暂无已发布文章）"
    return "\n".join(f"- {name}: {count}" for name, count in counts.items())


def _series_issue_number(config: ProductConfig) -> int:
    """下一期期号。已发布几篇，下一篇就是几加一。"""
    return len(list_published_titles(_site_dir(config))) + 1


def _series_bucket(config: ProductConfig) -> str:
    """按已发布篇数轮换主题角度，避免连续几天挤在同一面。"""
    buckets = [item for item in config.keyword_scene_hints if item]
    if not buckets:
        return _choose_seed(config)
    published = len(list_published_titles(_site_dir(config)))
    return buckets[published % len(buckets)]


def create_series_find_task(
    researcher,
    config: ProductConfig,
    gate_system: QualityGateSystem,
    existing_titles: list[str],
    existing_docs: list[str],
    bucket: str,
) -> Task:
    """系列选题：一条事实加一个来源，不写搜索量和竞品。"""
    theme = _choose_seed(config)
    description = f"""为栏目「{config.name}」找 1 条还没发过的冷知识。

【主题】
{theme}

【今天优先的角度】
{bucket}

【已发标题——不要再找同一条】
{_format_existing_titles(existing_titles)}

规则：
1. 用 Google Search Grounding 找一条具体事实。要能让人「咦」一下，但不要猎奇谣言。
2. 来源必须是这次搜索打开过的页面。百科、博物馆、论文摘要、正规媒体都可以。
3. 用自己的话写事实，不要整段抄原文。
4. 找不到可打开的页面，就不要换一个编出来的 URL。## source_url 下面写「未找到」。
5. 不要写搜索量、关键词难度、竞品、产品。

【输出格式】每个小节都是单独一行、行首的二级标题。

## title
（一句话标题，不要写期号）
## fact
（两三句，说清事实本身）
## why
（一句，它和日常印象哪里相反）
## source_name
（来源站点或文章名）
## source_url
（一个 http 开头的 URL）
"""
    expected_output = "一条冷知识简报：标题、事实、一句理由、来源名、可打开的 URL。"

    def brief_guardrail(output) -> tuple[bool, str]:
        text = getattr(output, "raw", None) or str(output)
        return gate_system.validate_series_brief(text, existing_titles, existing_docs)

    return Task(
        description=description,
        expected_output=expected_output,
        agent=researcher,
        guardrail=brief_guardrail,
        guardrail_max_retries=1,
    )


def create_series_write_task(
    writer,
    config: ProductConfig,
    gate_system: QualityGateSystem,
    brief: str,
    existing_titles: list[str],
    voice: str,
    issue: int,
) -> Task:
    """把简报收成一张卡片。期号由代码写入，不让模型编号。"""
    source_url = _first_url(brief)
    description = f"""把下面这份简报收成一张「{config.name}」卡片。不要再搜索，不要换事实。

【简报】
{brief}

【栏目语气】
{voice or "短、好奇，像跟朋友说一件刚刚核对过的事。"}

【已发标题】
{_format_existing_titles(existing_titles)}

卡片只有这四段，大约 {config.word_count_min}-{config.word_count_max} 字：

# 标题
事实写两三句，用自己的话。
为什么值得说：一句，点出和日常印象相反的地方，不展开证明。
来源：[这里写简报里的来源名]({source_url})

要求：
1. H1 只写标题，不要自己加「第 N 期」。
2. 来源那一行必须原样带上这个 URL：{source_url}
3. 不要写据说、网传、听说。
4. 不要写步骤、评测、搜索量或产品推荐。
5. 简报里没有的数字和人物不要补。
"""
    expected_output = (
        f"{config.word_count_min}-{config.word_count_max} 字的 Markdown 卡片："
        "标题、事实、一句理由、带来源链接。"
    )

    def card_guardrail(output) -> tuple[bool, str]:
        text = getattr(output, "raw", None) or str(output)
        ok, revised = gate_system.validate_series_card(
            text,
            existing_titles,
            source_url=source_url,
        )
        if not ok:
            return ok, revised
        return True, stamp_series_issue(revised, issue)

    return Task(
        description=description,
        expected_output=expected_output,
        agent=writer,
        guardrail=card_guardrail,
        guardrail_max_retries=1,
    )


def run_series_find(config: ProductConfig, factory: AgentFactory, gate_system: QualityGateSystem) -> str:
    """系列：找一条带来源的事实。"""
    print(f"[{config.name}] 选题：找一条还没发过的冷知识")
    site_dir = _site_dir(config)
    existing_titles = list_published_titles(site_dir)
    existing_docs = list_published_markdown(site_dir)
    bucket = _series_bucket(config)
    print(f"已发 {len(existing_titles)} 期")
    print(f"今天的角度：{bucket}")

    researcher = factory.create_researcher(_choose_seed(config))
    if config.agent_researcher_use_grounding:
        enable_google_search_grounding(researcher.llm)

    task = create_series_find_task(
        researcher,
        config,
        gate_system,
        existing_titles,
        existing_docs,
        bucket,
    )
    text = _kickoff([researcher], [task], {})
    path = _save_step(config, "keyword", text)
    _show_step("keyword", path, text)
    print(f"简报已保存: {path}")
    print(f"下一步：python main.py --product {config.id} --step write")
    return text


def run_series_write(config: ProductConfig, factory: AgentFactory, gate_system: QualityGateSystem) -> str:
    """系列：简报收成卡片，并写成终稿。不再走 SEO 编辑。"""
    print(f"[{config.name}] 写作：简报 → 卡片")
    brief = _load_step(config, "keyword")
    voice = factory.kb_loader.load().get("content", "")
    existing_titles = list_published_titles(_site_dir(config))
    issue = _series_issue_number(config)
    writer = factory.create_writer()
    task = create_series_write_task(
        writer,
        config,
        gate_system,
        brief,
        existing_titles,
        voice,
        issue,
    )
    text = _kickoff([writer], [task], {})
    text = stamp_series_issue(text, issue)
    draft_path = _save_step(config, "write", text)
    final_path = _save_step(config, "edit", text)
    _show_step("write", draft_path, text)
    print(f"卡片已保存: {final_path}")
    print(f"下一步：python main.py --product {config.id} --step publish")
    return text


def run_series_finalize(config: ProductConfig, gate_system: QualityGateSystem) -> str:
    """不再叫编辑模型。核对卡片，通过后当作终稿。"""
    print(f"[{config.name}] 核对卡片")
    draft = _load_step(config, "write")
    brief = _load_step(config, "keyword")
    existing_titles = list_published_titles(_site_dir(config))
    ok, revised = gate_system.validate_series_card(
        draft,
        existing_titles,
        source_url=_first_url(brief),
    )
    if not ok:
        raise SystemExit(revised)
    text = stamp_series_issue(revised, _series_issue_number(config))
    path = _save_step(config, "edit", text)
    _show_step("edit", path, text)
    print(f"终稿已保存: {path}")
    return text


def run_series_all(
    config: ProductConfig,
    factory: AgentFactory,
    gate_system: QualityGateSystem,
    publisher: MultiPublisher,
) -> dict:
    """系列完整流程：找一条 → 卡片 → 发布。"""
    print(f"[{config.name}] 完整流程：找一条 → 卡片 → 发布\n")
    run_series_find(config, factory, gate_system)
    run_series_write(config, factory, gate_system)
    return run_publish(config, publisher)


def run_keyword(config: ProductConfig, factory: AgentFactory, gate_system: QualityGateSystem) -> str:
    """只跑关键词研究"""
    print(f"🔍 [{config.name}] 关键词研究：种子词 → 长尾词简报")
    
    site_dir = _site_dir(config)
    existing_titles = list_published_titles(site_dir)
    published_types = list_published_content_types(site_dir)
    type_stats: dict[str, int] = {}
    for content_type in published_types:
        type_stats[content_type] = type_stats.get(content_type, 0) + 1
    seed = _choose_seed(config)
    preferred = _get_preferred_content_type(config)
    print(f"📚 已有文章 {len(existing_titles)} 篇")
    print(f"📊 内容类型分布：{type_stats or '暂无'}")
    print(f"🔑 本篇种子词：{seed}")
    print(f"📎 本篇指定类型：{preferred}")

    researcher = factory.create_researcher(seed)
    if config.agent_researcher_use_grounding:
        enable_google_search_grounding(researcher.llm)
    
    if config.monitoring_gsc_enabled:
        gsc_notes = gsc_research_notes(
            site_url=config.monitoring_gsc_site_url,
            lookback_days=config.monitoring_gsc_lookback_days,
        )
    else:
        gsc_notes = "GSC 监控未启用。继续挖一个新的长尾，不要等待。"
    
    task = create_research_task(researcher, config, gate_system, existing_titles, gsc_notes)
    
    text = _kickoff([researcher], [task], {})
    path = _save_step(config, "keyword", text)
    _show_step("keyword", path, text)
    
    print(f"✅ 研究简报已保存: {path}")
    print(f"下一步：python main.py --product {config.id} --step write")
    return text


def run_write(config: ProductConfig, factory: AgentFactory, gate_system: QualityGateSystem) -> str:
    """只跑写作"""
    print(f"✍️  [{config.name}] 写作：研究简报 → 草稿")
    
    brief = _load_step(config, "keyword")
    writer = factory.create_writer()
    existing_titles = list_published_titles(_site_dir(config))
    
    task = create_write_task(writer, config, gate_system, brief, existing_titles)
    
    text = _kickoff([writer], [task], {})
    path = _save_step(config, "write", text)
    _show_step("write", path, text)
    
    print(f"✅ 草稿已保存: {path}")
    print(f"下一步：python main.py --product {config.id} --step edit")
    return text


def run_edit(config: ProductConfig, factory: AgentFactory, gate_system: QualityGateSystem) -> str:
    """只跑编辑"""
    print(f"📝 [{config.name}] 编辑：草稿 → 终稿")
    
    draft = _load_step(config, "write")
    editor = factory.create_editor()
    existing_titles = list_published_titles(_site_dir(config))
    
    task = create_edit_task(editor, config, gate_system, draft, existing_titles)
    
    text = _kickoff([editor], [task], {})
    path = _save_step(config, "edit", text)
    _show_step("edit", path, text)
    
    print(f"✅ 终稿已保存: {path}")
    print(f"下一步：python main.py --product {config.id} --step publish")
    return text


def run_publish(config: ProductConfig, publisher: MultiPublisher) -> dict:
    """只发布"""
    print(f"📤 [{config.name}] 发布：终稿 → 静态HTML")
    
    final = _load_step(config, "edit")
    
    results = publisher.publish(
        final,
        metadata={"seed_keyword": config.get_primary_seed_keyword()}
    )
    
    for channel, result in results.items():
        if "error" in channel:
            print(f"❌ {channel}: {result}")
        else:
            print(f"✅ {channel}: {result}")
    
    return results


def run_all(
    config: ProductConfig,
    factory: AgentFactory,
    gate_system: QualityGateSystem,
    publisher: MultiPublisher,
) -> dict:
    """完整流程"""
    print(f"🚀 [{config.name}] 完整流程：挖词 → 写作 → 编辑 → 发布\n")
    
    run_keyword(config, factory, gate_system)
    run_write(config, factory, gate_system)
    run_edit(config, factory, gate_system)
    return run_publish(config, publisher)


def main():
    parser = argparse.ArgumentParser(description="多产品 SEO 自动化工厂")
    parser.add_argument(
        "--product",
        required=True,
        help="产品ID，如 yibelin, tranzify, toolnav"
    )
    parser.add_argument(
        "--step",
        choices=("keyword", "write", "edit", "publish", "all"),
        default="all",
        help="执行步骤"
    )
    parser.add_argument(
        "--list-products",
        action="store_true",
        help="列出所有可用的产品配置"
    )
    args = parser.parse_args()
    
    # 列出产品
    if args.list_products:
        from core.config import list_available_products
        products = list_available_products()
        print("可用的产品配置：")
        for p in products:
            print(f"  - {p}")
        return
    
    # 1. 加载产品配置
    try:
        config = ProductConfig.load(args.product)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        print("\n可用的产品配置：")
        from core.config import list_available_products
        for p in list_available_products():
            print(f"  - {p}")
        raise SystemExit(1)
    
    print(f"🎯 产品: {config.name}")
    print(f"🌐 域名: {config.domain}")
    print(f"📂 输出: {config.publishing_output_dir}")
    if config.mode == "series":
        print(f"📌 模式: 系列栏目")
        print(f"🔑 主题: {', '.join(config.seed_keywords)}\n")
    else:
        print(f"🔑 种子词: {', '.join(config.seed_keywords)}\n")
    
    # 2. 初始化 Vertex LLM
    try:
        configure_vertex_env()
        researcher_llm = build_gemini_llm(temperature=config.agent_researcher_temperature)
        writer_llm = build_gemini_llm(temperature=config.agent_writer_temperature)
        editor_llm = build_gemini_llm(temperature=config.agent_editor_temperature)
        print("✅ Vertex AI Gemini 已就绪\n")
    except Exception as e:
        print(f"❌ LLM 初始化失败: {_redact_secrets(str(e))}")
        raise SystemExit(1)
    
    # 3. 创建核心组件
    kb_loader = KnowledgeBaseLoader(config)
    factory = AgentFactory(config, kb_loader, researcher_llm, writer_llm, editor_llm)
    gate_system = QualityGateSystem(config)
    publisher = MultiPublisher(config)
    
    # 4. 执行流程。系列栏目不走选词量和长文编辑。
    if config.mode == "series":
        runners = {
            "keyword": lambda: run_series_find(config, factory, gate_system),
            "write": lambda: run_series_write(config, factory, gate_system),
            "edit": lambda: run_series_finalize(config, gate_system),
            "publish": lambda: run_publish(config, publisher),
            "all": lambda: run_series_all(config, factory, gate_system, publisher),
        }
    else:
        runners = {
            "keyword": lambda: run_keyword(config, factory, gate_system),
            "write": lambda: run_write(config, factory, gate_system),
            "edit": lambda: run_edit(config, factory, gate_system),
            "publish": lambda: run_publish(config, publisher),
            "all": lambda: run_all(config, factory, gate_system, publisher),
        }
    
    try:
        runners[args.step]()
        print(f"\n🎉 [{config.name}] {args.step} 步骤完成！")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        raise SystemExit(1)
    except Exception as e:
        print(f"❌ 运行异常: {_redact_secrets(str(e))}")
        import traceback
        traceback.print_exc()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
