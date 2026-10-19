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
    
    description = f"""针对种子词 '{seed}'，使用 Google Search Grounding 深度挖掘高价值内容素材。

【已有文章标题——禁止重复同一角度】
{_format_existing_titles(existing_titles)}

【已有内容类型】
{_format_content_types(config)}

【GSC 近况】
{gsc_notes}

上面若列出了可优先写的查询，本篇问句优先贴近其中一条，并且避开已有标题。
上面若写的是没有数据，就按种子词继续挖一个新的{', '.join(config.keyword_types)}关键词。
两种情况都要交出简报，不要等待 GSC。

选词门槛（写进简报；禁止编造数字）：
1. **关键词**：## keyword 只写 1 个{keyword_shape}，不能是种子大词「{seed}」
2. **搜索量**：找到公开来源就写「搜索量: 数字」和 URL，数字须在 {config.search_volume_min}-{config.search_volume_max}。
   公开结果里没有，就只写一行「搜索量: 未找到公开数据」
3. **KD**：找到就写「KD: 数字」和 URL，须低于 {config.keyword_difficulty_max}。
   没有就只写一行「KD: 未找到公开数据」
4. **竞品缺口**：## competitor_keyword_gap 写竞品页面 URL，以及一行「缺口词: …」
5. **内容类型**：本篇必须是 {preferred_type}。
   ## suggested_content_type 只写这个类型，不要因为素材像别的类型就改掉。

核心要求：
- 至少 {config.evidence_min_urls} 个真实 URL 证据，每个附 50-100 字抱怨摘要
- 至少 {config.evidence_min_data_points} 个量化数据，并标注来源
- 找不到公开数字就写「未找到公开数据」，不要编造

输出这些小节：
## keyword
## search_volume
## keyword_difficulty
## competitor_keyword_gap
## user_persona
## pain_points
## quantitative_data
## evidence_urls
## suggested_content_type
## suggested_h1
## unique_angle
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
    
    expected_output = (
        f"{config.word_count_min}-{config.word_count_max} 字 Markdown：先把问题写清楚，证据来自简报；"
        f"体裁是 {preferred_type}；产品提及不超过 {config.product_mention_max} 次。"
    )
    
    def claim_guardrail(output) -> tuple[bool, str]:
        text = getattr(output, "raw", None) or str(output)
        ok, message = gate_system.validate_article_claims(text)
        if not ok:
            return ok, message
        return gate_system.validate_content_type(text, preferred_type)
    
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
1. 标题与差异化：H1 贴近本篇内容，与已有标题明显区分
2. 内容深度与证据：是否引用了研究简报中的真实证据和 URL？
3. SEO 优化：密度 {config.seo_keyword_density_min*100:.1f}%-{config.seo_keyword_density_max*100:.1f}%，调用 seo_link_injector
4. 可读性：删除 AI 套话，段落适中
5. 产品：{_product_rule(config)}
6. 内容类型必须仍是 {preferred_type}。FAQ 要保留至少 5 个「## Q:」标题。
7. 夸大句改成问题机制或知识库原话。贬低竞品、没有来源的测试和用户原话删掉。

"""
    
    expected_output = (
        "可上线 Markdown 终稿：问题写清楚、证据来自简报、"
        "无夸大、无贬低竞品、无广告腔。"
    )
    
    def claim_guardrail(output) -> tuple[bool, str]:
        text = getattr(output, "raw", None) or str(output)
        ok, message = gate_system.validate_article_claims(text)
        if not ok:
            return ok, message
        return gate_system.validate_content_type(text, preferred_type)
    
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
    product_line = _product_rule(config)
    ending = (
        "不要写自己的产品。"
        if config.product_mention_max == 0
        else "文末一段产品能力（只复述知识库，并写限制）"
    )
    return f"""
【写作要求】
1. 字数：{config.word_count_min}-{config.word_count_max} 字
2. H1 使用简报的 suggested_h1 或写得更具体，必须含 ## keyword 里的那个词，并与已有标题区分
3. 至少引用 2 个简报里的真实 URL。简报里没有的测试、样本、评分和人物结局不要写
4. {product_line}
5. 段落不超过 4 行。不用「在当今」「综上所述」「赋能」
6. 禁止夸大、禁止贬低竞品、禁止过度营销

【只套本篇指定的一种结构】
深度分析型：问题场景 → 问题为何发生（含量化数据和 URL）→ 表现与影响 → 读者可以做的核对 → {ending}
对比评测型：问题场景 → 简报里有 URL 的事实 → 这些事实说明了问题的哪一面 → {ending}。不打分，不宣布赢家
教程指南型：问题场景 → 为什么困难 → 读者能做的 3-5 步 → 常见核对点 → {ending}
FAQ型：引入这个问题 → 至少 5 个「## Q: 问题？」→ 每个答案先解释问题 → {ending}。少于 5 个不算 FAQ
案例故事型：只复述简报里带 URL 的抱怨 → 这个场景里问题如何发生 → {ending}
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
        default=None,
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
    if not args.product:
        parser.error("需要 --product，例如 yibelin")
    
    # 1. 加载产品配置
    try:
        config = ProductConfig.load(args.product)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        print(f"\n可用的产品配置：")
        from core.config import list_available_products
        for p in list_available_products():
            print(f"  - {p}")
        raise SystemExit(1)
    
    print(f"🎯 产品: {config.name}")
    print(f"🌐 域名: {config.domain}")
    print(f"📂 输出: {config.publishing_output_dir}")
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
    
    # 4. 执行流程
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
