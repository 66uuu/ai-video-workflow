#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
preprocess5 —— 源帧预处理 v5（修 v3/v4 染色管线的 3 个 bug）
====================================================================
v3/v4 三 bug（194 帧全片返工级别）：
① erode 2 次 + MIN_AREA 1500 把细手臂/袖子连通域切碎 → f005 袖子大面积白；
② 小掩膜用 prev_keep 膨胀兜底 → f090/f145 盖出巨大蓝块（人物糊了）；
③ 模糊大动态帧掩膜选太大（白睡衣运动模糊连成片）→ 整个人被染蓝。

v5 修正：
① erode 1 次 + MIN_AREA 800：保住手臂/袖子细条；
② 删除 prev_keep 兜底：宁可漏染也不乱盖；
③ 掩膜面积 > 画面 25% 直接放弃染色（该帧交给提示词+IP-Adapter）；
④ Haar 放宽（1.05/3/minSize40）多捞回几张脸做排除；
⑤ 左上「AI 生成」标签实测全帧固定 x10-110 y12-51 → 固定矩形 inpaint，不匹配；
⑥ 右下「AI创作 ID」块固定 (548,500) → matchTemplate 阈值降到 0.4；
⑦ blur_map 改在【原帧】上算（v4 在 inpaint 后帧上算 → 全 194 帧误判 <130）；
⑧ 漂移的「抖音」logo 块不追了：3 张验证帧实测被 img2img 重绘自然抹掉。

