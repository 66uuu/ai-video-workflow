#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本地配音轨生成（Windows SAPI / 系统内置语音，零联网、零模型下载）

为什么用它：管线原来只有配音单和 TTS 提示词，没有音轨，成片是静音轨占位。
本脚本先把"能听的草稿音轨"做出来（用于对时、审节奏），音色质量由后续
IndexTTS2 / CosyVoice 替换，不影响时间轴与封装流程。

用法：
  python tts_local.py --sheet "配音单.tsv" --out "..\\_产出\\配音_SC17"
  python tts_local.py --sheet EP04_voice_records.tsv --timeline EP04_timeline_v2.json ^
                      --out "..\\_产出\\配音_EP04" --voice "Microsoft Huihui Desktop"

产物：
  lines/01.wav …        逐句干声
  voice_manifest.csv    行,镜,角色,台词,文件,起始秒,时长秒
  voice_track.wav       按时间轴对齐的整轨（16bit 单声道 24kHz）
  voice_track.srt       可直接软挂/烧录的字幕

配音单格式（TSV，UTF-8，列名固定）：
  行  镜  角色  台词  字数  预估秒  语速  情绪指令  气口  音频处理
时间轴格式（可选）：{"shots":[{"shot_id":"S02","start":12.5,"duration":3.0}]}
  start 缺失时按顺序累加，句间留 --gap 秒。
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import wave

SR = 24000  # 统一采样率，SAPI 默认 22.05k，重采样到此值


