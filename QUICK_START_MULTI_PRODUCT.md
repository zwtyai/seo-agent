# 多产品SEO平台快速上手

## 🎯 5分钟理解核心概念

### 什么变了？

**之前（单产品）**:
```bash
python main.py  # 只能为yibelin生产内容
```

**现在（多产品）**:
```bash
python main.py --product yibelin   # 为译比邻生产
python main.py --product tranzify  # 为Tranzify生产
python main.py --product toolnav   # 为工具导航站生产
```

### 核心变化

| 原来 | 现在 | 说明 |
|------|------|------|
| 硬编码`SEED_KEYWORD = "PDF在线翻译"` | YAML配置 | 每个产品独立配置 |
| `product_knowledge_base_tool()` | 动态工具加载 | 支持产品KB或工具数据库 |
| 固定质量门槛 | 配置驱动门槛 | 导航站可跳过产品提及检查 |
| `docs/` 统一输出 | `outputs/<product>/docs/` | 多产品隔离 |

---

## 🚀 快速开始

### 步骤1: 添加新产品配置

复制模板：
```bash
cp configs/product_template.yaml configs/myproduct.yaml
```

编辑 `configs/myproduct.yaml`:
```yaml
product:
  id: "myproduct"
  name: "我的产品"
  domain: "https://myproduct.com"

keyword_strategy:
  seed_keywords:
    - "我的核心关键词"
  search_volume:
    min: 200
    max: 2000
  keyword_difficulty:
    max: 30

# ... 其他配置
```

### 步骤2: 创建知识库

```bash
mkdir -p knowledge_base/myproduct
```

创建 `knowledge_base/myproduct/capabilities.md`:
```markdown
# 我的产品能力

1. 功能A：描述...
2. 功能B：描述...
3. 限制：说明...
```

### 步骤3: 运行

```bash
python main.py --product myproduct --step all
```

生成的内容在: `outputs/myproduct/docs/`

---

## 📋 三个产品的配置示例

### 1. yibelin（原有产品）

**特点**: 问题型长尾词 + 产品在文末

```yaml
# configs/yibelin.yaml
product:
  id: "yibelin"
  name: "译比邻 PDF 在线翻译"
  domain: "https://yibelin.com"

keyword_strategy:
  seed_keywords:
    - "PDF 在线翻译"
  keyword_types:
    - "问题型"    # 如何/为什么/怎么
  
content_strategy:
  types:
    - name: "FAQ型"
      priority: 1
    - name: "教程指南型"
      priority: 2

quality_gates:
  claim_gate:
    max_product_mentions: 4  # 全文最多4次
```

**知识库结构**:
```
knowledge_base/yibelin/
├── capabilities.md    # 6条产品能力
└── limitations.md     # 限制说明
```

---

### 2. tranzify（新PDF翻译产品）

**特点**: 允许对比评测 + 可稍多提产品

```yaml
# configs/tranzify.yaml
product:
  id: "tranzify"
  name: "Tranzify - 智能PDF翻译"
  domain: "https://tranzify.cn"

keyword_strategy:
  seed_keywords:
    - "PDF翻译"
    - "论文翻译"
  keyword_types:
    - "问题型"
    - "工具推荐型"  # "最好的PDF翻译工具"

content_strategy:
  types:
    - name: "对比评测型"  # 优先对比
      priority: 1
    - name: "教程指南型"
      priority: 2

quality_gates:
  claim_gate:
    max_product_mentions: 5  # 新品牌可稍多
    
publishing:
  output_dir: "outputs/tranzify/docs/"
```

**知识库结构**:
```
knowledge_base/tranzify/
├── features.md           # 功能特性
└── vs_competitors.md     # 竞品对比（客观数据）
```

---

### 3. toolnav（工具导航站）

**特点**: 工具数据库 + 不推销产品 + 客观中立

```yaml
# configs/toolnav.yaml
product:
  id: "toolnav"
  name: "AI工具导航"
  domain: "https://toolnav.example.com"

keyword_strategy:
  seed_keywords:
    - "AI工具"
    - "效率工具"
  keyword_types:
    - "推荐型"    # "最好的XX工具"
    - "对比型"    # "XX vs YY"

content_strategy:
  types:
    - name: "对比评测型"
      priority: 1
    - name: "深度分析型"
      priority: 2
  
  product_mention:
    max_count: 0        # 导航站不推销产品
    position: "none"

quality_gates:
  keyword_gate:
    require_question_type: false  # 不要求问题型
  
  claim_gate:
    max_product_mentions: 0       # 不提自己

knowledge_base:
  source: "knowledge_base/toolnav/"
  main_file: "tools_database.json"  # JSON格式！
```

