#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""镜头质检器（必须用 E:/ComfyUI/venv/Scripts/python.exe 跑，需要 av + numpy）

判据（P24 §三 验收门）：
  G2 真运动：相邻帧差均值 >= 0.30 且首末帧差 >= 1.5
  G3 不出画：末帧左右边带方差不得低于首帧的 55%
  G1 帧数对齐：帧数必须等于时间轴要求
用法：python _qa_check.py <mp4> [要求帧数]
"""
import os
import sys

import av
import numpy as np


def qa(path, want=None):
    fr = [f.to_ndarray(format="gray").astype(np.float32) for f in av.open(path).decode(video=0)]
    n = len(fr)

    def d(i, j):
        return float(np.abs(fr[i] - fr[j]).mean())

    step = [d(i, i + 1) for i in range(0, n - 1, 6)]
    m_step, m_ends = sum(step) / len(step), d(0, n - 1)

    def edge_std(a):
        h, w = a.shape
        return float(np.concatenate([a[:, : w // 6].ravel(), a[:, -w // 6:].ravel()]).std())

    e0, e1 = edge_std(fr[0]), edge_std(fr[-1])
    hollow = e1 < e0 * 0.55

    g1 = (want is None) or (n == want)
    g2 = m_step >= 0.30 and m_ends >= 1.5
    g3 = not hollow
    ok = g1 and g2 and g3

    name = os.path.basename(path)
    print("%-22s %3d帧%s | 相邻帧差%5.2f | 首末%6.2f | 边带%5.2f→%5.2f %s | %s" % (
        name, n, ("" if want is None else "(要%d)" % want),
        m_step, m_ends, e0, e1, "出画!" if hollow else "在画",
        "PASS" if ok else "FAIL"))
    if not g1:
        print("    G1 帧数不对齐")
    if not g2:
        print("    G2 运动不足（疑似滑片）")
    if not g3:
        print("    G3 主体出画")
    return ok


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("用法: _qa_check.py <mp4> [帧数]")
        sys.exit(2)
    want = int(args[1]) if len(args) > 1 else None
    sys.exit(0 if qa(args[0], want) else 1)
