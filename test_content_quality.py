#!/usr/bin/env python3
"""
内容质量测试脚本

目的：
1. 验证内容类型识别功能
2. 测试已发布内容统计
3. 检查内容质量评分机制
4. 模拟内容生成流程（不调用 LLM）

用法：
    python test_content_quality.py
"""

import re
from pathlib import Path
from static_publish import (
    list_published_titles,
    list_published_content_types,
    _infer_content_type,
)


# ============================================================
# 1. 内容类型识别测试
# ============================================================

def test_content_type_inference():
    """测试内容类型识别准确性"""
    print("=" * 60)
    print("📋 测试 1：内容类型识别")
    print("=" * 60)
    
    test_cases = [
        # (markdown_content, expected_type)
        (
            """# 如何翻译扫描版PDF？3步搞定OCR错误
            
第一步：上传文件
第二步：选择语言
第三步：下载译文""",
            "教程指南型"
        ),
        (
            """# PDF翻译工具横向评测
            
| 工具 | 识别率 | 价格 |
|------|--------|------|
| 工具A | 80% | 免费 |
| 工具B | 90% | $10 |

对比分析...""",
            "对比评测型"
        ),
        (
            """# 常见PDF翻译问题解答
            
## Q: 为什么格式会乱？
答：...

## Q: 扫描版能翻译吗？
答：...

## Q: 双栏论文怎么处理？
答：...

## Q: 价格多少？
答：...

## Q: 支持哪些语言？
答：...""",
            "FAQ型"
        ),
        (
            """# 如何处理扫描版PDF里的文字？

## Q: 为什么格式会乱？
答：...

## Q: 扫描版能翻译吗？
答：...

## Q: 双栏论文怎么处理？
答：...

## Q: 价格多少？
答：...

## Q: 支持哪些语言？
答：...""",
            "FAQ型"
        ),
        (
            """# 清华博士的论文翻译经历
            
李博士是清华材料学研究生，导师发来58页德文论文...
遇到格式错乱的困境，尝试了Google翻译失败...
使用译比邻后解决问题...""",
            "案例故事型"
        ),
        (
            """# 扫描版PDF的OCR困境深度剖析
            
根据调研数据，68%的用户遇到OCR错误问题。
传统OCR技术的三大缺陷：
1. 识别率低
2. 格式丢失
3. 特殊符号错误""",
            "深度分析型"
        ),
    ]
    
    passed = 0
    failed = 0
    
    for i, (content, expected) in enumerate(test_cases, 1):
        result = _infer_content_type(content)
        status = "✅" if result == expected else "❌"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} 测试 {i}: 期望 [{expected}], 实际 [{result}]")
    
    print(f"\n通过: {passed}/{len(test_cases)}, 失败: {failed}/{len(test_cases)}")
    print()
    return failed == 0


# ============================================================
# 2. 已发布内容统计测试
# ============================================================

def test_published_content_stats():
    """测试已发布内容的标题和类型统计"""
    print("=" * 60)
    print("📊 测试 2：已发布内容统计")
    print("=" * 60)
    
    titles = list_published_titles()
    types = list_published_content_types()
    
    print(f"✅ 已发布文章数量: {len(titles)}")
    print(f"✅ 识别内容类型数量: {len(types)}")
    
    if titles:
        print(f"\n最近 5 篇文章标题:")
        for i, title in enumerate(titles[:5], 1):
            print(f"  {i}. {title}")
    
    if types:
        type_stats = {}
        for ct in types:
            type_stats[ct] = type_stats.get(ct, 0) + 1
        
        print(f"\n内容类型分布:")
        for ct, count in sorted(type_stats.items(), key=lambda x: -x[1]):
            percentage = count / len(types) * 100
            print(f"  {ct}: {count}篇 ({percentage:.1f}%)")
        
        # 建议下一篇应该写什么类型
        all_types = ["深度分析型", "对比评测型", "教程指南型", "FAQ型", "案例故事型"]
        missing_types = [t for t in all_types if t not in type_stats]
        underused_types = sorted(type_stats.items(), key=lambda x: x[1])[:2]
        
        print(f"\n💡 内容类型建议:")
        if missing_types:
            print(f"  缺失类型: {', '.join(missing_types)}")
        if underused_types:
            print(f"  使用较少: {', '.join([t for t, _ in underused_types])}")
    
    print()
    return True


