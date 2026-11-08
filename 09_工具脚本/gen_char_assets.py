# -*- coding: utf-8 -*-
"""
人物资产包生成器（通用层，不限于某个题材）

输入：一张面部参考图（+ 可选半身/全身参考图）
输出：一套可直接用于后续图生视频的角色资产
  01_正脸_中性.png        02_正脸_冷笑.png
  03_半身_正面.png        04_全身_正面.png
  05_全身_侧身.png        06_全身_背面.png
  07~12_表情_*.png        表情六宫格.png
  三视图.png              总览_联系表.png
  00_人物设定.md           （身份提示词块，后续所有镜头直接复制）

用法：
  <D盘>\\ComfyUI\\venv\\Scripts\\python.exe gen_char_assets.py ^
      --face ref_face.png --body ref_body.png --out "..\\_产出\\人物资产_XXX" ^
      --hair "ash brown layered hair, long bangs" ^
      --outfit "black three piece suit, white shirt, black tie" ^
      --style "3d render, cg, semi realistic"

只重做某几项：--only faces / body / expr
"""
import argparse
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.abspath(os.path.join(HERE, "..", "11_本地工具接入指南", "bridge"))
if BRIDGE not in sys.path:
    sys.path.insert(0, BRIDGE)

import nr_bridge as nb  # noqa: E402

# 统一反向词：把「变女性 / 变扁平卡通 / 糊脸 / 双联画 / 半身裁切 / 道具」压掉
NEG = ("1girl, female, woman, feminine, cartoon, anime, flat shading, lowres, blurry, "
       "bad anatomy, extra limbs, extra fingers, deformed eyes, asymmetric eyes, "
       "watermark, text, signature, logo, "
       "split screen, multiple views, two people, collage, panels, border, "
       "cropped legs, cropped feet, furniture, cabinet, table, chair, "
       "grey suit, light grey suit, white suit")

EXPRESSIONS = [
    ("平静", "neutral expression, calm, mouth closed"),
    ("冷笑", "cold smirk, one corner of mouth raised, mocking"),
    ("愤怒", "angry, furrowed brows, glaring, tense jaw"),
    ("惊讶", "slightly surprised, eyes widened, lips parted"),
    ("悲伤", "sad, melancholy, downcast eyes"),
    ("沉思", "eyes closed, thinking, hand near temple"),
]


def build_plan(a, identity, style):
    """返回 [(key, 文件名, prompt, ref_path, weight, w, h, seed)]"""
    P = []

    def add(key, fn, extra, ref, w, h, seed, ratio=None):
        prompt = ", ".join(x for x in (identity, extra, style) if x)
        P.append(dict(key=key, file=fn, prompt=prompt, ref=ref,
                      weight=ratio or 0.65, w=w, h=h, seed=seed))

    face, body = a.face, a.body or a.face

    # ── 正脸特写 ──
    add("face_neutral", "01_正脸_中性.png",
        "solo, front view, looking at viewer, head and shoulders, plain light grey studio background, "
        "soft even lighting, highly detailed face", face, 512, 768, a.seed, 0.65)
    add("face_smirk", "02_正脸_冷笑.png",
        "solo, front view, looking at viewer, confident smug smile, slight smirk, sharp eyes, "
        "head and shoulders, plain light grey studio background, soft even lighting, highly detailed face",
        face, 512, 768, a.seed + 1, 0.60)

    # ── 半身 / 全身 ──
    # ★ 全身必须写 "head to toe, feet visible, wide shot"，否则 512×768 会裁到膝盖
    # ★ 尺寸用 512×768，不要用 512×896：太瘦长会触发「双联画」把一个人画成两张
    FULL = ("solo, full body, head to toe, feet visible, standing straight, wide shot, "
            "plain light grey studio background")
    add("half", "03_半身_正面.png",
        "solo, front view, looking at viewer, neutral expression, waist up, hands relaxed at sides, "
        "plain light grey studio background, soft even lighting", body, 512, 768, a.seed + 2, 0.55)
    add("full_front", "04_全身_正面.png",
        FULL + ", front view, looking at viewer, arms at sides, black leather shoes",
        body, 512, 768, a.seed + 3, 0.45)
    # ★ 侧身权重必须压到 0.15 以下，否则 IPAdapter 会把画面拉回正面
    add("full_side", "05_全身_侧身.png",
        FULL + ", side view, profile, ear visible, nose silhouette, facing left",
        body, 512, 768, a.seed + 4, 0.14)
    # ★ 背面用面部参考图 + 低权重，人脸不出镜，靠文字描述发型服装即可
    add("full_back", "06_全身_背面.png",
        FULL + ", from behind, back view, back of head",
        face, 512, 768, a.seed + 5, 0.20)

    # ── 表情差分 ──
    for i, (cn, en) in enumerate(EXPRESSIONS):
        add("expr%d" % i, "07~12_表情_%d_%s.png" % (i + 1, cn),
            "solo, front view, head and shoulders, %s, plain light grey studio background, "
            "soft even lighting, highly detailed face" % en,
            face, 512, 512, a.seed + 10 + i, 0.80)

    return P


