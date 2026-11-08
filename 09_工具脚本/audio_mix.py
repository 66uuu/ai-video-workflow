#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
音效与混音（ffmpeg 合成，不依赖任何外部音效素材）

补的是生产链里唯一断掉的一环：配音轨挂上去之后，片子里没有环境底噪、没有
设计音效、没有抽空、响度也没标准化。本脚本一次做完四件事：

  1. 环境底（beds）：雨/灯管/引擎低频，按时间段铺在整个片上
  2. 设计音效（hits）：闷响、计价器咔哒、耳鸣、心跳、弦乐尖音，按时间点插入
  3. 抽空（voids）：指定区间把整条混音压到 0（本剧最强手法，比加声音更有效）
  4. 响度：整条混音 loudnorm 到 -16 LUFS / TP -1.5

用法：
  python audio_mix.py --video 正片.mp4 --voice voice_track.wav --out 混音.mp4
  python audio_mix.py --video 正片.mp4 --voice voice_track.wav --cues cues.json --out mix.mp4
  python audio_mix.py --video 正片.mp4 --voice voice_track.wav --auto --timeline timeline.json --out mix.mp4
  python audio_mix.py --list          # 看可用的合成音效名

cues.json 结构（三段都可省）：
{
  "beds":  [{"sfx": "rain_in", "from": 0, "to": 91, "gain": 0.18}],
  "hits":  [{"sfx": "thud", "at": 88.5, "gain": 0.55}],
  "voids": [{"from": 30.0, "to": 31.0}]
}

--auto 模式按时间轴自动排：
  · 全场铺 rain_in（室内镜换 room）
  · S19 / S22 开抽空（各 0.9s，从镜头起点开始）
  · 最后一镜收尾挂 thud
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile


# 音效合成表：name -> (lavfi 输入, 时长秒, 说明)
# 全部用 ffmpeg 内置信号源，本机零素材也能出片
SYNTH = {
    "rain_in":   ("anoisesrc=color=pink:amplitude=0.55,highpass=f=300,lowpass=f=7000", 0, "雨打车顶/玻璃（近场）"),
    "rain_out":  ("anoisesrc=color=pink:amplitude=0.70,highpass=f=150", 0, "雨幕（车外/空旷）"),
    "room":      ("anoisesrc=color=pink:amplitude=0.18,highpass=f=800,lowpass=f=4000", 0, "室内底噪"),
    "hum":       ("sine=frequency=100:duration=3600,volume=0.16", 0, "灯管电流嗡鸣"),
    "engine":    ("anoisesrc=color=brown:amplitude=0.5,lowpass=f=90,volume=0.9", 0, "引擎/电机低频 60-90Hz"),
    "rumble":    ("anoisesrc=color=brown:amplitude=0.9,lowpass=f=55", 0, "30-50Hz 低频轰鸣"),
    "thud":      ("sine=frequency=72:duration=0.30,afade=t=out:st=0.04:d=0.26", 0.30, "闷响（每集结尾固定）"),
    "tick":      ("sine=frequency=1400:duration=0.035,afade=t=out:st=0.004:d=0.03", 0.05, "计价器跳字"),
    "sting":     ("sine=frequency=2100:duration=1.6,afade=t=out:st=0.9:d=0.7,volume=0.6", 1.6, "弦乐尖音"),
    "ting":      ("sine=frequency=8500:duration=2.5,volume=0.05", 2.5, "耳鸣高频"),
    "heart":     ("sine=frequency=58:duration=0.14,afade=t=out:st=0.05:d=0.09", 0.14, "心跳（单次，可用 bpm 复制）"),
    "breath":    ("anoisesrc=color=pink:amplitude=0.5,highpass=f=500,lowpass=f=2500,"
                  "tremolo=f=0.55:d=0.75", 0, "第二道呼吸（近场，慢于本人）"),
}


def which_ffmpeg(explicit=""):
    ff = explicit or shutil.which("ffmpeg")
    if not ff:
        raise SystemExit("找不到 ffmpeg，请用 --ffmpeg 指定")
    return ff


def synth(ff, name, dur, out_wav):
    """把合成音效渲染成 wav；dur<=0 表示按需长度（这里统一用给定时长）"""
    if name not in SYNTH:
        raise SystemExit("未知音效 %s，可用：%s" % (name, ", ".join(sorted(SYNTH))))
    src, fixed, _desc = SYNTH[name]
    d = fixed or dur
    cmd = [ff, "-y", "-v", "error", "-f", "lavfi", "-i", src,
           "-t", "%.3f" % d, "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", out_wav]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("合成 %s 失败：%s" % (name, r.stderr[-400:]))
    return d


def load_cues(path):
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    return (c.get("beds") or [], c.get("hits") or [], c.get("voids") or [])


