#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
preprocess3 —— 源帧预处理 v3：模板匹配去水印 + 整衣染色(BGR修正+护脸)
===================================================================
v2 三 bug：① NAVY_SCALE 写成 RGB 顺序但 cv2 是 BGR → 染成棕红；
② 脸部高光(暖光下低饱和)被染色 → 需大连通域过滤；
③ 中值检测对静止水印失效 → 改 cv2.matchTemplate 模板匹配。

用法：python preprocess3.py
产出：frames_wm3/（去水印）、frames_tint3/（去水印+染蓝）、_clean_check3.jpg
"""
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "frames")
WM = os.path.join(HERE, "frames_wm3")
TINT = os.path.join(HERE, "frames_tint3")
N = 194

# 模板：f001 水印块（抖音 AI创作 / ID:...），坐标由实测裁剪确认
TPL_X, TPL_Y, TPL_W, TPL_H = 548, 500, 177, 50
MATCH_TH = 0.45          # 匹配置信阈值，低于则放弃该帧（交给img2img重绘）

# 染色参数（BGR 顺序！）
NAVY_BGR = (0.431, 0.227, 0.176)   # B=0.431 G=0.227 R=0.176 → 255白=(45,58,110)海军蓝
V_MIN, SAT2_MAX = 170, 35          # 更严饱和度：护脸（暖光下皮肤饱和40-70）
MIN_AREA = 1500                    # 连通域最小面积：剔脸部/牙齿小斑块


def imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_u(p, img):
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(p)
    return ok


def watermark_pass(frames, template):
    os.makedirs(WM, exist_ok=True)
    miss = []
    for i, f in enumerate(frames):
        res = cv2.matchTemplate(f, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score >= MATCH_TH:
            x, y = loc
            mask = np.zeros(f.shape[:2], np.uint8)
            x0, y0 = max(0, x - 8), max(0, y - 8)
            x1 = min(f.shape[1], x + TPL_W + 8)
            y1 = min(f.shape[0], y + TPL_H + 8)
            mask[y0:y1, x0:x1] = 255
            mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)
            f = cv2.inpaint(f, mask, 4, cv2.INPAINT_TELEA)
            frames[i] = f
        else:
            miss.append(i + 1)
        imwrite_u(os.path.join(WM, "f%03d.png" % (i + 1)), f)
        if (i + 1) % 40 == 0:
            print("  水印 %d/%d" % (i + 1, N))
    print("水印完成 → frames_wm3/（未检出 %d 帧: %s）" % (len(miss), miss[:12]))
    return frames


def tint_pass(frames):
    os.makedirs(TINT, exist_ok=True)
    scale = np.array(NAVY_BGR, dtype=np.float32)
    k = np.ones((7, 7), np.uint8)
    # Haar 人脸检测：染衣前先把脸+下巴+胡子区整体排除（假胡子在暗光下是亮低饱和灰，阈值拦不住）
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    no_face = 0
    for i, f in enumerate(frames):
        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
        face_excl = np.zeros(f.shape[:2], np.uint8)
        if len(faces):
            fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
            x0 = max(0, int(fx - 0.35 * fw)); x1 = min(f.shape[1], int(fx + 1.35 * fw))
            y0 = max(0, int(fy - 0.35 * fh)); y1 = min(f.shape[0], int(fy + 1.75 * fh))
            face_excl[y0:y1, x0:x1] = 255
        else:
            no_face += 1
        mx = f.max(axis=2).astype(np.int16)
        mn = f.min(axis=2).astype(np.int16)
        mask = ((mx >= V_MIN) & ((mx - mn) <= SAT2_MAX)).astype(np.uint8) * 255
        # 先腐蚀切断「下巴高光→衣领」细桥，再取大连通域（衣服/手套），
        # 剔除牙齿/脸部高光小斑块；最后膨胀还原
        mask_e = cv2.erode(mask, k, iterations=2)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask_e, 8)
        keep = np.zeros_like(mask)
        for c in range(1, n):
            if stats[c, cv2.CC_STAT_AREA] >= MIN_AREA:
                keep[labels == c] = 255
        # 闭运算填褶皱 + 膨胀盖渐变边
        keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, k, iterations=2)
        keep = cv2.dilate(keep, k, iterations=2)
        # 人脸区整体排除
        keep = cv2.bitwise_and(keep, cv2.bitwise_not(face_excl))
        m3 = cv2.cvtColor(keep, cv2.COLOR_GRAY2BGR).astype(bool)
        out = (f.astype(np.float32) * scale).clip(0, 255).astype(np.uint8)
        res = f.copy()
        res[m3] = out[m3]
        imwrite_u(os.path.join(TINT, "f%03d.png" % (i + 1)), res)
        if (i + 1) % 40 == 0:
            print("  染色 %d/%d" % (i + 1, N))
    print("整衣染色完成 → frames_tint3/（未检出人脸 %d 帧）" % no_face)


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
    sheet.save(os.path.join(HERE, "_clean_check3.jpg"), quality=88)
    print("验收图 → _clean_check3.jpg")


if __name__ == "__main__":
    frames = [imread_u(os.path.join(SRC, "f%03d.png" % i)) for i in range(1, N + 1)]
    bad = [i + 1 for i, f in enumerate(frames) if f is None]
    if bad:
        raise SystemExit("读图失败帧: %s" % bad[:5])
    print("已加载 %d 帧" % len(frames))
    template = frames[0][TPL_Y:TPL_Y + TPL_H, TPL_X:TPL_X + TPL_W].copy()
    frames = watermark_pass(frames, template)
    tint_pass(frames)
    check_sheet()
