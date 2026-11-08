#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
通用一键出片：统一规格 → 拼接 → 打包到 D 盘成果区
=====================================================
只做交付，不改内容。生成的原片原封不动一并打包。

流程：
  1. 按项目时间轴的镜头顺序，找项目视频目录/<镜号>_i2v.mp4
  2. 逐镜统一到 1024×1536 / 24fps / yuv420p（lanczos 2× 放大）
  3. 无音轨的镜头补一条静音轨，避免播放器/剪辑软件出错
  4. 按顺序 concat 成正片
  5. 打包到桌面：正片 + 逐镜原片 + 时间轴 + 提示词包 + 交付说明

用法：
  python assemble_ep04.py                # 全片（缺镜头则拒绝出正片，只出预览）
  python assemble_ep04.py --allow-partial # 缺镜头也拼，用于中途看效果
  python assemble_ep04.py --native        # 不放大，保持 512×768
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from pathlib import Path
from project_paths import ProjectPaths

FFMPEG = (os.environ.get("FFMPEG")
          or next((p for p in (r"ComfyUI\ffmpeg.exe",
                               r"<D盘>\ffmpeg\bin\ffmpeg.exe") if os.path.exists(p)), None)
          or shutil.which("ffmpeg") or "ffmpeg")
PROJECT = ProjectPaths()
EPISODE = PROJECT.episode
EPDIR = str(PROJECT.root)
VIDDIR = str(PROJECT.video_dir)
REWORK = str(PROJECT.rework_json)
TMP = str(PROJECT.output_dir / "_临时合成")
TIMELINE = str(PROJECT.timeline)
SHOTS_FILE = str(PROJECT.shots)
DELIVERY_ROOT = str(PROJECT.output_dir)

OUT_W, OUT_H = 1024, 1536
LOG = []


def log(m):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(str(m).encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)
    LOG.append(m)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return r


def normalize(src, dst, native, grade=False):
    vf = [] if native else ["scale=%d:%d:flags=lanczos" % (OUT_W, OUT_H)]
    if grade:
        # 统一观感：轻微提对比 / 压饱和 / 冷阴影 / 轻锐化
        # 逐镜单独调色会让相邻镜头发色跳，整集统一过一次才连得住
        vf.append("eq=contrast=1.07:saturation=0.90:brightness=-0.012")
        vf.append("colorbalance=rs=-0.025:bs=0.032:rm=-0.008")
        vf.append("unsharp=5:5:0.45:5:5:0.0")
    f = []
    if vf:
        f = ["-vf", ",".join(vf)]
    run([FFMPEG, "-y", "-i", src,
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         *f,
         "-c:v", "libx264", "-preset", "medium", "-crf", "17",
         "-pix_fmt", "yuv420p", "-r", "24",
         "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
         dst, "-loglevel", "error"])


