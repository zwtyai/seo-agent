"""
把 Crew 产出的 Markdown 写成 docs/ 下的静态 HTML，供本地预览或 GitHub Pages。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

_REPO_ROOT = Path(__file__).resolve().parent
# GitHub Pages「从分支部署」只支持 / 或 /docs，故静态站落在 docs/
_DEFAULT_SITE_DIR = _REPO_ROOT / "docs"
SITE_ORIGIN = "https://zwtyai.github.io/seo-agent"

_TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_TAG_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_DAY_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def series_day_key(tz_name: str = "Asia/Shanghai") -> str:
    """按栏目时区得到当天目录名，例如 2026-10-31。"""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 - 非法时区名退回上海
        tz = ZoneInfo("Asia/Shanghai")
    return datetime.now(tz).date().isoformat()


def _iter_day_dirs(site_dir: Path) -> list[Path]:
    if not site_dir.is_dir():
        return []
    return sorted(
        (
            child
            for child in site_dir.iterdir()
            if child.is_dir() and _DAY_DIR_RE.match(child.name)
        ),
        reverse=True,
    )


def iter_published_files(
    site_dir: Path,
    *,
    suffix: str,
) -> Iterator[Path]:
    """
    已发布文件：优先按天目录 YYYY-MM-DD/，再兼容旧 posts/。
    新到旧：日期新的在前；同日内按文件名升序（01、02、03）。
    """
    for day_dir in _iter_day_dirs(site_dir):
        for path in sorted(day_dir.glob(f"*{suffix}")):
            if path.name.startswith("_"):
                continue
            yield path
    posts_dir = site_dir / "posts"
    if posts_dir.is_dir():
        for path in sorted(posts_dir.glob(f"*{suffix}"), reverse=True):
            if path.name.startswith("_"):
                continue
            yield path


def _result_to_markdown(result: Any) -> str:
    if result is None:
        return ""
    raw = getattr(result, "raw", None)
    if raw:
        return str(raw).strip()
    return str(result).strip()


def _slugify(text: str, max_len: int = 48) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-一-龥]+", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return (text or "post")[:max_len]


CONTENT_TYPES = (
    "FAQ型",
    "教程指南型",
    "对比评测型",
    "案例故事型",
    "深度分析型",
)


def least_used_content_type(
    published_types: list[str],
    order: tuple[str, ...] | list[str] | None = None,
) -> str:
    """下一篇用篇数最少的类型。篇数相同按 order 的顺序取，默认是 CONTENT_TYPES。"""
    names = tuple(order) if order else CONTENT_TYPES
    counts = {name: 0 for name in names}
    for name in published_types:
        if name in counts:
            counts[name] += 1
    return min(names, key=lambda name: (counts[name], list(names).index(name)))


def _infer_content_type(markdown: str) -> str:
    """从文章内容推断内容类型。"""
    md = markdown.lower()
    title = ""
    for line in markdown.splitlines():
        if line.strip().startswith("# "):
            title = line.strip()[2:].lower()
            break

    # FAQ 先认。长尾问句标题常含「如何 / 怎么」，不能因此把 FAQ 算成教程。
    if md.count("## q:") + md.count("## 问") >= 5:
        return "FAQ型"

    # 对比评测型
    if "|" in markdown and ("对比" in md or "vs" in md or "比较" in md):
        return "对比评测型"
    
    # 教程指南型
    if any(kw in title for kw in ["如何", "怎么", "步骤", "教程", "指南"]):
        return "教程指南型"
    if md.count("第一步") + md.count("第二步") + md.count("步骤") >= 3:
        return "教程指南型"
    
    # 案例故事型
    if any(kw in md for kw in ["故事", "案例", "经历", "博士", "研究生", "用户"]):
        if md.count("使用") + md.count("遇到") + md.count("解决") >= 5:
            return "案例故事型"
    
    # 默认深度分析型
    return "深度分析型"


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text).replace("&nbsp;", " ").strip()


def _clean_title_text(title: str) -> str:
    """去掉误写入标题的 Markdown 链接等，只保留可读文案。"""
    t = title.strip()
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = _strip_html(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return _clean_title_text(s[2:]) or fallback
    return fallback


def _title_from_html(html: str) -> Optional[str]:
    m = _TITLE_TAG_RE.search(html)
    if m:
        t = _clean_title_text(m.group(1))
        if t:
            return t
    m = _H1_TAG_RE.search(html)
    if m:
        t = _clean_title_text(m.group(1))
        if t:
            return t
    return None


def _normalize_title_key(title: str) -> str:
    """用于去重比较：去空白与常见标点。"""
    t = title.strip().lower()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[^\w一-龥]+", "", t, flags=re.UNICODE)
    return t


def list_published_titles(site_dir: Optional[Path] = None) -> list[str]:
    """读取已发布文章的内容标题（优先 HTML <title>/H1）。含按天目录与旧 posts/。"""
    site_dir = Path(site_dir) if site_dir else _DEFAULT_SITE_DIR
    titles: list[str] = []
    for p in iter_published_files(site_dir, suffix=".html"):
        try:
            html = p.read_text(encoding="utf-8")
        except OSError:
            continue
        title = _title_from_html(html) or p.stem
        titles.append(title)
    return titles


def list_published_content_types(site_dir: Optional[Path] = None) -> list[str]:
    """读取已发布文章的内容类型（从 Markdown 推断）。"""
    site_dir = Path(site_dir) if site_dir else _DEFAULT_SITE_DIR
    types: list[str] = []
    for p in iter_published_files(site_dir, suffix=".md"):
        if p.name.endswith(".xhs.md"):
            continue
        try:
            markdown = p.read_text(encoding="utf-8")
            content_type = _infer_content_type(markdown)
            types.append(content_type)
        except OSError:
            continue
    return types


def list_published_markdown(site_dir: Optional[Path] = None) -> list[str]:
    """读取已发布文章的 Markdown，供种子词轮换统计与系列去重。"""
    site_dir = Path(site_dir) if site_dir else _DEFAULT_SITE_DIR
    texts: list[str] = []
    for path in iter_published_files(site_dir, suffix=".md"):
        if path.name.endswith(".xhs.md"):
            continue
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return texts


def _ensure_unique_title(title: str, existing: list[str], *, hint: str = "") -> str:
    keys = {_normalize_title_key(t) for t in existing if t}
    key = _normalize_title_key(title)
    if key and key not in keys:
        return title

    hint_label = _slugify(hint, 16).replace("-", "") or "续篇"
    candidate = f"{title}（{hint_label}）"
    n = 2
    while _normalize_title_key(candidate) in keys:
        candidate = f"{title}（{n}）"
        n += 1
    return candidate


def _replace_markdown_h1(markdown: str, new_title: str) -> str:
    lines = markdown.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("# "):
            lines[i] = f"# {new_title}"
            return "\n".join(lines)
    return f"# {new_title}\n\n{markdown}"


def _markdown_to_html_body(markdown: str) -> str:
    try:
        import markdown as md

        return md.markdown(
            markdown,
            extensions=["extra", "sane_lists", "nl2br"],
        )
    except ImportError:
        # 无 markdown 包时的兜底：整块转义 + 换行
        return "<pre class=\"md-fallback\">" + escape(markdown) + "</pre>"


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


class SiteBrand:
    """静态页上的站点名、正式站地址和页面来源。不传时保持译比邻演示站。"""

    def __init__(
        self,
        origin: str = SITE_ORIGIN,
        name: str = "译比邻",
        url: str = "https://yibelin.com",
        blurb: str = "译比邻 PDF 在线翻译",
    ):
        self.origin = (origin or SITE_ORIGIN).rstrip("/")
        self.name = name or "译比邻"
        self.url = url or "https://yibelin.com"
        self.blurb = blurb or self.name


def _meta_description(markdown: str, fallback: str = "译比邻 PDF 在线翻译") -> str:
    text = re.sub(r"(?m)^#+\s*", "", markdown or "")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`>#|]", "", text)
    return _clip(text, 160) or fallback


def _post_url(
    filename: str,
    origin: str = SITE_ORIGIN,
    *,
    day: str | None = None,
) -> str:
    base = origin.rstrip("/")
    if day:
        return f"{base}/{day}/{quote(filename)}"
    return f"{base}/posts/{quote(filename)}"


def _lastmod_from_name(filename: str, path: Path) -> str:
    match = re.match(r"(\d{8})-", filename)
    if match:
        return datetime.strptime(match.group(1), "%Y%m%d").date().isoformat()
    if path.parent and _DAY_DIR_RE.match(path.parent.name):
        return path.parent.name
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()


def _json_ld(
    title: str,
    description: str,
    canonical: str,
    published: str,
    brand: SiteBrand,
) -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": _clip(title, 110),
        "description": description,
        "inLanguage": "zh-CN",
        "mainEntityOfPage": canonical,
        "datePublished": published,
        "author": {
            "@type": "Organization",
            "name": brand.name,
            "url": brand.url,
        },
    }
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")


def _page_shell(
    title: str,
    body_html: str,
    *,
    description: str,
    canonical: str,
    published: str,
    relative_css: str = "../assets/style.css",
    brand: SiteBrand | None = None,
) -> str:
    brand = brand or SiteBrand()
    safe_title = escape(_clip(title, 60))
    safe_description = escape(description)
    safe_canonical = escape(canonical)
    linked_data = _json_ld(title, description, canonical, published, brand)
    footer_name = escape(brand.name)
    footer_url = escape(brand.url)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <meta name="description" content="{safe_description}" />
  <link rel="canonical" href="{safe_canonical}" />
  <meta property="og:type" content="article" />
  <meta property="og:locale" content="zh_CN" />
  <meta property="og:title" content="{safe_title}" />
  <meta property="og:description" content="{safe_description}" />
  <meta property="og:url" content="{safe_canonical}" />
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content="{safe_title}" />
  <meta name="twitter:description" content="{safe_description}" />
  <script type="application/ld+json">{linked_data}</script>
  <link rel="stylesheet" href="{relative_css}" />
</head>
<body>
  <header class="site-header">
    <a href="../index.html">SEO Agent 静态站</a>
  </header>
  <main class="post">
    <article>
{body_html}
    </article>
  </main>
  <footer class="site-footer">
    <p>Generated by seo-agent · <a href="{footer_url}">{footer_name}</a></p>
  </footer>
</body>
</html>
"""


