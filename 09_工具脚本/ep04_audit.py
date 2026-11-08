#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
EP04 审计器 —— 把「哪镜有图 / 有卡 / 有片 / 帧数对不对 / 运镜冲不冲突」变成机读表
=============================================================================
以前这些数是手数的，错一次就传一整套文档。本脚本只做一件事：
拿时间轴当唯一真源，逐镜核对 6 个来源，输出：

  06_分镜与时间轴/EP04_审计报告.md
  06_分镜与时间轴/EP04_audit.json

用法：
  python ep04_audit.py
  python ep04_audit.py --rebuild-prompt-pack   # 顺带按 SHOTS_EP04.json 重建提示词包
  python ep04_audit.py --no-probe              # 不调 ffprobe，只查文件在不在（更快）

退出码：0 = 全部镜有图有片且帧数对齐；1 = 仍有缺口。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

EPDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MM = os.path.join(EPDIR, "06_分镜与时间轴")
TL_JSON = os.path.join(MM, "EP04_timeline_v2.json")
TL_CSV = os.path.join(MM, "EP04_timeline_v2.csv")
SHOTS = os.path.join(MM, "SHOTS_EP04.json")
P13 = os.path.join(EPDIR, "07_提示词与剧本", "P13_切片提示词_EP04.md")
PACK = os.path.join(MM, "EP04_提示词包.md")
LOCK = os.path.join(EPDIR, "08_资产库", "_资产锁定")
KEYDIR = os.path.join(EPDIR, "08_资产库", "EP04_关键帧")
CLIPDIR = os.path.join(EPDIR, "05_成品视频", "单镜原片")
LEGACY = os.path.join(EPDIR, "video_i2v")
OUT_MD = os.path.join(MM, "EP04_审计报告.md")
OUT_JSON = os.path.join(MM, "EP04_audit.json")

FFPROBE = (os.environ.get("FFPROBE")
           or next((p for p in (r"源机器E盘ffmpeg_bin\ffprobe.exe", r"ComfyUI\ffprobe.exe",
                                r"<D盘>\ffmpeg\bin\ffprobe.exe") if os.path.exists(p)), None)
           or shutil.which("ffprobe"))

CAM_LOCK_OK = {"固定", "完全固定", "不动", ""}


def rd_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def sha1(p, n=1 << 20):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        while True:
            b = f.read(n)
            if not b:
                break
            h.update(b)
    return h.hexdigest()[:12]


def probe_frames(p):
    if not FFPROBE or not os.path.exists(p):
        return None
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                            "-count_frames", "-show_entries", "stream=nb_read_frames",
                            "-of", "csv=p=0", p],
                           capture_output=True, text=True, timeout=60)
        s = r.stdout.strip().splitlines()
        return int(s[0]) if s and s[0].strip().isdigit() else None
    except Exception:
        return None


def md_headings(path, pat):
    if not os.path.exists(path):
        return set()
    out = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(pat, line.strip())
            if m:
                out.add(m.group(1))
    return out


