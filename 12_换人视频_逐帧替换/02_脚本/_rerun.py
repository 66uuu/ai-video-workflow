#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_rerun —— 问题帧重跑换 seed
f097：denoise 0.6 把运动模糊人体解构成双主体 → 降 0.5 换 3 个 seed
f193：贴镜头帧崩坏+左下漂移水印 → 用 inpaint 过的底图(tint5b) + 0.45 换 3 个 seed
输出到 swapped_try/，肉眼挑最好的替换进 swapped/。"""
import os
import sys

BRIDGE = r"你的桌面\AI生成视频\11_本地工具接入指南\bridge"
sys.path.insert(0, BRIDGE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nr_bridge import Comfy  # noqa
import frameswap as fs  # noqa

HERE = fs.HERE
OUT = os.path.join(HERE, "swapped_try")
os.makedirs(OUT, exist_ok=True)
CKPT = "Counterfeit-V2.5_pruned.safetensors"

JOBS = [
    # (idx, 底图路径, denoise, seeds)
    (97, os.path.join(fs.FRAMES, "f097.png"), 0.50, [101, 202, 303]),
    (193, os.path.join(HERE, "tint5b", "f193.png"), 0.45, [101, 202, 303]),
]

c = Comfy()
ref = c.upload_image(fs.REF)
print("参考图已上传：%s" % ref)

for idx, fpath, denoise, seeds in JOBS:
    for seed in seeds:
        name = c.upload_image(fpath)
        wf = fs.build_frameswap(name, ref, ref_weight=0.9, steps=24,
                                denoise=denoise, seed=seed, checkpoint=CKPT)
        wf["9"]["inputs"]["filename_prefix"] = "NR/RETRY_%03d_%d" % (idx, seed)
        files = c.run(wf, OUT, timeout=600)
        if files:
            dst = os.path.join(OUT, "f%03d_s%d.png" % (idx, seed))
            os.replace(files[0], dst)
            print("[ok] f%03d seed=%d -> %s" % (idx, seed, dst))
        else:
            print("[fail] f%03d seed=%d" % (idx, seed))
print("重跑完成")
