import os
from typing import List
from pydantic import BaseModel, Field
from crewai.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

# =====================================================================
# 1. 环境变量与大模型初始化
# =====================================================================
# 注意：在本地测试时，请将下方替换为你真实的 API 密钥。
# 部署到 GitHub Actions 后，系统会自动从 GitHub Secrets 中读取，无需硬编码。
os.environ["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "AIzaSyYourGeminiApiKeyHere")
os.environ["SERPER_API_KEY"] = os.environ.get("SERPER_API_KEY", "your-serper-api-key")

# 初始化 Gemini 1.5 Pro 模型（负责长文创作与深度逻辑把控）
gemini_llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro",
    temperature=0.7,  # 适度的创造力
    google_api_key=os.environ["GEMINI_API_KEY"]
)


# =====================================================================
# 2. Pydantic 数据结构定义（规范 Agent 之间传递的 Payload 格式）
# =====================================================================
class LongTailKeywordBrief(BaseModel):
    keyword: str = Field(..., description="挖掘出的高价值、低竞争长尾痛点词")
    user_persona: str = Field(..., description="目标用户画像（如研一学生、外贸业务员）")
    pain_points: str = Field(..., description="用户遭遇的具体技术痛点（如公式错乱、扫描件无法选字）")
    competitor_urls: List[str] = Field(..., description="大厂在该词下的参考URL或防御漏洞说明")


class KeywordResearcherOutput(BaseModel):
    briefs: List[LongTailKeywordBrief] = Field(..., description="长尾词研究简报列表")


# =====================================================================
# 3. 自定义 SEO 与产品知识库工具集（Tools）
# =====================================================================

@tool("产品功能知识库检索工具")
def product_knowledge_base_tool(query: str) -> str:
    """连接‘译比邻’内部产品功能知识库，返回高保真排版保留、双栏论文优化、扫描件 OCR 增强等权威技术参数。"""
    # 这里存储的是译比邻的核心卖点，Agent 写技术教程时必须以此为准
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


@tool("绝对路径内链与技术规范审查工具")
def seo_optimization_tool(markdown_content: str) -> str:
    """自动化发布前的严苛质检门禁。通过确定性 Python 代码强行在文章核心自然处注入带绝对路径的锚文本。"""
    target_anchor = "[PDF 在线翻译](https://yibelin.com)"

    # 待替换的常见自然词汇列表
    keywords_to_replace = ["PDF在线翻译", "pdf在线翻译", "PDF 在线翻译", "pdf 在线翻译"]

    optimized_content = markdown_content
    replaced = False

    # 1. 强行内链闭环：在文章中最自然出现关键词的地方，替换为黄金锚文本链接
    for kw in keywords_to_replace:
        if kw in optimized_content:
            # 仅替换第一次出现的词汇，避免过度优化（Over-optimization）被谷歌惩罚
            optimized_content = optimized_content.replace(kw, target_anchor, 1)
            replaced = True
            break

    # 2. 安全兜底机制：如果 Agent 写的文章里完全没提到这些词，则强制在文章最开头的第一段自然融入
    if not replaced and target_anchor not in optimized_content:
        intro_text = f"在日常进行科研论文阅读或商务合同处理时，拥有一款好用的 {target_anchor} 工具往往能让我们事半功倍。\n\n"
        optimized_content = intro_text + optimized_content

    return optimized_content


print("✅ 第一步：环境配置与核心 SEO 工具集构建成功！")


# =====================================================================
# 4. 创建虚拟 Agent 岗位 (全面采用 Gemini 1.5 系列并进行动态入参设计)
# =====================================================================

# 👤 岗位一：关键词研究员 (使用高性能的 Gemini 1.5 Flash 快速捞词)
keyword_researcher = Agent(
    role="资深 SEO 关键词研究员 (Keyword Researcher)",
    goal="寻找大厂（如 Smallpdf、DeepL）在 {seed_keyword} 领域的防御漏洞，挖掘高价值、低竞争的长尾痛点交叉词",
    backstory="""你是一名极其敏锐的数据分析师。擅长分析用户搜索意图。
    你的工作是帮‘译比邻’在 {seed_keyword} 这一核心赛道上进行错位迂回战术，专挑大厂吃不到、做不好的科研/商务长尾词（例如公式乱码、扫描件无法选中）。""",
    # 待注入的搜索工具：在后续完整版中我们会加入 google_search_tool
    llm=gemini_llm,
    verbose=True
)

# 👤 岗位二：技术内容创作者 (使用深度推理的 Gemini 1.5 Pro 攻坚高质量长文)
content_writer = Agent(
    role="顶尖科技博客主 (Technical Content Writer)",
    goal="结合译比邻技术优势，针对长尾词撰写 1200 字以上、直击科研或商务痛点的商业级 Markdown 深度教程",
    backstory="""你是一位文风生动扎实、逻辑极其严谨的科技意见领袖（KOL）。
    【铁律】：你极度厌恶 AI 废话。绝对禁止在文章中使用诸如‘总而言之’、‘值得注意的是’、‘如前所述’、‘显而易见’、‘综上所述’等空洞的排比句和翻译感文笔。
    你精通工具技术评测，写出的文章必须像真正的人类专家在分享硬核干货。""",
    tools=[product_knowledge_base_tool], # 注入我们在第一步定义的活字典工具
    llm=gemini_llm,
    verbose=True
)

