#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
EP04 秒级时间轴生成器
从单一真源（SHOTS 列表）生成三份交付物：
  1. EP04_timeline.csv   —— Excel / 剪辑软件可直接读
  2. EP04_timeline.json  —— ComfyUI / Python 合成脚本读
  3. EP04_concat.txt     —— ffmpeg concat demuxer 读
并做三重校验：总长、总帧数、镜号连续性。

真源纪律：改时长只改本文件，然后重跑；不要手改 CSV/JSON。
"""
import csv
import json
import os
import sys

FPS = 24
PAD = "00:00:00.000"  # 占位，稍后按帧算

# ── 单一真源 ────────────────────────────────────────────────
# (镜号, 时长s, 场, 景别, 运动, 节拍段, 核心资产, 台词, 角色, 声音标记)
SHOTS = [
    ("S01", 3.0, "SC01", "大特写",  "极缓推8%", "冷开场",   "PR_OLDPAPER划痕版|SC_DEPOT复用档案室", "", "—", ""),
    ("S02", 4.0, "SC02", "大远景",  "缓摇→停",  "情境",     "SC_DEPOT复用地库|CH_LINYAN远景", "十月十七号……市报社，地下二层。", "林砚", "录音笔起录"),
    ("S03", 3.0, "SC02", "中景",    "固定",     "情境",     "CH_LINYAN|PR_RECORDER", "", "林砚", ""),
    ("S04", 2.5, "SC02", "特写",    "微退",     "情境",     "CH_LINYAN手|抽屉", "", "林砚", "抽屉滑轨"),
    ("S05", 2.5, "SC02", "大特写",  "固定",     "异变",     "F04索引卡留白", "", "—", ""),
    ("S06", 3.0, "SC02", "近景",    "固定",     "异变",     "F05合订本留白", "", "—", ""),
    ("S07", 2.5, "SC02", "大特写",  "极缓推6%", "异变",     "缺页装订孔", "……没了。", "林砚", "翻页骤停"),
    ("S08", 2.5, "SC02", "中景",    "固定",     "异变",     "CH_LINYAN", "", "林砚", ""),
    ("S09", 3.0, "SC02", "全景",    "固定",     "异变",     "CH_ARCHIVIST|SC_DEPOT复用地库", "找什么。", "档案员", "CRT电流"),
    ("S10", 3.0, "SC02", "中景",    "固定",     "异变",     "CH_LINYAN|CH_ARCHIVIST|缺页", "三年前十月份。郊环线，第七段。", "林砚", ""),
    ("S11", 2.5, "SC02", "近景",    "固定",     "异变",     "CH_ARCHIVIST", "那天没有事故。", "档案员", ""),
    ("S12", 2.0, "SC02", "特写",    "固定",     "异变",     "CH_LINYAN手指", "", "—", "衣料摩擦"),
    ("S13", 3.0, "SC02", "近景",    "微推3%",   "异变收尾", "CH_LINYAN", "那这照片上的人……是谁。", "林砚", ""),
    ("S14", 3.0, "SC03", "中景",    "固定",     "规则触发", "CH_ARCHIVIST|CH_LINYAN|合订本", "姑娘，查不到的东西……就别查了。", "档案员", ""),
    ("S15", 2.5, "SC03", "近景",    "固定",     "规则触发", "CH_LINYAN_EX冷", "", "—", ""),
    ("S16", 3.0, "SC03", "特写",    "极缓推5%", "规则触发", "CH_ARCHIVIST|老花镜反光挡眼", "", "档案员", "摘镜金属细响"),
    ("S17", 4.0, "SC03", "近景",    "完全固定", "规则触发", "CH_ARCHIVIST", "天亮之前，别说自己真名。", "档案员", ""),
    ("S18", 3.0, "SC03", "特写",    "固定",     "规则触发", "PR_RECORDER红灯不亮|CH_LINYAN手", "", "—", ""),
    ("S19", 4.0, "SC03", "大全景",  "固定",     "规则触发尾", "SC_DEPOT复用走廊|CH_LINYAN剪影", "", "—", "抽空1"),
    ("S20", 3.5, "SC04", "中景",    "固定",     "反转",     "SC台阶|PR_PHONE_LY", "喂，您好……我想打听个人。车队是不是有个姓周的师傅。", "林砚", "拨号音"),
    ("S21", 3.0, "SC04", "特写",    "微推4%",   "反转",     "PR_PHONE_LY屏幕留白", "老周？三年前就不在了。", "车队听筒", "电话失真"),
    ("S22", 3.0, "SC04", "大特写",  "极缓推6%", "反转收尾", "CH_LINYAN眼部瞳孔收缩", "", "—", "抽空2"),
    ("S23", 4.0, "SC05", "全景",    "固定",     "新钩子",   "SC_DEPOT停车场|车门开", "", "—", "车门咔"),
    ("S24", 3.5, "SC05", "中景",    "极缓推5%", "新钩子",   "CH_LAOZHOU|PR_PINGANFU红", "", "老周", "脚步匀速"),
]

# 抽空区间（镜号, 镜内起始偏移s, 时长s）
VOIDS = [("S19", 0.6, 0.8), ("S22", 0.5, 0.8)]

RETROFIT = [
    ("S20A", 3.0, "SC04", "中景",   "固定",     "反转",   "PR_PHONE_LY等待音", "", "—", ""),
    ("S21A", 2.5, "SC04", "近景",   "固定",     "反转",   "CH_LINYAN摸口袋PR_PINGANFU", "", "—", ""),
    ("S22A", 3.0, "SC04", "特写",   "固定",     "反转",   "PR_PHONE_LY熄屏映脸", "", "—", ""),
    ("S22B", 2.0, "SC04", "中景",   "固定",     "反转",   "SC_STATION复用站牌", "", "—", ""),
    ("S23A", 3.0, "SC05", "中景",   "固定",     "新钩子", "SC_CARINT空驾驶座顶灯", "", "—", ""),
    ("S24A", 2.5, "SC05", "近景",   "固定",     "新钩子", "CH_LAOZHOU|PR_RECORDER", "", "老周", ""),
    ("S24B", 2.0, "SC05", "特写",   "固定",     "新钩子", "PR_PINGANFU晃幅加大", "", "—", ""),
]


# ── 补拍镜插入位置（v2 合并用）────────────────────────────
# 语义：在 key 这一镜「之后」插入；S24A 是 S24「之前」，单独处理。
_AFTER = {
    "S20": ["S20A"],
    "S21": ["S21A"],
    "S22": ["S22A", "S22B"],
    "S23": ["S23A"],
    "S24": ["S24B"],
}
_BEFORE = {"S24": ["S24A"]}


def merged_shots():
    """24 原镜 + 7 补拍镜 → 31 镜的叙事顺序（不改动原镜号）"""
    base = {s[0]: s for s in SHOTS}
    retro = {s[0]: s for s in RETROFIT}
    out = []
    for i in range(1, len(SHOTS) + 1):
        sid = "S%02d" % i
        for r in _BEFORE.get(sid, []):
            out.append(retro[r])
        out.append(base[sid])
        for r in _AFTER.get(sid, []):
            out.append(retro[r])
    return out


def tc(sec):
    """秒 → HH:MM:SS.mmm"""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec - h * 3600 - m * 60
    return "%02d:%02d:%06.3f" % (h, m, s)


def frames(sec):
    return int(round(sec * FPS))


def build(shots, name_with_index=False):
    t = 0.0
    out = []
    for i, (sid, dur, sc, size, mv, beat, asset, line, who, snd) in enumerate(shots):
        start, end = t, t + dur
        vf = ("%02d_%s.mp4" % (i + 1, sid)) if name_with_index else ("%s.mp4" % sid)
        out.append({
            "index": i + 1,
            "shot_id": sid,
            "scene": sc,
            "beat": beat,
            "start": round(start, 3),
            "end": round(end, 3),
            "start_tc": tc(start),
            "end_tc": tc(end),
            "duration": dur,
            "frames": frames(dur),
            "shot_size": size,
            "camera_move": mv,
            "assets": asset,
            "dialogue": line,
            "speaker": who,
            "audio_note": snd,
            "source_image": "",
            "video_file": vf,
            "transition": "cut",
        })
        t = end
    return out, round(t, 3)


COLS = ["index", "shot_id", "scene", "beat", "start", "end", "start_tc", "end_tc",
        "duration", "frames", "shot_size", "camera_move", "assets", "dialogue",
        "speaker", "audio_note", "source_image", "video_file", "transition"]


def write_all(epdir, rows, suffix, concat_header, prefix="shots/"):
    csv_path = os.path.join(epdir, "EP04_timeline%s.csv" % suffix)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    json_path = os.path.join(epdir, "EP04_timeline%s.json" % suffix)
    concat_path = os.path.join(epdir, "EP04_concat%s.txt" % suffix)
    with open(concat_path, "w", encoding="utf-8") as f:
        f.write(concat_header)
        for r in rows:
            f.write("file '%s%s'\n" % (prefix, r["video_file"]))

    return csv_path, json_path, concat_path


def gen_v2(epdir):
    """31 镜版（24 原镜 + 7 补拍镜），91.0s / 2184 帧"""
    seq = merged_shots()
    rows, total = build(seq, name_with_index=True)
    total_frames = sum(r["frames"] for r in rows)

    assert len(seq) == 31, "镜数不符：%d != 31" % len(seq)
    assert abs(total - 91.0) < 1e-6, "总长不符：%.3f != 91.000" % total
    assert total_frames == 2184, "总帧数不符：%d != 2184" % total_frames
    for i, r in enumerate(rows):
        assert r["index"] == i + 1
    # 补拍镜必须全部在册且只出现一次
    for s in RETROFIT:
        assert sum(1 for r in rows if r["shot_id"] == s[0]) == 1, "补拍镜重复或缺失：%s" % s[0]

    payload = {
        "episode": "EP04",
        "version": "v2_91s",
        "title": "报纸",
        "fps": FPS,
        "resolution": [1024, 1536],
        "aspect": "2:3",
        "codec": {"format": "mp4", "codec": "h264", "crf": 18},
        "total_duration": total,
        "total_frames": total_frames,
        "shot_count": len(rows),
        "base_shots": len(SHOTS),
        "retrofit_shots": len(RETROFIT),
        "voids": [{"shot_id": v[0], "offset": v[1], "duration": v[2]} for v in VOIDS],
        "shots": rows,
    }
    csv_path, json_path, concat_path = write_all(
        epdir, rows, "_v2",
        "# EP04 成片 v2 拼接清单（31 镜 / 91.0s）—— 每段须同分辨率/同帧率/同编码\n"
        "# 用法：ffmpeg -f concat -safe 0 -i EP04_concat_v2.txt -c copy EP04_成片_v2_91s.mp4\n")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("=" * 62)
    print("EP04 时间轴 v2（补拍后）生成完成")
    print("=" * 62)
    print("镜数        : %d  (%d 原镜 + %d 补拍镜)" % (len(rows), len(SHOTS), len(RETROFIT)))
    print("总长        : %.3fs  (%s)" % (total, tc(total)))
    print("总帧数      : %d  @ %dfps" % (total_frames, FPS))
    print("校验        : 总长 OK | 帧数 OK | 序号连续 OK | 补拍镜唯一 OK")
    for r in rows:
        mark = " +" if r["shot_id"] in {s[0] for s in RETROFIT} else "  "
        print("%s %2d  %-5s %5.1fs  %s → %s" %
              (mark, r["index"], r["shot_id"], r["duration"], r["start_tc"], r["end_tc"]))
    print("-" * 62)
    print("CSV         : %s" % csv_path)
    print("JSON        : %s" % json_path)
    print("concat      : %s" % concat_path)
    print("=" * 62)
    return 0


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 02_分镜
    root = os.path.dirname(base)
    epdir = os.path.join(root, "07_成片", "EP04")
    os.makedirs(epdir, exist_ok=True)

    if "--v2" in sys.argv[1:]:
        return gen_v2(epdir)

    rows, total = build(SHOTS)
    total_frames = sum(r["frames"] for r in rows)

    # ── 校验 1：总长 ──
    expect_total = 73.0
    assert abs(total - expect_total) < 1e-6, "总长不符：%.3f != %.3f" % (total, expect_total)

    # ── 校验 2：总帧数 ──
    expect_frames = 1752
    assert total_frames == expect_frames, "总帧数不符：%d != %d" % (total_frames, expect_frames)

    # ── 校验 3：镜号连续 ──
    ids = [r["shot_id"] for r in rows]
    for i, sid in enumerate(ids):
        assert sid == "S%02d" % (i + 1), "镜号不连续：期望 S%02d，实际 %s" % (i + 1, sid)

    # ── JSON ──
    retro_rows, _ = build(RETROFIT)
    payload = {
        "episode": "EP04",
        "title": "报纸",
        "fps": FPS,
        "resolution": [1024, 1536],
        "aspect": "2:3",
        "codec": {"format": "mp4", "codec": "h264", "crf": 18},
        "total_duration": total,
        "total_frames": total_frames,
        "shot_count": len(rows),
        "retrofit": {
            "adds_seconds": round(sum(s[1] for s in RETROFIT), 3),
            "total_after": round(total + sum(s[1] for s in RETROFIT), 3),
            "shots": retro_rows,
        },
        "voids": [{"shot_id": v[0], "offset": v[1], "duration": v[2]} for v in VOIDS],
        "shots": rows,
    }

    # ── CSV / JSON / concat（三份同一真源）──
    csv_path, json_path, concat_path = write_all(
        epdir, rows, "",
        "# EP04 成片拼接清单 —— 每段须为同分辨率/同帧率/同编码\n"
        "# 用法：ffmpeg -f concat -safe 0 -i EP04_concat.txt -c copy EP04_成片.mp4\n")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # ── 报告 ──
    print("=" * 62)
    print("EP04 时间轴生成完成")
    print("=" * 62)
    print("镜数        : %d" % len(rows))
    print("总长        : %.3fs  (%s)" % (total, tc(total)))
    print("总帧数      : %d  @ %dfps" % (total_frames, FPS))
    print("---")
    print("CSV         : %s" % csv_path)
    print("JSON        : %s" % json_path)
    print("concat      : %s" % concat_path)
    print("---")
    print("补拍镜数    : %d  +%.1fs  → 总长 %.1fs" % (
        len(RETROFIT), sum(s[1] for s in RETROFIT), total + sum(s[1] for s in RETROFIT)))
    print("抽空点      : %s" % ", ".join("%s@+%.1fs/%.1fs" % (v[0], v[1], v[2]) for v in VOIDS))
    print("校验        : 总长 OK | 帧数 OK | 镜号连续 OK")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