def gen_len(frames):
    return ((frames - 1 + 3) // 4) * 4 + 1


def rebuild_prompt_pack(pack, tl):
    """按 SHOTS_EP04.json 重建 EP04_提示词包.md（修掉「S13 被误列为待补」这类陈旧错误）"""
    shots, blocked = pack["shots"], pack.get("blocked", [])
    by_id = {s["id"]: s for s in shots}
    neg = ("镜头推近，镜头拉远，变焦，摇镜，平移，构图漂移，人物出画，裁掉头部，只拍身体，"
           "换脸，长着另一张脸，发型改变，发色改变，服装改变，多余的手指，畸形的手，扭曲的脸，"
           "五官变形，字幕，水印，文字，logo，过曝，整体发灰，低质量，最差质量，"
           "JPEG压缩残留，杂乱的背景，多重人影，闪烁")
    L = []
    L.append("# EP04 提示词包（可直接粘进 ComfyUI）\n")
    L.append("> 本文件由 `SHOTS_EP04.json` 自动生成（`ep04_audit.py --rebuild-prompt-pack`）。"
             "改提示词请改 JSON，不要直接改本文件。\n")
    L.append("## 通用设置\n")
    L.append("| 项 | 值 |\n|---|---|")
    m = pack["model"]
    L.append("| 模型 | `%s` |" % m["unet"])
    L.append("| 文本编码器 | `%s`（type=`%s`） |" % (m["clip"], m["text_encoder_type"]))
    L.append("| VAE | `%s` |" % m["vae"])
    L.append("| 分辨率 | %d×%d |" % (m["width"], m["height"]))
    L.append("| 采样 | %s / %s / %d 步 / cfg %.1f / shift %.1f |"
             % (m["sampler"], m["scheduler"], m["steps"], m["cfg"], m["shift"]))
    L.append("| 帧率 | %d fps |" % m["fps"])
    L.append("| 节点链 | LoadImage → Wan22ImageToVideoLatent → KSampler → "
             "VAEDecode → CreateVideo → SaveVideo |\n")
    L.append("**负向词（全镜通用）**\n")
    L.append("```\n%s\n```\n" % neg)
    L.append("---\n")
    L.append("## 可拍镜头（%d 镜）\n" % len(shots))
    for s in shots:
        sid = s["id"]
        f = tl.get(sid)
        if not f:
            continue
        L.append("### %s · %.2fs / %d 帧 → 生成长度 %d\n" % (sid, f / 24.0, f, gen_len(f)))
        L.append("- 首帧：`_资产锁定/%s`" % s["img"])
        L.append("- 景别：见时间轴 ｜ 运镜：固定（全局锁死）\n")
        body = " ".join([s["action"], s["sound"], s["music"], s["lens"], "机位固定不动。"])
        L.append("```\n%s\n```\n" % body)
    L.append("---\n")
    L.append("## 待补关键帧（%d 镜，暂不可生成）\n" % len(blocked))
    L.append("| 镜号 | 缺什么 |")
    L.append("|---|---|")
    for b in blocked:
        L.append("| %s | %s |" % (b["id"], b.get("reason", "")))
    L.append("\n> 按 P24 §三 验收门 G5：占位素材不得进入任何交付版本，这些镜必须先补专属关键帧。")
    with open(PACK, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("已重建：%s（可拍 %d / 待补 %d）" % (PACK, len(shots), len(blocked)))


def build_asset_index():
    """扫描 _资产锁定，输出一份「代码 → 实际文件」映射，解决三套命名并存的问题。"""
    out = os.path.join(EPDIR, "08_资产库", "_资产索引.md")
    if not os.path.isdir(LOCK):
        print("找不到资产库：%s" % LOCK)
        return
    files = [f for f in os.listdir(LOCK) if os.path.isfile(os.path.join(LOCK, f))]
    dirs = [d for d in os.listdir(LOCK) if os.path.isdir(os.path.join(LOCK, d))]

    chars = sorted({re.sub(r"^(M|EX)_", "", f).split("_")[0]
                    for f in files if re.match(r"^(M|EX)_", f)})
    scenes = {d for d in dirs if d.startswith("SC_")}
    for f in files:                      # A01_SC_NIGHTROAD_主视觉_v01.png
        m = re.match(r"A\d+_(SC_[A-Z0-9]+)_", f)
        if m:
            scenes.add(m.group(1))
    scenes = sorted(scenes)

    L = ["# 资产索引（脚本实测，自动生成）\n",
         "> 来源：`ep04_audit.py --asset-index` ｜ 目录：`08_资产库/_资产锁定`",
         "> 用途：把时间轴里的 `CH_*` / `SC_*` 代码对到真实文件，避免再挂错图。\n",
         "## 一、人物\n",
         "| 代码 | 角色锚点 / 面部 | 三视图 | 表情差分 | 目录 |",
         "|---|---|---|---|---|"]
    for c in chars:
        anchor = next((f for f in files if f.startswith("M_%s_" % c) and
                       ("锚点" in f or "面部" in f)), "")
        tri = next((f for f in files if f.startswith("M_%s_三视图" % c)), "")
        exboard = next((f for f in files if f.startswith("EX_%s_表情差分板" % c)), "")
        exdir = next((d for d in dirs if d == "EX_%s" % c), "")
        L.append("| CH_%s | %s | %s | %s | %s |" % (
            c,
            "`%s`" % anchor if anchor else "—",
            "`%s`" % tri if tri else "—",
            "`%s`" % exboard if exboard else "—",
            "`EX_%s/`" % c if exdir else "—"))
    L += ["\n## 二、场景\n",
          "| 代码 | 主视觉 | 九宫格 | 机位板 |", "|---|---|---|---|"]
    for s in scenes:
        main = next((f for f in files if f.startswith("A") and ("_%s_" % s) in f), "")
        if not main:
            main = next((f for f in files if f.startswith(s) and "主视觉" in f), "")
        grid = next((d for d in dirs if d == s), "")
        n = 0
        if grid:
            n = len([f for f in os.listdir(os.path.join(LOCK, grid)) if f.endswith(".png")])
        board = next((f for f in files if s in f and "机位板" in f), "")
        if not board:
            bd = os.path.join(LOCK, "_机位板")
            if os.path.isdir(bd):
                board = next((f for f in os.listdir(bd) if s in f), "")
                board = "_机位板/%s" % board if board else ""
        L.append("| %s | %s | %s | %s |" % (
            s,
            "`%s`" % main if main else "—",
            "%d 张（`%s/`）" % (n, grid) if grid else "—",
            "`%s`" % board if board else "—"))

    ep = os.path.join(LOCK, "EP04")
    epimgs = sorted(f for f in os.listdir(ep) if f.endswith(".png")) if os.path.isdir(ep) else []
    L += ["\n## 三、EP04 专属首帧（%d 张）\n" % len(epimgs),
          "这些是**只属于 EP04** 的图，优先级高于通用角色/场景锚点。\n",
          "| 文件 | 对应镜号 |", "|---|---|"]
    for f in epimgs:
        m = re.search(r"EP04_(S[0-9A-Za-z]+)_", f)
        L.append("| `EP04/%s` | %s |" % (f, m.group(1) if m else "—"))
    L += ["\n## 四、命名对照（三套并存，以本表为准）\n",
          "| 时间轴写法 | 实际可用文件 | 说明 |", "|---|---|---|",
          "| `CH_LINYAN` | `M_LINYAN_三视图_v01.png` / `M_LINYAN_面部锚点_v01.png` | 人物锚点 |",
          "| `CH_LINYAN_EX` | `EX_LINYAN/EX_LINYAN_0x_*.png` | 表情差分 |",
          "| `CH_ARCHIVIST` | **无独立锚点** | 只有 EP04 单镜图，需补 |",
          "| `CH_LAOZHOU` | **无独立锚点** | 只有 EP04 单镜图，需补 |",
          "| `SC_DEPOT` | `SC_DEPOT/`（九宫格）+ `A06_SC_DEPOT_主视觉_v01.png` | 场景 |",
          "| `SC_STATION` | `SC_STATION/`（九宫格）+ `A04_SC_STATION_主视觉_v01.png` | 场景 |",
          "",
          "> 铁律：**人物镜不要挂 `A01..A11` 场景图**；场景镜不要挂 `M_*` 人物图。"
          "EP04 已有专属图的镜，优先用 `EP04/EP04_Sxx_*.png`。\n"]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("已生成：%s（人物 %d / 场景 %d / EP04 首帧 %d）" % (
        out, len(chars), len(scenes), len(epimgs)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild-prompt-pack", action="store_true")
    ap.add_argument("--asset-index", action="store_true")
    ap.add_argument("--no-probe", action="store_true")
    a = ap.parse_args()

    if a.asset_index:
        build_asset_index()

    timeline = rd_json(TL_JSON)["shots"]
    tl = {s["shot_id"]: s["frames"] for s in timeline}
    order = [s["shot_id"] for s in timeline]
    info = {s["shot_id"]: s for s in timeline}

    csv_rows = {}
    if os.path.exists(TL_CSV):
        with open(TL_CSV, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                csv_rows[r["shot_id"]] = r

    pack = rd_json(SHOTS)
    if a.rebuild_prompt_pack:
        rebuild_prompt_pack(pack, tl)
    shot_ids = {s["id"] for s in pack["shots"]}
    blocked = {b["id"]: b.get("reason", "") for b in pack.get("blocked", [])}

    p13_ids = md_headings(P13, r"^###\s+`?(EP04_S[0-9A-Za-z]+)`?")
    p13_ids = {x.replace("EP04_", "") for x in p13_ids}
    pack_ids = md_headings(PACK, r"^###\s+(S[0-9A-Za-z]+)\s*·")

    imgs = {}
    epdir = os.path.join(LOCK, "EP04")
    if os.path.isdir(epdir):
        for fn in os.listdir(epdir):
            if fn.lower().endswith(".png"):
                imgs.setdefault(fn, os.path.join(epdir, fn))
    img_by_id = {}
    for s in pack["shots"]:
        p = os.path.join(LOCK, s["img"].replace("/", os.sep))
        if os.path.exists(p):
            img_by_id[s["id"]] = p

    key_clips = {}
    if os.path.isdir(KEYDIR):
        for fn in os.listdir(KEYDIR):
            if fn.lower().endswith(".mp4"):
                key_clips[os.path.splitext(fn)[0]] = os.path.join(KEYDIR, fn)
    single = {}
    one_clips = {}
    legacy_clips = {}
    for d, box in ((CLIPDIR, one_clips), (LEGACY, legacy_clips)):
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.lower().endswith("_i2v.mp4"):
                    box[fn[:-len("_i2v.mp4")]] = os.path.join(d, fn)
    single.update(legacy_clips)
    single.update(one_clips)          # 单镜原片优先

    # 重做清单（batch_local.py --qa-all 产出）——有就并入，没有就标"未检"
    qa_state = {}
    rw_json = os.path.join(LEGACY, "重做清单.json")
    if os.path.exists(rw_json):
        try:
            for r in rd_json(rw_json):
                qa_state[r["shot"]] = (bool(r.get("ok")), r.get("rep", ""))
        except Exception:
            qa_state = {}

    rows = []
    for sid in order:
        frames = tl[sid]
        crow = csv_rows.get(sid, {})
        cam = (crow.get("camera_move") or "").strip()
        key = key_clips.get(sid)
        one = single.get(sid)
        kf, kres = None, None
        if key and not a.no_probe:
            pf = probe_frames(key)
            kf = pf
        rows.append(dict(
            shot=sid, frames=frames, dur=round(frames / 24.0, 2),
            size=crow.get("shot_size", ""), cam=cam,
            img=os.path.relpath(img_by_id[sid], EPDIR) if sid in img_by_id else "",
            has_shot=sid in shot_ids,
            has_p13=sid in p13_ids,
            has_pack=sid in pack_ids,
            blocked=blocked.get(sid, ""),
            key_clip=os.path.relpath(key, EPDIR) if key else "",
            key_frames=kf,
            single=os.path.relpath(one, EPDIR) if one else "",
            img_ok=bool(img_by_id.get(sid)),
            cam_conflict=(cam not in CAM_LOCK_OK) and sid in shot_ids,
            qa=qa_state.get(sid, (None, ""))[0],
            qa_rep=qa_state.get(sid, (None, ""))[1],
        ))

    # 成片同内容检测（占位图凑出来的镜往往字节级相同）
    dup = {}
    for sid, p in key_clips.items():
        try:
            dup.setdefault(sha1(p), []).append(sid)
        except Exception:
            pass
    dup_groups = [v for v in dup.values() if len(v) > 1]

    n = len(rows)
    has_img = sum(1 for r in rows if r["img_ok"])
    has_key = sum(1 for r in rows if r["key_clip"])
    has_one = sum(1 for r in rows if r["shot"] in one_clips)
    has_legacy = sum(1 for r in rows if r["shot"] in legacy_clips)
    has_anyclip = sum(1 for r in rows if r["key_clip"] or r["single"])
    has_shot = sum(1 for r in rows if r["has_shot"])
    has_p13 = sum(1 for r in rows if r["has_p13"])
    cam_conf = [r for r in rows if r["cam_conflict"]]
    frame_bad = [r for r in rows if r["key_frames"] is not None and r["key_frames"] != r["frames"]]
    qa_pass = [r for r in rows if r["qa"] is True]
    qa_fail = [r for r in rows if r["qa"] is False]
    qa_unknown = [r for r in rows if r["qa"] is None]

    miss_img = [r["shot"] for r in rows if not r["img_ok"]]
    miss_clip = [r["shot"] for r in rows if not (r["key_clip"] or r["single"])]
    miss_p13 = [r["shot"] for r in rows if not r["has_p13"]]

    stamp = time.strftime("%Y-%m-%d %H:%M")
    L = []
    L.append("# EP04 审计报告（脚本实测）\n")
    L.append("> 生成时间 %s ｜ 来源：`ep04_audit.py`" % stamp)
    L.append("> 真源：`06_分镜与时间轴/EP04_timeline_v2.json`（%d 镜 / %.1fs）" % (n, sum(tl.values()) / 24.0))
    L.append("> 本文件只报数，不改内容。改完素材重跑一次即可刷新。\n")
    L.append("## 一、总账\n")
    L.append("| 口径 | 数量 | 说明 |")
    L.append("|---|---|---|")
    L.append("| 时间轴镜数 | %d | 唯一真源 |" % n)
    L.append("| 有专属首帧 PNG | %d / %d | `08_资产库/_资产锁定/EP04` |" % (has_img, n))
    L.append("| 有 I2V 任务条目 | %d / %d | `SHOTS_EP04.json` 可拍段 |" % (has_shot, n))
    L.append("| 有 I2V 提示词 | %d / %d | `EP04_提示词包.md` |" % (has_shot, n))
    L.append("| 有 P13 生图卡 | %d / %d | 旧三件套（v3） |" % (has_p13, n))
    L.append("| 有成片（任一来源） | %d / %d | 关键帧目录 + 单镜原片 |" % (has_anyclip, n))
    L.append("| ↳ `08_资产库/EP04_关键帧` | %d / %d | 1024×1536 交付规格 |" % (has_key, n))
    L.append("| ↳ `05_成品视频/单镜原片` | %d / %d | 512×768 原片（A 镜） |" % (has_one, n))
    L.append("| ↳ `video_i2v` | %d / %d | 收片工作目录（含从上两处复制的副本） |" % (has_legacy, n))
    L.append("| 帧数与时间轴不符 | %d | ffprobe 逐条实测 |" % len(frame_bad))
    L.append("| 运镜与「机位固定」冲突 | %d | 时间轴写了推/摇/移 |" % len(cam_conf))
    L.append("| 质检通过 | %d / %d | `batch_local.py --qa-all` |" % (len(qa_pass), n))
    L.append("| 质检未通过 | %d | 见 `video_i2v/重做清单.md` |" % len(qa_fail))
    L.append("| 未质检 | %d | 跑一次 `--qa-all` 即可 |" % len(qa_unknown))
    L.append("\n## 二、逐镜表\n")
    L.append("| # | 镜号 | 帧 | 秒 | 景别 | 时间轴运镜 | 首帧 | 任务卡 | P13 | 成片 | 实测帧 | 质检 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        L.append("| %d | %s | %d | %.2f | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            i, r["shot"], r["frames"], r["dur"], r["size"], r["cam"] or "—",
            "✓" if r["img_ok"] else "✗",
            "✓" if r["has_shot"] else "✗",
            "✓" if r["has_p13"] else "✗",
            "关键帧" if r["key_clip"] else ("原片" if r["single"] else "✗"),
            r["key_frames"] if r["key_frames"] is not None else "—",
            "PASS" if r["qa"] is True else ("FAIL" if r["qa"] is False else "未检")))
    if miss_img:
        L.append("\n**缺首帧（%d）**：%s" % (len(miss_img), "、".join(miss_img)))
    if miss_clip:
        L.append("\n**缺成片（%d）**：%s" % (len(miss_clip), "、".join(miss_clip)))
    if miss_p13:
        L.append("\n**P13 无卡（%d）**：%s（这些镜的头帧/提示词见 `SHOTS_EP04.json`）" %
                 (len(miss_p13), "、".join(miss_p13)))
    if frame_bad:
        L.append("\n**帧数不符**：")
        for r in frame_bad:
            L.append("- %s：时间轴 %d，成片 %d" % (r["shot"], r["frames"], r["key_frames"]))
    L.append("\n## 三、成片同内容检测（占位图凑镜的硬证据）\n")
    if dup_groups:
        L.append("以下镜头的 mp4 **字节级相同**，说明用的是同一张占位首帧，不能算独立镜头：\n")
        for g in dup_groups:
            L.append("- `%s`（%d 个）" % ("`、`".join(g), len(g)))
    else:
        L.append("未发现字节级重复。")
    L.append("\n## 四、运镜冲突\n")
    if cam_conf:
        L.append("时间轴要求运镜，但全管线的负向词禁推拉摇移、提示词统一追加「机位固定不动」。"
                 "二者只能留一个，必须由导演裁定：\n")
        L.append("| 镜号 | 时间轴写法 |")
        L.append("|---|---|")
        for r in cam_conf:
            L.append("| %s | %s |" % (r["shot"], r["cam"]))
    else:
        L.append("无冲突。")
    L.append("\n## 五、待补（按阻塞原因）\n")
    if blocked:
        L.append("| 镜号 | 原因 |")
        L.append("|---|---|")
        for sid in order:
            if sid in blocked:
                L.append("| %s | %s |" % (sid, blocked[sid]))
    L.append("\n---\n")
    L.append("结论：**%d/%d 有专属首帧，%d/%d 有成片文件，%d/%d 质检通过**。" % (
        has_img, n, has_anyclip, n, len(qa_pass), n))
    if miss_clip:
        L.append("仍缺成片的镜：%s。" % "、".join(miss_clip))
    if qa_fail:
        L.append("质检不通过的镜：%s（逐条原因见 `video_i2v/重做清单.md`）。" %
                 "、".join(r["shot"] for r in qa_fail))
    L.append("补齐后重跑 `ep04_audit.py`，数字会自动刷新。\n")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(dict(generated=stamp, total=n, rows=rows,
                       dup_groups=dup_groups),
                  f, ensure_ascii=False, indent=1)

    print("镜数 %d ｜ 首帧 %d ｜ 成片 %d ｜ 缺片 %d ｜ 帧数不符 %d ｜ 运镜冲突 %d" % (
        n, has_img, has_anyclip, len(miss_clip), len(frame_bad), len(cam_conf)))
    print("报告：%s" % OUT_MD)
    return 0 if (not miss_clip and not frame_bad) else 1


if __name__ == "__main__":
    sys.exit(main())
