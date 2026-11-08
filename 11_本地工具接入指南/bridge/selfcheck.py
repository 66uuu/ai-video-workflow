#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
selfcheck —— 换电脑后的第一件事
================================
一条命令告诉你：这台机器能不能直接开工。

检查七项：
  1) 配置解析      config.json 的 auto 能不能探到真实路径
  2) 服务连通      ComfyUI 在不在 8188
  3) 显存设备      GPU 型号与可用显存
  4) 模型文件      7 个必需模型在不在 models 目录
  5) 必备节点      18 个节点类全不全（缺 = 插件没好）
  6) ffmpeg        能不能调用
  7) 端到端试跑    真出一张图 + 一段视频（--run 才跑）

用法：
    python selfcheck.py            # 只体检，不动队列
    python selfcheck.py --run      # 体检 + 真跑一次出图/出视频（会占队列）
    python selfcheck.py --json     # 输出机器可读结果
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from nr_bridge import (Comfy, build_t2i, build_i2v, gen_len, load_config, resolve)

OK, BAD, WARN = "✔", "✘", "!"

report = []
fail_hard = 0


def line(status, title, detail=""):
    report.append((status, title, detail))
    text = "%s %s%s" % (status, title, ("  —  " + detail) if detail else "")
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


# ─────────────────────────────────────────────────────────────
def check_config(cfg):
    comfy = cfg["comfy"]
    root = comfy.get("root") or ""
    auto = comfy.get("_root_autodetected")
    if root and os.path.isdir(root):
        line(OK, "ComfyUI 目录", "%s%s" % (root, "（自动探测）" if auto else "（配置指定）"))
    else:
        line(BAD, "ComfyUI 目录", "没找到。请在 config.json 里把 comfy.root 写成真实路径")
        return False

    py = comfy.get("python") or ""
    if py and os.path.isfile(py):
        line(OK, "Python 解释器", py)
    else:
        line(WARN, "Python 解释器", "没探到独立 venv，将用当前解释器")

    st = comfy.get("startup") or ""
    line(OK if st else WARN, "启动脚本", st or "没找到 启动.bat，手动起服务也行")

    ff = cfg.get("ffmpeg") or ""
    if ff and os.path.isfile(ff):
        try:
            r = subprocess.run([ff, "-version"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            ver = (r.stdout or "").split("\n")[0][:60]
            line(OK, "ffmpeg", "%s（%s）" % (ff, ver))
        except Exception as e:
            line(BAD, "ffmpeg", "找到了但调不动：%s" % e)
            return False
    else:
        line(WARN, "ffmpeg", "没找到。视频帧数无法裁切，生成仍是 4n+1 帧")
    return True


def check_service(c):
    h = c.health()
    if not h["alive"]:
        line(BAD, "服务连通", h.get("error", "")[:160])
        line(WARN, "→", "先起服务：双击 <ComfyUI>/启动.bat，等浏览器自动打开")
        return False
    line(OK, "服务连通", "%s  队列：运行 %d / 等待 %d" % (h["host"], h["running"], h["pending"]))
    return True


def check_gpu(c, busy=False):
    """
    判据分两层：
      · 总显存（vram_total）决定这台机器「能不能跑」，与队列状态无关
      · 空闲显存（vram_free）只有在队列清空时才有参考意义 ——
        有任务在跑时模型已加载占显存，free 低是正常的，不能判不足
    """
    try:
        s = c.stats()
    except Exception as e:
        line(WARN, "显存设备", "拿不到：%s" % str(e)[:100])
        return
    devs = s.get("devices") or []
    if not devs:
        line(WARN, "显存设备", "system_stats 里没有设备信息")
        return
    for d in devs:
        tot = d.get("vram_total", 0) / 1024 ** 3
        free = d.get("vram_free", 0) / 1024 ** 3
        name = (d.get("name", "?") or "?").split(" : ")[0].strip()

        if tot >= 10.5:
            cap = "宽裕，121 帧没问题"
            st = OK
        elif tot >= 7.5:
            cap = "可跑 121 帧（贴上限），日常用 72 帧更稳"
            st = OK
        elif tot >= 6.0:
            cap = "建议降到 448×672，或帧数控制在 60 以内"
            st = WARN
        else:
            cap = "跑不动 Wan 5B，应改用 SD1.5 或换卡"
            st = BAD

        detail = "%s  总 %.1fG" % (name, tot)
        if busy:
            detail += "  当前空闲 %.1fG（队列在跑，属正常）  %s" % (free, cap)
        else:
            detail += "  空闲 %.1fG  %s" % (free, cap)
        line(st, "显存", detail)


def find_model(root, name):
    md = os.path.join(root, "models")
    if not os.path.isdir(md):
        return None
    for dp, _dn, fn in os.walk(md):
        if name in fn:
            return os.path.join(dp, name)
    return None


def check_models(cfg):
    root = cfg["comfy"]["root"]
    want = {k: v for k, v in (cfg.get("models") or {}).items() if not k.startswith("_")}
    miss = []
    for label, fn in want.items():
        p = find_model(root, fn)
        if p:
            sz = os.path.getsize(p) / 1024 ** 3
            line(OK, "模型 %s" % label, "%s  %.1fG" % (fn, sz))
        else:
            line(BAD, "模型 %s" % label, "缺 %s" % fn)
            miss.append(fn)
    return miss


def check_nodes(c):
    cfg = c.cfg
    want = []
    for k, v in (cfg.get("required_nodes") or {}).items():
        if isinstance(v, list):
            want += v
    try:
        res = c.has_nodes(want)
    except Exception as e:
        line(BAD, "节点检查", "拿不到 object_info：%s" % str(e)[:120])
        return want
    miss = [k for k, v in res.items() if not v]
    if not miss:
        line(OK, "必备节点", "%d 个全在" % len(want))
    else:
        line(BAD, "必备节点", "缺 %d 个：%s" % (len(miss), "、".join(miss)))
        if any(n in miss for n in ("UnetLoaderGGUF", "CLIPLoaderGGUF")):
            line(WARN, "→", "缺 GGUF 节点 = ComfyUI-GGUF 插件没装好")
        if any(n in miss for n in ("IPAdapterAdvanced", "IPAdapterModelLoader")):
            line(WARN, "→", "缺 IPAdapter = ComfyUI_IPAdapter_plus 插件没装好")
        if any(n.startswith("NR_") for n in miss):
            line(WARN, "→", "缺 NR_* = 自研节点包没拷进 custom_nodes")
    return miss


def try_run(c, outdir):
    """真跑一次：一张图 + 一段 16 帧视频。占队列，用 --run 才执行。"""
    os.makedirs(outdir, exist_ok=True)

    # 先报队列情况：有任务在跑时，下面的耗时会包含排队时间，别误读成生成慢
    try:
        q = c.queue()
        busy = q["running"] + q["pending"]
    except Exception:
        busy = 0
    if busy:
        print("  [注意] 队列里还有 %d 个任务。下面的耗时包含排队时间，" % busy)
        print("         不是单张/单段的真实生成耗时。空队列时：图约 8 秒，"
              "16 帧视频约 60–90 秒。\n")

    print("── 试跑 1/2：文生图（约 8 秒 + 排队）")
    wf = build_t2i("1girl, solo, portrait, photorealistic, soft natural daylight, "
                   "high detail, looking at viewer, upper body",
                   width=512, height=768, steps=20, seed=20261018,
                   prefix="NR/SELFCHECK_T2I")
    t0 = time.time()
    try:
        files = c.run(wf, outdir, number=0,
                      on_tick=lambda el: print("  … %.0fs" % el, end="\r", flush=True))
    except Exception as e:
        line(BAD, "文生图试跑", str(e)[:200])
        return None
    print(" " * 20, end="\r")
    if not files:
        line(BAD, "文生图试跑", "跑完了但没拿到文件")
        return None
    line(OK, "文生图试跑", "%s  %.0fs" % (os.path.basename(files[0]), time.time() - t0))
    img = files[0]

    print("\n── 试跑 2/2：图生视频（16 帧，约 60–90 秒 + 排队）")
    t0 = time.time()
    try:
        nm = c.upload_image(img, "selfcheck_ref.png")
        line(OK, "首帧上传", nm)
        wf2 = build_i2v(nm, "夜，画面中的女子极轻地眨了一下眼睛，然后停住。"
                            "雨声持续。无配乐。近景，50mm，浅景深。",
                        frames=16, width=512, height=768, steps=16, seed=20261018,
                        prefix="NR/SELFCHECK_I2V")
        files2 = c.run(wf2, outdir, number=0,
                       on_tick=lambda el: print("  … %.0fs" % el, end="\r", flush=True))
    except Exception as e:
        line(BAD, "图生视频试跑", str(e)[:300])
        return img
    print(" " * 20, end="\r")
    if not files2:
        line(BAD, "图生视频试跑", "跑完了但没拿到文件")
        return img
    line(OK, "图生视频试跑", "%s  %.0fs  （目标 16 帧 → 生成 %d 帧）"
         % (os.path.basename(files2[0]), time.time() - t0, gen_len(16)))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="体检 + 真跑一次出图出视频")
    ap.add_argument("--json", action="store_true", help="附加机器可读结果")
    a = ap.parse_args()

    print("=" * 66)
    print("  本地工具接入 · 环境体检")
    print("=" * 66)
    print()

    try:
        cfg = resolve(load_config())
    except SystemExit as e:
        print("✘ 配置读取失败：%s" % e)
        sys.exit(2)

    if not check_config(cfg):
        sys.exit(2)

    c = Comfy(cfg)
    if not check_service(c):
        sys.exit(3)

    try:
        q = c.queue()
        busy = (q["running"] + q["pending"]) > 0
    except Exception:
        busy = False
    check_gpu(c, busy=busy)
    print()
    miss_model = check_models(cfg)
    print()
    miss_node = check_nodes(c)
    print()

    # 结论
    print("=" * 66)
    blockers = len(miss_model) + len(miss_node)
    if blockers:
        print("  ✘ 还不能开工：缺 %d 项（模型 %d / 节点 %d）"
              % (blockers, len(miss_model), len(miss_node)))
        print("     补装方法见 ../02_下载与安装_从零到能出图.md")
    else:
        print("  ✔ 环境就绪，可以直接开工")
        print("     出图：python nr_bridge.py t2i --prompt \"...\" --out .")
        print("     出视频：python nr_bridge.py i2v --image 首帧.png --prompt \"...\" --frames 72")
    print("=" * 66)

    if a.run and not blockers:
        print()
        outdir = os.path.join(cfg["output_dir"], "selfcheck")
        try_run(c, outdir)
        print()
        print("试跑产物：%s" % outdir)

    if a.json:
        print()
        print(json.dumps({"ok": blockers == 0,
                          "missing_models": miss_model,
                          "missing_nodes": miss_node,
                          "comfy_root": cfg["comfy"]["root"]},
                         ensure_ascii=False, indent=2))

    sys.exit(1 if blockers else 0)


if __name__ == "__main__":
    main()