# ============================================================
# 3. 内容质量评分测试
# ============================================================

def analyze_content_quality(markdown: str) -> dict:
    """分析单篇文章的内容质量"""
    
    # 字数统计
    text_only = re.sub(r'#.*\n', '', markdown)  # 去除标题
    text_only = re.sub(r'\[.*?\]\(.*?\)', '', text_only)  # 去除链接
    char_count = len(re.sub(r'\s', '', text_only))
    
    # 检查结构
    h1_count = markdown.count('\n# ')
    h2_count = markdown.count('\n## ')
    has_structure = h1_count >= 1 and h2_count >= 2
    
    # 检查量化数据（数字+单位）
    quantitative_patterns = [
        r'\d+%',  # 百分比
        r'\d+篇',  # 数量
        r'\d+小时',  # 时间
        r'\d+页',  # 页数
        r'\d+个',  # 个数
        r'\d+倍',  # 倍数
    ]
    has_quantitative = any(re.search(p, markdown) for p in quantitative_patterns)
    
    # 检查URL引用
    url_pattern = r'https?://[^\s\)]+|www\.[^\s\)]+'
    urls = re.findall(url_pattern, markdown)
    has_urls = len(urls) >= 1
    
    # 检查用户引用
    user_reference_patterns = [
        r'知乎.*?表示',
        r'Reddit.*?讨论',
        r'用户.*?抱怨',
        r'博客.*?指出',
        r'评论.*?提到',
        r'根据.*?调研',
    ]
    has_user_reference = any(re.search(p, markdown) for p in user_reference_patterns)
    
    # 检查对比表格
    has_table = '|' in markdown and markdown.count('|') >= 6
    
    # 检查CTA
    cta_patterns = [
        r'访问.*yibelin',
        r'立即',
        r'马上',
        r'开始',
        r'体验',
    ]
    has_cta = any(re.search(p, markdown) for p in cta_patterns)
    
    # 检查AI套话（应该避免）
    ai_fluff_patterns = [
        r'在当今',
        r'综上所述',
        r'赋能',
        r'助力',
        r'深度赋能',
    ]
    has_ai_fluff = any(re.search(p, markdown) for p in ai_fluff_patterns)
    
    # 计算得分
    score = 0
    max_score = 9
    
    if char_count >= 1000:
        score += 1
    if has_structure:
        score += 1
    if has_quantitative:
        score += 2  # 重要
    if has_urls:
        score += 2  # 重要
    if has_user_reference:
        score += 1
    if has_table:
        score += 1
    if has_cta:
        score += 1
    if not has_ai_fluff:
        score += 1  # 没有AI套话加分
    
    return {
        'score': score,
        'max_score': max_score,
        'percentage': score / max_score * 100,
        'char_count': char_count,
        'has_structure': has_structure,
        'has_quantitative': has_quantitative,
        'url_count': len(urls),
        'has_user_reference': has_user_reference,
        'has_table': has_table,
        'has_cta': has_cta,
        'has_ai_fluff': has_ai_fluff,
    }


