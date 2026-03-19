#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 3-6: 用户画像 + T20分析 + 卡点识别 + 报告生成
用法: python3 generate_report.py <csv_path> <out_dir> <report_path>
依赖: 先运行 analyze.py 和 classify.py 生成中间文件
"""
import csv, json, re, sys, os
from collections import Counter, defaultdict
from datetime import datetime

csv.field_size_limit(10 * 1024 * 1024)
HEARTBEAT_RE = re.compile(r'^(HEARTBEAT|heartbeat|ping|pong)\b', re.I)


def is_noise(c):
    c = c.strip()
    return not c or len(c) <= 2 or bool(HEARTBEAT_RE.match(c))


# ──────────────────────────────────────────────────────────────
# 用户画像规则（可按业务场景自定义）
# ──────────────────────────────────────────────────────────────
PERSONA_RULES = [
    # (画像名称, 判断函数)
    # 判断函数签名: (uid, uid_counts, uid_l1_cats, all_msgs_text) -> bool
    ("长篇创作者",
     lambda uid, cnt, cats, txt:
         sum(1 for m in txt.split("|||") if any(k in m for k in ["章节", "续写", "继续写第"])) >= 5),

    ("金融分析用户",
     lambda uid, cnt, cats, txt:
         sum(1 for m in txt.split("|||") if any(k in m for k in ["股票", "行情", "黄金", "日报"])) >= 5),

    ("产品配置探索用户",
     lambda uid, cnt, cats, txt:
         cats.get("产品配置与安装", 0) >= 4 and
         any(k in txt for k in ["消息渠道", "推送", "渠道接入", "机器人配置",
                                 "飞书", "企业微信", "钉钉", "telegram"])),

    ("软件安装调试用户",
     lambda uid, cnt, cats, txt:
         cats.get("产品配置与安装", 0) >= 4 and
         any(k in txt for k in ["安装", "安装失败", "命令不存在", "路径", "配置"])),

    ("开发者用户",
     lambda uid, cnt, cats, txt:
         cats.get("代码开发", 0) >= 4),

    ("文档/内容生产用户",
     lambda uid, cnt, cats, txt:
         cats.get("文档处理与学术", 0) + cats.get("文件与多媒体", 0) >= 5),

    ("内容创作用户",
     lambda uid, cnt, cats, txt:
         cats.get("内容创作", 0) >= 4),

    ("AI功能探索用户",
     lambda uid, cnt, cats, txt:
         cats.get("AI能力探索", 0) >= 3),

    ("信息研究用户",
     lambda uid, cnt, cats, txt:
         cats.get("信息检索与研究", 0) >= 3),
]

PERSONA_L1_MAP = {
    "内容创作":       "内容创作用户",
    "数据分析":       "金融分析用户",
    "产品配置与安装": "产品配置探索用户",
    "代码开发":       "开发者用户",
    "文档处理与学术": "文档/内容生产用户",
    "文件与多媒体":   "文档/内容生产用户",
    "AI能力探索":     "AI功能探索用户",
    "信息检索与研究": "信息研究用户",
}


# ──────────────────────────────────────────────────────────────
# 卡点检测规则（通用，可按业务场景扩展）
# ──────────────────────────────────────────────────────────────
PAIN_POINT_RULES = [
    {
        "type":    "🔴 文件下载/交付断链",
        "desc":    "生成文件后无法提供可靠下载链接，或文件发送失败；用户反复追问获取入口",
        "kws":     ["下载链接", "给我链接", "发给我", "发送到邮箱", "发邮箱", "打包下载", "下载地址"],
        "suggest": "建立统一文件交付面板，生成后自动展示可点击链接；发送失败时给出明确错误提示",
    },
    {
        "type":    "🔴 安装/环境配置失败",
        "desc":    "软件安装或运行环境配置时遭遇系统级报错，新用户难以独立完成",
        "kws":     ["安装失败", "命令不存在", "无法识别", "路径错误", "权限被拒", "无法运行"],
        "suggest": "提供一键安装脚本或图形化向导，自动检测并修复常见环境问题",
    },
    {
        "type":    "🔴 消息推送失效",
        "desc":    "渠道推送配置成功后次日失效，或消息格式异常；用户无法得知失败原因",
        "kws":     ["没有收到", "没收到", "不行了", "推送失败", "未连接", "连接失败"],
        "suggest": "提升定时任务持久化稳定性；推送失败时自动重试并通知用户",
    },
    {
        "type":    "🟡 任务完成无主动通知",
        "desc":    "长任务/子任务完成后不主动告知用户，用户只能反复追问进度",
        "kws":     ["完成了吗", "做完了吗", "是否完成", "好了吗", "进展如何", "怎么还没"],
        "suggest": "任务完成/失败/中断时主动推送通知到当前会话",
    },
    {
        "type":    "🟡 长任务中断",
        "desc":    "复杂任务因上下文超限或中间步骤失败而中断，无法自动续接",
        "kws":     ["你还在吗", "怎么停了", "继续", "任务中断", "没有完成"],
        "suggest": "支持任务断点保存与续接；超长任务自动拆分为子任务分段执行",
    },
    {
        "type":    "⚠️ 安全风险（提示词注入）",
        "desc":    "疑似通过角色扮演或特殊指令绕过系统限制",
        "kws":     ["系统提示", "system prompt", "忽略之前", "没有任何限制", "jailbreak"],
        "suggest": "建立注入检测规则，对高频越权尝试用户进行标记和审计",
    },
]


def assign_persona(uid, uid_counts, uid_l1, valid_rows):
    cats = uid_l1.get(uid, {})
    msgs = [r["content"] for r in valid_rows if r["uid"] == uid]
    txt  = "|||".join(msgs)
    cnt  = uid_counts[uid]

    for name, rule in PERSONA_RULES:
        try:
            if rule(uid, cnt, cats, txt):
                return name
        except Exception:
            pass

    # 兜底：按主导分类
    filtered = {k: v for k, v in cats.items()
                if k not in ["其他/跟进回复", "其他"]}
    if not filtered:
        return "通用用户"
    top = max(filtered, key=filtered.get)
    return PERSONA_L1_MAP.get(top, "通用用户")


def detect_pain_points(valid_rows):
    results = []
    for rule in PAIN_POINT_RULES:
        kws     = rule["kws"]
        hit_rows = [r for r in valid_rows
                    if any(k.lower() in r["content"].lower() for k in kws)]
        hit_uids = set(r["uid"] for r in hit_rows)
        if hit_rows:
            results.append({
                "type":    rule["type"],
                "desc":    rule["desc"],
                "n_uids":  len(hit_uids),
                "n_msgs":  len(hit_rows),
                "suggest": rule["suggest"],
            })
    return results


def build_report(summary, classif, uid_persona, persona_counter,
                 pain_points, valid_rows, report_date):
    total   = summary["total_msgs"]
    n_users = summary["total_users"]
    n_sess  = summary["total_sessions"]
    avg     = summary["avg_per_user"]
    dist    = summary["uid_distribution"]
    top20   = summary["top20"]

    lines = []
    A = lines.append

    # 标题
    A(f"# 智能体用户场景分析报告")
    A(f"")
    A(f"**数据日期：** {report_date}  ")
    A(f"**报告生成：** {datetime.now().strftime('%Y-%m-%d')}  ")
    A(f"")
    A("---")
    A("")

    # 1. 执行摘要
    A("## 一、执行摘要")
    A("")
    scene_totals = sorted(
        [(l1, d["total"]) for l1, d in classif.items()
         if l1 not in ["其他/跟进回复", "其他"]],
        key=lambda x: -x[1]
    )
    top1 = scene_totals[0] if scene_totals else ("N/A", 0)
    top2 = scene_totals[1] if len(scene_totals) > 1 else ("N/A", 0)
    churn_cnt = dist.get("1次", 0)
    churn_pct = round(100 * churn_cnt / n_users, 1) if n_users else 0
    sec_total = classif.get("安全风险", {}).get("total", 0)

    A(f"1. **用户规模**：单日有效提问 **{total:,} 条**，独立用户 **{n_users:,} 人**，"
      f"人均提问 **{avg} 次**。")
    A(f"2. **最大需求场景**：{top1[0]}（{top1[1]} 条），其次为 {top2[0]}（{top2[1]} 条）。")
    A(f"3. **最大操作卡点**：文件/结果交付链路存在系统性障碍，"
      f"用户反复追问下载链接或文件发送入口。")
    A(f"4. **新用户流失**：{churn_cnt} 人（{churn_pct}%）仅提问1次，"
      f"安装/配置卡点是主要流失原因。")
    if sec_total:
        A(f"5. **安全风险**：检测到 **{sec_total} 条**提示词注入/越权尝试，需重点关注。")
    A("")
    A("---")
    A("")

    # 2. 数据总览
    A("## 二、核心数据总览")
    A("")
    A("| 指标 | 数值 |")
    A("|------|------|")
    A(f"| 有效提问总量 | **{total:,} 条** |")
    A(f"| 独立用户数 | **{n_users:,} 人** |")
    A(f"| 总会话数 | **{n_sess:,} 个** |")
    A(f"| 人均提问次数 | **{avg} 次** |")
    top20_sum = sum(u["count"] for u in top20)
    A(f"| Top20用户提问占比 | **{round(100*top20_sum/total,1)}%** |")
    A("")
    A("**每日统计**")
    A("")
    A("| 日期 | 提问量 | 活跃用户 | 人均提问 |")
    A("|------|--------|---------|---------|")
    for day, d in summary["daily"].items():
        m, u = d["msgs"], d["users"]
        A(f"| {day} | {m} | {u} | {round(m/u,2) if u else 0} |")
    A("")
    A("**用户活跃度分层**")
    A("")
    A("| 层级 | 用户数 | 占比 |")
    A("|------|--------|------|")
    for lbl, cnt in dist.items():
        A(f"| {lbl} | {cnt} | {round(100*cnt/n_users,1)}% |")
    A("")
    A("---")
    A("")

    # 3. 场景分类
    A("## 三、场景分类分析")
    A("")
    A("| 一级分类 | 提问量 | 占比 |")
    A("|---------|--------|------|")
    for l1, data in sorted(classif.items(), key=lambda x: -x[1]["total"]):
        A(f"| {l1} | {data['total']} | {round(100*data['total']/total,1)}% |")
    A("")

    for l1, data in sorted(classif.items(), key=lambda x: -x[1]["total"]):
        if l1 in ["其他/跟进回复", "其他"]:
            continue
        pct = round(100*data["total"]/total, 1)
        A(f"### {l1}（{data['total']} 条，{pct}%）")
        A("")
        A("| 二级场景 | 数量 | 占比 |")
        A("|---------|------|------|")
        for l2, sub in sorted(data["sub"].items(), key=lambda x: -x[1]["count"]):
            A(f"| {l2} | {sub['count']} | {round(100*sub['count']/total,1)}% |")
        A("")
        A("**Top10 典型真实提问：**")
        A("")
        all_exs, seen, count = [], set(), 0
        for sub in data["sub"].values():
            all_exs.extend(sub["examples"])
        for ex in all_exs:
            ex_clean = ex[:200].strip()
            if ex_clean not in seen and count < 10:
                seen.add(ex_clean)
                A(f'{count+1}. "{ex_clean}"')
                count += 1
        A("")

    A("---")
    A("")

    # 4. 用户画像
    A("## 四、用户行为与画像")
    A("")
    A("| 画像 | 用户数 | 占比 |")
    A("|------|--------|------|")
    for persona, cnt in sorted(persona_counter.items(), key=lambda x: -x[1]):
        A(f"| {persona} | {cnt} | {round(100*cnt/n_users,1)}% |")
    A("")

    persona_uids = defaultdict(list)
    for uid, p in uid_persona.items():
        persona_uids[p].append(uid)
    uid_counts_local = Counter(r["uid"] for r in valid_rows)

    for persona in sorted(persona_uids, key=lambda p: -persona_counter.get(p, 0)):
        uids     = persona_uids[persona]
        top_uids = sorted(uids, key=lambda u: -uid_counts_local[u])[:3]
        cnt      = persona_counter.get(persona, 0)
        A(f"### {persona}（{cnt} 人，{round(100*cnt/n_users,1)}%）")
        A("")
        A(f"**代表 uid：** {', '.join(top_uids)}")
        A("")
        A("**典型提问（5条）：**")
        A("")
        shown, count = set(), 0
        for uid in top_uids:
            for r in valid_rows:
                if r["uid"] == uid and count < 5:
                    ex = r["content"][:150].strip()
                    if ex not in shown:
                        shown.add(ex)
                        A(f'{count+1}. "{ex}"')
                        count += 1
        A("")

    A("---")
    A("")

    # 5. T20
    A("## 五、T20 高频用户核心任务分析")
    A("")
    A("| # | uid | 提问 | 会话 | 消息预览（前3条） |")
    A("|---|-----|------|------|-----------------|")
    for i, u in enumerate(top20, 1):
        preview = " ／ ".join(m[:50] for m in u["messages"][:3])
        A(f"| {i} | `{u['uid']}` | {u['count']} | {u['sessions']} | {preview} |")
    A("")
    A("> **说明：** 核心任务描述、复杂度评级、主要卡点需结合完整消息上下文人工补充。")
    A("> 读取 `contents_all.txt` 中对应 uid 的消息，理解用户最终目标而非单条字面意思。")
    A("")
    A("---")
    A("")

    # 6. 卡点
    A("## 六、发现的问题与卡点")
    A("")
    A("| 问题类型 | 描述 | 影响用户 | 提问量 | 建议 |")
    A("|---------|------|---------|--------|------|")
    for p in pain_points:
        A(f"| {p['type']} | {p['desc']} | ~{p['n_uids']}人 | {p['n_msgs']}条 | {p['suggest']} |")
    A("")
    A("---")
    A("")

    # 7. 建议
    A("## 七、结论与优化建议")
    A("")
    A("### P0（立即处理）")
    A("")
    for p in pain_points:
        if "🔴" in p["type"]:
            A(f"- **{p['type']}**：{p['suggest']}（影响约 {p['n_uids']} 人）")
    A("")
    A("### P1（1-2周内）")
    A("")
    for p in pain_points:
        if "🟡" in p["type"]:
            A(f"- **{p['type']}**：{p['suggest']}（影响约 {p['n_uids']} 人）")
    A("")
    A("### P2（中期规划）")
    A("")
    A("- **新用户 Onboarding 优化**：首次使用展示核心场景，引导完成第一个有价值任务")
    A("- **安全风险持续监控**：建立注入检测规则，高频越权用户标记审计")
    A("")
    A("---")
    A("")
    A(f"*有效提问：{total:,} 条 ｜ 用户：{n_users:,} 人 ｜ 数据日期：{report_date}*")

    return "\n".join(lines)


def run(csv_path, out_dir, report_path):
    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    valid = [r for r in rows if not is_noise(r.get("content", ""))]

    with open(os.path.join(out_dir, "analysis_summary.json"), encoding="utf-8") as f:
        summary = json.load(f)
    with open(os.path.join(out_dir, "classification_results.json"), encoding="utf-8") as f:
        classif = json.load(f)
    with open(os.path.join(out_dir, "uid_classification.json"), encoding="utf-8") as f:
        uid_l1 = json.load(f)

    uid_counts = Counter(r["uid"] for r in valid)
    uid_persona = {uid: assign_persona(uid, uid_counts, uid_l1, valid)
                   for uid in uid_counts}
    persona_counter = Counter(uid_persona.values())
    pain_points     = detect_pain_points(valid)

    dates = []
    for r in valid:
        try:
            dates.append(
                datetime.strptime(r["created_at"].strip(),
                                  "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
            )
        except Exception:
            pass
    report_date = max(dates) if dates else "unknown"

    md = build_report(summary, classif, uid_persona, persona_counter,
                      pain_points, valid, report_date)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\n✅ 报告已生成: {report_path}")


if __name__ == "__main__":
    csv_path    = sys.argv[1] if len(sys.argv) > 1 else "input.csv"
    out_dir     = sys.argv[2] if len(sys.argv) > 2 else "."
    report_path = sys.argv[3] if len(sys.argv) > 3 else f"report_{datetime.now().strftime('%Y%m%d')}.md"
    run(csv_path, out_dir, report_path)
