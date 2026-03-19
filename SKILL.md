---
name: chat-log-analyst
description: 分析智能体/AI助手/聊天平台的用户对话日志（CSV格式），自动完成场景分类、用户画像、高频用户任务分析、卡点识别，输出可向领导汇报的完整 Markdown 分析报告。适用场景：用户提供含 uid/content/session_id/created_at 字段的对话导出文件，要求进行用户行为分析、场景分类、运营洞察、流程自动化识别等任务时触发。关键词触发：聊天日志分析、对话数据分析、用户行为分析、场景分类报告、智能体数据分析、chat log analysis、conversation analysis、用户提问分析。
---

# Chat Log Analyst

分析 AI 智能体用户对话日志，输出结构化汇报报告。

## 输入规范

标准 CSV 字段（允许列顺序不同，允许有额外列）：

| 字段 | 说明 |
|------|------|
| `uid` | 用户唯一标识 |
| `content` | 用户提问内容 |
| `session_id` | 会话 ID（同 session = 一次连续对话） |
| `created_at` | 时间戳，格式 `YYYY-MM-DD HH:MM:SS` |

> 文件可能含大字段（如 JSON 格式的多媒体消息），脚本已内置扩大 field_size_limit。

## 分析流程

### Step 1：数据加载与清洗

运行 `scripts/analyze.py <csv_path> [--out-dir <dir>]`，输出：
- `analysis_summary.json` — 基础统计
- `contents_all.txt` — 全量有效消息（编号+uid+内容）

**心跳/噪音过滤规则：**
- 匹配 `HEARTBEAT`、`ping`、`pong`（忽略大小写）
- 内容长度 ≤ 2
- 纯空白内容

### Step 2：场景分类

运行 `scripts/classify.py <csv_path> [--out-dir <dir>]`，输出：
- `classification_results.json` — 二级分类统计 + 示例
- `uid_classification.json` — 每个用户的分类分布

分类规则参见 `references/classification_rules.md`。

**核心设计原则：**
- 分类关键词面向**通用中文对话场景**，不绑定任何特定产品
- 按优先级顺序匹配，命中第一条即停止
- JSON 多媒体消息（以 `[{"type"` 开头）提取内嵌 text 字段再分类
- 安全风险类（提示词注入/越权）无论数量多少必须单独列出

### Step 3：报告生成

运行 `scripts/generate_report.py <csv_path> <out_dir> <report_path>`，依赖 Step 1+2 的输出。

报告包含以下章节：

1. **执行摘要** — ≤5条，每条带数据
2. **核心数据总览** — 基础统计表格 + 活跃度分层
3. **场景分类分析** — 二级分类 + Top10 真实提问原文 + 关键词
4. **用户行为与画像** — 5-8个用户群体，含代表uid、典型提问、痛点
5. **T20高频用户分析** — 逐用户：提问数/会话数/核心任务/复杂度/卡点
6. **问题与卡点** — 表格：类型/描述/影响用户数/建议
7. **结论与建议** — P0/P1/P2 优先级

## 关键词自定义

分类关键词存放在 `scripts/classify.py` 顶部的字典结构中，可按业务场景直接修改：

```python
CATEGORY_RULES = {
    "金融分析": ["股票", "行情", "基金", ...],
    "代码开发": ["代码", "报错", "接口", ...],
    # 新增场景：
    "医疗咨询": ["诊断", "用药", "症状", ...],
}
```

修改后无需改动其他文件，分类和报告自动更新。

## 输出

- 报告保存至 `<report_path>` 参数指定路径
- 若未指定，默认输出到当前目录 `report_<日期>.md`
- 同时在对话中展示执行摘要和核心数据总览

## 注意事项

- 引用用户原话时保持原文，不做意译
- 单日数据跳过日环比；多日数据自动输出每日趋势
- T20 核心任务需读前30条消息，识别用户**最终目标**而非单条字面意思
- 安全风险条目必须独立列出，不得归入"其他"