def auto_cues(timeline_path, total):
    """按时间轴自动排一版：全程雨底 + 指定镜抽空 + 片尾闷响"""
    with open(timeline_path, encoding="utf-8") as f:
        tl = json.load(f)
    shots = tl.get("shots") or tl
    beds = [{"sfx": "rain_in", "from": 0, "to": total, "gain": 0.16},
            {"sfx": "engine", "from": 0, "to": total, "gain": 0.05}]
    hits, voids = [], []
    for s in shots:
        sid = str(s.get("shot_id") or s.get("id") or s.get("shot") or "")
        start = float(s.get("start") or 0)
        dur = float(s.get("duration") or 0)
        if not dur and s.get("end"):
            dur = float(s["end"]) - start
        if sid.startswith(("S19", "S22")):
            voids.append({"from": round(start + 0.4, 2), "to": round(start + 1.3, 2)})
        if sid.startswith("S17"):
            hits.append({"sfx": "ting", "at": round(start + 0.2, 2), "gain": 0.5})
    if shots:
        last = shots[-1]
        end = float(last.get("end") or (float(last.get("start", 0)) + float(last.get("duration", 0))))
        hits.append({"sfx": "thud", "at": max(0.0, end - 1.2), "gain": 0.7})
    return beds, hits, voids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", help="成片 mp4（只取画面，视频流不重编码）")
    ap.add_argument("--voice", help="配音轨 wav")
    ap.add_argument("--out", help="输出 mp4")
    ap.add_argument("--cues", default="", help="音效时间表 json")
    ap.add_argument("--auto", action="store_true", help="按时间轴自动排音效")
    ap.add_argument("--timeline", default="", help="配合 --auto 用的时间轴 json")
    ap.add_argument("--lufs", type=float, default=-16.0, help="目标响度，默认 -16")
    ap.add_argument("--tp", type=float, default=-1.5, help="真峰值上限 dBTP")
    ap.add_argument("--list", action="store_true", help="列出可用音效")
    ap.add_argument("--ffmpeg", default="")
    a = ap.parse_args()

    if a.list:
        for k in sorted(SYNTH):
            print("%-8s %s" % (k, SYNTH[k][2]))
        return

    for need, val in (("--video", a.video), ("--voice", a.voice), ("--out", a.out)):
        if not val:
            raise SystemExit("缺参数 %s（想看用法加 -h）" % need)
    for p in (a.video, a.voice):
        if not os.path.exists(p):
            raise SystemExit("文件不存在：%s" % p)

    ff = which_ffmpeg(a.ffmpeg)
    dur = video_duration(ff, a.video)
    if not dur:
        raise SystemExit("取不到视频时长：%s" % a.video)

    if a.auto:
        if not a.timeline or not os.path.exists(a.timeline):
            raise SystemExit("--auto 需要 --timeline")
        beds, hits, voids = auto_cues(a.timeline, dur)
    elif a.cues:
        beds, hits, voids = load_cues(a.cues)
    else:
        beds, hits, voids = [], [], []

    tmp = tempfile.mkdtemp(prefix="nr_mix_")
    inputs = [a.voice]                      # 0 = 人声
    chains = []                             # (label, filter)
    for i, b in enumerate(beds):
        w = os.path.join(tmp, "bed%d.wav" % i)
        synth(ff, b["sfx"], max(0.5, float(b["to"]) - float(b["from"])), w)
        inputs.append(w)
        idx = len(inputs) - 1
        delay = int(float(b.get("from", 0)) * 1000)
        chains.append("[%d:a]volume=%.3f,adelay=%d|%d[b%d]" %
                      (idx, float(b.get("gain", 0.15)), delay, delay, i))
    for i, h in enumerate(hits):
        # heartbeat 用 bpm 展开成重复点
        n = 1
        if h.get("bpm"):
            n = max(1, int(dur * float(h["bpm"]) / 60.0))
            step = 60.0 / float(h["bpm"])
        for k in range(n):
            w = os.path.join(tmp, "hit%d_%d.wav" % (i, k))
            synth(ff, h["sfx"], 1.0, w)
            inputs.append(w)
            idx = len(inputs) - 1
            at = float(h["at"]) + (step * k if h.get("bpm") else 0)
            delay = int(at * 1000)
            chains.append("[%d:a]volume=%.3f,adelay=%d|%d[h%d_%d]" %
                          (idx, float(h.get("gain", 0.5)), delay, delay, i, k))

    n_in = len(inputs)
    # hits 的标签必须与实际生成的数量一致（bpm 会展开成多个点），统一在这里算
    hit_tags = []
    for i, h in enumerate(hits):
        n = max(1, int(dur * float(h["bpm"]) / 60.0)) if h.get("bpm") else 1
        hit_tags += ["[h%d_%d]" % (i, k) for k in range(n)]
    mix_inputs = "[0:a]" + "".join("[b%d]" % i for i in range(len(beds))) + "".join(hit_tags)

    post = ("amix=inputs=%d:duration=first:dropout_transition=0:normalize=0,apad" % n_in)
    for v in voids:
        post += ",volume=volume=0:enable='between(t,%.3f,%.3f)'" % (float(v["from"]), float(v["to"]))

    graph = ";".join(chains + ["%s%s[aout]" % (mix_inputs, post)])

    # 第一步：先只渲染混音本身（不封装），这样响度可以量准
    mix_wav = os.path.join(tmp, "mix.wav")
    cmd = [ff, "-y", "-v", "error"]
    for p in inputs:
        cmd += ["-i", p]
    cmd += ["-filter_complex", graph, "-map", "[aout]", "-t", "%.3f" % dur,
            "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", mix_wav]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1200:])
        raise SystemExit("混音渲染失败")

    # 单遍 loudnorm 在长静音段会明显欠冲（实测 -21.15 LUFS 而不是 -16）；
    # 而「静态增益 + 限幅」在峰值高的混音上会被限幅器压回去（-28 → +12dB 后只有 -19.2）。
    # 正确做法是 loudnorm 两遍：第一遍量四元组，第二遍把测出来的值喂回去做线性归一。
    m = measure_lufs(ff, mix_wav)
    if m:
        # 需要抬多少 dB；如果抬上去会把峰值顶破 TP 上限，就只能用动态模式
        # （linear=true 是静态增益，会被 TP 卡住而达不到目标响度）
        need = a.lufs - m["i"]
        head = a.tp - m["tp"]
        linear = need <= head + 0.05
        af = ("loudnorm=I=%.1f:TP=%.1f:LRA=11:linear=%s:"
              "measured_I=%.2f:measured_TP=%.2f:measured_LRA=%.2f:measured_thresh=%.2f:offset=%.2f"
              % (a.lufs, a.tp, "true" if linear else "false",
                 m["i"], m["tp"], m["lra"], m["thresh"], m["offset"]))
        note = ("源 %.2f LUFS / TP %.2f，需 %+.2f dB（余量 %.2f）→ %s loudnorm → 目标 %.1f"
                % (m["i"], m["tp"], need, head, "线性" if linear else "动态", a.lufs))
        # 第三遍：loudnorm 动态模式通常还欠冲 2-3 dB，用一遍预演把残差量出来，
        # 用静态增益补足、再用 alimiter 钉住 TP（只削瞬间峰值，不动平均响度）
        prev = preview_loudnorm(ff, mix_wav, af)
        if prev:
            res = min(a.lufs - prev["i"], 4.0)
            if res > 0.3:
                af += ",volume=%.2fdB,alimiter=limit=%.4f:level=false" % (
                    res, 10 ** ((a.tp - 0.2) / 20.0))
                note += " | 残差补 %+.2f dB" % res
    else:
        af = "volume=0dB"
        note = "量不到响度，按原样封装"

    cmd = [ff, "-y", "-v", "error", "-i", a.video, "-i", mix_wav,
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
           "-af", af, "-c:a", "aac", "-b:a", "192k",
           "-t", "%.3f" % dur, "-movflags", "+faststart", a.out]
    print("音效：底 %d / 点 %d / 抽空 %d | %s" % (len(beds), len(hits), len(voids), note))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1200:])
        raise SystemExit("封装失败")
    print("完成：%s  %.1fMB" % (a.out, os.path.getsize(a.out) / 1024 / 1024))
    chk = measure_lufs(ff, a.out)
    if chk:
        ok = abs(chk["i"] - a.lufs) <= 1.0 and chk["tp"] <= a.tp + 0.5
        print("响度自检：%.2f LUFS / TP %.2f → %s（目标 %.1f / %.1f）"
              % (chk["i"], chk["tp"], "PASS" if ok else "MISS", a.lufs, a.tp))
    shutil.rmtree(tmp, ignore_errors=True)


