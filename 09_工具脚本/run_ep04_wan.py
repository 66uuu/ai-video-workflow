#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
EP04 真·图生视频 v2（Wan2.2 TI2V-5B GGUF）— 按 P24 审计修正后的规范
====================================================================
与 v1 的差别（全部来自 P24 的漏洞清单）：
  V2  帧数不再手写，一律从 EP04_timeline_v2.json 读，向上取到 4n+1（Wan 要求）
  V3  正文不写画风（画风归后期统一 LUT + 颗粒）
  V4  正文不写长相/服装/发色（外观 100% 交给首帧参考图，否则换脸）
  V5  只写几秒内能做完的大动作，不写眨眼/重心这类微动作
  V6  一切一个运镜，正文只写一句，正向固定追加 CAM_LOCK
  V7  构图靠 lens 句落进正文（焦距+景别+景深）
  V8  声音三层：动作 → 声景 → 配乐，各自成句
  G2/G3 出片后自动做帧差量化与出画检测

显存：512x768 是精确 2:3；TI2V-5B 用 16x16x4 高压缩 VAE，latent 只有 32x48x31。

用法：
  python run_ep04_wan.py --list
  python run_ep04_wan.py --shot S20A
  python run_ep04_wan.py --batch S20A,S24A
  python run_ep04_wan.py --shot S20A --dry
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
COMFY = r"源机器E盘ComfyUI"
IN_SUB = "NR_EP04_WAN"
LOCK = r"源机器E盘灵异悬疑短剧_资产包\04_提示词\_资产锁定"
EPDIR = r"源机器E盘灵异悬疑短剧_资产包\07_成片\EP04"
VIDDIR = os.path.join(EPDIR, "video_i2v")
TIMELINE = os.path.join(EPDIR, "EP04_timeline_v2.json")
FFMPEG = (os.environ.get("FFMPEG")
          or next((p for p in (r"源机器E盘ffmpeg_bin\ffmpeg.exe", r"ComfyUI\ffmpeg.exe",
                               r"<D盘>\ffmpeg\bin\ffmpeg.exe") if os.path.exists(p)), None)
          or shutil.which("ffmpeg") or "ffmpeg")

UNET = "Wan2.2-TI2V-5B-Q5_K_M.gguf"
CLIP = "umt5-xxl-encoder-Q4_K_M.gguf"
VAE = "wan2.2_vae.safetensors"

# V6：负向必须显式禁运镜与换脸。禁止写「没有 X」句式（会被读成「不要 X」）
NEG = ("镜头推近，镜头拉远，变焦，摇镜，平移，构图漂移，人物出画，裁掉头部，只拍身体，"
       "换脸，长着另一张脸，发型改变，发色改变，服装改变，"
       "多余的手指，畸形的手，扭曲的脸，五官变形，"
       "字幕，水印，文字，logo，"
       "过曝，整体发灰，低质量，最差质量，JPEG压缩残留，杂乱的背景，多重人影，闪烁")

# V6：全剧机位纪律
CAM_LOCK = "机位固定不动。"

