"""成稿门槛：禁止夸大、贬低竞品和过度营销，正文以问题本身为主。"""

from __future__ import annotations

import re

MAX_PRODUCT_MENTIONS = 4

_HYPE = re.compile(
    r"终极|彻底(?:解决|告别|杜绝|终结|消除)|"
    r"完美(?:无瑕|解决|保留|还原)|前所未有|革命性|"
    r"数字炼金术|化腐朽为神奇|从根源上解决|从根本上解决|"
    r"无疑是|卓越|百分百|100%|精准还原|格式完美"
)
_DISPARAGE = re.compile(
    r"垃圾|一无是处|完全不行|远不如|一塌糊涂|智商税|"
    r"普通工具只|传统工具仅|传统工具都|其他工具都|竞品都|"
    r"大多数工具无法|与普通工具不同|与传统工具不同"
)
_MARKETING = re.compile(
    r"一站式|工作效率倍增|数字修复师|终结你的|终结排版|"
    r"开启您的|开启你的|体验真正|无忧|告别排版焦虑|"
    r"经过(?:我们的)?测试|实测|正如一位用户"
)


def validate_article_claims(markdown: str) -> tuple[bool, str]:
    text = markdown or ""
    problems: list[str] = []
    for label, pattern in (
        ("禁止夸大", _HYPE),
        ("禁止贬低竞品", _DISPARAGE),
        ("禁止过度营销", _MARKETING),
    ):
        found = list(dict.fromkeys(pattern.findall(text)))
        if found:
            problems.append(f"{label}：删掉这些说法：{'、'.join(found[:8])}")

    mentions = len(re.findall(r"译比邻", text))
    if mentions > MAX_PRODUCT_MENTIONS:
        problems.append(
            "尽量还原问题本身："
            f"译比邻出现了 {mentions} 次，全文最多 {MAX_PRODUCT_MENTIONS} 次。"
            "正文写问题为何发生、表现是什么，产品只在文末提一次。"
        )

    if not problems:
        return True, ""
    return False, (
        "成稿未通过，请改写：\n- "
        + "\n- ".join(problems)
        + "\n产品只复述知识库里的能力，并写明复杂版式仍需人工核对。"
        "不要给竞品打分，不要编测试和用户原话。"
    )
