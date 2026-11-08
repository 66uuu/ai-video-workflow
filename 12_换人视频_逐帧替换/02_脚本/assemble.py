#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
assemble —— 把换人后的帧拼回视频并铺原音频
=============================================
用法：
  python assemble.py            # 拼 24fps + 铺音频，输出 final/换人成片.mp4
  python assemble.py --hd       # 额外 2x 放大到 1504x1120（高清）
  python assemble.py --cmp      # 额外生成 原图vs换人 对比图（首/中/尾帧）
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(HERE, "frames")
SWAPPED = os.path.join(HERE, "swapped")
FINAL = os.path.join(HERE, "final")
AUDIO = os.path.join(HERE, "audio.m4a")
FF = (r"C:\Users\<USER>\AppData\Local\Microsoft\WinGet\Packages"
      r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
      r"\ffmpeg-9.0.1-full_build\bin\ffmpeg")

N = 194  # 总帧数


def fps_file_list():
    """生成连续帧列表文件 list.txt（跳过缺失帧用上一帧补，保证连续）"""
    lst = os.path.join(HERE, "list.txt")
    lines = []
    prev = None
    for i in range(1, N + 1):
        p = os.path.join(SWAPPED, "f%03d.png" % i)
        if os.path.isfile(p):
            prev = p
        if prev is None:
            continue
        lines.append("file '%s'" % prev.replace("/", "\\"))
    with open(lst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("帧列表：%d 段（缺帧用前帧补）" % len(lines))
    return lst


def assemble(hd=False):
    os.makedirs(FINAL, exist_ok=True)
    lst = fps_file_list()
    raw = os.path.join(FINAL, "raw.mp4")
    vf = "scale=1504:1120:flags=lanczos" if hd else "null"
    # 先拼无声视频
    cmd = [FF, "-y", "-r", "24", "-f", "concat", "-safe", "0", "-i", lst,
           "-vf", vf, "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", raw]
    if not hd:
        cmd.remove("-vf"); cmd.remove("null")
    print("拼接中…")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("拼接失败：%s" % (r.stderr or "")[-500:])
    # 铺音频
    out = os.path.join(FINAL, "换人成片" + ("_HD.mp4" if hd else ".mp4"))
    cmd2 = [FF, "-y", "-i", raw, "-i", AUDIO, "-c:v", "copy", "-c:a", "aac",
            "-b:a", "192k", "-shortest", out]
    r2 = subprocess.run(cmd2, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r2.returncode != 0:
        raise RuntimeError("铺音频失败：%s" % (r2.stderr or "")[-500:])
    os.remove(raw)
    print("成品：%s" % out)
    return out


def compare():
    """原图 vs 换人 三帧对比（竖排），方便肉眼验收"""
    from PIL import Image
    out = os.path.join(FINAL, "对比_原vs换人.png")
    idxs = [5, 90, 185]
    pairs = []
    for i in idxs:
        a = os.path.join(FRAMES, "f%03d.png" % i)
        b = os.path.join(SWAPPED, "f%03d.png" % i)
        if os.path.isfile(a) and os.path.isfile(b):
            pairs.append((Image.open(a).convert("RGB"), Image.open(b).convert("RGB")))
    if not pairs:
        print("无可比帧")
        return
    w = max(p[0].width for p in pairs)
    h = max(p[0].height for p in pairs)
    sheet = Image.new("RGB", (w * 2, h * len(pairs)), (255, 255, 255))
    for r, (a, b) in enumerate(pairs):
        sheet.paste(a, (0, r * h))
        sheet.paste(b, (w, r * h))
    sheet.save(out)
    print("对比图：%s" % out)


if __name__ == "__main__":
    hd = "--hd" in sys.argv
    cmp = "--cmp" in sys.argv
    assemble(hd=hd)
    if cmp:
        compare()
