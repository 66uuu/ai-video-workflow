# -*- coding: utf-8 -*-
"""水印乱码残留检测器：扫 swapped/ 全片，找边缘带里的「白字条」连通域。
水印特征：白(>150)、聚集成横条(高宽比0.08-0.7)、贴画面边缘、有硬边。
输出嫌疑帧列表（人眼复核用）。"""
import os, cv2, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
SW = os.path.join(HERE, "swapped")
def imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)

H, W = 560, 752
def edge_band(y, x):
    return y < 72 or y > 428 or x < 58 or x > 694

suspects = []
for i in range(1, 195):
    f = imread_u(os.path.join(SW, "f%03d.png" % i))
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    m = (g > 150).astype(np.uint8)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(m, 8)
    hits = []
    for c in range(1, n):
        x, y, w, h, area = stats[c]
        if area < 90 or area > 9000:
            continue
        if not (0.06 <= h / max(w, 1) <= 0.75):   # 横条
            continue
        # 团必须大部分在边缘带
        cx, cy = cents[c]
        if not edge_band(cy, cx):
            continue
        # 硬边：团边界梯度大（文字特征），软团（光晕/睡衣）梯度小
        x0, y0 = max(0, x - 2), max(0, y - 2)
        x1, y1 = min(W, x + w + 2), min(H, y + h + 2)
        patch = g[y0:y1, x0:x1].astype(np.float32)
        if patch.size == 0:
            continue
        gx = np.abs(np.diff(patch, axis=1)).mean()
        if gx < 6:    # 太软，不是文字
            continue
        hits.append((x, y, w, h, area))
    if hits:
        suspects.append((i, hits))
print("嫌疑帧 %d 个：" % len(suspects))
for i, hits in suspects:
    print("f%03d: %d 个团 %s" % (i, len(hits), [(x, y, w, h) for x, y, w, h, a in hits[:4]]))
