#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI生成视频专项技能路由器：只读扫描、分类、检索和显示技能包。"""

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "原始技能库"
INDEX_JSON = ROOT / "技能索引.json"
INDEX_MD = ROOT / "技能索引.md"

CATEGORY_RULES = [
    ("脚本与分镜", "脚本|剧本|分镜|故事板|故事|钩子|对白|编剧|拆解"),
    ("导演与镜头", "导演|镜头|运镜|摄影|电影|TVC|MV|一镜到底|动作指导|光影"),
    ("人物与资产", "人物|角色|人设|立绘|三视图|四视图|资产|换装|模特|一致性|表演"),
    ("视觉风格与场景", "风格|场景|美学|写实|国风|古风|水墨|赛博|科幻|渲染|材质|建筑"),
    ("广告与电商", "广告|电商|产品|带货|品牌|宣传|包装|详情页|珠宝|化妆品|汽车"),
    ("动画与漫剧", "动画|动漫|漫剧|短剧|仙侠|红楼梦|吉卜力|迪士尼|二次元"),
    ("声音与后期", "声音|配音|音频|播客|字幕|剪辑|混音|后期"),
    ("视频通用", "视频|短片|短视频|影像|成片|生成器|工作流|视觉"),
]


def read_text(path):
    return path.read_text(encoding="utf-8-sig", errors="replace")


def category(name, description):
    text = f"{name} {description}"
    for label, pattern in CATEGORY_RULES:
        if re.search(pattern, text, re.I):
            return label
    return "其他待确认"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def metadata(skill_dir):
    name = skill_dir.name
    description = ""
    meta_path = skill_dir / "_meta.json"
    if meta_path.exists():
        try:
            data = json.loads(read_text(meta_path))
            name = str(data.get("name") or data.get("title") or name)
            description = str(data.get("description") or data.get("summary") or "")
        except (OSError, ValueError):
            pass
    skill_path = skill_dir / "SKILL.md"
    if skill_path.exists():
        text = read_text(skill_path)
        if not description:
            match = re.search(r"^description:\s*(.+)$", text, re.M)
            description = match.group(1).strip().strip('"') if match else ""
    return name, description, skill_path


def build_index():
    rows = []
    for directory in sorted((p for p in LIB.iterdir() if p.is_dir()), key=lambda p: p.name):
        skill_path = directory / "SKILL.md"
        if not skill_path.exists():
            continue
        name, description, skill_path = metadata(directory)
        rows.append({
            "name": name,
            "folder": directory.name,
            "relative_path": str(skill_path.relative_to(ROOT)).replace("\\", "/"),
            "category": category(name, description),
            "description": description,
            "skill_hash": sha256(skill_path),
        })
    payload = {
        "schema_version": "1.0",
        "source": "D:/UserFiles/Desktop/skills",
        "copied_to": str(LIB).replace("\\", "/"),
        "skill_count": len(rows),
        "categories": {label: sum(r["category"] == label for r in rows) for label, _ in CATEGORY_RULES} | {"其他待确认": sum(r["category"] == "其他待确认" for r in rows)},
        "skills": rows,
    }
    INDEX_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 专项技能索引", "", f"技能数量：{len(rows)}", "", "| 分类 | 数量 |", "|---|---:|"]
    for label, count in payload["categories"].items():
        lines.append(f"| {label} | {count} |")
    lines += ["", "## 技能列表", "", "| 名称 | 分类 | SKILL 路径 | 哈希 |", "|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['name'].replace('|', '/') } | {row['category']} | `{row['relative_path']}` | `{row['skill_hash']}` |")
    INDEX_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def load_index():
    if not INDEX_JSON.exists():
        return build_index()
    return json.loads(read_text(INDEX_JSON))


def search(query, video_only=False, limit=12):
    data = load_index()
    terms = [x.lower() for x in re.findall(r"[A-Za-z0-9_+-]+|[\u4e00-\u9fff]+", query) if x.strip()]
    if not terms:
        return []
    rows = []
    for row in data["skills"]:
        hay = " ".join([row["name"], row["folder"], row["category"], row["description"]]).lower()
        if video_only and row["category"] == "其他待确认":
            continue
        score = sum(hay.count(term) for term in terms)
        if query.lower() in hay:
            score += 5
        if score:
            rows.append((score, row))
    rows.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [{"score": score, **row} for score, row in rows[:limit]]


def main():
    parser = argparse.ArgumentParser(description="AI生成视频专项技能路由器")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rebuild", help="重建技能索引")
    s = sub.add_parser("search", help="按关键词检索技能")
    s.add_argument("query")
    s.add_argument("--video-only", action="store_true")
    s.add_argument("-n", "--limit", type=int, default=12)
    s.add_argument("--json", action="store_true")
    show = sub.add_parser("show", help="按名称查看技能")
    show.add_argument("name")
    args = parser.parse_args()
    if args.command == "rebuild":
        data = build_index()
        print(f"已建立专项技能索引：{INDEX_JSON}（{data['skill_count']} 个技能）")
    elif args.command == "search":
        result = search(args.query, args.video_only, args.limit)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif not result:
            print("未找到匹配技能：" + args.query)
        else:
            for row in result:
                print(f"[{row['score']}] {row['name']} ｜ {row['category']} ｜ {row['relative_path']}")
    else:
        data = load_index()
        hits = [r for r in data["skills"] if args.name.lower() in r["name"].lower() or args.name.lower() in r["folder"].lower()]
        print(json.dumps(hits[:20], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
