#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
preprocess2 —— 源帧预处理 v2：自动去水印 + 整衣染色
==================================================
v1 教训：阈值染色斑驳（褶皱空洞）、锚点插值去水印漏检。
v2 方案：
1) 水印自动检测：水印=「短时间静止(与±10帧中值差小) 且 比中值亮 且 灰白」，
   舞动的人体差值大被自然排除 → 膨胀后 cv2.inpaint 干净抹除
2) 整衣染色：亮低饱和掩膜 → 形态学闭运算(填褶皱) → 膨胀(盖渐变边) →
   整块染海军蓝（按原亮度缩放，保留明暗层次）→ img2img 底图自带蓝西装

用法：python preprocess2.py
产出：frames_wm/（去水印）、frames_tint2/（去水印+染色）、_clean_check2.jpg
"""
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "frames")
WM = os.path.join(HERE, "frames_wm")
TINT = os.path.join(HERE, "frames_tint2")
N = 194
WIN = 10          # 中值窗口半径（帧）

# 水印检测参数
DIFF_MAX = 18     # 与中值最大通道差（小=静止）
BRIGHT_MIN = 12   # 比中值亮至少多少（灰度）
SAT_MAX = 60      # 灰白判定 max-min

# 染色参数
V_MIN, SAT2_MAX = 165, 50
NAVY_SCALE = (0.176, 0.227, 0.431)   # 255 白 → (45,58,110) 深海军蓝


def imread_u(p):
    """cv2 读图（Windows 中文路径兼容）"""
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_u(p, img):
    """cv2 写图（Windows 中文路径兼容）"""
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(p)
    return ok


def load_all():
    frames = []
    for i in range(1, N + 1):
        p = os.path.join(SRC, "f%03d.png" % i)
        frames.append(imread_u(p))
    return frames


def watermark_pass(frames):
    """返回去水印后的帧列表"""
    os.makedirs(WM, exist_ok=True)
    out = []
    gray_all = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    kernel = np.ones((9, 9), np.uint8)
    last_mask = None
    for i in range(N):
        lo, hi = max(0, i - WIN), min(N, i + WIN + 1)
        med = np.median(np.stack(gray_all[lo:hi]), axis=0).astype(np.uint8)
        f = frames[i]
        diff = np.abs(f.astype(np.int16) - cv2.cvtColor(med, cv2.COLOR_GRAY2BGR).astype(np.int16)).max(axis=2)
        g = gray_all[i].astype(np.int16)
        mx = f.max(axis=2).astype(np.int16)
        mn = f.min(axis=2).astype(np.int16)
        mask = ((diff <= DIFF_MAX) & (g > med.astype(np.int16) + BRIGHT_MIN)
                & ((mx - mn) <= SAT_MAX)).astype(np.uint8) * 255
        if last_mask is None or mask.sum() / 255 >= 50:
            last_mask = mask
        use = last_mask.copy()
        use = cv2.dilate(use, kernel, iterations=2)
        cleaned = cv2.inpaint(f, use, 4, cv2.INPAINT_TELEA)
        imwrite_u(os.path.join(WM, "f%03d.png" % (i + 1)), cleaned)
        out.append(cleaned)
        if (i + 1) % 40 == 0:
            print("  水印 %d/%d" % (i + 1, N))
    print("水印抹除完成 → frames_wm/")
    return out


def tint_pass(frames):
    os.makedirs(TINT, exist_ok=True)
    kernel = np.ones((9, 9), np.uint8)
    scale = np.array(NAVY_SCALE, dtype=np.float32)
    for i, f in enumerate(frames):
        mx = f.max(axis=2).astype(np.int16)
        mn = f.min(axis=2).astype(np.int16)
        mask = ((mx >= V_MIN) & ((mx - mn) <= SAT2_MAX)).astype(np.uint8) * 255
        # 闭运算填褶皱空洞，再膨胀盖渐变边
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)
        mask = cv2.dilate(mask, kernel, iterations=2)
        m3 = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR).astype(bool)
        out = (f.astype(np.float32) * scale).clip(0, 255).astype(np.uint8)
        res = f.copy()
        res[m3] = out[m3]
        imwrite_u(os.path.join(TINT, "f%03d.png" % (i + 1)), res)
        if (i + 1) % 40 == 0:
            print("  染色 %d/%d" % (i + 1, N))
    print("整衣染色完成 → frames_tint2/")


def check_sheet():
    idxs = [1, 17, 33, 49, 65, 90, 97, 113, 135, 155, 177, 193]
    cols, rows, w, h = 4, 3, 376, 280
    sheet = Image.new("RGB", (w * cols, h * rows), (30, 30, 30))
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
    sheet.save(os.path.join(HERE, "_clean_check2.jpg"), quality=88)
    print("验收图 → _clean_check2.jpg")


if __name__ == "__main__":
    frames = load_all()
    bad = [i + 1 for i, f in enumerate(frames) if f is None]
    if bad:
        raise SystemExit("读图失败帧: %s" % bad[:5])
    print("已加载 %d 帧" % len(frames))
    frames = watermark_pass(frames)
    tint_pass(frames)
    check_sheet()