def run_batch(plan, outdir, a):
    c = nb.Comfy()
    if not c.health().get("alive"):
        raise SystemExit("ComfyUI 不在线，先启动 <D盘>\\ComfyUI 的启动.bat")

    os.makedirs(outdir, exist_ok=True)
    raw = os.path.join(outdir, "_raw")
    os.makedirs(raw, exist_ok=True)

    up = {}
    for p in plan:
        if p["ref"] not in up:
            up[p["ref"]] = c.upload_image(p["ref"])
    print("参考图已上传：%s" % json.dumps({os.path.basename(k): v for k, v in up.items()},
                                    ensure_ascii=False))

    wfs = [nb.build_t2i_ref(p["prompt"], up[p["ref"]], p["weight"], NEG,
                            p["w"], p["h"], a.steps, p["seed"], prefix="NR_CHAR/" + p["key"])
           for p in plan]

    t0 = time.time()
    res = c.run_many(wfs, raw, label=[p["key"] for p in plan])
    print("生成完成，共 %d 张，用时 %.0fs" % (len(plan), time.time() - t0))

    saved = {}
    for p, files in zip(plan, res):
        if not files:
            print("  ✗ %s 没有产出" % p["key"])
            continue
        dst = os.path.join(outdir, p["file"])
        with open(files[0], "rb") as f:
            data = f.read()
        with open(dst, "wb") as f:
            f.write(data)
        saved[p["key"]] = dst
        print("  ✓ %s" % p["file"])
    return saved


