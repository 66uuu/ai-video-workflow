#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
规则字卡 / 标题卡（PIL 排版 + ffmpeg 叠化，零外部素材）

补的是生产链第 10 环：正片做完了，但片头没有标题、剧中的「夜路规则」没有
字卡、片尾没有收束。以前这些只能手工在剪辑软件里打，现在一条命令烧进片子。

三种版式：
  title  片头标题（大字居中 + 黑条底 + 描边）
  rule   规则卡（红顶线 + 半透明黑卡 + 白字，屏幕中下）
  sub    小字说明（片尾/注释，底部居中）

用法：
  python card_gen.py --video 正片.mp4 --cards cards.json --out 带字卡.mp4
  python card_gen.py --video 正片.mp4 --title "夜路司机 第04集" --auto --out 带字卡.mp4
  python card_gen.py --video 正片.mp4 --cards cards.json --out out.mp4 --no-jitter

cards.json：
{
  "cards": [
    {"text": "夜路司机", "sub": "第一规则", "from": 1.0, "to": 5.0, "style": "title"},
    {"text": "后座有人说话\\n不要回头", "from": 12.0, "to": 17.0, "style": "rule", "tag": "规则 01"},
    {"text": "第 04 集 · 完", "from": 87.0, "to": 91.0, "style": "sub"}
  ]
}
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

FONTS = [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
         "/System/Library/Fonts/PingFang.ttc",
         "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"]


def pick_font(explicit=""):
    for p in ([explicit] if explicit else []) + FONTS:
        if p and os.path.exists(p):
            return p
    raise SystemExit("找不到中文字体，用 --font 指定一个 .ttf/.ttc")