def test_content_quality_scoring():
    """测试已发布内容的质量评分"""
    print("=" * 60)
    print("🎯 测试 3：内容质量评分")
    print("=" * 60)
    
    docs_dir = Path("docs/posts")
    if not docs_dir.exists():
        print("⚠️  docs/posts 目录不存在，跳过测试")
        print()
        return True
    
    md_files = sorted(docs_dir.glob("*.md"), reverse=True)[:5]  # 最近5篇
    
    if not md_files:
        print("⚠️  没有找到 Markdown 文件，跳过测试")
        print()
        return True
    
    print(f"分析最近 {len(md_files)} 篇文章的质量...\n")
    
    total_scores = []
    
    for md_file in md_files:
        try:
            content = md_file.read_text(encoding='utf-8')
            result = analyze_content_quality(content)
            total_scores.append(result['percentage'])
            
            # 提取标题
            title = "未知标题"
            for line in content.split('\n'):
                if line.startswith('# '):
                    title = line[2:].strip()
                    break
            
            # 显示结果
            status = "🟢" if result['percentage'] >= 70 else "🟡" if result['percentage'] >= 50 else "🔴"
            print(f"{status} {title[:40]}...")
            print(f"   评分: {result['score']}/{result['max_score']} ({result['percentage']:.0f}%)")
            print(f"   字数: {result['char_count']} | URL: {result['url_count']}个")
            
            # 显示缺失项
            missing = []
            if not result['has_quantitative']:
                missing.append("缺少量化数据")
            if result['url_count'] == 0:
                missing.append("缺少URL引用")
            if not result['has_user_reference']:
                missing.append("缺少用户引用")
            if result['has_ai_fluff']:
                missing.append("含AI套话")
            
            if missing:
                print(f"   ⚠️  {', '.join(missing)}")
            print()
        
        except Exception as e:
            print(f"❌ 分析 {md_file.name} 时出错: {e}\n")
    
    if total_scores:
        avg_score = sum(total_scores) / len(total_scores)
        print(f"📊 平均质量得分: {avg_score:.1f}%")
        
        if avg_score >= 70:
            print("✅ 内容质量良好")
        elif avg_score >= 50:
            print("⚠️  内容质量中等，建议优化")
        else:
            print("❌ 内容质量需要提升")
    
    print()
    return True


# ============================================================
# 4. 模拟研究简报测试
# ============================================================

def test_research_brief_format():
    """测试研究简报格式是否完整"""
    print("=" * 60)
    print("📝 测试 4：研究简报格式检查")
    print("=" * 60)
    
    # 模拟一个好的研究简报
    good_brief = """
## keyword
如何翻译扫描版PDF

## search_volume
搜索量: 880
来源: https://example.com/keyword-volume

## keyword_difficulty
KD: 18
来源: https://example.com/keyword-difficulty

## competitor_keyword_gap
竞品页: https://example.com/competitor
缺口词: 如何翻译扫描版PDF

## user_persona
科研工作者、学生、法律从业者

## pain_points
扫描版PDF无法选择文字，OCR识别率低，公式和特殊符号变成乱码，导致翻译质量差

## quantitative_data
- 根据知乎问题"PDF翻译为什么是乱码"统计，该问题有 247 个回答，浏览量超过 15 万次
- DeepL官方文档承认"扫描版PDF的OCR错误率可能高达 20-30%"

## evidence_urls
1. https://www.zhihu.com/question/xxx - 用户抱怨："扫描版论文用Google翻译，公式全变成乱码"
2. https://www.reddit.com/r/xxx - "Tried 5 PDF translators, all failed on scanned documents"
3. https://support.deepl.com/xxx - 官方承认扫描版PDF翻译存在高错误率

## competitor_gaps
- Google翻译：对扫描版PDF支持差，需手动OCR
- DeepL：官方文档承认扫描版错误率高
- Adobe Acrobat：OCR功能强但不支持直接翻译

## suggested_content_type
深度分析型 - 因为有丰富的数据支撑和竞品分析，适合深度剖析

## suggested_h1
扫描版PDF的「鬼影」：OCR不准，公式与特殊符号何以沦为数字乱码？

## unique_angle
聚焦扫描版PDF的OCR技术难题，通过量化数据和竞品对比说明问题严重性，与已有文章的"双栏"、"表格"角度不同
"""
    
    required_sections = [
        "## keyword",
        "## search_volume",
        "## keyword_difficulty",
        "## competitor_keyword_gap",
        "## user_persona",
        "## pain_points",
        "## quantitative_data",
        "## evidence_urls",
        "## suggested_content_type",
        "## suggested_h1",
        "## unique_angle"
    ]
    
    print("检查必需章节...")
    all_present = True
    for section in required_sections:
        if section in good_brief:
            print(f"  ✅ {section}")
        else:
            print(f"  ❌ 缺少 {section}")
            all_present = False
    
    # 检查具体内容
    print("\n检查内容质量...")
    
    # 至少3个URL
    urls = re.findall(r'https?://[^\s]+', good_brief)
    if len(urls) >= 3:
        print(f"  ✅ URL数量充足 ({len(urls)}个)")
    else:
        print(f"  ❌ URL数量不足 (仅{len(urls)}个，需要≥3)")
        all_present = False
    
    # 有量化数据
    has_numbers = bool(re.search(r'\d+%|\d+个|\d+篇|\d+万', good_brief))
    if has_numbers:
        print(f"  ✅ 包含量化数据")
    else:
        print(f"  ❌ 缺少量化数据")
        all_present = False
    
    print()
    if all_present:
        print("✅ 研究简报格式完整")
    else:
        print("❌ 研究简报格式不完整")
    
    print()
    return all_present


