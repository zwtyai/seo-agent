# 多产品架构迁移指南

## 🎉 架构改造已完成

原有的单产品SEO系统已成功改造为**多产品配置驱动架构**。

---

## 📊 改动总结

### 新增文件

```
core/
├── __init__.py              # 模块初始化
├── config.py                # ProductConfig 配置加载器
├── knowledge_base.py        # KnowledgeBaseLoader 知识库加载
├── gates.py                 # QualityGateSystem 质量门槛
├── agents.py                # AgentFactory Agent工厂
└── publisher.py             # MultiPublisher 多渠道发布

configs/
├── product_template.yaml    # 配置模板
├── yibelin.yaml            # 译比邻配置（从旧代码提取）
├── tranzify.yaml           # Tranzify配置（占位）
└── toolnav.yaml            # 工具导航站配置（占位）

knowledge_base/
├── yibelin/
│   └── capabilities.md     # 译比邻产品能力（从旧代码提取）
├── tranzify/
│   └── features.md         # 【占位】Tranzify特性
└── toolnav/
    └── tools_database.json # 【占位】工具数据库

main.py                      # 全新的多产品入口
main_legacy.py               # 备份的旧版本
```

### 保留文件（未改动）

```
vertex_llm.py               # Vertex AI配置（保持不变）
publish_and_monitor.py      # GSC/WordPress（保持不变）
static_publish.py           # 静态发布（保持不变）
keyword_gate.py             # 旧质量门槛（已迁移到core/gates.py，可删除）
claim_gate.py               # 旧质量门槛（已迁移到core/gates.py，可删除）
seo_solution.py             # SEO案例打捞（独立工具，保持不变）
```

---

## 🚀 使用新架构

### 1. 安装依赖

```bash
pip install -r requirements.txt  # 新增了 pyyaml>=6.0.0
```

### 2. 运行示例

```bash
# 查看可用产品
python main.py --list-products

# 为 yibelin 生产内容（完整流程）
python main.py --product yibelin --step all

# 只运行关键词研究
python main.py --product yibelin --step keyword

# 为 tranzify 生产（需先补充知识库）
python main.py --product tranzify --step all
```

### 3. 输出位置

```
outputs/
├── yibelin/docs/         # 译比邻的HTML输出
├── tranzify/docs/        # Tranzify的HTML输出
└── toolnav/docs/         # 工具导航站的HTML输出

runs/
├── yibelin/latest/       # 译比邻的中间文件
│   ├── 01-keyword.md
│   ├── 02-draft.md
│   └── 03-final.md
├── tranzify/latest/
└── toolnav/latest/
```

---

## 📝 补充产品知识库

### 方式一：编辑Markdown（产品型）

**适用**：yibelin, tranzify

编辑 `knowledge_base/<product>/capabilities.md` 或 `features.md`：

```markdown
# 产品能力说明

1. **功能A**：描述...
2. **功能B**：描述...
3. **限制**：说明...
```

### 方式二：编辑JSON（导航站型）

**适用**：toolnav

编辑 `knowledge_base/toolnav/tools_database.json`：

```json
{
  "tools": [
    {
      "id": "chatgpt",
      "name": "ChatGPT",
      "category": "AI写作",
      "description": "OpenAI的对话AI助手",
      "features": ["自然语言对话", "代码生成"],
      "pricing": "免费版 + $20/月",
      "url": "https://chat.openai.com",
      "pros": ["强大", "中文支持"],
      "cons": ["限流", "隐私担忧"]
    }
  ]
}
```

---

## 🔧 调整产品配置

编辑 `configs/<product>.yaml`：

```yaml
product:
  name: "我的产品"
  domain: "https://myproduct.com"

keyword_strategy:
  seed_keywords:
    - "核心关键词"
  search_volume:
    min: 200
    max: 2000

# ... 更多配置见 product_template.yaml
```

---

## 🆕 添加新产品

### 1. 复制配置模板

```bash
cp configs/product_template.yaml configs/newproduct.yaml
```

### 2. 编辑配置

```yaml
product:
  id: "newproduct"
  name: "新产品"
  # ... 其他配置
```

### 3. 创建知识库

```bash
mkdir -p knowledge_base/newproduct
# 创建 capabilities.md 或 tools_database.json
```

### 4. 运行

```bash
python main.py --product newproduct --step all
```

---

## ⚙️ GitHub Actions 更新（TODO）

需要修改 `.github/workflows/seo_factory.yml`：

```yaml
# 添加 product 输入参数
on:
  workflow_dispatch:
    inputs:
      product:
        description: '选择产品'
        required: true
        type: choice
        options:
          - yibelin
          - tranzify
          - toolnav

# 在运行时传入参数
- name: Run SEO Factory
  run: |
    python main.py --product ${{ github.event.inputs.product }} --step all
```

---

## 🔄 从旧版本迁移

### 旧版本运行方式

```bash
# 旧版（已废弃）
python main.py                 # 只能为yibelin生产
python main.py --step keyword  # 分步运行
```

### 新版本等价命令

```bash
# 新版
python main.py --product yibelin --step all
python main.py --product yibelin --step keyword
```

### 兼容性说明

- **环境变量**：完全兼容（GOOGLE_CREDENTIALS_ENC等）
- **输出格式**：兼容（仍然生成静态HTML）
- **质量门槛**：逻辑保持不变，只是迁移到配置驱动
- **Agent提示词**：动态生成，但核心逻辑与旧版一致

---

## 🐛 故障排查

### 问题1：配置文件不存在

```
❌ 配置文件不存在: configs/xxx.yaml
```

**解决**：
```bash
cp configs/product_template.yaml configs/xxx.yaml
# 然后编辑 configs/xxx.yaml
```

### 问题2：知识库加载失败

```
【XXX 知识库占位】请在 knowledge_base/xxx 创建知识库文件
```

**解决**：
```bash
mkdir -p knowledge_base/xxx
# 创建 capabilities.md 或 tools_database.json
```

### 问题3：模块导入错误

```
ModuleNotFoundError: No module named 'yaml'
```

**解决**：
```bash
pip install pyyaml>=6.0.0
```

---

## 📚 相关文档

- [快速上手指南](QUICK_START_MULTI_PRODUCT.md)
- [完整架构设计](MULTI_PRODUCT_ARCHITECTURE.md)
- [配置模板说明](configs/product_template.yaml)
- [原README](README.md)

---

## ✅ 验证改造是否成功

运行以下命令测试：

```bash
# 1. 列出产品
python main.py --list-products

# 2. 为yibelin运行关键词研究（应该成功）
python main.py --product yibelin --step keyword

# 3. 查看生成的简报
cat runs/yibelin/latest/01-keyword.md
```

如果以上命令都成功，说明架构改造完成！

---

## 🎯 下一步

1. **补充知识库**：
   - 完善 `knowledge_base/yibelin/capabilities.md`（如有需要）
   - 创建 `knowledge_base/tranzify/features.md`
   - 创建 `knowledge_base/toolnav/tools_database.json`

2. **调整配置**：
   - 根据实际需求微调 `configs/tranzify.yaml`
   - 根据实际需求微调 `configs/toolnav.yaml`

3. **测试运行**：
   - 为每个产品运行一次完整流程
   - 检查输出质量

4. **更新CI/CD**：
   - 修改GitHub Actions支持多产品

---

**有问题？** 查看 [QUICK_START_MULTI_PRODUCT.md](QUICK_START_MULTI_PRODUCT.md) 的FAQ部分。
