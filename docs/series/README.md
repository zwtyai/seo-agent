# 系列栏目（Pages 可访问，官网反代请排除）

GitHub Pages 源是仓库的 `/docs`，所以系列页必须写在这里，公网才打得开：

- 本地：`docs/series/coldfact/`
- 公网：`https://zwtyai.github.io/seo-agent/series/coldfact/`

`docs/` 里其它内容（例如根下的产品文）以后可能整段代理进 yibelin 官网。  
反代时请**不要**带上 `/series/`，冷知识只留在 GitHub Pages，不进官网。

当前栏目定位：**每日冷知识 = 纠正日常生活里的小误判**  
（厨房、清洁洗衣、睡眠疲劳、家用小物；人体常见误解只作配菜。不做疗效、投资、心理鸡汤、思想实验。）

## 按天布局

每天（北京时间）一次跑 **3** 条，落在同一天目录下：

```text
docs/series/coldfact/
  index.html
  assets/
  2026-10-30/
    01-….html  01-….md  01-….xhs.md  01-….xhs.txt
    02-….html  …
    03-….html  …
  2026-10-31/
    01-….html  …
    02-….html  …
    03-….html  …
  posts/          # 旧篇，首页「往期」仍可读
```

公网对应：`…/series/coldfact/2026-10-31/01-….html`  
期号仍全局递增（第 007、008…），只是文件按天分组。

来源 URL 必须最终 **HTTP 200**（跟随跳转后），不能用 grounding 跳转链或验证码页。

## 生成

```bash
python main.py --product coldfact --step all
```

定时：`.github/workflows/coldfact_series.yml`（UTC 00:00 ≈ 北京 08:00）。

只生成小红书文案（不发帖）：

```bash
python main.py --product coldfact --step xhs
```