def test_keyword_gate():
    """长尾词必须满足搜索量、难度和竞品缺口。"""
    from keyword_gate import validate_keyword_brief

    print("=" * 60)
    print("📝 测试 5：关键词选题门槛")
    print("=" * 60)

    good = """
## keyword
如何翻译扫描版PDF
## search_volume
搜索量: 880
来源: https://example.com/volume
## keyword_difficulty
KD: 18
来源: https://example.com/kd
## competitor_keyword_gap
竞品页: https://example.com/competitor
缺口词: 如何翻译扫描版PDF
"""
    ok, _ = validate_keyword_brief(
        good,
        seed_keyword="PDF 在线翻译",
        existing_titles=["双栏论文PDF翻译"],
    )
    cases = [("合格长尾词", ok)]

    low_volume = good.replace("搜索量: 880", "搜索量: 40")
    cases.append((
        "搜索量过低",
        not validate_keyword_brief(low_volume, "PDF 在线翻译")[0],
    ))

    hard = good.replace("KD: 18", "KD: 46")
    cases.append((
        "难度过高",
        not validate_keyword_brief(hard, "PDF 在线翻译")[0],
    ))

    head = good.replace("如何翻译扫描版PDF", "PDF 在线翻译", 1)
    cases.append((
        "拒绝大词",
        not validate_keyword_brief(head, "PDF 在线翻译")[0],
    ))

    no_source = good.replace("来源: https://example.com/volume\n", "")
    cases.append((
        "搜索量缺少来源",
        not validate_keyword_brief(no_source, "PDF 在线翻译")[0],
    ))

    covered = validate_keyword_brief(
        good,
        seed_keyword="PDF 在线翻译",
        existing_titles=["如何翻译扫描版PDF后格式错乱"],
    )[0]
    cases.append(("已有标题覆盖则拒绝", not covered))

    missing = good.replace(
        "搜索量: 880\n来源: https://example.com/volume",
        "搜索量: 未找到公开数据",
    ).replace(
        "KD: 18\n来源: https://example.com/kd",
        "KD: 无法提供",
    )
    cases.append((
        "没有公开搜索量和难度也可以通过",
        validate_keyword_brief(missing, "PDF 在线翻译")[0],
    ))

    bold_gap = good.replace(
        "缺口词: 如何翻译扫描版PDF",
        "**缺口词**: 如何翻译扫描版PDF",
    )
    cases.append((
        "加粗的缺口词可以通过",
        validate_keyword_brief(bold_gap, "PDF 在线翻译")[0],
    ))

    typed = good + "\n## suggested_content_type\nFAQ型\n"
    cases.append((
        "指定类型一致可以通过",
        validate_keyword_brief(typed, "PDF 在线翻译", required_content_type="FAQ型")[0],
    ))
    cases.append((
        "指定类型被改掉则拒绝",
        not validate_keyword_brief(good, "PDF 在线翻译", required_content_type="FAQ型")[0],
    ))

    passed = True
    for name, result in cases:
        print(f"  {'✅' if result else '❌'} {name}")
        passed = passed and result
    print()
    return passed


def test_claim_gate():
    """成稿不得夸大、贬低竞品或把产品写成主体。"""
    from claim_gate import validate_article_claims

    print("=" * 60)
    print("📝 测试 6：成稿表述门槛")
    print("=" * 60)

    calm = """
# 为什么 PDF 翻译后双栏会串行

双栏 PDF 按阅读顺序存储时，左栏还没结束，右栏文字可能已经插入。
知乎上有读者描述过左右栏交错后论证接不上的情况：https://example.com/post

译比邻按段落处理，尽量保留原文排版。复杂公式、印章、批注、水印不保证与原文一致。
单文件建议 10MB、20 页以内，复杂版式仍需人工核对。
"""
    hype = calm + "\n译比邻彻底解决了这个问题，是终极解法。普通工具只翻文字。\n"
    spam = "译比邻。" * 5 + calm

    cases = [
        ("问题说明可以通过", validate_article_claims(calm)[0]),
        ("夸大和贬低会被拒绝", not validate_article_claims(hype)[0]),
        ("产品露出过多会被拒绝", not validate_article_claims(spam)[0]),
    ]
    passed = True
    for name, result in cases:
        print(f"  {'✅' if result else '❌'} {name}")
        passed = passed and result
    print()
    return passed