def find_powershell():
    for exe in ("powershell.exe", "pwsh.exe"):
        p = subprocess.run(["where", exe], capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip().splitlines()[0]
    raise SystemExit("找不到 PowerShell，无法调用系统语音")


def shift_pitch(wav, semitones):
    """
    变调不变速。本机只装了 Huihui（女声），档案员/车队这类男角色靠降调近似，
    够用来对时；真音色仍要等 IndexTTS2 / CosyVoice。
    """
    import shutil
    ff = shutil.which("ffmpeg")
    if not ff:
        raise SystemExit("用了 --pitch-map 但 PATH 里没有 ffmpeg")
    sr = wav_info(wav)[0]
    factor = 2.0 ** (semitones / 12.0)
    tmp = wav + ".pitch.wav"
    cmd = [ff, "-y", "-v", "error", "-i", wav, "-filter:a",
           "asetrate=%d,aresample=%d,atempo=%.6f" % (int(sr * factor), sr, 1.0 / factor),
           "-c:a", "pcm_s16le", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        raise SystemExit("ffmpeg 变调失败：%s" % r.stderr[:300])
    os.replace(tmp, wav)


def parse_map(s):
    """'档案员=-4,车队=-5' → {'档案员': '-4', '车队': '-5'}"""
    out = {}
    for part in (s or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip():
                out[k.strip()] = v.strip()
    return out


def synth(text, out_wav, voice, rate, ps):
    """调 SAPI 合成一句，落 WAV。文本走 .ps1 文件，避免命令行转义问题。"""
    os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
    script = (
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$s.SelectVoice('%s')\n"
        "$s.Rate = %d\n"
        "$s.SetOutputToWaveFile('%s')\n"
        "$s.Speak(@'\n%s\n'@)\n"
        "$s.Dispose()\n"
    ) % (voice, rate, out_wav.replace("'", "''"), text)
    fd, tmp = tempfile.mkstemp(suffix=".ps1")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8-sig") as f:
            f.write(script)
        r = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out_wav):
            raise SystemExit("SAPI 合成失败：%s\n%s" % (text[:20], r.stderr))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def wav_info(path):
    with wave.open(path, "rb") as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()


def read_wav_mono(path):
    import numpy as np
    with wave.open(path, "rb") as w:
        sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise SystemExit("只支持 16bit WAV：%s" % path)
    a = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def resample(a, sr_in, sr_out=SR):
    import numpy as np
    if sr_in == sr_out:
        return a
    n_out = int(round(len(a) * sr_out / sr_in))
    x_old = np.linspace(0, 1, len(a), endpoint=False)
    x_new = np.linspace(0, 1, n_out, endpoint=False)
    return np.interp(x_new, x_old, a).astype("float32")


def load_sheet(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    if not rows:
        raise SystemExit("配音单为空：%s" % path)
    need = {"镜", "台词"}
    if not need.issubset(rows[0].keys()):
        raise SystemExit("配音单缺少列：%s（现有：%s）" % (need, list(rows[0].keys())))
    return rows


def load_shots(path):
    """时间轴 → {shot_id: (start_sec, duration_sec)}"""
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for s in data.get("shots", []):
        sid = s.get("shot_id") or s.get("id")
        st = s.get("start", s.get("start_time", s.get("start_sec")))
        if sid and st is not None:
            out[str(sid)] = (float(st), float(s.get("duration") or 0))
    return out


def fmt_ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True, help="配音单 TSV")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--timeline", default="", help="时间轴 JSON（可选，按镜号对齐）")
    ap.add_argument("--voice", default="Microsoft Huihui Desktop", help="系统语音名")
    ap.add_argument("--gap", type=float, default=0.3, help="无时间轴时句间间隔秒")
    ap.add_argument("--rate-max", type=int, default=5, help="语速上限（SAPI -10~10）")
    ap.add_argument("--no-fit", action="store_true", help="关闭按『预估秒』自动校准语速")
    ap.add_argument("--voice-map", default="", help='按角色换语音："林砚=xxx,档案员=yyy"')
    ap.add_argument("--pitch-map", default="", help='按角色变调（半音，负数降调）："档案员=-4,车队=-5"')
    a = ap.parse_args()

    vmap = parse_map(a.voice_map)
    pmap = {k: float(v) for k, v in parse_map(a.pitch_map).items()}
    ps = find_powershell()
    rows = load_sheet(a.sheet)
    shots = load_shots(a.timeline)
    starts = {k: v[0] for k, v in shots.items()}
    lines_dir = os.path.join(a.out, "lines")
    os.makedirs(lines_dir, exist_ok=True)

    manifest, cursor = [], 0.0
    for i, r in enumerate(rows, 1):
        text = (r.get("台词") or "").strip()
        if not text:
            continue
        shot = (r.get("镜") or "").strip()
        role = (r.get("角色") or "").strip()
        voice = vmap.get(role, a.voice)
        try:
            speed = float((r.get("语速") or "1.0").strip() or 1.0)
        except ValueError:
            speed = 1.0
        rate = max(-10, min(a.rate_max, int(round((speed - 1.0) * 10))))
        # 同一镜里有两句时，第二句必须接在第一句后面，不能被镜号起点拽回去
        start = max(starts.get(shot, cursor), cursor)
        budget = None
        if shot in shots:
            budget = shots[shot][0] + shots[shot][1] - start
        wav = os.path.join(lines_dir, "%02d_%s.wav" % (i, re.sub(r"[^\w.-]", "_", shot or str(i))))
        synth(text, wav, voice, rate, ps)
        sr, _, _, n = wav_info(wav)
        dur = n / float(sr)

        # 按『预估秒』校准：SAPI 的 Rate 每级约 ±10%，最多回炉 2 次
        # 预估秒比镜头还长时（S14 写了 4.2s，镜头只有 3.0s）以镜头预算为准
        try:
            target = float((r.get("预估秒") or "0").strip() or 0)
        except ValueError:
            target = 0.0
        if budget and budget > 0.5:
            target = min(target, budget) if target > 0 else budget
        if not a.no_fit and target > 0:
            for _ in range(2):
                if 0.9 * target <= dur <= 1.1 * target:
                    break
                delta = int(round((dur / target - 1.0) * 10))
                if delta == 0:
                    break
                rate = max(-10, min(a.rate_max, rate + delta))
                synth(text, wav, voice, rate, ps)
                sr, _, _, n = wav_info(wav)
                dur = n / float(sr)

        # 变调必须在语速校准之后：校准只动 Rate，变调不动时长
        if role in pmap:
            shift_pitch(wav, pmap[role])
            sr, _, _, n = wav_info(wav)
            dur = n / float(sr)
        # 语速已顶到上限还是塞不进镜头时，宁可让这句溢出，也不要再压
        if budget and dur > budget + 0.05:
            print("    ! 超出本镜 %.2fs（预算 %.2fs，语速已到 %d）" % (dur - budget, budget, rate))
        manifest.append({"row": "%02d" % i, "shot": shot,
                         "role": role, "text": text, "voice": voice,
                         "file": os.path.relpath(wav, a.out).replace("\\", "/"),
                         "start": round(start, 3), "dur": round(dur, 3)})
        cursor = start + dur + a.gap
        print("[%02d] %-6s %5.2fs  %s" % (i, shot, dur, text[:24]))

    import numpy as np
    total = max(m["start"] + m["dur"] for m in manifest) + 1.0
    track = np.zeros(int(total * SR), dtype="float32")
    for m in manifest:
        seg, sr = read_wav_mono(os.path.join(a.out, m["file"]))
        seg = resample(seg, sr)
        i0 = int(m["start"] * SR)
        track[i0:i0 + len(seg)] += seg

    peak = float(np.max(np.abs(track))) or 1.0
    track = track / peak * 0.89
    wav_out = os.path.join(a.out, "voice_track.wav")
    with wave.open(wav_out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((track * 32767).astype("<i2").tobytes())

    with open(os.path.join(a.out, "voice_manifest.csv"), "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["row", "shot", "role", "text", "voice", "file", "start", "dur"])
        wr.writeheader()
        wr.writerows(manifest)

    with open(os.path.join(a.out, "voice_track.srt"), "w", encoding="utf-8") as f:
        for i, m in enumerate(manifest, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (
                i, fmt_ts(m["start"]), fmt_ts(m["start"] + m["dur"]), m["text"]))

    print("\n整轨：%s  %.1fs" % (wav_out, total))
    print("清单：%s" % os.path.join(a.out, "voice_manifest.csv"))
    print("字幕：%s" % os.path.join(a.out, "voice_track.srt"))


if __name__ == "__main__":
    main()
