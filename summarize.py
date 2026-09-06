#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把反馈站的三份数据汇总成一份 Markdown 案情(给智能体或人读)。

    python3 summarize.py [--root DIR] [--batch ID ...] [--all]

默认只汇总清单最新批次(batches[0]);--all 汇总全部;--batch 指定一个或多个批次 id。
输出顺序:进度 → 未通过 → 未测试 → 通过但留了备注 → 新 Bug → 新需求。附件给的是相对 <root> 的路径。
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_NAME = {"pass": "通过", "fail": "未通过", "blocked": "未测试", None: "未勾选"}


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _lines(text, indent="  "):
    text = (text or "").strip()
    if not text:
        return []
    return [indent + line for line in text.splitlines()]


def _attachments(files, indent="  "):
    return [indent + "附件: data/" + path for path in (files or [])]


def _pick_batches(checklist, wanted, everything):
    batches = [b for b in checklist.get("batches", []) if isinstance(b, dict) and b.get("id")]
    if everything:
        return batches
    if wanted:
        by_id = {b["id"]: b for b in batches}
        missing = [w for w in wanted if w not in by_id]
        if missing:
            sys.stderr.write("[警告] 清单里没有这些批次: %s\n" % ", ".join(missing))
        return [by_id[w] for w in wanted if w in by_id]
    return batches[:1]


def _summarize_batch(batch, results, bugs, reqs, out):
    total = tested = 0
    buckets = {"fail": [], "blocked": [], "pass_noted": []}
    for section in batch.get("sections", []):
        for item in section.get("items", []):
            total += 1
            rec = results.get(item.get("id")) or {}
            status = rec.get("status")
            if status in ("pass", "fail"):
                tested += 1
            row = (section.get("title", ""), item, rec)
            if status == "fail":
                buckets["fail"].append(row)
            elif status == "blocked":
                buckets["blocked"].append(row)
            elif status == "pass" and ((rec.get("note") or "").strip() or rec.get("files")):
                buckets["pass_noted"].append(row)

    my_bugs = [e for e in bugs if e.get("batchId") == batch["id"]]
    my_reqs = [e for e in reqs if e.get("batchId") == batch["id"]]

    title = batch.get("title", batch["id"])
    date = batch.get("date")
    out.append("# %s%s" % (title, "（%s）" % date if date else ""))
    out.append("")
    out.append("已测 %d / %d · 未通过 %d · 未测试 %d · 通过留言 %d · 新 Bug %d · 新需求 %d" % (
        tested, total, len(buckets["fail"]), len(buckets["blocked"]),
        len(buckets["pass_noted"]), len(my_bugs), len(my_reqs)))
    out.append("")

    def dump_items(heading, rows):
        if not rows:
            return
        out.append("## %s（%d）" % (heading, len(rows)))
        out.append("")
        for section_title, item, rec in rows:
            out.append("- **%s** · %s" % (item.get("label", item.get("id")), item.get("text", "")))
            if section_title:
                out.append("  小节: %s" % section_title)
            out.extend(_lines(rec.get("note")))
            out.extend(_attachments(rec.get("files")))
        out.append("")

    dump_items("未通过", buckets["fail"])
    dump_items("未测试", buckets["blocked"])
    dump_items("通过但留了备注 / 优化建议", buckets["pass_noted"])

    def dump_entries(heading, entries):
        if not entries:
            return
        out.append("## %s（%d）" % (heading, len(entries)))
        out.append("")
        for entry in entries:
            out.append("- **%s**（%s · %s）" % (
                (entry.get("title") or "（无标题）").strip(), entry.get("id", ""),
                (entry.get("createdAt") or "")[:10]))
            out.extend(_lines(entry.get("note")))
            out.extend(_attachments(entry.get("files")))
        out.append("")

    dump_entries("新 Bug", my_bugs)
    dump_entries("新需求", my_reqs)


def main(argv=None):
    parser = argparse.ArgumentParser(description="汇总反馈站数据为 Markdown。")
    parser.add_argument("--root", default=SCRIPT_DIR, help="存放 checklist.json 与 data/ 的目录")
    parser.add_argument("--batch", action="append", default=[], help="只汇总这个批次 id,可重复")
    parser.add_argument("--all", action="store_true", help="汇总全部批次")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    data = os.path.join(root, "data")
    checklist = _read_json(os.path.join(root, "checklist.json"), {"batches": []})
    results = _read_json(os.path.join(data, "results.json"), {})
    bugs = _read_json(os.path.join(data, "bugs.json"), [])
    reqs = _read_json(os.path.join(data, "requirements.json"), [])
    if not isinstance(results, dict):
        results = {}
    bugs = [e for e in bugs if isinstance(e, dict)] if isinstance(bugs, list) else []
    reqs = [e for e in reqs if isinstance(e, dict)] if isinstance(reqs, list) else []

    batches = _pick_batches(checklist, args.batch, args.all)
    if not batches:
        sys.stderr.write("清单里没有批次(%s)。\n" % os.path.join(root, "checklist.json"))
        return 1
    out = []
    for batch in batches:
        _summarize_batch(batch, results, bugs, reqs, out)
    sys.stdout.write("\n".join(out).rstrip() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
