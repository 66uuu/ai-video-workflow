#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
速度 / 画质 基准测试 —— 用真实机器数据决定该用哪一档
=====================================================================
不要再靠"感觉慢"判断。这个脚本对每个参数档位跑一小段视频（默认 25 帧 ≈ 1 秒），
量出真实耗时，再折算成"一条 72 帧镜头要多久"，出一张对比表。

用法：
  python bench.py                          # 跑 4 档，每档 25 帧
  python bench.py --frames 33              # 用更长片段（数字更稳，但更慢）
  python bench.py --profiles draft,std     # 只测指定档
  python bench.py --dry-run                # 只打印计划，不真跑
  python bench.py --image xxx.png          # 换首帧图

输出：
  屏幕表格 + _bench/bench_YYYYmmdd_HHMM.md（可直接贴给别人看）

判读方法：
  · 看「折算 72 帧」这一列 —— 这就是你实际等待的时间
  · 如果 draft 档都要 > 10 分钟，说明不是参数问题，是链路问题（见 04 文档排查表）
  · 画质请自己看 _bench/ 里生成的 mp4，参数表给不了主观结论
"""
import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
BRIDGE = os.path.join(PKG, "11_本地工具接入指南", "bridge")
sys.path.insert(0, BRIDGE)

try:
    import nr_bridge as nb
except Exception as e:
    raise SystemExit("导入 nr_bridge 失败（%s）。检查路径：%s" % (e, BRIDGE))

BENCHDIR = os.path.join(HERE, "_bench")
DEFAULT_IMG = os.path.join(PKG, "08_资产库", "_资产锁定", "A01_SC_NIGHTROAD_主视觉_v01.png")
DEFAULT_PROMPT = ("The camera slowly pushes forward, the night road stretches into the distance, "
                  "distant streetlights flicker once. Ambient night wind, low drone. "
                  "Wide establishing shot.")


def human(sec):
    if sec < 60:
        return "%.0f 秒" % sec
    return "%.1f 分钟" % (sec / 60.0)


def main():
    ap = argparse.ArgumentParser(description="速度/画质基准测试")
    ap.add_argument("--frames", type=int, default=25, help="每档跑多少帧（默认 25）")
    ap.add_argument("--profiles", default="draft,fast,std,hq")
    ap.add_argument("--image", default=DEFAULT_IMG)
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--seed", type=int, default=12345, help="固定种子，保证可比")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    names = [x.strip() for x in a.profiles.split(",") if x.strip()]
    bad = [x for x in names if x not in nb.PROFILES]
    if bad:
        raise SystemExit("未知档位：%s（可选 %s）" % (",".join(bad), ",".join(nb.PROFILES)))

    if not os.path.exists(a.image):
        raise SystemExit("首帧图不存在：%s\n用 --image 指定一张" % a.image)

    gl = nb.gen_len(a.frames)
    print("首帧：%s" % os.path.basename(a.image))
    print("每档目标 %d 帧（实际生成 %d 帧，4n+1）  固定 seed=%d" % (a.frames, gl, a.seed))
    print("-" * 74)

    if a.dry_run:
        for n in names:
            p = nb.PROFILES[n]
            print("%-6s %dx%d  %2d 步  %-9s / %-7s" % (
                n, p["width"], p["height"], p["steps"], p["sampler"], p["scheduler"]))
        return

    c = nb.Comfy()
    h = c.health()
    if not h.get("alive"):
        raise SystemExit("ComfyUI 不在线：%s\n先启动 <D盘>\\ComfyUI 的启动.bat\n错误：%s"
                         % (h.get("host"), h.get("error", "")))
    st = c.stats()
    dev = (st.get("devices") or [{}])[0]
    print("GPU：%s  显存 空闲 %.1fG / 共 %.1fG" % (
        dev.get("name", "?"),
        dev.get("vram_free", 0) / 1024 ** 3,
        dev.get("vram_total", 0) / 1024 ** 3))
    print("-" * 74)

    nm = c.upload_image(a.image)
    os.makedirs(BENCHDIR, exist_ok=True)
    rows = []

    for n in names:
        p = nb.PROFILES[n]
        print("\n[%s] %dx%d  %d 步  %s / %s  —— 开始" % (
            n, p["width"], p["height"], p["steps"], p["sampler"], p["scheduler"]))
        wf = nb.build_i2v(nm, a.prompt, a.frames,
                          width=p["width"], height=p["height"], steps=p["steps"],
                          sampler=p["sampler"], scheduler=p["scheduler"],
                          seed=a.seed, prefix="NR_BENCH/%s" % n)
        t0 = time.time()
        try:
            files = c.run(wf, BENCHDIR,
                          on_tick=lambda el: print("   … %.0fs" % el, end="\r", flush=True))
        except Exception as e:
            print("\n   ✘ 失败：%s" % str(e)[:300])
            rows.append(dict(name=n, w=p["width"], h=p["height"], steps=p["steps"],
                             sampler=p["sampler"], scheduler=p["scheduler"],
                             sec=None, note="失败"))
            continue
        dt = time.time() - t0
        est72 = dt / float(gl) * 73.0  # 72 帧目标 → 实际 73 帧
        print("\n   ✔ %.1f 秒   →  折算 72 帧约 %s" % (dt, human(est72)))
        rows.append(dict(name=n, w=p["width"], h=p["height"], steps=p["steps"],
                         sampler=p["sampler"], scheduler=p["scheduler"],
                         sec=dt, est72=est72, files=files, note=""))

    # ── 汇总 ────────────────────────────────────────────────
    print("\n" + "=" * 74)
    print("结果汇总（固定 seed=%d，%d 帧实测）" % (a.seed, gl))
    print("=" * 74)
    hdr = "%-7s %-10s %-5s %-10s %-9s %-14s %s" % (
        "档位", "分辨率", "步数", "采样器", "调度器", "实测耗时", "折算72帧")
    print(hdr)
    print("-" * 74)
    base = next((r for r in rows if r["name"] == "std" and r["sec"]), None)
    for r in rows:
        if r["sec"] is None:
            print("%-7s %-10s %-5s %-10s %-9s %-14s %s" % (
                r["name"], "%dx%d" % (r["w"], r["h"]), r["steps"],
                r["sampler"], r["scheduler"], "失败", r["note"]))
            continue
        speed = ""
        if base:
            sp = base["sec"] / r["sec"]
            speed = "  ×%.2f" % sp
        print("%-7s %-10s %-5s %-10s %-9s %-14s %s%s" % (
            r["name"], "%dx%d" % (r["w"], r["h"]), r["steps"],
            r["sampler"], r["scheduler"],
            "%.1f 秒" % r["sec"], human(r["est72"]), speed))
    print("-" * 74)

    ok = [r for r in rows if r["sec"]]
    if ok:
        fast = min(ok, key=lambda x: x["sec"])
        print("\n最快：%s（%s）" % (fast["name"], human(fast["est72"])))
        print("画质请自己看：%s" % BENCHDIR)
        if fast["est72"] > 600:
            print("\n⚠ 连最快档折算 72 帧都要 %s —— 这不是参数问题，是链路问题。" % human(fast["est72"]))
            print("  按 04_速度与一致性优化.md 的 8 项排查表逐条查：")
            print("  ① GPU 是否在跑（任务管理器看 CUDA）  ② 是否 --lowvram 回退")
            print("  ③ 是否误跑 121 帧  ④ 模型是否反复重载  ⑤ 显存是否溢出到内存")

    # 落盘
    md = os.path.join(BENCHDIR, "bench_%s.md" % time.strftime("%Y%m%d_%H%M"))
    with open(md, "w", encoding="utf-8") as f:
        f.write("# 基准测试结果\n\n")
        f.write("- 时间：%s\n" % time.strftime("%Y-%m-%d %H:%M"))
        f.write("- GPU：%s（显存 %.1fG）\n" % (
            dev.get("name", "?"), dev.get("vram_total", 0) / 1024 ** 3))
        f.write("- 首帧：%s\n- 目标帧数：%d（实际 %d）\n- seed：%d\n\n" % (
            os.path.basename(a.image), a.frames, gl, a.seed))
        f.write("| 档位 | 分辨率 | 步数 | 采样器 | 调度器 | 实测 | 折算72帧 |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in rows:
            if r["sec"] is None:
                f.write("| %s | %dx%d | %d | %s | %s | 失败 | %s |\n" % (
                    r["name"], r["w"], r["h"], r["steps"], r["sampler"],
                    r["scheduler"], r["note"]))
            else:
                f.write("| %s | %dx%d | %d | %s | %s | %.1f 秒 | %s |\n" % (
                    r["name"], r["w"], r["h"], r["steps"], r["sampler"],
                    r["scheduler"], r["sec"], human(r["est72"])))
    print("\n报告已存：%s" % md)


if __name__ == "__main__":
    main()
