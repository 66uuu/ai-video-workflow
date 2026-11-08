#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_rerun3 —— 修构图崩坏(f113) + 大蓝块(f145/f194)
f113: 双臂上举模糊帧，denoise 0.6 把左臂解构成人形 → 降 0.5
f145/f194: 底图蓝块被当实体 → tint6 底图 + 换 seed
输出 swapped_try3/"""
import os, sys, json
BRIDGE = r"D:/UserFiles/Desktop/AI生成视频/11_本地工具接入指南/bridge"
sys.path.insert(0, BRIDGE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nr_bridge import Comfy
import frameswap as fs

HERE = fs.HERE
OUT = os.path.join(HERE, "swapped_try3")
SRC6 = os.path.join(HERE, "tint6")
os.makedirs(OUT, exist_ok=True)
JOBS = [
    (113, 0.50, [404, 505, 606]),
    (145, 0.60, [404, 505, 606]),
    (194, 0.45, [404, 505, 606]),
]
with open(os.path.join(HERE, "_blur_map.json")) as fp:
    blur_map = json.load(fp)
c = Comfy()
ref = c.upload_image(fs.REF)
print("参考图：%s" % ref)
for idx, denoise, seeds in JOBS:
    fpath = os.path.join(SRC6, "f%03d.png" % idx)
    if not os.path.isfile(fpath):
        print("[skip] 缺 tint6/f%03d" % idx)
        continue
    for seed in seeds:
        name = c.upload_image(fpath)
        wf = fs.build_frameswap(name, ref, ref_weight=0.9, steps=24,
                                denoise=denoise, seed=seed,
                                checkpoint="Counterfeit-V2.5_pruned.safetensors")
        wf["9"]["inputs"]["filename_prefix"] = "NR/RETRY3_%03d_%d" % (idx, seed)
        files = c.run(wf, OUT, timeout=600)
        if files:
            dst = os.path.join(OUT, "f%03d_s%d.png" % (idx, seed))
            os.replace(files[0], dst)
            print("[ok] f%03d seed=%d（方差%.0f）" % (idx, seed, blur_map.get(str(idx), 999)))
        else:
            print("[fail] f%03d seed=%d" % (idx, seed))
print("完成")
