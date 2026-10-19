import os
import datetime
import httplib2
import requests
from requests.auth import HTTPBasicAuth
from google.oauth2 import service_account
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build

from vertex_llm import resolve_secret_text

# =====================================================================
# 1. 动态加载 GitHub Secrets 环境变量（确保明文密码不泄露）
# =====================================================================
WP_USER = os.environ.get("WP_USER", "your_wordpress_username")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
WP_URL = os.environ.get("WP_URL", "https://yibelin.com")
GSC_SITE_URL = os.environ.get("GSC_SITE_URL", "sc-domain:yibelin.com")
# google-api-python-client 默认 60 秒。连 Google 偏慢时放宽，只作用于这次 GSC 请求。
GSC_HTTP_TIMEOUT_SEC = 180


# =====================================================================
# 2. WordPress 自动化发布模块
# =====================================================================
def publish_to_wordpress(title: str, content_markdown: str, status: str = "publish"):
    """将 Agent 生成的成品文章自动通过 REST API 发布到 WordPress 网站"""
    if "your_wordpress_username" in WP_USER or "xxxx" in WP_APP_PASSWORD:
        print("⚠️ 未配置 WP 凭证，跳过发布阶段（本地测试环境）。")
        return None

    payload = {
        "title": title,
        "content": content_markdown,  # WordPress 块编辑器会自动解析 Markdown/HTML
        "status": status,  # 'publish' 为直接公开，'draft' 为存为后台草稿
    }

    try:
        response = requests.post(
            WP_URL,
            json=payload,
            auth=HTTPBasicAuth(WP_USER, WP_APP_PASSWORD),
            timeout=15
        )
        if response.status_code == 201:
            post_link = response.json().get('link')
            print(f"🎉 自动化发布成功！文章已线上公开: {post_link}")
            return post_link
        else:
            print(f"❌ WP 发布失败，状态码: {response.status_code}, 原因: {response.text}")
    except Exception as e:
        print(f"❌ 连接 WordPress 发生异常: {str(e)}")
    return None


# =====================================================================
# 3. Google Search Console (GSC) 数据监控模块
# =====================================================================
NO_GSC_NOTES = "没有 GSC 查询数据。继续写一个新的问题型长尾，不要等待，不要因此停。"


def format_gsc_notes(rows: list | None) -> str:
    """把 GSC 查询行收成挖词可用的短说明。没有行时明确要求继续写新词。"""
    if not rows:
        return NO_GSC_NOTES
    lines = ["近 7 天 Search Console 查询（按曝光）："]
    opportunities: list[str] = []
    for row in rows:
        keys = row.get("keys") or [""]
        query = str(keys[0])
        clicks = int(row.get("clicks") or 0)
        impressions = int(row.get("impressions") or 0)
        position = round(float(row.get("position") or 0), 1)
        ctr_pct = round(float(row.get("ctr") or 0) * 100, 1)
        lines.append(
            f"- {query} | 曝光 {impressions} | 点击 {clicks} | CTR {ctr_pct}% | 排名 {position}"
        )
        weak_click = impressions >= 1 and float(row.get("ctr") or 0) < 0.02
        mid_rank = 8 <= position <= 20
        if query and (weak_click or mid_rank):
            opportunities.append(query)
    if opportunities:
        lines.append(
            "可优先写的查询（有曝光但点击弱，或排名在 8–20）："
            + "、".join(opportunities)
        )
    else:
        lines.append("这些查询没有明显的低点击或 8–20 名机会。继续挖一个新的问题型长尾。")
    lines.append("无论有没有机会，都不要因为 GSC 停下来。")
    return "\n".join(lines)


def gsc_research_notes() -> str:
    """有凭证就拉近 7 天查询；没有、为空或失败时返回继续挖词的说明。"""
    gsc_json_string = (os.environ.get("GOOGLE_GSC_KEY_JSON") or "").strip()
    if not gsc_json_string:
        print("⚠️ 未配置 GOOGLE_GSC_KEY_JSON，挖词不等待 GSC。")
        return NO_GSC_NOTES

    try:
        import json
        info = json.loads(resolve_secret_text(gsc_json_string))
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        )
        http = AuthorizedHttp(
            credentials, http=httplib2.Http(timeout=GSC_HTTP_TIMEOUT_SEC)
        )
        service = build("webmasters", "v3", http=http)
        today = datetime.date.today()
        end_date = (today - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
        start_date = (today - datetime.timedelta(days=9)).strftime("%Y-%m-%d")
        print(f"正在拉取 GSC，单次请求最多等 {GSC_HTTP_TIMEOUT_SEC} 秒…")
        response = service.searchanalytics().query(
            siteUrl=GSC_SITE_URL,
            body={
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["query"],
                "rowLimit": 100,
            },
        ).execute()
        rows = response.get("rows") or []
        rows = sorted(rows, key=lambda row: row.get("impressions") or 0, reverse=True)[:10]
        notes = format_gsc_notes(rows)
        print(f"\n📊 GSC {start_date} 至 {end_date}\n{notes}")
        return notes
    except Exception as exc:
        detail = str(exc).replace("\n", " ")[:300]
        print(
            f"❌ 拉取 GSC 失败（单次最多等了 {GSC_HTTP_TIMEOUT_SEC} 秒），"
            f"原因: {type(exc).__name__}: {detail}。挖词继续，不等待。"
        )
        return NO_GSC_NOTES


def fetch_gsc_performance_report():
    """拉取过去 7 天的查询并打印。失败或未配置时不抛错。"""
    print(gsc_research_notes())


if __name__ == "__main__":
    # 本地或线上单独测试时运行
    fetch_gsc_performance_report()
