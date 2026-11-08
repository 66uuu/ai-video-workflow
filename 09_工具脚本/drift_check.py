#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
主体一致性检测（漂移检测）—— 把"人脸身材会变"变成数字
=====================================================================
Wan2.2 TI2V-5B 只"参考"首帧、不"锁定"首帧，误差会随帧数累积。
肉眼看片很累，而且容易漏。这个脚本逐帧量三个量：

  NCC   当前帧与首帧的"结构相似度"（做过位移对齐，所以测的是"变形"不是"走动"）
        1.00 = 完全一致   0.85 以上 = 稳   0.70 以下 = 主体开始变
  ΔRGB  中心区域的 RGB 均值偏移（抓"肤色变白/服装变色/整片变灰"）
  运动   相邻帧差（判断是不是死片）

判读：
  · NCC 末段 >= 0.85   → 一致性好，可用
  · NCC 末段 0.70–0.85 → 轻微漂移，短镜头还行，长镜头会看出来
  · NCC 末段 < 0.70    → 主体明显变形，建议重拍或缩短帧数
  · ΔRGB 持续单向增大  → 色调漂移（常见于低照度 + 高 shift）

用法（必须用 ComfyUI 的 venv，它才有 av）：
  <D盘>\\ComfyUI\\venv\\Scripts\\python.exe drift_check.py 片子.mp4
  ... drift_check.py 片子.mp4 --verbose      # 打印每 10% 的明细
  ... drift_check.py video_i2v\\*.mp4          # 批量，最后出排名