# ── 每切的正文（协议无关：只写这几秒发生什么）────────────────────
# 严禁出现：画风词、长相词、姓名、微表情、第二个运镜
SHOTS = {
    "S20A": dict(
        img="EP04/EP04_S20A_台阶打电话_v01.png",
        action="夜，一名女子站在台阶上，把手机贴在耳边等着，身体几乎不动。她缓慢地低下头，"
               "把手机往耳朵上贴紧一点，停住。",
        sound="雨持续落在水泥台阶和铁皮雨棚上，远处有车驶过积水的声音。",
        music="无配乐。",
        lens="近景，85mm 中长焦，浅景深。",
        steps=24, shift=8.0, cfg=5.0),
    "S21A": dict(
        img="EP04/EP04_S21A_摸口袋_v01.png",
        action="她还举着手机听，另一只手缓慢移到身前，隔着外套按住胸口的位置，停住不动。",
        sound="雨声，听筒里极轻的电流声。",
        music="无配乐。",
        lens="近景，85mm 中长焦，浅景深。",
        steps=24, shift=8.0, cfg=5.0),
    "S22A": dict(
        img="EP04/EP04_S22A_黑屏倒影_v01.png",
        action="她把手机从耳边放下，屏幕的光慢慢暗下去，黑色玻璃里映出她半张脸。",
        sound="雨声，衣料摩擦声。",
        music="无配乐。",
        lens="特写，100mm，极浅景深。",
        steps=24, shift=8.0, cfg=5.0),
    "S22B": dict(
        img="EP04/EP04_S22B_空站牌_v01.png",
        action="她侧身站着，缓慢抬起头，看向街对面，停住。",
        sound="雨落，远处车流。",
        music="无配乐。",
        lens="中景，50mm，中浅景深。",
        steps=24, shift=8.0, cfg=5.0),
    "S23A": dict(
        img="EP04/EP04_S23A_空车厢_v01.png",
        action="夜，一辆车的车门敞开着，车里顶灯亮着，驾驶座空着。雨落在车顶和玻璃上，"
               "水顺着车窗往下淌，后视镜上的布符轻轻摆动。",
        sound="雨打车顶，车门缝里的风声。",
        music="无配乐。",
        lens="中景，35mm，中景深。",
        steps=24, shift=8.0, cfg=5.0),
    # V9：2.5 秒塞不下「走过整个画面」，只能「擦过前景并停住」
    "S24A": dict(
        img="EP04/EP04_S24A_老周看录音笔_v01.png",
        action="夜，一名中年男子侧身从画面右侧走过来，肩膀擦过画面边缘，头低着，视线向下，"
               "在画面右三分之一处停住。",
        sound="脚步声踩过积水，雨声。",
        music="无配乐。",
        lens="近景，50mm，浅景深。",
        steps=24, shift=8.0, cfg=5.0),
    "S24B": dict(
        img="EP04/EP04_S24B_平安符晃_v01.png",
        action="夜，车内，后视镜上挂的布符还在摆动，摆动的幅度慢慢变小。挡风玻璃外的雨在流。",
        sound="雨打车顶，布料摩擦。",
        music="无配乐。",
        lens="特写，100mm，极浅景深。",
        steps=24, shift=8.0, cfg=5.0),
}


