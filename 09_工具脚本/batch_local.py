#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本地批量生成器 —— 支持任意项目，不经过任何外部额度
=====================================================================
它做的事：读项目镜头包里的提示词 → 逐镜推进本机 ComfyUI（127.0.0.1:8188）
→ 每镜出片后自动裁到时间轴帧数 → 自动质检 → 汇总报告。

特性：
  · 断点续跑：已存在的镜头自动跳过，断电/中断后重跑不会重算
  · 帧数唯一真源：从项目时间轴取，自动向上取到 4n+1（Wan 要求）
  · 质检内建：相邻帧差 / 首末帧差 / 出画检测，不过关的镜标 FAIL
  · 日志落盘：_logs/batch_YYYYmmdd_HHMM.log

用法（也可以直接双击 bat）：
  python batch_local.py                  # 跑全部可拍镜
  python batch_local.py --only S24A,S20A # 只跑指定镜
  python batch_local.py --force          # 已存在的也重跑
  python batch_local.py --list           # 只打印提示词，不生成
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

from project_paths import ProjectPaths

HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
COMFY = os.environ.get("COMFY_ROOT") or next(
    (p for p in (r"ComfyUI", r"源机器E盘ComfyUI") if os.path.isdir(p)), r"ComfyUI")
IN_SUB = os.environ.get("NR_INPUT_SUBDIR", "NR_I2V")
# ComfyUI 的输入/输出目录可单独指定：在受限沙箱或只想隔离读写时用
COMFY_IN = os.environ.get("COMFY_IN_DIR") or os.path.join(COMFY, "input")
COMFY_OUT = os.environ.get("COMFY_OUT_DIR") or os.path.join(COMFY, "output")
PROJECT = ProjectPaths()
EPISODE = PROJECT.episode
EPDIR = str(PROJECT.root)
LOCK = str(PROJECT.lock_dir)
VIDDIR = str(PROJECT.video_dir)
LOGDIR = str(PROJECT.log_dir)
# 临时落盘目录（_raw_*.mp4）：默认跟原片同目录；也可用 I2V_RAW_DIR 指到高速盘。
RAW_DIR = os.environ.get("I2V_RAW_DIR") or VIDDIR
REWORK_MD = str(PROJECT.rework_md)
REWORK_JSON = str(PROJECT.rework_json)
FFMPEG = (os.environ.get("FFMPEG")
          or next((p for p in (r"源机器E盘ffmpeg_bin\ffmpeg.exe", r"ComfyUI\ffmpeg.exe",
                               r"<D盘>\ffmpeg\bin\ffmpeg.exe") if os.path.exists(p)), None)
          or shutil.which("ffmpeg") or "ffmpeg")

TIMELINE = str(PROJECT.timeline)
SHOTS_FILE = str(PROJECT.shots)
SUBMIT_LOG = str(PROJECT.submit_log)


CAM_LOCK = "机位固定不动。"

# 负向：显式禁运镜与换脸。注意不能写「没有 X」句式（会被模型读成「不要 X」）
NEG = ("镜头推近，镜头拉远，变焦，摇镜，平移，构图漂移，人物出画，裁掉头部，只拍身体，"
       "换脸，长着另一张脸，发型改变，发色改变，服装改变，"
       "多余的手指，畸形的手，扭曲的脸，五官变形，"
       "字幕，水印，文字，logo，"
       "过曝，整体发灰，低质量，最差质量，JPEG压缩残留，杂乱的背景，多重人影，闪烁")

LOG = []


