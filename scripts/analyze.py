#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 1: 数据加载、清洗、基础统计
用法: python3 analyze.py <csv_path> [--out-dir <dir>]
输出: analysis_summary.json, contents_all.txt
"""
import csv, json, re, sys, os
from collections import Counter, defaultdict
from datetime import datetime

csv.field_size_limit(10 * 1024 * 1024)
HEARTBEAT_RE = re.compile(r'^(HEARTBEAT|heartbeat|ping|pong)\b', re.I)


def is_noise(content):
    c = content.strip()
    return not c or len(c) <= 2 or bool(HEARTBEAT_RE.match(c))


def run(csv_path, out_dir="."):
    os.makedirs(out_dir, exist_ok=True)

    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    valid = [r for r in rows if not is_noise(r.get("content", ""))]

    uids    = [r["uid"] for r in valid]
    uid_set = set(uids)
    sess    = set(r["session_id"] for r in valid)
    total   = len(valid)
    n_users = len(uid_set)

    # 每日统计
    daily_msgs  = Counter()
    daily_users = defaultdict(set)
    for r in valid:
        try:
            day = datetime.strptime(
                r["created_at"].strip(), "%Y-%m-%d %H:%M:%S"
            ).strftime("%Y-%m-%d")
        except Exception:
            day = "unknown"
        daily_msgs[day]  += 1
        daily_users[day].add(r["uid"])

    uid_counts = Counter(uids)

    brackets = [
        (1,  1,    "1次"),
        (2,  5,    "2-5次"),
        (6,  10,   "6-10次"),
        (11, 20,   "11-20次"),
        (21, 50,   "21-50次"),
        (51, 9999, ">50次"),
    ]
    dist = {
        lbl: sum(1 for v in uid_counts.values() if lo <= v <= hi)
        for lo, hi, lbl in brackets
    }

    top20 = uid_counts.most_common(20)
    top20_detail = []
    for uid, cnt in top20:
        user_msgs     = [r["content"] for r in valid if r["uid"] == uid]
        user_sessions = set(r["session_id"] for r in valid if r["uid"] == uid)
        top20_detail.append({
            "uid":      uid,
            "count":    cnt,
            "sessions": len(user_sessions),
            "messages": user_msgs[:60],
        })

    summary = {
        "raw_rows":       len(rows),
        "total_msgs":     total,
        "total_users":    n_users,
        "total_sessions": len(sess),
        "avg_per_user":   round(total / n_users, 2) if n_users else 0,
        "daily": {
            d: {"msgs": daily_msgs[d], "users": len(daily_users[d])}
            for d in sorted(daily_msgs)
        },
        "uid_distribution": dist,
        "top20": top20_detail,
    }

    out_json = os.path.join(out_dir, "analysis_summary.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    out_txt = os.path.join(out_dir, "contents_all.txt")
    with open(out_txt, "w", encoding="utf-8") as f:
        for i, r in enumerate(valid):
            f.write(
                f"[{i+1}] uid={r['uid']} "
                f"session={r['session_id'][:8]} | {r['content']}\n"
            )

    print(f"原始行数:  {len(rows)}")
    print(f"有效行数:  {total}")
    print(f"独立用户:  {n_users}")
    print(f"总会话数:  {len(sess)}")
    print(f"人均提问:  {summary['avg_per_user']}")
    print(f"活跃度分布: {dist}")
    print(f"\n已保存: {out_json}, {out_txt}")
    return summary


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "input.csv"
    out_dir  = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--out-dir" else "."
    run(csv_path, out_dir)