def seg_duration(path):
    """探每段实际时长（秒），xfade 的 offset 必须按真实时长累加"""
    ext = ".exe" if os.name == "nt" else ""
    probe = os.path.join(os.path.dirname(FFMPEG), "ffprobe" + ext)
    if not os.path.exists(probe):
        probe = shutil.which("ffprobe")
    out = subprocess.check_output(
        [probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        text=True).strip()
    return float(out)


def concat_xfade(segs, fade, out):
    """镜头之间做短溶解，避免逐镜硬切。总长会缩短 (n-1)*fade"""
    durs = [seg_duration(p) for p in segs]
    cmd = [FFMPEG, "-y", "-v", "error"]
    for p in segs:
        cmd += ["-i", p]
    chains, prev, acc = [], "[0:v]", durs[0]
    for i in range(1, len(segs)):
        offset = acc - fade
        outl = "[vx%d]" % i
        chains.append("%s[%d:v]xfade=transition=fade:duration=%.3f:offset=%.3f%s"
                      % (prev, i, fade, offset, outl))
        prev = outl
        acc = acc + durs[i] - fade
    # 各段音轨都是静音占位，直接用第一段的音轨补长即可
    graph = ";".join(chains + ["[0:a]apad[aout]"])
    cmd += ["-filter_complex", graph, "-map", prev, "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
            "-r", "24", "-c:a", "aac", "-b:a", "128k", "-shortest",
            "-movflags", "+faststart", out]
    run(cmd)
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=os.environ.get("NR_PROJECT_ROOT", ""))
    ap.add_argument("--episode", default=os.environ.get("NR_EPISODE", ""))
    ap.add_argument("--timeline", default=os.environ.get("NR_TIMELINE", ""))
    ap.add_argument("--shots", default=os.environ.get("NR_SHOTS", ""))
    ap.add_argument("--video-dir", default=os.environ.get("NR_VIDEO_DIR", ""))
    ap.add_argument("--output-dir", default=os.environ.get("NR_OUTPUT_DIR", ""))
    ap.add_argument("--allow-partial", action="store_true")
    ap.add_argument("--allow-bad", action="store_true",
                    help="质检未通过也照拼（占位静止帧/出画会进入正片）")
    ap.add_argument("--native", action="store_true")
    ap.add_argument("--no-desktop", action="store_true")
    ap.add_argument("--grade", action="store_true", help="整集统一调色（冷阴影 + 压饱和 + 轻锐化）")
    ap.add_argument("--xfade", type=float, default=0.0, help="镜头间溶解秒数，0=硬切")
    a = ap.parse_args()

    global PROJECT, EPISODE, EPDIR, VIDDIR, REWORK, TMP, TIMELINE, SHOTS_FILE, DELIVERY_ROOT
    PROJECT = ProjectPaths(project_root=a.project_root, episode=a.episode,
                           timeline=a.timeline, shots=a.shots, video_dir=a.video_dir,
                           output_dir=a.output_dir)
    EPISODE = PROJECT.episode
    EPDIR = str(PROJECT.root)
    VIDDIR = str(PROJECT.video_dir)
    REWORK = str(PROJECT.rework_json)
    TMP = str(PROJECT.output_dir / "_临时合成")
    TIMELINE = str(PROJECT.timeline)
    SHOTS_FILE = str(PROJECT.shots)
    DELIVERY_ROOT = str(PROJECT.output_dir)
    if not os.path.exists(TIMELINE) or not os.path.exists(SHOTS_FILE):
        log("✗ 找不到时间轴或镜头包：%s / %s" % (TIMELINE, SHOTS_FILE))
        return 1

    tl = json.load(open(TIMELINE, encoding="utf-8"))
    shots = tl["shots"]
    pack = json.load(open(SHOTS_FILE, encoding="utf-8"))
    ready = {s["id"] for s in pack["shots"]}

    have, miss, blocked = [], [], []
    for s in shots:
        sid = s["shot_id"]
        f = os.path.join(VIDDIR, "%s_i2v.mp4" % sid)
        if os.path.exists(f):
            have.append((s, f))
        elif sid in ready:
            miss.append(sid)          # 该渲还没渲完
        else:
            blocked.append(sid)       # 根本没关键帧

    log("=" * 70)
    log("%s 出片 · 镜数 %d ｜ 已有 %d ｜ 待渲 %d ｜ 缺关键帧 %d" %
        (EPISODE, len(shots), len(have), len(miss), len(blocked)))
    log("=" * 70)
    if miss:
        log("待渲：" + ", ".join(miss))
    if blocked:
        log("缺关键帧：" + ", ".join(blocked))

    full = (len(have) == len(shots))
    if not full and not a.allow_partial:
        log("-" * 70)
        log("✗ 不是完整集，拒绝出正片。当前只出了 %d/%d。" % (len(have), len(shots)))
        log("  要看效果可加 --allow-partial；要补齐请先补关键帧。")
        return 1

    # 有文件 ≠ 能交片：按重做清单再拦一道，避免占位静止帧混进正片
    bad = []
    if os.path.exists(REWORK):
        try:
            for r in json.load(open(REWORK, encoding="utf-8")):
                if (not r.get("ok") or
                        (r.get("ncc") is not None and r.get("ncc") < 0.70)):
                    m = r.get("metrics") or {}
                    bad.append((r["shot"], m.get("step"), r.get("rep", "")))
        except Exception as e:
            log("⚠ 重做清单读不了（%s），跳过质检拦截" % str(e)[:40])
    if bad:
        log("-" * 70)
        log("✗ 有 %d 镜质检未通过，拒绝出正片：" % len(bad))
        for sid, step, rep in bad:
            log("   %-5s 相邻%s  %s" % (sid, ("%.2f" % step) if step is not None else "—", rep))
        log("  先按 video_i2v/重做清单.md 重跑；执意要拼加 --allow-bad。")
        if not a.allow_bad:
            return 1
    elif not os.path.exists(REWORK):
        log("✗ 没找到重做清单：请先跑 batch_local.py --qa-all，不能跳过质检")
        if not a.allow_bad:
            return 1

    os.makedirs(TMP, exist_ok=True)
    segs = []
    tag = ("_g" if a.grade else "")
    for i, (s, f) in enumerate(have):
        sid = s["shot_id"]
        dst = os.path.join(TMP, "%02d_%s_norm%s.mp4" % (i + 1, sid, tag))
        if not os.path.exists(dst):
            normalize(f, dst, a.native, a.grade)
        segs.append(dst)
        log("  [%02d] %-5s %5.2fs  OK" % (i + 1, sid, s["duration"]))

    lst = os.path.join(TMP, "_concat.txt")
    with open(lst, "w", encoding="utf-8") as fp:
        for p in segs:
            fp.write("file '%s'\n" % p.replace("\\", "/"))

    stamp = time.strftime("%Y%m%d")
    name = "%s_%s%s%s.mp4" % (
        EPISODE,
        "正片_" if full else "预览_",
        ("调色_" if a.grade else "") + ("溶解_" if a.xfade else ""), stamp)
    os.makedirs(DELIVERY_ROOT, exist_ok=True)
    out = os.path.join(DELIVERY_ROOT, name)
    if a.xfade > 0:
        real = concat_xfade(segs, a.xfade, out)
        log("  拼接：%d 段溶解 %.2fs（预计缩短 %.2fs）" % (len(segs), a.xfade,
                                                   (len(segs) - 1) * a.xfade))
    else:
        run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst,
             "-c", "copy", "-movflags", "+faststart", out, "-loglevel", "error"])

    # 校验总长
    try:
        import av
        with av.open(out) as c:
            st = c.streams.video[0]
            dur = float(c.duration) / 1e6 if c.duration else 0
            log("-" * 70)
            log("正片：%s" % out)
            log("  %dx%d  %.2ffps  %d 帧  %.2fs  %.1fMB" % (
                st.width, st.height, float(st.average_rate), st.frames or 0,
                dur, os.path.getsize(out) / 1048576))
            total_duration = tl.get("total_duration", tl.get("total_seconds", 0))
            log("  时间轴标称 %.2fs  差 %+.2fs" % (total_duration, dur - total_duration))
    except Exception as e:
        log("  （时长校验跳过：%s）" % str(e)[:60])

    if a.no_desktop:
        return 0

    # ── 打包到成果区 ──
    box = os.path.join(DELIVERY_ROOT, "%s_交付_%s" % (EPISODE, stamp))
    os.makedirs(box, exist_ok=True)
    sub = os.path.join(box, "分镜原片")
    os.makedirs(sub, exist_ok=True)
    shutil.copy2(out, os.path.join(box, os.path.basename(out)))
    for s, f in have:
        shutil.copy2(f, os.path.join(sub, os.path.basename(f)))
    for extra in (os.path.basename(TIMELINE), os.path.basename(SHOTS_FILE)):
        p = str(Path(TIMELINE).parent / extra)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(box, extra))

    total_duration = tl.get("total_duration", tl.get("total_seconds", 0))
    readme = ["%s 交付包" % EPISODE,
              "=" * 40,
              "生成时间：%s" % time.strftime("%Y-%m-%d %H:%M"),
              "生成方式：本机 ComfyUI + Wan2.2 TI2V-5B（GGUF Q5_K_M），逐镜模型推理，非静帧推拉",
              "画幅：%s" % ("512×768 原生" if a.native else "%d×%d（lanczos 2× 放大）" % (OUT_W, OUT_H)),
              "镜数：%d / %d" % (len(have), len(shots)),
              "总时长：%.2f 秒" % total_duration,
              "",
              "目录说明：",
              "  %s   正片（可直接播放/上传）" % os.path.basename(out),
              "  分镜原片/            每一镜的模型原始输出，未经二次处理",
              "  %s                时间轴唯一真源" % os.path.basename(TIMELINE),
              "  %s                提示词唯一真源" % os.path.basename(SHOTS_FILE),
              "",
              "未完成事项：" + ("无" if full else "缺 %d 镜（见对话记录）" % (len(shots) - len(have))),
              "音轨：本版为静音轨占位，台词/声景/配乐待 TTS 与后期",
              ]
    with open(os.path.join(box, "交付说明.txt"), "w", encoding="utf-8") as fp:
        fp.write("\n".join(readme))

    log("-" * 70)
    log("已打包到桌面：%s" % box)
    os.makedirs(os.path.join(DELIVERY_ROOT, "日志"), exist_ok=True)
    with open(os.path.join(DELIVERY_ROOT, "日志", "assemble_%s.log" % stamp), "w", encoding="utf-8") as fp:
        fp.write("\n".join(LOG))
    return 0


if __name__ == "__main__":
    sys.exit(main())
