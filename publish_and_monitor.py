import os
import datetime
import requests
from requests.auth import HTTPBasicAuth
from google.oauth2 import service_account
from googleapiclient.discovery import build

# =====================================================================
# 1. 动态加载 GitHub Secrets 环境变量（确保明文密码不泄露）
# =====================================================================
WP_USER = os.environ.get("WP_USER", "your_wordpress_username")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
WP_URL = os.environ.get("WP_URL", "https://yibelin.com")
GSC_SITE_URL = os.environ.get("GSC_SITE_URL", "sc-domain:yibelin.com")


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
def fetch_gsc_performance_report():
    """动态计算日期，调用谷歌 GSC API 自动拉取过去 7 天的 SEO 表现报表"""
    # 动态从 GitHub 环境变量读取谷歌服务账号的 JSON 字符串内容
    gsc_json_string = os.environ.get("GOOGLE_GSC_KEY_JSON")

    if not gsc_json_string:
        print("⚠️ 未配置 GOOGLE_GSC_KEY_JSON 环境变量，跳过 GSC 数据监控。")
        return

    try:
        # 将环境变量中的 JSON 字符串动态解析为谷歌凭证
        import json
        info = json.loads(gsc_json_string)
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=['https://googleapis.com']
        )

        # 构建谷歌站长工具服务
        service = build('webmasters', 'v3', credentials=credentials)

        # 动态计算日期（谷歌数据通常有 2-3 天延迟，拉取过去 7 天）
        today = datetime.date.today()
        end_date = (today - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
        start_date = (today - datetime.timedelta(days=9)).strftime("%Y-%m-%d")

        request_body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["query"],  # 按照用户搜索的“关键词”聚合数据
            "rowLimit": 10  # 仅看曝光前 10 名的核心长尾词
        }

        response = service.searchanalytics().query(siteUrl=GSC_SITE_URL, body=request_body).execute()

        print(f"\n📊 ==== 译比邻 GSC 数据监控报表 ({start_date} 至 {end_date}) ====")
        if 'rows' in response:
            for row in response['rows']:
                keyword = row['keys'][0]
                clicks = row['clicks']
                impressions = row['impressions']
                position = round(row['position'], 1)
                print(
                    f"🔍 关键词: [{keyword}] | 曝光量: {impressions} | 点击量: {clicks} | 谷歌平均排名: 第 {position} 名")
        else:
            print("查无数据，新站或新长尾词请静候谷歌蜘蛛抓取并建立索引。")

    except Exception as e:
        print(f"❌ 拉取 GSC 报表失败，错误原因: {str(e)}")


if __name__ == "__main__":
    # 本地或线上单独测试时运行
    fetch_gsc_performance_report()
