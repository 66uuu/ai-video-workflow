#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
nr_bridge —— AI 与本地 ComfyUI 之间的唯一连接层
================================================
零第三方依赖（只用 Python 标准库）。换电脑只改 config.json，本文件不用动。

它解决的四件事：
  1) 找得到本地工具   —— 自动探测 ComfyUI 目录 / python / ffmpeg
  2) 连得上           —— 强制绕代理（本机踩过的坑，见铁律 45）
  3) 说得清           —— 把「我要一张图」「我要一段视频」翻译成 ComfyUI 的 workflow JSON
  4) 拿得回           —— 提交 → 轮询 → 下载产出 → 落地到你指定的目录

典型用法：
    from nr_bridge import Comfy, build_t2i, build_i2v

    c = Comfy()
    print(c.health())                       # 服务活不活
    files = c.run(build_t2i("1girl, portrait, ..."), "out/")
    files = c.run(build_i2v("EP04/S01.png", "夜，……", frames=72), "out/")

命令行自测：
    python nr_bridge.py health
    python nr_bridge.py nodes
    python nr_bridge.py t2i --prompt "1girl, portrait" --out .
    python nr_bridge.py i2v --image 某图.png --prompt "夜，一个女子缓慢抬头，停住。" --frames 72 --out .
"""
import json
import os
import random
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

# ComfyUI history 里产出可能挂在这三个键下，不同保存节点不一样
OUTPUT_KEYS = ("images", "videos", "gifs")


# ─────────────────────────────────────────────────────────────
# 一、配置与路径探测
# ─────────────────────────────────────────────────────────────

def load_config(path=None):
    p = path or CONFIG_PATH
    if not os.path.isfile(p):
        raise SystemExit("找不到配置文件：%s" % p)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _first_existing(*cands):
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def _guess_comfy_roots():
    """按可能性从高到低给出候选 ComfyUI 目录"""
    cands = []
    # 1) 与本文件同级的兄弟目录（把包和 ComfyUI 放一起的情况）
    for up in (HERE, os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))):
        for name in ("ComfyUI", "comfyui", "ComfyUI_windows_portable"):
            cands.append(os.path.join(up, name))
    # 2) 各盘根目录
    for drive in ("E:", "D:", "F:", "C:"):
        for name in ("ComfyUI", "ComfyUI_windows_portable"):
            cands.append(os.path.join(drive + os.sep, name))
    # 3) 便携版常见嵌套
    for drive in ("E:", "D:", "F:"):
        cands.append(os.path.join(drive + os.sep, "ComfyUI_windows_portable", "ComfyUI"))
    # 判定标准：有 main.py 或 custom_nodes 目录
    return [c for c in cands if os.path.isdir(c)]


def resolve(cfg):
    """把 config 里所有 auto 填成真实路径。返回 cfg（原地改）"""
    comfy = cfg.setdefault("comfy", {})

    # ── ComfyUI 根目录
    if comfy.get("root", "auto") == "auto":
        hit = None
        for c in _guess_comfy_roots():
            if os.path.isfile(os.path.join(c, "main.py")) or os.path.isdir(os.path.join(c, "custom_nodes")):
                hit = c
                break
        comfy["root"] = hit or ""
        comfy["_root_autodetected"] = bool(hit)

    # ── python 解释器：优先本目录内的 venv，其次系统 python
    if comfy.get("python", "auto") == "auto":
        root = comfy.get("root") or ""
        cands = [
            os.path.join(root, "venv", "Scripts", "python.exe"),
            os.path.join(root, "venv", "bin", "python"),
            os.path.join(root, "python_embeded", "python.exe"),
            os.path.join(os.path.dirname(root), "python_embeded", "python.exe"),
            sys.executable,
        ]
        comfy["python"] = _first_existing(*cands) or sys.executable

    # ── 启动脚本
    if comfy.get("startup", "auto") == "auto":
        root = comfy.get("root") or ""
        comfy["startup"] = _first_existing(
            os.path.join(root, "启动.bat"),
            os.path.join(root, "run_nvidia_gpu.bat"),
            os.path.join(root, "run_cpu.bat"),
            os.path.join(os.path.dirname(root), "run_nvidia_gpu.bat"),
        ) or ""

    # ── ffmpeg
    if cfg.get("ffmpeg", "auto") == "auto":
        root = comfy.get("root") or ""
        cands = [
            os.path.join(root, "ffmpeg.exe"),
            os.path.join(os.path.dirname(root), "ffmpeg.exe"),
            r"C:\ffmpeg\bin\ffmpeg.exe",
        ]
        cfg["ffmpeg"] = _first_existing(*cands) or (shutil.which("ffmpeg") or "")

    # ── 产出目录
    if cfg.get("output_dir", "auto") == "auto":
        cfg["output_dir"] = os.path.join(r"你的桌面\AI产物", "_默认输出")
    os.makedirs(cfg["output_dir"], exist_ok=True)

    return cfg


# ─────────────────────────────────────────────────────────────
# 二、HTTP 层（强制绕代理）
# ─────────────────────────────────────────────────────────────

def _opener():
    """
    关键：本机所有 localhost 请求必须绕代理。
    不绕会报 upstream connect failed / 10061，极易被误判成「服务没起来」。
    见踩坑铁律 45。
    """
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


_OPENER = None


def _get_opener():
    global _OPENER
    if _OPENER is None:
        _OPENER = _opener()
    return _OPENER


def _http(url, data=None, headers=None, timeout=30, raw=False):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with _get_opener().open(req, timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read()[:800].decode("utf-8", "replace")
        raise RuntimeError("HTTP %s @ %s\n%s" % (e.code, url, detail))
    except urllib.error.URLError as e:
        raise RuntimeError(
            "连不上 %s\n原因：%s\n"
            "排查顺序：① ComfyUI 起了吗（浏览器开 %s）"
            "② 端口对吗（netstat -ano | findstr :8188）"
            "③ 已强制绕代理，若仍失败看防火墙" % (url, e.reason, url))
    return body if raw else json.loads(body.decode("utf-8"))


# ─────────────────────────────────────────────────────────────
# 三、ComfyUI 客户端
# ─────────────────────────────────────────────────────────────

class Comfy:
    def __init__(self, cfg=None, config_path=None):
        self.cfg = resolve(cfg or load_config(config_path))
        self.host = self.cfg["comfy"]["host"].rstrip("/")
        self.upload_subdir = self.cfg["comfy"].get("input_subdir", "NR_UPLOAD")

    # ── 3.1 健康与信息

    def health(self):
        """服务存活检查。返回 {alive, host, queue, root, python}"""
        out = {"alive": False, "host": self.host,
               "root": self.cfg["comfy"].get("root") or "(未探测到)",
               "python": self.cfg["comfy"].get("python", ""),
               "ffmpeg": self.cfg.get("ffmpeg") or "(未找到)"}
        try:
            q = self.queue()
            out["alive"] = True
            out["running"] = q["running"]
            out["pending"] = q["pending"]
        except Exception as e:
            out["error"] = str(e)
        return out

    def stats(self):
        """显存 / 设备信息"""
        return _http(self.host + "/system_stats",
                     timeout=self.cfg["comfy"]["timeout_connect"])

    def object_info(self):
        """全部节点定义（可能数 MB，缓存一次）"""
        if not hasattr(self, "_oi"):
            self._oi = _http(self.host + "/object_info", timeout=90)
        return self._oi

    def has_nodes(self, names):
        oi = self.object_info()
        return {n: (n in oi) for n in names}

    # ── 3.2 队列

    def queue(self):
        d = _http(self.host + "/queue", timeout=self.cfg["comfy"]["timeout_connect"])
        return {"running": len(d.get("queue_running") or []),
                "pending": len(d.get("queue_pending") or [])}

    def clear_queue(self):
        _http(self.host + "/queue", data=b"{}",
              headers={"Content-Type": "application/json"}, timeout=10)
        _http(self.host + "/interrupt", data=b"{}",
              headers={"Content-Type": "application/json"}, timeout=10)

    # ── 3.3 提交 / 等待 / 取回

    def submit(self, workflow, client_id=None, number=None):
        """
        number=None 排到队尾（默认，批量用这个）
        number=0    插到队首（调试/试跑用，只延迟正在跑的那个）
        """
        payload = {"prompt": workflow, "client_id": client_id or uuid.uuid4().hex}
        if number is not None:
            payload["number"] = number
        r = _http(self.host + "/prompt", data=json.dumps(payload).encode("utf-8"),
                  headers={"Content-Type": "application/json"},
                  timeout=self.cfg["comfy"]["timeout_submit"])
        if r.get("node_errors"):
            raise RuntimeError("工作流校验失败：%s" % json.dumps(r["node_errors"], ensure_ascii=False)[:800])
        return r["prompt_id"]

    def history(self, prompt_id):
        h = _http(self.host + "/history/%s" % prompt_id, timeout=30)
        return h.get(prompt_id)

    def wait(self, prompt_id, timeout=None, on_tick=None):
        """轮询直到完成。返回该 prompt 的 history 条目；超时/失败抛异常。"""
        tmo = timeout or self.cfg["comfy"]["timeout_wait"]
        iv = self.cfg["comfy"].get("poll_interval", 3)
        t0 = time.time()
        while True:
            e = self.history(prompt_id)
            if e:
                st = (e.get("status") or {})
                if st.get("status_str") == "error" or st.get("completed") is False and st.get("messages"):
                    msgs = st.get("messages") or []
                    if any(m and m[0] == "execution_error" for m in msgs):
                        raise RuntimeError("执行出错：%s" % json.dumps(msgs, ensure_ascii=False)[:800])
                if st.get("completed") or e.get("outputs"):
                    return e
            el = time.time() - t0
            if el > tmo:
                raise TimeoutError("等太久了（%.0fs > %.0fs），检查服务是否卡住" % (el, tmo))
            if on_tick:
                on_tick(el)
            time.sleep(iv)

    def fetch(self, entry, dst_dir, kinds=OUTPUT_KEYS):
        """从 history 条目下载全部产出文件到 dst_dir。返回本地路径列表。"""
        os.makedirs(dst_dir, exist_ok=True)
        saved = []
        outputs = entry.get("outputs") or {}
        for _nid, o in outputs.items():
            for key in kinds:
                for it in (o.get(key) or []):
                    fn = str(it.get("filename") or "")
                    if not fn:
                        continue
                    q = urllib.parse.urlencode({
                        "filename": fn,
                        "subfolder": it.get("subfolder", ""),
                        "type": it.get("type", "output"),
                    })
                    blob = _http("%s/view?%s" % (self.host, q), raw=True, timeout=180)
                    dst = os.path.join(dst_dir, os.path.basename(fn))
                    # 重名不覆盖
                    if os.path.exists(dst):
                        base, ext = os.path.splitext(dst)
                        dst = "%s_%s%s" % (base, uuid.uuid4().hex[:6], ext)
                    with open(dst, "wb") as f:
                        f.write(blob)
                    saved.append(dst)
        return saved

    def run(self, workflow, dst_dir=None, timeout=None, on_tick=None, number=None):
        """一站式：提交 → 等待 → 下载。返回落地文件路径列表。"""
        dst = dst_dir or self.cfg["output_dir"]
        pid = self.submit(workflow, number=number)
        entry = self.wait(pid, timeout=timeout, on_tick=on_tick)
        return self.fetch(entry, dst)

    def run_many(self, workflows, dst_dir=None, timeout=None, on_tick=None,
                 label=None):
        """
        批量跑：**先全部入队，再依次收片**。这是本包最重要的速度优化。

        为什么要这样：submit → 等 → submit 中间那段空闲期，ComfyUI 会把模型
        从显存卸掉，下一条又从零加载。实测（RTX 4060 / Wan2.2 TI2V-5B GGUF）：
            逐个跑：88 秒 / 条
            一次入队：第 1 条 160 秒（含加载），第 2 条起 24–27 秒  ← 快 3.5 倍
        镜头越多，省得越多。24 镜 EP04 从约 35 分钟降到约 12 分钟。

        workflows  工作流 dict 的列表
        label      可选的进度标签列表（与 workflows 等长），用于打印
        返回       与 workflows 等长的列表，每项是该条的本地文件路径列表
        """
        dst = dst_dir or self.cfg["output_dir"]
        pids = []
        for i, wf in enumerate(workflows):
            pids.append(self.submit(wf))
            if on_tick:
                on_tick(0, i + 1, "已入队 %d/%d" % (i + 1, len(workflows)))
        results = []
        t0 = time.time()
        for i, pid in enumerate(pids):
            tag = (label[i] if label and i < len(label) else "#%d" % (i + 1))
            entry = self.wait(pid, timeout=timeout)
            files = self.fetch(entry, dst)
            results.append(files)
            print("[%s] 完成 %d/%d  累计 %.0fs" % (
                tag, i + 1, len(pids), time.time() - t0), flush=True)
        return results

    # ── 3.4 首帧上传（I2V 的关键一步）

    def upload_image(self, path, name=None):
        """
        把本地图片传进 ComfyUI 的 input 目录，返回可被 LoadImage 引用的名字。
        返回形如 "NR_UPLOAD/abc_ref.png"。

        为什么不用「复制到 input 目录」这种土办法：换电脑后目录结构不同，
        复制会失败且报错难懂。走官方 /upload/image 接口最稳。
        """
        if not os.path.isfile(path):
            raise SystemExit("图片不存在：%s" % path)
        # 文件名必须是纯 ASCII，中文名会让 API 返回 400（见铁律 66）
        base, ext = os.path.splitext(name or os.path.basename(path))
        safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in base)
        if not safe or not safe.isascii():
            safe = "img_" + uuid.uuid4().hex[:8]
        safe = safe + (ext if ext.lower() in (".png", ".jpg", ".jpeg", ".webp") else ".png")

        boundary = "----nrbridge" + uuid.uuid4().hex
        with open(path, "rb") as f:
            blob = f.read()
        parts = []
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\ninput\r\n" % boundary).encode())
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"subfolder\"\r\n\r\n%s\r\n" % (boundary, self.upload_subdir)).encode())
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n" % boundary).encode())
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\n"
                      "Content-Type: image/png\r\n\r\n" % (boundary, safe)).encode())
        parts.append(blob)
        parts.append(("\r\n--%s--\r\n" % boundary).encode())
        body = b"".join(parts)

        r = _http(self.host + "/upload/image", data=body,
                  headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary},
                  timeout=120)
        sub = r.get("subfolder") or ""
        nm = r.get("name") or safe
        return ("%s/%s" % (sub, nm)) if sub else nm


# ─────────────────────────────────────────────────────────────
# 四、工作流构建器
# ─────────────────────────────────────────────────────────────

DEFAULT_NEG = ("lowres, bad anatomy, bad hands, text, watermark, signature, "
               "extra limbs, deformed, blurry, ugly, worst quality, jpeg artifacts")

# I2V 负向：显式禁运镜与换脸。
# 注意：不能写「没有 X」句式，会被模型读成「不要 X」（实测导致墨迹消失）
I2V_NEG = ("镜头推近，镜头拉远，变焦，摇镜，平移，构图漂移，人物出画，裁掉头部，只拍身体，"
           "换脸，长着另一张脸，发型改变，发色改变，服装改变，"
           "多余的手指，畸形的手，扭曲的脸，五官变形，"
           "字幕，水印，文字，logo，")
CAM_LOCK = "机位固定不动。"


def gen_len(frames):
    """Wan 要求 length = 4n+1。目标帧数上取到最近的 4n+1。见铁律 52。"""
    return ((frames - 1 + 3) // 4) * 4 + 1


def build_t2i(prompt, negative=None, width=512, height=768, steps=28, seed=None,
              cfg_scale=7.0, sampler="dpmpp_2m", scheduler="karras",
              checkpoint=None, prefix="NR/T2I"):
    """纯文生图。seed=None 时随机。"""
    ckpt = checkpoint or "majicmixRealistic_v7.safetensors"
    seed = random.randint(0, 2 ** 31 - 1) if seed is None else seed
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative if negative is not None else DEFAULT_NEG, "clip": ["4", 1]}},
        "3": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": cfg_scale,
                         "sampler_name": sampler, "scheduler": scheduler,
                         "denoise": 1.0, "model": ["4", 0],
                         "positive": ["6", 0], "negative": ["7", 0],
                         "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
    }


def build_t2i_ref(prompt, ref_image, ref_weight=0.5, negative=None,
                  width=512, height=768, steps=28, seed=None, cfg_scale=7.0,
                  checkpoint=None, clip_vision=None, ipadapter=None, prefix="NR/T2IREF"):
    """
    挂参考图保人物一致（IPAdapter）。

    ref_image 必须是 Comfy.upload_image() 返回的名字，形如 "NR_UPLOAD/xxx.png"。
    ref_weight 分级（实测，见铁律 64）：
        保脸 + 换场景        0.45–0.55
        保脸 + 同场景换机位  0.70–0.80
        只改表情（构图不变） 0.85–0.90
    """
    ckpt = checkpoint or "majicmixRealistic_v7.safetensors"
    cv = clip_vision or "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
    ipa = ipadapter or "ip-adapter-plus_sd15.safetensors"
    seed = random.randint(0, 2 ** 31 - 1) if seed is None else seed
    wf = build_t2i(prompt, negative, width, height, steps, seed, cfg_scale,
                   checkpoint=ckpt, prefix=prefix)
    wf["10"] = {"class_type": "LoadImage", "inputs": {"image": ref_image}}
    wf["11"] = {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": ipa}}
    wf["12"] = {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": cv}}
    wf["13"] = {"class_type": "IPAdapterAdvanced",
                "inputs": {"weight": ref_weight, "weight_type": "linear",
                           "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
                           "embeds_scaling": "V only",
                           "model": ["4", 0], "ipadapter": ["11", 0],
                           "image": ["10", 0], "clip_vision": ["12", 0]}}
    # 采样器的 model 改为经 IPAdapter 处理后的模型
    wf["3"]["inputs"]["model"] = ["13", 0]
    return wf


def build_i2v(image_input, prompt, frames=72, width=512, height=768, steps=24,
              cfg_scale=5.0, shift=8.0, seed=None, fps=24,
              sampler="euler", scheduler="simple",
              unet=None, clip=None, vae=None, prefix="NR/I2V"):
    """
    图生视频（Wan2.2 TI2V-5B GGUF）。

    prompt      四段式：动作 + 声景 + 配乐 + 镜头。程序自动追加「机位固定不动。」
                禁止写画风 / 长相 / 服装 / 姓名（见铁律 53/54）
    frames      目标帧数。内部自动上取 4n+1，出片后用 ffmpeg 裁回 frames。
    image_input Comfy.upload_image() 返回的名字

    sampler/scheduler  档位用的采样组合（默认 euler + simple 保持旧行为）：
        euler   + simple   最快，12 步够用        → draft
        uni_pc  + beta     20 步≈euler 24 步画质  → fast / std（推荐）
        dpmpp_2m+ karras   收敛最稳，28 步        → hq
    """
    unet = unet or "Wan2.2-TI2V-5B-Q5_K_M.gguf"
    clip = clip or "umt5-xxl-encoder-Q4_K_M.gguf"
    vae = vae or "wan2.2_vae.safetensors"
    seed = random.randint(0, 2 ** 31 - 1) if seed is None else seed
    body = prompt.rstrip()
    if "机位固定不动" not in body:
        body = body + " " + CAM_LOCK
    gl = gen_len(frames)
    return {
        "10": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": unet}},
        "11": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": clip, "type": "wan"}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "13": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["10", 0], "shift": shift}},
        "14": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": body}},
        "15": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": I2V_NEG}},
        "16": {"class_type": "LoadImage", "inputs": {"image": image_input}},
        "17": {"class_type": "Wan22ImageToVideoLatent",
               "inputs": {"vae": ["12", 0], "width": width, "height": height,
                          "length": gl, "batch_size": 1, "start_image": ["16", 0]}},
        "18": {"class_type": "KSampler",
               "inputs": {"seed": seed, "steps": steps, "cfg": cfg_scale,
                          "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0,
                          "model": ["13", 0], "positive": ["14", 0], "negative": ["15", 0],
                          "latent_image": ["17", 0]}},
        "19": {"class_type": "VAEDecode", "inputs": {"samples": ["18", 0], "vae": ["12", 0]}},
        "20": {"class_type": "CreateVideo",
               "inputs": {"images": ["19", 0], "fps": fps}},
        # format 必须是字符串。传 dict 会被校验层吃掉 → SaveVideo 缺参数（铁律 43）
        "21": {"class_type": "SaveVideo",
               "inputs": {"video": ["20", 0], "filename_prefix": prefix, "format": "mp4"}},
    }


def trim_video(src, dst, frames, ffmpeg=None):
    """把生成的多余帧裁掉，精确到 frames；没有 ffmpeg 直接失败。"""
    exe = ffmpeg or shutil.which("ffmpeg")
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    if not exe:
        raise RuntimeError("没找到 ffmpeg，不能保证输出帧数严格对齐")
    import subprocess
    r = subprocess.run([exe, "-y", "-i", src, "-frames:v", str(frames),
                        "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
                        dst, "-loglevel", "error"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("裁切失败：%s" % (r.stderr or "")[-400:])
    return dst


# ─────────────────────────────────────────────────────────────
# 五、命令行自测
# ─────────────────────────────────────────────────────────────

# 参数档位：速度 / 画质权衡。与 09_工具脚本/batch_local.py 的 PROFILES 保持一致。
PROFILES = {
    "draft": dict(width=384, height=576, steps=12, sampler="euler",    scheduler="simple"),
    "fast":  dict(width=448, height=672, steps=16, sampler="uni_pc",   scheduler="beta"),
    "std":   dict(width=512, height=768, steps=20, sampler="uni_pc",   scheduler="beta"),
    "hq":    dict(width=512, height=768, steps=28, sampler="dpmpp_2m", scheduler="karras"),
}


def _main():
    import argparse
    ap = argparse.ArgumentParser(description="nr_bridge 命令行自测")
    ap.add_argument("cmd", choices=["health", "nodes", "stats", "t2i", "i2v"])
    ap.add_argument("--prompt", default="")
    ap.add_argument("--negative", default=None)
    ap.add_argument("--image", default="")
    ap.add_argument("--ref", default="")
    ap.add_argument("--ref-weight", type=float, default=0.5)
    ap.add_argument("--frames", type=int, default=72)
    ap.add_argument("--width", type=int, default=0, help="0=用档位/默认值")
    ap.add_argument("--height", type=int, default=0, help="0=用档位/默认值")
    ap.add_argument("--steps", type=int, default=0)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default="")
    ap.add_argument("--profile", default="", choices=["", "draft", "fast", "std", "hq"],
                    help="参数档位：draft=最快 / fast=快 / std=均衡 / hq=画质优先")
    ap.add_argument("--sampler", default="", help="覆盖采样器：euler / uni_pc / dpmpp_2m")
    ap.add_argument("--scheduler", default="", help="覆盖调度器：simple / beta / karras")
    ap.add_argument("--cfg", type=float, default=0.0, help="覆盖 CFG，0=用默认")
    ap.add_argument("--shift", type=float, default=0.0, help="覆盖 shift，0=用默认")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--max-frames", type=int, default=0,
                    help="帧数上限，防止误跑 121 帧；0=不限制")
    a = ap.parse_args()

    # 档位先铺底，显式参数再覆盖。空串/0 表示"该子命令用自己的默认值"
    prof = dict(PROFILES.get(a.profile) or {})
    width = a.width or prof.get("width") or 512
    height = a.height or prof.get("height") or 768
    steps = a.steps or prof.get("steps") or 0
    sampler = a.sampler or prof.get("sampler") or ""
    scheduler = a.scheduler or prof.get("scheduler") or ""
    frames = a.frames
    if a.max_frames:
        frames = min(frames, a.max_frames)

    c = Comfy()

    if a.cmd == "health":
        h = c.health()
        print(json.dumps(h, ensure_ascii=False, indent=2))
        return

    if a.cmd == "stats":
        s = c.stats()
        devs = s.get("devices") or []
        for d in devs:
            print("%s  显存 总%.1fG 空闲%.1fG" % (
                d.get("name"),
                d.get("vram_total", 0) / 1024 ** 3,
                d.get("vram_free", 0) / 1024 ** 3))
        return

    if a.cmd == "nodes":
        cfg = c.cfg
        want = []
        for k, v in (cfg.get("required_nodes") or {}).items():
            if isinstance(v, list):
                want += v
        res = c.has_nodes(want)
        miss = [k for k, v in res.items() if not v]
        for k in want:
            print("%s %s" % ("✔" if res[k] else "✘", k))
        print("\n共 %d 个，缺 %d 个" % (len(want), len(miss)))
        sys.exit(1 if miss else 0)

    if a.cmd == "t2i":
        if not a.prompt:
            raise SystemExit("要给 --prompt")
        if a.ref:
            nm = c.upload_image(a.ref)
            wf = build_t2i_ref(a.prompt, nm, a.ref_weight, a.negative,
                               width, height, steps or 26, a.seed)
        else:
            wf = build_t2i(a.prompt, a.negative, width, height, steps or 28, a.seed,
                           sampler=sampler or "dpmpp_2m",
                           scheduler=scheduler or "karras")
        files = c.run(wf, a.out or c.cfg["output_dir"])
        for f in files:
            print(f)
        return

    if a.cmd == "i2v":
        if not (a.image and a.prompt):
            raise SystemExit("要给 --image 和 --prompt")
        nm = c.upload_image(a.image)
        print("首帧已上传：%s（目标 %d 帧 → 生成 %d 帧）" % (nm, frames, gen_len(frames)))
        print("参数：%dx%d  %d 步  %s / %s  cfg=%.1f" % (
            width, height, steps or 24, sampler or "euler", scheduler or "simple",
            a.cfg or 5.0))
        wf = build_i2v(nm, a.prompt, frames, width, height,
                       steps or 24,
                       cfg_scale=a.cfg or 5.0,
                       shift=a.shift or 8.0,
                       seed=a.seed, fps=a.fps,
                       sampler=sampler or "euler",
                       scheduler=scheduler or "simple")
        t0 = time.time()
        files = c.run(wf, a.out or c.cfg["output_dir"],
                      on_tick=lambda el: print("  … %.0fs" % el, end="\r", flush=True))
        print("\n完成 %.0fs" % (time.time() - t0))
        for f in files:
            print(f)
        return


if __name__ == "__main__":
    _main()