def compose(outdir, saved, title):
    """拼三张合成图：表情六宫格 / 三视图 / 总览联系表"""
    from PIL import Image, ImageDraw, ImageFont

    def font(sz):
        for f in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
            if os.path.exists(f):
                try:
                    return ImageFont.truetype(f, sz)
                except Exception:
                    pass
        return ImageFont.load_default()

    def label(draw, xy, text, sz=28):
        draw.text(xy, text, font=font(sz), fill=(30, 30, 30))

    # 1) 表情六宫格 3x2
    cells = [(k, saved.get(k)) for k in ["expr%d" % i for i in range(6)]]
    cells = [(k, v) for k, v in cells if v]
    if cells:
        S, PAD, TOP = 512, 16, 56
        W = 3 * S + 4 * PAD
        H = 2 * S + 3 * PAD + TOP
        sheet = Image.new("RGB", (W, H), (245, 245, 245))
        d = ImageDraw.Draw(sheet)
        label(d, (PAD, 14), "表情差分（同一角色 · 6 种）", 32)
        for i, (k, p) in enumerate(cells):
            r, col = divmod(i, 3)
            im = Image.open(p).convert("RGB").resize((S, S), Image.LANCZOS)
            x = PAD + col * (S + PAD)
            y = TOP + PAD + r * (S + PAD)
            sheet.paste(im, (x, y))
            label(d, (x + 10, y + 10), "%d %s" % (i + 1, EXPRESSIONS[i][0]), 26)
        sheet.save(os.path.join(outdir, "表情六宫格.png"))
        print("  ✓ 表情六宫格.png")

    # 2) 三视图
    keys = [("full_front", "正面"), ("full_side", "侧身"), ("full_back", "背面")]
    have = [(k, n, saved.get(k)) for k, n in keys if saved.get(k)]
    if have:
        W0, H0, PAD, TOP = 512, 768, 16, 56
        W = len(have) * W0 + (len(have) + 1) * PAD
        H = H0 + 2 * PAD + TOP
        sheet = Image.new("RGB", (W, H), (245, 245, 245))
        d = ImageDraw.Draw(sheet)
        label(d, (PAD, 14), "三视图（正面 / 侧身 / 背面）", 32)
        for i, (k, n, p) in enumerate(have):
            im = Image.open(p).convert("RGB").resize((W0, H0), Image.LANCZOS)
            x = PAD + i * (W0 + PAD)
            sheet.paste(im, (x, TOP + PAD))
            label(d, (x + 10, TOP + PAD + 10), n, 28)
        sheet.save(os.path.join(outdir, "三视图.png"))
        print("  ✓ 三视图.png")

    # 3) 总览联系表
    order = ["face_neutral", "face_smirk", "half", "full_front", "full_side", "full_back"] + \
            ["expr%d" % i for i in range(6)]
    items = [(k, saved.get(k)) for k in order]
    items = [(k, v) for k, v in items if v]
    if items:
        COLS, CW, CH, PAD, TOP = 4, 256, 384, 12, 56
        rows = (len(items) + COLS - 1) // COLS
        W = COLS * CW + (COLS + 1) * PAD
        H = rows * CH + (rows + 1) * PAD + TOP
        sheet = Image.new("RGB", (W, H), (250, 250, 250))
        d = ImageDraw.Draw(sheet)
        label(d, (PAD, 14), title + " · 人物资产总览", 30)
        for i, (k, p) in enumerate(items):
            r, col = divmod(i, COLS)
            im = Image.open(p).convert("RGB")
            im.thumbnail((CW, CH), Image.LANCZOS)
            x = PAD + col * (CW + PAD)
            y = TOP + PAD + r * (CH + PAD)
            sheet.paste(im, (x + (CW - im.width) // 2, y))
        sheet.save(os.path.join(outdir, "总览_联系表.png"))
        print("  ✓ 总览_联系表.png")


def write_doc(outdir, plan, a, identity, style, saved):
    lines = []
    lines.append("# 人物设定（自动生成）\n")
    lines.append("> 由 `09_工具脚本/gen_char_assets.py` 生成，%s\n" % time.strftime("%Y-%m-%d %H:%M"))
    lines.append("## 一、身份提示词块（后续所有镜头直接复制这一段）\n")
    lines.append("```text")
    lines.append(identity)
    lines.append("```\n")
    lines.append("## 二、统一反向词\n")
    lines.append("```text")
    lines.append(NEG)
    lines.append("```\n")
    lines.append("## 三、资产清单\n")
    lines.append("| 文件 | 尺寸 | IPAdapter 权重 | 种子 |")
    lines.append("|---|---|---|---|")
    for p in plan:
        mark = "" if p["key"] in saved else "（未生成）"
        lines.append("| `%s` %s | %d×%d | %.2f | %d |" %
                     (p["file"], mark, p["w"], p["h"], p["weight"], p["seed"]))
    lines.append("\n## 四、用法\n")
    lines.append("**出图**：`nr_bridge.py t2i` 的 `--prompt` 用「身份块 + 动作/场景 + 光线」，")
    lines.append("挂了参考图时**不要再写长相和服装**（防换脸，铁律 54）。\n")
    lines.append("**出视频**：首帧用上面任一张，`build_i2v` 的 prompt 只写动作 + 声景 + 配乐 + 镜头。\n")
    lines.append("**权重经验**：保脸换场景 0.45–0.55 / 同场景换机位 0.70–0.80 / 只改表情 0.85–0.90。")
    lines.append("\n## 五、风格词\n")
    lines.append("```text")
    lines.append(style)
    lines.append("```")
    with io.open(os.path.join(outdir, "00_人物设定.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("  ✓ 00_人物设定.md")


def main():
    ap = argparse.ArgumentParser(description="人物资产包生成器")
    ap.add_argument("--face", required=True, help="面部参考图（建议正方形、脸占 60%% 以上）")
    ap.add_argument("--body", default="", help="半身/全身参考图（不给就用 --face）")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--hair", default="", help="发型描述，如 'ash brown layered hair, long bangs'")
    ap.add_argument("--outfit", default="", help="服装描述，如 'black three piece suit, white shirt, black tie'")
    ap.add_argument("--look", default="", help="其他长相特征，如 'pale skin, sharp narrow eyes, thin lips'")
    ap.add_argument("--style", default="photorealistic, cinematic lighting",
                    help="画风词，默认写实；要 CG 感写 '3d render, cg, semi realistic'")
    ap.add_argument("--title", default="人物资产", help="合成图标题")
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--only", default="", choices=["", "faces", "body", "expr"])
    a = ap.parse_args()

    if not os.path.exists(a.face):
        raise SystemExit("找不到面部参考图：%s" % a.face)

    identity = ", ".join(x for x in ("1boy, male focus", a.look, a.hair, a.outfit) if x)
    plan = build_plan(a, identity, a.style)

    if a.only == "faces":
        plan = [p for p in plan if p["key"].startswith("face")]
    elif a.only == "body":
        plan = [p for p in plan if p["key"] in ("half", "full_front", "full_side", "full_back")]
    elif a.only == "expr":
        plan = [p for p in plan if p["key"].startswith("expr")]

    print("身份块：%s" % identity)
    print("画风词：%s" % a.style)
    print("计划生成 %d 张\n" % len(plan))

    saved = run_batch(plan, a.out, a)
    print()
    compose(a.out, saved, a.title)
    write_doc(a.out, plan, a, identity, a.style, saved)
    print("\n输出目录：%s" % a.out)


if __name__ == "__main__":
    main()