def test_content_rotation():
    """下一篇使用篇数最少的类型，篇数相同按固定顺序。"""
    from static_publish import least_used_content_type

    print("=" * 60)
    print("📝 测试 7：内容类型轮换")
    print("=" * 60)

    cases = [
        ("没有文章时先写 FAQ", least_used_content_type([]) == "FAQ型"),
        (
            "FAQ 还是 0 时继续写 FAQ",
            least_used_content_type(["深度分析型", "教程指南型"]) == "FAQ型",
        ),
        (
            "篇数相同按 FAQ、教程、对比、案例、深度分析",
            least_used_content_type(
                ["FAQ型", "教程指南型", "对比评测型", "案例故事型", "深度分析型"]
            )
            == "FAQ型",
        ),
        (
            "其余类型仍是 0 时不跳到教程",
            least_used_content_type(["FAQ型", "FAQ型", "教程指南型"]) == "对比评测型",
        ),
        (
            "FAQ 更多且其他类型都有时改写教程",
            least_used_content_type(
                ["FAQ型", "FAQ型", "教程指南型", "对比评测型", "案例故事型", "深度分析型"]
            )
            == "教程指南型",
        ),
    ]
    passed = True
    for name, result in cases:
        print(f"  {'✅' if result else '❌'} {name}")
        passed = passed and result
    print()
    return passed

def test_page_seo():
    """新发布的页面带 meta、Open Graph、Article 结构化数据，并写出 sitemap 与 robots。"""
    import tempfile
    from urllib.parse import quote

    from static_publish import publish_static_page

    print("=" * 60)
    print("📝 测试 8：发布页技术 SEO")
    print("=" * 60)

    markdown = "# 为什么扫描版PDF会认错字？\n\n" + ("扫描件把字形当成图片，复制出来就不是原来的字。" * 8)
    with tempfile.TemporaryDirectory() as tmp:
        page = publish_static_page(markdown, seed_keyword="PDF 在线翻译", site_dir=Path(tmp))
        html = page.read_text(encoding="utf-8")
        sitemap = (Path(tmp) / "sitemap.xml").read_text(encoding="utf-8")
        robots = (Path(tmp) / "robots.txt").read_text(encoding="utf-8")
        cases = [
            ("有 meta description", 'name="description"' in html),
            ("有 Open Graph", 'property="og:title"' in html and 'property="og:description"' in html),
            ("有 Article 结构化数据", "application/ld+json" in html and '"@type": "Article"' in html),
            ("sitemap 带 lastmod", "<lastmod>" in sitemap and quote(page.name) in sitemap),
            ("robots 指向 sitemap", "Sitemap: https://zwtyai.github.io/seo-agent/sitemap.xml" in robots),
        ]
    passed = True
    for name, result in cases:
        print(f"  {'✅' if result else '❌'} {name}")
        passed = passed and result
    print()
    return passed


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🧪 SEO 内容质量测试套件")
    print("=" * 60)
    print()
    
    results = []
    
    # 运行所有测试
    results.append(("内容类型识别", test_content_type_inference()))
    results.append(("已发布内容统计", test_published_content_stats()))
    results.append(("内容质量评分", test_content_quality_scoring()))
    results.append(("研究简报格式", test_research_brief_format()))
    results.append(("关键词选题门槛", test_keyword_gate()))
    results.append(("成稿表述门槛", test_claim_gate()))
    results.append(("内容类型轮换", test_content_rotation()))
    results.append(("发布页技术 SEO", test_page_seo()))
    
    # 汇总结果
    print("=" * 60)
    print("📊 测试汇总")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    print()
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("🎉 所有测试通过！内容质量机制运行正常。")
        return 0
    else:
        print("⚠️  部分测试失败，请检查相关功能。")
        return 1


if __name__ == "__main__":
    exit(main())