注意：这不是人脸识别。它测的是"画面主体结构相对首帧变了多少"，
对人物、产品、建筑都适用。数值低就代表"变了"，具体变在哪要自己看一眼。
"""
import argparse
import glob
import os
import sys

try:
    import av
    import numpy as np
except ImportError:
    raise SystemExit("缺依赖。请用 ComfyUI 的 python 跑：\n"
                     "  <D盘>\\ComfyUI\\venv\\Scripts\\python.exe drift_check.py xxx.mp4")

WORK_W = 160          # 工作分辨率宽（够用且快）
SEARCH = 24           # 位移搜索半径（工作分辨率像素）
NCC_GOOD, NCC_WARN = 0.85, 0.70


def _resize_block(a, tw):
    """块平均缩放（纯 numpy，无 cv2）。a: HxW float32"""
    h, w = a.shape
    th = max(1, int(round(h * tw / float(w))))
    ys = np.linspace(0, h, th + 1).astype(int)
    xs = np.linspace(0, w, tw + 1).astype(int)
    out = np.empty((th, tw), np.float32)
    for i in range(th):
        for j in range(tw):
            blk = a[ys[i]:max(ys[i] + 1, ys[i + 1]), xs[j]:max(xs[j] + 1, xs[j + 1])]
            out[i, j] = blk.mean() if blk.size else 0.0
    return out


def _ncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    da, db = np.sqrt((a * a).sum()), np.sqrt((b * b).sum())
    if da < 1e-6 or db < 1e-6:
        return 0.0
    return float((a * b).sum() / (da * db))


def _best_ncc(ref, cur, r=SEARCH, step=2):
    """在 ±r 像素内搜索最佳对齐后的 NCC，排除"走动"干扰"""
    h, w = ref.shape
    m = r + 2                      # 中心裁剪，保证各偏移下都取同样大小
    if h <= 2 * m or w <= 2 * m:
        return _ncc(ref, cur)
    core = ref[m:h - m, m:w - m]
    best, bo = -1.0, (0, 0)
    for dy in range(-r, r + 1, step):
        for dx in range(-r, r + 1, step):
            patch = cur[m + dy:h - m + dy, m + dx:w - m + dx]
            v = _ncc(core, patch)
            if v > best:
                best, bo = v, (dy, dx)
    # 在最优附近再精搜一步（步长 1）
    by, bx = bo
    for dy in (by - 1, by, by + 1):
        for dx in (bx - 1, bx, bx + 1):
            if abs(dy) > r or abs(dx) > r:
                continue
            patch = cur[m + dy:h - m + dy, m + dx:w - m + dx]
            v = _ncc(core, patch)
            if v > best:
                best = v
    return best


def check(path, verbose=False, fast=False):
    r_search, r_step = (12, 4) if fast else (SEARCH, 2)
    with av.open(path) as cont:
        frames = [f.to_ndarray(format="rgb24") for f in cont.decode(video=0)]
    if len(frames) < 3:
        return dict(path=path, n=len(frames), ok=False, note="帧数太少")

    # 统一到工作分辨率
    small = [_resize_block(f.astype(np.float32).mean(axis=2), WORK_W) for f in frames]
    ref = small[0]
    h, w = ref.shape
    cy0, cy1 = int(h * 0.25), int(h * 0.75)
    cx0, cx1 = int(w * 0.25), int(w * 0.75)

    def center_rgb(f):
        c = f[cy0:cy1, cx0:cx1].reshape(-1, 3)
        return c.mean(axis=0)

    r0 = center_rgb(frames[0])
    nccs, drgbs, motion = [], [], []
    for i in range(1, len(small)):
        nccs.append(_best_ncc(ref, small[i], r_search, r_step))
        drgbs.append(float(np.abs(center_rgb(frames[i]) - r0).mean()))
        motion.append(float(np.abs(frames[i].astype(np.float32)
                                  - frames[i - 1].astype(np.float32)).mean()))

    tail = max(3, len(nccs) // 4)          # 末 25% 作为"最终一致性"
    ncc_end = float(np.mean(nccs[-tail:]))
    ncc_min = float(np.min(nccs))
    rgb_end = float(np.mean(drgbs[-tail:]))
    m_mean = float(np.mean(motion))

    if ncc_end >= NCC_GOOD:
        verdict, ok = "一致性好", True
    elif ncc_end >= NCC_WARN:
        verdict, ok = "轻微漂移", True
    else:
        verdict, ok = "主体变形", False

    res = dict(path=path, n=len(frames), ncc_end=ncc_end, ncc_min=ncc_min,
               rgb_end=rgb_end, motion=m_mean, verdict=verdict, ok=ok)

    if verbose:
        step = max(1, len(nccs) // 10)
        print("     进度   NCC    ΔRGB   运动")
        for i in range(0, len(nccs), step):
            print("     %3d%%  %.3f  %5.1f  %5.2f" % (
                int(100 * (i + 1) / len(nccs)), nccs[i], drgbs[i], motion[i]))
        print("     末段  %.3f  %5.1f  %5.2f" % (ncc_end, rgb_end, m_mean))
    return res


def main():
    ap = argparse.ArgumentParser(description="主体一致性 / 漂移检测")
    ap.add_argument("files", nargs="+", help="mp4 路径，支持通配符")
    ap.add_argument("--verbose", "-v", action="store_true", help="打印逐段明细")
    ap.add_argument("--min-ncc", type=float, default=None,
                    help="自定义合格线（默认 0.85），低于此值判 FAIL")
    ap.add_argument("--fast", action="store_true",
                    help="粗搜（半径 12/步长 4），约快 4 倍，用于批量巡检")
    ap.add_argument("--json", action="store_true",
                    help="只输出 JSON 数组，供 batch_local.py 等程序调用")
    a = ap.parse_args()

    paths = []
    for p in a.files:
        paths += sorted(glob.glob(p)) or ([p] if os.path.exists(p) else [])
    if not paths:
        raise SystemExit("没找到视频文件")

    thr = a.min_ncc if a.min_ncc is not None else NCC_GOOD
    if not a.json:
        print("%-34s %5s %8s %8s %7s  %s" % ("文件", "帧数", "末段NCC", "ΔRGB", "运动", "判定"))
        print("-" * 88)

    rows = []
    for p in paths:
        if a.verbose:
            print("\n[%s]" % os.path.basename(p))
        try:
            r = check(p, a.verbose, a.fast)
        except Exception as e:
            if not a.json:
                print("%-34s  读取失败：%s" % (os.path.basename(p)[:34], str(e)[:60]))
            continue
        if not r.get("n"):
            continue
        passed = r["ok"] and r["ncc_end"] >= thr
        tag = "PASS" if passed else "FAIL"
        if not a.json:
            print("%-34s %5d %8.3f %8.1f %7.2f  %s %s" % (
                os.path.basename(p)[:34], r["n"], r["ncc_end"], r["rgb_end"],
                r["motion"], r["verdict"], "" if passed else "←"))
        r["passed"] = passed
        rows.append(r)

    if a.json:
        import json
        print(json.dumps(rows, ensure_ascii=False))
        return

    if not rows:
        return

    print("-" * 88)
    worst = sorted(rows, key=lambda x: x["ncc_end"])[:3]
    print("\n一致性最差的三条（优先重拍或缩短帧数）：")
    for r in worst:
        print("  %.3f  %s  （%d 帧，ΔRGB %.1f）" % (
            r["ncc_end"], os.path.basename(r["path"]), r["n"], r["rgb_end"]))

    fail = [r for r in rows if not (r["ok"] and r["ncc_end"] >= thr)]
    if fail:
        print("\n共 %d/%d 条不达标。对策（按性价比排序）：" % (len(fail), len(rows)))
        print("  1. 缩短到 49–65 帧（误差随帧数累积，这是最有效的一条）")
        print("  2. 把动作改小：只写一个几秒内能完成的动作，别写「走过来又转身」")
        print("  3. 避开全身景别，改半身/近景（身材变化在远景里最刺眼）")
        print("  4. 首帧先修脸：首帧有瑕疵，后面每一帧都会放大它")
        print("  5. 换 uni_pc + beta 跑（收敛更稳，见 --profile std）")
    else:
        print("\n全部达标。可以拼片了。")

    sys.exit(0 if not fail else 1)


if __name__ == "__main__":
    main()
