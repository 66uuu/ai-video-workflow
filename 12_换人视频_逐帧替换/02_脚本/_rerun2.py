#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_rerun2 —— 用 v6 修补底图（tint6/）重跑漂移水印嫌疑帧
参数与全片一致：denoise 0.6 / weight 0.9 / cfg 5.5 / blur 帧自动降 0.45
seed 固定（可复现）：seed = idx * 7 + 1000
输出到 swapped_try2/，人眼抽检后替换进 swapped/。"""
import os
import sys
import json

BRIDGE = r"你的桌面\AI生成视频\11_本地工具接入指南\bridge"
sys.path.insert(0, BRIDGE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nr_bridge import Comfy  # noqa
import frameswap as fs  # noqa

HERE = fs.HERE
OUT = os.path.join(HERE, "swapped_try2")
SRC6 = os.path.join(HERE, "tint6")
os.makedirs(OUT, exist_ok=True)

IDXS = [7, 12, 17, 25, 32, 33, 35, 44, 64, 70, 72, 75, 92, 101, 104, 107, 110,
        111, 113, 115, 119, 120, 125, 132, 133, 143, 149, 151, 159, 160, 161,
        163, 167, 168, 171, 176, 177, 178, 179, 180, 181, 189, 190, 191, 193]

with open(os.path.join(HERE, "_blur_map.json")) as fp:
    blur_map = json.load(fp)

c = Comfy()
ref = c.upload_image(fs.REF)
print("参考图已上传：%s，共 %d 帧待重跑" % (ref, len(IDXS)))

ok = 0
for idx in IDXS:
    fpath = os.path.join(SRC6, "f%03d.png" % idx)
    if not os.path.isfile(fpath):
        print("[skip] 缺底图 f%03d" % idx)
        continue
    denoise = 0.6
    var = blur_map.get(str(idx), 999)
    if var < 130:
        denoise = 0.45
    seed = idx * 7 + 1000
    name = c.upload_image(fpath)
    wf = fs.build_frameswap(name, ref, ref_weight=0.9, steps=24,
                            denoise=denoise, seed=seed,
                            checkpoint="Counterfeit-V2.5_pruned.safetensors")
    wf["9"]["inputs"]["filename_prefix"] = "NR/RETRY2_%03d" % idx
    files = c.run(wf, OUT, timeout=600)
    if files:
        dst = os.path.join(OUT, "f%03d.png" % idx)
        os.replace(files[0], dst)
        ok += 1
        print("[ok] f%03d（denoise=%.2f seed=%d 方差=%.0f）" % (idx, denoise, seed, var))
    else:
        print("[fail] f%03d" % idx)
print("\n完成：%d/%d" % (ok, len(IDXS)))