用法：python preprocess5.py
产出：frames_wm5/（去水印）、frames_tint5/（去水印+染蓝）、_blur_map.json（原帧清晰度）
"""
import os
import json
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "frames")
WM = os.path.join(HERE, "frames_wm5")
TINT = os.path.join(HERE, "frames_tint5")
N = 194

# 右下「AI创作 ID:xxx」块（实测全帧固定在 548,500）
WM_X, WM_Y, WM_W, WM_H = 548, 500, 177, 50
MATCH_TH = 0.40
# 左上「AI 生成」标签（实测全帧固定 x10-110, y12-51）→ 固定矩形直接涂
TL_X, TL_Y, TL_W, TL_H = 6, 8, 118, 54

# 染色参数（BGR 顺序！）
NAVY_BGR = (0.431, 0.227, 0.176)   # 255白→(45,58,110) 海军蓝
V_MIN, SAT2_MAX = 170, 35
MIN_AREA = 800                     # v3=1500 切碎手臂，v5 降到 800
MAX_MASK_RATIO = 0.25              # 掩膜超画面 25% 放弃染色（防模糊帧整片蓝）


def imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_u(p, img):
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(p)
    return ok


def blur_map_pass(frames):
    """在原帧上算 Laplacian 方差（v4 的错误：在 inpaint 后帧上算，水印锐利边缘
    被抹掉导致方差从 254 暴跌到 109，全片误判为模糊帧）。"""
    blur_map = {}
    for i, f in enumerate(frames):
        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        blur_map[i + 1] = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1)
    with open(os.path.join(HERE, "_blur_map.json"), "w") as fp:
        json.dump(blur_map, fp)
    vals = sorted(blur_map.values())
    print("清晰度图 → _blur_map.json（min=%.1f 中位=%.1f max=%.1f，方差<130 的帧：%d）"
          % (vals[0], vals[len(vals) // 2], vals[-1],
             sum(1 for v in blur_map.values() if v < 130)))
    return blur_map


def watermark_pass(frames, template):
    os.makedirs(WM, exist_ok=True)
    miss = []
    for i, f in enumerate(frames):
        mask = np.zeros(f.shape[:2], np.uint8)
        # 右下漂移检测（保险：虽然实测固定，仍匹配兜底）
        res = cv2.matchTemplate(f, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score >= MATCH_TH:
            x, y = loc
            x0, y0 = max(0, x - 8), max(0, y - 8)
            x1 = min(f.shape[1], x + WM_W + 8)
            y1 = min(f.shape[0], y + WM_H + 8)
            mask[y0:y1, x0:x1] = 255
        else:
            miss.append(i + 1)
        # 左上「AI 生成」固定标签：直接涂（不匹配，实测全帧同位置）
        mask[TL_Y:TL_Y + TL_H, TL_X:TL_X + TL_W] = 255
        mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)
        f = cv2.inpaint(f, mask, 4, cv2.INPAINT_TELEA)
        frames[i] = f
        imwrite_u(os.path.join(WM, "f%03d.png" % (i + 1)), f)
        if (i + 1) % 40 == 0:
            print("  水印 %d/%d" % (i + 1, N))
    print("水印完成 → frames_wm5/（右下块未检出 %d 帧: %s）" % (len(miss), miss[:12]))
    return frames


def tint_pass(frames):
    os.makedirs(TINT, exist_ok=True)
    scale = np.array(NAVY_BGR, dtype=np.float32)
    k = np.ones((7, 7), np.uint8)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    no_face = 0
    skipped = 0
    areas = []
    for i, f in enumerate(frames):
        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.05, 3, minSize=(40, 40))
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
        # v5：只腐蚀 1 次（v3 腐蚀 2 次把手臂细桥切断）
        mask_e = cv2.erode(mask, k, iterations=1)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask_e, 8)
        keep = np.zeros_like(mask)
        for c in range(1, n):
            if stats[c, cv2.CC_STAT_AREA] >= MIN_AREA:
                keep[labels == c] = 255
        keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, k, iterations=2)
        keep = cv2.dilate(keep, k, iterations=1)
        keep = cv2.bitwise_and(keep, cv2.bitwise_not(face_excl))
        area_px = int(keep.sum() // 255)
        areas.append(area_px)
        frame_px = f.shape[0] * f.shape[1]
        if area_px > MAX_MASK_RATIO * frame_px:
            # v5：掩膜失控（模糊帧白睡衣连成片）→ 放弃染色，交给 IPA+提示词
            skipped += 1
            imwrite_u(os.path.join(TINT, "f%03d.png" % (i + 1)), f)
            if (i + 1) % 40 == 0:
                print("  染色 %d/%d" % (i + 1, N))
            continue
        m3 = cv2.cvtColor(keep, cv2.COLOR_GRAY2BGR).astype(bool)
        out = (f.astype(np.float32) * scale).clip(0, 255).astype(np.uint8)
        res = f.copy()
        res[m3] = out[m3]
        imwrite_u(os.path.join(TINT, "f%03d.png" % (i + 1)), res)
        if (i + 1) % 40 == 0:
            print("  染色 %d/%d" % (i + 1, N))
    areas_s = sorted(areas)
    print("整衣染色完成 → frames_tint5/（未检出人脸 %d 帧，掩膜超25%%放弃染色 %d 帧）"
          % (no_face, skipped))
    print("掩膜面积分布: min=%d p10=%d 中位=%d p90=%d max=%d"
          % (areas_s[0], areas_s[len(areas_s) // 10], areas_s[len(areas_s) // 2],
             areas_s[len(areas_s) * 9 // 10], areas_s[-1]))


if __name__ == "__main__":
    frames = [imread_u(os.path.join(SRC, "f%03d.png" % i)) for i in range(1, N + 1)]
    bad = [i + 1 for i, f in enumerate(frames) if f is None]
    if bad:
        raise SystemExit("读图失败帧: %s" % bad[:5])
    print("已加载 %d 帧" % len(frames))
    blur_map_pass(frames)  # 先算清晰度（必须在 watermark_pass 原地修改前）
    template = frames[0][WM_Y:WM_Y + WM_H, WM_X:WM_X + WM_W].copy()
    frames = watermark_pass(frames, template)
    tint_pass(frames)
    print("全部完成")
