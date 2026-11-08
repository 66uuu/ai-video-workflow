#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gen_jianying_draft —— 时间轴 JSON → 剪映专业版可编辑草稿（多轨自动组装）
=======================================================================
把 AI 生成视频工作流的产物，自动组装成剪映专业版里可直接打开精修的草稿：

    视频主轨  ← 各镜 mp4 / 图片（按时间轴 shots 顺序排列）
    字幕轨    ← timeline 里的台词（或直接导入 --srt）
    配音轨    ← --audio（整集配音）
    BGM 轨    ← --bgm（音量默认 0.3）

依赖（一次性）：
    pip install pyJianYingDraft

用法示例：
    python gen_jianying_draft.py ^
        --timeline "<D盘>\\...\\EP04_timeline_v2.json" ^
        --video-dir "<D盘>\\...\\EP04_视频" ^
        --audio "<D盘>\\...\\EP04_配音.mp3" ^
        --srt "<D盘>\\...\\EP04_字幕.srt" ^
        --bgm "<D盘>\\...\\BGM.mp3"

    # 只看排布不生成：
    python gen_jianying_draft.py --timeline xxx.json --dry-run

说明：
  * 草稿写入剪映「草稿位置」（默认自动探测本机 JianyingPro 草稿目录）。
  * 新版剪映 6+ 的 draft_content.json 是加密的，所以本脚本只做「新建草稿」，
    不读取/改写你已有的草稿（避免破坏原工程）。
  * 素材为本地绝对路径引用，生成后请勿移动素材文件。
  * 剪映 7+ 不支持脚本控制自动导出，需在剪映里手动点导出。