def probe_size(ff, path):
    ext = ".exe" if os.name == "nt" else ""
    probe = os.path.join(os.path.dirname(ff), "ffprobe" + ext)
    if not os.path.exists(probe):
        probe = shutil.which("ffprobe")
    out = subprocess.check_output(
        [probe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
        text=True).strip().splitlines()[0]
    w, h = out.split("x")[:2]
    return int(w), int(h)


def probe_duration(ff, path):
    ext = ".exe" if os.name == "nt" else ""
    probe = os.path.join(os.path.dirname(ff), "ffprobe" + ext)
    if not os.path.exists(probe):
        probe = shutil.which("ffprobe")
    out = subprocess.check_output(
        [probe, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], text=True).strip()
    return float(out)


def render_card(card, W, H, font_path, out_png):
    """把一张卡排成整幅透明 PNG（文字位置跟版式走，叠加时 x/y=0）"""
    from PIL import Image, ImageDraw, ImageFont

    style = card.get("style", "rule")
    text = card.get("text", "")
    sub = card.get("sub", "")
    tag = card.get("tag", "")

    base = {"title": 0.070, "rule": 0.044, "sub": 0.030}.get(style, 0.044)
    size = max(18, int(H * base))
    stroke = max(2, size // 16)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, size)

    def measure(t, f):
        box = d.multiline_textbbox((0, 0), t, font=f, spacing=int(size * 0.35),
                                   align="center", stroke_width=stroke)
        return box[2] - box[0], box[3] - box[1]

    tw, th = measure(text, font)
    cy = {"title": int(H * 0.44), "rule": int(H * 0.63), "sub": int(H * 0.86)}.get(style, int(H * 0.6))

    if style in ("title", "rule"):
        pad_x, pad_y = int(size * 0.9), int(size * 0.55)
        bw, bh = tw + pad_x * 2, th + pad_y * 2
        alpha = 190 if style == "title" else 150
        d.rectangle([(W - bw) // 2, cy - bh // 2, (W + bw) // 2, cy + bh // 2],
                    fill=(0, 0, 0, alpha))
        if style == "rule":
            d.rectangle([(W - bw) // 2, cy - bh // 2, (W + bw) // 2,
                         cy - bh // 2 + max(3, size // 22)], fill=(198, 42, 38, 235))
        if tag:
            tf = ImageFont.truetype(font_path, max(14, int(size * 0.46)))
            if style == "rule":
                d.multiline_text((W // 2, cy - bh // 2 - int(size * 0.55)), tag,
                                 font=tf, fill=(214, 60, 52, 240), anchor="mm",
                                 align="center", stroke_width=2, stroke_fill=(0, 0, 0, 255))
            else:
                pass

    fill = (255, 255, 255, 252) if style != "sub" else (232, 232, 232, 225)
    d.multiline_text((W // 2, cy), text, font=font, fill=fill, anchor="mm",
                     align="center", spacing=int(size * 0.35),
                     stroke_width=stroke, stroke_fill=(0, 0, 0, 255))

    if sub and style == "title":
        sf = ImageFont.truetype(font_path, max(16, int(size * 0.34)))
        d.multiline_text((W // 2, cy + th // 2 + int(size * 1.15)), sub,
                         font=sf, fill=(205, 205, 205, 235), anchor="mm",
                         align="center", stroke_width=2, stroke_fill=(0, 0, 0, 220))

    img.save(out_png)
    return out_png


def auto_cards(title, dur):
    cards = []
    if title:
        cards.append({"text": title, "from": 0.8, "to": min(4.2, dur * 0.2),
                      "style": "title"})
    tail = min(4.0, max(2.0, dur * 0.06))
    cards.append({"text": "本片音画均为本地生成", "from": max(0.0, dur - tail - 0.4),
                  "to": dur, "style": "sub"})
    return cards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cards", default="", help="字卡时间表 json")
    ap.add_argument("--title", default="", help="配合 --auto 的片头标题")
    ap.add_argument("--auto", action="store_true", help="自动排片头标题 + 片尾说明")
    ap.add_argument("--font", default="")
    ap.add_argument("--no-jitter", action="store_true", help="关掉细微抖动")
    ap.add_argument("--fade", type=float, default=0.32, help="淡入淡出秒数")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--ffmpeg", default="")
    a = ap.parse_args()

    ff = a.ffmpeg or shutil.which("ffmpeg")
    if not ff:
        raise SystemExit("找不到 ffmpeg，用 --ffmpeg 指定")
    if not os.path.exists(a.video):
        raise SystemExit("视频不存在：%s" % a.video)

    dur = probe_duration(ff, a.video)
    if a.auto:
        cards = auto_cards(a.title, dur)
    elif a.cards:
        with open(a.cards, encoding="utf-8") as f:
            cards = (json.load(f).get("cards") or [])
    else:
        raise SystemExit("要么给 --cards，要么 --auto")
    if not cards:
        raise SystemExit("字卡为空")

    cards = [c for c in cards if float(c.get("to", 0)) > float(c.get("from", 0))]
    cards.sort(key=lambda c: float(c["from"]))

    W, H = probe_size(ff, a.video)
    font = pick_font(a.font)
    tmp = tempfile.mkdtemp(prefix="nr_card_")

    cmd = [ff, "-y", "-v", "error", "-i", a.video]
    chains, prev = [], "[0:v]"
    for i, c in enumerate(cards):
        png = os.path.join(tmp, "c%d.png" % i)
        render_card(c, W, H, font, png)
        f, t = float(c["from"]), float(c["to"])
        d = max(0.6, t - f)
        cmd += ["-loop", "1", "-framerate", "24", "-t", "%.3f" % d, "-i", png]
        idx = i + 1
        fade = min(a.fade, d / 2.0)
        chains.append(
            "[%d:v]format=rgba,fade=t=in:st=0:d=%.2f:alpha=1,"
            "fade=t=out:st=%.2f:d=%.2f:alpha=1,setpts=PTS+%.3f/TB[c%d]"
            % (idx, fade, d - fade, fade, f, i))
        jx = "" if a.no_jitter else "x='1.6*sin(9*t)':y='1.1*sin(13*t)'"
        pos = jx or "x=0:y=0"
        out = "[v%d]" % i
        chains.append("%s[c%d]overlay=%s:enable='between(t,%.3f,%.3f)':eof_action=pass%s"
                      % (prev, i, pos, f, t, out))
        prev = out

    if len(chains):
        graph = ";".join(chains)
        cmd += ["-filter_complex", graph, "-map", prev,
                "-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf),
                "-pix_fmt", "yuv420p", "-an",
                "-movflags", "+faststart", a.out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr[-1500:])
            raise SystemExit("叠字卡失败")
    else:
        raise SystemExit("没有有效字卡")

    print("字卡：%d 张 / %dx%d / 抖动 %s" % (len(cards), W, H,
                                           "关" if a.no_jitter else "开"))
    for c in cards:
        print("  %6.2f–%6.2f  [%-5s]  %s" % (float(c["from"]), float(c["to"]),
                                             c.get("style", "rule"),
                                             c["text"].replace("\n", " / ")))
    print("完成：%s  %.1fMB" % (a.out, os.path.getsize(a.out) / 1024 / 1024))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