**知识库结构**:
```
knowledge_base/toolnav/
├── tools_database.json   # 工具数据库（核心）
├── categories.json       # 分类定义
└── update_log.md         # 更新日志
```

**tools_database.json 示例**:
```json
{
  "tools": [
    {
      "id": "chatgpt",
      "name": "ChatGPT",
      "category": "AI写作",
      "description": "OpenAI开发的对话式AI助手",
      "features": ["自然语言对话", "代码生成"],
      "pricing": "免费版 + $20/月 Plus",
      "url": "https://chat.openai.com",
      "pros": ["强大的理解能力", "支持中文"],
      "cons": ["免费版限流", "数据隐私担忧"]
    },
    {
      "id": "midjourney",
      "name": "Midjourney",
      "category": "图片生成",
      "description": "AI图片生成工具",
      "features": ["文本生成图片", "风格多样"],
      "pricing": "$10/月起",
      "url": "https://midjourney.com",
      "pros": ["画质高", "社区活跃"],
      "cons": ["需Discord", "排队时间长"]
    }
  ],
  "categories": ["AI写作", "图片生成", "PDF处理", "视频编辑"]
}
```

---

## 🔄 工作流对比

### yibelin（产品型）

```
研究员：挖掘"如何翻译扫描版PDF"
    ↓
作者：调用 product_knowledge_base_tool()
      → 获取译比邻6条能力
      → 正文写问题，文末提产品（≤4次）
    ↓
总编：检查"译比邻"次数、删夸大词
    ↓
发布：outputs/yibelin/docs/
```

### toolnav（导航站型）

```
研究员：挖掘"最好的AI写作工具推荐"
    ↓
作者：调用 tool_database_tool()
      → 查询 tools_database.json
      → 获取ChatGPT、Notion AI等信息
      → 客观对比功能、价格、适用场景
      → 不推销特定工具
    ↓
总编：检查中立性（不能有"最强""碾压"）
      → 跳过产品提及检查（max_count=0）
    ↓
发布：outputs/toolnav/docs/
```

---

## 🛠️ 常用命令

### 本地运行

```bash
# 完整流程
python main.py --product yibelin --step all

# 只跑关键词研究
python main.py --product tranzify --step keyword

# 只发布（假设前几步已完成）
python main.py --product toolnav --step publish
```

### 查看配置

```bash
# 校验配置文件
python -c "from core.config import ProductConfig; ProductConfig.load('yibelin')"

# 查看知识库
cat knowledge_base/yibelin/capabilities.md
cat knowledge_base/toolnav/tools_database.json
```

### 查看输出

```bash
# 查看生成的HTML
open outputs/yibelin/docs/index.html
open outputs/tranzify/docs/index.html
open outputs/toolnav/docs/index.html

# 查看sitemap
cat outputs/yibelin/docs/sitemap.xml
```

---

## 📊 目录结构一览

```
seo-agent/
├── configs/                    # 产品配置
│   ├── product_template.yaml  # 模板
│   ├── yibelin.yaml           # 译比邻
│   ├── tranzify.yaml          # Tranzify
│   └── toolnav.yaml           # 工具导航站
│
├── knowledge_base/             # 知识库
│   ├── yibelin/
│   │   ├── capabilities.md    # Markdown格式
│   │   └── limitations.md
│   ├── tranzify/
│   │   └── features.md
│   └── toolnav/
│       └── tools_database.json # JSON格式
│
├── outputs/                    # 输出（各产品隔离）
│   ├── yibelin/docs/
│   ├── tranzify/docs/
│   └── toolnav/docs/
│
├── core/                       # 核心代码（通用）
│   ├── config.py              # ProductConfig
│   ├── agents.py              # AgentFactory
│   ├── gates.py               # QualityGateSystem
│   ├── knowledge_base.py      # KnowledgeBaseLoader
│   └── publisher.py           # MultiPublisher
│
├── runs/                       # 运行中间文件
│   ├── yibelin/latest/
│   ├── tranzify/latest/
│   └── toolnav/latest/
│
├── main.py                     # 统一入口
├── requirements.txt
└── MULTI_PRODUCT_ARCHITECTURE.md  # 架构文档
```

