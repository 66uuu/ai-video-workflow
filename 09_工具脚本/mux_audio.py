#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
音轨 / BGM / 字幕封装（ffmpeg）

解决：成片一直是静音轨占位（assemble_ep04.py 第174行）。本脚本不重编码视频，
只把配音轨、可选 BGM、可选字幕挂进已有 mp4，几秒完成。

用法：
  python mux_audio.py --video "成片.mp4" --audio "配音\\voice_track.wav" --out "成片_有声.mp4"
  python mux_audio.py --video "成片.mp4" --audio voice.wav --bgm bgm.mp3 --bgm-volume 0.15 --out out.mp4
  python mux_audio.py --video "成片.mp4" --audio voice.wav --srt voice.srt --out out.mp4

规则：
  - 视频流 -c:v copy，不二次压缩、不掉画质；
  - 有 BGM 时做 amix（人声 1.0 / BGM 由 --bgm-volume 控制，默认 0.15），BGM 循环到片长；
  - 字幕默认软挂（mov_text），加 --burn 才烧录进画面（需要 libass，ffmpeg full build 自带）。
"""
import argparse
import os
import shutil
import subprocess
import sys


def video_duration(ff, path):
    """取视频流时长；取不到返回 None（此时退回 -shortest）"""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--audio", required=True, help="配音轨 wav/mp3")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bgm", default="", help="背景音乐（可选）")
    ap.add_argument("--bgm-volume", type=float, default=0.15)
    ap.add_argument("--srt", default="", help="字幕文件（可选）")
    ap.add_argument("--burn", action="store_true", help="烧录字幕（默认软挂）")
    ap.add_argument("--ffmpeg", default="")
    a = ap.parse_args()

    ff = a.ffmpeg or shutil.which("ffmpeg")
    if not ff:
        raise SystemExit("找不到 ffmpeg，请用 --ffmpeg 指定")
    for p in (a.video, a.audio):
        if not os.path.exists(p):
            raise SystemExit("文件不存在：%s" % p)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)

    # 所有输入必须先声明，再写 -map：ffmpeg 在 -map 之后再出现 -i 会报
    # 「Error parsing options for input file」
    if a.srt and not os.path.exists(a.srt):
        raise SystemExit("字幕不存在：%s" % a.srt)

    cmd = [ff, "-y", "-i", a.video, "-i", a.audio]
    srt_index = None
    if a.bgm:
        cmd += ["-stream_loop", "-1", "-i", a.bgm]
    if a.srt:
        cmd += ["-i", a.srt]
        srt_index = 3 if a.bgm else 2

    # apad + -shortest 的组合含义：配音短于画面时补静音，画面一帧不切；
    # 配音长于画面时以画面为准收尾。不加 apad 会被 -shortest 直接截掉片尾。
    if a.bgm:
        cmd += ["-filter_complex",
                "[1:a]volume=1.0[v];[2:a]volume=%.2f[m];[v][m]amix=inputs=2:duration=first:dropout_transition=0,apad[aout]" % a.bgm_volume,
                "-map", "0:v:0", "-map", "[aout]"]
    else:
        cmd += ["-map", "0:v:0", "-map", "1:a:0", "-af", "apad"]

    if a.srt:
        if a.burn:
            # 相对路径 + 正斜杠，规避 Windows 盘符冒号在 filter 里的转义问题
            rel = os.path.relpath(a.srt).replace("\\", "/")
            cmd += ["-vf", "subtitles='%s'" % rel]
        else:
            cmd += ["-map", "%d:s:0" % srt_index, "-c:s", "mov_text"]

    # 烧录字幕必须重编码；软挂才可以 -c:v copy（-vf 与 copy 同时出现 ffmpeg 会直接报错）
    if a.srt and a.burn:
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
    else:
        cmd += ["-c:v", "copy"]
    cmd += ["-c:a", "aac", "-b:a", "192k"]
    # 用视频时长 -t 收尾：-shortest 会把较短的音频/字幕当成最短流，连画面一起截断
    dur = video_duration(ff, a.video)
    cmd += ["-t", "%.3f" % dur] if dur else ["-shortest"]
    cmd += ["-movflags", "+faststart", a.out]

    print("执行：" + " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("封装失败，退出码 %d" % r.returncode)
    print("完成：%s  %.1fMB" % (a.out, os.path.getsize(a.out) / 1024 / 1024))


if __name__ == "__main__":
    main()