def measure_lufs(ff, path):
    """量整条音频的响度四元组（第一遍 loudnorm）；量不到返回 None

    返回 {"i","tp","lra","thresh","offset"}，第二遍把这些值喂回去，
    才不会因为长静音段欠冲（单遍 loudnorm 实测 -21.15 而非 -16）。
    """
    cmd = [ff, "-hide_banner", "-nostats", "-i", path,
           "-af", "loudnorm=print_format=json", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    txt = r.stderr
    try:
        j = json.loads(txt[txt.rindex("{"):txt.rindex("}") + 1])
        return {"i": float(j["input_i"]), "tp": float(j["input_tp"]),
                "lra": float(j["input_lra"]), "thresh": float(j["input_thresh"]),
                "offset": float(j["target_offset"])}
    except Exception:
        return None


def preview_loudnorm(ff, path, af):
    """不落盘地跑一遍滤波器，读 loudnorm 自报的 output_i / output_tp"""
    cmd = [ff, "-hide_banner", "-nostats", "-i", path,
           "-af", af + ":print_format=json", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    txt = r.stderr
    try:
        j = json.loads(txt[txt.rindex("{"):txt.rindex("}") + 1])
        return {"i": float(j["output_i"]), "tp": float(j["output_tp"])}
    except Exception:
        return None


def video_duration(ff, path):
    ext = ".exe" if os.name == "nt" else ""
    probe = os.path.join(os.path.dirname(ff), "ffprobe" + ext)
    if not os.path.exists(probe):
        probe = shutil.which("ffprobe")
    if not probe:
        return None
    try:
        out = subprocess.check_output(
            [probe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=duration", "-of", "csv=p=0", path],
            text=True).strip()
        return float(out)
    except Exception:
        return None


if __name__ == "__main__":
    main()
