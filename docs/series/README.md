# 系列栏目（Pages 可访问，官网反代请排除）

GitHub Pages 源是仓库的 `/docs`，所以系列页必须写在这里，公网才打得开：

- 本地：`docs/series/coldfact/`
- 公网：`https://zwtyai.github.io/seo-agent/series/coldfact/`

`docs/` 里其它内容（例如根下的产品文）以后可能整段代理进 yibelin 官网。  
反代时请**不要**带上 `/series/`，冷知识只留在 GitHub Pages，不进官网。

生成：

```bash
python main.py --product coldfact --step all
```

会同时产出：

- 站内卡片：`docs/series/coldfact/posts/*.html`
- 小红书文案（不自动发帖）：同目录 `*.xhs.md` / `*.xhs.txt`

只生成小红书文案：

```bash
python main.py --product coldfact --step xhs
```
