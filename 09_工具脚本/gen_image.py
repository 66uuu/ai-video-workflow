#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本地生图执行器（SD1.5 / majicmixRealistic_v7 + IPAdapter）
==========================================================
用途：图片也走本机 ComfyUI，不再依赖外部额度。
我（Agent）只写提示词，出图由这台机器算，出完自动回流并可选打包到桌面。

两种模式：
  t2i  —— 纯文生图
  ref  —— 挂参考图（IPAdapter），用于"人物别换脸"的续作

任务文件格式（IMAGES.json）：
{
  "jobs": [
    {"id": "IMG01", "mode": "t2i", "prompt": "...", "negative": "",
     "width": 768, "height": 1152, "steps": 28, "cfg": 6.0, "seed": 0},
    {"id": "IMG02", "mode": "ref", "ref": "E:/.../锚点.png", "ref_weight": 0.8,
     "prompt": "...", "width": 768, "height": 1152}
  ]
}

用法：
  python gen_image.py --probe                  # 打印可用节点与模型清单
  python gen_image.py --jobs IMAGES.json       # 批量出图
  python gen_image.py --prompt "..." --desktop # 单张，直接放桌面
"""
import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request

HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
# ComfyUI 根目录：优先环境变量，其次自动探测
COMFY = os.environ.get("COMFY_ROOT") or next(
    (p for p in (r"ComfyUI", r"源机器E盘ComfyUI") if os.path.isdir(p)), r"ComfyUI")
COMFY_OUT = os.environ.get("COMFY_OUT_DIR") or os.path.join(COMFY, "output")
COMFY_IN = os.environ.get("COMFY_IN_DIR") or os.path.join(COMFY, "input")
OUTROOT = os.environ.get("IMG_OUT_ROOT") or os.path.join(
    r"你的桌面\AI生成视频", "08_资产库", "_本地生图")
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")

CKPT = "majicmixRealistic_v7.safetensors"
DEFAULT_NEG = ("(worst quality, low quality:1.4), text, watermark, signature, logo, "
               "jpeg artifacts, blurry, deformed face, extra fingers, bad hands, "
               "multiple views, collage, border")


def api(path, payload=None, timeout=120):
    url = HOST + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            j = json.loads(body)
            msg = json.dumps(j, ensure_ascii=False)
        except Exception:
            msg = body
        raise RuntimeError("HTTP %d: %s" % (e.code, msg[:600]))


def probe():
    d = api("/object_info", timeout=90)
    print("节点总数", len(d))
    for n in ["CheckpointLoaderSimple", "IPAdapterModelLoader", "CLIPVisionLoader",
              "IPAdapterAdvanced", "IPAdapterUnifiedLoader", "IPAdapterApply"]:
        print(("  ✓ " if n in d else "  ✗ ") + n)
    ck = d.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [[]])[0]
    print("\n可用底座：", ck)
    if "IPAdapterModelLoader" in d:
        ip = d["IPAdapterModelLoader"]["input"]["required"]["ipadapter_file"][0]
        print("可用 IPAdapter：", ip)
    if "CLIPVisionLoader" in d:
        cv = d["CLIPVisionLoader"]["input"]["required"]["clip_name"][0]
        print("可用 CLIP Vision：", cv)
    if "IPAdapterAdvanced" in d:
        print("IPAdapterAdvanced 输入：", list(d["IPAdapterAdvanced"]["input"]["required"]))
    return 0


def build(job, has_ip, ref_name=None):
    w = job.get("width", 768)
    h = job.get("height", 1152)
    steps = job.get("steps", 28)
    cfg = job.get("cfg", 6.0)
    seed = job.get("seed", 0)
    pos = job["prompt"]
    neg = job.get("negative") or DEFAULT_NEG

    p = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": pos}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": neg}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {
            "images": ["6", 0], "filename_prefix": "LOCALIMG/%s" % job["id"]}},
    }

    model_src = ["1", 0]
    if has_ip and job.get("mode") == "ref" and ref_name:
        p["8"] = {"class_type": "IPAdapterModelLoader", "inputs": {
            "ipadapter_file": "ip-adapter-plus_sd15.safetensors"}}
        p["9"] = {"class_type": "CLIPVisionLoader", "inputs": {
            "clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"}}
        p["10"] = {"class_type": "LoadImage",
                   "inputs": {"image": "LOCALIMG_REF/%s" % ref_name}}
        p["11"] = {"class_type": "IPAdapterAdvanced", "inputs": {
            "model": ["1", 0], "ipadapter": ["8", 0], "image": ["10", 0],
            "clip_vision": ["9", 0],
            "weight": job.get("ref_weight", 0.8), "weight_type": "linear",
            "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
            "embeds_scaling": "V only"}}
        model_src = ["11", 0]

    p["5"] = {"class_type": "KSampler", "inputs": {
        "model": model_src, "seed": seed, "steps": steps, "cfg": cfg,
        "sampler_name": "dpmpp_2m", "scheduler": "karras",
        "positive": ["2", 0], "negative": ["3", 0],
        "latent_image": ["4", 0], "denoise": job.get("denoise", 1.0)}}
    return p


def wait(pid, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = api("/history/%s" % pid)
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed") or st.get("status_str") == "success":
                return h[pid]
            if st.get("status_str") == "error":
                raise RuntimeError(json.dumps(st.get("messages") or [], ensure_ascii=False)[-500:])
        time.sleep(2)
    raise TimeoutError("超时")


def grab_imgs(hist):
    out = []
    for _, node_out in (hist.get("outputs") or {}).items():
        for v in (node_out.get("images") or []):
            fn = v.get("filename", "")
            if fn.lower().endswith((".png", ".jpg", ".webp")):
                out.append(os.path.join(COMFY_OUT, v.get("subfolder", ""), fn))
    return out


def run_job(job, daydir, has_ip):
    ref_name = None
    if job.get("mode") == "ref" and job.get("ref"):
        src = job["ref"]
        if not os.path.exists(src):
            raise RuntimeError("参考图不存在：%s" % src)
        sub = os.path.join(COMFY_IN, "LOCALIMG_REF")
        os.makedirs(sub, exist_ok=True)
        ref_name = "%s_ref.png" % job["id"]   # 必须纯 ASCII，中文名会被 ComfyUI 校验拒绝
        shutil.copy2(src, os.path.join(sub, ref_name))
    wf = build(job, has_ip, ref_name)
    pid = api("/prompt", {"prompt": wf, "client_id": "localimg"})["prompt_id"]
    hist = wait(pid)
    files = grab_imgs(hist)
    if not files:
        raise RuntimeError("没有产出图片")
    dst = os.path.join(daydir, "%s_%s" % (job["id"], os.path.basename(files[0])))
    if job.get("out"):                       # 指定落盘路径（首帧等要固定命名的场景）
        dst = job["out"]
        os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(files[0], dst)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", default="")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--negative", default="")
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=1152)
    ap.add_argument("--steps", type=int, default=28)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--ref", default="")
    ap.add_argument("--ref-weight", type=float, default=0.8)
    ap.add_argument("--desktop", action="store_true")
    ap.add_argument("--only", default="", help="只跑指定 job id，逗号分隔")
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()

    if a.probe:
        return probe()

    # /object_info 在装了 ReActor/VideoHelperSuite 的实例上首次调用可能 1~3 分钟，
    # 用 COMFY_SKIP_INFO=1 可跳过探测（默认按 IPAdapter 可用处理）
    if os.environ.get("COMFY_SKIP_INFO"):
        has_ip = True
        print("跳过 /object_info 探测（COMFY_SKIP_INFO=1），按 IPAdapter 可用处理")
    else:
        try:
            info = api("/object_info", timeout=240)
        except Exception as e:
            print("✗ 连不上 ComfyUI：%s" % e)
            return 2
        has_ip = "IPAdapterAdvanced" in info and "IPAdapterModelLoader" in info

    if a.jobs:
        jobs = json.load(open(a.jobs, encoding="utf-8"))["jobs"]
        if a.only:
            keep = {x.strip() for x in a.only.split(",") if x.strip()}
            jobs = [j for j in jobs if j.get("id") in keep]
    elif a.prompt:
        jobs = [{"id": "IMG", "mode": "ref" if a.ref else "t2i", "prompt": a.prompt,
                 "negative": a.negative, "width": a.width, "height": a.height,
                 "steps": a.steps, "seed": a.seed, "ref": a.ref,
                 "ref_weight": a.ref_weight}]
    else:
        print("需要 --jobs 或 --prompt")
        return 2

    daydir = os.path.join(OUTROOT, time.strftime("%Y%m%d"))
    os.makedirs(daydir, exist_ok=True)
    print("=" * 62)
    print("本地生图 · %d 张 · 底座 %s · IPAdapter %s" % (len(jobs), CKPT, "可用" if has_ip else "未加载"))
    print("=" * 62)

    done = []
    for job in jobs:
        t0 = time.time()
        try:
            p = run_job(job, daydir, has_ip)
            print("  ✅ %-10s %4.0fs  %s" % (job["id"], time.time() - t0, os.path.basename(p)))
            done.append(p)
        except Exception as e:
            print("  ✗ %-10s %s" % (job["id"], str(e)[-160:]))

    if a.desktop and done:
        box = os.path.join(DESKTOP, "本地生图_%s" % time.strftime("%Y%m%d_%H%M"))
        os.makedirs(box, exist_ok=True)
        for p in done:
            shutil.copy2(p, os.path.join(box, os.path.basename(p)))
        print("已放桌面：%s" % box)
    print("输出目录：%s" % daydir)
    return 0 if len(done) == len(jobs) else 1


if __name__ == "__main__":
    sys.exit(main())
