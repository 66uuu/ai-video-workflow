#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""preprocess6_wm —— 单帧底图修补：漂移水印边缘四区 inpaint + 整衣染色
=====================================================================
背景：抖音 ID 水印在 8 秒里从顶部→右侧→底部→左下→右下循环漂移，preprocess5
只处理了右下「AI创作」块和左上「AI生成」标签，漂移块没处理 → img2img 把
水印文字结构锚住重绘成了幻觉乱码（MiniMax/KOBE/Hit... 等，约 20+ 帧）。

v6 策略（只修嫌疑帧，不动全片）：
① 在 frames_wm5（已去两个固定水印）基础上，对【顶部 y<65 / 底部 y>415 /
   左下 x<60&y>415 / 右下 x>690&y>415】四个水印高发区做白字检测：
   灰度>150 + 横条比例 0.06-0.75 + 面积 90-9000 + 硬边(横向梯度>6)
② 命中区域膨胀 8px 后 inpaint(TELEA)
③ 复用 v5 染色逻辑整衣染海军蓝（erode1/MIN_AREA800/无兜底/面积上限25%）
输出：tint6/f%03d.png（只生成被指定的嫌疑帧）
"""
import os
import sys
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WM5 = os.path.join(HERE, "frames_wm5")
OUT = os.path.join(HERE, "tint6")
N = 194

NAVY_BGR = (0.431, 0.227, 0.176)
V_MIN, SAT2_MAX = 170, 35
MIN_AREA = 800
MAX_MASK_RATIO = 0.25


def imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_u(p, img):
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(p)
    return ok


def in_wm_zone(y, x, h=560, w=752):
    """水印高发四区（避开人物活动的中段，防误伤白手套/白睡衣/床单）"""
    return y < 65 or y > 415 or (x < 60 and y > 415) or (x > 690 and y > 415)


def strip_wm(f):
    """边缘四区白字检测 + inpaint，返回处理后的帧"""
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    m = (g > 150).astype(np.uint8)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(m, 8)
    mask = np.zeros(f.shape[:2], np.uint8)
    hits = 0
    for c in range(1, n):
        x, y, w, h, area = stats[c]
        if area < 90 or area > 9000:
            continue
        if not (0.06 <= h / max(w, 1) <= 0.75):
            continue
        cx, cy = cents[c]
        if not in_wm_zone(cy, cx):
            continue
        x0, y0 = max(0, x - 2), max(0, y - 2)
        x1, y1 = min(f.shape[1], x + w + 2), min(f.shape[0], y + h + 2)
        patch = g[y0:y1, x0:x1].astype(np.float32)
        if patch.size and np.abs(np.diff(patch, axis=1)).mean() < 6:
            continue  # 软团（光晕/睡衣）不碰
        mask[max(0, y - 8):min(f.shape[0], y + h + 8),
             max(0, x - 8):min(f.shape[1], x + w + 8)] = 255
        hits += 1
    if hits:
        mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)
        f = cv2.inpaint(f, mask, 5, cv2.INPAINT_TELEA)
    return f, hits


def tint(f):
    """v5 同款整衣染色（单帧版，无邻帧兜底）"""
    scale = np.array(NAVY_BGR, dtype=np.float32)
    k = np.ones((7, 7), np.uint8)
    gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    faces = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    ).detectMultiScale(gray, 1.05, 3, minSize=(40, 40))
    face_excl = np.zeros(f.shape[:2], np.uint8)
    if len(faces):
        fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
        x0 = max(0, int(fx - 0.35 * fw)); x1 = min(f.shape[1], int(fx + 1.35 * fw))
        y0 = max(0, int(fy - 0.35 * fh)); y1 = min(f.shape[0], int(fy + 1.75 * fh))
        face_excl[y0:y1, x0:x1] = 255
    mx = f.max(axis=2).astype(np.int16)
    mn = f.min(axis=2).astype(np.int16)
    mask = ((mx >= V_MIN) & ((mx - mn) <= SAT2_MAX)).astype(np.uint8) * 255
    mask_e = cv2.erode(mask, k, iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask_e, 8)
    keep = np.zeros_like(mask)
    for c in range(1, n):
        if stats[c, cv2.CC_STAT_AREA] >= MIN_AREA:
            keep[labels == c] = 255
    keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, k, iterations=2)
    keep = cv2.dilate(keep, k, iterations=1)
    keep = cv2.bitwise_and(keep, cv2.bitwise_not(face_excl))
    if keep.sum() // 255 > MAX_MASK_RATIO * f.shape[0] * f.shape[1]:
        return f, "skip"
    m3 = cv2.cvtColor(keep, cv2.COLOR_GRAY2BGR).astype(bool)
    out = (f.astype(np.float32) * scale).clip(0, 255).astype(np.uint8)
    res = f.copy()
    res[m3] = out[m3]
    return res, "ok"


if __name__ == "__main__":
    idxs = [int(x) for x in sys.argv[1].split(",") if x.strip()]
    os.makedirs(OUT, exist_ok=True)
    for i in idxs:
        f = imread_u(os.path.join(WM5, "f%03d.png" % i))
        f, hits = strip_wm(f)
        res, st = tint(f)
        imwrite_u(os.path.join(OUT, "f%03d.png" % i), res)
        print("f%03d: 去水印团 %d 个，染色 %s" % (i, hits, st))
    print("完成 %d 帧 → tint6/" % len(idxs))
