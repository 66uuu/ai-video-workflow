#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
frameswap —— 逐帧换人（img2img + IP-Adapter）
============================================
把原视频每一帧作为 img2img 底图（物理级锁定姿势/表情/机位），
用 IP-Adapter 注入参考角色（西装 2D 男），逐帧重绘后拼回视频。

用法：
  python frameswap.py validate            # 验 3 帧（敬礼/舞动/贴镜头）
  python frameswap.py run --idx 1,90,185  # 指定帧
  python frameswap.py all                 # 全片 194 帧
  python frameswap.py all --ckpt Counterfeit-V2.5_pruned.safetensors
"""
import os
import sys
import json
import time

BRIDGE = r"你的桌面\AI生成视频\11_本地工具接入指南\bridge"
sys.path.insert(0, BRIDGE)
from nr_bridge import Comfy, DEFAULT_NEG  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(HERE, "frames_tint5")  # v5: 修了染色3bug的底图（erode1/MIN_AREA800/无兜底/面积上限）
SWAPPED = os.path.join(HERE, "swapped")
REF = r"<D盘>\UserFiles\Pictures\0efdf501e37d6ee039e9e44a6c16d961.jpg"

# 负向：禁低质/畸变/水印/文字（原视频有"AI创作"水印，尽量让它被重绘抹掉）
SWAP_NEG = ("lowres, bad anatomy, bad hands, text, watermark, signature, "
            "extra limbs, deformed, blurry, ugly, worst quality, jpeg artifacts, "
            "white clothes, white jacket, white sleeves, white cuffs, "
            "pajamas, casual wear, extra text, logo, "
            "字幕, 水印, 文字, logo, 变形的脸, 多余的手指, 扭曲的身体")

# 正向：强调深海军蓝西装（原视频人物穿白色睡衣，必须强力覆盖）
SWAP_POS = ("masterpiece, best quality, 2d anime illustration, "
            "a young man with short brown layered hair and thin round glasses, "
            "wearing a deep navy blue three-piece business suit, crisp white shirt, "
            "dark navy necktie, dancing energetically, "
            "dim bedroom with green curtains, cinematic lighting, "
            "same camera angle, keep original background")


def build_frameswap(frame_image, ref_image, ref_weight=1.0,
                    prompt=SWAP_POS, negative=SWAP_NEG,
                    steps=24, seed=None, cfg_scale=6.0, denoise=0.55,
                    checkpoint="Counterfeit-V2.5_pruned.safetensors",
                    clip_vision="CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
                    ipadapter="ip-adapter-plus_sd15.safetensors",
                    prefix="NR/SWAP"):
    import random
    seed = random.randint(0, 2 ** 31 - 1) if seed is None else seed
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        # 原帧 → VAE 编码，作为 img2img 底图（锁姿势/机位）
        "30": {"class_type": "LoadImage", "inputs": {"image": frame_image}},
        "31": {"class_type": "VAEEncode", "inputs": {"pixels": ["30", 0], "vae": ["4", 2]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        # 参考角色 → IP-Adapter
        "10": {"class_type": "LoadImage", "inputs": {"image": ref_image}},
        "11": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": ipadapter}},
        "12": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": clip_vision}},
        "13": {"class_type": "IPAdapterAdvanced", "inputs": {
            "weight": ref_weight, "weight_type": "linear", "combine_embeds": "concat",
            "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only",
            "model": ["4", 0], "ipadapter": ["11", 0],
            "image": ["10", 0], "clip_vision": ["12", 0]}},
        "3": {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": steps, "cfg": cfg_scale,
            "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": denoise,
            "model": ["13", 0], "positive": ["6", 0], "negative": ["7", 0],
            "latent_image": ["31", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
    }


def process(c, idx, ref_name, ckpt, denoise, ref_weight, steps, blur_map=None, blur_denoise=0.4):
    """处理单帧 idx（1-based），落盘 swapped/f%03d.png。返回本地路径或 None。
    模糊帧（Laplacian 方差<130，人物扭动/结构不清）自动降 denoise 防幻觉。"""
    fpath = os.path.join(FRAMES, "f%03d.png" % idx)
    if not os.path.isfile(fpath):
        print("[skip] 缺帧 %d" % idx)
        return None
    use_denoise = denoise
    if blur_map is not None:
        var = blur_map.get(str(idx), blur_map.get(idx, 999))
        if var < 130:
            use_denoise = blur_denoise
    # 原帧必须先上传到 ComfyUI（LoadImage 只认 input 目录里的图）
    frame_name = c.upload_image(fpath)
    wf = build_frameswap(frame_name, ref_name,
                         ref_weight=ref_weight, steps=steps, denoise=use_denoise,
                         checkpoint=ckpt)
    # 用帧名当 prefix 以便 fetch 后识别
    prefix = "NR/SWAP_%03d" % idx
    wf["9"]["inputs"]["filename_prefix"] = prefix
    t0 = time.time()
    files = c.run(wf, SWAPPED, timeout=600)
    # 重命名为 swapped/f%03d.png
    if files:
        src = files[0]
        dst = os.path.join(SWAPPED, "f%03d.png" % idx)
        if os.path.abspath(src) != os.path.abspath(dst):
            os.replace(src, dst)
        print("[ok] 帧 %03d  用时 %.0fs  -> %s" % (idx, time.time() - t0, dst))
        return dst
    print("[fail] 帧 %03d 无产出" % idx)
    return None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["validate", "run", "all"])
    ap.add_argument("--idx", default="")
    ap.add_argument("--ckpt", default="Counterfeit-V2.5_pruned.safetensors")
    ap.add_argument("--denoise", type=float, default=0.6)
    ap.add_argument("--blur-denoise", type=float, default=0.45)
    ap.add_argument("--weight", type=float, default=0.9)
    ap.add_argument("--steps", type=int, default=24)
    ap.add_argument("--cfg", type=float, default=5.5)
    a = ap.parse_args()

    # 清晰度图（preprocess3 产出）：模糊帧自动降 denoise
    blur_map = None
    bm_path = os.path.join(HERE, "_blur_map.json")
    if os.path.isfile(bm_path):
        with open(bm_path) as fp:
            blur_map = json.load(fp)

    c = Comfy()
    h = c.health()
    if not h.get("alive"):
        raise SystemExit("ComfyUI 未启动：%s" % h)
    print("ComfyUI 在线，空闲VRAM 见 stats；开始上传参考角色图…")
    ref_name = c.upload_image(REF)
    print("参考图已上传：%s" % ref_name)

    if a.cmd == "validate":
        idxs = [5, 90, 145]  # 敬礼 / 大动态模糊 / 贴镜头模糊
    elif a.cmd == "run":
        idxs = [int(x) for x in a.idx.split(",") if x.strip()]
    else:  # all
        idxs = list(range(1, 195))

    print("处理帧：%s（ckpt=%s denoise=%.2f weight=%.2f steps=%d）"
          % (idxs if len(idxs) <= 12 else "%d 帧" % len(idxs),
             a.ckpt, a.denoise, a.weight, a.steps))
    ok = 0
    for i in idxs:
        r = process(c, i, ref_name, a.ckpt, a.denoise, a.weight, a.steps,
                    blur_map=blur_map, blur_denoise=a.blur_denoise)
        if r:
            ok += 1
    print("\n完成：%d/%d 帧成功" % (ok, len(idxs)))


if __name__ == "__main__":
    main()
