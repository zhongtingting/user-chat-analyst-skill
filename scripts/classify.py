#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 2: 场景二级分类
用法: python3 classify.py <csv_path> [--out-dir <dir>]
输出: classification_results.json, uid_classification.json

【自定义说明】
修改下方 CATEGORY_RULES 字典即可调整分类关键词，无需改动其他文件。
key = 二级场景名称，value = 触发关键词列表（中英文均支持）。
"""
import csv, json, re, sys, os
from collections import Counter, defaultdict

csv.field_size_limit(10 * 1024 * 1024)
HEARTBEAT_RE = re.compile(r'^(HEARTBEAT|heartbeat|ping|pong)\b', re.I)

# ──────────────────────────────────────────────────────────────
# 可自定义的分类关键词（按优先级排列，越靠前越优先）
# key = (一级分类, 二级分类), value = 关键词列表
# ──────────────────────────────────────────────────────────────
CATEGORY_RULES = [
    # 安全风险（最高优先级）
    (("安全风险", "提示词注入/越权尝试"),
     ["系统提示", "system prompt", "忽略之前", "没有任何限制", "无限制模式",
      "jailbreak", "越权", "提示词注入"]),

    # 内容创作
    (("内容创作", "长篇小说创作"),       ["续写", "章节", "继续写第", "第.*章"]),
    (("文件与多媒体", "音频生成发送"),    ["mp3", "tts", "朗读", "音频", "播客", "语音合成"]),
    (("内容创作", "PPT与演示文稿"),       ["ppt", "演示文稿", "幻灯片"]),
    (("文档处理与学术", "毕业论文辅助"),  ["毕业设计", "毕业论文", "开题报告", "sci投稿"]),
    (("内容创作", "报告与汇报材料"),      ["汇报", "述职", "工作报告", "日报", "周报", "月报"]),
    (("数据分析", "数据表格处理"),        ["excel", "报表", "资产负债", "数据表"]),
    (("内容创作", "翻译"),                ["翻译", "translate"]),
    (("内容创作", "营销文案创作"),        ["文案", "推广", "软文", "营销", "发布内容", "短视频脚本"]),

    # 数据分析
    (("数据分析", "金融行情分析"),
     ["股票", "行情", "基金", "etf", "期货", "财报", "社融", "信贷",
      "贵金属", "黄金", "原油", "大宗商品", "涨跌"]),

    # 信息检索
    (("信息检索与研究", "网络信息检索"),  ["检索", "搜索", "查询", "资讯", "新闻", "摘要采集"]),

    # 产品/工具配置（通用化，不绑定特定产品）
    (("产品配置与安装", "消息渠道接入"),
     ["telegram", "微信", "whatsapp", "discord", "飞书", "企业微信",
      "钉钉", "webhook", "消息推送", "渠道接入", "机器人配置"]),
    (("产品配置与安装", "插件/技能安装"),
     ["插件安装", "技能安装", "skill", "自主学习能力", "扩展安装"]),
    (("产品配置与安装", "软件安装与配置"),
     ["安装", "配置", "api key", "token配置", "环境配置",
      "无法识别", "命令不存在", "安装失败", "路径错误"]),
    (("产品配置与安装", "自动化与定时任务"),
     ["定时任务", "自动化", "cron", "工作流", "workflow", "定时发送", "定时推送"]),

    # 代码开发
    (("代码开发", "Web应用开发"),         ["网页", "前端", "html", "css", "浏览器页面"]),
    (("代码开发", "软件开发与调试"),
     ["代码", "编程", "开发", "报错", "调试", "接口", "java", "python",
      "javascript", "typescript", "docker", "数据库", "sql", "架构设计"]),

    # 文件操作
    (("文件与多媒体", "文件管理与下载"),
     ["下载链接", "发邮箱", "发送到邮箱", "打包下载", "压缩文件", "文件链接"]),

    # AI能力探索
    (("AI能力探索", "功能咨询与探索"),
     ["你是谁", "你能做什么", "有什么功能", "本地部署", "怎么使用",
      "和xxx区别", "与其他ai"]),
    (("AI能力探索", "角色定制与命名"),
     ["叫我", "起个名字", "你叫什么", "角色设定", "人设"]),

    # 学术教育
    (("文档处理与学术", "教育学术辅助"),
     ["学术论文", "知识产权", "培训课程", "教学设计", "学校作业"]),
]

# 简短跟进（兜底）
SHORT_THRESHOLD = 20


def is_noise(content):
    c = content.strip()
    return not c or len(c) <= 2 or bool(HEARTBEAT_RE.match(c))


def extract_text(content):
    """从 JSON 多媒体消息中提取文本部分"""
    if content.strip().startswith('[{"type"'):
        try:
            items = json.loads(content.strip())
            parts = [i.get("content", "") for i in items if i.get("type") == "text"]
            return " ".join(parts)
        except Exception:
            pass
    return content


def classify(content):
    """Returns (L1, L2)"""
    raw = content
    text = extract_text(content)
    c = text.lower()

    # JSON 多媒体：无文本时按附件类型判断
    if raw.strip().startswith('[{"type"'):
        if not text.strip():
            try:
                items = json.loads(raw.strip())
                for item in items:
                    url = item.get("content", "").lower()
                    if any(ext in url for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                        return ("文件与多媒体", "图片上传与分析")
                    if any(ext in url for ext in [".pdf", ".docx", ".doc", ".xlsx"]):
                        return ("文件与多媒体", "文档上传处理")
                    if any(ext in url for ext in [".mp3", ".wav", ".m4a"]):
                        return ("文件与多媒体", "音频生成发送")
            except Exception:
                pass
            return ("文件与多媒体", "附件/多媒体处理")

    # 按优先级规则匹配
    for (l1, l2), keywords in CATEGORY_RULES:
        for kw in keywords:
            if re.search(kw, c, re.IGNORECASE):
                return (l1, l2)

    # 小说创作（需要两个条件同时满足）
    if any(k in c for k in ["小说", "续写"]) and any(k in c for k in ["写作", "创作", "继续"]):
        return ("内容创作", "长篇小说创作")

    # 报告（宽泛匹配兜底）
    if any(k in c for k in ["报告", "方案", "总结"]):
        return ("内容创作", "报告与汇报材料")

    # 文档格式化
    if any(k in c for k in ["word", "pdf", "文档", "格式化", "整理文档"]):
        return ("文档处理与学术", "文档生成与格式化")

    # 短消息兜底
    if len(text.strip()) < SHORT_THRESHOLD:
        return ("其他/跟进回复", "简短跟进或确认")

    return ("其他", "未分类")


def run(csv_path, out_dir="."):
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    valid = [r for r in rows if not is_noise(r.get("content", ""))]

    classified = []
    for r in valid:
        l1, l2 = classify(r["content"])
        classified.append({**r, "l1": l1, "l2": l2})

    # 统计
    l1_groups = defaultdict(list)
    for r in classified:
        l1_groups[r["l1"]].append(r)

    results = {}
    total = len(classified)
    for l1, items in l1_groups.items():
        results[l1] = {"total": len(items), "sub": {}}
        l2c = Counter(r["l2"] for r in items)
        for l2, cnt in l2c.most_common():
            exs = [r["content"] for r in items if r["l2"] == l2][:10]
            results[l1]["sub"][l2] = {"count": cnt, "examples": exs}

    out1 = os.path.join(out_dir, "classification_results.json")
    with open(out1, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    uid_l1 = defaultdict(Counter)
    for r in classified:
        uid_l1[r["uid"]][r["l1"]] += 1
    out2 = os.path.join(out_dir, "uid_classification.json")
    with open(out2, "w", encoding="utf-8") as f:
        json.dump({u: dict(c) for u, c in uid_l1.items()},
                  f, ensure_ascii=False, indent=2)

    print(f"\n=== 分类结果 ===")
    for l1, data in sorted(results.items(), key=lambda x: -x[1]["total"]):
        pct = round(100 * data["total"] / total, 1)
        print(f"  {l1}: {data['total']}条 ({pct}%)")
    print(f"\n已保存: {out1}, {out2}")
    return results


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "input.csv"
    out_dir = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--out-dir" else "."
    run(csv_path, out_dir)