"""
import argparse
import glob
import json
import os
import sys

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".avi", ".webm")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def die(msg):
    print("[错误] " + msg)
    sys.exit(1)


def load_timeline(path):
    if not os.path.isfile(path):
        die("时间轴文件不存在: " + path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {"shots": data}
    if "shots" not in data:
        die("时间轴 JSON 结构不对：缺少 shots 数组")
    return data


def parse_canvas(timeline, width, height):
    if width and height:
        return int(width), int(height)
    res = str(timeline.get("resolution", "") or "")
    if "x" in res.lower():
        try:
            w, h = res.lower().split("x", 1)
            return int(w), int(h)
        except ValueError:
            pass
    return 1080, 1920


def find_material(shot, video_dir, timeline_dir):
    """按 shot_id 找素材：shot.video_file > video_dir 命名匹配 > 时间轴同目录。"""
    vf = (shot.get("video_file") or "").strip()
    if vf and os.path.isfile(vf):
        return vf

    sid = (shot.get("shot_id") or "").strip()
    if not sid:
        return None

    dirs = [d for d in (video_dir, timeline_dir) if d]
    for d in dirs:
        for ext in VIDEO_EXT + IMAGE_EXT:
            hit = glob.glob(os.path.join(d, "**", sid + "*" + ext), recursive=True)
            if hit:
                return sorted(hit)[0]
        # 也试 EP04_S01_ 这类前缀
        for ext in VIDEO_EXT + IMAGE_EXT:
            hit = glob.glob(os.path.join(d, "**", "*" + sid + "*" + ext), recursive=True)
            if hit:
                return sorted(hit)[0]
    return None


def default_drafts_dir():
    base = os.environ.get("LOCALAPPDATA", "")
    p = os.path.join(base, "JianyingPro", "User Data", "Projects", "com.lveditor.draft")
    return p if os.path.isdir(p) else None


def main():
    ap = argparse.ArgumentParser(description="时间轴 JSON → 剪映草稿")
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--drafts", default="")
    ap.add_argument("--video-dir", default="")
    ap.add_argument("--audio", default="")
    ap.add_argument("--bgm", default="")
    ap.add_argument("--srt", default="")
    ap.add_argument("--width", type=int, default=0)
    ap.add_argument("--height", type=int, default=0)
    ap.add_argument("--fps", type=int, default=0)
    ap.add_argument("--bgm-volume", type=float, default=0.3)
    ap.add_argument("--allow-replace", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        import pyJianYingDraft as draft
        from pyJianYingDraft import (
            DraftFolder, VideoSegment, TextSegment, AudioSegment,
            VideoMaterial, AudioMaterial, TrackSpec, TrackType, trange_seconds,
        )
    except ImportError:
        die("缺少依赖，请先执行: pip install pyJianYingDraft")

    timeline = load_timeline(args.timeline)
    timeline_dir = os.path.dirname(os.path.abspath(args.timeline))
    shots = sorted(timeline["shots"], key=lambda s: s.get("index", 0))

    w, h = parse_canvas(timeline, args.width, args.height)
    fps = args.fps or int(timeline.get("fps", 24) or 24)
    name = args.name or str(timeline.get("episode") or timeline.get("title") or "AI草稿")

    drafts = args.drafts or default_drafts_dir()
    if not drafts:
        die("未找到剪映草稿目录，请用 --drafts 指定（剪映-全局设置-草稿位置）")

    # 预先解析每个镜的素材与时长规划
    plan = []
    cursor = 0.0
    missing = []
    for s in shots:
        mat_path = find_material(s, args.video_dir, timeline_dir)
        if not mat_path:
            missing.append(s.get("shot_id", "?"))
            continue
        target = float(s.get("duration") or 0)
        if target <= 0:
            # 没写时长就用素材实际时长
            try:
                material = VideoMaterial(mat_path)
                target = material.duration / 1_000_000
            except Exception:
                target = 3.0
        plan.append((s, mat_path, cursor, target))
        cursor += target

    print("=== 组装计划 ===")
    print("草稿名 :", name)
    print("画布   : %dx%d @ %dfps" % (w, h, fps))
    print("镜头   : %d 个可行, %d 个缺素材" % (len(plan), len(missing)))
    print("总时长 : %.2f s" % cursor)
    if missing:
        print("缺素材 :", ", ".join(missing))
    for s, p, st, du in plan:
        print("  %-6s %6.2f-%-6.2f %5.2fs  %s" % (
            s.get("shot_id", "?"), st, st + du, du, os.path.basename(p)))

    if not plan:
        die("没有任何可用素材，无法生成草稿")
    if args.dry_run:
        print("\n[dry-run] 未写草稿")
        return

    # 生成草稿
    folder = DraftFolder(drafts)
    script = folder.create_draft(name, w, h, fps, allow_replace=args.allow_replace)
    v_track = script.append_track(TrackSpec(TrackType.video, "视频主轨"))

    # 视频主轨
    for s, p, st, du in plan:
        try:
            material = VideoMaterial(p)
            real = material.duration / 1_000_000
            use = min(real, du) if real > 0 else du
            seg = VideoSegment(material, trange_seconds(st, duration=use),
                               source_timerange=trange_seconds(0, duration=use))
            script.add_segment(seg, v_track)
            if abs(use - du) > 0.05:
                print("  [提示] %s 素材 %.2fs ≠ 时间轴 %.2fs，已按实际时长排" % (
                    s.get("shot_id"), real, du))
        except Exception as e:
            print("  [跳过] %s 素材加载失败: %s" % (s.get("shot_id"), e))

    # 字幕轨：优先 SRT，其次台词
    if args.srt:
        if not os.path.isfile(args.srt):
            die("SRT 不存在: " + args.srt)
        script.import_srt(args.srt, "字幕轨")
        print("  字幕轨 ← 导入 %s" % os.path.basename(args.srt))
    else:
        t_track = script.append_track(TrackSpec(TrackType.text, "字幕轨"))
        n = 0
        for s, p, st, du in plan:
            line = (s.get("dialogue") or "").strip()
            if not line:
                continue
            speaker = (s.get("speaker") or "").strip()
            text = ("%s：%s" % (speaker, line)) if speaker else line
            script.add_segment(TextSegment(text, trange_seconds(st, duration=du)), t_track)
            n += 1
        print("  字幕轨 ← 台词 %d 条" % n)

    # 配音轨
    if args.audio:
        if not os.path.isfile(args.audio):
            die("配音不存在: " + args.audio)
        a_track = script.append_track(TrackSpec(TrackType.audio, "配音轨"))
        amat = AudioMaterial(args.audio)
        a_dur = amat.duration / 1_000_000
        script.add_segment(AudioSegment(amat, trange_seconds(0, duration=a_dur)), a_track)
        print("  配音轨 ← %s (%.2fs)" % (os.path.basename(args.audio), a_dur))

    # BGM 轨
    if args.bgm:
        if not os.path.isfile(args.bgm):
            die("BGM 不存在: " + args.bgm)
        b_track = script.append_track(TrackSpec(TrackType.audio, "BGM轨"))
        bmat = AudioMaterial(args.bgm)
        b_dur = bmat.duration / 1_000_000
        use = min(b_dur, cursor)
        script.add_segment(
            AudioSegment(bmat, trange_seconds(0, duration=use), volume=args.bgm_volume),
            b_track,
        )
        print("  BGM轨  ← %s (%.2fs, 音量 %.2f)" % (
            os.path.basename(args.bgm), use, args.bgm_volume))

    script.save()
    draft_dir = os.path.join(drafts, name)
    print("\n[完成] 草稿已生成: " + draft_dir)
    print("打开方式：剪映里进入任一草稿再退出（或重启剪映）刷新列表，找到「%s」。" % name)
    print("注意：剪映 7+ 不支持脚本自动导出，请在剪映内手动点导出。")


if __name__ == "__main__":
    main()