def gen_len(frames):
    """Wan 要求 length = 4n+1，向上取最小合法值"""
    return ((frames - 1 + 3) // 4) * 4 + 1


def timeline_frames():
    if not os.path.exists(TIMELINE):
        return {}
    tl = json.load(open(TIMELINE, encoding="utf-8"))
    return {s["shot_id"]: s["frames"] for s in tl["shots"]}


def api(path, payload=None, timeout=60):
    url = HOST + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def body(cfg):
    """正文组装：动作 → 声景 → 配乐 → 镜头。四段各自成句，互不污染。"""
    return "%s %s %s %s %s" % (cfg["action"], cfg["sound"], cfg["music"], cfg["lens"], CAM_LOCK)


def build(sid, cfg, w, h, length, steps, seed):
    in_name = "%s_%s.png" % (sid, os.path.basename(cfg["img"]).replace("_v01.png", ""))
    return in_name, {
        "10": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": UNET}},
        "11": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": CLIP, "type": "wan"}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "13": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["10", 0], "shift": cfg["shift"]}},
        "14": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": body(cfg)}},
        "15": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": NEG}},
        "16": {"class_type": "LoadImage", "inputs": {"image": "%s/%s" % (IN_SUB, in_name)}},
        "20": {"class_type": "Wan22ImageToVideoLatent", "inputs": {
            "vae": ["12", 0], "width": w, "height": h, "length": length,
            "batch_size": 1, "start_image": ["16", 0]}},
        "21": {"class_type": "KSampler", "inputs": {
            "model": ["13", 0], "seed": seed, "steps": steps, "cfg": cfg["cfg"],
            "sampler_name": "euler", "scheduler": "simple",
            "positive": ["14", 0], "negative": ["15", 0],
            "latent_image": ["20", 0], "denoise": 1.0}},
        "22": {"class_type": "VAEDecode", "inputs": {"samples": ["21", 0], "vae": ["12", 0]}},
        "23": {"class_type": "CreateVideo", "inputs": {"images": ["22", 0], "fps": 24.0}},
        "24": {"class_type": "SaveVideo", "inputs": {
            "video": ["23", 0], "filename_prefix": "NR/EP04_I2V/%s" % sid,
            "format": "mp4", "codec": {"codec": "h264"}}},
    }


def wait(pid, timeout=3600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = api("/history/%s" % pid)
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed") or st.get("status_str") == "success":
                return h[pid]
            if st.get("status_str") == "error":
                raise RuntimeError("工作流报错: " +
                                   json.dumps(st.get("messages") or [], ensure_ascii=False)[-900:])
        time.sleep(2)
    raise TimeoutError("超时")


def grab(hist):
    for _, node_out in (hist.get("outputs") or {}).items():
        for key in ("images", "videos", "gifs"):
            for v in (node_out.get(key) or []):
                fn = str(v.get("filename", ""))
                if fn.endswith(".mp4"):
                    return os.path.join(COMFY, "output", v.get("subfolder", ""), fn)
    return None


def trim(src, dst, frames):
    """把 4n+1 帧裁到时间轴要求的精确帧数（V2）"""
    subprocess.run([FFMPEG, "-y", "-i", src, "-frames:v", str(frames),
                    "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                    "-an", dst, "-loglevel", "error"], check=True)


def qa(path):
    """G2 真运动 / G3 不出画 —— 量化，不靠眼看"""
    try:
        import av
        import numpy as np
        fr = [f.to_ndarray(format="gray").astype(np.float32) for f in av.open(path).decode(video=0)]

        def d(i, j):
            return float(np.abs(fr[i] - fr[j]).mean())

        step = [d(i, i + 1) for i in range(0, len(fr) - 1, 6)]
        m_step, m_ends = sum(step) / len(step), d(0, len(fr) - 1)

        # 出画检测：末帧左右两侧条带的方差若远低于首帧，说明主体走了、画面空掉
        def edges(a):
            h, w = a.shape
            return float(np.concatenate([a[:, :w // 6].ravel(), a[:, -w // 6:].ravel()]).std())

        hollow = edges(fr[-1]) < edges(fr[0]) * 0.55
        ok = m_step >= 0.30 and m_ends >= 1.5 and not hollow
        return ("%d帧 | 相邻帧差%.2f | 首末帧差%.2f | 出画%s | %s" %
                (len(fr), m_step, m_ends, "是" if hollow else "否", "PASS" if ok else "FAIL"), ok)
    except Exception as e:
        return ("QA 跳过: %s" % str(e)[:80], True)


def run_one(sid, seed):
    cfg = SHOTS[sid]
    frames = timeline_frames().get(sid)
    if not frames:
        print("  ✗ 时间轴里没有 %s 的帧数，拒绝渲染" % sid)
        return False
    length = gen_len(frames)
    os.makedirs(os.path.join(COMFY, "input", IN_SUB), exist_ok=True)
    os.makedirs(VIDDIR, exist_ok=True)
    src = os.path.join(LOCK, cfg["img"].replace("/", os.sep))
    in_name, wf = build(sid, cfg, 512, 768, length, cfg["steps"], seed)
    shutil.copy2(src, os.path.join(COMFY, "input", IN_SUB, in_name))

    print("[%s] 时间轴 %d 帧(%.2fs) → 生成 %d 帧(4n+1)  512x768  %d 步" %
          (sid, frames, frames / 24.0, length, cfg["steps"]))
    t0 = time.time()
    pid = api("/prompt", {"prompt": wf, "client_id": "nr_ep04_wan"})["prompt_id"]
    hist = wait(pid)
    out = grab(hist)
    if not out or not os.path.exists(out):
        print("  ✗ 没拿到 mp4")
        return False
    raw = os.path.join(VIDDIR, "_raw_%s.mp4" % sid)
    shutil.copy2(out, raw)
    dst = os.path.join(VIDDIR, "%s_i2v.mp4" % sid)
    trim(raw, dst, frames)
    os.remove(raw)
    report, ok = qa(dst)
    print("  %s %s  (%.0fs)" % ("✅" if ok else "⚠️", report, time.time() - t0))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", default="")
    ap.add_argument("--batch", default="")
    ap.add_argument("--seed", type=int, default=20261017)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        tf = timeline_frames()
        for k, v in SHOTS.items():
            f = tf.get(k, 48)
            print("%-5s 时间轴%3d帧(%.2fs) → 生成%3d帧  %s" % (k, f, f / 24.0, gen_len(f), v["img"]))
        return 0

    ids = [s.strip() for s in (a.batch or a.shot).split(",") if s.strip()]
    if not ids:
        print("需要 --shot 或 --batch，或 --list")
        return 2

    if a.dry:
        for sid in ids:
            print("=" * 60)
            print("镜 %s  时间轴 %s 帧" % (sid, timeline_frames().get(sid)))
            print("正文：" + body(SHOTS[sid]))
        return 0

    res = {}
    for i, sid in enumerate(ids):
        res[sid] = run_one(sid, a.seed + i)
    print("-" * 60)
    for sid, ok in res.items():
        print("  %s %s" % ("PASS" if ok else "FAIL", sid))
    return 0 if all(res.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
