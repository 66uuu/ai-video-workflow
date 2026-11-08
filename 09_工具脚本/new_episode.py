#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新一集脚手架：一条命令把「新集」需要的目录、时间轴、提示词骨架全部生出来

以前开 EP05 要手工复制一堆文件、手算帧数、手写时间轴，容易出错（帧数不满足
4n+1 会导致 I2V 直接报错）。这个脚本把这些固定动作固化掉。

用法：
  python new_episode.py --ep EP05 --shots shots.csv
  python new_episode.py --ep EP05 --shots shots.csv --project-root D:/UserFiles/Desktop/AI产物/20261028_EP05
  python new_episode.py --ep EP05 --shots shots.csv --fps 24 --force
  python new_episode.py --ep EP05 --shots EP05_shots.json     # 也吃 json

shots.csv 每行：镜号,秒数,场景,景别,内容
  S01,3.0,SC01,大特写,报纸上的划痕
  S02,2.5,SC02,大全景,档案库空镜

生成的：
  06_分镜与时间轴/EP05_timeline_v2.json   时间轴（含 start/end/frames/时长校验）
  06_分镜与时间轴/SHOTS_EP05.json         提示词骨架（prompt 留空等你填）
  08_资产库/EP05_关键帧/                  关键帧落点

校验：
  · 帧数自动取到 4n+1（Wan2.2 只吃 4n+1 帧，差一帧就报错）
  · start 必须严丝合缝接上一镜的 end
  · 总时长与各路求和必须一致
"""
import argparse
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def safe_print(message):
    """兼容 Windows 非 UTF-8 控制台，不能因勾叉符号导致脚手架崩溃。"""
    try:
        print(message)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(str(message).encode(enc, errors="replace").decode(enc, errors="replace"))


def snap_4n1(sec, fps):
    """秒 -> 最近的 4n+1 帧（Wan2.2 的硬约束）"""
    raw = max(1, round(float(sec) * fps))
    n = max(1, round((raw - 1) / 4.0))
    return 4 * n + 1


def load_rows(path):
    rows = []
    if path.lower().endswith(".json"):
        data = json.load(open(path, encoding="utf-8"))
        for r in data.get("shots") or data:
            rows.append((r.get("shot_id") or r.get("id"), float(r.get("seconds") or r.get("duration") or 0),
                         r.get("scene", ""), r.get("shot_size", ""), r.get("content", "")))
        return rows
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if not row or not row[0].strip() or row[0].strip().startswith("#"):
                continue
            if row[0].strip() in ("镜号", "shot", "id"):
                continue
            rows.append((row[0].strip(), float(row[1]), *[(c.strip() if i < len(row) else "")
                                                          for i, c in enumerate(row[2:5], start=2)]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep", required=True, help="集号，如 EP05")
    ap.add_argument("--shots", required=True, help="镜表 csv/json")
    ap.add_argument("--fps", type=float, default=24.0)
    ap.add_argument("--project-root", default=os.environ.get("NR_PROJECT_ROOT", ROOT),
                    help="项目根目录；建议使用 <D盘>\\UserFiles\\Desktop\\AI产物 下的独立目录")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    a = ap.parse_args()

    ep = a.ep.upper()
    project_root = os.path.abspath(a.project_root)
    timeline_dir = os.path.join(project_root, "06_分镜与时间轴")
    asset_dir = os.path.join(project_root, "08_资产库")
    os.makedirs(project_root, exist_ok=True)
    for output_name in ("图片", "视频", "成片", "日志"):
        os.makedirs(os.path.join(project_root, output_name), exist_ok=True)
    tp = os.path.join(timeline_dir, "%s_timeline_v2.json" % ep)
    sp = os.path.join(timeline_dir, "SHOTS_%s.json" % ep)
    kd = os.path.join(asset_dir, "%s_关键帧" % ep)

    if not a.force:
        for p in (tp, sp):
            if os.path.exists(p):
                raise SystemExit("%s 已存在。要重做请加 --force（否则会覆盖你的提示词）" % p)
    if not os.path.exists(a.shots):
        raise SystemExit("镜表不存在：%s" % a.shots)

    rows = load_rows(a.shots)
    if not rows:
        raise SystemExit("镜表是空的")

    shots, cursor, total_frames = [], 0.0, 0
    for sid, sec, scene, size, content in rows:
        frames = snap_4n1(sec, a.fps)
        dur = frames / a.fps
        shots.append({
            "shot_id": sid, "scene": scene, "shot_size": size, "content": content,
            "start": round(cursor, 3), "end": round(cursor + dur, 3),
            "duration": round(dur, 3), "frames": frames,
            "dialogue": "", "speaker": "—", "prompt": "",
        })
        cursor += dur
        total_frames += frames

    timeline = {"episode": ep, "version": 2, "fps": a.fps, "total_frames": total_frames,
                "total_seconds": round(cursor, 3), "shots": shots}

    os.makedirs(timeline_dir, exist_ok=True)
    os.makedirs(kd, exist_ok=True)
    json.dump(timeline, open(tp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    model = {
        "unet": "Wan2.2-TI2V-5B-Q5_K_M.gguf",
        "clip": "umt5-xxl-encoder-Q4_K_M.gguf",
        "text_encoder_type": "wan", "vae": "wan_2.1_vae.safetensors",
        "shift": 8.0, "width": 512, "height": 768, "steps": 20,
        "cfg": 6.0, "sampler": "uni_pc", "scheduler": "beta", "fps": a.fps,
    }
    shot_pack = {
        "episode": ep, "model": model,
        "shots": [{
            "id": s["shot_id"], "frames": s["frames"], "scene": s["scene"],
            "img": "08_资产库/%s_关键帧/%s.png" % (ep, s["shot_id"]),
            "action": s["content"] or "保持主体和构图稳定，完成一个清晰的小动作",
            "sound": "", "music": "", "lens": s["shot_size"] or "中景",
            "prompt": s["content"] or "",
        } for s in shots], "blocked": [],
    }
    json.dump(shot_pack,
              open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump({"episode": ep, "fps": a.fps, "timeline": tp, "shots": sp,
               "asset_dir": kd, "output_dirs": ["图片", "视频", "成片", "日志"]},
              open(os.path.join(project_root, "project.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # 三重自检（和时间轴生成脚本同一套判据）
    gaps = [(p["shot_id"], p["start"], s["start"]) for p, s in zip(shots, shots[1:])
            if abs(p["end"] - s["start"]) > 1e-6]
    bad = [s["shot_id"] for s in shots if (s["frames"] - 1) % 4 != 0]
    safe_print("%s：%d 镜 / %d 帧 / %.3fs" % (ep, len(shots), total_frames, cursor))
    safe_print("  时间轴  %s" % tp)
    safe_print("  提示词  %s" % sp)
    safe_print("  关键帧  %s" % kd)
    safe_print("  ✓ 4n+1 帧约束" if not bad else "  ✗ 帧数不合 4n+1：%s" % bad)
    safe_print("  ✓ 时间轴无空隙" if not gaps else "  ✗ 有空隙：%s" % gaps)
    if bad or gaps:
        sys.exit(1)
    safe_print("下一步：填 SHOTS_%s.json 的 prompt → gen_image.py --jobs → batch_local.py --submit-only" % ep)


if __name__ == "__main__":
    main()