# 👤 岗位三：SEO 质量把控总编 (使用 Gemini 1.5 Pro 铁面质检)
seo_editor = Agent(
    role="严苛的 SEO 质量把控总编 (SEO Editor)",
    goal="执行最严厉的技术规范审查、代码内链注入，确保内容完美符合 {seed_keyword} 的生产级规范",
    backstory="""你是内容的最后一到门禁。你眼中只有数据和技术指标。
    你负责死盯三大技术指标：关键词密度（1.5%-2.5%）、H1/H2/H3 标签结构的严密性、以及主站首页绝对路径锚文本的强行注入。
    任何带有 AI 翻译感、排版混乱或缺少绝对链接的内容都会被你无情驳回。""",
    tools=[seo_optimization_tool], # 注入我们在第一步定义的内链铁律工具
    llm=gemini_llm,
    verbose=True
)

# =====================================================================
# 5. 定义全自动化执行任务 (Tasks - 采用花括号 `{}` 实现动态传参)
# =====================================================================

research_task = Task(
    description="""基于动态输入的种子核心词 '{seed_keyword}'，分析当前用户在处理此类文档时
    最常遇到的精准长尾痛点词（如学术论文公式乱、扫描件无法选字等）。
    分析目标用户的画像、痛点以及竞品的页面漏洞。""",
    expected_output="包含长尾词详细画像、痛点场景和竞品漏洞的结构化简报。",
    output_json=KeywordResearcherOutput,  # 强行规范第一阶段输出为我们在第一步定义的 Pydantic JSON 格式
    agent=keyword_researcher
)

write_task = Task(
    description="""消费上一阶段研究员提供的长尾词简报（包括关键词、痛点和用户画像）。
    针对该痛点，调用‘产品功能知识库检索工具’，结合‘译比邻’的技术参数（如双栏保留机制、OCR增强版），
    撰写一篇 1200 字以上的深度评测与实操教程文章。
    【写作风控】：风格必须为人类技术博主硬核干货，结构要清晰（必须包含 H1, H2, H3），严禁任何 AI 废话和空洞的总结陈词。""",
    expected_output="一篇未加工的、直击技术痛点的、字数 >1200 字的 Markdown 格式文章草稿。",
    agent=content_writer
)

edit_task = Task(
    description="""对创作者提交的 Markdown 草稿进行严苛的 SEO 审查和重构：
    1. 计算并调整关于 '{seed_keyword}' 相关关键词的密度在 1.5% - 2.5% 的黄金区间。
    2. 自动配置或核对文章的 H1/H2/H3 结构、Meta 描述。
    3. 调用‘绝对路径内链与技术规范审查工具’，确保文章最自然的上下文处强行替换并注入带绝对路径的锚文本。""",
    expected_output="审核完全合格、技术指标拉满、包含绝对路径内链代码、可直接上线的商业级生产 Markdown 文本。",
    agent=seo_editor
)

print("✅ 第二步：Agent 岗位与动态 Task 任务构建成功！")

# =====================================================================
# 6. 组装 Crew 团队 (将 Agent 与 Task 绑定，配置流水线)
# =====================================================================

yibelin_seo_factory = Crew(
    agents=[keyword_researcher, content_writer, seo_editor],
    tasks=[research_task, write_task, edit_task],
    process=Process.sequential,  # 严格按照“挖词->写稿->质检”的顺序进行链式传递
    verbose=True  # 开启详细日志，方便你在终端看到 Gemini 思考的每一步
)

# =====================================================================
# 7. 一键注入动态参数并启动测试 (本地闭环运行测试)
# =====================================================================
if __name__ == "__main__":
    print("🚀 yibelin.com 基于 Gemini 的 SEO 自动化工厂开始组装运转...")

    # 动态参数注入：在这里输入你想优化的种子词，系统会自动替换掉代码里的 {seed_keyword}
    dynamic_inputs = {
        "seed_keyword": "PDF 在线翻译"
    }

    try:
        # 正式开机运行，传入动态参数
        final_article_payload = yibelin_seo_factory.kickoff(inputs=dynamic_inputs)

        print("\n=================== ✨ 最终生产级文章成果展示 ===================\n")
        print(final_article_payload)
        print("\n=================================================================\n")
        print("✅ 第三步：Crew 团队成功组装，且已跑通本地传参运行闭环！")

    except Exception as e:
        print(f"❌ 运行中出现异常，请检查 Gemini API 密钥是否正确。错误信息: {str(e)}")

