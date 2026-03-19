# user-chat-analyst-skill

> **一个开箱即用的 AgentSkill** — 上传 AI 智能体的用户对话日志（CSV），自动完成场景分类、用户画像、高频用户任务分析、卡点识别，输出可直接汇报的完整 Markdown 报告。

---

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🧹 数据清洗 | 自动过滤心跳消息、空白内容、噪音数据 |
| 🏷️ 场景二级分类 | 22条优先级规则，覆盖内容创作/金融分析/代码开发/产品配置等场景 |
| 👥 用户画像 | 自动划分 5-8 个用户群体，含代表用户、典型提问、痛点诉求 |
| 📊 T20分析 | 高频用户逐一分析核心任务、复杂度、主要卡点 |
| 🚨 卡点检测 | 自动识别文件下载断链、安装失败、推送失效等共性问题 |
| ⚠️ 安全风险 | 独立标出提示词注入/越权尝试行为 |
| 📝 报告生成 | 输出结构化 Markdown 报告，包含执行摘要、数据总览、建议（P0/P1/P2） |

---

## 📁 项目结构

```
user-chat-analyst-skill/
├── SKILL.md                          # AgentSkill 主文件（触发描述 + 使用流程）
├── chat-log-analyst.skill            # 打包好的 .skill 文件（可直接安装）
├── scripts/
│   ├── analyze.py                    # Step 1：数据加载与基础统计
│   ├── classify.py                   # Step 2：场景二级分类
│   └── generate_report.py            # Step 3-6：画像 + T20 + 卡点 + 报告生成
└── references/
    └── classification_rules.md       # 分类规则速查表 + 卡点信号说明
```

---

## 🚀 快速开始

### 方式一：作为 AgentSkill 安装（推荐）

将 `chat-log-analyst.skill` 安装到你的 OpenClaw/智能体平台，之后直接对话：

> "帮我分析这份用户对话日志 input.csv，输出场景分析报告"

### 方式二：直接运行脚本

**环境要求：** Python 3.8+，无需额外依赖

```bash
# Step 1：基础统计
python3 scripts/analyze.py your_data.csv --out-dir ./output

# Step 2：场景分类
python3 scripts/classify.py your_data.csv --out-dir ./output

# Step 3：生成报告
python3 scripts/generate_report.py your_data.csv ./output ./output/report.md
```

---

## 📋 输入数据格式

标准 CSV，包含以下字段（列顺序不限，允许有额外列）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `uid` | string | 用户唯一标识 |
| `content` | string | 用户提问内容 |
| `session_id` | string | 会话 ID（同一 session = 一次连续对话） |
| `created_at` | string | 时间戳，格式 `YYYY-MM-DD HH:MM:SS` |

---

## 🔧 自定义配置

### 修改分类关键词

编辑 `scripts/classify.py` 顶部的 `CATEGORY_RULES`：

```python
CATEGORY_RULES = [
    (("数据分析", "金融行情分析"),
     ["股票", "行情", "基金", "etf"]),

    # 新增你的业务场景：
    (("医疗咨询", "症状问诊"),
     ["诊断", "用药", "症状", "医院"]),
]
```

### 修改卡点检测规则

编辑 `scripts/generate_report.py` 的 `PAIN_POINT_RULES`：

```python
PAIN_POINT_RULES = [
    {
        "type":    "🔴 文件下载断链",
        "kws":     ["下载链接", "发邮箱", "打包下载"],
        "desc":    "...",
        "suggest": "...",
    },
    # 添加新卡点...
]
```

### 新增用户画像

编辑 `scripts/generate_report.py` 的 `PERSONA_RULES`：

```python
PERSONA_RULES = [
    ("医疗用户",
     lambda uid, cnt, cats, txt:
         sum(1 for m in txt.split("|||")
             if any(k in m for k in ["诊断", "用药"])) >= 3),
]
```

---

## 📊 报告章节说明

| 章节 | 内容 |
|------|------|
| 执行摘要 | ≤5条核心结论，每条带数据 |
| 核心数据总览 | 提问量、用户数、会话数、活跃度分层 |
| 场景分类分析 | 二级分类统计 + Top10 真实提问原文 |
| 用户行为与画像 | 5-8个用户群体，含代表uid、典型提问、痛点 |
| T20高频用户分析 | 逐用户：提问数/会话数/消息预览 |
| 问题与卡点 | 类型/描述/影响用户数/优化建议 |
| 结论与优化建议 | P0/P1/P2 优先级排列 |

---

## 📄 License

MIT License — 自由使用、修改、分发。