def log(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(str(msg).encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)
    LOG.append(msg)


def apply_project_paths(args):
    """在读取镜头包前应用命令行项目路径，彻底避免脚本锁死 EP04。"""
    global PROJECT, EPISODE, EPDIR, LOCK, VIDDIR, LOGDIR, RAW_DIR
    global REWORK_MD, REWORK_JSON, TIMELINE, SHOTS_FILE, SUBMIT_LOG, IN_SUB
    PROJECT = ProjectPaths(
        project_root=args.project_root,
        episode=args.episode,
        timeline=args.timeline,
        shots=args.shots,
        video_dir=args.video_dir,
        lock_dir=args.lock_dir,
        log_dir=args.log_dir,
        output_dir=args.output_dir,
    )
    EPISODE = PROJECT.episode
    EPDIR = str(PROJECT.root)
    LOCK = str(PROJECT.lock_dir)
    VIDDIR = str(PROJECT.video_dir)
    LOGDIR = str(PROJECT.log_dir)
    RAW_DIR = os.environ.get("I2V_RAW_DIR") or VIDDIR
    REWORK_MD = str(PROJECT.rework_md)
    REWORK_JSON = str(PROJECT.rework_json)
    TIMELINE = str(PROJECT.timeline)
    SHOTS_FILE = str(PROJECT.shots)
    SUBMIT_LOG = str(PROJECT.submit_log)
    IN_SUB = os.environ.get("NR_INPUT_SUBDIR", PROJECT.input_subdir)


def save_json_atomic(path, value):
    """提交记录等状态文件先落临时文件，再替换，避免中断留下半个 JSON。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(value, fp, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def api(path, payload=None, timeout=60):
    url = HOST + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 本机，绕过代理
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check_server():
    try:
        api("/system_stats", timeout=5)
        return True
    except Exception:
        log("✗ 连不上 ComfyUI（%s）。请先启动：%s，再运行本脚本。" %
            (HOST, os.path.join(COMFY, "启动.bat")))
        return False


def gen_len(frames):
    return ((frames - 1 + 3) // 4) * 4 + 1


def body(shot):
    return "%s %s %s %s %s" % (
        shot.get("action", "保持主体稳定，完成一个清晰的小动作"),
        shot.get("sound", ""), shot.get("music", ""), shot.get("lens", "中景"), CAM_LOCK)


def build(shot, m, length, seed):
    in_name = "%s_%s.png" % (shot["id"], os.path.basename(shot["img"]).replace("_v01.png", ""))
    return in_name, {
        "10": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": m["unet"]}},
        "11": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": m["clip"],
                                                          "type": m["text_encoder_type"]}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": m["vae"]}},
        "13": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["10", 0], "shift": m["shift"]}},
        "14": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": body(shot)}},
        "15": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": NEG}},
        "16": {"class_type": "LoadImage", "inputs": {"image": "%s/%s" % (IN_SUB, in_name)}},
        "20": {"class_type": "Wan22ImageToVideoLatent", "inputs": {
            "vae": ["12", 0], "width": m["width"], "height": m["height"], "length": length,
            "batch_size": 1, "start_image": ["16", 0]}},
        "21": {"class_type": "KSampler", "inputs": {
            "model": ["13", 0], "seed": seed, "steps": m["steps"], "cfg": m["cfg"],
            "sampler_name": m["sampler"], "scheduler": m["scheduler"],
            "positive": ["14", 0], "negative": ["15", 0],
            "latent_image": ["20", 0], "denoise": 1.0}},
        "22": {"class_type": "VAEDecode", "inputs": {"samples": ["21", 0], "vae": ["12", 0]}},
        "23": {"class_type": "CreateVideo", "inputs": {"images": ["22", 0], "fps": float(m["fps"])}},
        "24": {"class_type": "SaveVideo", "inputs": {
            "video": ["23", 0], "filename_prefix": "NR/%s_I2V/%s" % (EPISODE, shot["id"]),
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
                raise RuntimeError(json.dumps(st.get("messages") or [], ensure_ascii=False)[-600:])
        time.sleep(2)
    raise TimeoutError("超时")


def grab(hist):
    for _, node_out in (hist.get("outputs") or {}).items():
        for key in ("images", "videos", "gifs"):
            for v in (node_out.get(key) or []):
                fn = str(v.get("filename", ""))
                if fn.endswith(".mp4"):
                    return os.path.join(COMFY_OUT, v.get("subfolder", ""), fn)
    return None


def trim(src, dst, frames):
    subprocess.run([FFMPEG, "-y", "-i", src, "-frames:v", str(frames),
                    "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                    "-an", dst, "-loglevel", "error"], check=True)


def _find_av_python():
    """找一个装了 PyAV 的 Python。质检需要 av+numpy，受管 Python 通常没有。"""
    cands = [os.path.join(COMFY, "venv", "Scripts", "python.exe"),
             os.path.join(COMFY, "python_embeded", "python.exe"),
             sys.executable]
    for p in cands:
        if p and os.path.exists(p):
            try:
                r = subprocess.run([p, "-c", "import av, numpy"],
                                   capture_output=True, timeout=30)
                if r.returncode == 0:
                    return p
            except Exception:
                pass
    return None


PY_AV = None   # 懒加载，避免每次 import 都探测


def _qa_via_subprocess(path, want):
    """用有 av 的 Python 跑 _qa_check.py，再把结果翻成结构化指标。"""
    global PY_AV
    if PY_AV is None:
        PY_AV = _find_av_python() or ""
    if not PY_AV:
        return False, "QA失败(没找到装了 av 的 Python，质检未执行)", {}
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_qa_check.py")
    try:
        r = subprocess.run([PY_AV, script, path, str(want)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
    except Exception as e:
        return False, "QA失败(%s)" % str(e)[:80], {}
    ok = r.returncode == 0
    out = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"(\d+)帧.*?相邻帧差\s*([\d.]+).*?首末\s*(-?[\d.]+).*?(出画!|在画)", out, re.S)
    if m:
        mt = dict(frames=int(m.group(1)), step=float(m.group(2)),
                  ends=float(m.group(3)), hollow=(m.group(4) == "出画!"))
        rep = "%d帧 | 相邻%.2f | 首末%.2f | %s" % (
            mt["frames"], mt["step"], mt["ends"], m.group(4))
        return ok, rep, mt
    return ok, ("QA通过" if ok else "QA失败") + "：" + out.strip().replace("\n", " ")[-80:], {}


def qa(path, want):
    """G1 帧数 / G2 真运动 / G3 不出画 → (是否通过, 人话, 指标dict)"""
    try:
        import av
        import numpy as np
    except ImportError:
        # 受管 Python 没有 av → 交给 ComfyUI 的 venv 跑，不要静默跳过
        return _qa_via_subprocess(path, want)
    try:
        fr = [f.to_ndarray(format="gray").astype(np.float32) for f in av.open(path).decode(video=0)]
        n = len(fr)

        def d(i, j):
            return float(np.abs(fr[i] - fr[j]).mean())

        step = [d(i, i + 1) for i in range(0, n - 1, 6)]
        m_step, m_ends = sum(step) / len(step), d(0, n - 1)

        def edge(a):
            h, w = a.shape
            return float(np.concatenate([a[:, : w // 6].ravel(), a[:, -w // 6:].ravel()]).std())

        hollow = edge(fr[-1]) < edge(fr[0]) * 0.55
        ok = (n == want) and m_step >= 0.30 and m_ends >= 1.5 and not hollow
        mt = dict(frames=n, step=m_step, ends=m_ends, hollow=hollow)
        return ok, "%d帧 | 相邻%.2f | 首末%.2f | %s" % (
            n, m_step, m_ends, "出画!" if hollow else "在画"), mt
    except Exception as e:
        return False, "QA失败(%s)" % str(e)[:80], {}


def drift_all(paths, fast=False):
    """跑 drift_check.py --json，返回 {文件名: {ncc_end,...}}。没有 av 就返回空。
    fast=True 用粗搜索（(12,4) 而非 (24,2)），速度快约 4 倍，精度足够做粗筛。"""
    global PY_AV
    if PY_AV is None:
        PY_AV = _find_av_python() or ""
    if not PY_AV or not paths:
        return {}
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drift_check.py")
    try:
        r = subprocess.run([PY_AV, script, "--json"] + (["--fast"] if fast else []) + paths,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=3600)
        return {os.path.basename(x["path"]): x for x in json.loads(r.stdout or "[]")}
    except Exception as e:
        log("漂移检测跳过：%s" % str(e)[:80])
        return {}


def write_rework(rows, with_drift=True):
    """把质检结果写成《重做清单.md / .json》。rows: [{shot,frames,ok,rep,mt,drift}]"""
    bad = [r for r in rows if not r["ok"]]
    if with_drift:
        bad += [r for r in rows if r["ok"] and r.get("ncc") is not None and r["ncc"] < 0.70]
    seen = set()
    uniq = []
    for r in bad:
        if r["shot"] in seen:
            continue
        seen.add(r["shot"])
        uniq.append(r)

    def why(r):
        mt = r.get("mt") or {}
        out = []
        if not mt:
            return r.get("rep") or "质检未通过"
        if mt.get("step") is not None and mt["step"] < 0.05:
            out.append("占位静止帧（相邻 %.2f，帧间几乎不变，不是真 I2V 输出）" % mt["step"])
        elif mt.get("step") is not None and mt["step"] < 0.30:
            out.append("运动不足/滑片（相邻 %.2f < 0.30）" % mt["step"])
        if mt.get("frames") is not None and mt["frames"] != r["frames"]:
            out.append("帧数不符（要 %d，实测 %d）" % (r["frames"], mt["frames"]))
        if mt.get("ends") is not None and mt["ends"] < 1.5:
            out.append("首末差过小（%.2f < 1.5）" % mt["ends"])
        if mt.get("hollow"):
            out.append("主体出画（末帧边带塌陷）")
        if r.get("ncc") is not None and r["ncc"] < 0.70:
            out.append("主体变形（NCC %.2f < 0.70）" % r["ncc"])
        return "；".join(out) or "质检未通过"

    def fix(r):
        mt = r.get("mt") or {}
        if mt.get("hollow"):
            return "改小动作幅度，避免走出画面；或缩短帧数"
        if mt.get("step") is not None and mt["step"] < 0.05:
            return "该条是占位/静止帧，加动作提示没用：补首帧后重新提交生成（--force）"
        if mt.get("step") is not None and mt["step"] < 0.30:
            return "动作太静：加一个可见的小动作，或换 --profile std（uni_pc+beta）"
        if r.get("ncc") is not None and r["ncc"] < 0.70:
            return "缩短到 49–65 帧；避开全身景别；首帧先修脸"
        if mt.get("frames") is not None and mt["frames"] != r["frames"]:
            return "重收片并裁到时间轴帧数"
        return "重跑该镜"

    L = ["# %s 重做清单（自动生成）\n" % EPISODE,
         "> 生成时间 %s ｜ 来源：`batch_local.py --qa-all`" % time.strftime("%Y-%m-%d %H:%M"),
         "> 判据：帧数对齐 / 相邻帧差≥0.30 / 首末帧差≥1.5 / 不出画 / NCC≥0.70（0.70–0.85 轻漂，<0.70 主体变形）\n",
         "## 需重做（%d 镜）\n" % len(uniq)]
    if uniq:
        L += ["| 镜号 | 原因 | 实测 | 建议 | 命令 |", "|---|---|---|---|---|"]
        for r in uniq:
            L.append("| %s | %s | %s | %s | `python batch_local.py --only %s --force` |" % (
                r["shot"], why(r), r.get("rep", ""), fix(r), r["shot"]))
    else:
        L.append("无。全部达标。")
    if with_drift:
        warn = [r for r in rows if r.get("ncc") is not None
                and 0.70 <= r["ncc"] < 0.85]
        if warn:
            L += ["\n## 轻漂（可选重跑，不拦交付）\n",
                  "| 镜号 | NCC | 说明 |", "|---|---|---|"]
            for r in sorted(warn, key=lambda x: x["shot"]):
                L.append("| %s | %.3f | 末段主体略变形，能看但不稳；有空再缩短帧数重跑 |"
                         % (r["shot"], r["ncc"]))
    L += ["\n## 全部实测\n", "| 镜号 | 要求帧 | 实测帧 | 相邻 | 首末 | 出画 | NCC | 判定 |",
          "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: x["shot"]):
        mt = r.get("mt") or {}
        L.append("| %s | %d | %s | %s | %s | %s | %s | %s |" % (
            r["shot"], r["frames"],
            mt.get("frames", "—"),
            "%.2f" % mt["step"] if mt.get("step") is not None else "—",
            "%.2f" % mt["ends"] if mt.get("ends") is not None else "—",
            "是" if mt.get("hollow") else ("否" if mt else "—"),
            "%.3f" % r["ncc"] if r.get("ncc") is not None else "—",
            "PASS" if r["ok"] else "FAIL"))
    def _safe_write(path, text):
        """先写临时文件再替换；被占用时退回直写，再不行写 .new 保证不丢结果"""
        tmp = path + ".tmp"
        for i in range(10):
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(text)
                os.replace(tmp, path)
                return True
            except Exception:
                time.sleep(0.6)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return True
        except Exception:
            alt = path + ".new"
            try:
                with open(alt, "w", encoding="utf-8") as f:
                    f.write(text)
                log("⚠ %s 被占用，已写到 %s" % (os.path.basename(path), alt))
                return False
            except Exception:
                log("✗ 写不进 %s（可能被杀软或编辑器占用）" % path)
                return False

    _safe_write(REWORK_MD, "\n".join(L) + "\n")
    _safe_write(REWORK_JSON, json.dumps(
        [{k: v for k, v in r.items() if k != "mt"} | {"metrics": r.get("mt")}
         for r in rows], ensure_ascii=False, indent=1, default=str))
    return uniq


def qa_all(with_drift=True, drift_fast=False):
    """对 VIDDIR 里所有已存在的原片做全量质检，写重做清单。不依赖 ComfyUI。"""
    tl = {s["shot_id"]: s["frames"] for s in
          json.load(open(TIMELINE, encoding="utf-8"))["shots"]}
    rows = []
    for sid, frames in sorted(tl.items()):
        p = os.path.join(VIDDIR, "%s_i2v.mp4" % sid)
        if not os.path.exists(p):
            log("[%s] ✗ 缺原片" % sid)
            rows.append(dict(shot=sid, frames=frames, ok=False, rep="缺原片", mt={}))
            continue
        good, rep, mt = qa(p, frames)
        log("[%s] %s %s" % (sid, "✅" if good else "⚠️", rep))
        rows.append(dict(shot=sid, frames=frames, ok=good, rep=rep, mt=mt,
                         path=p, ncc=None))
    if with_drift:
        # 只对「有真实运动」的片子跑漂移：静止帧的 NCC 恒等于 1，跑了也没信息量
        cand = [r for r in rows if r.get("path") and r["ok"]]
        dm = drift_all([r["path"] for r in cand], fast=drift_fast)
        for r in cand:
            d = dm.get(os.path.basename(r["path"]))
            if d and d.get("ncc_end") is not None:
                r["ncc"] = d["ncc_end"]
    uniq = write_rework(rows, with_drift)
    log("-" * 68)
    log("全量质检 %d 镜：需重做 %d 镜" % (len(rows), len(uniq)))
    log("清单：%s" % REWORK_MD)
    return 0 if not uniq else 1


def submit_all(shots, m, tl, seed, force=False):
    """只提交不等待：把全部镜头一次性压进 ComfyUI 队列。
    好处是——即使本脚本退出，ComfyUI 自己会把队列跑完。"""
    os.makedirs(os.path.join(COMFY_IN, IN_SUB), exist_ok=True)
    os.makedirs(VIDDIR, exist_ok=True)
    rec = {}
    for i, s in enumerate(shots):
        sid = s["id"]
        frames = tl.get(sid)
        if not frames:
            log("[%s] ✗ 无时间轴帧数" % sid)
            continue
        if os.path.exists(os.path.join(VIDDIR, "%s_i2v.mp4" % sid)) and not force:
            log("[%s] ⏭ 已存在，不提交" % sid)
            continue
        src = str(PROJECT.resolve_asset(s["img"]))
        if not os.path.exists(src):
            log("[%s] ✗ 首帧缺失" % sid)
            continue
        length = gen_len(frames)
        in_name, wf = build(s, m, length, seed + i)
        shutil.copy2(src, os.path.join(COMFY_IN, IN_SUB, in_name))
        pid = api("/prompt", {"prompt": wf, "client_id": "%s_local" % EPISODE.lower()})["prompt_id"]
        rec[sid] = {"prompt_id": pid, "frames": frames}
        log("[%s] 已入队 %d帧→%d帧  pid=%s" % (sid, frames, length, pid[:8]))
    old = {}
    if os.path.exists(SUBMIT_LOG):
        try:
            old = json.load(open(SUBMIT_LOG, encoding="utf-8"))
        except Exception:
            old = {}
    old.update(rec)
    save_json_atomic(SUBMIT_LOG, old)
    log("-" * 68)
    log("已提交 %d 镜。ComfyUI 会自己按顺序跑完，关掉本窗口也不影响。" % len(rec))
    log("跑完后运行：batch_local.py --collect")
    return 0


def collect(with_drift=False, force=False):
    """从 ComfyUI 历史里收片 → 裁到时间轴帧数 → 全量质检 → 写重做清单"""
    if not os.path.exists(SUBMIT_LOG):
        log("没有提交记录，先跑 --submit-only")
        return 2
    rec = json.load(open(SUBMIT_LOG, encoding="utf-8"))
    wait_n = 0
    for sid, info in rec.items():
        dst = os.path.join(VIDDIR, "%s_i2v.mp4" % sid)
        if os.path.exists(dst) and not force:
            log("[%s] ⏭ 已收" % sid)
            continue
        h = api("/history/%s" % info["prompt_id"])
        if info["prompt_id"] not in h:
            log("[%s] … 还在排队/渲染" % sid)
            wait_n += 1
            continue
        out = grab(h[info["prompt_id"]])
        if not out or not os.path.exists(out):
            log("[%s] ✗ 历史里没有 mp4" % sid)
            continue
        raw = os.path.join(RAW_DIR, "_raw_%s.mp4" % sid)
        os.makedirs(RAW_DIR, exist_ok=True)
        shutil.copy2(out, raw)
        trim(raw, dst, info["frames"])
        os.remove(raw)
        log("[%s] 已收 %d帧" % (sid, info["frames"]))
    log("-" * 68)
    log("收片完成 / 仍在渲染 %d 镜。开始全量质检…" % wait_n)
    return qa_all(with_drift=with_drift)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=os.environ.get("NR_PROJECT_ROOT", ""),
                    help="项目根目录；默认使用本工作流目录")
    ap.add_argument("--episode", default=os.environ.get("NR_EPISODE", ""),
                    help="集数/项目编号，如 EP05")
    ap.add_argument("--timeline", default=os.environ.get("NR_TIMELINE", ""))
    ap.add_argument("--shots", default=os.environ.get("NR_SHOTS", ""))
    ap.add_argument("--video-dir", default=os.environ.get("NR_VIDEO_DIR", ""))
    ap.add_argument("--lock-dir", default=os.environ.get("NR_LOCK_DIR", ""))
    ap.add_argument("--log-dir", default=os.environ.get("NR_LOG_DIR", ""))
    ap.add_argument("--output-dir", default=os.environ.get("NR_OUTPUT_DIR", ""),
                    help="交付目录；仅用于记录项目配置")
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--seed", type=int, default=20261018)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--submit-only", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--qa-all", action="store_true",
                    help="不连 ComfyUI，只对已有原片做全量质检并写重做清单")
    ap.add_argument("--redo", action="store_true",
                    help="按重做清单.json 里 FAIL 的镜号自动重跑（等价于 --only 那些镜 + --force）")
    ap.add_argument("--with-drift", action="store_true",
                    help="质检时附带漂移检测（NCC），约慢 4 倍")
    ap.add_argument("--drift-fast", action="store_true",
                    help="配合 --with-drift：用粗搜索(12,4)跑 NCC，约快 4 倍")
    ap.add_argument("--profile", default="",
                    choices=["", "draft", "fast", "std", "hq"],
                    help="参数档位：draft=快5倍 / fast=快1.9倍 / std=均衡 / hq=画质优先")
    ap.add_argument("--draft", action="store_true",
                    help="等价于 --profile draft（保留旧用法）")
    ap.add_argument("--steps", type=int, default=0, help="覆盖步数（0=用档位/镜表的值）")
    ap.add_argument("--height", type=int, default=0, help="覆盖高度（宽度按 2:3 自动算，16 的倍数）")
    ap.add_argument("--sampler", default="", help="覆盖采样器，如 uni_pc / dpmpp_2m / euler")
    ap.add_argument("--scheduler", default="", help="覆盖调度器，如 beta / karras / simple")
    ap.add_argument("--cfg", type=float, default=0.0, help="覆盖 cfg（0=用档位/镜表的值）")
    ap.add_argument("--max-frames", type=int, default=0,
                    help="帧数上限（防止误跑 121 帧；0=不限制）")
    a = ap.parse_args()

    apply_project_paths(a)

    if not os.path.exists(TIMELINE):
        log("✗ 找不到时间轴：%s" % TIMELINE)
        return 1
    if not os.path.exists(SHOTS_FILE):
        log("✗ 找不到镜头包：%s" % SHOTS_FILE)
        return 1

    pack = json.load(open(SHOTS_FILE, encoding="utf-8"))
    m = pack.get("model")
    if not m:
        log("✗ 镜头包缺少 model 参数：%s" % SHOTS_FILE)
        return 1

    # ── 参数档位（不传参时行为与原来完全一致）──────────────────
    # uni_pc + beta 在 20 步左右通常能追平 euler + simple 24~28 步的画质，
    # 所以 std 档用 20 步反而比原来的 24 步更快、且不一定更差。
    PROFILES = {
        "draft": dict(width=384, height=576, steps=12, sampler="euler", scheduler="simple"),
        "fast":  dict(width=448, height=672, steps=16, sampler="uni_pc", scheduler="beta"),
        "std":   dict(width=512, height=768, steps=20, sampler="uni_pc", scheduler="beta"),
        "hq":    dict(width=512, height=768, steps=28, sampler="dpmpp_2m", scheduler="karras"),
    }
    prof = a.profile or ("draft" if a.draft else "")
    if prof:
        m = dict(m)
        m.update(PROFILES[prof])
    if a.steps:
        m = dict(m)
        m["steps"] = a.steps
    if a.height:
        m = dict(m)
        m["height"] = a.height
        m["width"] = max(256, int(round(a.height * 2.0 / 3.0 / 16.0)) * 16)
    if a.sampler:
        m = dict(m)
        m["sampler"] = a.sampler
    if a.scheduler:
        m = dict(m)
        m["scheduler"] = a.scheduler
    if a.cfg:
        m = dict(m)
        m["cfg"] = a.cfg
    tl = {s["shot_id"]: s["frames"] for s in
          json.load(open(TIMELINE, encoding="utf-8"))["shots"]}
    if a.max_frames:
        tl = {k: min(v, a.max_frames) for k, v in tl.items()}
    shots = pack["shots"]
    if a.only:
        keep = {s.strip() for s in a.only.split(",")}
        shots = [s for s in shots if s["id"] in keep]

    if a.redo:
        if not os.path.exists(REWORK_JSON):
            log("✗ 没有重做清单，先跑：python batch_local.py --qa-all")
            return 1
        try:
            bad = {r["shot"] for r in json.load(open(REWORK_JSON, encoding="utf-8"))
                   if not r.get("ok") or
                   (r.get("ncc") is not None and r.get("ncc") < 0.70)}
        except Exception as e:
            log("✗ 重做清单读不了：%s" % str(e)[:60])
            return 1
        if not bad:
            log("✓ 重做清单里没有 FAIL，不用重跑")
            return 0
        shots = [s for s in pack["shots"] if s["id"] in bad]
        a.force = True
        no_src = sorted(bad - {s["id"] for s in shots})
        log("按重做清单重跑 %d 镜：%s" % (len(shots), ", ".join(s["id"] for s in shots)))
        if no_src:
            log("⚠ 以下镜号在提示词包里没有 K4（缺首帧），本次跳过：%s" % ", ".join(no_src))

    if a.qa_all:
        return qa_all(with_drift=a.with_drift, drift_fast=a.drift_fast)

    if a.collect:
        if not check_server():
            return 2
        return collect(with_drift=a.with_drift, force=a.force)

    if a.list:
        for s in shots:
            f = tl.get(s["id"], 48)
            print("\n[%s] %d帧(%.2fs) → 生成%d帧  %s" %
                  (s["id"], f, f / 24.0, gen_len(f), s["img"]))
            print("  提示词：" + body(s))
        print("\n可拍 %d 镜 / 待补关键帧 %d 镜" %
              (len(pack["shots"]), len(pack.get("blocked", []))))
        return 0

    if not check_server():
        return 2

    if a.submit_only:
        return submit_all(shots, m, tl, a.seed, a.force)

    os.makedirs(os.path.join(COMFY_IN, IN_SUB), exist_ok=True)
    os.makedirs(VIDDIR, exist_ok=True)
    os.makedirs(LOGDIR, exist_ok=True)

    log("=" * 68)
    log("%s 本地批量生成 · %d 镜 · ComfyUI %s" % (EPISODE, len(shots), HOST))
    log("=" * 68)

    ok, fail, skip = [], [], []
    t_all = time.time()
    # ── 第一段：全部先入队 ────────────────────────────────────
    # ★ 关键优化（实测）：submit→等→submit 中间那段空闲，ComfyUI 会把模型
    #   从显存卸掉，下一条又从零加载（约 36–70 秒白白浪费）。
    #   一次性把全部镜头压进队列，任务之间没有空闲期，模型常驻，
    #   实测第 2 条起每条从 88 秒降到 25 秒（快 3.5 倍）。
    queue = []
    for i, s in enumerate(shots):
        sid = s["id"]
        frames = tl.get(sid)
        if not frames:
            log("[%s] ✗ 时间轴无此镜，跳过" % sid)
            fail.append((sid, "无时间轴帧数"))
            continue
        dst = os.path.join(VIDDIR, "%s_i2v.mp4" % sid)
        if os.path.exists(dst) and not a.force:
            log("[%s] ⏭ 已存在，跳过（要重跑加 --force）" % sid)
            skip.append(sid)
            continue

        length = gen_len(frames)
        src = str(PROJECT.resolve_asset(s["img"]))
        if not os.path.exists(src):
            log("[%s] ✗ 首帧不存在：%s" % (sid, src))
            fail.append((sid, "首帧缺失"))
            continue

        in_name, wf = build(s, m, length, a.seed + i)
        for _try in range(6):
            try:
                shutil.copy2(src, os.path.join(COMFY_IN, IN_SUB, in_name))
                break
            except PermissionError as e:
                if _try == 5:
                    log("[%s] ✗ 首帧复制被占用（%s），关掉图片预览/杀软后再跑" % (sid, in_name))
                    fail.append((sid, "复制首帧被占用"))
                    raise SystemExit(1)
                time.sleep(1.0)
        try:
            pid = api("/prompt", {"prompt": wf, "client_id": "%s_local" % EPISODE.lower()})["prompt_id"]
            queue.append((sid, pid, frames, dst))
            log("[%s] 已入队 %d帧→%d帧  %dx%d %d步" %
                (sid, frames, length, m["width"], m["height"], m["steps"]))
        except Exception as e:
            log("[%s] ✗ 入队失败 %s" % (sid, str(e)[-160:]))
            fail.append((sid, str(e)[:120]))

    log("-" * 68)
    log("已入队 %d 镜，开始按顺序收片（模型常驻，后续每条更快）" % len(queue))

    # ── 第二段：依次等待 + 收片 + 裁切 + 质检 ────────────────
    for n, (sid, pid, frames, dst) in enumerate(queue, 1):
        t0 = time.time()
        try:
            hist = wait(pid)
            out = grab(hist)
            if not out or not os.path.exists(out):
                raise RuntimeError("没拿到 mp4")
            raw = os.path.join(RAW_DIR, "_raw_%s.mp4" % sid)
            os.makedirs(RAW_DIR, exist_ok=True)
            shutil.copy2(out, raw)
            trim(raw, dst, frames)
            os.remove(raw)
            good, rep, _mt = qa(dst, frames)
            log("[%d/%d][%s] %s %s  (%.0fs)" % (
                n, len(queue), sid, "✅" if good else "⚠️", rep, time.time() - t0))
            (ok if good else fail).append(sid if good else (sid, rep))
        except Exception as e:
            log("[%d/%d][%s] ✗ %s" % (n, len(queue), sid, str(e)[-200:]))
            fail.append((sid, str(e)[:120]))

    log("-" * 68)
    log("成功 %d / 失败 %d / 跳过 %d  总耗时 %.1f 分钟" %
        (len(ok), len(fail), len(skip), (time.time() - t_all) / 60))
    if fail:
        for f in fail:
            log("  ✗ %s  %s" % f if isinstance(f, tuple) else "  ✗ %s" % f)

    stamp = time.strftime("%Y%m%d_%H%M")
    with open(os.path.join(LOGDIR, "batch_%s.log" % stamp), "w", encoding="utf-8") as f:
        f.write("\n".join(LOG))
    log("日志：%s" % os.path.join(LOGDIR, "batch_%s.log" % stamp))
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