def _write_crawl_files(site_dir: Path, brand: SiteBrand | None = None) -> None:
    brand = brand or SiteBrand()
    urls = [
        "  <url>\n"
        f"    <loc>{escape(brand.origin + '/')}</loc>\n"
        "  </url>"
    ]
    for path in iter_published_files(site_dir, suffix=".html"):
        day = path.parent.name if _DAY_DIR_RE.match(path.parent.name) else None
        lastmod = _lastmod_from_name(path.name, path)
        loc = escape(_post_url(path.name, brand.origin, day=day))
        urls.append(
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            "  </url>"
        )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    (site_dir / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (site_dir / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n\n"
        f"Sitemap: {brand.origin}/sitemap.xml\n",
        encoding="utf-8",
    )


def _index_listing_html(site_dir: Path) -> str:
    """首页列表：按天分组；旧 posts/ 放在「往期」下。"""
    chunks: list[str] = []
    for day_dir in _iter_day_dirs(site_dir):
        day_items: list[str] = []
        for p in sorted(day_dir.glob("*.html")):
            if p.name.startswith("_"):
                continue
            try:
                html = p.read_text(encoding="utf-8")
            except OSError:
                html = ""
            label = _title_from_html(html) or p.stem
            day_items.append(
                f'        <li><a href="{escape(day_dir.name)}/{escape(p.name)}">'
                f"{escape(label)}</a></li>"
            )
        if day_items:
            chunks.append(f"      <h2>{escape(day_dir.name)}</h2>")
            chunks.append('      <ul class="post-list">')
            chunks.extend(day_items)
            chunks.append("      </ul>")

    posts_dir = site_dir / "posts"
    legacy: list[str] = []
    if posts_dir.is_dir():
        for p in sorted(posts_dir.glob("*.html"), reverse=True):
            if p.name.startswith("_"):
                continue
            try:
                html = p.read_text(encoding="utf-8")
            except OSError:
                html = ""
            label = _title_from_html(html) or p.stem
            legacy.append(
                f'        <li><a href="posts/{escape(p.name)}">{escape(label)}</a></li>'
            )
    if legacy:
        chunks.append("      <h2>往期</h2>")
        chunks.append('      <ul class="post-list">')
        chunks.extend(legacy)
        chunks.append("      </ul>")

    if not chunks:
        return '      <ul class="post-list">\n      <li>（暂无文章）</li>\n      </ul>'
    return "\n".join(chunks)


def _rebuild_index(site_dir: Path, brand: SiteBrand | None = None) -> Path:
    brand = brand or SiteBrand()
    listing = _index_listing_html(site_dir)
    index_url = escape(brand.origin + "/")
    index_title = escape(f"{brand.name} 文章")
    index_description = escape(f"{brand.blurb}相关文章列表")
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{index_title}</title>
  <meta name="description" content="{index_description}" />
  <link rel="canonical" href="{index_url}" />
  <meta property="og:title" content="{index_title}" />
  <meta property="og:description" content="{index_description}" />
  <meta property="og:url" content="{index_url}" />
  <link rel="stylesheet" href="assets/style.css" />
</head>
<body>
  <header class="site-header">
    <strong>{index_title}</strong>
  </header>
  <main class="index">
    <h1>文章列表</h1>
{listing}
  </main>
  <footer class="site-footer">
    <p>Generated by seo-agent</p>
  </footer>
</body>
</html>
"""
    index_path = site_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    _write_crawl_files(site_dir, brand)
    return index_path


def rebuild_index(site_dir: Optional[Path] = None) -> Path:
    site_dir = Path(site_dir) if site_dir else _DEFAULT_SITE_DIR
    return _rebuild_index(site_dir)


def publish_static_page(
    result: Any,
    *,
    seed_keyword: str = "post",
    site_dir: Optional[Path] = None,
    site_origin: str | None = None,
    brand_name: str | None = None,
    brand_url: str | None = None,
    brand_blurb: str | None = None,
    day: str | None = None,
    slot: int | None = None,
) -> Path:
    """
    将一次流水线结果写成静态 HTML，并刷新 index.html。

    - 默认（SEO）：site_dir/posts/<timestamp>-<slug>.html
    - 系列按天：site_dir/YYYY-MM-DD/01-<slug>.html（day + slot）
    """
    site_dir = Path(site_dir) if site_dir else _DEFAULT_SITE_DIR
    brand = SiteBrand(
        origin=site_origin or SITE_ORIGIN,
        name=brand_name or "译比邻",
        url=brand_url or "https://yibelin.com",
        blurb=brand_blurb or "译比邻 PDF 在线翻译",
    )
    if day:
        if not _DAY_DIR_RE.match(day):
            raise ValueError(f"day 必须是 YYYY-MM-DD，收到：{day!r}")
        posts_dir = site_dir / day
    else:
        posts_dir = site_dir / "posts"
    assets_dir = site_dir / "assets"
    posts_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    style_path = assets_dir / "style.css"
    if not style_path.exists():
        bundled = Path(__file__).resolve().parent / "docs" / "assets" / "style.css"
        if bundled.is_file():
            style_path.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")

    markdown = _result_to_markdown(result)
    existing = list_published_titles(site_dir)
    raw_title = _extract_title(markdown, fallback=seed_keyword)
    title = _ensure_unique_title(raw_title, existing, hint=seed_keyword)
    if title != raw_title:
        markdown = _replace_markdown_h1(markdown, title)

    body = _markdown_to_html_body(markdown)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    slug = _slugify(title) or _slugify(seed_keyword)
    if day and slot is not None:
        filename = f"{int(slot):02d}-{slug}.html"
        stem = f"{int(slot):02d}-{slug}"
    elif day:
        filename = f"{stamp}-{slug}.html"
        stem = f"{stamp}-{slug}"
    else:
        filename = f"{stamp}-{slug}.html"
        stem = f"{stamp}-{slug}"
    out_path = posts_dir / filename
    out_path.write_text(
        _page_shell(
            title,
            body,
            description=_meta_description(markdown, brand.blurb),
            canonical=_post_url(filename, brand.origin, day=day),
            published=now.isoformat(),
            brand=brand,
        ),
        encoding="utf-8",
    )

    # 同步保存原始 Markdown，方便 diff / 再加工
    md_path = posts_dir / f"{stem}.md"
    md_path.write_text(markdown + "\n", encoding="utf-8")

    _rebuild_index(site_dir, brand)
    return out_path


if __name__ == "__main__":
    path = rebuild_index()
    titles = list_published_titles()
    print(f"✅ 已重建索引: {path}")
    for t in titles:
        print(f"  - {t}")
