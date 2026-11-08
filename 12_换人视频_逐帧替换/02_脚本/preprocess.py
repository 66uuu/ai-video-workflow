#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
preprocess —— 源帧预处理：逐帧去漂浮水印 + 白衣预染海军蓝
========================================================
1) 水印：抖音水印 8 秒内漂浮经过 ~7 个区域。手工标定 30 个锚点帧的水印框，
   逐帧线性插值出该帧水印位置，ffmpeg delogo 抹掉 → frames_clean2/
2) 染色：原人物穿白色睡衣，img2img 低 denoise 会把白色带进结果（西装变白）。
   把「亮且低饱和」的像素预染成深海军蓝 → frames_tint/
   这样 img2img 底图本身就是深蓝西装，低 denoise 也不会跑色。

用法：python preprocess.py
产出：frames_clean2/（去水印）、frames_tint/（去水印+染色）、_clean_check.jpg（验收图）
"""
import os
import subprocess
import shutil
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "frames")
CLEAN2 = os.path.join(HERE, "frames_clean2")
TINT = os.path.join(HERE, "frames_tint")
FF = (r"C:\Users\<USER>\AppData\Local\Microsoft\WinGet\Packages"
      r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
      r"\ffmpeg-9.0.1-full_build\bin\ffmpeg")
N = 194

# 锚点帧 → 水印 bbox (x, y, w, h)，已含外扩余量（坐标基于 752x560）
ANCHORS = [
    (1,   388, 316, 184, 90),
    (33,  388, 316, 184, 90),
    (37,  388, 316, 184, 90),
    (40,  378, 322, 184, 88),
    (43,  416, 326, 156, 84),
    (46,  586, 296, 148, 88),
    (49,  556, 156, 168, 92),
    (52,  8,   86,  192, 96),
    (56,  10,  106, 192, 96),
    (60,  8,   136, 194, 96),
    (65,  12,  164, 192, 92),
    (81,  6,   186, 194, 92),
    (85,  6,   68,  192, 96),
    (90,  4,   236, 198, 100),
    (93,  6,   116, 196, 100),
    (97,  526, 38,  192, 84),
    (113, 526, 18,  196, 84),
    (129, 540, 28,  188, 84),
    (135, 496, 22,  216, 88),
    (140, 496, 22,  216, 88),
    (150, 526, 18,  206, 86),
    (155, 376, 486, 188, 72),
    (158, 546, 496, 186, 62),
    (161, 586, 476, 168, 76),
    (177, 586, 466, 170, 82),
    (180, 536, 486, 194, 72),
    (186, 486, 12,  226, 92),
    (193, 16,  476, 198, 80),
    (194, 16,  476, 198, 80),
]

# 亮且低饱和 → 深海军蓝（白色睡衣 → 蓝西装底）
NAVY_SCALE = (0.176, 0.227, 0.431)   # 255 白 → (45,58,110)
V_MIN, SAT_MAX = 170, 48


def bbox_at(i):
    """线性插值出第 i 帧的水印框"""
    if i <= ANCHORS[0][0]:
        return ANCHORS[0][1:]
    for k in range(len(ANCHORS) - 1):
        a, b = ANCHORS[k], ANCHORS[k + 1]
        if a[0] <= i <= b[0]:
            t = (i - a[0]) / max(1, (b[0] - a[0]))
            return tuple(round(a[j + 1] + t * (b[j + 1] - a[j + 1])) for j in range(4))
    return ANCHORS[-1][1:]


def clamp_bbox(x, y, w, h):
    x = max(2, min(x, 752 - w - 2))
    y = max(2, min(y, 560 - h - 2))
    return x, y, w, h


def delogo_pass():
    os.makedirs(CLEAN2, exist_ok=True)
    for i in range(1, N + 1):
        src = os.path.join(SRC, "f%03d.png" % i)
        dst = os.path.join(CLEAN2, "f%03d.png" % i)
        x, y, w, h = clamp_bbox(*bbox_at(i))
        vf = "delogo=x=%d:y=%d:w=%d:h=%d" % (x, y, w, h)
        r = subprocess.run([FF, "-y", "-i", src, "-vf", vf, "-q:v", "2", dst],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print("[fail] delogo f%03d: %s" % (i, (r.stderr or "")[-200:]))
            shutil.copyfile(src, dst)
    print("delogo 完成 → frames_clean2/")


def tint_pass():
    import numpy as np
    os.makedirs(TINT, exist_ok=True)
    lo = np.array([int(255 * c) for c in NAVY_SCALE], dtype=np.uint8)
    for i in range(1, N + 1):
        src = os.path.join(CLEAN2, "f%03d.png" % i)
        dst = os.path.join(TINT, "f%03d.png" % i)
        arr = np.asarray(Image.open(src).convert("RGB")).astype(np.int16)
        mx = arr.max(axis=2)
        mn = arr.min(axis=2)
        mask = (mx >= V_MIN) & ((mx - mn) <= SAT_MAX)
        # 目标色 = 原亮度 × 海军蓝比例（保持明暗层次）
        out = (arr * np.array(NAVY_SCALE)).astype(np.int16)
        arr[mask] = out[mask]
        Image.fromarray(arr.astype(np.uint8)).save(dst)
    print("tint 完成 → frames_tint/")


def check_sheet():
    idxs = [1, 17, 33, 49, 65, 90, 97, 113, 135, 155, 177, 193]
    cols, rows, w, h = 4, 3, 376, 280
    sheet = Image.new("RGB", (w * cols, h * rows), (30, 30, 30))
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    for k, i in enumerate(idxs):
        p = os.path.join(TINT, "f%03d.png" % i)
        if not os.path.isfile(p):
            continue
        im = Image.open(p).convert("RGB").resize((w, h))
        x, y = (k % cols) * w, (k // cols) * h
        sheet.paste(im, (x, y))
        d.rectangle([x + 4, y + 4, x + 90, y + 24], fill=(0, 0, 0))
        d.text((x + 8, y + 8), "f%03d" % i, fill=(255, 255, 0))
    sheet.save(os.path.join(HERE, "_clean_check.jpg"), quality=88)
    print("验收图 → _clean_check.jpg")


if __name__ == "__main__":
    delogo_pass()
    tint_pass()
    check_sheet()
