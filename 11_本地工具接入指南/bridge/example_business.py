#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
example_business —— 业务脚本的标准写法（可移植样板）
=====================================================
这是一个「照着改就能跑新一集」的完整示例。没有一行硬编码路径。

它演示了六件事：
  1) 怎么读镜表（frames + 提示词）
  2) 怎么把关键帧上传给 ComfyUI（不依赖 input 目录布局）
  3) 怎么按 4n+1 生成再裁回精确帧数
  4) 怎么做断点续跑
  5) 怎么写落地命名（补零，保证排序正确）
  6) 怎么算帧差做基础质检

用法：
    python example_business.py --shots 镜表.json --frames 时间轴.json --keyframes 关键帧目录 --out 产出目录

镜表格式（最小）：
    {
      "shots": [
        { "id": "S01", "keyframe": "S01.png",
          "prompt": "夜，一名女子缓慢抬头，停住。雨声持续。无配乐。近景，50mm，浅景深。" }
      ]
    }

时间轴格式（只取 frames 字段）：
    { "shots": [ { "shot_id": "S01", "frames": 72 } ] }

这个脚本不依赖本项目的任何业务文件。把它拷到任何地方，只要有镜表 + 关键帧，
就能对着一个跑着的 ComfyUI 出片。
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from nr_bridge import Comfy, build_i2v, gen_len, trim_video


def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def build_frame_map(timeline_path):
    """从时间轴里取 {镜号: 帧数}"""
    if not timeline_path or not os.path.isfile(timeline_path):
        return {}
    d = load_json(timeline_path)
    out = {}
    for s in (d.get("shots") or []):
        sid = s.get("shot_id") or s.get("id")
        if sid and s.get("frames"):
            out[sid] = int(s["frames"])
    return out


def qa_video(path, min_adj=0.30, min_end=1.5):
    """
    基础质检：相邻帧差 + 首末帧差。没有 av/numpy 时返回 None（不阻断流程）。
    """
    try:
        import av
        import numpy as np
    except Exception:
        return None
    try:
        c = av.open(path)
        fr = [np.frombuffer(f.to_ndarray(format="gray").tobytes(), dtype=np.uint8)
              for f in c.decode(video=0)]
        c.close()
    except Exception:
        return None
    if len(fr) < 2:
        return {"frames": len(fr), "adj": 0.0, "end": 0.0, "pass": False}
    adj = float(np.mean([np.abs(fr[i + 1].astype(float) - fr[i].astype(float)).mean()
                         for i in range(len(fr) - 1)]))
    end = float(np.abs(fr[-1].astype(float) - fr[0].astype(float)).mean())
    return {"frames": len(fr), "adj": round(adj, 2), "end": round(end, 2),
            "pass": adj >= min_adj and end >= min_end}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", required=True, help="镜表 json（含 id / keyframe / prompt）")
    ap.add_argument("--frames", default="", help="时间轴 json（取 frames 字段，可选）")
    ap.add_argument("--keyframes", required=True, help="关键帧所在目录")
    ap.add_argument("--out", required=True, help="产出目录")
    ap.add_argument("--only", default="", help="只做指定镜，逗号分隔")
    ap.add_argument("--force", action="store_true", help="已存在的也重做")
    ap.add_argument("--default-frames", type=int, default=72, help="时间轴里没有时用这个")
    ap.add_argument("--steps", type=int, default=24)
    ap.add_argument("--width", type=int, default=512)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--submit-only", action="store_true", help="只压队列就退出")
    a = ap.parse_args()

    shots = load_json(a.shots).get("shots") or []
    if not shots:
        raise SystemExit("镜表里没有 shots")
    fmap = build_frame_map(a.frames)
    os.makedirs(a.out, exist_ok=True)

    only = set(x.strip() for x in a.only.split(",") if x.strip())
    if only:
        shots = [s for s in shots if s["id"] in only]

    c = Comfy()
    h = c.health()
    if not h["alive"]:
        raise SystemExit("ComfyUI 没起来：%s" % h.get("error", ""))

    print("ComfyUI: %s  队列 运行%d/等待%d" % (h["host"], h["running"], h["pending"]))
    print("待处理 %d 镜，产出到 %s\n" % (len(shots), os.path.abspath(a.out)))

    ok, skip, fail = 0, 0, 0
    t_all = time.time()

    for i, s in enumerate(shots, 1):
        sid = s["id"]
        # 落地名补零，保证 dir /b 排序正确（铁律 49）
        dst = os.path.join(a.out, "%02d_%s.mp4" % (i, sid))
        raw = os.path.join(a.out, "_raw", "%s_raw.mp4" % sid)

        if os.path.exists(dst) and not a.force:
            print("[%s] 跳过（已存在）" % sid)
            skip += 1
            continue

        kf = os.path.join(a.keyframes, s.get("keyframe") or "%s.png" % sid)
        if not os.path.isfile(kf):
            print("[%s] ✘ 关键帧不存在：%s" % (sid, kf))
            fail += 1
            continue

        frames = fmap.get(sid, a.default_frames)
        try:
            nm = c.upload_image(kf, "%s_ref.png" % sid)
            wf = build_i2v(nm, s["prompt"], frames=frames,
                           width=a.width, height=a.height, steps=a.steps,
                           prefix="NR/BIZ/%s" % sid)
            t0 = time.time()
            files = c.run(wf, os.path.join(a.out, "_raw"), number=None,
                          on_tick=lambda el: print("  … %.0fs" % el, end="\r", flush=True))
            print(" " * 16, end="\r")
            if not files:
                print("[%s] ✘ 跑完但没拿到文件" % sid)
                fail += 1
                continue

            os.makedirs(os.path.dirname(raw), exist_ok=True)
            if os.path.abspath(files[0]) != os.path.abspath(raw):
                os.replace(files[0], raw)

            # 4n+1 生成的帧数裁回精确帧数（铁律 52）
            trim_video(raw, dst, frames)

            q = qa_video(dst)
            if q is None:
                print("[%s] ✅ %d帧  %.0fs  （未装 av，跳过质检）"
                      % (sid, frames, time.time() - t0))
            else:
                flag = "✅" if q["pass"] else "⚠"
                print("[%s] %s %d帧 | 相邻%.2f | 首末%.2f | %.0fs"
                      % (sid, flag, q["frames"], q["adj"], q["end"], time.time() - t0))
            ok += 1

            if a.submit_only:
                # 只压队列模式：不等待，直接下一条
                continue

        except Exception as e:
            print("[%s] ✘ %s" % (sid, str(e)[:200]))
            fail += 1

    print("\n" + "-" * 60)
    print("完成 %d / 跳过 %d / 失败 %d   总耗时 %.0fs"
          % (ok, skip, fail, time.time() - t_all))


if __name__ == "__main__":
    main()