---

## 🎯 关键差异点速查

| 特性 | yibelin | tranzify | toolnav |
|------|---------|----------|---------|
| **关键词类型** | 问题型 | 问题型+推荐型 | 推荐型+对比型 |
| **知识库格式** | Markdown | Markdown | JSON |
| **内容优先级** | FAQ > 教程 | 对比 > 教程 | 对比 > 深度 |
| **产品提及** | ≤4次 | ≤5次 | 0次 |
| **质量门槛** | 严格 | 中等 | 客观中立 |
| **工具类型** | product_kb | product_kb | tool_db |

---

## 🚨 常见问题

### Q1: 如何添加第4个产品？

**A**: 3步搞定
1. 复制 `configs/product_template.yaml` → `configs/newproduct.yaml`
2. 创建 `knowledge_base/newproduct/`
3. 运行 `python main.py --product newproduct`

### Q2: 工具数据库多久更新一次？

**A**: 建议策略
- 手动更新：每月review一次 `tools_database.json`
- 自动化（可选）：实现爬虫定期抓取Product Hunt

### Q3: 能否同时运行多个产品？

**A**: 可以
```bash
# 串行
python main.py --product yibelin && \
python main.py --product tranzify && \
python main.py --product toolnav

# 并行（需小心LLM配额）
python main.py --product yibelin &
python main.py --product tranzify &
wait
```

### Q4: GitHub Actions如何调度？

**A**: 轮换策略
```yaml
schedule:
  - cron: '0 2 * * 1,3,5'  # 周一三五: yibelin
  - cron: '0 2 * * 2,4'    # 周二四: tranzify
  - cron: '0 2 * * 6'      # 周六: toolnav
```

### Q5: 配置文件能否用JSON？

**A**: 可以，但推荐YAML
- YAML更易读、支持注释
- JSON更严格、易于校验
- 修改 `ProductConfig.load()` 即可支持JSON

---

## 📈 性能优化建议

### 1. 缓存知识库

```python
# core/knowledge_base.py
from functools import lru_cache

class KnowledgeBaseLoader:
    @lru_cache(maxsize=10)
    def load(self) -> dict:
        # 避免重复读取文件
        pass
```

### 2. 并行生成多产品

```bash
# parallel_run.sh
#!/bin/bash
python main.py --product yibelin --step all &
python main.py --product tranzify --step all &
wait
```

### 3. 增量更新工具数据库

```python
# 只更新变化的工具，不是每次全量
def update_tools_incremental():
    existing = load_tools_db()
    new_tools = fetch_from_product_hunt()
    merged = merge_with_dedup(existing, new_tools)
    save_tools_db(merged)
```

---

## 🎓 进阶用法

### 自定义内容类型

在配置中添加新类型：

```yaml
content_strategy:
  types:
    - name: "视频脚本型"
      priority: 1
      word_count: 500
      format: "script"
```

在 `AgentFactory._generate_writer_backstory()` 中添加对应逻辑。

### A/B测试标题

```yaml
seo:
  ab_testing:
    enabled: true
    variants: 3  # 生成3个标题变体
```

### 多语言支持

```yaml
product:
  id: "yibelin"
  locales:
    - "zh-CN"
    - "en-US"
```

---

## ✅ 检查清单

新产品上线前：

- [ ] 配置文件无语法错误（`yamllint configs/myproduct.yaml`）
- [ ] 知识库文件存在且内容完整
- [ ] 本地测试运行成功（`python main.py --product myproduct --step keyword`）
- [ ] 输出目录正确（`outputs/myproduct/docs/`）
- [ ] GitHub Actions配置已更新
- [ ] Secrets已添加（如需要）
- [ ] 文档已更新

---

## 🔗 相关文档

- [完整架构设计](MULTI_PRODUCT_ARCHITECTURE.md)
- [配置模板说明](configs/product_template.yaml)
- [原始README](README.md)

---

**下一步**: 选择一个产品，开始你的第一次运行吧！

```bash
# 推荐：先用yibelin测试（配置已完善）
python main.py --product yibelin --step keyword
```
