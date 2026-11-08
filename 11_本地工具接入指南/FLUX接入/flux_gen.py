#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
flux_gen.py — FLUX.1-schnell GGUF 一键出图（8GB 显卡低显存方案）
依赖：仅 Python 标准库（urllib / json / time），无需 requests。
用法：
  python flux_gen.py --prompt "a man in red cape, film still, 1024" \
      --seed 1 --width 1024 --height 1024 --prefix test_flux --out result.png

它会把 flux_schnell_gguf.json 作为模板，替换提示词/尺寸/种子/输出前缀，
POST 到本机 ComfyUI(127.0.0.1:8188)，轮询结果并下载成品 PNG。
"""
import argparse
import json
import os
import time
import urllib.parse
import urllib.request
import uuid

BASE = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flux_schnell_gguf.json")


def _post(path, data):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=600) as r:
        return r.read()


def _download_file(filename, subfolder, ftype, out_path):
    q = urllib.parse.quote(filename, safe="")
    url = f"{BASE}/view?filename={q}&subfolder={urllib.parse.quote(subfolder, safe='')}&type={ftype}"
    with urllib.request.urlopen(url, timeout=600) as r, open(out_path, "wb") as f:
        f.write(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=1024)
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--prefix", default="flux_schnell")
    ap.add_argument("--out", default="flux_out.png")
    args = ap.parse_args()

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        graph = json.load(f)

    graph["5"]["inputs"]["text"] = args.prompt
    graph["7"]["inputs"].update({"width": args.width, "height": args.height})
    graph["8"]["inputs"]["seed"] = args.seed
    graph["8"]["inputs"]["steps"] = args.steps
    graph["11"]["inputs"]["filename_prefix"] = args.prefix

    client_id = str(uuid.uuid4())
    resp = _post("/prompt", {"prompt": graph, "client_id": client_id})
    prompt_id = resp["prompt_id"]
    print(f"[已入队] prompt_id = {prompt_id}  开始采样…")

    deadline = time.time() + 1800
    out_image = None
    while time.time() < deadline:
        try:
            hist = json.loads(_get(f"/history/{prompt_id}").decode("utf-8"))
        except Exception:
            time.sleep(2)
            continue
        entry = hist.get(prompt_id)
        if entry and entry.get("outputs"):
            for node_out in entry["outputs"].values():
                for img in node_out.get("images", []):
                    out_image = img
            if out_image:
                break
        time.sleep(3)

    if not out_image:
        print("[失败] 超时或未拿到输出，请检查 ComfyUI 前端报错")
        return 1

    _download_file(out_image["filename"], out_image.get("subfolder", ""),
                   out_image.get("type", "output"), args.out)
    print(f"[完成] 已保存: {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
